"""Hospital Inventory Form schemas."""

from datetime import date, datetime
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import InventoryCategory, InventoryUnit
from src.domain.schemas.common import IdentifiedResponse, RequestSchema, ResponseSchema
from src.domain.types import ShortText

__all__ = [
    "CapacitySummaryResponse",
    "InventoryItemCreateRequest",
    "InventoryItemResponse",
    "InventoryItemUpdateRequest",
    "InventoryStockAdjustmentRequest",
    "LowStockAlertResponse",
]


class InventoryItemCreateRequest(RequestSchema):
    """Hospital Inventory Form."""

    category: InventoryCategory
    item_name: ShortText
    total_stock: float = Field(ge=0.0)
    available_stock: float = Field(ge=0.0)
    min_safety_threshold: float = Field(default=0.0, ge=0.0)
    unit: InventoryUnit = Field(default=InventoryUnit.UNITS)
    last_restocked_at: datetime | None = Field(default=None)
    expires_on: date | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_available_within_total(self) -> Self:
        """Mirror the model rule so the API rejects impossible stock early."""
        if self.available_stock > self.total_stock:
            msg = (
                f"available_stock ({self.available_stock}) cannot exceed "
                f"total_stock ({self.total_stock})"
            )
            raise ValueError(msg)
        return self


class InventoryItemUpdateRequest(RequestSchema):
    """Partial update to an inventory line."""

    total_stock: float | None = Field(default=None, ge=0.0)
    available_stock: float | None = Field(default=None, ge=0.0)
    min_safety_threshold: float | None = Field(default=None, ge=0.0)
    unit: InventoryUnit | None = Field(default=None)
    last_restocked_at: datetime | None = Field(default=None)
    expires_on: date | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_available_within_total(self) -> Self:
        """Check the invariant when both quantities are supplied together."""
        if (
            self.total_stock is not None
            and self.available_stock is not None
            and self.available_stock > self.total_stock
        ):
            msg = (
                f"available_stock ({self.available_stock}) cannot exceed "
                f"total_stock ({self.total_stock})"
            )
            raise ValueError(msg)
        return self


class InventoryStockAdjustmentRequest(RequestSchema):
    """Consume or release stock, e.g. allocating an ICU bed to a case."""

    delta: float = Field(
        description="Change to available stock. Negative consumes, positive releases."
    )
    reason: ShortText = Field(description="Why the adjustment was made.")

    @model_validator(mode="after")
    def _reject_zero_delta(self) -> Self:
        """A zero adjustment is a no-op and is almost always a client bug."""
        if self.delta == 0:
            msg = "delta must be non-zero"
            raise ValueError(msg)
        return self


class InventoryItemResponse(IdentifiedResponse):
    """An inventory line as returned by the API."""

    hospital_id: PydanticObjectId
    category: InventoryCategory
    item_name: str
    total_stock: float
    available_stock: float
    min_safety_threshold: float
    unit: InventoryUnit
    last_restocked_at: datetime | None = None
    expires_on: date | None = None
    is_active: bool


class CapacitySummaryResponse(ResponseSchema):
    """One live capacity card on the hospital overview.

    A hospital can track several lines in the same category -- two ventilator
    models, three oxygen tanks -- so a card sums the category rather than
    reporting a single line, and says how many lines it rolled up.
    """

    category: InventoryCategory
    total_stock: float = Field(ge=0.0)
    available_stock: float = Field(ge=0.0)
    in_use: float = Field(ge=0.0)
    min_safety_threshold: float = Field(ge=0.0)
    unit: InventoryUnit | None = Field(
        default=None, description="None when the hospital tracks nothing in this category."
    )
    utilisation_ratio: float = Field(ge=0.0, le=1.0)
    is_below_threshold: bool
    line_count: int = Field(ge=0)


class LowStockAlertResponse(ResponseSchema):
    """An inventory line that has reached its safety threshold."""

    hospital_id: PydanticObjectId
    item_id: PydanticObjectId
    category: InventoryCategory
    item_name: str
    available_stock: float
    min_safety_threshold: float
    unit: InventoryUnit
