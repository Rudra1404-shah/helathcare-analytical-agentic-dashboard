"""Department registry and the hospital staff hierarchy.

The two staff intake forms -- Admin & Support, and Medical -- resolve to one
``staff`` collection discriminated by ``staff_category``. The category is
derived here from the submitted role rather than trusted from the client, so a
Cleaner filed on the medical form cannot inflate clinical staffing counts even
if the request schema were bypassed.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.config import Settings, get_settings
from src.core.errors import ConflictError
from src.domain.enums import ShiftType, StaffCategory, StaffRole, StaffStatus
from src.domain.models import Department, Doctor, ProtectedNationalId, Staff, User
from src.domain.schemas.department import DepartmentCreateRequest, DepartmentUpdateRequest
from src.domain.schemas.staff import (
    AdminSupportStaffIntakeRequest,
    MedicalStaffIntakeRequest,
    StaffUpdateRequest,
)
from src.services.common import (
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "count_staff",
    "create_department",
    "get_department",
    "get_staff",
    "intake_admin_support_staff",
    "intake_medical_staff",
    "list_departments",
    "list_staff",
    "staff_hierarchy",
    "update_department",
    "update_staff",
]

_DEPARTMENTS = "departments"
_STAFF = "staff"


# --------------------------------------------------------------------------- #
# Departments
# --------------------------------------------------------------------------- #
async def create_department(
    hospital_id: PydanticObjectId,
    request: DepartmentCreateRequest,
    actor: User,
) -> Department:
    """Register a department inside a hospital.

    Raises:
        ConflictError: If the code is already used in this hospital, or the
            nominated head of department is not a doctor here.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "department")
    if request.hod_doctor_id is not None:
        await _require_doctor_in_hospital(request.hod_doctor_id, hospital_id)

    try:
        department = Department(
            hospital_id=hospital_id,
            name=request.name,
            code=request.code,
            floor=request.floor,
            wing=request.wing,
            hod_doctor_id=request.hod_doctor_id,
            bed_count=request.bed_count,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        department.insert,
        f"department code {request.code} is already registered at this hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _DEPARTMENTS,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=department.id,
        hospital_id=hospital_id,
    )
    return department


async def get_department(department_id: PydanticObjectId, actor: User) -> Department:
    """Fetch one department, enforcing hospital scope."""
    department = await get_or_404(Department, department_id, "department")
    ensure_hospital_match(department.hospital_id, hospital_scope_of(actor), "department")
    return department


async def list_departments(
    hospital_id: PydanticObjectId,
    actor: User,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Department]:
    """Return a hospital's department registry."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "department")
    query: dict[str, object] = {"hospital_id": hospital_id}
    if is_active is not None:
        query["is_active"] = is_active
    return await Department.find(query).sort("+name").skip(skip).limit(limit).to_list()


async def count_departments(
    hospital_id: PydanticObjectId,
    actor: User,
    is_active: bool | None = None,
) -> int:
    """Return how many departments match."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "department")
    query: dict[str, object] = {"hospital_id": hospital_id}
    if is_active is not None:
        query["is_active"] = is_active
    return await Department.find(query).count()


async def update_department(
    department_id: PydanticObjectId,
    request: DepartmentUpdateRequest,
    actor: User,
) -> Department:
    """Apply a partial update. The department code is immutable."""
    department = await get_or_404(Department, department_id, "department")
    ensure_hospital_match(department.hospital_id, hospital_scope_of(actor), "department")

    if request.hod_doctor_id is not None:
        await _require_doctor_in_hospital(request.hod_doctor_id, department.hospital_id)

    changes: dict[str, object] = {
        "name": request.name,
        "floor": request.floor,
        "wing": request.wing,
        "hod_doctor_id": request.hod_doctor_id,
        "bed_count": request.bed_count,
        "is_active": request.is_active,
    }
    if apply_partial_update(department, changes):
        department.touch()
        await department.save()

    audit_event(
        AuditAction.UPDATE,
        _DEPARTMENTS,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=department.id,
        hospital_id=department.hospital_id,
    )
    return department


# --------------------------------------------------------------------------- #
# Staff
# --------------------------------------------------------------------------- #
async def intake_admin_support_staff(
    hospital_id: PydanticObjectId,
    request: AdminSupportStaffIntakeRequest,
    actor: User,
    settings: Settings | None = None,
) -> Staff:
    """File an Admin & Support Staff Intake Form."""
    return await _intake_staff(
        hospital_id=hospital_id,
        actor=actor,
        full_name=request.full_name,
        employee_id=request.employee_id,
        phone=request.phone,
        national_id=request.national_id,
        role=request.role,
        registration_no=None,
        department_id=request.department_id,
        assigned_ward_area=request.assigned_ward_area,
        shift=request.shift,
        status=request.status,
        is_emergency_on_call=False,
        settings=settings,
    )


async def intake_medical_staff(
    hospital_id: PydanticObjectId,
    request: MedicalStaffIntakeRequest,
    actor: User,
    settings: Settings | None = None,
) -> Staff:
    """File a Medical Staff Intake Form."""
    return await _intake_staff(
        hospital_id=hospital_id,
        actor=actor,
        full_name=request.full_name,
        employee_id=request.employee_id,
        phone=request.phone,
        national_id=request.national_id,
        role=request.role,
        registration_no=request.registration_no,
        department_id=request.department_id,
        assigned_ward_area=request.assigned_ward_area,
        shift=request.shift,
        status=request.status,
        is_emergency_on_call=request.is_emergency_on_call,
        settings=settings,
    )


async def get_staff(staff_id: PydanticObjectId, actor: User) -> Staff:
    """Fetch one staff record, enforcing hospital scope."""
    staff = await get_or_404(Staff, staff_id, "staff member")
    ensure_hospital_match(staff.hospital_id, hospital_scope_of(actor), "staff member")
    return staff


async def list_staff(
    hospital_id: PydanticObjectId,
    actor: User,
    staff_category: StaffCategory | None = None,
    role: StaffRole | None = None,
    shift: ShiftType | None = None,
    department_id: PydanticObjectId | None = None,
    status: StaffStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Staff]:
    """Return the workforce roster, filtered as the roster view requires."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "staff member")
    query = _staff_query(hospital_id, staff_category, role, shift, department_id, status)
    return await Staff.find(query).sort("+full_name").skip(skip).limit(limit).to_list()


async def count_staff(
    hospital_id: PydanticObjectId,
    actor: User,
    staff_category: StaffCategory | None = None,
    role: StaffRole | None = None,
    shift: ShiftType | None = None,
    department_id: PydanticObjectId | None = None,
    status: StaffStatus | None = None,
) -> int:
    """Return how many staff match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "staff member")
    query = _staff_query(hospital_id, staff_category, role, shift, department_id, status)
    return await Staff.find(query).count()


async def update_staff(
    staff_id: PydanticObjectId,
    request: StaffUpdateRequest,
    actor: User,
) -> Staff:
    """Apply a partial update to a staff record."""
    staff = await get_or_404(Staff, staff_id, "staff member")
    ensure_hospital_match(staff.hospital_id, hospital_scope_of(actor), "staff member")

    if request.department_id is not None:
        await _require_department_in_hospital(request.department_id, staff.hospital_id)

    changes: dict[str, object] = {
        "phone": request.phone,
        "department_id": request.department_id,
        "assigned_ward_area": request.assigned_ward_area,
        "shift": request.shift,
        "is_emergency_on_call": request.is_emergency_on_call,
        "status": request.status,
    }
    if apply_partial_update(staff, changes):
        staff.touch()
        await staff.save()

    audit_event(
        AuditAction.UPDATE,
        _STAFF,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=staff.id,
        hospital_id=staff.hospital_id,
    )
    return staff


async def staff_hierarchy(
    hospital_id: PydanticObjectId,
    actor: User,
    shift: ShiftType | None = None,
) -> dict[str, list[Staff]]:
    """Group the roster by category, then role, for the hierarchy view.

    Returns a mapping of role name to the staff holding it, with medical roles
    listed before admin and support roles so the clinical chain of command
    reads top-down.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "staff member")
    query: dict[str, object] = {"hospital_id": hospital_id, "status": StaffStatus.ACTIVE.value}
    if shift is not None:
        query["shift"] = shift.value

    roster = await Staff.find(query).sort("+full_name").to_list()
    grouped: dict[str, list[Staff]] = {}
    for role in _HIERARCHY_ORDER:
        members = [member for member in roster if member.role is role]
        if members:
            grouped[role.value] = members
    return grouped


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
_HIERARCHY_ORDER: tuple[StaffRole, ...] = (
    StaffRole.MATRON,
    StaffRole.STAFF_NURSE,
    StaffRole.COMPOUNDER,
    StaffRole.LAB_ASSISTANT,
    StaffRole.WARD_BOY,
    StaffRole.ADMIN,
    StaffRole.ACCOUNTANT,
    StaffRole.DESK_ADMIN,
    StaffRole.SECURITY,
    StaffRole.DRIVER,
    StaffRole.LIFTMAN,
    StaffRole.CLEANER,
    StaffRole.HELPER,
)
"""Clinical seniority first, then administrative, then support."""


async def _intake_staff(
    hospital_id: PydanticObjectId,
    actor: User,
    full_name: str,
    employee_id: str,
    phone: str,
    national_id: str | None,
    role: StaffRole,
    registration_no: str | None,
    department_id: PydanticObjectId | None,
    assigned_ward_area: str | None,
    shift: ShiftType,
    status: StaffStatus,
    is_emergency_on_call: bool,
    settings: Settings | None,
) -> Staff:
    """Create a staff record from either intake form."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "staff member")
    if department_id is not None:
        await _require_department_in_hospital(department_id, hospital_id)

    active = settings or get_settings()
    protected = ProtectedNationalId.protect(national_id, active) if national_id else None

    try:
        staff = Staff(
            hospital_id=hospital_id,
            employee_id=employee_id,
            full_name=full_name,
            phone=phone,
            national_id=protected,
            staff_category=role.category,
            role=role,
            registration_no=registration_no,
            department_id=department_id,
            assigned_ward_area=assigned_ward_area,
            shift=shift,
            is_emergency_on_call=is_emergency_on_call,
            status=status,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        staff.insert,
        f"employee id {employee_id} is already in use at this hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _STAFF,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=staff.id,
        hospital_id=hospital_id,
        detail=f"{role.category} intake: {role}",
    )
    return staff


def _staff_query(
    hospital_id: PydanticObjectId,
    staff_category: StaffCategory | None,
    role: StaffRole | None,
    shift: ShiftType | None,
    department_id: PydanticObjectId | None,
    status: StaffStatus | None,
) -> dict[str, object]:
    """Build the roster filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if staff_category is not None:
        query["staff_category"] = staff_category.value
    if role is not None:
        query["role"] = role.value
    if shift is not None:
        query["shift"] = shift.value
    if department_id is not None:
        query["department_id"] = department_id
    if status is not None:
        query["status"] = status.value
    return query


async def _require_department_in_hospital(
    department_id: PydanticObjectId,
    hospital_id: PydanticObjectId,
) -> None:
    """Reject an assignment to a department belonging to a different hospital."""
    department = await Department.get(department_id)
    if department is None or department.hospital_id != hospital_id:
        msg = f"department {department_id} does not belong to this hospital"
        raise ConflictError(msg)


async def _require_doctor_in_hospital(
    doctor_id: PydanticObjectId,
    hospital_id: PydanticObjectId,
) -> None:
    """Reject a head of department who does not work at this hospital."""
    doctor = await Doctor.get(doctor_id)
    if doctor is None or doctor.hospital_id != hospital_id:
        msg = f"doctor {doctor_id} is not onboarded at this hospital and cannot be its HOD"
        raise ConflictError(msg)
