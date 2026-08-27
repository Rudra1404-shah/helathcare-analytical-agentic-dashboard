"""Itemised invoicing and payment settlement.

Totals are derived here, never accepted from the client. A request supplies
descriptions, rates, and quantities; the line total, subtotal, and grand total
are all computed server-side through :func:`~src.domain.models.bill.money`.
Letting a caller post its own totals would make an overcharging complaint
indistinguishable from a rounding bug.
"""

from decimal import Decimal

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import ConflictError
from src.domain.enums import PaymentStatus
from src.domain.models import Bill, PatientCase, User
from src.domain.models.base import utcnow
from src.domain.models.bill import money
from src.domain.schemas.bill import BillCreateRequest, PaymentRecordRequest
from src.services.common import (
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "count_bills",
    "create_bill",
    "get_bill",
    "list_bills",
    "record_payment",
    "void_bill",
]

_COLLECTION = "bills"


async def create_bill(
    hospital_id: PydanticObjectId,
    request: BillCreateRequest,
    actor: User,
) -> Bill:
    """Raise an invoice against a case.

    Raises:
        ConflictError: If the invoice number is taken at this hospital, or the
            case does not belong to it.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "bill")
    case = await _require_case(request.case_id, hospital_id)

    if case.patient_id != request.patient_id:
        msg = (
            f"case {case.case_number} belongs to patient {case.patient_id}, "
            f"not {request.patient_id}"
        )
        raise ConflictError(msg)

    line_items = [item.to_line_item() for item in request.line_items]
    subtotal = money(sum((item.total for item in line_items), Decimal("0")))
    grand_total = money(subtotal + request.tax_amount - request.discount_amount)

    try:
        bill = Bill(
            invoice_no=request.invoice_no,
            hospital_id=hospital_id,
            case_id=request.case_id,
            patient_id=request.patient_id,
            line_items=line_items,
            subtotal=subtotal,
            tax_amount=request.tax_amount,
            discount_amount=request.discount_amount,
            grand_total=grand_total,
            payment_mode=request.payment_mode,
            payment_status=(
                PaymentStatus.PAID if grand_total == Decimal("0.00") else PaymentStatus.PENDING
            ),
            amount_paid=Decimal("0.00"),
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        bill.insert,
        f"invoice number {request.invoice_no} is already issued at this hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=bill.id,
        hospital_id=hospital_id,
        detail=f"invoice {request.invoice_no} for {grand_total}",
    )
    return bill


async def get_bill(bill_id: PydanticObjectId, actor: User) -> Bill:
    """Fetch one invoice, enforcing hospital scope."""
    bill = await get_or_404(Bill, bill_id, "bill")
    ensure_hospital_match(bill.hospital_id, hospital_scope_of(actor), "bill")

    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=bill.id,
        hospital_id=bill.hospital_id,
    )
    return bill


async def list_bills(
    hospital_id: PydanticObjectId,
    actor: User,
    payment_status: PaymentStatus | None = None,
    patient_id: PydanticObjectId | None = None,
    case_id: PydanticObjectId | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Bill]:
    """Return invoices, newest first."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "bill")
    query = _bill_query(hospital_id, payment_status, patient_id, case_id)
    return await Bill.find(query).sort("-issued_at").skip(skip).limit(limit).to_list()


async def count_bills(
    hospital_id: PydanticObjectId,
    actor: User,
    payment_status: PaymentStatus | None = None,
    patient_id: PydanticObjectId | None = None,
    case_id: PydanticObjectId | None = None,
) -> int:
    """Return how many invoices match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "bill")
    return await Bill.find(_bill_query(hospital_id, payment_status, patient_id, case_id)).count()


async def record_payment(
    bill_id: PydanticObjectId,
    request: PaymentRecordRequest,
    actor: User,
) -> Bill:
    """Apply a payment, moving the invoice through its settlement states.

    Partial payments accumulate; the status becomes ``PAID`` only when the
    running total reaches the grand total exactly, which is why money is
    ``Decimal`` throughout.

    Raises:
        ConflictError: If the invoice is already settled or cancelled, or the
            payment would overshoot the balance due.
    """
    bill = await get_or_404(Bill, bill_id, "bill")
    ensure_hospital_match(bill.hospital_id, hospital_scope_of(actor), "bill")

    if bill.payment_status in {PaymentStatus.CANCELLED, PaymentStatus.REFUNDED}:
        msg = f"invoice {bill.invoice_no} is {bill.payment_status} and cannot take a payment"
        raise ConflictError(msg)
    if bill.payment_status is PaymentStatus.PAID:
        msg = f"invoice {bill.invoice_no} is already paid in full"
        raise ConflictError(msg)

    updated_paid = money(bill.amount_paid + request.amount)
    if updated_paid > bill.grand_total:
        msg = (
            f"payment of {request.amount} exceeds the balance due on invoice "
            f"{bill.invoice_no}: {bill.balance_due} remains"
        )
        raise ConflictError(msg)

    settled = updated_paid == bill.grand_total
    try:
        bill.amount_paid = updated_paid
        bill.payment_status = PaymentStatus.PAID if settled else PaymentStatus.PARTIALLY_PAID
        bill.payment_mode = request.payment_mode
        if settled:
            bill.settled_at = request.paid_at or utcnow()
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    bill.touch()
    await bill.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=bill.id,
        hospital_id=bill.hospital_id,
        detail=f"paid {request.amount} via {request.payment_mode}; status {bill.payment_status}",
    )
    return bill


async def void_bill(bill_id: PydanticObjectId, actor: User, reason: str) -> Bill:
    """Cancel an unpaid invoice.

    An invoice that has taken money cannot be cancelled -- it must be refunded,
    which leaves the payment trail intact.

    Raises:
        ConflictError: If any amount has already been paid.
    """
    bill = await get_or_404(Bill, bill_id, "bill")
    ensure_hospital_match(bill.hospital_id, hospital_scope_of(actor), "bill")

    if bill.amount_paid > Decimal("0.00"):
        msg = (
            f"invoice {bill.invoice_no} has taken {bill.amount_paid} and cannot be "
            f"cancelled; issue a refund instead so the payment trail survives"
        )
        raise ConflictError(msg)

    bill.payment_status = PaymentStatus.CANCELLED
    bill.touch()
    await bill.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=bill.id,
        hospital_id=bill.hospital_id,
        detail=f"cancelled: {reason}",
    )
    return bill


async def bills_for_patient(patient_id: PydanticObjectId) -> list[Bill]:
    """Return every invoice raised for one patient record, newest first.

    Used by the PHR assembler, which reads across hospitals and therefore
    applies no tenancy filter of its own.
    """
    return await Bill.find(Bill.patient_id == patient_id).sort("-issued_at").to_list()


async def _require_case(
    case_id: PydanticObjectId,
    hospital_id: PydanticObjectId,
) -> PatientCase:
    """Reject an invoice raised against another hospital's case."""
    case = await PatientCase.get(case_id)
    if case is None or case.hospital_id != hospital_id:
        msg = f"case {case_id} does not belong to this hospital"
        raise ConflictError(msg)
    return case


def _bill_query(
    hospital_id: PydanticObjectId,
    payment_status: PaymentStatus | None,
    patient_id: PydanticObjectId | None,
    case_id: PydanticObjectId | None,
) -> dict[str, object]:
    """Build the invoice filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if payment_status is not None:
        query["payment_status"] = payment_status.value
    if patient_id is not None:
        query["patient_id"] = patient_id
    if case_id is not None:
        query["case_id"] = case_id
    return query
