"""The ``hospital_inventory`` collection: beds, oxygen, ventilators, and supplies.

Backs the Hospital Inventory Form. ``min_safety_threshold`` is the trigger the
future 4-tier Smart Alerts module fires on, and ``available_stock`` is what the
resource-prediction module extrapolates.
"""

from datetime import date, datetime
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, model_validator
from pymongo import IndexModel

from src.domain.enums import InventoryCategory, InventoryUnit
from src.domain.models.base import TimestampedDocument
from src.domain.types import ShortText

__all__ = ["InventoryItem"]


class InventoryItem(TimestampedDocument):
    """One tracked resource line at one hospital.

    Quantities are floats rather than integers because the same model tracks
    countable things (beds, ventilators) and continuous ones (bulk oxygen in
    litres).
    """

    hospital_id: PydanticObjectId
    category: InventoryCategory
    item_name: ShortText = Field(description="e.g. 'Adult Ventilator', 'Paracetamol 500mg'.")

    total_stock: float = Field(ge=0.0, description="Total owned quantity.")
    available_stock: float = Field(ge=0.0, description="Currently free quantity.")
    min_safety_threshold: float = Field(
        default=0.0,
        ge=0.0,
        description="Level at or below which an alert must be raised.",
    )
    unit: InventoryUnit = Field(default=InventoryUnit.UNITS)

    last_restocked_at: datetime | None = Field(default=None)
    expires_on: date | None = Field(
        default=None, description="Relevant for medicines and consumables."
    )
    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "hospital_inventory"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [
                    ("hospital_id", pymongo.ASCENDING),
                    ("category", pymongo.ASCENDING),
                    ("item_name", pymongo.ASCENDING),
                ],
                unique=True,
                name="uq_inventory_hospital_category_item",
            ),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("category", pymongo.ASCENDING)],
                name="ix_inventory_hospital_category",
            ),
            IndexModel(
                [("expires_on", pymongo.ASCENDING)],
                name="ix_inventory_expiry",
                sparse=True,
            ),
        ]

    @model_validator(mode="after")
    def _validate_available_within_total(self) -> Self:
        """Available stock can never exceed what the hospital owns.

        A violation here would let a hospital advertise ICU beds it does not
        have, which is precisely the fragmentation this platform exists to fix.
        """
        if self.available_stock > self.total_stock:
            msg = (
                f"available_stock ({self.available_stock}) cannot exceed "
                f"total_stock ({self.total_stock})"
            )
            raise ValueError(msg)
        return self

    @property
    def is_below_threshold(self) -> bool:
        """Return whether this item has hit its safety threshold."""
        return self.available_stock <= self.min_safety_threshold

    @property
    def in_use(self) -> float:
        """Return the quantity currently allocated or consumed."""
        return self.total_stock - self.available_stock

    @property
    def utilisation_ratio(self) -> float:
        """Return utilisation as a fraction between 0.0 and 1.0."""
        if self.total_stock == 0:
            return 0.0
        return self.in_use / self.total_stock
