"""Analytical intelligence endpoints for the ministry and hospital portals.

Two parallel families of routes read the same seven modules at different scopes.
The ``/analytics/national/*`` family is ministry-only; the
``/hospitals/{hospital_id}/analytics/*`` family is confined to one hospital and
is open to any account entitled to work inside it, the ministry included, so a
national official can drill from a flagged zone into the site causing it.

Neither ``GovtAdmin`` nor ``HospitalActor`` admits a citizen. That is the outer
guard; :func:`src.services.analytics_service.resolve_analytics_scope` repeats
the check inside every service call, because a caller reaching the service by
another path must not be able to read across hospitals either.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from src.api.deps import GovtAdmin, HospitalActor, HospitalPath
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
from src.domain.schemas.common import ApiResponse
from src.services import analytics_service
from src.services.analytics_reducers import (
    DEFAULT_BASELINE_WINDOW_DAYS,
    DEFAULT_FORECAST_HORIZON_DAYS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_OUTBREAK_THRESHOLD,
)

router = APIRouter(tags=["analytics"])

MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 180
MAX_HORIZON_DAYS = 30

WindowDays = Annotated[
    int,
    Query(
        ge=MIN_WINDOW_DAYS,
        le=MAX_WINDOW_DAYS,
        description="Days of history to read as the baseline.",
    ),
]
HistoryDays = Annotated[
    int,
    Query(
        ge=MIN_WINDOW_DAYS,
        le=MAX_WINDOW_DAYS,
        description="Days of observed admissions to fit the forecast on.",
    ),
]
HorizonDays = Annotated[
    int,
    Query(ge=1, le=MAX_HORIZON_DAYS, description="Days to project forward."),
]
Threshold = Annotated[
    float,
    Query(ge=1.0, le=6.0, description="Z-score at which a cluster is flagged."),
]


# --------------------------------------------------------------------------- #
# National -- Health Ministry
# --------------------------------------------------------------------------- #
@router.get(
    "/analytics/national/overview",
    response_model=ApiResponse[NationalOverviewResponse],
)
async def national_overview(actor: GovtAdmin) -> ApiResponse[NationalOverviewResponse]:
    """Return the summary strip for the national command centre."""
    return ApiResponse.ok(await analytics_service.national_overview(actor))


@router.get(
    "/analytics/national/realtime",
    response_model=ApiResponse[RealtimeMonitoringResponse],
)
async def national_realtime(actor: GovtAdmin) -> ApiResponse[RealtimeMonitoringResponse]:
    """Return live occupancy and triage mix across every active hospital."""
    return ApiResponse.ok(await analytics_service.realtime_monitoring(None, actor))


@router.get(
    "/analytics/national/outbreaks",
    response_model=ApiResponse[OutbreakDetectionResponse],
)
async def national_outbreaks(
    actor: GovtAdmin,
    window_days: WindowDays = DEFAULT_BASELINE_WINDOW_DAYS,
    threshold: Threshold = DEFAULT_OUTBREAK_THRESHOLD,
) -> ApiResponse[OutbreakDetectionResponse]:
    """Return notifiable-disease clusters breaking from their zone baseline."""
    return ApiResponse.ok(
        await analytics_service.outbreak_signals(
            None, actor, window_days=window_days, threshold=threshold
        )
    )


@router.get(
    "/analytics/national/surge",
    response_model=ApiResponse[SurgeForecastResponse],
)
async def national_surge(
    actor: GovtAdmin,
    history_days: HistoryDays = DEFAULT_HISTORY_WINDOW_DAYS,
    horizon_days: HorizonDays = DEFAULT_FORECAST_HORIZON_DAYS,
) -> ApiResponse[SurgeForecastResponse]:
    """Return the national admissions projection with 95% intervals."""
    return ApiResponse.ok(
        await analytics_service.surge_forecast(
            None, actor, history_days=history_days, horizon_days=horizon_days
        )
    )


@router.get(
    "/analytics/national/workforce",
    response_model=ApiResponse[WorkforceReallocationResponse],
)
async def national_workforce(actor: GovtAdmin) -> ApiResponse[WorkforceReallocationResponse]:
    """Return workload strain aggregated to department level.

    Carries no doctor names: the ministry needs to know where the pressure is,
    not who is under it. Per-doctor detail is on the hospital route.
    """
    return ApiResponse.ok(await analytics_service.workforce_reallocation(None, actor))


@router.get(
    "/analytics/national/resources",
    response_model=ApiResponse[ResourcePredictionResponse],
)
async def national_resources(
    actor: GovtAdmin,
    window_days: WindowDays = DEFAULT_BASELINE_WINDOW_DAYS,
) -> ApiResponse[ResourcePredictionResponse]:
    """Return estimated burn rates and days-to-stockout for every hospital."""
    return ApiResponse.ok(
        await analytics_service.resource_prediction(None, actor, window_days=window_days)
    )


@router.get(
    "/analytics/national/alerts",
    response_model=ApiResponse[SmartAlertsResponse],
)
async def national_alerts(actor: GovtAdmin) -> ApiResponse[SmartAlertsResponse]:
    """Return the four-tier national action list, most severe first."""
    return ApiResponse.ok(await analytics_service.smart_alerts(None, actor))


@router.get(
    "/analytics/national/policy-impact",
    response_model=ApiResponse[PolicyImpactResponse],
)
async def national_policy_impact(actor: GovtAdmin) -> ApiResponse[PolicyImpactResponse]:
    """Return enforcement mix, resolution speed, and recidivism after action."""
    return ApiResponse.ok(await analytics_service.policy_impact(None, actor))


# --------------------------------------------------------------------------- #
# Hospital-scoped
# --------------------------------------------------------------------------- #
@router.get(
    "/hospitals/{hospital_id}/analytics/realtime",
    response_model=ApiResponse[RealtimeMonitoringResponse],
)
async def hospital_realtime(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[RealtimeMonitoringResponse]:
    """Return this hospital's live bed and ICU occupancy with its triage mix."""
    return ApiResponse.ok(await analytics_service.realtime_monitoring(hospital_id, actor))


@router.get(
    "/hospitals/{hospital_id}/analytics/outbreaks",
    response_model=ApiResponse[OutbreakDetectionResponse],
)
async def hospital_outbreaks(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    window_days: WindowDays = DEFAULT_BASELINE_WINDOW_DAYS,
    threshold: Threshold = DEFAULT_OUTBREAK_THRESHOLD,
) -> ApiResponse[OutbreakDetectionResponse]:
    """Return notifiable-disease clustering attributable to this hospital's zone."""
    return ApiResponse.ok(
        await analytics_service.outbreak_signals(
            hospital_id, actor, window_days=window_days, threshold=threshold
        )
    )


@router.get(
    "/hospitals/{hospital_id}/analytics/surge",
    response_model=ApiResponse[SurgeForecastResponse],
)
async def hospital_surge(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    history_days: HistoryDays = DEFAULT_HISTORY_WINDOW_DAYS,
    horizon_days: HorizonDays = DEFAULT_FORECAST_HORIZON_DAYS,
) -> ApiResponse[SurgeForecastResponse]:
    """Return this hospital's 7-to-14 day admissions projection."""
    return ApiResponse.ok(
        await analytics_service.surge_forecast(
            hospital_id, actor, history_days=history_days, horizon_days=horizon_days
        )
    )


@router.get(
    "/hospitals/{hospital_id}/analytics/workforce",
    response_model=ApiResponse[WorkforceReallocationResponse],
)
async def hospital_workforce(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[WorkforceReallocationResponse]:
    """Return per-doctor burnout, shift cover, and suggested reallocations."""
    return ApiResponse.ok(await analytics_service.workforce_reallocation(hospital_id, actor))


@router.get(
    "/hospitals/{hospital_id}/analytics/resources",
    response_model=ApiResponse[ResourcePredictionResponse],
)
async def hospital_resources(
    hospital_id: HospitalPath,
    actor: HospitalActor,
    window_days: WindowDays = DEFAULT_BASELINE_WINDOW_DAYS,
) -> ApiResponse[ResourcePredictionResponse]:
    """Return estimated burn rates and days-to-stockout for this hospital."""
    return ApiResponse.ok(
        await analytics_service.resource_prediction(hospital_id, actor, window_days=window_days)
    )


@router.get(
    "/hospitals/{hospital_id}/analytics/alerts",
    response_model=ApiResponse[SmartAlertsResponse],
)
async def hospital_alerts(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[SmartAlertsResponse]:
    """Return this hospital's four-tier action list, most severe first."""
    return ApiResponse.ok(await analytics_service.smart_alerts(hospital_id, actor))


@router.get(
    "/hospitals/{hospital_id}/analytics/policy-impact",
    response_model=ApiResponse[PolicyImpactResponse],
)
async def hospital_policy_impact(
    hospital_id: HospitalPath,
    actor: HospitalActor,
) -> ApiResponse[PolicyImpactResponse]:
    """Return complaints, enforcement, and resolution speed for this hospital."""
    return ApiResponse.ok(await analytics_service.policy_impact(hospital_id, actor))
