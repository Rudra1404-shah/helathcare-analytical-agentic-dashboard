"""Shared building blocks for every Beanie document in the platform.

Contains the timestamped document base plus the value objects that appear across
several collections: protected National IDs, GeoJSON locations, and addresses.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from beanie import Document
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.config import Settings
from src.core.security import (
    NATIONAL_ID_LOOKUP_HASH_LENGTH,
    encrypt_national_id,
    national_id_lookup_hash,
)

__all__ = [
    "Address",
    "GeoLocation",
    "ProtectedNationalId",
    "TimestampedDocument",
    "utcnow",
]

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


class ValueObject(BaseModel):
    """Base for immutable embedded documents.

    Frozen to honour the project immutability rule: build a new instance rather
    than mutating an existing one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class ProtectedNationalId(ValueObject):
    """A National ID stored as ciphertext plus a deterministic lookup hash.

    The plaintext is never persisted. ``lookup_hash`` is what queries and unique
    indexes are built on; ``ciphertext`` is what gets decrypted when a citizen
    views their own record.
    """

    ciphertext: str = Field(
        min_length=1,
        description="urlsafe-base64 AES-GCM ciphertext of the National ID.",
    )
    lookup_hash: str = Field(
        min_length=NATIONAL_ID_LOOKUP_HASH_LENGTH,
        max_length=NATIONAL_ID_LOOKUP_HASH_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
        description="Deterministic HMAC-SHA256 hex digest used for lookups.",
    )

    @classmethod
    def protect(cls, national_id: str, settings: Settings | None = None) -> Self:
        """Encrypt and hash a plaintext National ID into a storable value object."""
        return cls(
            ciphertext=encrypt_national_id(national_id, settings),
            lookup_hash=national_id_lookup_hash(national_id, settings),
        )


class GeoLocation(ValueObject):
    """A GeoJSON Point, ready for a MongoDB ``2dsphere`` index.

    MongoDB requires ``coordinates`` in ``[longitude, latitude]`` order, which is
    the reverse of how humans normally quote them, so latitude and longitude are
    also exposed as named properties.
    """

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] = Field(
        description="GeoJSON ordering: [longitude, latitude].",
    )

    @field_validator("coordinates")
    @classmethod
    def _validate_coordinate_ranges(cls, value: tuple[float, float]) -> tuple[float, float]:
        """Reject coordinates outside the valid geographic ranges."""
        longitude, latitude = value
        if not MIN_LONGITUDE <= longitude <= MAX_LONGITUDE:
            msg = f"longitude must be between {MIN_LONGITUDE} and {MAX_LONGITUDE}"
            raise ValueError(msg)
        if not MIN_LATITUDE <= latitude <= MAX_LATITUDE:
            msg = f"latitude must be between {MIN_LATITUDE} and {MAX_LATITUDE}"
            raise ValueError(msg)
        return value

    @classmethod
    def from_lat_lon(cls, latitude: float, longitude: float) -> Self:
        """Build a point from human-ordered latitude and longitude."""
        return cls(coordinates=(longitude, latitude))

    @property
    def longitude(self) -> float:
        """Return the longitude component."""
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        """Return the latitude component."""
        return self.coordinates[1]


class Address(ValueObject):
    """A postal address as captured on citizen and hospital forms."""

    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    pincode: Annotated[str, Field(pattern=r"^\d{6}$")] = Field(
        description="Six-digit Indian PIN code.",
    )


class TimestampedDocument(Document):
    """Base document carrying creation and update timestamps.

    Every collection in the platform inherits from this so the analytics engine
    can reason about record age and change velocity uniformly.

    ``validate_assignment`` is on deliberately. Without it a caller could
    construct a valid document and then mutate it into an invalid one --
    emptying a complaint's mandatory evidence, or pushing available stock above
    total stock -- and the invalid state would be written straight to MongoDB.
    Validators must guard mutation, not just construction.
    """

    model_config = ConfigDict(validate_assignment=True)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def touch(self) -> None:
        """Stamp ``updated_at`` with the current time ahead of a write."""
        self.updated_at = utcnow()
