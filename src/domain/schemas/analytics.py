"""Read-only schemas for the 7-module analytical intelligence engine.

**Zero PHI by construction.** Nothing in this module carries a patient
identifier, an MRN, a name, a National ID, a vitals reading, a prescription, a
bill amount, or any free-text clinical or grievance field. Analytics answers
questions about populations and resources, and it can answer every one of them
from counts, ratios, dates, and enum labels. A response schema is the last gate
before data leaves the process, so the constraint is enforced here rather than
trusted to each call site.

The single exception is :class:`DoctorLoadResponse`, which names a doctor
because "redistribute the ward" is not actionable without knowing who to move.
That is workforce data, not patient data, and it appears only on the
hospital-scoped workforce view -- the national view aggregates to department
level and carries no names at all.

Every module that infers rather than measures says so in its payload, through
:class:`~src.domain.enums.EstimationBasis` and
:class:`~src.domain.enums.SignalConfidence`. A dashboard that cannot tell a
measurement from an extrapolation will eventually present one as the other.
"""

from datetime import date, datetime

from beanie import PydanticObjectId
from pydantic import Field

from src.domain.enums import (
    ActionTaken,
    AlertKind,
    AlertTier,
    ComplaintCategory,
    EstimationBasis,
    InventoryCategory,
    InventoryUnit,
    InvestigationStatus,
    ShiftType,
    SignalConfidence,
    TrendDirection,
    TriageLevel,
)
from src.domain.schemas.common import ResponseSchema

__all__ = [
    "ActionCountResponse",
    "CategoryCountResponse",
    "DepartmentLoadResponse",
    "DoctorLoadResponse",
    "ForecastPointResponse",
    "NationalOverviewResponse",
    "OutbreakDetectionResponse",
    "OutbreakSignalResponse",
    "PolicyImpactResponse",
    "ReallocationSuggestionResponse",
    "RealtimeMonitoringResponse",
    "RecidivismEntryResponse",
    "ResourcePredictionResponse",
    "ResourceProjectionResponse",
    "ShiftBalanceResponse",
    "SmartAlertResponse",
    "SmartAlertsResponse",
    "StatusCountResponse",
    "SurgeForecastResponse",
    "TriageBreakdownEntry",
    "WorkforceReallocationResponse",
]


# --------------------------------------------------------------------------- #
# Module 1 -- Real-time monitoring
# --------------------------------------------------------------------------- #
class TriageBreakdownEntry(ResponseSchema):
    """Open cases at one triage level."""

    triage_level: TriageLevel
    open_cases: int = Field(ge=0)


class RealtimeMonitoringResponse(ResponseSchema):
    """Live occupancy and triage mix.

    Occupancy ratios are nullable rather than zero-defaulted. A hospital with no
    sanctioned ICU beds has *undefined* ICU occupancy, and rendering that as 0%
    would show a comfortably empty ward where there is in fact no ward at all.
    """

    hospital_id: PydanticObjectId | None = Field(
        default=None, description="None when the figures cover every hospital."
    )
    hospital_count: int = Field(ge=0, description="Hospitals rolled into these figures.")

    open_cases: int = Field(ge=0)
    admitted_cases: int = Field(ge=0)
    icu_cases: int = Field(ge=0)
    observation_cases: int = Field(ge=0)

    total_sanctioned_beds: int = Field(ge=0)
    icu_beds: int = Field(ge=0)

    bed_occupancy_ratio: float | None = Field(
        default=None, ge=0.0, description="Open cases per sanctioned bed. None if no beds."
    )
    icu_occupancy_ratio: float | None = Field(default=None, ge=0.0)
    ventilator_utilisation_ratio: float | None = Field(default=None, ge=0.0)
    oxygen_utilisation_ratio: float | None = Field(default=None, ge=0.0)

    triage_breakdown: list[TriageBreakdownEntry] = Field(default_factory=list)
    unclassified_cases: int = Field(
        default=0, ge=0, description="Open cases with neither a triage level nor a case type."
    )
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 2 -- Outbreak anomaly detection
# --------------------------------------------------------------------------- #
class OutbreakSignalResponse(ResponseSchema):
    """One zone-and-disease pair evaluated against its own recent history.

    Rates are per 100 000 residents because raw counts are not comparable across
    zones of different sizes, which is the reason ``zones.population_covered``
    exists as a stored field.
    """

    zone_code: str
    zone_name: str
    state: str
    city: str
    case_type_id: PydanticObjectId | None = None
    case_type_name: str
    icd10_code: str
    population_covered: int = Field(ge=0)

    observed_cases: int = Field(ge=0)
    observed_rate_per_100k: float | None = Field(default=None, ge=0.0)
    baseline_mean_rate_per_100k: float | None = Field(default=None, ge=0.0)
    z_score: float | None = Field(
        default=None,
        description="None when the baseline is flat or too short to support one.",
    )
    is_anomaly: bool
    confidence: SignalConfidence
    baseline_days: int = Field(ge=0)


class OutbreakDetectionResponse(ResponseSchema):
    """Every evaluated signal, with the flagged ones counted."""

    signals: list[OutbreakSignalResponse] = Field(default_factory=list)
    anomaly_count: int = Field(ge=0)
    evaluated_count: int = Field(ge=0)
    window_days: int = Field(ge=1)
    threshold: float
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 3 -- Surge forecasting
# --------------------------------------------------------------------------- #
class ForecastPointResponse(ResponseSchema):
    """One projected day with its 95% interval."""

    horizon_day: int = Field(ge=1)
    forecast_date: date
    predicted_admissions: float = Field(ge=0.0)
    lower_bound: float = Field(ge=0.0)
    upper_bound: float = Field(ge=0.0)


class SurgeForecastResponse(ResponseSchema):
    """A 7-to-14 day admissions projection from Holt's linear trend.

    ``history`` is returned alongside the projection so a client can plot the
    observed series and the forecast on one axis without a second call.
    """

    hospital_id: PydanticObjectId | None = None
    history: list[int] = Field(
        default_factory=list, description="Daily admissions, oldest first, ending today."
    )
    history_window_days: int = Field(ge=0)
    observations: int = Field(ge=0)

    points: list[ForecastPointResponse] = Field(default_factory=list)
    horizon_days: int = Field(ge=0)

    trend_direction: TrendDirection
    trend_per_day: float = Field(description="Fitted change in daily admissions, per day.")
    confidence: SignalConfidence

    projected_7_day_total: float = Field(ge=0.0)
    projected_14_day_total: float = Field(ge=0.0)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 4 -- Workforce reallocation
# --------------------------------------------------------------------------- #
class DoctorLoadResponse(ResponseSchema):
    """One doctor's current load against their declared daily ceiling.

    The only schema in this module naming a person, and only on the
    hospital-scoped view: reallocating a ward is not actionable without knowing
    who to move. Carries no contact details, licence number, or National ID.
    """

    doctor_id: PydanticObjectId
    full_name: str
    specialization: str
    department_id: PydanticObjectId
    is_available: bool

    active_load: int = Field(ge=0, description="Open cases currently assigned.")
    max_daily_patients: int = Field(ge=0)
    burnout_index: float | None = Field(
        default=None,
        ge=0.0,
        description="Active load per unit of daily capacity. None if no ceiling is set.",
    )
    is_overloaded: bool


class DepartmentLoadResponse(ResponseSchema):
    """Aggregate load for one department, carrying no names."""

    department_id: PydanticObjectId
    doctor_count: int = Field(ge=0)
    active_load: int = Field(ge=0)
    daily_capacity: int = Field(ge=0)
    burnout_index: float | None = Field(default=None, ge=0.0)


class ShiftBalanceResponse(ResponseSchema):
    """Headcount covering one shift.

    Doctors declare a list of shifts they cover while support and medical staff
    hold exactly one, so a doctor can legitimately appear under several shifts.
    """

    shift: ShiftType
    doctor_count: int = Field(ge=0)
    medical_staff_count: int = Field(ge=0)
    support_staff_count: int = Field(ge=0)


class ReallocationSuggestionResponse(ResponseSchema):
    """A proposed move from a department with slack to one under strain."""

    from_department_id: PydanticObjectId
    to_department_id: PydanticObjectId
    from_burnout_index: float
    to_burnout_index: float
    reason: str


class WorkforceReallocationResponse(ResponseSchema):
    """Burnout distribution, shift cover, and suggested moves.

    ``has_capacity_data`` exists so a client can distinguish "no doctors are
    under strain" from "no doctors are on file". Both would otherwise render as
    a reassuring zero.
    """

    hospital_id: PydanticObjectId | None = None
    has_capacity_data: bool

    doctor_count: int = Field(ge=0)
    active_doctor_count: int = Field(ge=0)
    total_active_load: int = Field(ge=0)
    total_daily_capacity: int = Field(ge=0)
    mean_burnout_index: float | None = Field(default=None, ge=0.0)
    overloaded_doctor_count: int = Field(ge=0)

    doctors: list[DoctorLoadResponse] = Field(
        default_factory=list,
        description="Per-doctor detail. Empty on the national view, which carries no names.",
    )
    departments: list[DepartmentLoadResponse] = Field(default_factory=list)
    shift_balance: list[ShiftBalanceResponse] = Field(default_factory=list)
    suggestions: list[ReallocationSuggestionResponse] = Field(default_factory=list)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 5 -- Resource prediction
# --------------------------------------------------------------------------- #
class ResourceProjectionResponse(ResponseSchema):
    """Days-to-stockout for one resource category at one hospital.

    ``days_to_stockout`` of ``None`` means no consumption has been observed, not
    that supply is unlimited. A client must render it as unknown rather than as
    a large comfortable number.
    """

    hospital_id: PydanticObjectId
    category: InventoryCategory
    line_count: int = Field(ge=0)

    total_stock: float = Field(ge=0.0)
    available_stock: float = Field(ge=0.0)
    min_safety_threshold: float = Field(ge=0.0)
    unit: InventoryUnit | None = Field(
        default=None, description="None when the hospital tracks nothing in this category."
    )

    daily_burn_rate: float = Field(ge=0.0, description="Estimated units consumed per day.")
    days_to_stockout: float | None = Field(default=None, ge=0.0)
    projected_stockout_on: date | None = Field(default=None)
    is_below_threshold: bool
    basis: EstimationBasis
    window_days: int = Field(ge=1)


class ResourcePredictionResponse(ResponseSchema):
    """Every category projection, with the at-risk ones counted."""

    projections: list[ResourceProjectionResponse] = Field(default_factory=list)
    at_risk_count: int = Field(ge=0, description="Projections stocking out inside the horizon.")
    window_days: int = Field(ge=1)
    basis: EstimationBasis
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 6 -- 4-tier Smart Alerts
# --------------------------------------------------------------------------- #
class SmartAlertResponse(ResponseSchema):
    """One triggered alert.

    Carries the measured value and the threshold it crossed, so the reader can
    see why it fired rather than trusting the tier. ``recommended_action`` says
    what to do about it: an alert nobody can act on is noise.
    """

    tier: AlertTier
    kind: AlertKind
    hospital_id: PydanticObjectId | None = None
    title: str
    detail: str
    metric_value: float | None = Field(default=None)
    threshold_value: float | None = Field(default=None)
    recommended_action: str


class SmartAlertsResponse(ResponseSchema):
    """Alerts ordered most severe first, with a count per tier."""

    alerts: list[SmartAlertResponse] = Field(default_factory=list)
    critical_count: int = Field(ge=0)
    high_count: int = Field(ge=0)
    medium_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Module 7 -- Policy impact tracking
# --------------------------------------------------------------------------- #
class CategoryCountResponse(ResponseSchema):
    """Complaints filed under one category."""

    category: ComplaintCategory
    count: int = Field(ge=0)


class StatusCountResponse(ResponseSchema):
    """Complaints sitting at one investigation status."""

    status: InvestigationStatus
    count: int = Field(ge=0)


class ActionCountResponse(ResponseSchema):
    """Enforcement decisions of one kind."""

    action: ActionTaken
    count: int = Field(ge=0)


class RecidivismEntryResponse(ResponseSchema):
    """A hospital that drew a further complaint of the same kind after enforcement.

    This is the closest the platform gets to measuring whether enforcement
    works: an action followed by more of the same complaint did not land.
    """

    hospital_id: PydanticObjectId
    category: ComplaintCategory
    action_taken: ActionTaken
    complaints_before_action: int = Field(ge=0)
    complaints_after_action: int = Field(ge=0)


class PolicyImpactResponse(ResponseSchema):
    """Grievance volume, enforcement mix, resolution speed, and recidivism.

    Resolution times are nullable rather than zero-defaulted: a ministry that
    has closed nothing has *no* mean resolution time, and reporting zero days
    would read as instant resolution.
    """

    hospital_id: PydanticObjectId | None = None
    total_complaints: int = Field(ge=0)
    closed_complaints: int = Field(ge=0)
    open_complaints: int = Field(ge=0)

    by_category: list[CategoryCountResponse] = Field(default_factory=list)
    by_status: list[StatusCountResponse] = Field(default_factory=list)
    by_action: list[ActionCountResponse] = Field(default_factory=list)

    mean_resolution_days: float | None = Field(default=None, ge=0.0)
    median_resolution_days: float | None = Field(default=None, ge=0.0)
    enforcement_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Closed complaints ending in an action other than dismissal.",
    )

    repeat_offender_count: int = Field(ge=0)
    recidivism: list[RecidivismEntryResponse] = Field(default_factory=list)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# National roll-up
# --------------------------------------------------------------------------- #
class NationalOverviewResponse(ResponseSchema):
    """The summary strip at the top of the ministry's command centre."""

    hospital_count: int = Field(ge=0)
    zone_count: int = Field(ge=0)
    population_covered: int = Field(ge=0)

    open_cases: int = Field(ge=0)
    total_sanctioned_beds: int = Field(ge=0)
    bed_occupancy_ratio: float | None = Field(default=None, ge=0.0)
    icu_occupancy_ratio: float | None = Field(default=None, ge=0.0)

    critical_alert_count: int = Field(ge=0)
    high_alert_count: int = Field(ge=0)
    outbreak_signal_count: int = Field(ge=0)
    at_risk_resource_count: int = Field(ge=0)
    open_complaint_count: int = Field(ge=0)
    generated_at: datetime
