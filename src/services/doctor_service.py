"""Doctor onboarding and availability.

Doctors are a separate collection from staff because they carry medical council
licences, specialisations, and a daily patient cap. That cap is the signal the
future workforce-reallocation module reads, so it is maintained here rather
than inferred from case volume.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.config import Settings, get_settings
from src.core.errors import ConflictError
from src.domain.enums import ShiftType, StaffStatus
from src.domain.models import Department, Doctor, ProtectedNationalId, User
from src.domain.schemas.doctor import DoctorOnboardingRequest, DoctorUpdateRequest
from src.services.common import (
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "count_doctors",
    "get_doctor",
    "list_doctors",
    "onboard_doctor",
    "update_doctor",
]

_COLLECTION = "doctors"


async def onboard_doctor(
    hospital_id: PydanticObjectId,
    request: DoctorOnboardingRequest,
    actor: User,
    settings: Settings | None = None,
) -> Doctor:
    """File a Doctor Onboarding Form.

    Raises:
        ConflictError: If the council licence is already registered anywhere on
            the platform, or the department belongs to another hospital.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "doctor")
    await _require_department_in_hospital(request.department_id, hospital_id)

    active = settings or get_settings()
    protected = (
        ProtectedNationalId.protect(request.national_id, active) if request.national_id else None
    )

    try:
        doctor = Doctor(
            hospital_id=hospital_id,
            full_name=request.full_name,
            license_no=request.license_no,
            specialization=request.specialization,
            department_id=request.department_id,
            qualification=request.qualification,
            phone=request.phone,
            email=request.email,
            national_id=protected,
            employment_type=request.employment_type,
            shifts=request.shifts,
            max_daily_patients=request.max_daily_patients,
            is_emergency_on_call=request.is_emergency_on_call,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        doctor.insert,
        f"medical licence {request.license_no} is already registered to another doctor",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=doctor.id,
        hospital_id=hospital_id,
    )
    return doctor


async def get_doctor(doctor_id: PydanticObjectId, actor: User) -> Doctor:
    """Fetch one doctor, enforcing hospital scope."""
    doctor = await get_or_404(Doctor, doctor_id, "doctor")
    ensure_hospital_match(doctor.hospital_id, hospital_scope_of(actor), "doctor")
    return doctor


async def list_doctors(
    hospital_id: PydanticObjectId,
    actor: User,
    department_id: PydanticObjectId | None = None,
    specialization: str | None = None,
    shift: ShiftType | None = None,
    status: StaffStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Doctor]:
    """Return the doctor roster for a hospital."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "doctor")
    query = _doctor_query(hospital_id, department_id, specialization, shift, status)
    return await Doctor.find(query).sort("+full_name").skip(skip).limit(limit).to_list()


async def count_doctors(
    hospital_id: PydanticObjectId,
    actor: User,
    department_id: PydanticObjectId | None = None,
    specialization: str | None = None,
    shift: ShiftType | None = None,
    status: StaffStatus | None = None,
) -> int:
    """Return how many doctors match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "doctor")
    query = _doctor_query(hospital_id, department_id, specialization, shift, status)
    return await Doctor.find(query).count()


async def update_doctor(
    doctor_id: PydanticObjectId,
    request: DoctorUpdateRequest,
    actor: User,
) -> Doctor:
    """Apply a partial update. The council licence number is immutable."""
    doctor = await get_or_404(Doctor, doctor_id, "doctor")
    ensure_hospital_match(doctor.hospital_id, hospital_scope_of(actor), "doctor")

    if request.department_id is not None:
        await _require_department_in_hospital(request.department_id, doctor.hospital_id)

    changes: dict[str, object] = {
        "specialization": request.specialization,
        "department_id": request.department_id,
        "phone": request.phone,
        "email": request.email,
        "employment_type": request.employment_type,
        "shifts": request.shifts,
        "max_daily_patients": request.max_daily_patients,
        "is_emergency_on_call": request.is_emergency_on_call,
        "status": request.status,
    }
    if apply_partial_update(doctor, changes):
        doctor.touch()
        await doctor.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=doctor.id,
        hospital_id=doctor.hospital_id,
    )
    return doctor


def _doctor_query(
    hospital_id: PydanticObjectId,
    department_id: PydanticObjectId | None,
    specialization: str | None,
    shift: ShiftType | None,
    status: StaffStatus | None,
) -> dict[str, object]:
    """Build the roster filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if department_id is not None:
        query["department_id"] = department_id
    if specialization:
        query["specialization"] = specialization
    if shift is not None:
        query["shifts"] = shift.value
    if status is not None:
        query["status"] = status.value
    return query


async def _require_department_in_hospital(
    department_id: PydanticObjectId,
    hospital_id: PydanticObjectId,
) -> None:
    """Reject a doctor assigned to another hospital's department."""
    department = await Department.get(department_id)
    if department is None or department.hospital_id != hospital_id:
        msg = f"department {department_id} does not belong to this hospital"
        raise ConflictError(msg)
