"""Pure document-to-response reducers for the analytical intelligence engine.

Every function here takes documents that have **already been fetched** and
returns a response schema. Nothing in this module touches Beanie, the event
loop, or the network, which is the whole point: `CLAUDE.md` requires unit tests
to run without MongoDB, and the interesting logic in an analytics engine is
precisely the arithmetic, not the query. Splitting the fetch away lets the
arithmetic be tested exhaustively against hand-built documents.

:mod:`src.services.analytics_service` is the public entry point; it resolves
tenancy, fetches, audits, and delegates here. These functions are re-exported
from there, so callers never need to import this module directly.

Documents that have never been persisted carry ``id is None``. Where a reducer
groups by identity it skips those rather than inventing one, so an in-memory
document can never silently merge with another.
"""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from beanie import PydanticObjectId

from src.domain.enums import (
    CLOSED_INVESTIGATION_STATUSES,
    TERMINAL_CASE_STATUSES,
    ActionTaken,
    AlertKind,
    AlertTier,
    CaseStatus,
    ComplaintCategory,
    EstimationBasis,
    InventoryCategory,
    InventoryUnit,
    InvestigationStatus,
    ShiftType,
    SignalConfidence,
    StaffCategory,
    StaffStatus,
    TrendDirection,
    TriageLevel,
)
from src.domain.models import (
    CaseType,
    Complaint,
    Doctor,
    Hospital,
    InventoryItem,
    PatientCase,
    Staff,
    Zone,
)
from src.domain.schemas.analytics import (
    ActionCountResponse,
    CategoryCountResponse,
    DepartmentLoadResponse,
    DoctorLoadResponse,
    ForecastPointResponse,
    OutbreakDetectionResponse,
    OutbreakSignalResponse,
    PolicyImpactResponse,
    ReallocationSuggestionResponse,
    RealtimeMonitoringResponse,
    RecidivismEntryResponse,
    ResourcePredictionResponse,
    ResourceProjectionResponse,
    ShiftBalanceResponse,
    SmartAlertResponse,
    SmartAlertsResponse,
    StatusCountResponse,
    SurgeForecastResponse,
    TriageBreakdownEntry,
    WorkforceReallocationResponse,
)
from src.services.analytics_math import (
    MIN_BASELINE_OBSERVATIONS,
    MIN_OBSERVATIONS_FOR_TREND,
    bucket_by_day,
    days_to_stockout,
    holt_linear_forecast,
    mean,
    median,
    per_capita,
    safe_ratio,
    z_score,
)

__all__ = [
    "AT_RISK_STOCKOUT_DAYS",
    "CRITICAL_ICU_OCCUPANCY",
    "CRITICAL_STOCKOUT_DAYS",
    "CRITICAL_Z_SCORE",
    "DEFAULT_BASELINE_WINDOW_DAYS",
    "DEFAULT_FORECAST_HORIZON_DAYS",
    "DEFAULT_HISTORY_WINDOW_DAYS",
    "DEFAULT_OUTBREAK_THRESHOLD",
    "HIGH_BED_OCCUPANCY",
    "HIGH_BURNOUT_INDEX",
    "HIGH_STOCKOUT_DAYS",
    "HIGH_Z_SCORE",
    "MEDIUM_OCCUPANCY",
    "MEDIUM_STOCKOUT_DAYS",
    "OVERLOAD_BURNOUT_INDEX",
    "SLACK_BURNOUT_INDEX",
    "UNITS_CONSUMED_PER_CASE",
    "summarise_outbreaks",
    "summarise_policy_impact",
    "summarise_realtime",
    "summarise_resources",
    "summarise_surge",
    "summarise_workforce",
    "synthesise_alerts",
]

# --------------------------------------------------------------------------- #
# Window defaults
# --------------------------------------------------------------------------- #
DEFAULT_BASELINE_WINDOW_DAYS = 28
"""Four weeks of history: long enough for a baseline, short enough to stay current."""

DEFAULT_HISTORY_WINDOW_DAYS = 30
"""Observed series length fed to the forecaster."""

DEFAULT_FORECAST_HORIZON_DAYS = 14
"""Upper end of the 7-to-14 day horizon the brief asks for."""

DEFAULT_OUTBREAK_THRESHOLD = 2.0
"""Two standard deviations above baseline, the conventional epidemiological trigger."""

# --------------------------------------------------------------------------- #
# Alert thresholds
#
# Named rather than inlined so the tiering rules can be read in one place and
# changed without hunting through branches.
# --------------------------------------------------------------------------- #
CRITICAL_ICU_OCCUPANCY = 0.95
HIGH_BED_OCCUPANCY = 0.90
MEDIUM_OCCUPANCY = 0.75

CRITICAL_STOCKOUT_DAYS = 2.0
HIGH_STOCKOUT_DAYS = 7.0
MEDIUM_STOCKOUT_DAYS = 14.0
AT_RISK_STOCKOUT_DAYS = 14.0

CRITICAL_Z_SCORE = 3.0
HIGH_Z_SCORE = 2.0

HIGH_BURNOUT_INDEX = 1.5
OVERLOAD_BURNOUT_INDEX = 1.0
SLACK_BURNOUT_INDEX = 0.5

TREND_EPSILON = 0.05
"""Below this daily change, a fitted trend is called stable rather than moving."""

MAX_PROJECTION_DAYS = 3650
"""Cap on a projected stockout date, so a tiny burn rate cannot overflow a date."""

_HIGH_CONFIDENCE_BASELINE_DAYS = 14
_HIGH_CONFIDENCE_OBSERVATIONS = 21
_FLAT_BASELINE_SURGE_MULTIPLE = 2.0

UNITS_CONSUMED_PER_CASE: dict[InventoryCategory, float] = {
    InventoryCategory.GENERAL_BEDS: 1.0,
    InventoryCategory.ICU_BEDS: 1.0,
    InventoryCategory.VENTILATORS: 1.0,
    InventoryCategory.OXYGEN_CYLINDERS: 1.0,
    InventoryCategory.OXYGEN_LITERS: 500.0,
    InventoryCategory.MEDICINES: 4.0,
    InventoryCategory.CONSUMABLES: 6.0,
}
"""Declared planning assumptions converting one case into units consumed.

The platform stores current stock but no stock-movement ledger, so consumption
is inferred rather than measured. Countable resources are one unit per case; a
ventilated day is roughly 500 litres of oxygen at typical flow; medicines and
consumables are multi-unit per admission. These are stated assumptions, not
observations, which is exactly why every projection built from them is stamped
:attr:`~src.domain.enums.EstimationBasis.ESTIMATED_FROM_CASE_DEMAND`.
"""

_ICU_DRIVEN_CATEGORIES = frozenset(
    {
        InventoryCategory.ICU_BEDS,
        InventoryCategory.VENTILATORS,
        InventoryCategory.OXYGEN_CYLINDERS,
        InventoryCategory.OXYGEN_LITERS,
    }
)
"""Categories whose demand tracks critical care rather than total admissions."""

_TIER_ORDER: dict[AlertTier, int] = {
    AlertTier.CRITICAL: 0,
    AlertTier.HIGH: 1,
    AlertTier.MEDIUM: 2,
    AlertTier.INFO: 3,
}


def _identity(document: CaseType | Doctor | InventoryItem) -> PydanticObjectId | None:
    """Return a document's id, or ``None`` when it has never been persisted."""
    return document.id


def _aware(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC so it can be compared with an aware one.

    Beanie clients set ``tz_aware=True`` so stored values arrive aware; this
    covers documents built in memory, which are otherwise incomparable.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _is_open(case: PatientCase) -> bool:
    """Return whether a case is still occupying capacity."""
    return case.status not in TERMINAL_CASE_STATUSES


# --------------------------------------------------------------------------- #
# Module 1 -- Real-time monitoring
# --------------------------------------------------------------------------- #
def summarise_realtime(
    *,
    hospitals: list[Hospital],
    cases: list[PatientCase],
    items: list[InventoryItem],
    case_types: list[CaseType],
    hospital_id: PydanticObjectId | None,
    now: datetime,
) -> RealtimeMonitoringResponse:
    """Roll live occupancy and triage mix up from open cases and capacity.

    Triage is read from the case where it was assigned at admission and falls
    back to the case type's default, because a case can be triaged before it is
    classified. Cases with neither are counted separately rather than being
    folded into the least urgent bucket, which would understate acuity.
    """
    open_cases = [case for case in cases if _is_open(case)]
    by_status = Counter(case.status for case in open_cases)

    sanctioned_beds = sum(hospital.capacity.total_sanctioned_beds for hospital in hospitals)
    icu_beds = sum(hospital.capacity.icu_beds for hospital in hospitals)

    triage_by_type: dict[PydanticObjectId, TriageLevel] = {
        case_type_id: case_type.triage_level
        for case_type in case_types
        if (case_type_id := _identity(case_type)) is not None
    }

    triage_counts: Counter[TriageLevel] = Counter()
    unclassified = 0
    for case in open_cases:
        level = case.triage_level
        if level is None and case.case_type_id is not None:
            level = triage_by_type.get(case.case_type_id)
        if level is None:
            unclassified += 1
        else:
            triage_counts[level] += 1

    return RealtimeMonitoringResponse(
        hospital_id=hospital_id,
        hospital_count=len(hospitals),
        open_cases=len(open_cases),
        admitted_cases=by_status[CaseStatus.ADMITTED],
        icu_cases=by_status[CaseStatus.ICU],
        observation_cases=by_status[CaseStatus.OBSERVATION],
        total_sanctioned_beds=sanctioned_beds,
        icu_beds=icu_beds,
        bed_occupancy_ratio=safe_ratio(len(open_cases), sanctioned_beds),
        icu_occupancy_ratio=safe_ratio(by_status[CaseStatus.ICU], icu_beds),
        ventilator_utilisation_ratio=_category_utilisation(items, (InventoryCategory.VENTILATORS,)),
        oxygen_utilisation_ratio=_category_utilisation(
            items, (InventoryCategory.OXYGEN_CYLINDERS, InventoryCategory.OXYGEN_LITERS)
        ),
        triage_breakdown=[
            TriageBreakdownEntry(triage_level=level, open_cases=triage_counts[level])
            for level in TriageLevel
        ],
        unclassified_cases=unclassified,
        generated_at=now,
    )


def _category_utilisation(
    items: list[InventoryItem],
    categories: tuple[InventoryCategory, ...],
) -> float | None:
    """Return the in-use fraction across one or more categories, or ``None``."""
    in_scope = [item for item in items if item.category in categories]
    total = sum(item.total_stock for item in in_scope)
    available = sum(item.available_stock for item in in_scope)
    return safe_ratio(total - available, total)


# --------------------------------------------------------------------------- #
# Module 2 -- Outbreak anomaly detection
# --------------------------------------------------------------------------- #
def summarise_outbreaks(
    *,
    zones: list[Zone],
    hospitals: list[Hospital],
    cases: list[PatientCase],
    case_types: list[CaseType],
    window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
    threshold: float = DEFAULT_OUTBREAK_THRESHOLD,
    now: datetime,
) -> OutbreakDetectionResponse:
    """Flag zone-and-disease pairs whose incidence has broken from its baseline.

    Only notifiable case types participate; the ministry monitors those for
    clustering by definition, and running the test across every condition would
    bury a cholera signal under seasonal orthopaedics.

    Counts are converted to incidence per 100 000 before comparison so that a
    dense zone does not permanently look like an outbreak next to a sparse one.
    The z-score is taken against the trailing window excluding today, so today's
    observation is tested against history rather than against itself.
    """
    zone_by_code = {zone.zone_code: zone for zone in zones}
    zone_code_by_hospital: dict[PydanticObjectId, str] = {
        hospital_id: hospital.zone_code
        for hospital in hospitals
        if (hospital_id := hospital.id) is not None
    }
    notifiable = {
        case_type_id: case_type
        for case_type in case_types
        if case_type.is_notifiable and (case_type_id := _identity(case_type)) is not None
    }

    grouped: defaultdict[tuple[str, PydanticObjectId], list[datetime]] = defaultdict(list)
    for case in cases:
        if case.case_type_id is None or case.case_type_id not in notifiable:
            continue
        zone_code = zone_code_by_hospital.get(case.hospital_id)
        if zone_code is None:
            continue
        grouped[(zone_code, case.case_type_id)].append(case.admitted_at)

    signals: list[OutbreakSignalResponse] = []
    for (zone_code, case_type_id), admissions in sorted(
        grouped.items(), key=lambda entry: (entry[0][0], str(entry[0][1]))
    ):
        zone = zone_by_code.get(zone_code)
        if zone is None:
            continue
        case_type = notifiable[case_type_id]
        signals.append(
            _evaluate_outbreak_signal(
                zone=zone,
                case_type=case_type,
                case_type_id=case_type_id,
                admissions=admissions,
                window_days=window_days,
                threshold=threshold,
                now=now,
            )
        )

    return OutbreakDetectionResponse(
        signals=signals,
        anomaly_count=sum(1 for signal in signals if signal.is_anomaly),
        evaluated_count=len(signals),
        window_days=window_days,
        threshold=threshold,
        generated_at=now,
    )


def _evaluate_outbreak_signal(
    *,
    zone: Zone,
    case_type: CaseType,
    case_type_id: PydanticObjectId,
    admissions: list[datetime],
    window_days: int,
    threshold: float,
    now: datetime,
) -> OutbreakSignalResponse:
    """Score one zone-and-disease pair against its own trailing baseline."""
    series = bucket_by_day(admissions, days=window_days, now=now)
    observed_count = series[-1] if series else 0
    baseline_counts = series[:-1]
    population = zone.population_covered

    observed_rate = per_capita(observed_count, population)
    baseline_rates = [
        rate for count in baseline_counts if (rate := per_capita(count, population)) is not None
    ]
    baseline_mean = mean(baseline_rates)

    score: float | None = None
    confidence = SignalConfidence.INSUFFICIENT_DATA
    is_anomaly = False

    if observed_rate is not None and len(baseline_rates) >= MIN_BASELINE_OBSERVATIONS:
        score = z_score(observed_rate, baseline_rates)
        if score is not None:
            is_anomaly = score >= threshold
            confidence = (
                SignalConfidence.HIGH
                if len(baseline_rates) >= _HIGH_CONFIDENCE_BASELINE_DAYS
                else SignalConfidence.MODERATE
            )
        else:
            # A perfectly flat baseline has no spread to divide by. That is not
            # an error: a rare disease reporting the same figure every day is
            # normal. A sustained multiple of a non-zero flat line is still
            # worth surfacing, at reduced confidence and never as a z-score.
            confidence = SignalConfidence.LOW
            if (
                baseline_mean is not None
                and baseline_mean > 0
                and observed_rate > baseline_mean * _FLAT_BASELINE_SURGE_MULTIPLE
            ):
                is_anomaly = True

    return OutbreakSignalResponse(
        zone_code=zone.zone_code,
        zone_name=zone.name,
        state=zone.state,
        city=zone.city,
        case_type_id=case_type_id,
        case_type_name=case_type.name,
        icd10_code=case_type.icd10_code,
        population_covered=population,
        observed_cases=observed_count,
        observed_rate_per_100k=observed_rate,
        baseline_mean_rate_per_100k=baseline_mean,
        z_score=score,
        is_anomaly=is_anomaly,
        confidence=confidence,
        baseline_days=len(baseline_counts),
    )


# --------------------------------------------------------------------------- #
# Module 3 -- Surge forecasting
# --------------------------------------------------------------------------- #
def summarise_surge(
    *,
    cases: list[PatientCase],
    hospital_id: PydanticObjectId | None,
    history_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    horizon_days: int = DEFAULT_FORECAST_HORIZON_DAYS,
    now: datetime,
) -> SurgeForecastResponse:
    """Project daily admissions forward with a fitted level and trend.

    Every admission counts toward the series, discharged or not: the question is
    how many people arrive, not how many are still in a bed.
    """
    series = bucket_by_day((case.admitted_at for case in cases), days=history_days, now=now)
    fit = holt_linear_forecast([float(count) for count in series], horizon=horizon_days)

    if fit.trend > TREND_EPSILON:
        direction = TrendDirection.RISING
    elif fit.trend < -TREND_EPSILON:
        direction = TrendDirection.FALLING
    else:
        direction = TrendDirection.STABLE

    # The series is padded to the full window, so its length says nothing about
    # how much history exists. Days that actually saw an admission do.
    non_empty_days = sum(1 for count in series if count > 0)
    if not fit.has_trend_fit or non_empty_days < MIN_OBSERVATIONS_FOR_TREND:
        confidence = SignalConfidence.INSUFFICIENT_DATA
    elif fit.residual_std_error is None:
        confidence = SignalConfidence.LOW
    elif non_empty_days >= _HIGH_CONFIDENCE_OBSERVATIONS:
        confidence = SignalConfidence.HIGH
    else:
        confidence = SignalConfidence.MODERATE

    today = now.date()
    points = [
        ForecastPointResponse(
            horizon_day=point.horizon_day,
            forecast_date=today + timedelta(days=point.horizon_day),
            predicted_admissions=point.predicted,
            lower_bound=point.lower_bound,
            upper_bound=point.upper_bound,
        )
        for point in fit.points
    ]

    return SurgeForecastResponse(
        hospital_id=hospital_id,
        history=series,
        history_window_days=history_days,
        observations=fit.observations,
        points=points,
        horizon_days=horizon_days,
        trend_direction=direction,
        trend_per_day=fit.trend,
        confidence=confidence,
        projected_7_day_total=sum(
            point.predicted_admissions for point in points if point.horizon_day <= 7
        ),
        projected_14_day_total=sum(
            point.predicted_admissions for point in points if point.horizon_day <= 14
        ),
        generated_at=now,
    )


# --------------------------------------------------------------------------- #
# Module 4 -- Workforce reallocation
# --------------------------------------------------------------------------- #
def summarise_workforce(
    *,
    doctors: list[Doctor],
    staff: list[Staff],
    cases: list[PatientCase],
    hospital_id: PydanticObjectId | None,
    include_names: bool,
    now: datetime,
) -> WorkforceReallocationResponse:
    """Measure per-doctor strain and propose moves from slack to pressure.

    ``include_names`` is how the national view stays free of personal data: the
    ministry sees department-level strain, the hospital sees who to move.
    """
    load_by_doctor = Counter(case.doctor_id for case in cases if _is_open(case))

    loads: list[DoctorLoadResponse] = []
    for doctor in doctors:
        doctor_id = _identity(doctor)
        if doctor_id is None:
            continue
        active_load = load_by_doctor[doctor_id]
        ceiling = doctor.max_daily_patients
        index = safe_ratio(active_load, ceiling)
        loads.append(
            DoctorLoadResponse(
                doctor_id=doctor_id,
                full_name=doctor.full_name,
                specialization=doctor.specialization,
                department_id=doctor.department_id,
                is_available=doctor.status is StaffStatus.ACTIVE,
                active_load=active_load,
                max_daily_patients=ceiling,
                burnout_index=index,
                is_overloaded=index is not None and index >= OVERLOAD_BURNOUT_INDEX,
            )
        )

    available = [load for load in loads if load.is_available]
    indices = [load.burnout_index for load in loads if load.burnout_index is not None]

    departments = _department_loads(loads)
    return WorkforceReallocationResponse(
        hospital_id=hospital_id,
        has_capacity_data=bool(loads),
        doctor_count=len(loads),
        active_doctor_count=len(available),
        total_active_load=sum(load.active_load for load in loads),
        total_daily_capacity=sum(load.max_daily_patients for load in available),
        mean_burnout_index=mean(indices),
        overloaded_doctor_count=sum(1 for load in loads if load.is_overloaded),
        doctors=loads if include_names else [],
        departments=departments,
        shift_balance=_shift_balance(doctors, staff),
        suggestions=_reallocation_suggestions(departments),
        generated_at=now,
    )


def _department_loads(loads: list[DoctorLoadResponse]) -> list[DepartmentLoadResponse]:
    """Aggregate per-doctor load to department level, carrying no names."""
    grouped: defaultdict[PydanticObjectId, list[DoctorLoadResponse]] = defaultdict(list)
    for load in loads:
        grouped[load.department_id].append(load)

    return [
        DepartmentLoadResponse(
            department_id=department_id,
            doctor_count=len(members),
            active_load=sum(member.active_load for member in members),
            daily_capacity=sum(member.max_daily_patients for member in members),
            burnout_index=safe_ratio(
                sum(member.active_load for member in members),
                sum(member.max_daily_patients for member in members),
            ),
        )
        for department_id, members in sorted(grouped.items(), key=lambda entry: str(entry[0]))
    ]


def _shift_balance(doctors: list[Doctor], staff: list[Staff]) -> list[ShiftBalanceResponse]:
    """Count who covers each shift.

    A doctor declares a list of shifts and can appear under several; support and
    medical staff hold exactly one each.
    """
    return [
        ShiftBalanceResponse(
            shift=shift,
            doctor_count=sum(1 for doctor in doctors if shift in doctor.shifts),
            medical_staff_count=sum(
                1
                for member in staff
                if member.shift is shift and member.staff_category is StaffCategory.MEDICAL
            ),
            support_staff_count=sum(
                1
                for member in staff
                if member.shift is shift and member.staff_category is StaffCategory.ADMIN_SUPPORT
            ),
        )
        for shift in ShiftType
    ]


def _reallocation_suggestions(
    departments: list[DepartmentLoadResponse],
) -> list[ReallocationSuggestionResponse]:
    """Pair each department under strain with the one carrying the most slack."""
    strained = [
        department
        for department in departments
        if department.burnout_index is not None
        and department.burnout_index >= OVERLOAD_BURNOUT_INDEX
    ]
    slack = sorted(
        (
            department
            for department in departments
            if department.burnout_index is not None
            and department.burnout_index <= SLACK_BURNOUT_INDEX
        ),
        key=lambda department: department.burnout_index or 0.0,
    )
    if not slack:
        return []

    suggestions: list[ReallocationSuggestionResponse] = []
    for target in strained:
        source = slack[0]
        if source.department_id == target.department_id:
            continue
        source_index = source.burnout_index or 0.0
        target_index = target.burnout_index or 0.0
        suggestions.append(
            ReallocationSuggestionResponse(
                from_department_id=source.department_id,
                to_department_id=target.department_id,
                from_burnout_index=source_index,
                to_burnout_index=target_index,
                reason=(
                    f"department is at {target_index:.0%} of its daily capacity while "
                    f"another is at {source_index:.0%}; moving cover evens the load"
                ),
            )
        )
    return suggestions


# --------------------------------------------------------------------------- #
# Module 5 -- Resource prediction
# --------------------------------------------------------------------------- #
def summarise_resources(
    *,
    items: list[InventoryItem],
    cases: list[PatientCase],
    window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
    now: datetime,
) -> ResourcePredictionResponse:
    """Estimate a daily burn rate per category and count down to stockout.

    Consumption is inferred from case activity because the platform keeps
    current stock levels and no movement ledger. Admissions drive general beds,
    medicines and consumables; critical-care cases drive ICU beds, ventilators
    and oxygen. Every projection carries its
    :class:`~src.domain.enums.EstimationBasis` so the estimate is never mistaken
    for a measurement.
    """
    effective_window = max(window_days, 1)
    admissions = bucket_by_day((case.admitted_at for case in cases), days=effective_window, now=now)
    critical = bucket_by_day(
        (case.admitted_at for case in cases if case.status is CaseStatus.ICU),
        days=effective_window,
        now=now,
    )
    admissions_per_day = sum(admissions) / effective_window
    critical_per_day = sum(critical) / effective_window

    basis = (
        EstimationBasis.ESTIMATED_FROM_CASE_DEMAND
        if sum(admissions) > 0
        else EstimationBasis.INSUFFICIENT_HISTORY
    )

    grouped: defaultdict[tuple[PydanticObjectId, InventoryCategory], list[InventoryItem]] = (
        defaultdict(list)
    )
    for item in items:
        grouped[(item.hospital_id, item.category)].append(item)

    projections = [
        _project_category(
            hospital_id=hospital_id,
            category=category,
            lines=lines,
            admissions_per_day=admissions_per_day,
            critical_per_day=critical_per_day,
            basis=basis,
            window_days=effective_window,
            now=now,
        )
        for (hospital_id, category), lines in sorted(
            grouped.items(), key=lambda entry: (str(entry[0][0]), entry[0][1].value)
        )
    ]

    return ResourcePredictionResponse(
        projections=projections,
        at_risk_count=sum(
            1
            for projection in projections
            if projection.days_to_stockout is not None
            and projection.days_to_stockout <= AT_RISK_STOCKOUT_DAYS
        ),
        window_days=effective_window,
        basis=basis,
        generated_at=now,
    )


def _project_category(
    *,
    hospital_id: PydanticObjectId,
    category: InventoryCategory,
    lines: list[InventoryItem],
    admissions_per_day: float,
    critical_per_day: float,
    basis: EstimationBasis,
    window_days: int,
    now: datetime,
) -> ResourceProjectionResponse:
    """Build one category's stockout projection from its stock lines."""
    total = sum(line.total_stock for line in lines)
    available = sum(line.available_stock for line in lines)
    threshold = sum(line.min_safety_threshold for line in lines)

    driver = critical_per_day if category in _ICU_DRIVEN_CATEGORIES else admissions_per_day
    burn = driver * UNITS_CONSUMED_PER_CASE[category]
    remaining = days_to_stockout(available, burn)

    stockout_on: date | None = None
    if remaining is not None:
        stockout_on = now.date() + timedelta(days=min(int(remaining), MAX_PROJECTION_DAYS))

    unit: InventoryUnit | None = lines[0].unit if lines else None
    return ResourceProjectionResponse(
        hospital_id=hospital_id,
        category=category,
        line_count=len(lines),
        total_stock=total,
        available_stock=available,
        min_safety_threshold=threshold,
        unit=unit,
        daily_burn_rate=burn,
        days_to_stockout=remaining,
        projected_stockout_on=stockout_on,
        is_below_threshold=bool(lines) and available <= threshold,
        basis=basis,
        window_days=window_days,
    )


# --------------------------------------------------------------------------- #
# Module 6 -- 4-tier Smart Alerts
# --------------------------------------------------------------------------- #
def synthesise_alerts(
    *,
    realtime: RealtimeMonitoringResponse,
    outbreaks: OutbreakDetectionResponse,
    workforce: WorkforceReallocationResponse,
    resources: ResourcePredictionResponse,
    hospital_id: PydanticObjectId | None,
    now: datetime,
) -> SmartAlertsResponse:
    """Fold the other modules' outputs into one ranked action list.

    This reads the already-computed module responses rather than re-querying, so
    an alert can never disagree with the panel a reader is looking at. Alerts are
    returned most severe first.
    """
    alerts: list[SmartAlertResponse] = []
    alerts.extend(_occupancy_alerts(realtime, hospital_id))
    alerts.extend(_outbreak_alerts(outbreaks, hospital_id))
    alerts.extend(_workforce_alerts(workforce, hospital_id))
    alerts.extend(_resource_alerts(resources))

    alerts.sort(key=lambda alert: (_TIER_ORDER[alert.tier], alert.kind.value, alert.title))
    tiers = Counter(alert.tier for alert in alerts)

    return SmartAlertsResponse(
        alerts=alerts,
        critical_count=tiers[AlertTier.CRITICAL],
        high_count=tiers[AlertTier.HIGH],
        medium_count=tiers[AlertTier.MEDIUM],
        info_count=tiers[AlertTier.INFO],
        generated_at=now,
    )


def _occupancy_alerts(
    realtime: RealtimeMonitoringResponse,
    hospital_id: PydanticObjectId | None,
) -> list[SmartAlertResponse]:
    """Raise bed and ICU pressure alerts from live occupancy."""
    alerts: list[SmartAlertResponse] = []

    icu = realtime.icu_occupancy_ratio
    if icu is not None and icu >= CRITICAL_ICU_OCCUPANCY:
        alerts.append(
            SmartAlertResponse(
                tier=AlertTier.CRITICAL,
                kind=AlertKind.ICU_CAPACITY,
                hospital_id=hospital_id,
                title="ICU capacity effectively exhausted",
                detail=(
                    f"{realtime.icu_cases} critical cases against {realtime.icu_beds} "
                    f"ICU beds, {icu:.0%} occupied"
                ),
                metric_value=icu,
                threshold_value=CRITICAL_ICU_OCCUPANCY,
                recommended_action=(
                    "Divert critical admissions and escalate to the zone nodal officer"
                ),
            )
        )

    beds = realtime.bed_occupancy_ratio
    if beds is not None and beds >= HIGH_BED_OCCUPANCY:
        alerts.append(
            SmartAlertResponse(
                tier=AlertTier.HIGH,
                kind=AlertKind.BED_CAPACITY,
                hospital_id=hospital_id,
                title="Bed occupancy above safe headroom",
                detail=(
                    f"{realtime.open_cases} open cases against "
                    f"{realtime.total_sanctioned_beds} sanctioned beds, {beds:.0%} occupied"
                ),
                metric_value=beds,
                threshold_value=HIGH_BED_OCCUPANCY,
                recommended_action="Review discharge-ready cases and open contingency beds",
            )
        )
    elif beds is not None and beds >= MEDIUM_OCCUPANCY:
        alerts.append(
            SmartAlertResponse(
                tier=AlertTier.MEDIUM,
                kind=AlertKind.BED_CAPACITY,
                hospital_id=hospital_id,
                title="Bed occupancy climbing",
                detail=f"{beds:.0%} of sanctioned beds are occupied",
                metric_value=beds,
                threshold_value=MEDIUM_OCCUPANCY,
                recommended_action="Monitor admissions and prepare discharge planning",
            )
        )

    return alerts


def _outbreak_alerts(
    outbreaks: OutbreakDetectionResponse,
    hospital_id: PydanticObjectId | None,
) -> list[SmartAlertResponse]:
    """Raise one alert per flagged outbreak signal."""
    alerts: list[SmartAlertResponse] = []
    for signal in outbreaks.signals:
        if not signal.is_anomaly:
            continue
        score = signal.z_score
        if score is not None and score >= CRITICAL_Z_SCORE:
            tier = AlertTier.CRITICAL
            threshold = CRITICAL_Z_SCORE
        elif score is not None and score >= HIGH_Z_SCORE:
            tier = AlertTier.HIGH
            threshold = HIGH_Z_SCORE
        else:
            tier = AlertTier.MEDIUM
            threshold = None

        measured = "no z-score, flat baseline" if score is None else f"z = {score:.1f}"
        alerts.append(
            SmartAlertResponse(
                tier=tier,
                kind=AlertKind.OUTBREAK_ANOMALY,
                hospital_id=hospital_id,
                title=f"{signal.case_type_name} clustering in {signal.zone_name}",
                detail=(
                    f"{signal.observed_cases} cases today in {signal.zone_code} "
                    f"({signal.city}), {measured} against a {signal.baseline_days}-day baseline"
                ),
                metric_value=score,
                threshold_value=threshold,
                recommended_action=(
                    "Notify the district surveillance officer and verify case reports"
                ),
            )
        )
    return alerts


def _workforce_alerts(
    workforce: WorkforceReallocationResponse,
    hospital_id: PydanticObjectId | None,
) -> list[SmartAlertResponse]:
    """Raise strain alerts from the burnout distribution.

    Reads department-level figures only, so this behaves identically on the
    national view where no doctor is named.
    """
    alerts: list[SmartAlertResponse] = []
    if not workforce.has_capacity_data:
        return alerts

    peak = max(
        (
            department.burnout_index
            for department in workforce.departments
            if department.burnout_index is not None
        ),
        default=None,
    )
    if peak is None:
        return alerts

    if peak >= HIGH_BURNOUT_INDEX:
        tier, threshold = AlertTier.HIGH, HIGH_BURNOUT_INDEX
        action = "Reallocate cover from a department with slack before the next shift"
    elif peak >= OVERLOAD_BURNOUT_INDEX:
        tier, threshold = AlertTier.MEDIUM, OVERLOAD_BURNOUT_INDEX
        action = "Review the on-call roster and rebalance the coming shift"
    else:
        return alerts

    alerts.append(
        SmartAlertResponse(
            tier=tier,
            kind=AlertKind.WORKFORCE_OVERLOAD,
            hospital_id=hospital_id,
            title="Clinical workload above declared capacity",
            detail=(
                f"{workforce.overloaded_doctor_count} of {workforce.doctor_count} doctors are "
                f"at or over their daily ceiling; the busiest department is at {peak:.0%}"
            ),
            metric_value=peak,
            threshold_value=threshold,
            recommended_action=action,
        )
    )
    return alerts


def _resource_alerts(resources: ResourcePredictionResponse) -> list[SmartAlertResponse]:
    """Raise depletion alerts, most urgent stock first."""
    alerts: list[SmartAlertResponse] = []
    for projection in resources.projections:
        remaining = projection.days_to_stockout
        if remaining is None:
            continue

        if remaining <= CRITICAL_STOCKOUT_DAYS and projection.is_below_threshold:
            tier, threshold = AlertTier.CRITICAL, CRITICAL_STOCKOUT_DAYS
            action = "Raise an emergency requisition now; stock is below its safety threshold"
        elif remaining <= HIGH_STOCKOUT_DAYS:
            tier, threshold = AlertTier.HIGH, HIGH_STOCKOUT_DAYS
            action = "Place a restocking order this week"
        elif remaining <= MEDIUM_STOCKOUT_DAYS:
            tier, threshold = AlertTier.MEDIUM, MEDIUM_STOCKOUT_DAYS
            action = "Schedule replenishment in the next procurement cycle"
        else:
            continue

        alerts.append(
            SmartAlertResponse(
                tier=tier,
                kind=AlertKind.STOCK_DEPLETION,
                hospital_id=projection.hospital_id,
                title=f"{projection.category.value.replace('_', ' ').title()} nearing stockout",
                detail=(
                    f"{projection.available_stock:g} available against an estimated "
                    f"{projection.daily_burn_rate:.1f} per day, about "
                    f"{remaining:.1f} days remaining"
                ),
                metric_value=remaining,
                threshold_value=threshold,
                recommended_action=action,
            )
        )
    return alerts


# --------------------------------------------------------------------------- #
# Module 7 -- Policy impact tracking
# --------------------------------------------------------------------------- #
def summarise_policy_impact(
    *,
    complaints: list[Complaint],
    hospital_id: PydanticObjectId | None,
    now: datetime,
) -> PolicyImpactResponse:
    """Measure grievance volume, enforcement mix, speed, and whether it worked.

    Resolution times are nullable rather than zero-defaulted: a ministry that
    has closed nothing has no mean resolution time, and zero days would read as
    instant resolution.
    """
    by_category: Counter[ComplaintCategory] = Counter()
    by_status: Counter[InvestigationStatus] = Counter()
    by_action: Counter[ActionTaken] = Counter()
    resolution_days: list[float] = []
    closed = 0

    for complaint in complaints:
        by_category[complaint.category] += 1
        by_status[complaint.investigation_status] += 1
        if complaint.action_taken is not None:
            by_action[complaint.action_taken] += 1
        if complaint.investigation_status in CLOSED_INVESTIGATION_STATUSES:
            closed += 1
            if complaint.closed_at is not None:
                resolution_days.append(_elapsed_days(complaint.created_at, complaint.closed_at))

    enforced = sum(
        count for action, count in by_action.items() if action is not ActionTaken.DISMISSED
    )
    recidivism = _recidivism(complaints)

    return PolicyImpactResponse(
        hospital_id=hospital_id,
        total_complaints=len(complaints),
        closed_complaints=closed,
        open_complaints=len(complaints) - closed,
        by_category=[
            CategoryCountResponse(category=category, count=by_category[category])
            for category in ComplaintCategory
        ],
        by_status=[
            StatusCountResponse(status=status, count=by_status[status])
            for status in InvestigationStatus
        ],
        by_action=[
            ActionCountResponse(action=action, count=by_action[action]) for action in ActionTaken
        ],
        mean_resolution_days=mean(resolution_days),
        median_resolution_days=median(resolution_days),
        enforcement_rate=safe_ratio(enforced, closed),
        repeat_offender_count=len({entry.hospital_id for entry in recidivism}),
        recidivism=recidivism,
        generated_at=now,
    )


def _elapsed_days(opened: datetime, closed: datetime) -> float:
    """Return days between two timestamps, never negative."""
    elapsed = (_aware(closed) - _aware(opened)).total_seconds() / 86_400.0
    return max(elapsed, 0.0)


def _recidivism(complaints: list[Complaint]) -> list[RecidivismEntryResponse]:
    """Find hospitals that drew the same complaint again after enforcement.

    An action followed by more of the same grievance is the clearest signal the
    platform holds that the action did not change behaviour.
    """
    grouped: defaultdict[tuple[PydanticObjectId, ComplaintCategory], list[Complaint]] = defaultdict(
        list
    )
    for complaint in complaints:
        grouped[(complaint.hospital_id, complaint.category)].append(complaint)

    entries: list[RecidivismEntryResponse] = []
    for (hospital_id, category), filed in sorted(
        grouped.items(), key=lambda entry: (str(entry[0][0]), entry[0][1].value)
    ):
        enforced = [
            complaint
            for complaint in filed
            if complaint.action_taken is not None
            and complaint.action_taken is not ActionTaken.DISMISSED
            and complaint.closed_at is not None
        ]
        if not enforced:
            continue

        first = min(enforced, key=lambda complaint: _closed_at(complaint))
        marker = _closed_at(first)
        after = sum(
            1 for complaint in filed if _incident_of(complaint) > marker and complaint is not first
        )
        if after == 0:
            continue

        entries.append(
            RecidivismEntryResponse(
                hospital_id=hospital_id,
                category=category,
                action_taken=first.action_taken or ActionTaken.WARNING,
                complaints_before_action=len(filed) - after,
                complaints_after_action=after,
            )
        )
    return entries


def _closed_at(complaint: Complaint) -> datetime:
    """Return a complaint's closure instant, normalised to be comparable."""
    return _aware(complaint.closed_at or complaint.created_at)


def _incident_of(complaint: Complaint) -> datetime:
    """Return when a complaint was filed, normalised to be comparable."""
    return _aware(complaint.created_at)
