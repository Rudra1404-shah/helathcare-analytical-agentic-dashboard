"""Case type definitions and the patient encounter workflow.

Admission, vitals, prescriptions, and discharge are separate endpoints against
the same case rather than one PATCH taking a conditionally-shaped body. Each
operation has different preconditions -- a discharge needs a summary, a vitals
reading does not -- and separate endpoints let each schema state its own rules.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import CurrentUser, HospitalActor, HospitalPath, Paging
from src.domain.enums import CaseStatus, DiseaseCategory, TriageLevel
from src.domain.schemas.case_type import (
    CaseTypeCreateRequest,
    CaseTypeResponse,
    CaseTypeUpdateRequest,
)
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.patient_case import (
    CaseAdmissionRequest,
    CaseDischargeRequest,
    CaseStatusUpdateRequest,
    PatientCaseResponse,
    PrescriptionRequest,
    VitalSignsRequest,
)
from src.services import case_service, case_type_service

case_types_router = APIRouter(prefix="/case-types", tags=["case-types"])
cases_router = APIRouter(tags=["cases"])


# --------------------------------------------------------------------------- #
# Case types
# --------------------------------------------------------------------------- #
@case_types_router.post(
    "", response_model=ApiResponse[CaseTypeResponse], status_code=status.HTTP_201_CREATED
)
async def create_case_type(
    request: Annotated[CaseTypeCreateRequest, Body()],
    actor: CurrentUser,
    hospital_id: Annotated[
        PydanticObjectId | None,
        Query(description="Ministry only: omit to define a national standard."),
    ] = None,
) -> ApiResponse[CaseTypeResponse]:
    """Define a case type.

    A hospital account always creates a definition scoped to its own hospital;
    only the ministry can create a national standard visible to everyone.
    """
    case_type = await case_type_service.create_case_type(request, actor, hospital_id)
    return ApiResponse.ok(CaseTypeResponse.model_validate(case_type))


@case_types_router.get("", response_model=ApiResponse[PaginatedResponse[CaseTypeResponse]])
async def list_case_types(
    actor: CurrentUser,
    paging: Paging,
    hospital_id: Annotated[PydanticObjectId | None, Query()] = None,
    disease_category: Annotated[DiseaseCategory | None, Query()] = None,
    triage_level: Annotated[TriageLevel | None, Query()] = None,
    is_notifiable: Annotated[bool | None, Query()] = None,
    include_national: Annotated[
        bool, Query(description="Include national standard definitions.")
    ] = True,
) -> ApiResponse[PaginatedResponse[CaseTypeResponse]]:
    """Return the case types available for classifying an admission."""
    case_types = await case_type_service.list_case_types(
        actor,
        hospital_id=hospital_id,
        disease_category=disease_category,
        triage_level=triage_level,
        is_notifiable=is_notifiable,
        include_national=include_national,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await case_type_service.count_case_types(
        actor,
        hospital_id=hospital_id,
        disease_category=disease_category,
        triage_level=triage_level,
        is_notifiable=is_notifiable,
        include_national=include_national,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[CaseTypeResponse.model_validate(item) for item in case_types],
            meta=paging.meta(total),
        )
    )


@case_types_router.get("/{case_type_id}", response_model=ApiResponse[CaseTypeResponse])
async def read_case_type(
    case_type_id: PydanticObjectId,
    actor: CurrentUser,
) -> ApiResponse[CaseTypeResponse]:
    """Return one case type."""
    case_type = await case_type_service.get_case_type(case_type_id, actor)
    return ApiResponse.ok(CaseTypeResponse.model_validate(case_type))


@case_types_router.patch("/{case_type_id}", response_model=ApiResponse[CaseTypeResponse])
async def update_case_type(
    case_type_id: PydanticObjectId,
    request: Annotated[CaseTypeUpdateRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[CaseTypeResponse]:
    """Update a case type. The ICD-10 code is immutable once defined."""
    case_type = await case_type_service.update_case_type(case_type_id, request, actor)
    return ApiResponse.ok(CaseTypeResponse.model_validate(case_type))


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
@cases_router.post(
    "/hospitals/{hospital_id}/cases",
    response_model=ApiResponse[PatientCaseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def admit_patient(
    hospital_id: HospitalPath,
    request: Annotated[CaseAdmissionRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Open a case, reserving a bed from the matching inventory pool.

    Admission is refused with a 409 when the hospital tracks the required bed
    category and none is free -- an admission the hospital cannot actually
    accommodate is worse than a clear refusal.
    """
    case = await case_service.admit_patient(hospital_id, request, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))


@cases_router.get(
    "/hospitals/{hospital_id}/cases",
    response_model=ApiResponse[PaginatedResponse[PatientCaseResponse]],
)
async def list_cases(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    case_status: Annotated[CaseStatus | None, Query(alias="status")] = None,
    patient_id: Annotated[PydanticObjectId | None, Query()] = None,
    doctor_id: Annotated[PydanticObjectId | None, Query()] = None,
    department_id: Annotated[PydanticObjectId | None, Query()] = None,
    triage_level: Annotated[TriageLevel | None, Query()] = None,
    open_only: Annotated[bool, Query(description="Exclude discharged and deceased.")] = False,
) -> ApiResponse[PaginatedResponse[PatientCaseResponse]]:
    """Return cases, newest admission first."""
    cases = await case_service.list_cases(
        hospital_id,
        actor,
        status=case_status,
        patient_id=patient_id,
        doctor_id=doctor_id,
        department_id=department_id,
        triage_level=triage_level,
        open_only=open_only,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await case_service.count_cases(
        hospital_id,
        actor,
        status=case_status,
        patient_id=patient_id,
        doctor_id=doctor_id,
        department_id=department_id,
        triage_level=triage_level,
        open_only=open_only,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[PatientCaseResponse.model_validate(case) for case in cases],
            meta=paging.meta(total),
        )
    )


@cases_router.get(
    "/hospitals/{hospital_id}/cases/triage-board",
    response_model=ApiResponse[dict[str, list[PatientCaseResponse]]],
)
async def triage_board(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[dict[str, list[PatientCaseResponse]]]:
    """Return open cases grouped by triage level, most urgent first.

    Cases with no triage assigned appear under ``UNTRIAGED`` rather than being
    dropped -- an unclassified patient is exactly the one to surface.
    """
    board = await case_service.triage_board(hospital_id, actor)
    return ApiResponse.ok(
        {
            level: [PatientCaseResponse.model_validate(case) for case in cases]
            for level, cases in board.items()
        }
    )


@cases_router.get("/cases/{case_id}", response_model=ApiResponse[PatientCaseResponse])
async def read_case(
    case_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Return one case, including its full vitals and prescription history."""
    case = await case_service.get_case(case_id, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))


@cases_router.patch("/cases/{case_id}", response_model=ApiResponse[PatientCaseResponse])
async def update_case(
    case_id: PydanticObjectId,
    request: Annotated[CaseStatusUpdateRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Move an open case between states, or reassign its bed, doctor, or triage.

    Closing a case is deliberately not possible here; use the discharge
    endpoint, which requires a discharge summary.
    """
    case = await case_service.update_case(case_id, request, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))


@cases_router.post(
    "/cases/{case_id}/vitals",
    response_model=ApiResponse[PatientCaseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def record_vitals(
    case_id: PydanticObjectId,
    request: Annotated[VitalSignsRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Append a set of bedside observations.

    Readings accumulate rather than overwrite: deterioration is only visible as
    a trend.
    """
    case = await case_service.record_vitals(case_id, request, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))


@cases_router.post(
    "/cases/{case_id}/prescriptions",
    response_model=ApiResponse[PatientCaseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_prescription(
    case_id: PydanticObjectId,
    request: Annotated[PrescriptionRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Add a medication order to an open case."""
    case = await case_service.add_prescription(case_id, request, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))


@cases_router.post("/cases/{case_id}/discharge", response_model=ApiResponse[PatientCaseResponse])
async def discharge_case(
    case_id: PydanticObjectId,
    request: Annotated[CaseDischargeRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[PatientCaseResponse]:
    """Close a case and release its bed.

    Requires a discharge summary; without one, occupancy analytics and
    length-of-stay statistics would be uncomputable.
    """
    case = await case_service.discharge_case(case_id, request, actor)
    return ApiResponse.ok(PatientCaseResponse.model_validate(case))
