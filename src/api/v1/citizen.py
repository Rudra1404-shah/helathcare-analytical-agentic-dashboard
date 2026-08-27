"""Citizen self-service: the unified Personal Health Record.

The record is assembled across every hospital that has treated this person,
resolved through their National ID lookup hash. A citizen reads only their own;
the ministry may read any, and both paths emit an audit event because this is
the most sensitive read in the platform.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body

from src.api.deps import CurrentUser, GovtAdmin
from src.domain.schemas.common import ApiResponse
from src.domain.schemas.patient import PatientResponse
from src.domain.schemas.phr import PersonalHealthRecordResponse, PhrExportRequest
from src.services import auth_service, citizen_service

router = APIRouter(prefix="/citizen", tags=["citizen"])


@router.get("/health-record", response_model=ApiResponse[PersonalHealthRecordResponse])
async def read_own_health_record(actor: CurrentUser) -> ApiResponse[PersonalHealthRecordResponse]:
    """Return the signed-in citizen's complete cross-hospital history."""
    record = await citizen_service.assemble_health_record(actor, actor)
    return ApiResponse.ok(record)


@router.post("/health-record/export", response_model=ApiResponse[PersonalHealthRecordResponse])
async def export_own_health_record(
    request: Annotated[PhrExportRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[PersonalHealthRecordResponse]:
    """Return a filtered export of the citizen's own record.

    Sections and a date window are chosen by the citizen; the export is logged
    separately from an ordinary read so an unusual bulk extraction stands out
    in the audit trail.
    """
    record = await citizen_service.assemble_health_record(actor, actor, request)
    return ApiResponse.ok(record)


@router.get("/records", response_model=ApiResponse[list[PatientResponse]])
async def list_own_patient_records(actor: CurrentUser) -> ApiResponse[list[PatientResponse]]:
    """Return every hospital-local patient record resolved to this citizen.

    Useful for showing which hospitals hold a record, before assembling the
    full history.
    """
    records = await citizen_service.linked_patient_records(actor)
    return ApiResponse.ok([PatientResponse.model_validate(record) for record in records])


@router.get(
    "/{citizen_user_id}/health-record",
    response_model=ApiResponse[PersonalHealthRecordResponse],
)
async def read_citizen_health_record(
    citizen_user_id: PydanticObjectId,
    actor: GovtAdmin,
) -> ApiResponse[PersonalHealthRecordResponse]:
    """Return any citizen's health record. Ministry only, and always audited."""
    citizen = await auth_service.get_user(citizen_user_id)
    record = await citizen_service.assemble_health_record(citizen, actor)
    return ApiResponse.ok(record)
