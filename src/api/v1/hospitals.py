"""Hospital directory, profile, and accreditation endpoints.

Two write paths against one document, split by who owns the fields. The
ministry owns identity and accreditation; a hospital admin owns operational
infrastructure. A hospital admin calling the accreditation endpoint gets a 403,
which is the whole point of separating them.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import CurrentUser, GovtAdmin, HospitalPath, Paging
from src.domain.enums import AccreditationStatus, SectorType
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.govt import HospitalAccreditationUpdateRequest
from src.domain.schemas.hospital import (
    HospitalCreateRequest,
    HospitalProfileUpdateRequest,
    HospitalResponse,
)
from src.services import hospital_service

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.post(
    "",
    response_model=ApiResponse[HospitalResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_hospital(
    request: Annotated[HospitalCreateRequest, Body()],
    actor: GovtAdmin,
) -> ApiResponse[HospitalResponse]:
    """Register a hospital from the Verification & Accreditation Form."""
    hospital = await hospital_service.create_hospital(request, actor)
    return ApiResponse.ok(HospitalResponse.model_validate(hospital))


@router.get("", response_model=ApiResponse[PaginatedResponse[HospitalResponse]])
async def list_hospitals(
    actor: CurrentUser,
    paging: Paging,
    state: Annotated[str | None, Query(description="Filter by state.")] = None,
    city: Annotated[str | None, Query(description="Filter by city.")] = None,
    zone_code: Annotated[str | None, Query(description="Filter by zone or ward.")] = None,
    sector_type: Annotated[SectorType | None, Query()] = None,
    accreditation_status: Annotated[AccreditationStatus | None, Query()] = None,
    search: Annotated[str | None, Query(description="Match name or licence number.")] = None,
) -> ApiResponse[PaginatedResponse[HospitalResponse]]:
    """Return the hospital directory.

    A hospital-scoped account sees only its own hospital, whatever filters it
    supplies.
    """
    hospitals = await hospital_service.list_hospitals(
        actor,
        state=state,
        city=city,
        zone_code=zone_code,
        sector_type=sector_type,
        accreditation_status=accreditation_status,
        search=search,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await hospital_service.count_hospitals(
        actor,
        state=state,
        city=city,
        zone_code=zone_code,
        sector_type=sector_type,
        accreditation_status=accreditation_status,
        search=search,
    )

    return ApiResponse.ok(
        PaginatedResponse(
            items=[HospitalResponse.model_validate(item) for item in hospitals],
            meta=paging.meta(total),
        )
    )


@router.get("/cities", response_model=ApiResponse[list[dict[str, str]]])
async def list_cities(actor: CurrentUser) -> ApiResponse[list[dict[str, str]]]:
    """Return the distinct state and city pairs present in the directory.

    Powers the ministry portal's city filter without paging the whole register.
    """
    return ApiResponse.ok(await hospital_service.list_cities(actor))


@router.get("/{hospital_id}", response_model=ApiResponse[HospitalResponse])
async def read_hospital(
    hospital_id: PydanticObjectId,
    actor: CurrentUser,
) -> ApiResponse[HospitalResponse]:
    """Return one hospital."""
    hospital = await hospital_service.get_hospital(hospital_id, actor)
    return ApiResponse.ok(HospitalResponse.model_validate(hospital))


@router.patch("/{hospital_id}/profile", response_model=ApiResponse[HospitalResponse])
async def update_profile(
    hospital_id: HospitalPath,
    request: Annotated[HospitalProfileUpdateRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[HospitalResponse]:
    """Apply the Profile & Infrastructure Setup Form.

    Cannot touch licence number, sector, or accreditation state -- those fields
    are absent from the request schema by design.
    """
    hospital = await hospital_service.update_profile(hospital_id, request, actor)
    return ApiResponse.ok(HospitalResponse.model_validate(hospital))


@router.patch("/{hospital_id}/accreditation", response_model=ApiResponse[HospitalResponse])
async def update_accreditation(
    hospital_id: PydanticObjectId,
    request: Annotated[HospitalAccreditationUpdateRequest, Body()],
    actor: GovtAdmin,
) -> ApiResponse[HospitalResponse]:
    """Record a ministry accreditation decision. Ministry only.

    Blacklisting also deactivates the hospital, so it stops appearing as an
    option anywhere a citizen or another hospital would pick one.
    """
    hospital = await hospital_service.update_accreditation(hospital_id, request, actor)
    return ApiResponse.ok(HospitalResponse.model_validate(hospital))
