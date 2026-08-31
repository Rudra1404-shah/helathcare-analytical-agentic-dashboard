"""Statistical primitives for the analytical intelligence engine.

Deliberately free of domain imports: everything here takes numbers and returns
numbers. That is what lets the entire statistical surface be unit tested without
a database, a document, or a fixture, which matters because these are the
functions most likely to be wrong in a way no integration test would notice.

The platform ships no scientific dependency -- ``pyproject.toml`` lists neither
numpy nor scipy -- so this is stdlib ``math`` and ``statistics`` throughout. At
this scale that is a feature rather than a limitation: a national daily case
series is a few hundred points, and compiled wheels on every deployment target
would be a real cost for no gain.

**Every function here is total.** Analytics runs against whatever hospitals have
actually entered, so an empty series, a zero denominator, a zero population, and
a perfectly flat baseline are ordinary inputs rather than exceptional ones.
Nothing raises. Each function returns ``None`` or a documented neutral value, so
a caller can always tell "no signal available" apart from "a signal of zero" --
a distinction that decides whether a dashboard shows an empty state or a
reassuring green figure, and those must never be confused.
"""

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_BETA",
    "MIN_BASELINE_OBSERVATIONS",
    "MIN_OBSERVATIONS_FOR_TREND",
    "PER_100K",
    "Z_SCORE_95",
    "ForecastPoint",
    "ForecastResult",
    "bucket_by_day",
    "days_to_stockout",
    "holt_linear_forecast",
    "mean",
    "median",
    "per_capita",
    "safe_ratio",
    "stdev_sample",
    "z_score",
]

DEFAULT_ALPHA = 0.4
"""Level smoothing factor. Responsive enough to follow a real surge within days."""

DEFAULT_BETA = 0.2
"""Trend smoothing factor, below alpha on purpose so noise does not become a trend."""

Z_SCORE_95 = 1.959963984540054
"""Two-sided normal quantile for a 95% interval."""

MIN_OBSERVATIONS_FOR_TREND = 7
"""Below one week of history, a fitted trend says more about noise than about disease."""

MIN_BASELINE_OBSERVATIONS = 3
"""A mean and a standard deviation from fewer than three points are not a baseline."""

PER_100K = 100_000
"""The epidemiological convention for incidence normalisation."""


# --------------------------------------------------------------------------- #
# Ratios
# --------------------------------------------------------------------------- #
def safe_ratio(numerator: float, denominator: float) -> float | None:
    """Divide, returning ``None`` rather than raising when there is no denominator.

    ``None`` means "this ratio is undefined here", which is a different fact
    from ``0.0``. A hospital with no sanctioned ICU beds has undefined ICU
    occupancy; reporting it as 0% would render as a comfortably empty ward.
    """
    if denominator == 0:
        return None
    return numerator / denominator


def per_capita(count: int, population: int, per: int = PER_100K) -> float | None:
    """Normalise a raw count to cases per ``per`` head of population.

    Comparing raw counts across zones is meaningless when one zone holds ten
    times the people of another, which is exactly why ``zones`` carries
    ``population_covered`` as a first-class field.

    Returns:
        Incidence per ``per`` head, or ``None`` when the population is unknown
        or zero and no meaningful rate exists.
    """
    if population <= 0:
        return None
    return (count / population) * per


def days_to_stockout(available: float, daily_burn: float) -> float | None:
    """Return how many days of stock remain at the observed consumption rate.

    Returns:
        ``0.0`` when nothing is left, the remaining days when stock is being
        consumed, or ``None`` when no consumption has been observed. ``None``
        deliberately does not mean "forever": it means the burn rate is unknown,
        and a UI must render it as such rather than as a comfortable large
        number or an infinity.
    """
    if available <= 0:
        return 0.0
    if daily_burn <= 0:
        return None
    return available / daily_burn


# --------------------------------------------------------------------------- #
# Descriptive statistics
# --------------------------------------------------------------------------- #
def mean(values: Sequence[float]) -> float | None:
    """Return the arithmetic mean, or ``None`` for an empty sequence."""
    if not values:
        return None
    return statistics.fmean(values)


def median(values: Sequence[float]) -> float | None:
    """Return the median, or ``None`` for an empty sequence."""
    if not values:
        return None
    return statistics.median(values)


def stdev_sample(values: Sequence[float]) -> float | None:
    """Return the sample standard deviation, or ``None`` when it is undefined.

    Undefined below two observations. A flat series correctly returns ``0.0``,
    which callers must handle: it is the input that turns a z-score into a
    division by zero.
    """
    if len(values) < 2:
        return None
    return statistics.stdev(values)


def z_score(observed: float, baseline: Sequence[float]) -> float | None:
    """Return how many standard deviations ``observed`` sits above its baseline.

    Returns:
        The z-score, or ``None`` when the baseline cannot support one -- fewer
        than :data:`MIN_BASELINE_OBSERVATIONS` points, or a baseline with zero
        variance. A flat baseline is common in practice, a rare notifiable
        disease reporting zero every day for a month, and a single case the
        following day is not infinitely anomalous. The caller decides what a
        break from a flat line means rather than receiving ``inf``.
    """
    if len(baseline) < MIN_BASELINE_OBSERVATIONS:
        return None
    spread = stdev_sample(baseline)
    if spread is None or spread == 0:
        return None
    centre = statistics.fmean(baseline)
    return (observed - centre) / spread


# --------------------------------------------------------------------------- #
# Time series
# --------------------------------------------------------------------------- #
def _as_utc(moment: datetime) -> datetime:
    """Normalise a timestamp to UTC, treating a naive value as already UTC.

    Clients are configured ``tz_aware=True`` so stored timestamps come back
    aware, but a caller constructing a document in memory may not be, and
    comparing the two raises ``TypeError``.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def bucket_by_day(
    timestamps: Iterable[datetime],
    *,
    days: int,
    now: datetime,
) -> list[int]:
    """Count timestamps into one bucket per calendar day.

    Args:
        timestamps: Event times, in any order and any timezone.
        days: Window length. The result always has exactly this many buckets,
            including days on which nothing happened. A gap in a time series is
            data, and dropping empty days would silently compress the timeline
            and inflate every rate computed from it.
        now: The instant the window ends.

    Returns:
        Counts oldest-first, so the last element is today. Empty when ``days``
        is not positive.
    """
    if days <= 0:
        return []

    today = _as_utc(now).date()
    counts = [0] * days
    for moment in timestamps:
        offset = (today - _as_utc(moment).date()).days
        if 0 <= offset < days:
            counts[days - 1 - offset] += 1
    return counts


@dataclass(frozen=True)
class ForecastPoint:
    """One projected day, with the interval around it."""

    horizon_day: int
    predicted: float
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True)
class ForecastResult:
    """A fitted forecast plus the diagnostics a caller needs to judge it."""

    points: tuple[ForecastPoint, ...]
    level: float
    trend: float
    residual_std_error: float | None
    observations: int

    @property
    def has_trend_fit(self) -> bool:
        """Whether a real trend was fitted rather than a flat fallback."""
        return self.observations >= MIN_OBSERVATIONS_FOR_TREND


def holt_linear_forecast(
    series: Sequence[float],
    *,
    horizon: int,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> ForecastResult:
    """Project a series forward with Holt's linear trend method.

    Double exponential smoothing carries a level and a trend::

        level_t = alpha * y_t + (1 - alpha) * (level_prev + trend_prev)
        trend_t = beta * (level_t - level_prev) + (1 - beta) * trend_prev
        forecast(h) = level_t + h * trend_t

    Single smoothing was rejected: it produces a flat line, and a flat line
    cannot express a surge, which is the entire purpose of the module.

    The 95% interval comes from the in-sample one-step-ahead residual standard
    error, widened as ``sqrt(h)`` with the horizon because forecast uncertainty
    compounds. The central estimate and the lower bound are both clamped at
    zero: a negative admission count is not a forecast, it is an artefact of
    extrapolating a falling line past the axis.

    Below :data:`MIN_OBSERVATIONS_FOR_TREND` observations no trend is fitted.
    The series mean is carried flat with no interval, and
    :attr:`ForecastResult.has_trend_fit` reports it, so the caller can label the
    output honestly instead of presenting a guess as a projection.
    """
    horizon_days = max(horizon, 0)
    observations = len(series)

    if observations == 0:
        return ForecastResult(
            points=tuple(
                ForecastPoint(horizon_day=step, predicted=0.0, lower_bound=0.0, upper_bound=0.0)
                for step in range(1, horizon_days + 1)
            ),
            level=0.0,
            trend=0.0,
            residual_std_error=None,
            observations=0,
        )

    if observations < MIN_OBSERVATIONS_FOR_TREND:
        flat = max(statistics.fmean(series), 0.0)
        return ForecastResult(
            points=tuple(
                ForecastPoint(
                    horizon_day=step,
                    predicted=flat,
                    lower_bound=flat,
                    upper_bound=flat,
                )
                for step in range(1, horizon_days + 1)
            ),
            level=flat,
            trend=0.0,
            residual_std_error=None,
            observations=observations,
        )

    level = float(series[0])
    trend = float(series[1] - series[0])
    residuals: list[float] = []

    for observed in series[1:]:
        one_step_ahead = level + trend
        residuals.append(observed - one_step_ahead)
        previous_level = level
        level = alpha * observed + (1.0 - alpha) * one_step_ahead
        trend = beta * (level - previous_level) + (1.0 - beta) * trend

    # Two degrees of freedom are spent estimating the level and the trend.
    degrees_of_freedom = len(residuals) - 2
    residual_std_error: float | None = None
    if degrees_of_freedom > 0:
        residual_std_error = math.sqrt(
            sum(residual * residual for residual in residuals) / degrees_of_freedom
        )

    points: list[ForecastPoint] = []
    for step in range(1, horizon_days + 1):
        predicted = max(level + step * trend, 0.0)
        margin = (
            0.0 if residual_std_error is None else Z_SCORE_95 * residual_std_error * math.sqrt(step)
        )
        points.append(
            ForecastPoint(
                horizon_day=step,
                predicted=predicted,
                lower_bound=max(predicted - margin, 0.0),
                upper_bound=predicted + margin,
            )
        )

    return ForecastResult(
        points=tuple(points),
        level=level,
        trend=trend,
        residual_std_error=residual_std_error,
        observations=observations,
    )
