"""Personal Health Record (PHR) schemas.

Backs the Citizen PHR Access Form: a citizen's complete medical history
assembled across every hospital that has treated them, plus an export envelope.

This is the payoff of the National ID lookup hash -- the same citizen treated at
a public hospital in one state and a private one in another resolves to a single
timeline here.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import BloodGroup, CaseStatus, Gender, PaymentStatus
from src.domain.models.patient import MedicalDocument
from src.domain.models.patient_case import Prescription, VitalSigns
from src.domain.schemas.common import RequestSchema, ResponseSchema

__all__ = [
    "PersonalHealthRecordResponse",
    "PhrBillSummary",
    "PhrCaseEntry",
    "PhrExportRequest",
    "PhrHospitalSummary",
]


class PhrHospitalSummary(ResponseSchema):
    """Minimal hospital identity shown alongside a history entry."""

    hospital_id: PydanticObjectId
    name: str
    city: str
    state: str


class PhrBillSummary(ResponseSchema):
    """Billing summary attached to a case in the citizen's history."""

    invoice_no: str
    grand_total: Decimal
    amount_paid: Decimal
    payment_status: PaymentStatus
    issued_at: datetime


class PhrCaseEntry(ResponseSchema):
    """One encounter in the citizen's cross-hospital timeline."""

    case_id: PydanticObjectId
    case_number: str
    hospital: PhrHospitalSummary
    department_name: str | None = None
    doctor_name: str | None = None
    case_type_name: str | None = None
    admitted_at: datetime
    discharged_at: datetime | None = None
    status: CaseStatus
    chief_symptoms: list[str] = Field(default_factory=list)
    vitals: list[VitalSigns] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)
    discharge_summary: str | None = None
    bill: PhrBillSummary | None = None


class PersonalHealthRecordResponse(ResponseSchema):
    """A citizen's complete health record across all hospitals."""

    citizen_user_id: PydanticObjectId
    full_name: str
    gender: Gender
    date_of_birth: date | None = None
    age_years: int | None = None
    blood_group: BloodGroup
    allergies: list[str] = Field(default_factory=list)
    pre_existing_conditions: list[str] = Field(default_factory=list)
    medical_history_files: list[MedicalDocument] = Field(default_factory=list)

    linked_patient_ids: list[PydanticObjectId] = Field(
        default_factory=list,
        description="Every hospital-local patient record resolved to this citizen.",
    )
    cases: list[PhrCaseEntry] = Field(
        default_factory=list, description="Encounters, most recent first."
    )
    generated_at: datetime

    @property
    def total_cases(self) -> int:
        """Return how many encounters the record contains."""
        return len(self.cases)

    @property
    def hospitals_visited(self) -> int:
        """Return how many distinct hospitals have treated this citizen."""
        return len({entry.hospital.hospital_id for entry in self.cases})


class PhrExportRequest(RequestSchema):
    """Request an export of the citizen's own health record."""

    include_bills: bool = Field(default=True)
    include_prescriptions: bool = Field(default=True)
    include_vitals: bool = Field(default=False)
    from_date: date | None = Field(default=None)
    to_date: date | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_date_range(self) -> Self:
        """The range must not run backwards."""
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.to_date < self.from_date
        ):
            msg = "to_date cannot precede from_date"
            raise ValueError(msg)
        return self
