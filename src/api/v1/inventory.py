"""Inventory, live capacity, and low-stock alert endpoints."""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import CurrentUser, HospitalActor, HospitalAdmin, HospitalPath, Paging
from src.domain.enums import InventoryCategory
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.inventory import (
    CapacitySummaryResponse,
    InventoryItemCreateRequest,
    InventoryItemResponse,
    InventoryItemUpdateRequest,
    InventoryStockAdjustmentRequest,
    LowStockAlertResponse,
)
from src.services import inventory_service

router = APIRouter(tags=["inventory"])


@router.post(
    "/hospitals/{hospital_id}/inventory",
    response_model=ApiResponse[InventoryItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_item(
    hospital_id: HospitalPath,
    request: Annotated[InventoryItemCreateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[InventoryItemResponse]:
    """Add a tracked resource line."""
    item = await inventory_service.create_item(hospital_id, request, actor)
    return ApiResponse.ok(InventoryItemResponse.model_validate(item))


@router.get(
    "/hospitals/{hospital_id}/inventory",
    response_model=ApiResponse[PaginatedResponse[InventoryItemResponse]],
)
async def list_items(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    paging: Paging,
    category: Annotated[InventoryCategory | None, Query()] = None,
    below_threshold: Annotated[
        bool | None, Query(description="Only lines at or below their safety threshold.")
    ] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ApiResponse[PaginatedResponse[InventoryItemResponse]]:
    """Return the hospital's stock register."""
    items = await inventory_service.list_items(
        hospital_id,
        actor,
        category=category,
        below_threshold=below_threshold,
        is_active=is_active,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await inventory_service.count_items(
        hospital_id,
        actor,
        category=category,
        below_threshold=below_threshold,
        is_active=is_active,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[InventoryItemResponse.model_validate(item) for item in items],
            meta=paging.meta(total),
        )
    )


@router.get(
    "/hospitals/{hospital_id}/inventory/capacity",
    response_model=ApiResponse[list[CapacitySummaryResponse]],
)
async def capacity_summary(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[list[CapacitySummaryResponse]]:
    """Return live capacity for general beds, ICU, ventilators, and oxygen.

    Several stock lines can share a category, so each card sums the category
    rather than reporting one line.
    """
    return ApiResponse.ok(await inventory_service.capacity_summary(hospital_id, actor))


@router.get("/inventory/alerts", response_model=ApiResponse[list[LowStockAlertResponse]])
async def low_stock_alerts(
    actor: CurrentUser,
    hospital_id: Annotated[
        PydanticObjectId | None,
        Query(description="Ministry only: omit to sweep every hospital."),
    ] = None,
) -> ApiResponse[list[LowStockAlertResponse]]:
    """Return every active line at or below its safety threshold."""
    return ApiResponse.ok(await inventory_service.list_low_stock(hospital_id, actor))


@router.get("/inventory/{item_id}", response_model=ApiResponse[InventoryItemResponse])
async def read_item(
    item_id: PydanticObjectId,
    actor: HospitalActor,
) -> ApiResponse[InventoryItemResponse]:
    """Return one inventory line."""
    item = await inventory_service.get_item(item_id, actor)
    return ApiResponse.ok(InventoryItemResponse.model_validate(item))


@router.patch("/inventory/{item_id}", response_model=ApiResponse[InventoryItemResponse])
async def update_item(
    item_id: PydanticObjectId,
    request: Annotated[InventoryItemUpdateRequest, Body()],
    actor: HospitalAdmin,
) -> ApiResponse[InventoryItemResponse]:
    """Update a stock line's quantities, threshold, unit, or expiry."""
    item = await inventory_service.update_item(item_id, request, actor)
    return ApiResponse.ok(InventoryItemResponse.model_validate(item))


@router.post("/inventory/{item_id}/adjust", response_model=ApiResponse[InventoryItemResponse])
async def adjust_stock(
    item_id: PydanticObjectId,
    request: Annotated[InventoryStockAdjustmentRequest, Body()],
    actor: HospitalActor,
) -> ApiResponse[InventoryItemResponse]:
    """Consume or release available stock.

    A negative delta consumes; a positive one releases. The reason is recorded
    in the audit trail, which is what makes a sudden oxygen drop explainable.
    """
    item = await inventory_service.adjust_stock(item_id, request, actor)
    return ApiResponse.ok(InventoryItemResponse.model_validate(item))
