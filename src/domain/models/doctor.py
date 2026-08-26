"""The ``doctors`` collection: licensed physicians and their availability.

Backs the Hospital Doctor Onboarding Form. ``max_daily_patients`` is the
capacity signal the future workforce-reallocation module reads when deciding
whether a department is over-subscribed.
"""

from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import EmailStr, Field, model_validator
from pymongo import IndexModel

from src.domain.enums import EmploymentType, ShiftType, StaffStatus
from src.domain.models.base import ProtectedNationalId, TimestampedDocument
from src.domain.types import LicenseNumber, PersonName, PhoneNumber, ShortText

__all__ = ["DEFAULT_MAX_DAILY_PATIENTS", "Doctor"]

DEFAULT_MAX_DAILY_PATIENTS = 30
MAX_ALLOWED_DAILY_PATIENTS = 200


class Doctor(TimestampedDocument):
    """A doctor onboarded to a hospital."""

    hospital_id: PydanticObjectId = Field(description="Employing hospital.")
    full_name: PersonName
    license_no: LicenseNumber = Field(
        description="Medical council licence number, unique across the platform."
    )
    specialization: ShortText = Field(description="e.g. 'Cardiology', 'Orthopaedics'.")
    department_id: PydanticObjectId = Field(description="Primary department.")
    qualification: ShortText = Field(description="e.g. 'MBBS, MD (Medicine)'.")

    # --- Contact ----------------------------------------------------------- #
    phone: PhoneNumber | None = Field(default=None)
    email: EmailStr | None = Field(default=None)
    national_id: ProtectedNationalId | None = Field(
        default=None, description="Encrypted National ID plus lookup hash."
    )

    # --- Engagement -------------------------------------------------------- #
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    shifts: list[ShiftType] = Field(
        default_factory=lambda: [ShiftType.GENERAL],
        min_length=1,
        description="One or more shifts this doctor covers.",
    )
    max_daily_patients: int = Field(
        default=DEFAULT_MAX_DAILY_PATIENTS,
        ge=1,
        le=MAX_ALLOWED_DAILY_PATIENTS,
        description="Upper bound on patients per day, used for load balancing.",
    )
    is_emergency_on_call: bool = Field(default=False)
    status: StaffStatus = Field(default=StaffStatus.ACTIVE)

    class Settings:
        """Beanie collection configuration."""

        name = "doctors"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("license_no", pymongo.ASCENDING)], unique=True, name="uq_doctors_license"),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("department_id", pymongo.ASCENDING)],
                name="ix_doctors_hospital_department",
            ),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("specialization", pymongo.ASCENDING)],
                name="ix_doctors_hospital_specialization",
            ),
            IndexModel([("status", pymongo.ASCENDING)], name="ix_doctors_status"),
        ]

    @model_validator(mode="after")
    def _validate_unique_shifts(self) -> Self:
        """Reject a duplicated shift entry, which would double-count availability."""
        if len(set(self.shifts)) != len(self.shifts):
            msg = "shifts must not contain duplicates"
            raise ValueError(msg)
        return self

    @property
    def is_available(self) -> bool:
        """Return whether this doctor can currently take patients."""
        return self.status is StaffStatus.ACTIVE
