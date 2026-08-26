"""Hospital registration, infrastructure, and profile schemas.

Covers the Government Hospital Verification & Accreditation Form and the
Hospital Profile & Infrastructure Setup Form.

Forms accept coordinates in human order (latitude, then longitude);
:class:`GeoPointPayload` flips them into the GeoJSON order MongoDB requires, so
callers never have to remember the reversal.
"""

from datetime import date
from typing import Self

from beanie import PydanticObjectId
from pydantic import EmailStr, Field, model_validator

from src.domain.enums import AccreditationStatus, SectorType
from src.domain.models.base import (
    MAX_LATITUDE,
    MAX_LONGITUDE,
    MIN_LATITUDE,
    MIN_LONGITUDE,
    Address,
    GeoLocation,
)
from src.domain.schemas.common import IdentifiedResponse, RequestSchema, ResponseSchema
from src.domain.types import LicenseNumber, PersonName, PhoneNumber, ShortText

__all__ = [
    "GeoPointPayload",
    "HospitalCapacityPayload",
    "HospitalCapacityResponse",
    "HospitalCreateRequest",
    "HospitalProfileUpdateRequest",
    "HospitalResponse",
]


class GeoPointPayload(RequestSchema):
    """Latitude/longitude as a human would type them."""

    latitude: float = Field(ge=MIN_LATITUDE, le=MAX_LATITUDE)
    longitude: float = Field(ge=MIN_LONGITUDE, le=MAX_LONGITUDE)

    def to_geo_location(self) -> GeoLocation:
        """Convert to the stored GeoJSON representation."""
        return GeoLocation.from_lat_lon(latitude=self.latitude, longitude=self.longitude)


class HospitalCapacityPayload(RequestSchema):
    """Bed, ventilator, oxygen, and ambulance counts."""

    total_sanctioned_beds: int = Field(ge=0)
    icu_beds: int = Field(ge=0)
    emergency_beds: int = Field(default=0, ge=0)
    ventilators: int = Field(default=0, ge=0)
    oxygen_bulk_capacity_liters: float = Field(default=0.0, ge=0.0)
    ambulance_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_bed_subsets(self) -> Self:
        """Mirror the model rule so the API rejects bad capacity early."""
        specialised = self.icu_beds + self.emergency_beds
        if specialised > self.total_sanctioned_beds:
            msg = (
                f"icu_beds + emergency_beds ({specialised}) cannot exceed "
                f"total_sanctioned_beds ({self.total_sanctioned_beds})"
            )
            raise ValueError(msg)
        return self


class HospitalCreateRequest(RequestSchema):
    """Government Hospital Verification & Accreditation Form."""

    name: ShortText
    license_no: LicenseNumber
    sector_type: SectorType

    state: ShortText
    city: ShortText
    zone_code: str = Field(min_length=2, max_length=30)
    ward_area: ShortText | None = Field(default=None)
    location: GeoPointPayload
    address: Address | None = Field(default=None)

    capacity: HospitalCapacityPayload

    accreditation_status: AccreditationStatus = Field(default=AccreditationStatus.PENDING)
    accredited_on: date | None = Field(default=None)
    license_valid_until: date | None = Field(default=None)
    nodal_officer_name: PersonName | None = Field(default=None)
    nodal_officer_id: PydanticObjectId | None = Field(default=None)

    contact_phone: PhoneNumber | None = Field(default=None)
    contact_email: EmailStr | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_accreditation_dates(self) -> Self:
        """An accredited hospital must say when accreditation was granted."""
        granted = {AccreditationStatus.NABH, AccreditationStatus.STATE_LICENSED}
        if self.accreditation_status in granted and self.accredited_on is None:
            msg = (
                f"accredited_on is required when accreditation_status is "
                f"{self.accreditation_status}"
            )
            raise ValueError(msg)
        return self


class HospitalProfileUpdateRequest(RequestSchema):
    """Hospital Profile & Infrastructure Setup Form.

    Hospital admins maintain operational infrastructure; they cannot alter their
    own licence number, sector, or accreditation state, so those fields are
    absent by design.
    """

    capacity: HospitalCapacityPayload | None = Field(default=None)
    ward_area: ShortText | None = Field(default=None)
    address: Address | None = Field(default=None)
    location: GeoPointPayload | None = Field(default=None)
    contact_phone: PhoneNumber | None = Field(default=None)
    contact_email: EmailStr | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class HospitalCapacityResponse(ResponseSchema):
    """Capacity as returned by the API."""

    total_sanctioned_beds: int
    icu_beds: int
    emergency_beds: int
    ventilators: int
    oxygen_bulk_capacity_liters: float
    ambulance_count: int


class HospitalResponse(IdentifiedResponse):
    """A hospital record as returned by the API."""

    name: str
    license_no: str
    sector_type: SectorType
    state: str
    city: str
    zone_code: str
    ward_area: str | None = None
    location: GeoLocation
    capacity: HospitalCapacityResponse
    accreditation_status: AccreditationStatus
    accredited_on: date | None = None
    license_valid_until: date | None = None
    nodal_officer_name: str | None = None
    contact_phone: str | None = None
    contact_email: EmailStr | None = None
    is_active: bool
