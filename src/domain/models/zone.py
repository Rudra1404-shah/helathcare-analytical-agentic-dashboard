"""The ``zones`` collection: administrative areas used for population analytics.

Backs the Government Zone/Area Management Form. ``population_covered`` is the
denominator the future surge-forecasting and outbreak-detection modules need to
turn raw case counts into per-capita rates, which is why zones are a first-class
collection rather than a string field on ``hospitals``.
"""

from typing import ClassVar

import pymongo
from pydantic import Field
from pymongo import IndexModel

from src.domain.models.base import GeoLocation, TimestampedDocument
from src.domain.types import ShortText

__all__ = ["Zone"]


class Zone(TimestampedDocument):
    """A ward, zone, or administrative area within a city."""

    zone_code: str = Field(
        min_length=2,
        max_length=30,
        description="Unique code for the zone, e.g. 'MH-MUM-Z12'.",
    )
    name: ShortText = Field(description="Human-readable zone or ward name.")
    state: ShortText
    city: ShortText
    population_covered: int = Field(
        ge=0,
        description="Census population served by this zone.",
    )
    centroid: GeoLocation | None = Field(
        default=None,
        description="Optional geographic centre, used for map rendering.",
    )
    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "zones"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("zone_code", pymongo.ASCENDING)], unique=True, name="uq_zones_code"),
            IndexModel(
                [("state", pymongo.ASCENDING), ("city", pymongo.ASCENDING)],
                name="ix_zones_state_city",
            ),
            IndexModel([("centroid", pymongo.GEOSPHERE)], name="ix_zones_centroid_2dsphere"),
        ]
