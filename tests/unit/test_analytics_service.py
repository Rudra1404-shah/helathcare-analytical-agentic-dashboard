"""The seven analytics modules, their tenancy guard, and their degenerate inputs.

These tests exercise the pure reducers directly rather than the ``async`` entry
points, which is what keeps them free of MongoDB. The reducers are where every
interesting decision lives -- what counts as an anomaly, what a zero denominator
means, whether an empty result is "nothing wrong" or "nothing known" -- and the
entry points around them only resolve scope, fetch, and audit.

:func:`resolve_analytics_scope` is tested here too, because tenancy is a pure
function of the actor and is the one piece of this module that must never be
wrong.
"""

from datetime import UTC, datetime, timedelta
from typing import TypeVar

import pytest
from beanie import Document, PydanticObjectId
from pydantic import ValidationError

from src.core.errors import PermissionDeniedError
from src.domain.enums import (
    ActionTaken,
    AlertTier,
    CaseStatus,
    ComplaintCategory,
    EstimationBasis,
    InventoryCategory,
    InvestigationStatus,
    ShiftType,
    SignalConfidence,
    StaffStatus,
    TrendDirection,
    TriageLevel,
    UserRole,
)
from src.domain.models import Doctor, User
from src.services import analytics_service
from src.services.analytics_reducers import (
    summarise_outbreaks,
    summarise_policy_impact,
    summarise_realtime,
    summarise_resources,
    summarise_surge,
    summarise_workforce,
    synthesise_alerts,
)
from tests import factories

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ZONE_CODE = "MH-MUM-Z12"

DocumentT = TypeVar("DocumentT", bound=Document)


def with_id(document: DocumentT, document_id: PydanticObjectId | None = None) -> DocumentT:
    """Stamp a persisted identity onto an in-memory document.

    Factory documents have never been saved, so ``id`` is ``None``. Reducers
    that group by identity skip those on purpose, so any test about grouping has
    to give them one.
    """
    document.id = document_id or factories.object_id()
    return document


def scoped_actor(role: UserRole) -> User:
    """Build a hospital-scoped account, supplying the linkage its role requires.

    The ``User`` model insists a doctor account names a doctor record and a
    staff account names a staff record, so a role cannot be swapped in isolation.
    """
    extra: dict[str, PydanticObjectId] = {}
    if role is UserRole.DOCTOR:
        extra["doctor_id"] = factories.object_id()
    elif role is UserRole.HOSPITAL_STAFF:
        extra["staff_id"] = factories.object_id()
    return factories.build_hospital_user(role=role, **extra)


def days_ago(count: int) -> datetime:
    """Return a timestamp ``count`` days before the fixed test clock."""
    return NOW - timedelta(days=count)


def discharged_case(**overrides: object) -> object:
    """Build a closed case, which needs a discharge time and summary together."""
    return factories.build_patient_case(
        status=CaseStatus.DISCHARGED,
        admitted_at=days_ago(5),
        discharged_at=days_ago(1),
        discharge_summary="Recovered and discharged.",
        **overrides,
    )


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
class TestAnalyticsScope:
    """Who may read what. The single most important behaviour in the module."""

    def test_citizen_is_refused_outright(self) -> None:
        """`hospital_scope_of` returns None for a citizen as well as a ministry
        official, so the ordinary sweep idiom would read None as "every
        hospital" and hand national intelligence to any citizen account.
        """
        citizen = factories.build_user(role=UserRole.CITIZEN)

        with pytest.raises(PermissionDeniedError, match="ministry and hospital staff"):
            analytics_service.resolve_analytics_scope(None, citizen)

    def test_citizen_is_refused_even_naming_a_hospital(self) -> None:
        """The refusal is about the role, not about which hospital was asked for."""
        citizen = factories.build_user(role=UserRole.CITIZEN)

        with pytest.raises(PermissionDeniedError):
            analytics_service.resolve_analytics_scope(factories.object_id(), citizen)

    def test_ministry_account_reads_nationally(self) -> None:
        """A ministry official asking for nothing in particular sees everything."""
        official = factories.build_user(
            role=UserRole.GOVT_ADMIN, email="official@health.gov.example"
        )

        assert analytics_service.resolve_analytics_scope(None, official) is None

    def test_ministry_account_may_drill_into_one_hospital(self) -> None:
        """Drilling from a flagged zone into the site causing it must work."""
        official = factories.build_user(
            role=UserRole.GOVT_ADMIN, email="official@health.gov.example"
        )
        target = factories.object_id()

        assert analytics_service.resolve_analytics_scope(target, official) == target

    @pytest.mark.parametrize(
        "role",
        [UserRole.HOSPITAL_ADMIN, UserRole.HOSPITAL_STAFF, UserRole.DOCTOR],
    )
    def test_hospital_roles_are_confined_to_their_own_hospital(self, role: UserRole) -> None:
        """Omitting the hospital cannot widen a scoped account to the nation."""
        actor = scoped_actor(role)

        assert analytics_service.resolve_analytics_scope(None, actor) == actor.hospital_id

    @pytest.mark.parametrize(
        "role",
        [UserRole.HOSPITAL_ADMIN, UserRole.HOSPITAL_STAFF, UserRole.DOCTOR],
    )
    def test_hospital_roles_cannot_read_another_hospital(self, role: UserRole) -> None:
        """A foreign hospital is refused rather than silently swapped for their own.

        Quiet redirection would turn a deliberate probe into a request that
        looks successful and leaves no trace of the attempt.
        """
        actor = scoped_actor(role)

        with pytest.raises(PermissionDeniedError, match="another hospital"):
            analytics_service.resolve_analytics_scope(factories.object_id(), actor)

    def test_asking_for_your_own_hospital_explicitly_is_allowed(self) -> None:
        """Naming your own hospital is the normal path from the portal."""
        actor = factories.build_hospital_user()

        resolved = analytics_service.resolve_analytics_scope(actor.hospital_id, actor)

        assert resolved == actor.hospital_id


# --------------------------------------------------------------------------- #
# Module 1 -- Real-time monitoring
# --------------------------------------------------------------------------- #
class TestRealtimeMonitoring:
    """Live occupancy, and what it reports when there is nothing to report."""

    def test_counts_open_cases_against_sanctioned_capacity(self) -> None:
        """Occupancy is open cases over sanctioned beds."""
        hospital = with_id(
            factories.build_hospital(
                capacity=factories.build_capacity(
                    total_sanctioned_beds=100, icu_beds=10, emergency_beds=0
                )
            )
        )
        cases = [
            factories.build_patient_case(case_number=f"CASE-{index}", status=CaseStatus.ADMITTED)
            for index in range(8)
        ]
        cases += [
            factories.build_patient_case(case_number=f"ICU-{index}", status=CaseStatus.ICU)
            for index in range(2)
        ]

        result = summarise_realtime(
            hospitals=[hospital],
            cases=cases,
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        assert result.open_cases == 10
        assert result.icu_cases == 2
        assert result.bed_occupancy_ratio == pytest.approx(0.10)
        assert result.icu_occupancy_ratio == pytest.approx(0.20)

    def test_discharged_cases_release_capacity(self) -> None:
        """A closed case no longer occupies a bed and must not inflate occupancy."""
        hospital = with_id(factories.build_hospital())

        result = summarise_realtime(
            hospitals=[hospital],
            cases=[discharged_case()],  # type: ignore[list-item]
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        assert result.open_cases == 0

    def test_hospital_with_no_icu_beds_reports_undefined_occupancy(self) -> None:
        """Zero ICU beds is undefined occupancy, not an empty ICU.

        Reporting 0% here would render as spare critical-care capacity that does
        not exist, which is precisely the fragmentation this platform fixes.
        """
        hospital = with_id(
            factories.build_hospital(
                capacity=factories.build_capacity(
                    total_sanctioned_beds=50, icu_beds=0, emergency_beds=0, ventilators=0
                )
            )
        )

        result = summarise_realtime(
            hospitals=[hospital],
            cases=[],
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        assert result.icu_occupancy_ratio is None
        assert result.bed_occupancy_ratio == 0.0

    def test_empty_platform_reports_zeros_rather_than_an_empty_body(self) -> None:
        """A view with no hospitals still owes the client a complete shape."""
        result = summarise_realtime(
            hospitals=[], cases=[], items=[], case_types=[], hospital_id=None, now=NOW
        )

        assert result.open_cases == 0
        assert result.hospital_count == 0
        assert result.bed_occupancy_ratio is None
        assert len(result.triage_breakdown) == len(TriageLevel)

    def test_triage_falls_back_to_the_case_type(self) -> None:
        """A case can be classified before it is triaged, and vice versa."""
        case_type = with_id(factories.build_case_type(triage_level=TriageLevel.IMMEDIATE))
        hospital = with_id(factories.build_hospital())
        case = factories.build_patient_case(case_type_id=case_type.id, triage_level=None)

        result = summarise_realtime(
            hospitals=[hospital],
            cases=[case],
            items=[],
            case_types=[case_type],
            hospital_id=hospital.id,
            now=NOW,
        )

        immediate = next(
            entry
            for entry in result.triage_breakdown
            if entry.triage_level is TriageLevel.IMMEDIATE
        )
        assert immediate.open_cases == 1
        assert result.unclassified_cases == 0

    def test_case_triage_wins_over_the_case_type_default(self) -> None:
        """Triage assigned at the bedside reflects this patient, not the disease."""
        case_type = with_id(factories.build_case_type(triage_level=TriageLevel.NON_URGENT))
        case = factories.build_patient_case(
            case_type_id=case_type.id, triage_level=TriageLevel.IMMEDIATE
        )

        result = summarise_realtime(
            hospitals=[with_id(factories.build_hospital())],
            cases=[case],
            items=[],
            case_types=[case_type],
            hospital_id=None,
            now=NOW,
        )

        by_level = {entry.triage_level: entry.open_cases for entry in result.triage_breakdown}
        assert by_level[TriageLevel.IMMEDIATE] == 1
        assert by_level[TriageLevel.NON_URGENT] == 0

    def test_untriaged_unclassified_cases_are_counted_separately(self) -> None:
        """Folding them into the least urgent bucket would understate acuity."""
        result = summarise_realtime(
            hospitals=[with_id(factories.build_hospital())],
            cases=[factories.build_patient_case(case_type_id=None, triage_level=None)],
            items=[],
            case_types=[],
            hospital_id=None,
            now=NOW,
        )

        assert result.unclassified_cases == 1
        assert sum(entry.open_cases for entry in result.triage_breakdown) == 0


# --------------------------------------------------------------------------- #
# Module 2 -- Outbreak anomaly detection
# --------------------------------------------------------------------------- #
class TestOutbreakDetection:
    """Clustering signals, and the inputs that would divide by zero."""

    @staticmethod
    def _world() -> tuple[object, object, object]:
        """Build one zone, one hospital inside it, and one notifiable disease."""
        zone = factories.build_zone(zone_code=ZONE_CODE, population_covered=250_000)
        hospital = with_id(factories.build_hospital(zone_code=ZONE_CODE))
        case_type = with_id(factories.build_case_type(is_notifiable=True))
        return zone, hospital, case_type

    def _cases(
        self,
        hospital_id: PydanticObjectId,
        case_type_id: PydanticObjectId,
        per_day: dict[int, int],
    ) -> list[object]:
        """Build cases admitted a given number of days ago."""
        cases: list[object] = []
        for offset, count in per_day.items():
            for index in range(count):
                cases.append(
                    factories.build_patient_case(
                        case_number=f"CASE-{offset}-{index}",
                        hospital_id=hospital_id,
                        case_type_id=case_type_id,
                        admitted_at=days_ago(offset),
                    )
                )
        return cases

    def test_flags_a_spike_against_a_varying_baseline(self) -> None:
        """A sharp break from a normal-looking baseline is the core signal."""
        zone, hospital, case_type = self._world()
        per_day = {offset: (1 if offset % 2 else 2) for offset in range(1, 28)}
        per_day[0] = 40

        result = summarise_outbreaks(
            zones=[zone],  # type: ignore[list-item]
            hospitals=[hospital],  # type: ignore[list-item]
            cases=self._cases(hospital.id, case_type.id, per_day),  # type: ignore[arg-type]
            case_types=[case_type],  # type: ignore[list-item]
            now=NOW,
        )

        assert result.evaluated_count == 1
        signal = result.signals[0]
        assert signal.is_anomaly
        assert signal.z_score is not None
        assert signal.z_score >= 2.0
        assert signal.confidence is SignalConfidence.HIGH
        assert result.anomaly_count == 1

    def test_steady_incidence_is_not_an_anomaly(self) -> None:
        """Business as usual must not fire, or the signal becomes noise."""
        zone, hospital, case_type = self._world()
        per_day = {offset: (1 if offset % 2 else 2) for offset in range(0, 28)}

        result = summarise_outbreaks(
            zones=[zone],  # type: ignore[list-item]
            hospitals=[hospital],  # type: ignore[list-item]
            cases=self._cases(hospital.id, case_type.id, per_day),  # type: ignore[arg-type]
            case_types=[case_type],  # type: ignore[list-item]
            now=NOW,
        )

        assert result.anomaly_count == 0

    def test_flat_baseline_reports_no_z_score_but_can_still_flag(self) -> None:
        """A rare disease reporting the same figure daily has zero variance.

        There is no standard deviation to divide by, so no z-score is produced.
        A sustained multiple of a non-zero flat line is still worth surfacing,
        at reduced confidence.
        """
        zone, hospital, case_type = self._world()
        per_day = dict.fromkeys(range(1, 28), 1)
        per_day[0] = 30

        result = summarise_outbreaks(
            zones=[zone],  # type: ignore[list-item]
            hospitals=[hospital],  # type: ignore[list-item]
            cases=self._cases(hospital.id, case_type.id, per_day),  # type: ignore[arg-type]
            case_types=[case_type],  # type: ignore[list-item]
            now=NOW,
        )

        signal = result.signals[0]
        assert signal.z_score is None
        assert signal.is_anomaly
        assert signal.confidence is SignalConfidence.LOW

    def test_zone_without_population_cannot_produce_a_rate(self) -> None:
        """Dividing by an unrecorded population would raise; it reports instead."""
        zone = factories.build_zone(zone_code=ZONE_CODE, population_covered=0)
        hospital = with_id(factories.build_hospital(zone_code=ZONE_CODE))
        case_type = with_id(factories.build_case_type(is_notifiable=True))

        result = summarise_outbreaks(
            zones=[zone],
            hospitals=[hospital],
            cases=self._cases(hospital.id, case_type.id, {0: 5}),  # type: ignore[arg-type]
            case_types=[case_type],
            now=NOW,
        )

        signal = result.signals[0]
        assert signal.observed_rate_per_100k is None
        assert signal.confidence is SignalConfidence.INSUFFICIENT_DATA
        assert not signal.is_anomaly

    def test_non_notifiable_conditions_are_excluded(self) -> None:
        """Running the test over every condition would bury a real signal."""
        zone = factories.build_zone(zone_code=ZONE_CODE)
        hospital = with_id(factories.build_hospital(zone_code=ZONE_CODE))
        routine = with_id(factories.build_case_type(is_notifiable=False))

        result = summarise_outbreaks(
            zones=[zone],
            hospitals=[hospital],
            cases=self._cases(hospital.id, routine.id, {0: 50}),  # type: ignore[arg-type]
            case_types=[routine],
            now=NOW,
        )

        assert result.evaluated_count == 0
        assert result.signals == []

    def test_empty_database_evaluates_nothing(self) -> None:
        """No data is an empty result, not a crash and not a false all-clear."""
        result = summarise_outbreaks(zones=[], hospitals=[], cases=[], case_types=[], now=NOW)

        assert result.evaluated_count == 0
        assert result.anomaly_count == 0

    def test_hospital_outside_any_known_zone_is_skipped(self) -> None:
        """A zone code with no matching zone has no population denominator."""
        hospital = with_id(factories.build_hospital(zone_code="XX-UNKNOWN-Z1"))
        case_type = with_id(factories.build_case_type(is_notifiable=True))

        result = summarise_outbreaks(
            zones=[factories.build_zone(zone_code=ZONE_CODE)],
            hospitals=[hospital],
            cases=self._cases(hospital.id, case_type.id, {0: 5}),  # type: ignore[arg-type]
            case_types=[case_type],
            now=NOW,
        )

        assert result.evaluated_count == 0


# --------------------------------------------------------------------------- #
# Module 3 -- Surge forecasting
# --------------------------------------------------------------------------- #
class TestSurgeForecast:
    """The projection, and how it labels itself when the history is thin."""

    def test_rising_admissions_project_upward(self) -> None:
        """A climbing arrival rate must produce a rising, labelled forecast."""
        cases = [
            factories.build_patient_case(
                case_number=f"CASE-{offset}-{index}", admitted_at=days_ago(offset)
            )
            for offset in range(0, 20)
            for index in range(max(1, 20 - offset))
        ]

        result = summarise_surge(cases=cases, hospital_id=None, horizon_days=14, now=NOW)

        assert result.trend_direction is TrendDirection.RISING
        assert result.trend_per_day > 0
        assert len(result.points) == 14
        assert result.projected_14_day_total > result.projected_7_day_total

    def test_projection_carries_a_widening_interval(self) -> None:
        """Day 14 is less certain than day 1 and must be shown as such."""
        cases = [
            factories.build_patient_case(
                case_number=f"CASE-{offset}-{index}", admitted_at=days_ago(offset)
            )
            for offset in range(0, 20)
            for index in range(1 + offset % 4)
        ]

        points = summarise_surge(cases=cases, hospital_id=None, horizon_days=14, now=NOW).points

        first = points[0].upper_bound - points[0].predicted_admissions
        last = points[-1].upper_bound - points[-1].predicted_admissions
        assert last > first

    def test_no_admissions_is_flagged_as_insufficient_data(self) -> None:
        """An empty history must not masquerade as a confident forecast of zero."""
        result = summarise_surge(cases=[], hospital_id=None, horizon_days=14, now=NOW)

        assert result.confidence is SignalConfidence.INSUFFICIENT_DATA
        assert result.trend_direction is TrendDirection.STABLE
        assert all(point.predicted_admissions == 0.0 for point in result.points)

    def test_a_few_days_of_history_is_flagged_as_insufficient(self) -> None:
        """A hospital that opened last week has no baseline, and says so."""
        cases = [
            factories.build_patient_case(case_number=f"CASE-{offset}", admitted_at=days_ago(offset))
            for offset in range(3)
        ]

        result = summarise_surge(
            cases=cases, hospital_id=None, history_days=30, horizon_days=7, now=NOW
        )

        assert result.confidence is SignalConfidence.INSUFFICIENT_DATA

    def test_forecast_never_projects_a_negative_admission_count(self) -> None:
        """Extrapolating a decline past zero is an artefact, not a projection."""
        cases = [
            factories.build_patient_case(
                case_number=f"CASE-{offset}-{index}", admitted_at=days_ago(offset)
            )
            for offset in range(0, 20)
            for index in range(offset)
        ]

        result = summarise_surge(cases=cases, hospital_id=None, horizon_days=30, now=NOW)

        assert result.trend_direction is TrendDirection.FALLING
        assert all(point.predicted_admissions >= 0.0 for point in result.points)
        assert all(point.lower_bound >= 0.0 for point in result.points)

    def test_history_is_returned_for_plotting(self) -> None:
        """A client plots observed and forecast on one axis without a second call."""
        result = summarise_surge(
            cases=[factories.build_patient_case(admitted_at=NOW)],
            hospital_id=None,
            history_days=30,
            horizon_days=7,
            now=NOW,
        )

        assert len(result.history) == 30
        assert result.history[-1] == 1


# --------------------------------------------------------------------------- #
# Module 4 -- Workforce reallocation
# --------------------------------------------------------------------------- #
class TestWorkforceReallocation:
    """Burnout, shift cover, and the difference between calm and unknown."""

    def test_burnout_is_load_over_declared_capacity(self) -> None:
        """Fifteen open cases against a ceiling of thirty is an index of 0.5."""
        doctor = with_id(factories.build_doctor(max_daily_patients=30))
        cases = [
            factories.build_patient_case(case_number=f"CASE-{index}", doctor_id=doctor.id)
            for index in range(15)
        ]

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=cases,
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert result.doctors[0].burnout_index == pytest.approx(0.5)
        assert not result.doctors[0].is_overloaded

    def test_a_doctor_over_their_ceiling_is_flagged(self) -> None:
        """Past the declared ceiling the index exceeds one and must be visible."""
        doctor = with_id(factories.build_doctor(max_daily_patients=5))
        cases = [
            factories.build_patient_case(case_number=f"CASE-{index}", doctor_id=doctor.id)
            for index in range(9)
        ]

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=cases,
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert result.doctors[0].burnout_index == pytest.approx(1.8)
        assert result.doctors[0].is_overloaded
        assert result.overloaded_doctor_count == 1

    def test_closed_cases_do_not_count_toward_load(self) -> None:
        """A discharged patient is no longer work in progress."""
        doctor = with_id(factories.build_doctor())

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=[discharged_case(doctor_id=doctor.id)],  # type: ignore[list-item]
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert result.doctors[0].active_load == 0

    def test_no_doctors_on_file_is_distinguished_from_no_strain(self) -> None:
        """Both would otherwise render as a reassuring zero on the dashboard."""
        result = summarise_workforce(
            doctors=[], staff=[], cases=[], hospital_id=None, include_names=True, now=NOW
        )

        assert not result.has_capacity_data
        assert result.mean_burnout_index is None
        assert result.doctor_count == 0

    def test_model_refuses_a_zero_daily_ceiling(self) -> None:
        """The real guarantee against dividing by zero is the model constraint."""
        with pytest.raises(ValidationError):
            factories.build_doctor(max_daily_patients=0)

    def test_reducer_survives_a_zero_ceiling_anyway(self) -> None:
        """Defence in depth: the arithmetic must be safe on any input.

        ``model_construct`` bypasses validation to produce the document the model
        layer would refuse, proving the reducer does not rely on that refusal.
        """
        doctor = Doctor.model_construct(
            **factories.build_doctor().model_dump() | {"max_daily_patients": 0}
        )
        doctor.id = factories.object_id()

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=[factories.build_patient_case(doctor_id=doctor.id)],
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert result.doctors[0].burnout_index is None
        assert not result.doctors[0].is_overloaded

    def test_inactive_doctors_do_not_contribute_capacity(self) -> None:
        """A suspended doctor is not available cover, whatever their ceiling."""
        doctor = with_id(
            factories.build_doctor(max_daily_patients=40, status=StaffStatus.SUSPENDED)
        )

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=[],
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert result.active_doctor_count == 0
        assert result.total_daily_capacity == 0

    def test_shift_cover_counts_doctors_across_every_shift_they_hold(self) -> None:
        """A doctor declares a list of shifts; support staff hold exactly one."""
        doctor = with_id(factories.build_doctor(shifts=[ShiftType.MORNING, ShiftType.NIGHT]))
        nurse = factories.build_medical_staff(shift=ShiftType.NIGHT)
        cleaner = factories.build_support_staff(shift=ShiftType.MORNING)

        result = summarise_workforce(
            doctors=[doctor],
            staff=[nurse, cleaner],
            cases=[],
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        by_shift = {entry.shift: entry for entry in result.shift_balance}
        assert by_shift[ShiftType.MORNING].doctor_count == 1
        assert by_shift[ShiftType.NIGHT].doctor_count == 1
        assert by_shift[ShiftType.NIGHT].medical_staff_count == 1
        assert by_shift[ShiftType.MORNING].support_staff_count == 1
        assert by_shift[ShiftType.EVENING].doctor_count == 0

    def test_suggests_moving_cover_from_slack_to_strain(self) -> None:
        """The point of the module is a move, not a number."""
        busy_department = factories.object_id()
        quiet_department = factories.object_id()
        busy = with_id(factories.build_doctor(department_id=busy_department, max_daily_patients=5))
        quiet = with_id(
            factories.build_doctor(
                department_id=quiet_department, max_daily_patients=40, license_no="MCI-000002"
            )
        )
        cases = [
            factories.build_patient_case(case_number=f"CASE-{index}", doctor_id=busy.id)
            for index in range(10)
        ]

        result = summarise_workforce(
            doctors=[busy, quiet],
            staff=[],
            cases=cases,
            hospital_id=None,
            include_names=True,
            now=NOW,
        )

        assert len(result.suggestions) == 1
        assert result.suggestions[0].from_department_id == quiet_department
        assert result.suggestions[0].to_department_id == busy_department


# --------------------------------------------------------------------------- #
# Zero PHI
# --------------------------------------------------------------------------- #
class TestZeroPhi:
    """Analytics must answer its questions without carrying personal data."""

    def test_national_workforce_view_names_nobody(self) -> None:
        """The ministry needs to know where pressure is, not who is under it."""
        doctor = with_id(factories.build_doctor(full_name="Test Doctor"))

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=[],
            hospital_id=None,
            include_names=False,
            now=NOW,
        )

        assert result.doctors == []
        assert "Test Doctor" not in result.model_dump_json()
        assert result.departments != []

    def test_hospital_workforce_view_names_the_doctor_to_move(self) -> None:
        """Reallocating a ward is not actionable without knowing who to move."""
        doctor = with_id(factories.build_doctor(full_name="Test Doctor"))

        result = summarise_workforce(
            doctors=[doctor],
            staff=[],
            cases=[],
            hospital_id=doctor.hospital_id,
            include_names=True,
            now=NOW,
        )

        assert result.doctors[0].full_name == "Test Doctor"

    def test_realtime_view_carries_no_patient_identifiers(self) -> None:
        """Occupancy is a population question and needs no patient in it."""
        patient_id = factories.object_id()
        case = factories.build_patient_case(patient_id=patient_id)

        payload = summarise_realtime(
            hospitals=[with_id(factories.build_hospital())],
            cases=[case],
            items=[],
            case_types=[],
            hospital_id=None,
            now=NOW,
        ).model_dump_json()

        assert str(patient_id) not in payload
        assert str(case.case_number) not in payload


# --------------------------------------------------------------------------- #
# Module 5 -- Resource prediction
# --------------------------------------------------------------------------- #
class TestResourcePrediction:
    """Burn rate, the stockout countdown, and its unknowns."""

    def test_counts_down_to_stockout_from_observed_demand(self) -> None:
        """Stock divided by an inferred daily burn is the whole module."""
        hospital_id = factories.object_id()
        item = factories.build_inventory_item(
            hospital_id=hospital_id,
            category=InventoryCategory.GENERAL_BEDS,
            total_stock=100.0,
            available_stock=28.0,
        )
        cases = [
            factories.build_patient_case(
                case_number=f"CASE-{offset}-{index}", admitted_at=days_ago(offset)
            )
            for offset in range(14)
            for index in range(2)
        ]

        result = summarise_resources(items=[item], cases=cases, window_days=14, now=NOW)

        projection = result.projections[0]
        assert projection.daily_burn_rate == pytest.approx(2.0)
        assert projection.days_to_stockout == pytest.approx(14.0)
        assert projection.basis is EstimationBasis.ESTIMATED_FROM_CASE_DEMAND
        assert projection.projected_stockout_on is not None

    def test_no_observed_demand_leaves_the_horizon_unknown(self) -> None:
        """Unknown is not the same as unlimited and must not render as a number."""
        item = factories.build_inventory_item(available_stock=10.0, total_stock=10.0)

        result = summarise_resources(items=[item], cases=[], window_days=14, now=NOW)

        projection = result.projections[0]
        assert projection.days_to_stockout is None
        assert projection.projected_stockout_on is None
        assert projection.basis is EstimationBasis.INSUFFICIENT_HISTORY

    def test_exhausted_stock_reports_zero_days(self) -> None:
        """Out of stock is a fact even when no consumption has been observed."""
        item = factories.build_inventory_item(available_stock=0.0, total_stock=10.0)

        result = summarise_resources(items=[item], cases=[], window_days=14, now=NOW)

        assert result.projections[0].days_to_stockout == 0.0
        assert result.at_risk_count == 1

    def test_empty_inventory_projects_nothing(self) -> None:
        """A hospital tracking no stock produces no projections, and no error."""
        result = summarise_resources(items=[], cases=[], window_days=14, now=NOW)

        assert result.projections == []
        assert result.at_risk_count == 0

    def test_lines_in_one_category_are_summed(self) -> None:
        """Two ventilator models are one category on the dashboard."""
        hospital_id = factories.object_id()
        items = [
            factories.build_inventory_item(
                hospital_id=hospital_id,
                category=InventoryCategory.VENTILATORS,
                item_name=name,
                total_stock=10.0,
                available_stock=4.0,
            )
            for name in ("Adult Ventilator", "Paediatric Ventilator")
        ]

        result = summarise_resources(items=items, cases=[], window_days=14, now=NOW)

        assert len(result.projections) == 1
        assert result.projections[0].line_count == 2
        assert result.projections[0].available_stock == pytest.approx(8.0)

    def test_below_threshold_is_reported_per_category(self) -> None:
        """The safety threshold is what the alert module fires on."""
        item = factories.build_inventory_item(
            total_stock=40.0, available_stock=3.0, min_safety_threshold=5.0
        )

        result = summarise_resources(items=[item], cases=[], window_days=14, now=NOW)

        assert result.projections[0].is_below_threshold


# --------------------------------------------------------------------------- #
# Module 6 -- 4-tier Smart Alerts
# --------------------------------------------------------------------------- #
class TestSmartAlerts:
    """Tiering and ordering, built only from the other modules' own outputs."""

    @staticmethod
    def _empty_inputs(now: datetime) -> dict[str, object]:
        """Build a quiet platform: every module reporting nothing of concern."""
        return {
            "realtime": summarise_realtime(
                hospitals=[], cases=[], items=[], case_types=[], hospital_id=None, now=now
            ),
            "outbreaks": summarise_outbreaks(
                zones=[], hospitals=[], cases=[], case_types=[], now=now
            ),
            "workforce": summarise_workforce(
                doctors=[], staff=[], cases=[], hospital_id=None, include_names=False, now=now
            ),
            "resources": summarise_resources(items=[], cases=[], window_days=14, now=now),
        }

    def test_a_quiet_platform_raises_nothing(self) -> None:
        """Alerts on an idle system would train operators to ignore them."""
        result = synthesise_alerts(
            **self._empty_inputs(NOW),  # type: ignore[arg-type]
            hospital_id=None,
            now=NOW,
        )

        assert result.alerts == []
        assert result.critical_count == 0

    def test_exhausted_icu_raises_a_critical_alert(self) -> None:
        """Full critical care is the most urgent thing the platform can say."""
        hospital = with_id(
            factories.build_hospital(
                capacity=factories.build_capacity(
                    total_sanctioned_beds=100, icu_beds=4, emergency_beds=0
                )
            )
        )
        cases = [
            factories.build_patient_case(case_number=f"ICU-{index}", status=CaseStatus.ICU)
            for index in range(4)
        ]
        inputs = self._empty_inputs(NOW)
        inputs["realtime"] = summarise_realtime(
            hospitals=[hospital],
            cases=cases,
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        result = synthesise_alerts(**inputs, hospital_id=hospital.id, now=NOW)  # type: ignore[arg-type]

        assert result.critical_count >= 1
        assert result.alerts[0].tier is AlertTier.CRITICAL

    def test_imminent_stockout_below_threshold_is_critical(self) -> None:
        """Two days of stock and already under the safety line is an emergency."""
        item = factories.build_inventory_item(
            category=InventoryCategory.GENERAL_BEDS,
            total_stock=100.0,
            available_stock=2.0,
            min_safety_threshold=10.0,
        )
        cases = [
            factories.build_patient_case(
                case_number=f"CASE-{offset}-{index}", admitted_at=days_ago(offset)
            )
            for offset in range(14)
            for index in range(2)
        ]
        inputs = self._empty_inputs(NOW)
        inputs["resources"] = summarise_resources(
            items=[item], cases=cases, window_days=14, now=NOW
        )

        result = synthesise_alerts(**inputs, hospital_id=None, now=NOW)  # type: ignore[arg-type]

        assert any(alert.tier is AlertTier.CRITICAL for alert in result.alerts)

    def test_alerts_are_ordered_most_severe_first(self) -> None:
        """An operations desk reads from the top; ordering is the interface."""
        hospital = with_id(
            factories.build_hospital(
                capacity=factories.build_capacity(
                    total_sanctioned_beds=10, icu_beds=2, emergency_beds=0
                )
            )
        )
        cases = [
            factories.build_patient_case(case_number=f"ICU-{index}", status=CaseStatus.ICU)
            for index in range(2)
        ]
        cases += [factories.build_patient_case(case_number=f"CASE-{index}") for index in range(8)]
        inputs = self._empty_inputs(NOW)
        inputs["realtime"] = summarise_realtime(
            hospitals=[hospital],
            cases=cases,
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        alerts = synthesise_alerts(**inputs, hospital_id=None, now=NOW).alerts  # type: ignore[arg-type]

        tiers = [alert.tier for alert in alerts]
        order = [AlertTier.CRITICAL, AlertTier.HIGH, AlertTier.MEDIUM, AlertTier.INFO]
        assert tiers == sorted(tiers, key=order.index)

    def test_every_alert_carries_an_action(self) -> None:
        """An alert nobody can act on is noise."""
        hospital = with_id(
            factories.build_hospital(
                capacity=factories.build_capacity(
                    total_sanctioned_beds=10, icu_beds=2, emergency_beds=0
                )
            )
        )
        inputs = self._empty_inputs(NOW)
        inputs["realtime"] = summarise_realtime(
            hospitals=[hospital],
            cases=[
                factories.build_patient_case(case_number=f"CASE-{index}") for index in range(10)
            ],
            items=[],
            case_types=[],
            hospital_id=hospital.id,
            now=NOW,
        )

        alerts = synthesise_alerts(**inputs, hospital_id=None, now=NOW).alerts  # type: ignore[arg-type]

        assert alerts
        assert all(alert.recommended_action for alert in alerts)


# --------------------------------------------------------------------------- #
# Module 7 -- Policy impact tracking
# --------------------------------------------------------------------------- #
class TestPolicyImpact:
    """Enforcement, speed, and whether any of it changed behaviour."""

    def test_counts_complaints_by_category_and_status(self) -> None:
        """The distribution is the first question a ministry desk asks."""
        complaints = [
            factories.build_complaint(
                complaint_number=f"CMP-{index}", category=ComplaintCategory.OVERCHARGING
            )
            for index in range(3)
        ]

        result = summarise_policy_impact(complaints=complaints, hospital_id=None, now=NOW)

        by_category = {entry.category: entry.count for entry in result.by_category}
        assert result.total_complaints == 3
        assert by_category[ComplaintCategory.OVERCHARGING] == 3
        assert by_category[ComplaintCategory.HYGIENE] == 0
        assert result.open_complaints == 3

    def test_resolution_time_is_measured_from_filing_to_closure(self) -> None:
        """Speed of resolution is the ministry's own performance measure."""
        complaint = factories.build_complaint(
            created_at=days_ago(10),
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.FINE,
            closure_remarks="Fine levied and paid.",
            closed_at=days_ago(4),
        )

        result = summarise_policy_impact(complaints=[complaint], hospital_id=None, now=NOW)

        assert result.closed_complaints == 1
        assert result.mean_resolution_days == pytest.approx(6.0)
        assert result.median_resolution_days == pytest.approx(6.0)

    def test_nothing_closed_yet_reports_no_resolution_time(self) -> None:
        """Zero days would read as instant resolution rather than none at all."""
        result = summarise_policy_impact(
            complaints=[factories.build_complaint()], hospital_id=None, now=NOW
        )

        assert result.mean_resolution_days is None
        assert result.median_resolution_days is None
        assert result.enforcement_rate is None

    def test_enforcement_rate_excludes_dismissals(self) -> None:
        """A dismissed complaint is a closure, not an enforcement."""
        fined = factories.build_complaint(
            complaint_number="CMP-0001",
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.FINE,
            closure_remarks="Fine levied.",
            closed_at=days_ago(1),
        )
        dismissed = factories.build_complaint(
            complaint_number="CMP-0002",
            investigation_status=InvestigationStatus.DISMISSED,
            action_taken=ActionTaken.DISMISSED,
            closure_remarks="No evidence of wrongdoing.",
            closed_at=days_ago(1),
        )

        result = summarise_policy_impact(complaints=[fined, dismissed], hospital_id=None, now=NOW)

        assert result.closed_complaints == 2
        assert result.enforcement_rate == pytest.approx(0.5)

    def test_repeat_complaint_after_enforcement_is_recidivism(self) -> None:
        """An action followed by more of the same is the clearest sign it failed."""
        hospital_id = factories.object_id()
        enforced = factories.build_complaint(
            complaint_number="CMP-0001",
            hospital_id=hospital_id,
            category=ComplaintCategory.HYGIENE,
            created_at=days_ago(30),
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.WARNING,
            closure_remarks="Warning issued to the administrator.",
            closed_at=days_ago(20),
        )
        repeat = factories.build_complaint(
            complaint_number="CMP-0002",
            hospital_id=hospital_id,
            category=ComplaintCategory.HYGIENE,
            created_at=days_ago(5),
        )

        result = summarise_policy_impact(complaints=[enforced, repeat], hospital_id=None, now=NOW)

        assert result.repeat_offender_count == 1
        entry = result.recidivism[0]
        assert entry.hospital_id == hospital_id
        assert entry.category is ComplaintCategory.HYGIENE
        assert entry.complaints_after_action == 1

    def test_enforcement_that_worked_is_not_recidivism(self) -> None:
        """No repeat complaint means the action landed and must not be flagged."""
        enforced = factories.build_complaint(
            created_at=days_ago(30),
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.LICENSE_SUSPENSION,
            closure_remarks="Licence suspended pending remediation.",
            closed_at=days_ago(20),
        )

        result = summarise_policy_impact(complaints=[enforced], hospital_id=None, now=NOW)

        assert result.recidivism == []
        assert result.repeat_offender_count == 0

    def test_no_complaints_reports_a_complete_empty_shape(self) -> None:
        """A clean record still owes the client every bucket, at zero."""
        result = summarise_policy_impact(complaints=[], hospital_id=None, now=NOW)

        assert result.total_complaints == 0
        assert len(result.by_category) == len(ComplaintCategory)
        assert len(result.by_status) == len(InvestigationStatus)
        assert all(entry.count == 0 for entry in result.by_category)
