"""Zone and area management endpoints for the Health Ministry portal."""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import CurrentUser, GovtAdmin, Paging
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.govt import ZoneCreateRequest, ZoneResponse, ZoneUpdateRequest
from src.services import zone_service

router = APIRouter(prefix="/zones", tags=["zones"])


@router.post("", response_model=ApiResponse[ZoneResponse], status_code=status.HTTP_201_CREATED)
async def create_zone(
    request: Annotated[ZoneCreateRequest, Body()],
    actor: GovtAdmin,
) -> ApiResponse[ZoneResponse]:
    """Register an administrative zone. Ministry only."""
    zone = await zone_service.create_zone(request, actor)
    return ApiResponse.ok(ZoneResponse.model_validate(zone))


@router.get("", response_model=ApiResponse[PaginatedResponse[ZoneResponse]])
async def list_zones(
    _actor: CurrentUser,
    paging: Paging,
    state: Annotated[str | None, Query()] = None,
    city: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ApiResponse[PaginatedResponse[ZoneResponse]]:
    """Return registered zones.

    Readable by any signed-in account: a hospital admin needs the zone list to
    file their own address, and a citizen needs it to find a nearby hospital.
    """
    zones = await zone_service.list_zones(
        state=state, city=city, is_active=is_active, skip=paging.skip, limit=paging.limit
    )
    total = await zone_service.count_zones(state=state, city=city, is_active=is_active)
    return ApiResponse.ok(
        PaginatedResponse(
            items=[ZoneResponse.model_validate(zone) for zone in zones],
            meta=paging.meta(total),
        )
    )


@router.get("/{zone_id}", response_model=ApiResponse[ZoneResponse])
async def read_zone(zone_id: PydanticObjectId, _actor: CurrentUser) -> ApiResponse[ZoneResponse]:
    """Return one zone."""
    zone = await zone_service.get_zone(zone_id)
    return ApiResponse.ok(ZoneResponse.model_validate(zone))


@router.patch("/{zone_id}", response_model=ApiResponse[ZoneResponse])
async def update_zone(
    zone_id: PydanticObjectId,
    request: Annotated[ZoneUpdateRequest, Body()],
    actor: GovtAdmin,
) -> ApiResponse[ZoneResponse]:
    """Update a zone's name, population, centroid, or active state.

    The zone code is immutable: hospitals reference it, and renaming it would
    orphan every hospital filed against the old code.
    """
    zone = await zone_service.update_zone(zone_id, request, actor)
    return ApiResponse.ok(ZoneResponse.model_validate(zone))
