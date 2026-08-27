"""Billing endpoints.

Note that no endpoint accepts a total. A create request supplies descriptions,
rates, and quantities; the server derives every total. That is deliberate --
a client-supplied total makes an overcharging complaint indistinguishable from
a rounding bug.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import HospitalActor, HospitalAdmin, HospitalPath, Paging
from src.domain.enums import PaymentStatus
from src.domain.schemas.bill import BillCreateRequest, BillResponse, PaymentRecordRequest
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.services import billing_service

router = APIRouter(tags=["bills"])


@router.post(
    "/hospitals/{hospital_id}/bills",
    response_model=ApiResponse[BillResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_bill(
    hospital_id: HospitalPath,
    request: Annotated[BillCreateRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[BillResponse]:
    """Raise an itemised invoice against a case."""
    bill = await billing_service.create_bill(hospital_id, request, actor)
    return ApiResponse.ok(BillResponse.model_validate(bill))


@router.get(
    "/hospitals/{hospital_id}/bills",
    response_model=ApiResponse[PaginatedResponse[BillResponse]],
)
async def list_bills(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    payment_status: Annotated[PaymentStatus | None, Query()] = None,
    patient_id: Annotated[PydanticObjectId | None, Query()] = None,
    case_id: Annotated[PydanticObjectId | None, Query()] = None,
) -> ApiResponse[PaginatedResponse[BillResponse]]:
    """Return invoices, newest first."""
    bills = await billing_service.list_bills(
        hospital_id,
        actor,
        payment_status=payment_status,
        patient_id=patient_id,
        case_id=case_id,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await billing_service.count_bills(
        hospital_id,
        actor,
        payment_status=payment_status,
        patient_id=patient_id,
        case_id=case_id,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[BillResponse.model_validate(bill) for bill in bills],
            meta=paging.meta(total),
        )
    )


@router.get("/bills/{bill_id}", response_model=ApiResponse[BillResponse])
async def read_bill(
    bill_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[BillResponse]:
    """Return one invoice, with every line item -- the printable receipt view."""
    bill = await billing_service.get_bill(bill_id, actor)
    return ApiResponse.ok(BillResponse.model_validate(bill))


@router.post("/bills/{bill_id}/payments", response_model=ApiResponse[BillResponse])
async def record_payment(
    bill_id: PydanticObjectId,
    request: Annotated[PaymentRecordRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[BillResponse]:
    """Record a payment.

    Partial payments accumulate; the invoice becomes ``PAID`` only when the
    running total reaches the grand total exactly.
    """
    bill = await billing_service.record_payment(bill_id, request, actor)
    return ApiResponse.ok(BillResponse.model_validate(bill))


@router.post("/bills/{bill_id}/cancel", response_model=ApiResponse[BillResponse])
async def cancel_bill(
    bill_id: PydanticObjectId,
    actor: HospitalAdmin,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> ApiResponse[BillResponse]:
    """Cancel an unpaid invoice.

    An invoice that has taken money cannot be cancelled; it must be refunded,
    which leaves the payment trail intact.
    """
    bill = await billing_service.void_bill(bill_id, actor, reason)
    return ApiResponse.ok(BillResponse.model_validate(bill))
