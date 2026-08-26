"""Doctor Onboarding Form schemas."""

from typing import Self

from beanie import PydanticObjectId
from pydantic import EmailStr, Field, model_validator

from src.domain.enums import EmploymentType, ShiftType, StaffStatus
from src.domain.models.doctor import DEFAULT_MAX_DAILY_PATIENTS, MAX_ALLOWED_DAILY_PATIENTS
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import LicenseNumber, PersonName, PhoneNumber, ShortText

__all__ = ["DoctorOnboardingRequest", "DoctorResponse", "DoctorUpdateRequest"]


class DoctorOnboardingRequest(RequestSchema):
    """Doctor Onboarding Form."""

    full_name: PersonName
    license_no: LicenseNumber = Field(description="Medical council licence number.")
    specialization: ShortText
    department_id: PydanticObjectId
    qualification: ShortText = Field(description="e.g. 'MBBS, MD (Medicine)'.")

    phone: PhoneNumber | None = Field(default=None)
    email: EmailStr | None = Field(default=None)
    national_id: str | None = Field(
        default=None,
        min_length=6,
        max_length=32,
        description="Plaintext National ID; encrypted before storage.",
    )

    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    shifts: list[ShiftType] = Field(
        default_factory=lambda: [ShiftType.GENERAL],
        min_length=1,
        description="One or more shifts this doctor covers.",
    )
    max_daily_patients: int = Field(
        default=DEFAULT_MAX_DAILY_PATIENTS, ge=1, le=MAX_ALLOWED_DAILY_PATIENTS
    )
    is_emergency_on_call: bool = Field(default=False)

    @model_validator(mode="after")
    def _validate_unique_shifts(self) -> Self:
        """Reject duplicated shifts, which would double-count availability."""
        if len(set(self.shifts)) != len(self.shifts):
            msg = "shifts must not contain duplicates"
            raise ValueError(msg)
        return self


class DoctorUpdateRequest(RequestSchema):
    """Partial update to a doctor record. The licence number is immutable."""

    specialization: ShortText | None = Field(default=None)
    department_id: PydanticObjectId | None = Field(default=None)
    phone: PhoneNumber | None = Field(default=None)
    email: EmailStr | None = Field(default=None)
    employment_type: EmploymentType | None = Field(default=None)
    shifts: list[ShiftType] | None = Field(default=None, min_length=1)
    max_daily_patients: int | None = Field(default=None, ge=1, le=MAX_ALLOWED_DAILY_PATIENTS)
    is_emergency_on_call: bool | None = Field(default=None)
    status: StaffStatus | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_unique_shifts(self) -> Self:
        """Reject duplicated shifts when shifts are being replaced."""
        if self.shifts is not None and len(set(self.shifts)) != len(self.shifts):
            msg = "shifts must not contain duplicates"
            raise ValueError(msg)
        return self


class DoctorResponse(IdentifiedResponse):
    """A doctor as returned by the API."""

    hospital_id: PydanticObjectId
    full_name: str
    license_no: str
    specialization: str
    department_id: PydanticObjectId
    qualification: str
    phone: str | None = None
    email: EmailStr | None = None
    employment_type: EmploymentType
    shifts: list[ShiftType]
    max_daily_patients: int
    is_emergency_on_call: bool
    status: StaffStatus
