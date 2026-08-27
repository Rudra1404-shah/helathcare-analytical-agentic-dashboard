"""Resource tracking: beds, ventilators, oxygen, medicines, consumables.

``available_stock`` is what the real-time monitoring module reads and
``min_safety_threshold`` is what the Smart Alerts module fires on, so both are
maintained here rather than derived at read time.

Bed allocation goes through :func:`adjust_stock`, which is also the function the
case service calls on admission and discharge. Keeping one path means a bed can
never be occupied by a case without the inventory reflecting it.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import ConflictError
from src.domain.enums import InventoryCategory
from src.domain.models import InventoryItem, User
from src.domain.schemas.inventory import (
    CapacitySummaryResponse,
    InventoryItemCreateRequest,
    InventoryItemUpdateRequest,
    InventoryStockAdjustmentRequest,
    LowStockAlertResponse,
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
    "BED_CATEGORIES",
    "adjust_stock",
    "capacity_summary",
    "count_items",
    "create_item",
    "get_item",
    "list_items",
    "list_low_stock",
    "update_item",
]

_COLLECTION = "hospital_inventory"

BED_CATEGORIES: tuple[InventoryCategory, ...] = (
    InventoryCategory.GENERAL_BEDS,
    InventoryCategory.ICU_BEDS,
    InventoryCategory.VENTILATORS,
    InventoryCategory.OXYGEN_LITERS,
)
"""The four categories surfaced as live capacity cards on the hospital overview."""


async def create_item(
    hospital_id: PydanticObjectId,
    request: InventoryItemCreateRequest,
    actor: User,
) -> InventoryItem:
    """Add a tracked resource line.

    Raises:
        ConflictError: If this hospital already tracks an item of the same name
            in the same category.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "inventory item")

    try:
        item = InventoryItem(
            hospital_id=hospital_id,
            category=request.category,
            item_name=request.item_name,
            total_stock=request.total_stock,
            available_stock=request.available_stock,
            min_safety_threshold=request.min_safety_threshold,
            unit=request.unit,
            last_restocked_at=request.last_restocked_at,
            expires_on=request.expires_on,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        item.insert,
        f"'{request.item_name}' is already tracked under {request.category} at this hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=item.id,
        hospital_id=hospital_id,
    )
    return item


async def get_item(item_id: PydanticObjectId, actor: User) -> InventoryItem:
    """Fetch one inventory line, enforcing hospital scope."""
    item = await get_or_404(InventoryItem, item_id, "inventory item")
    ensure_hospital_match(item.hospital_id, hospital_scope_of(actor), "inventory item")
    return item


async def list_items(
    hospital_id: PydanticObjectId,
    actor: User,
    category: InventoryCategory | None = None,
    below_threshold: bool | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 200,
) -> list[InventoryItem]:
    """Return a hospital's stock register.

    ``below_threshold`` is applied in Python rather than in the query because
    the comparison is between two fields of the same document, which MongoDB
    can only express through an aggregation ``$expr``. The register is a few
    hundred lines per hospital, so the simpler path is the right one here.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "inventory item")
    query = _inventory_query(hospital_id, category, is_active)

    if below_threshold is None:
        return (
            await InventoryItem.find(query)
            .sort("+category", "+item_name")
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    everything = await InventoryItem.find(query).sort("+category", "+item_name").to_list()
    filtered = [item for item in everything if item.is_below_threshold is below_threshold]
    return filtered[skip : skip + limit]


async def count_items(
    hospital_id: PydanticObjectId,
    actor: User,
    category: InventoryCategory | None = None,
    below_threshold: bool | None = None,
    is_active: bool | None = None,
) -> int:
    """Return how many inventory lines match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "inventory item")
    query = _inventory_query(hospital_id, category, is_active)

    if below_threshold is None:
        return await InventoryItem.find(query).count()

    everything = await InventoryItem.find(query).to_list()
    return sum(1 for item in everything if item.is_below_threshold is below_threshold)


async def update_item(
    item_id: PydanticObjectId,
    request: InventoryItemUpdateRequest,
    actor: User,
) -> InventoryItem:
    """Apply a partial update to a stock line.

    When only one of the two quantities is supplied, the stored model still
    checks the pair, so lowering ``total_stock`` below the current
    ``available_stock`` is refused rather than silently accepted.
    """
    item = await get_or_404(InventoryItem, item_id, "inventory item")
    ensure_hospital_match(item.hospital_id, hospital_scope_of(actor), "inventory item")

    # Order the two stock writes so the intermediate state never breaks the
    # available <= total invariant. Raising the ceiling first lets available
    # follow it up; lowering available first lets the ceiling come down after.
    ordered: dict[str, object] = {
        **_ordered_stock_changes(item, request.total_stock, request.available_stock),
        "min_safety_threshold": request.min_safety_threshold,
        "unit": request.unit,
        "last_restocked_at": request.last_restocked_at,
        "expires_on": request.expires_on,
        "is_active": request.is_active,
    }
    if apply_partial_update(item, ordered):
        item.touch()
        await item.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=item.id,
        hospital_id=item.hospital_id,
    )
    return item


async def adjust_stock(
    item_id: PydanticObjectId,
    request: InventoryStockAdjustmentRequest,
    actor: User,
) -> InventoryItem:
    """Consume or release available stock.

    A negative delta consumes -- allocating an ICU bed, drawing oxygen. A
    positive delta releases it again on discharge or restock.

    Raises:
        ConflictError: If the adjustment would drive stock negative or above
            the total the hospital owns.
    """
    item = await get_or_404(InventoryItem, item_id, "inventory item")
    ensure_hospital_match(item.hospital_id, hospital_scope_of(actor), "inventory item")

    updated = item.available_stock + request.delta
    if updated < 0:
        msg = (
            f"cannot consume {abs(request.delta)} {item.unit} of '{item.item_name}': "
            f"only {item.available_stock} available"
        )
        raise ConflictError(msg)
    if updated > item.total_stock:
        msg = (
            f"cannot release {request.delta} {item.unit} of '{item.item_name}': "
            f"available stock would exceed the {item.total_stock} the hospital owns"
        )
        raise ConflictError(msg)

    item.available_stock = updated
    item.touch()
    await item.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=item.id,
        hospital_id=item.hospital_id,
        detail=f"stock {request.delta:+g} -> {updated:g}; {request.reason}",
    )
    return item


async def list_low_stock(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> list[LowStockAlertResponse]:
    """Return every active line at or below its safety threshold.

    A ministry actor may pass ``None`` to sweep every hospital, which is what
    the national resource view needs.
    """
    query: dict[str, object] = {"is_active": True}
    scope = hospital_scope_of(actor) or hospital_id
    if scope is not None:
        ensure_hospital_match(scope, hospital_scope_of(actor), "inventory item")
        query["hospital_id"] = scope

    items = await InventoryItem.find(query).to_list()
    return [
        LowStockAlertResponse(
            hospital_id=item.hospital_id,
            item_id=_require_id(item),
            category=item.category,
            item_name=item.item_name,
            available_stock=item.available_stock,
            min_safety_threshold=item.min_safety_threshold,
            unit=item.unit,
        )
        for item in items
        if item.is_below_threshold
    ]


async def capacity_summary(
    hospital_id: PydanticObjectId,
    actor: User,
) -> list[CapacitySummaryResponse]:
    """Aggregate the four capacity categories into live dashboard cards.

    Several lines can share a category -- two ventilator models, three oxygen
    tanks -- so totals are summed per category rather than reported per line.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "inventory item")
    items = await InventoryItem.find({"hospital_id": hospital_id, "is_active": True}).to_list()

    summary: list[CapacitySummaryResponse] = []
    for category in BED_CATEGORIES:
        in_category = [item for item in items if item.category is category]
        total = sum(item.total_stock for item in in_category)
        available = sum(item.available_stock for item in in_category)
        threshold = sum(item.min_safety_threshold for item in in_category)
        summary.append(
            CapacitySummaryResponse(
                category=category,
                total_stock=total,
                available_stock=available,
                in_use=total - available,
                min_safety_threshold=threshold,
                unit=in_category[0].unit if in_category else None,
                utilisation_ratio=((total - available) / total) if total else 0.0,
                is_below_threshold=bool(in_category) and available <= threshold,
                line_count=len(in_category),
            )
        )
    return summary


async def find_allocatable_bed(
    hospital_id: PydanticObjectId,
    category: InventoryCategory,
) -> InventoryItem | None:
    """Return a stock line of this category with a free unit, if one exists."""
    items = await InventoryItem.find(
        {"hospital_id": hospital_id, "category": category.value, "is_active": True}
    ).to_list()
    for item in items:
        if item.available_stock >= 1:
            return item
    return None


def _require_id(item: InventoryItem) -> PydanticObjectId:
    """Return a persisted item's id, or fail loudly if it has none."""
    if item.id is None:
        msg = "inventory item has not been persisted and has no id"
        raise ConflictError(msg)
    return item.id


def _ordered_stock_changes(
    item: InventoryItem,
    total_stock: float | None,
    available_stock: float | None,
) -> dict[str, object]:
    """Order the total and available writes so neither intermediate state fails.

    Documents validate on assignment, so setting a lower ``total_stock`` while
    ``available_stock`` is still high raises -- even when the caller supplied a
    matching lower available in the same request.
    """
    lowering_available = available_stock is not None and available_stock < item.available_stock
    if lowering_available:
        return {"available_stock": available_stock, "total_stock": total_stock}
    return {"total_stock": total_stock, "available_stock": available_stock}


def _inventory_query(
    hospital_id: PydanticObjectId,
    category: InventoryCategory | None,
    is_active: bool | None,
) -> dict[str, object]:
    """Build the register filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if category is not None:
        query["category"] = category.value
    if is_active is not None:
        query["is_active"] = is_active
    return query
