"""The ``patients`` collection: unified patient identity across hospitals.

Backs the Hospital Patient Intake Form (manual entry and Excel bulk upload).

The ``national_id`` lookup hash is what makes a *unified* record possible: the
same citizen treated at a public hospital in one state and a private hospital in
another resolves to the same person without any hospital ever storing the
plaintext National ID.
"""

from datetime import date
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, HttpUrl, model_validator
from pymongo import IndexModel

from src.domain.enums import BloodGroup, Gender
from src.domain.models.base import (
    ProtectedNationalId,
    TimestampedDocument,
    ValueObject,
    utcnow,
)
from src.domain.types import (
    MedicalRecordNumber,
    NonEmptyStr,
    PersonName,
    PhoneNumber,
    ShortText,
)

__all__ = ["EmergencyContact", "MedicalDocument", "Patient"]

MAX_HUMAN_AGE_YEARS = 130


class EmergencyContact(ValueObject):
    """Next of kin to contact about this patient."""

    name: PersonName
    phone: PhoneNumber
    relationship: ShortText = Field(description="e.g. 'Spouse', 'Son', 'Guardian'.")


class MedicalDocument(ValueObject):
    """A reference to an uploaded medical history file.

    Only the pointer and integrity metadata live in MongoDB; the bytes live in
    the object store chosen in a later phase.
    """

    file_name: ShortText
    url: HttpUrl = Field(description="Location of the stored file.")
    content_type: NonEmptyStr = Field(description="MIME type, e.g. 'application/pdf'.")
    size_bytes: int = Field(ge=0)
    checksum_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Hex SHA-256 of the file, for tamper detection.",
    )
    uploaded_at: date | None = Field(default=None)


class Patient(TimestampedDocument):
    """A patient registered at a hospital, optionally linked to a citizen account."""

    hospital_id: PydanticObjectId = Field(description="Hospital that registered this record.")
    mrn: MedicalRecordNumber = Field(
        description="Medical Record Number, unique within the hospital."
    )

    # --- Cross-hospital identity ------------------------------------------- #
    citizen_user_id: PydanticObjectId | None = Field(
        default=None, description="Linked citizen account, when the patient has one."
    )
    national_id: ProtectedNationalId | None = Field(
        default=None,
        description="Encrypted National ID plus deterministic lookup hash. "
        "The join key for a unified cross-hospital history.",
    )

    # --- Demographics ------------------------------------------------------ #
    full_name: PersonName
    gender: Gender
    date_of_birth: date | None = Field(default=None)
    age_years: int | None = Field(
        default=None,
        ge=0,
        le=MAX_HUMAN_AGE_YEARS,
        description="Recorded age, used when an exact date of birth is unknown.",
    )
    phone: PhoneNumber | None = Field(default=None)
    blood_group: BloodGroup = Field(default=BloodGroup.UNKNOWN)

    # --- Clinical background ----------------------------------------------- #
    emergency_contact: EmergencyContact | None = Field(default=None)
    allergies: list[ShortText] = Field(default_factory=list)
    pre_existing_conditions: list[ShortText] = Field(default_factory=list)
    medical_history_files: list[MedicalDocument] = Field(default_factory=list)

    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "patients"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("mrn", pymongo.ASCENDING)],
                unique=True,
                name="uq_patients_hospital_mrn",
            ),
            IndexModel(
                [("national_id.lookup_hash", pymongo.ASCENDING)],
                name="ix_patients_national_id_lookup",
                sparse=True,
            ),
            IndexModel([("citizen_user_id", pymongo.ASCENDING)], name="ix_patients_citizen"),
            IndexModel([("phone", pymongo.ASCENDING)], name="ix_patients_phone", sparse=True),
        ]

    @model_validator(mode="after")
    def _require_age_or_date_of_birth(self) -> Self:
        """Require at least one age signal.

        The intake form accepts either, but a record with neither cannot be
        triaged (paediatric versus geriatric protocols differ sharply).
        """
        if self.date_of_birth is None and self.age_years is None:
            msg = "either date_of_birth or age_years must be provided"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _reject_future_date_of_birth(self) -> Self:
        """A patient cannot be born in the future."""
        if self.date_of_birth is not None and self.date_of_birth > utcnow().date():
            msg = "date_of_birth cannot be in the future"
            raise ValueError(msg)
        return self

    @property
    def effective_age_years(self) -> int | None:
        """Return age derived from date of birth, falling back to the recorded age."""
        if self.date_of_birth is None:
            return self.age_years
        today = utcnow().date()
        years = today.year - self.date_of_birth.year
        had_birthday = (today.month, today.day) >= (
            self.date_of_birth.month,
            self.date_of_birth.day,
        )
        return years if had_birthday else years - 1
