"""Patient admissions, triage, vitals, and discharge.

This is the highest-volume workflow in the platform and the primary feed for
the real-time monitoring, surge-forecasting, and outbreak-detection modules.

Admission and discharge move bed inventory as well as case state. MongoDB
transactions need a replica set, which a single-node development deployment does
not have, so the two writes are ordered to fail safe instead: the bed is
reserved *before* the case is created, and released again if case creation
fails. The worst outcome is a bed briefly held by nobody, which a human can see
and correct -- rather than a case occupying a bed the inventory says is free.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import ConflictError
from src.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus, InventoryCategory, TriageLevel
from src.domain.models import (
    CaseType,
    Department,
    Doctor,
    InventoryItem,
    Patient,
    PatientCase,
    Prescription,
    User,
    VitalSigns,
)
from src.domain.models.base import utcnow
from src.domain.schemas.inventory import InventoryStockAdjustmentRequest
from src.domain.schemas.patient_case import (
    CaseAdmissionRequest,
    CaseDischargeRequest,
    CaseStatusUpdateRequest,
    PrescriptionRequest,
    VitalSignsRequest,
)
from src.services import inventory_service
from src.services.common import (
    apply_atomic_update,
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "add_prescription",
    "admit_patient",
    "count_cases",
    "discharge_case",
    "get_case",
    "list_cases",
    "record_vitals",
    "triage_board",
    "update_case",
]

_COLLECTION = "patient_cases"

_BED_CATEGORY_FOR_STATUS: dict[CaseStatus, InventoryCategory] = {
    CaseStatus.ICU: InventoryCategory.ICU_BEDS,
    CaseStatus.ADMITTED: InventoryCategory.GENERAL_BEDS,
    CaseStatus.OBSERVATION: InventoryCategory.GENERAL_BEDS,
}
"""Which bed pool an open case draws from, by its status."""


async def admit_patient(
    hospital_id: PydanticObjectId,
    request: CaseAdmissionRequest,
    actor: User,
) -> PatientCase:
    """Open a case, reserving a bed from the matching inventory pool.

    Raises:
        ConflictError: If the case number is taken, a referenced record belongs
            to another hospital, or no bed of the required kind is free.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "case")
    await _require_references(hospital_id, request)

    triage_level = request.triage_level or await _triage_from_case_type(request.case_type_id)
    bed_item = await _reserve_bed(hospital_id, request.status, actor)

    try:
        case = PatientCase(
            case_number=request.case_number,
            hospital_id=hospital_id,
            patient_id=request.patient_id,
            doctor_id=request.doctor_id,
            department_id=request.department_id,
            case_type_id=request.case_type_id,
            bed_allocated=request.bed_allocated,
            triage_level=triage_level,
            admitted_at=request.admitted_at or utcnow(),
            chief_symptoms=list(request.chief_symptoms),
            vitals=[_to_vitals(request.initial_vitals)] if request.initial_vitals else [],
            status=request.status,
        )
        await guard_duplicate(
            case.insert,
            f"case number {request.case_number} is already open at this hospital",
        )
    except ValidationError as exc:
        await _release_bed(bed_item, actor, "admission failed validation")
        raise translate_validation_error(exc) from exc
    except Exception:
        await _release_bed(bed_item, actor, "admission failed")
        raise

    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case.id,
        hospital_id=hospital_id,
        detail=f"admitted as {request.status}, triage {triage_level}",
    )
    return case


async def get_case(case_id: PydanticObjectId, actor: User) -> PatientCase:
    """Fetch one case, enforcing hospital scope and emitting a read event."""
    case = await get_or_404(PatientCase, case_id, "case")
    ensure_hospital_match(case.hospital_id, hospital_scope_of(actor), "case")

    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case.id,
        hospital_id=case.hospital_id,
    )
    return case


async def list_cases(
    hospital_id: PydanticObjectId,
    actor: User,
    status: CaseStatus | None = None,
    patient_id: PydanticObjectId | None = None,
    doctor_id: PydanticObjectId | None = None,
    department_id: PydanticObjectId | None = None,
    triage_level: TriageLevel | None = None,
    open_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> list[PatientCase]:
    """Return cases, newest admission first."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "case")
    query = _case_query(
        hospital_id, status, patient_id, doctor_id, department_id, triage_level, open_only
    )
    cases = await PatientCase.find(query).sort("-admitted_at").skip(skip).limit(limit).to_list()

    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        hospital_id=hospital_id,
        detail=f"listed {len(cases)} cases",
    )
    return cases


async def count_cases(
    hospital_id: PydanticObjectId,
    actor: User,
    status: CaseStatus | None = None,
    patient_id: PydanticObjectId | None = None,
    doctor_id: PydanticObjectId | None = None,
    department_id: PydanticObjectId | None = None,
    triage_level: TriageLevel | None = None,
    open_only: bool = False,
) -> int:
    """Return how many cases match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "case")
    query = _case_query(
        hospital_id, status, patient_id, doctor_id, department_id, triage_level, open_only
    )
    return await PatientCase.find(query).count()


async def triage_board(
    hospital_id: PydanticObjectId,
    actor: User,
) -> dict[str, list[PatientCase]]:
    """Group open cases by triage level, most urgent first.

    Cases with no triage assigned are grouped under ``"UNTRIAGED"`` rather than
    dropped -- an unclassified patient is exactly the one a charge nurse needs
    to see.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "case")
    open_cases = (
        await PatientCase.find(
            {
                "hospital_id": hospital_id,
                "status": {"$nin": [s.value for s in TERMINAL_CASE_STATUSES]},
            }
        )
        .sort("+admitted_at")
        .to_list()
    )

    board: dict[str, list[PatientCase]] = {}
    for level in sorted(TriageLevel, key=int):
        matching = [case for case in open_cases if case.triage_level is level]
        if matching:
            board[level.name] = matching

    untriaged = [case for case in open_cases if case.triage_level is None]
    if untriaged:
        board["UNTRIAGED"] = untriaged
    return board


async def update_case(
    case_id: PydanticObjectId,
    request: CaseStatusUpdateRequest,
    actor: User,
) -> PatientCase:
    """Move an open case between states, or reassign its bed or doctor.

    Moving between ICU and a general ward swaps which inventory pool the case
    draws from, so the old bed is released and a new one reserved.
    """
    case = await get_or_404(PatientCase, case_id, "case")
    ensure_hospital_match(case.hospital_id, hospital_scope_of(actor), "case")

    if not case.is_open:
        msg = f"case {case.case_number} is already closed as {case.status} and cannot be reopened"
        raise ConflictError(msg)

    if request.doctor_id is not None:
        await _require_doctor(request.doctor_id, case.hospital_id)
    if request.case_type_id is not None:
        await _require_case_type(request.case_type_id, case.hospital_id)

    if request.status is not None and request.status is not case.status:
        await _move_bed(case, request.status, actor)

    changes: dict[str, object] = {
        "status": request.status,
        "bed_allocated": request.bed_allocated,
        "doctor_id": request.doctor_id,
        "case_type_id": request.case_type_id,
        "triage_level": request.triage_level,
    }
    if apply_partial_update(case, changes):
        case.touch()
        await case.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case.id,
        hospital_id=case.hospital_id,
    )
    return case


async def record_vitals(
    case_id: PydanticObjectId,
    request: VitalSignsRequest,
    actor: User,
) -> PatientCase:
    """Append a set of bedside observations.

    Vitals accumulate as a list because deterioration is only visible as a
    trend; nothing here overwrites an earlier reading.
    """
    case = await _open_case(case_id, actor)

    try:
        case.vitals = [*case.vitals, _to_vitals(request)]
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    case.touch()
    await case.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case.id,
        hospital_id=case.hospital_id,
        detail="vitals recorded",
    )
    return case


async def add_prescription(
    case_id: PydanticObjectId,
    request: PrescriptionRequest,
    actor: User,
) -> PatientCase:
    """Append a medication order to an open case."""
    case = await _open_case(case_id, actor)

    try:
        case.prescriptions = [
            *case.prescriptions,
            Prescription(
                medicine_name=request.medicine_name,
                dosage=request.dosage,
                frequency=request.frequency,
                duration_days=request.duration_days,
                notes=request.notes,
            ),
        ]
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    case.touch()
    await case.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case.id,
        hospital_id=case.hospital_id,
        detail=f"prescribed {request.medicine_name}",
    )
    return case


async def discharge_case(
    case_id: PydanticObjectId,
    request: CaseDischargeRequest,
    actor: User,
) -> PatientCase:
    """Close a case and release its bed back to the inventory pool.

    Raises:
        ConflictError: If the case is already closed, or discharge would
            precede admission.
    """
    case = await _open_case(case_id, actor)
    discharged_at = request.discharged_at or utcnow()

    if discharged_at < case.admitted_at:
        msg = (
            f"discharge at {discharged_at.isoformat()} precedes admission at "
            f"{case.admitted_at.isoformat()}"
        )
        raise ConflictError(msg)

    previous_status = case.status
    # Status and discharge details must move together: either alone is invalid,
    # so they are validated as one transition rather than field by field.
    closed = apply_atomic_update(
        case,
        {
            "discharged_at": discharged_at,
            "discharge_summary": request.discharge_summary,
            "status": request.status,
            "updated_at": utcnow(),
        },
    )
    await closed.save()
    await _release_bed_for_status(closed.hospital_id, previous_status, actor, "case discharged")

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=closed.id,
        hospital_id=closed.hospital_id,
        detail=f"closed as {request.status}",
    )
    return closed


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
async def _open_case(case_id: PydanticObjectId, actor: User) -> PatientCase:
    """Fetch a case that must still be open."""
    case = await get_or_404(PatientCase, case_id, "case")
    ensure_hospital_match(case.hospital_id, hospital_scope_of(actor), "case")
    if not case.is_open:
        msg = f"case {case.case_number} is closed as {case.status} and cannot be amended"
        raise ConflictError(msg)
    return case


def _to_vitals(request: VitalSignsRequest) -> VitalSigns:
    """Convert a vitals payload into the stored value object."""
    return VitalSigns(
        systolic_bp=request.systolic_bp,
        diastolic_bp=request.diastolic_bp,
        pulse_bpm=request.pulse_bpm,
        spo2_percent=request.spo2_percent,
        temperature_celsius=request.temperature_celsius,
        respiratory_rate=request.respiratory_rate,
        recorded_at=request.recorded_at or utcnow(),
    )


async def _require_references(
    hospital_id: PydanticObjectId,
    request: CaseAdmissionRequest,
) -> None:
    """Confirm every referenced record belongs to this hospital."""
    patient = await Patient.get(request.patient_id)
    if patient is None or patient.hospital_id != hospital_id:
        msg = f"patient {request.patient_id} is not registered at this hospital"
        raise ConflictError(msg)

    await _require_doctor(request.doctor_id, hospital_id)

    department = await Department.get(request.department_id)
    if department is None or department.hospital_id != hospital_id:
        msg = f"department {request.department_id} does not belong to this hospital"
        raise ConflictError(msg)

    if request.case_type_id is not None:
        await _require_case_type(request.case_type_id, hospital_id)


async def _require_doctor(doctor_id: PydanticObjectId, hospital_id: PydanticObjectId) -> None:
    """Reject an attending doctor who does not work at this hospital."""
    doctor = await Doctor.get(doctor_id)
    if doctor is None or doctor.hospital_id != hospital_id:
        msg = f"doctor {doctor_id} is not onboarded at this hospital"
        raise ConflictError(msg)


async def _require_case_type(
    case_type_id: PydanticObjectId,
    hospital_id: PydanticObjectId,
) -> None:
    """Reject a case type scoped to a different hospital.

    A national standard -- ``hospital_id`` of ``None`` -- is always acceptable.
    """
    case_type = await CaseType.get(case_type_id)
    if case_type is None:
        msg = f"case type {case_type_id} does not exist"
        raise ConflictError(msg)
    if case_type.hospital_id is not None and case_type.hospital_id != hospital_id:
        msg = f"case type {case_type_id} belongs to another hospital"
        raise ConflictError(msg)


async def _triage_from_case_type(case_type_id: PydanticObjectId | None) -> TriageLevel | None:
    """Inherit the triage level from the classified case type, when there is one."""
    if case_type_id is None:
        return None
    case_type = await CaseType.get(case_type_id)
    return case_type.triage_level if case_type else None


async def _reserve_bed(
    hospital_id: PydanticObjectId,
    status: CaseStatus,
    actor: User,
) -> PydanticObjectId | None:
    """Consume one unit from the bed pool this status draws on.

    Returns the inventory line drawn from, so the caller can put the unit back
    if the admission then fails. ``None`` means the hospital tracks no such
    pool, which is not an error -- a hospital may run its beds outside the
    inventory module.
    """
    category = _BED_CATEGORY_FOR_STATUS.get(status)
    if category is None:
        return None

    item = await inventory_service.find_allocatable_bed(hospital_id, category)
    if item is None:
        if await _tracks_category(hospital_id, category):
            msg = f"no {category} are available at this hospital; admission refused"
            raise ConflictError(msg)
        return None

    await inventory_service.adjust_stock(
        _require_item_id(item.id),
        InventoryStockAdjustmentRequest(delta=-1, reason="bed allocated to admission"),
        actor,
    )
    return item.id


async def _release_bed(
    item_id: PydanticObjectId | None,
    actor: User,
    reason: str,
) -> None:
    """Return one unit to a bed pool, ignoring a pool that no longer exists."""
    if item_id is None:
        return
    try:
        await inventory_service.adjust_stock(
            item_id,
            InventoryStockAdjustmentRequest(delta=1, reason=reason),
            actor,
        )
    except ConflictError:
        # The pool is already at capacity; nothing to give back.
        return


async def _release_bed_for_status(
    hospital_id: PydanticObjectId,
    status: CaseStatus,
    actor: User,
    reason: str,
) -> None:
    """Return a unit to whichever pool the given status drew from."""
    category = _BED_CATEGORY_FOR_STATUS.get(status)
    if category is None:
        return

    item = await InventoryItem.find_one(
        {"hospital_id": hospital_id, "category": category.value, "is_active": True}
    )
    if item is not None and item.id is not None:
        await _release_bed(item.id, actor, reason)


async def _move_bed(case: PatientCase, new_status: CaseStatus, actor: User) -> None:
    """Swap the case between bed pools when its status changes ward."""
    old_category = _BED_CATEGORY_FOR_STATUS.get(case.status)
    new_category = _BED_CATEGORY_FOR_STATUS.get(new_status)
    if old_category is new_category:
        return

    reserved = await _reserve_bed(case.hospital_id, new_status, actor)
    if reserved is not None or new_category is None:
        await _release_bed_for_status(
            case.hospital_id, case.status, actor, f"moved from {case.status} to {new_status}"
        )


async def _tracks_category(hospital_id: PydanticObjectId, category: InventoryCategory) -> bool:
    """Return whether the hospital tracks this category at all."""
    return (
        await InventoryItem.find(
            {"hospital_id": hospital_id, "category": category.value, "is_active": True}
        ).count()
        > 0
    )


def _require_item_id(item_id: PydanticObjectId | None) -> PydanticObjectId:
    """Return a persisted inventory line's id, or fail loudly."""
    if item_id is None:
        msg = "inventory line has no id; it was never persisted"
        raise ConflictError(msg)
    return item_id


def _case_query(
    hospital_id: PydanticObjectId,
    status: CaseStatus | None,
    patient_id: PydanticObjectId | None,
    doctor_id: PydanticObjectId | None,
    department_id: PydanticObjectId | None,
    triage_level: TriageLevel | None,
    open_only: bool,
) -> dict[str, object]:
    """Build the case filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if status is not None:
        query["status"] = status.value
    elif open_only:
        query["status"] = {"$nin": [state.value for state in TERMINAL_CASE_STATUSES]}
    if patient_id is not None:
        query["patient_id"] = patient_id
    if doctor_id is not None:
        query["doctor_id"] = doctor_id
    if department_id is not None:
        query["department_id"] = department_id
    if triage_level is not None:
        query["triage_level"] = int(triage_level)
    return query
