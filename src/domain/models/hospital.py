"""The ``hospitals`` collection: accreditation, location, and physical capacity.

Backs two forms that describe the same real-world entity from different sides:

* the Government **Hospital Verification & Accreditation Form** (licence,
  sector, sanctioned capacity, accreditation state), and
* the Hospital **Profile & Infrastructure Setup Form** (working bed counts,
  oxygen, ambulances).

They share one document so that a ministry official and a hospital admin can
never disagree about how many beds a hospital has.
"""

from datetime import date
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import EmailStr, Field, model_validator
from pymongo import IndexModel

from src.domain.enums import AccreditationStatus, SectorType
from src.domain.models.base import Address, GeoLocation, TimestampedDocument, ValueObject
from src.domain.types import LicenseNumber, PersonName, PhoneNumber, ShortText

__all__ = ["Hospital", "HospitalCapacity"]


class HospitalCapacity(ValueObject):
    """Physical capacity of a hospital.

    ICU and emergency beds are subsets of the sanctioned total, so their sum can
    never exceed it. Getting this wrong would let a hospital appear to have more
    capacity than the ministry sanctioned.
    """

    total_sanctioned_beds: int = Field(ge=0, description="Beds sanctioned by the ministry.")
    icu_beds: int = Field(ge=0, description="Subset of sanctioned beds that are ICU.")
    emergency_beds: int = Field(
        default=0, ge=0, description="Subset of sanctioned beds reserved for emergency."
    )
    ventilators: int = Field(default=0, ge=0)
    oxygen_bulk_capacity_liters: float = Field(
        default=0.0, ge=0.0, description="Bulk medical oxygen storage capacity in litres."
    )
    ambulance_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_bed_subsets(self) -> Self:
        """Ensure specialised beds do not exceed the sanctioned total."""
        specialised = self.icu_beds + self.emergency_beds
        if specialised > self.total_sanctioned_beds:
            msg = (
                f"icu_beds + emergency_beds ({specialised}) cannot exceed "
                f"total_sanctioned_beds ({self.total_sanctioned_beds})"
            )
            raise ValueError(msg)
        return self


class Hospital(TimestampedDocument):
    """A registered public, private, or trust hospital."""

    # --- Identity --------------------------------------------------------- #
    name: ShortText = Field(description="Registered hospital name.")
    license_no: LicenseNumber = Field(description="Unique government licence number.")
    sector_type: SectorType

    # --- Location --------------------------------------------------------- #
    state: ShortText
    city: ShortText
    zone_code: str = Field(min_length=2, max_length=30, description="References Zone.zone_code.")
    ward_area: ShortText | None = Field(default=None)
    location: GeoLocation = Field(description="Geo-coordinates for mapping and routing.")
    address: Address | None = Field(default=None)

    # --- Capacity --------------------------------------------------------- #
    capacity: HospitalCapacity

    # --- Accreditation ---------------------------------------------------- #
    accreditation_status: AccreditationStatus = Field(default=AccreditationStatus.PENDING)
    accredited_on: date | None = Field(default=None)
    license_valid_until: date | None = Field(default=None)
    nodal_officer_name: PersonName | None = Field(
        default=None, description="Ministry officer assigned to this hospital."
    )
    nodal_officer_id: PydanticObjectId | None = Field(
        default=None, description="References the assigned officer's User document."
    )

    # --- Contact ---------------------------------------------------------- #
    contact_phone: PhoneNumber | None = Field(default=None)
    contact_email: EmailStr | None = Field(default=None)

    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "hospitals"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("license_no", pymongo.ASCENDING)], unique=True, name="uq_hospitals_license"
            ),
            IndexModel(
                [("state", pymongo.ASCENDING), ("city", pymongo.ASCENDING)],
                name="ix_hospitals_state_city",
            ),
            IndexModel([("zone_code", pymongo.ASCENDING)], name="ix_hospitals_zone"),
            IndexModel(
                [("sector_type", pymongo.ASCENDING), ("accreditation_status", pymongo.ASCENDING)],
                name="ix_hospitals_sector_accreditation",
            ),
            IndexModel([("location", pymongo.GEOSPHERE)], name="ix_hospitals_location_2dsphere"),
        ]

    @model_validator(mode="after")
    def _validate_accreditation_dates(self) -> Self:
        """An accredited hospital must record when accreditation was granted."""
        granted_statuses = {AccreditationStatus.NABH, AccreditationStatus.STATE_LICENSED}
        if self.accreditation_status in granted_statuses and self.accredited_on is None:
            msg = (
                f"accredited_on is required when accreditation_status is "
                f"{self.accreditation_status}"
            )
            raise ValueError(msg)
        if (
            self.accredited_on is not None
            and self.license_valid_until is not None
            and self.license_valid_until < self.accredited_on
        ):
            msg = "license_valid_until cannot precede accredited_on"
            raise ValueError(msg)
        return self

    @property
    def is_blacklisted(self) -> bool:
        """Return whether the ministry has blacklisted this hospital."""
        return self.accreditation_status is AccreditationStatus.BLACKLISTED
