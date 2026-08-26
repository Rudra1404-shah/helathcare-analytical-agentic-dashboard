"""Patient Intake Form schemas, including the Excel/CSV bulk upload contract.

Phase 1 defines the *shape* of a bulk upload -- one row schema plus a
per-row error report. The parser that turns an ``.xlsx``/``.csv`` file into
these rows is an ingestion service and arrives in Phase 2; having the contract
settled first means the parser has a target to validate against.
"""

from datetime import date
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import BloodGroup, Gender
from src.domain.models.patient import MAX_HUMAN_AGE_YEARS, EmergencyContact, MedicalDocument
from src.domain.schemas.common import IdentifiedResponse, RequestSchema, ResponseSchema
from src.domain.types import MedicalRecordNumber, PersonName, PhoneNumber, ShortText

__all__ = [
    "BulkUploadReport",
    "BulkUploadRowError",
    "PatientBulkUploadRow",
    "PatientIntakeRequest",
    "PatientResponse",
    "PatientUpdateRequest",
]


class _PatientCoreFields(RequestSchema):
    """Demographic fields shared by manual intake and bulk upload."""

    mrn: MedicalRecordNumber
    full_name: PersonName
    gender: Gender
    date_of_birth: date | None = Field(default=None)
    age_years: int | None = Field(default=None, ge=0, le=MAX_HUMAN_AGE_YEARS)
    phone: PhoneNumber | None = Field(default=None)
    blood_group: BloodGroup = Field(default=BloodGroup.UNKNOWN)
    national_id: str | None = Field(
        default=None,
        min_length=6,
        max_length=32,
        description="Plaintext National ID; encrypted before storage. "
        "This is the key that unifies a patient's history across hospitals.",
    )

    @model_validator(mode="after")
    def _require_age_or_date_of_birth(self) -> Self:
        """Require at least one age signal, mirroring the stored model."""
        if self.date_of_birth is None and self.age_years is None:
            msg = "either date_of_birth or age_years must be provided"
            raise ValueError(msg)
        return self


class PatientIntakeRequest(_PatientCoreFields):
    """Patient Intake Form, entered manually by hospital desk staff."""

    citizen_user_id: PydanticObjectId | None = Field(default=None)
    emergency_contact: EmergencyContact | None = Field(default=None)
    allergies: list[ShortText] = Field(default_factory=list)
    pre_existing_conditions: list[ShortText] = Field(default_factory=list)
    medical_history_files: list[MedicalDocument] = Field(default_factory=list)


class PatientBulkUploadRow(_PatientCoreFields):
    """One row of an uploaded ``.xlsx``/``.csv`` patient file.

    Allergies and conditions arrive as delimited strings in a spreadsheet cell
    rather than as lists, so they are captured as text and split on ingestion.
    """

    row_number: int = Field(ge=1, description="1-indexed row in the source file.")
    allergies_csv: str | None = Field(
        default=None,
        max_length=1000,
        description="Semicolon- or comma-separated allergies from a single cell.",
    )
    conditions_csv: str | None = Field(
        default=None,
        max_length=1000,
        description="Semicolon- or comma-separated pre-existing conditions.",
    )
    emergency_contact_name: PersonName | None = Field(default=None)
    emergency_contact_phone: PhoneNumber | None = Field(default=None)
    emergency_contact_relationship: ShortText | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_emergency_contact_completeness(self) -> Self:
        """An emergency contact needs a name, a phone, and a relationship, or none."""
        provided = [
            self.emergency_contact_name,
            self.emergency_contact_phone,
            self.emergency_contact_relationship,
        ]
        supplied = [value for value in provided if value]
        if supplied and len(supplied) != len(provided):
            msg = (
                "emergency contact requires name, phone, and relationship together; "
                "supply all three or none"
            )
            raise ValueError(msg)
        return self

    def split_allergies(self) -> list[str]:
        """Split the allergies cell into individual entries."""
        return _split_delimited(self.allergies_csv)

    def split_conditions(self) -> list[str]:
        """Split the conditions cell into individual entries."""
        return _split_delimited(self.conditions_csv)


def _split_delimited(raw: str | None) -> list[str]:
    """Split a spreadsheet cell on semicolons or commas, dropping empties."""
    if not raw:
        return []
    normalised = raw.replace(";", ",")
    return [part.strip() for part in normalised.split(",") if part.strip()]


class BulkUploadRowError(ResponseSchema):
    """Why one row of a bulk upload was rejected."""

    row_number: int = Field(ge=1)
    field: str | None = Field(default=None, description="Offending field, when known.")
    message: str = Field(description="Human-readable reason for rejection.")


class BulkUploadReport(ResponseSchema):
    """Outcome of an Excel/CSV patient upload.

    Rows are validated independently: a malformed row is reported and skipped
    rather than failing the whole file, so a thousand-row upload with two bad
    rows still imports nine hundred and ninety-eight patients.
    """

    total_rows: int = Field(ge=0)
    accepted: int = Field(ge=0)
    rejected: int = Field(ge=0)
    errors: list[BulkUploadRowError] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_counts_reconcile(self) -> Self:
        """Accepted plus rejected must account for every row."""
        if self.accepted + self.rejected != self.total_rows:
            msg = (
                f"accepted ({self.accepted}) + rejected ({self.rejected}) must equal "
                f"total_rows ({self.total_rows})"
            )
            raise ValueError(msg)
        if len(self.errors) != self.rejected:
            msg = f"errors list has {len(self.errors)} entries but rejected is {self.rejected}"
            raise ValueError(msg)
        return self


class PatientUpdateRequest(RequestSchema):
    """Partial update to a patient record. The MRN is immutable."""

    full_name: PersonName | None = Field(default=None)
    phone: PhoneNumber | None = Field(default=None)
    blood_group: BloodGroup | None = Field(default=None)
    emergency_contact: EmergencyContact | None = Field(default=None)
    allergies: list[ShortText] | None = Field(default=None)
    pre_existing_conditions: list[ShortText] | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class PatientResponse(IdentifiedResponse):
    """A patient as returned by the API.

    Carries no National ID in any form -- neither plaintext nor ciphertext.
    """

    hospital_id: PydanticObjectId
    mrn: str
    citizen_user_id: PydanticObjectId | None = None
    full_name: str
    gender: Gender
    date_of_birth: date | None = None
    age_years: int | None = None
    phone: str | None = None
    blood_group: BloodGroup
    emergency_contact: EmergencyContact | None = None
    allergies: list[str] = Field(default_factory=list)
    pre_existing_conditions: list[str] = Field(default_factory=list)
    medical_history_files: list[MedicalDocument] = Field(default_factory=list)
    is_active: bool
