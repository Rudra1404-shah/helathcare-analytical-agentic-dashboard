"""The statistical primitives behind the analytics engine, at their edges.

These are the functions most likely to be wrong in a way nothing else notices: a
division by zero only appears at the moment a hospital has no ICU beds, and a
flat baseline only appears for the rare disease the outbreak module exists to
catch. Every degenerate input is therefore covered explicitly.
"""

from datetime import UTC, datetime, timedelta

import pytest

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
    stdev_sample,
    z_score,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


class TestSafeRatio:
    """Division must never raise, and must distinguish undefined from zero."""

    def test_divides_normally(self) -> None:
        """An ordinary ratio is returned unchanged."""
        assert safe_ratio(45, 90) == 0.5

    def test_zero_denominator_is_undefined_not_zero(self) -> None:
        """A hospital with no beds has undefined occupancy, not empty wards.

        Returning 0.0 here would render as a comfortably empty ward on the
        dashboard, which is the opposite of the truth.
        """
        assert safe_ratio(10, 0) is None

    def test_zero_numerator_is_a_real_zero(self) -> None:
        """No occupied beds against real capacity genuinely is zero occupancy."""
        assert safe_ratio(0, 90) == 0.0


class TestPerCapita:
    """Incidence normalisation is what makes zones comparable."""

    def test_normalises_to_the_conventional_denominator(self) -> None:
        """Twenty-five cases in 250,000 people is ten per 100,000."""
        assert per_capita(25, 250_000) == pytest.approx(10.0)

    @pytest.mark.parametrize("population", [0, -1])
    def test_missing_population_yields_no_rate(self, population: int) -> None:
        """A zone with no recorded population cannot produce an incidence rate."""
        assert per_capita(5, population) is None

    def test_zero_cases_is_a_rate_of_zero(self) -> None:
        """A quiet zone has a real rate of zero, not an unknown one."""
        assert per_capita(0, 250_000) == 0.0


class TestDaysToStockout:
    """The countdown must never report infinity or a misleading large number."""

    def test_divides_stock_by_burn_rate(self) -> None:
        """Twenty units burning four a day lasts five days."""
        assert days_to_stockout(20.0, 4.0) == pytest.approx(5.0)

    def test_empty_stock_is_already_out(self) -> None:
        """Nothing left is zero days, whatever the burn rate."""
        assert days_to_stockout(0.0, 4.0) == 0.0

    def test_no_observed_burn_is_unknown_not_infinite(self) -> None:
        """No consumption means the horizon is unknown, not unlimited.

        A UI must render this as a dash. Reporting a huge number would read as
        reassurance the data does not support.
        """
        assert days_to_stockout(20.0, 0.0) is None

    def test_empty_stock_takes_priority_over_unknown_burn(self) -> None:
        """Out of stock is a fact even when nothing has been consumed yet."""
        assert days_to_stockout(0.0, 0.0) == 0.0


class TestDescriptiveStatistics:
    """Empty and single-point inputs are ordinary, not exceptional."""

    def test_mean_of_empty_series_is_undefined(self) -> None:
        """An empty series has no mean to report."""
        assert mean([]) is None

    def test_median_of_empty_series_is_undefined(self) -> None:
        """An empty series has no median to report."""
        assert median([]) is None

    def test_median_of_even_length_series_averages_the_middle(self) -> None:
        """The standard even-length median is used."""
        assert median([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)

    def test_stdev_needs_two_observations(self) -> None:
        """A single point has no spread."""
        assert stdev_sample([4.0]) is None

    def test_flat_series_has_zero_spread(self) -> None:
        """A flat series is not undefined; it genuinely has no variation."""
        assert stdev_sample([3.0, 3.0, 3.0]) == 0.0


class TestZScore:
    """The outbreak trigger, and the two inputs that would make it divide by zero."""

    def test_scores_a_clear_departure_from_baseline(self) -> None:
        """A value well above a varying baseline scores positively."""
        score = z_score(10.0, [1.0, 2.0, 1.0, 2.0, 1.0])
        assert score is not None
        assert score > 2.0

    def test_short_baseline_yields_no_score(self) -> None:
        """Fewer than the minimum observations is not a baseline."""
        baseline = [1.0] * (MIN_BASELINE_OBSERVATIONS - 1)
        assert z_score(10.0, baseline) is None

    def test_flat_baseline_yields_no_score_rather_than_infinity(self) -> None:
        """Zero variance has no standard deviation to divide by.

        A rare notifiable disease reporting the same figure every day produces
        exactly this, and a single case the next day is not infinitely anomalous.
        """
        assert z_score(10.0, [0.0, 0.0, 0.0, 0.0]) is None

    def test_value_below_baseline_scores_negative(self) -> None:
        """A quiet day scores below zero and cannot trip an upward threshold."""
        score = z_score(0.0, [5.0, 6.0, 5.0, 6.0])
        assert score is not None
        assert score < 0


class TestBucketByDay:
    """A daily series must preserve its gaps; they are data."""

    def test_returns_one_bucket_per_day_in_the_window(self) -> None:
        """The series length is the window, regardless of how sparse events are."""
        assert len(bucket_by_day([NOW], days=28, now=NOW)) == 28

    def test_today_lands_in_the_final_bucket(self) -> None:
        """Counts are oldest-first, so the last element is today."""
        counts = bucket_by_day([NOW, NOW], days=7, now=NOW)
        assert counts[-1] == 2
        assert sum(counts[:-1]) == 0

    def test_days_with_no_events_stay_as_zeros(self) -> None:
        """Dropping empty days would compress the timeline and inflate rates."""
        counts = bucket_by_day([NOW, NOW - timedelta(days=3)], days=5, now=NOW)
        assert counts == [0, 1, 0, 0, 1]

    def test_events_outside_the_window_are_ignored(self) -> None:
        """History older than the window contributes nothing to the baseline."""
        counts = bucket_by_day([NOW - timedelta(days=40)], days=7, now=NOW)
        assert sum(counts) == 0

    def test_future_events_are_ignored(self) -> None:
        """A timestamp ahead of the window end is out of range, not bucket zero."""
        counts = bucket_by_day([NOW + timedelta(days=2)], days=7, now=NOW)
        assert sum(counts) == 0

    def test_naive_timestamps_are_treated_as_utc(self) -> None:
        """An in-memory document may be naive; comparing it must not raise."""
        naive = NOW.replace(tzinfo=None)
        assert bucket_by_day([naive], days=3, now=NOW)[-1] == 1

    def test_unordered_input_buckets_correctly(self) -> None:
        """Callers pass whatever Mongo returned; ordering is not their job."""
        stamps = [NOW - timedelta(days=offset) for offset in (4, 0, 2, 0)]
        assert bucket_by_day(stamps, days=5, now=NOW) == [1, 0, 1, 0, 2]

    @pytest.mark.parametrize("days", [0, -1])
    def test_non_positive_window_is_empty(self, days: int) -> None:
        """A meaningless window produces no buckets rather than raising."""
        assert bucket_by_day([NOW], days=days, now=NOW) == []


class TestHoltLinearForecast:
    """The surge projection, its fallbacks, and its interval behaviour."""

    def test_empty_series_projects_zeros(self) -> None:
        """A hospital with no admissions on record forecasts nothing, safely."""
        result = holt_linear_forecast([], horizon=14)
        assert result.observations == 0
        assert len(result.points) == 14
        assert all(point.predicted == 0.0 for point in result.points)
        assert result.residual_std_error is None

    def test_short_series_carries_the_mean_flat(self) -> None:
        """Below a week of history no trend is fitted and none is implied."""
        series = [2.0] * (MIN_OBSERVATIONS_FOR_TREND - 1)
        result = holt_linear_forecast(series, horizon=7)
        assert not result.has_trend_fit
        assert result.trend == 0.0
        assert all(point.predicted == pytest.approx(2.0) for point in result.points)

    def test_short_series_offers_no_interval(self) -> None:
        """An interval implies a fit that was never made."""
        result = holt_linear_forecast([1.0, 5.0, 3.0], horizon=3)
        assert result.residual_std_error is None
        assert all(
            point.lower_bound == point.predicted == point.upper_bound for point in result.points
        )

    def test_rising_series_projects_upward(self) -> None:
        """A sustained climb produces a positive trend and a growing projection."""
        result = holt_linear_forecast([float(day) for day in range(1, 15)], horizon=14)
        assert result.has_trend_fit
        assert result.trend > 0
        assert result.points[-1].predicted > result.points[0].predicted

    def test_falling_series_never_projects_a_negative_count(self) -> None:
        """Extrapolating a decline past the axis is an artefact, not a forecast."""
        series = [float(value) for value in range(20, 6, -1)]
        result = holt_linear_forecast(series, horizon=30)
        assert result.trend < 0
        assert all(point.predicted >= 0.0 for point in result.points)
        assert all(point.lower_bound >= 0.0 for point in result.points)

    def test_interval_widens_with_the_horizon(self) -> None:
        """Uncertainty compounds, so day 14 is less certain than day 1."""
        series = [3.0, 5.0, 4.0, 8.0, 6.0, 9.0, 7.0, 11.0, 10.0, 13.0]
        result = holt_linear_forecast(series, horizon=14)
        assert result.residual_std_error is not None
        widths = [point.upper_bound - point.predicted for point in result.points]
        assert widths == sorted(widths)
        assert widths[-1] > widths[0]

    def test_interval_brackets_the_central_estimate(self) -> None:
        """The prediction always sits inside its own interval."""
        series = [3.0, 5.0, 4.0, 8.0, 6.0, 9.0, 7.0, 11.0]
        for point in holt_linear_forecast(series, horizon=14).points:
            assert point.lower_bound <= point.predicted <= point.upper_bound

    @pytest.mark.parametrize("horizon", [0, -3])
    def test_non_positive_horizon_projects_nothing(self, horizon: int) -> None:
        """Asking for no days ahead returns no points rather than raising."""
        assert holt_linear_forecast([1.0, 2.0, 3.0], horizon=horizon).points == ()

    def test_flat_series_has_no_trend(self) -> None:
        """A steady arrival rate is stable, and stays stable when projected."""
        result = holt_linear_forecast([5.0] * 20, horizon=14)
        assert result.trend == pytest.approx(0.0, abs=1e-9)
        assert all(point.predicted == pytest.approx(5.0) for point in result.points)
