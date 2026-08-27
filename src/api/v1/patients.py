"""Patient register endpoints, including the Excel/CSV bulk upload.

The bulk endpoint answers 200 rather than 201 even when rows were created,
because the interesting part of the response is the *report*: how many rows
were accepted, how many were rejected, and why. A 201 would imply the whole
file succeeded.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, File, Query, UploadFile, status

from src.api.deps import HospitalActor, HospitalAdmin, HospitalPath, Paging, SettingsDep
from src.domain.enums import Gender
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.patient import (
    BulkUploadReport,
    PatientIntakeRequest,
    PatientResponse,
    PatientUpdateRequest,
)
from src.services import patient_service

router = APIRouter(tags=["patients"])


@router.post(
    "/hospitals/{hospital_id}/patients",
    response_model=ApiResponse[PatientResponse],
    status_code=status.HTTP_201_CREATED,
)
async def intake_patient(
    hospital_id: HospitalPath,
    request: Annotated[PatientIntakeRequest, Body()],
    actor: HospitalActor,
    settings: SettingsDep,
) -> ApiResponse[PatientResponse]:
    """Register a patient from the manual intake form.

    A National ID supplied here is encrypted before storage and, if it matches
    a registered citizen, links this record to that account so the encounter
    appears in their unified health record.
    """
    patient = await patient_service.intake_patient(hospital_id, request, actor, settings)
    return ApiResponse.ok(PatientResponse.model_validate(patient))


@router.post(
    "/hospitals/{hospital_id}/patients/bulk",
    response_model=ApiResponse[BulkUploadReport],
)
async def bulk_upload_patients(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="An .xlsx or .csv patient file.")],
) -> ApiResponse[BulkUploadReport]:
    """Import patients from a spreadsheet.

    Rows are validated independently: a malformed row is reported and skipped
    rather than failing the whole file. Every cell is read as raw text, so an
    MRN of ``0012`` is not silently turned into ``12``.
    """
    content = await file.read()
    report = await patient_service.bulk_import_patients(
        hospital_id, content, file.filename or "upload.csv", actor, settings
    )
    return ApiResponse.ok(report)


@router.get(
    "/hospitals/{hospital_id}/patients",
    response_model=ApiResponse[PaginatedResponse[PatientResponse]],
)
async def list_patients(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    search: Annotated[str | None, Query(description="Match name, MRN, or phone.")] = None,
    gender: Annotated[Gender | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ApiResponse[PaginatedResponse[PatientResponse]]:
    """Return the hospital's patient register, newest first."""
    patients = await patient_service.list_patients(
        hospital_id,
        actor,
        search=search,
        gender=gender,
        is_active=is_active,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await patient_service.count_patients(
        hospital_id, actor, search=search, gender=gender, is_active=is_active
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[PatientResponse.model_validate(patient) for patient in patients],
            meta=paging.meta(total),
        )
    )


@router.get("/patients/{patient_id}", response_model=ApiResponse[PatientResponse])
async def read_patient(
    patient_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[PatientResponse]:
    """Return one patient. The National ID is never included, in any form."""
    patient = await patient_service.get_patient(patient_id, actor)
    return ApiResponse.ok(PatientResponse.model_validate(patient))


@router.patch("/patients/{patient_id}", response_model=ApiResponse[PatientResponse])
async def update_patient(
    patient_id: PydanticObjectId,
    request: Annotated[PatientUpdateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[PatientResponse]:
    """Update a patient. The MRN and National ID are immutable."""
    patient = await patient_service.update_patient(patient_id, request, actor)
    return ApiResponse.ok(PatientResponse.model_validate(patient))
