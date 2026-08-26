"""Patient Case / Encounter Form schemas.

Admission, vitals recording, and discharge are separate operations against the
same case, so each gets its own request schema rather than one giant payload
whose fields are conditionally required.
"""

from datetime import datetime
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus, TriageLevel
from src.domain.models.patient_case import Prescription, VitalSigns
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import ShortText

__all__ = [
    "CaseAdmissionRequest",
    "CaseDischargeRequest",
    "CaseStatusUpdateRequest",
    "PatientCaseResponse",
    "PrescriptionRequest",
    "VitalSignsRequest",
]


class VitalSignsRequest(RequestSchema):
    """One set of bedside observations appended to a case."""

    systolic_bp: int = Field(ge=40, le=300)
    diastolic_bp: int = Field(ge=20, le=200)
    pulse_bpm: int = Field(ge=20, le=300)
    spo2_percent: float = Field(ge=0.0, le=100.0)
    temperature_celsius: float = Field(ge=25.0, le=45.0)
    respiratory_rate: int | None = Field(default=None, ge=4, le=80)
    recorded_at: datetime | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_blood_pressure_ordering(self) -> Self:
        """Systolic pressure must exceed diastolic."""
        if self.systolic_bp <= self.diastolic_bp:
            msg = (
                f"systolic_bp ({self.systolic_bp}) must be greater than "
                f"diastolic_bp ({self.diastolic_bp})"
            )
            raise ValueError(msg)
        return self


class PrescriptionRequest(RequestSchema):
    """A medication order added to a case."""

    medicine_name: ShortText
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    duration_days: int = Field(ge=1, le=365)
    notes: str | None = Field(default=None, max_length=500)


class CaseAdmissionRequest(RequestSchema):
    """Open a new case for a patient."""

    case_number: str = Field(min_length=3, max_length=40)
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId
    department_id: PydanticObjectId
    case_type_id: PydanticObjectId | None = Field(default=None)
    bed_allocated: str | None = Field(default=None, max_length=40)
    triage_level: TriageLevel | None = Field(default=None)
    admitted_at: datetime | None = Field(default=None)
    chief_symptoms: list[ShortText] = Field(
        min_length=1, description="At least one presenting symptom is required."
    )
    initial_vitals: VitalSignsRequest | None = Field(default=None)
    status: CaseStatus = Field(default=CaseStatus.ADMITTED)

    @model_validator(mode="after")
    def _reject_terminal_status_on_admission(self) -> Self:
        """A case cannot be opened already discharged or deceased."""
        if self.status in TERMINAL_CASE_STATUSES:
            msg = f"a case cannot be admitted with status {self.status}; use the discharge form"
            raise ValueError(msg)
        return self


class CaseStatusUpdateRequest(RequestSchema):
    """Move a case between open states, or reassign its bed."""

    status: CaseStatus | None = Field(default=None)
    bed_allocated: str | None = Field(default=None, max_length=40)
    doctor_id: PydanticObjectId | None = Field(default=None)
    case_type_id: PydanticObjectId | None = Field(default=None)
    triage_level: TriageLevel | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _reject_terminal_status(self) -> Self:
        """Closing a case requires the discharge form, which captures the summary."""
        if self.status in TERMINAL_CASE_STATUSES:
            msg = (
                f"status {self.status} closes the case and must be set through the "
                f"discharge form, which requires a discharge summary"
            )
            raise ValueError(msg)
        return self


class CaseDischargeRequest(RequestSchema):
    """Close a case, recording the outcome."""

    status: CaseStatus = Field(description="Must be DISCHARGED or DECEASED.")
    discharged_at: datetime | None = Field(default=None)
    discharge_summary: str = Field(
        min_length=1,
        max_length=5000,
        description="Mandatory narrative of the outcome.",
    )

    @model_validator(mode="after")
    def _validate_terminal_status(self) -> Self:
        """Only terminal statuses may be set through the discharge form."""
        if self.status not in TERMINAL_CASE_STATUSES:
            msg = f"discharge requires status DISCHARGED or DECEASED, got {self.status}"
            raise ValueError(msg)
        return self


class PatientCaseResponse(IdentifiedResponse):
    """A case as returned by the API."""

    case_number: str
    hospital_id: PydanticObjectId
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId
    department_id: PydanticObjectId
    case_type_id: PydanticObjectId | None = None
    bed_allocated: str | None = None
    triage_level: TriageLevel | None = None
    admitted_at: datetime
    discharged_at: datetime | None = None
    chief_symptoms: list[str]
    vitals: list[VitalSigns] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)
    status: CaseStatus
    discharge_summary: str | None = None
