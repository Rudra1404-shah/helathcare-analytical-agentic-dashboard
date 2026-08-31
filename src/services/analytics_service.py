"""The 7-module AI analytical intelligence engine.

``PROJECT_SPEC.md`` §1 records that every model in Phases 1 to 3 was shaped by
what this engine would need to read: ``zones`` is a first-class collection so
outbreak detection has a per-capita denominator, vitals are a list so
deterioration is visible as a trend, and timestamps are mandatory everywhere.
This module is the payoff. It reads across the existing twelve collections and
adds none of its own.

**Shape.** Each module is a pair. A pure reducer in
:mod:`src.services.analytics_reducers` turns fetched documents into a response;
the ``async`` function here resolves tenancy, fetches, audits, and delegates to
it. The split exists because `CLAUDE.md` requires unit tests to run without
MongoDB, and in an analytics engine the arithmetic is what is worth testing
exhaustively. Every reducer is re-exported here, so callers import this module
and nothing else.

**Tenancy.** :func:`resolve_analytics_scope` runs first in every entry point,
including the ones a router already guards. That duplication is deliberate and
`CLAUDE.md` requires it: a seed script or a scheduled job that bypasses the
router must still be unable to read across hospitals.

**Aggregation happens in Python, not in MongoDB.** No service in this codebase
uses ``.aggregate()``; the convention is ``.find(...).to_list()`` followed by a
reduction, as :func:`src.services.inventory_service.capacity_summary` does. The
analytics reducers keep that convention, which is also what makes them testable
without a server.
"""

from datetime import datetime, timedelta

from beanie import PydanticObjectId

from src.core.audit import AuditAction, audit_event
from src.core.errors import PermissionDeniedError
from src.domain.enums import (
    CLOSED_INVESTIGATION_STATUSES,
    TERMINAL_CASE_STATUSES,
    UserRole,
)
from src.domain.models import (
    CaseType,
    Complaint,
    Doctor,
    Hospital,
    InventoryItem,
    PatientCase,
    Staff,
    User,
    Zone,
)
from src.domain.models.base import utcnow
from src.domain.schemas.analytics import (
    NationalOverviewResponse,
    OutbreakDetectionResponse,
    PolicyImpactResponse,
    RealtimeMonitoringResponse,
    ResourcePredictionResponse,
    SmartAlertsResponse,
    SurgeForecastResponse,
    WorkforceReallocationResponse,
)
from src.services.analytics_reducers import (
    DEFAULT_BASELINE_WINDOW_DAYS,
    DEFAULT_FORECAST_HORIZON_DAYS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_OUTBREAK_THRESHOLD,
    summarise_outbreaks,
    summarise_policy_impact,
    summarise_realtime,
    summarise_resources,
    summarise_surge,
    summarise_workforce,
    synthesise_alerts,
)
from src.services.common import ensure_hospital_match, hospital_scope_of

__all__ = [
    "national_overview",
    "outbreak_signals",
    "policy_impact",
    "realtime_monitoring",
    "resolve_analytics_scope",
    "resource_prediction",
    "smart_alerts",
    "summarise_outbreaks",
    "summarise_policy_impact",
    "summarise_realtime",
    "summarise_resources",
    "summarise_surge",
    "summarise_workforce",
    "surge_forecast",
    "synthesise_alerts",
    "workforce_reallocation",
]

_COLLECTION = "analytics"
"""Audit label. Analytics spans several collections, so the detail names the module."""


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
def resolve_analytics_scope(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> PydanticObjectId | None:
    """Return the hospital an analytics read is confined to, or ``None`` nationally.

    :func:`~src.services.common.hospital_scope_of` returns ``None`` for a
    citizen as well as for a ministry official, because a citizen is filtered by
    their own identity rather than by tenancy. That is right for the PHR and
    wrong here: the ministry-wide sweep idiom used elsewhere treats ``None`` as
    "every hospital", so reusing it unmodified would hand national intelligence
    to any citizen account. Analytics is staff-only, and this is the check that
    makes it so.

    A hospital-scoped actor naming another hospital is refused rather than
    quietly redirected to their own data. Silent redirection would turn a
    deliberate probe into a successful-looking request and leave no trace of the
    attempt.

    Args:
        hospital_id: Requested hospital, or ``None`` to ask for the national view.
        actor: The account making the request.

    Returns:
        The hospital to confine every query to, or ``None`` for a ministry sweep.

    Raises:
        PermissionDeniedError: If the actor is a citizen, or is scoped to a
            different hospital than the one requested.
    """
    if actor.role is UserRole.CITIZEN:
        msg = (
            "analytical intelligence is limited to ministry and hospital staff; "
            "a citizen account can read its own health record instead"
        )
        raise PermissionDeniedError(msg)

    scope = hospital_scope_of(actor)
    if scope is None:
        # Ministry account, citizens having been excluded above.
        return hospital_id
    if hospital_id is not None and hospital_id != scope:
        ensure_hospital_match(hospital_id, scope, "analytics view")
    return scope


def _scoped(scope: PydanticObjectId | None) -> dict[str, object]:
    """Build the hospital filter clause, empty for a national sweep."""
    return {} if scope is None else {"hospital_id": scope}


def _audit(
    actor: User,
    scope: PydanticObjectId | None,
    module: str,
) -> None:
    """Record that an analytics module was read.

    `CLAUDE.md` requires an audit event on every clinical read. These are
    aggregate views rather than single records, so no ``document_id`` is
    attached; the module name and the scope are what an investigator needs.
    """
    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        hospital_id=scope,
        detail=f"{module} ({'national' if scope is None else 'hospital'} scope)",
    )


# --------------------------------------------------------------------------- #
# Fetch helpers
# --------------------------------------------------------------------------- #
async def _load_hospitals(scope: PydanticObjectId | None) -> list[Hospital]:
    """Return the hospitals in scope, active ones only for a national sweep."""
    if scope is None:
        return await Hospital.find({"is_active": True}).to_list()
    hospital = await Hospital.get(scope)
    return [] if hospital is None else [hospital]


async def _load_case_types(scope: PydanticObjectId | None) -> list[CaseType]:
    """Return case types visible to the scope.

    ``CaseType.hospital_id`` is nullable: ``None`` marks a national standard
    definition shared by every hospital, so a scoped read must include those as
    well as its own.
    """
    if scope is None:
        return await CaseType.find({"is_active": True}).to_list()
    return await CaseType.find(
        {"is_active": True, "$or": [{"hospital_id": scope}, {"hospital_id": None}]}
    ).to_list()


async def _load_open_cases(scope: PydanticObjectId | None) -> list[PatientCase]:
    """Return every case still occupying capacity."""
    query: dict[str, object] = {"status": {"$nin": list(TERMINAL_CASE_STATUSES)}}
    query.update(_scoped(scope))
    return await PatientCase.find(query).to_list()


async def _load_recent_cases(
    scope: PydanticObjectId | None,
    window_days: int,
    now: datetime,
) -> list[PatientCase]:
    """Return cases admitted inside the window.

    Bounded by time rather than by page size: a national sweep over every
    admission ever recorded would grow without limit, and nothing outside the
    window contributes to a baseline or a burn rate anyway.
    """
    cutoff = now - timedelta(days=window_days)
    query: dict[str, object] = {"admitted_at": {"$gte": cutoff}}
    query.update(_scoped(scope))
    return await PatientCase.find(query).to_list()


async def _load_inventory(scope: PydanticObjectId | None) -> list[InventoryItem]:
    """Return active stock lines in scope."""
    query: dict[str, object] = {"is_active": True}
    query.update(_scoped(scope))
    return await InventoryItem.find(query).to_list()


# --------------------------------------------------------------------------- #
# Module gathering -- fetch and reduce, without tenancy or audit
#
# Split out so :func:`smart_alerts` can compose four modules while emitting one
# audit event, instead of five for a single request.
# --------------------------------------------------------------------------- #
async def _gather_realtime(
    scope: PydanticObjectId | None,
    now: datetime,
) -> RealtimeMonitoringResponse:
    """Fetch and reduce the real-time monitoring module."""
    return summarise_realtime(
        hospitals=await _load_hospitals(scope),
        cases=await _load_open_cases(scope),
        items=await _load_inventory(scope),
        case_types=await _load_case_types(scope),
        hospital_id=scope,
        now=now,
    )


async def _gather_outbreaks(
    scope: PydanticObjectId | None,
    window_days: int,
    threshold: float,
    now: datetime,
) -> OutbreakDetectionResponse:
    """Fetch and reduce the outbreak detection module."""
    return summarise_outbreaks(
        zones=await Zone.find({"is_active": True}).to_list(),
        hospitals=await _load_hospitals(scope),
        cases=await _load_recent_cases(scope, window_days, now),
        case_types=await _load_case_types(scope),
        window_days=window_days,
        threshold=threshold,
        now=now,
    )


async def _gather_surge(
    scope: PydanticObjectId | None,
    history_days: int,
    horizon_days: int,
    now: datetime,
) -> SurgeForecastResponse:
    """Fetch and reduce the surge forecasting module."""
    return summarise_surge(
        cases=await _load_recent_cases(scope, history_days, now),
        hospital_id=scope,
        history_days=history_days,
        horizon_days=horizon_days,
        now=now,
    )


async def _gather_workforce(
    scope: PydanticObjectId | None,
    now: datetime,
) -> WorkforceReallocationResponse:
    """Fetch and reduce the workforce module.

    Names are included only for a hospital-scoped read. The national view
    aggregates to department level and carries no personal data.
    """
    return summarise_workforce(
        doctors=await Doctor.find(_scoped(scope)).to_list(),
        staff=await Staff.find(_scoped(scope)).to_list(),
        cases=await _load_open_cases(scope),
        hospital_id=scope,
        include_names=scope is not None,
        now=now,
    )


async def _gather_resources(
    scope: PydanticObjectId | None,
    window_days: int,
    now: datetime,
) -> ResourcePredictionResponse:
    """Fetch and reduce the resource prediction module."""
    return summarise_resources(
        items=await _load_inventory(scope),
        cases=await _load_recent_cases(scope, window_days, now),
        window_days=window_days,
        now=now,
    )


async def _gather_policy_impact(
    scope: PydanticObjectId | None,
    now: datetime,
) -> PolicyImpactResponse:
    """Fetch and reduce the policy impact module."""
    return summarise_policy_impact(
        complaints=await Complaint.find(_scoped(scope)).to_list(),
        hospital_id=scope,
        now=now,
    )


# --------------------------------------------------------------------------- #
# Module 1 -- Real-time monitoring
# --------------------------------------------------------------------------- #
async def realtime_monitoring(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> RealtimeMonitoringResponse:
    """Return live bed and ICU occupancy with the triage mix behind it."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_realtime(scope, utcnow())
    _audit(actor, scope, "realtime monitoring")
    return result


# --------------------------------------------------------------------------- #
# Module 2 -- Outbreak anomaly detection
# --------------------------------------------------------------------------- #
async def outbreak_signals(
    hospital_id: PydanticObjectId | None,
    actor: User,
    *,
    window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
    threshold: float = DEFAULT_OUTBREAK_THRESHOLD,
) -> OutbreakDetectionResponse:
    """Return notifiable-disease clusters breaking from their zone baseline."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_outbreaks(scope, window_days, threshold, utcnow())
    _audit(actor, scope, "outbreak detection")
    return result


# --------------------------------------------------------------------------- #
# Module 3 -- Surge forecasting
# --------------------------------------------------------------------------- #
async def surge_forecast(
    hospital_id: PydanticObjectId | None,
    actor: User,
    *,
    history_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    horizon_days: int = DEFAULT_FORECAST_HORIZON_DAYS,
) -> SurgeForecastResponse:
    """Return a 7-to-14 day admissions projection with 95% intervals."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_surge(scope, history_days, horizon_days, utcnow())
    _audit(actor, scope, "surge forecast")
    return result


# --------------------------------------------------------------------------- #
# Module 4 -- Workforce reallocation
# --------------------------------------------------------------------------- #
async def workforce_reallocation(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> WorkforceReallocationResponse:
    """Return doctor burnout, shift cover, and suggested moves."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_workforce(scope, utcnow())
    _audit(actor, scope, "workforce reallocation")
    return result


# --------------------------------------------------------------------------- #
# Module 5 -- Resource prediction
# --------------------------------------------------------------------------- #
async def resource_prediction(
    hospital_id: PydanticObjectId | None,
    actor: User,
    *,
    window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
) -> ResourcePredictionResponse:
    """Return estimated burn rates and days-to-stockout per resource category."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_resources(scope, window_days, utcnow())
    _audit(actor, scope, "resource prediction")
    return result


# --------------------------------------------------------------------------- #
# Module 6 -- 4-tier Smart Alerts
# --------------------------------------------------------------------------- #
async def smart_alerts(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> SmartAlertsResponse:
    """Return the four-tier action list synthesised from the other modules.

    Composed from the same computed responses the individual panels return, so
    an alert can never contradict the panel a reader is looking at.
    """
    scope = resolve_analytics_scope(hospital_id, actor)
    now = utcnow()

    result = synthesise_alerts(
        realtime=await _gather_realtime(scope, now),
        outbreaks=await _gather_outbreaks(
            scope, DEFAULT_BASELINE_WINDOW_DAYS, DEFAULT_OUTBREAK_THRESHOLD, now
        ),
        workforce=await _gather_workforce(scope, now),
        resources=await _gather_resources(scope, DEFAULT_BASELINE_WINDOW_DAYS, now),
        hospital_id=scope,
        now=now,
    )
    _audit(actor, scope, "smart alerts")
    return result


# --------------------------------------------------------------------------- #
# Module 7 -- Policy impact tracking
# --------------------------------------------------------------------------- #
async def policy_impact(
    hospital_id: PydanticObjectId | None,
    actor: User,
) -> PolicyImpactResponse:
    """Return enforcement mix, resolution speed, and recidivism after action."""
    scope = resolve_analytics_scope(hospital_id, actor)
    result = await _gather_policy_impact(scope, utcnow())
    _audit(actor, scope, "policy impact")
    return result


# --------------------------------------------------------------------------- #
# National roll-up
# --------------------------------------------------------------------------- #
async def national_overview(actor: User) -> NationalOverviewResponse:
    """Return the summary strip at the top of the ministry's command centre.

    Ministry-only by construction: a hospital-scoped actor resolves to their own
    hospital and would receive a "national" view of one site, which would be
    misleading, so the role is checked explicitly here rather than only at the
    router.
    """
    scope = resolve_analytics_scope(None, actor)
    if scope is not None:
        msg = "the national overview is a ministry view; use the hospital analytics routes instead"
        raise PermissionDeniedError(msg)

    now = utcnow()
    realtime = await _gather_realtime(None, now)
    outbreaks = await _gather_outbreaks(
        None, DEFAULT_BASELINE_WINDOW_DAYS, DEFAULT_OUTBREAK_THRESHOLD, now
    )
    resources = await _gather_resources(None, DEFAULT_BASELINE_WINDOW_DAYS, now)
    workforce = await _gather_workforce(None, now)
    alerts = synthesise_alerts(
        realtime=realtime,
        outbreaks=outbreaks,
        workforce=workforce,
        resources=resources,
        hospital_id=None,
        now=now,
    )

    zones = await Zone.find({"is_active": True}).to_list()
    open_complaints = await Complaint.find(
        {"investigation_status": {"$nin": list(CLOSED_INVESTIGATION_STATUSES)}}
    ).count()

    _audit(actor, None, "national overview")
    return NationalOverviewResponse(
        hospital_count=realtime.hospital_count,
        zone_count=len(zones),
        population_covered=sum(zone.population_covered for zone in zones),
        open_cases=realtime.open_cases,
        total_sanctioned_beds=realtime.total_sanctioned_beds,
        bed_occupancy_ratio=realtime.bed_occupancy_ratio,
        icu_occupancy_ratio=realtime.icu_occupancy_ratio,
        critical_alert_count=alerts.critical_count,
        high_alert_count=alerts.high_count,
        outbreak_signal_count=outbreaks.anomaly_count,
        at_risk_resource_count=resources.at_risk_count,
        open_complaint_count=open_complaints,
        generated_at=now,
    )
