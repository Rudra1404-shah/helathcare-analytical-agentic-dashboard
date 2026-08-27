"""Department registry, staff intake, and doctor onboarding endpoints.

All three are hospital-scoped and nested under ``/hospitals/{hospital_id}``, so
the tenancy check happens once in the path dependency rather than being
re-derived from a body field that a client could lie about.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import (
    CurrentUser,
    HospitalActor,
    HospitalAdmin,
    HospitalPath,
    Paging,
    SettingsDep,
)
from src.domain.enums import ShiftType, StaffCategory, StaffRole, StaffStatus
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.department import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from src.domain.schemas.doctor import DoctorOnboardingRequest, DoctorResponse, DoctorUpdateRequest
from src.domain.schemas.staff import (
    AdminSupportStaffIntakeRequest,
    MedicalStaffIntakeRequest,
    StaffResponse,
    StaffUpdateRequest,
)
from src.services import doctor_service, staff_service

departments_router = APIRouter(tags=["departments"])
staff_router = APIRouter(tags=["staff"])
doctors_router = APIRouter(tags=["doctors"])


# --------------------------------------------------------------------------- #
# Departments
# --------------------------------------------------------------------------- #
@departments_router.post(
    "/hospitals/{hospital_id}/departments",
    response_model=ApiResponse[DepartmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    hospital_id: HospitalPath,
    request: Annotated[DepartmentCreateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[DepartmentResponse]:
    """Register a department. The code is unique within the hospital."""
    department = await staff_service.create_department(hospital_id, request, actor)
    return ApiResponse.ok(DepartmentResponse.model_validate(department))


@departments_router.get(
    "/hospitals/{hospital_id}/departments",
    response_model=ApiResponse[PaginatedResponse[DepartmentResponse]],
)
async def list_departments(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    is_active: Annotated[bool | None, Query()] = None,
) -> ApiResponse[PaginatedResponse[DepartmentResponse]]:
    """Return a hospital's department registry."""
    departments = await staff_service.list_departments(
        hospital_id, actor, is_active=is_active, skip=paging.skip, limit=paging.limit
    )
    total = await staff_service.count_departments(hospital_id, actor, is_active=is_active)
    return ApiResponse.ok(
        PaginatedResponse(
            items=[DepartmentResponse.model_validate(item) for item in departments],
            meta=paging.meta(total),
        )
    )


@departments_router.get(
    "/departments/{department_id}", response_model=ApiResponse[DepartmentResponse]
)
async def read_department(
    department_id: PydanticObjectId,
    actor: CurrentUser,
) -> ApiResponse[DepartmentResponse]:
    """Return one department."""
    department = await staff_service.get_department(department_id, actor)
    return ApiResponse.ok(DepartmentResponse.model_validate(department))


@departments_router.patch(
    "/departments/{department_id}", response_model=ApiResponse[DepartmentResponse]
)
async def update_department(
    department_id: PydanticObjectId,
    request: Annotated[DepartmentUpdateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[DepartmentResponse]:
    """Update a department. The code is immutable once registered."""
    department = await staff_service.update_department(department_id, request, actor)
    return ApiResponse.ok(DepartmentResponse.model_validate(department))


# --------------------------------------------------------------------------- #
# Staff
# --------------------------------------------------------------------------- #
@staff_router.post(
    "/hospitals/{hospital_id}/staff/admin-support",
    response_model=ApiResponse[StaffResponse],
    status_code=status.HTTP_201_CREATED,
)
async def intake_admin_support_staff(
    hospital_id: HospitalPath,
    request: Annotated[AdminSupportStaffIntakeRequest, Body()],
    actor: HospitalAdmin,
    settings: SettingsDep,
) -> ApiResponse[StaffResponse]:
    """File an Admin & Support Staff Intake Form.

    Accepts only ADMIN_SUPPORT roles; a medical role submitted here is refused
    so it cannot inflate clinical staffing counts.
    """
    staff = await staff_service.intake_admin_support_staff(hospital_id, request, actor, settings)
    return ApiResponse.ok(StaffResponse.model_validate(staff))


@staff_router.post(
    "/hospitals/{hospital_id}/staff/medical",
    response_model=ApiResponse[StaffResponse],
    status_code=status.HTTP_201_CREATED,
)
async def intake_medical_staff(
    hospital_id: HospitalPath,
    request: Annotated[MedicalStaffIntakeRequest, Body()],
    actor: HospitalAdmin,
    settings: SettingsDep,
) -> ApiResponse[StaffResponse]:
    """File a Medical Staff Intake Form. A registration number is mandatory."""
    staff = await staff_service.intake_medical_staff(hospital_id, request, actor, settings)
    return ApiResponse.ok(StaffResponse.model_validate(staff))


@staff_router.get(
    "/hospitals/{hospital_id}/staff",
    response_model=ApiResponse[PaginatedResponse[StaffResponse]],
)
async def list_staff(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    staff_category: Annotated[StaffCategory | None, Query()] = None,
    role: Annotated[StaffRole | None, Query()] = None,
    shift: Annotated[ShiftType | None, Query()] = None,
    department_id: Annotated[PydanticObjectId | None, Query()] = None,
    staff_status: Annotated[StaffStatus | None, Query(alias="status")] = None,
) -> ApiResponse[PaginatedResponse[StaffResponse]]:
    """Return the workforce roster."""
    roster = await staff_service.list_staff(
        hospital_id,
        actor,
        staff_category=staff_category,
        role=role,
        shift=shift,
        department_id=department_id,
        status=staff_status,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await staff_service.count_staff(
        hospital_id,
        actor,
        staff_category=staff_category,
        role=role,
        shift=shift,
        department_id=department_id,
        status=staff_status,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[StaffResponse.model_validate(member) for member in roster],
            meta=paging.meta(total),
        )
    )


@staff_router.get(
    "/hospitals/{hospital_id}/staff/hierarchy",
    response_model=ApiResponse[dict[str, list[StaffResponse]]],
)
async def staff_hierarchy(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    shift: Annotated[ShiftType | None, Query(description="Narrow to one shift.")] = None,
) -> ApiResponse[dict[str, list[StaffResponse]]]:
    """Return the active roster grouped by role, clinical seniority first."""
    grouped = await staff_service.staff_hierarchy(hospital_id, actor, shift=shift)
    return ApiResponse.ok(
        {
            role: [StaffResponse.model_validate(member) for member in members]
            for role, members in grouped.items()
        }
    )


@staff_router.get("/staff/{staff_id}", response_model=ApiResponse[StaffResponse])
async def read_staff(
    staff_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[StaffResponse]:
    """Return one staff record. The National ID is never included."""
    staff = await staff_service.get_staff(staff_id, actor)
    return ApiResponse.ok(StaffResponse.model_validate(staff))


@staff_router.patch("/staff/{staff_id}", response_model=ApiResponse[StaffResponse])
async def update_staff(
    staff_id: PydanticObjectId,
    request: Annotated[StaffUpdateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[StaffResponse]:
    """Update a staff member's assignment, shift, or employment status."""
    staff = await staff_service.update_staff(staff_id, request, actor)
    return ApiResponse.ok(StaffResponse.model_validate(staff))


# --------------------------------------------------------------------------- #
# Doctors
# --------------------------------------------------------------------------- #
@doctors_router.post(
    "/hospitals/{hospital_id}/doctors",
    response_model=ApiResponse[DoctorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def onboard_doctor(
    hospital_id: HospitalPath,
    request: Annotated[DoctorOnboardingRequest, Body()],
    actor: HospitalAdmin,
    settings: SettingsDep,
) -> ApiResponse[DoctorResponse]:
    """File a Doctor Onboarding Form.

    The council licence number is unique across the whole platform, not just
    this hospital.
    """
    doctor = await doctor_service.onboard_doctor(hospital_id, request, actor, settings)
    return ApiResponse.ok(DoctorResponse.model_validate(doctor))


@doctors_router.get(
    "/hospitals/{hospital_id}/doctors",
    response_model=ApiResponse[PaginatedResponse[DoctorResponse]],
)
async def list_doctors(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    department_id: Annotated[PydanticObjectId | None, Query()] = None,
    specialization: Annotated[str | None, Query()] = None,
    shift: Annotated[ShiftType | None, Query()] = None,
    doctor_status: Annotated[StaffStatus | None, Query(alias="status")] = None,
) -> ApiResponse[PaginatedResponse[DoctorResponse]]:
    """Return a hospital's doctor roster."""
    doctors = await doctor_service.list_doctors(
        hospital_id,
        actor,
        department_id=department_id,
        specialization=specialization,
        shift=shift,
        status=doctor_status,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await doctor_service.count_doctors(
        hospital_id,
        actor,
        department_id=department_id,
        specialization=specialization,
        shift=shift,
        status=doctor_status,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[DoctorResponse.model_validate(doctor) for doctor in doctors],
            meta=paging.meta(total),
        )
    )


@doctors_router.get("/doctors/{doctor_id}", response_model=ApiResponse[DoctorResponse])
async def read_doctor(
    doctor_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[DoctorResponse]:
    """Return one doctor."""
    doctor = await doctor_service.get_doctor(doctor_id, actor)
    return ApiResponse.ok(DoctorResponse.model_validate(doctor))


@doctors_router.patch("/doctors/{doctor_id}", response_model=ApiResponse[DoctorResponse])
async def update_doctor(
    doctor_id: PydanticObjectId,
    request: Annotated[DoctorUpdateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[DoctorResponse]:
    """Update a doctor. The council licence number is immutable."""
    doctor = await doctor_service.update_doctor(doctor_id, request, actor)
    return ApiResponse.ok(DoctorResponse.model_validate(doctor))
