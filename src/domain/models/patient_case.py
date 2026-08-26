"""The ``patient_cases`` collection: admissions, encounters, and discharges.

Backs the Hospital Patient Case / Encounter Form. This is the highest-volume
collection in the platform and the primary feed for the real-time monitoring,
surge-forecasting, and outbreak-detection modules.
"""

from datetime import datetime
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, model_validator
from pymongo import IndexModel

from src.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus, TriageLevel
from src.domain.models.base import TimestampedDocument, ValueObject, utcnow
from src.domain.types import NonEmptyStr, ShortText

__all__ = ["PatientCase", "Prescription", "VitalSigns"]

# Physiologically plausible bounds. Values outside these ranges indicate a data
# entry error rather than a real observation, and would poison trend analytics.
MIN_SYSTOLIC_BP = 40
MAX_SYSTOLIC_BP = 300
MIN_DIASTOLIC_BP = 20
MAX_DIASTOLIC_BP = 200
MIN_PULSE_BPM = 20
MAX_PULSE_BPM = 300
MIN_TEMPERATURE_C = 25.0
MAX_TEMPERATURE_C = 45.0
MIN_RESPIRATORY_RATE = 4
MAX_RESPIRATORY_RATE = 80


class VitalSigns(ValueObject):
    """One timestamped set of bedside observations.

    Cases hold a list of these rather than a single snapshot, because
    deterioration is visible only as a trend.
    """

    systolic_bp: int = Field(ge=MIN_SYSTOLIC_BP, le=MAX_SYSTOLIC_BP, description="mmHg.")
    diastolic_bp: int = Field(ge=MIN_DIASTOLIC_BP, le=MAX_DIASTOLIC_BP, description="mmHg.")
    pulse_bpm: int = Field(ge=MIN_PULSE_BPM, le=MAX_PULSE_BPM, description="Beats per minute.")
    spo2_percent: float = Field(
        ge=0.0, le=100.0, description="Peripheral oxygen saturation, percent."
    )
    temperature_celsius: float = Field(ge=MIN_TEMPERATURE_C, le=MAX_TEMPERATURE_C)
    respiratory_rate: int | None = Field(
        default=None, ge=MIN_RESPIRATORY_RATE, le=MAX_RESPIRATORY_RATE
    )
    recorded_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _validate_blood_pressure_ordering(self) -> Self:
        """Systolic pressure must exceed diastolic; the reverse is impossible."""
        if self.systolic_bp <= self.diastolic_bp:
            msg = (
                f"systolic_bp ({self.systolic_bp}) must be greater than "
                f"diastolic_bp ({self.diastolic_bp})"
            )
            raise ValueError(msg)
        return self


class Prescription(ValueObject):
    """A single medication order within a case."""

    medicine_name: ShortText
    dosage: NonEmptyStr = Field(description="e.g. '500 mg'.")
    frequency: NonEmptyStr = Field(description="e.g. 'twice daily'.")
    duration_days: int = Field(ge=1, le=365)
    notes: str | None = Field(default=None, max_length=500)
    prescribed_at: datetime = Field(default_factory=utcnow)


class PatientCase(TimestampedDocument):
    """A patient encounter, from admission through to discharge."""

    # --- Identity ---------------------------------------------------------- #
    case_number: str = Field(
        min_length=3,
        max_length=40,
        description="Human-facing case identifier, unique within the hospital.",
    )
    hospital_id: PydanticObjectId
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId = Field(description="Attending doctor.")
    department_id: PydanticObjectId
    case_type_id: PydanticObjectId | None = Field(
        default=None, description="Classified case type; may be assigned after triage."
    )

    # --- Placement --------------------------------------------------------- #
    bed_allocated: str | None = Field(
        default=None, max_length=40, description="Bed label, e.g. 'ICU-04'."
    )
    triage_level: TriageLevel | None = Field(
        default=None, description="Triage assigned at admission."
    )

    # --- Timeline ---------------------------------------------------------- #
    admitted_at: datetime = Field(default_factory=utcnow)
    discharged_at: datetime | None = Field(default=None)

    # --- Clinical content -------------------------------------------------- #
    chief_symptoms: list[ShortText] = Field(
        min_length=1, description="At least one presenting symptom is required."
    )
    vitals: list[VitalSigns] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)

    status: CaseStatus = Field(default=CaseStatus.ADMITTED)
    discharge_summary: str | None = Field(default=None, max_length=5000)

    class Settings:
        """Beanie collection configuration."""

        name = "patient_cases"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("case_number", pymongo.ASCENDING)],
                unique=True,
                name="uq_patient_cases_hospital_number",
            ),
            IndexModel([("patient_id", pymongo.ASCENDING)], name="ix_patient_cases_patient"),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
                name="ix_patient_cases_hospital_status",
            ),
            IndexModel(
                [("case_type_id", pymongo.ASCENDING), ("admitted_at", pymongo.DESCENDING)],
                name="ix_patient_cases_type_admitted",
            ),
            IndexModel([("doctor_id", pymongo.ASCENDING)], name="ix_patient_cases_doctor"),
            IndexModel([("admitted_at", pymongo.DESCENDING)], name="ix_patient_cases_admitted_at"),
        ]

    @model_validator(mode="after")
    def _validate_closure_details(self) -> Self:
        """A closed case must record when and why it closed.

        Without this, discharged cases would keep occupying beds in occupancy
        analytics and length-of-stay statistics would be uncomputable.
        """
        is_closed = self.status in TERMINAL_CASE_STATUSES
        if is_closed:
            if self.discharged_at is None:
                msg = f"discharged_at is required when status is {self.status}"
                raise ValueError(msg)
            if not self.discharge_summary:
                msg = f"discharge_summary is required when status is {self.status}"
                raise ValueError(msg)
        elif self.discharged_at is not None:
            msg = f"discharged_at must not be set while status is {self.status}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_timeline_ordering(self) -> Self:
        """Discharge cannot precede admission."""
        if self.discharged_at is not None and self.discharged_at < self.admitted_at:
            msg = "discharged_at cannot precede admitted_at"
            raise ValueError(msg)
        return self

    @property
    def is_open(self) -> bool:
        """Return whether this case still occupies capacity."""
        return self.status not in TERMINAL_CASE_STATUSES

    @property
    def latest_vitals(self) -> VitalSigns | None:
        """Return the most recently recorded observation set."""
        if not self.vitals:
            return None
        return max(self.vitals, key=lambda reading: reading.recorded_at)
