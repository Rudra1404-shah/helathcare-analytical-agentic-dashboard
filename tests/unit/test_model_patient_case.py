"""Patient case rules: vitals plausibility, discharge completeness, timeline."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.domain.enums import CaseStatus
from src.domain.models.base import utcnow
from tests import factories


class TestVitalSigns:
    """Observations must be physiologically plausible."""

    def test_valid_vitals_are_accepted(self) -> None:
        """A normal observation set passes."""
        vitals = factories.build_vitals()
        assert vitals.systolic_bp == 120

    def test_systolic_below_diastolic_is_rejected(self) -> None:
        """Inverted blood pressure is physically impossible."""
        with pytest.raises(ValidationError, match="must be greater than"):
            factories.build_vitals(systolic_bp=70, diastolic_bp=110)

    def test_equal_systolic_and_diastolic_is_rejected(self) -> None:
        """Equal pressures mean no pulse pressure, which is not survivable."""
        with pytest.raises(ValidationError, match="must be greater than"):
            factories.build_vitals(systolic_bp=90, diastolic_bp=90)

    @pytest.mark.parametrize("spo2", [-1.0, 100.1, 150.0])
    def test_out_of_range_spo2_is_rejected(self, spo2: float) -> None:
        """Oxygen saturation is a percentage and cannot leave 0-100."""
        with pytest.raises(ValidationError):
            factories.build_vitals(spo2_percent=spo2)

    @pytest.mark.parametrize("spo2", [0.0, 88.5, 100.0])
    def test_in_range_spo2_is_accepted(self, spo2: float) -> None:
        """The full percentage range is valid, including the boundaries."""
        assert factories.build_vitals(spo2_percent=spo2).spo2_percent == spo2

    @pytest.mark.parametrize("temperature", [24.9, 45.1, 200.0])
    def test_implausible_temperature_is_rejected(self, temperature: float) -> None:
        """A temperature outside survivable bounds is a data entry error."""
        with pytest.raises(ValidationError):
            factories.build_vitals(temperature_celsius=temperature)

    @pytest.mark.parametrize("pulse", [19, 301])
    def test_implausible_pulse_is_rejected(self, pulse: int) -> None:
        """A pulse outside plausible bounds would distort deterioration trends."""
        with pytest.raises(ValidationError):
            factories.build_vitals(pulse_bpm=pulse)

    def test_vitals_are_immutable(self) -> None:
        """A recorded observation must not be rewritten in place."""
        vitals = factories.build_vitals()
        with pytest.raises(ValidationError):
            vitals.pulse_bpm = 80


class TestCaseDischarge:
    """A closed case must carry complete closure details."""

    def test_open_case_needs_no_discharge_details(self) -> None:
        """An admitted case has no discharge information yet."""
        case = factories.build_patient_case()
        assert case.is_open is True
        assert case.discharged_at is None

    @pytest.mark.parametrize("status", [CaseStatus.DISCHARGED, CaseStatus.DECEASED])
    def test_closing_without_discharge_time_is_rejected(self, status: CaseStatus) -> None:
        """Without a discharge time, length of stay is uncomputable."""
        with pytest.raises(ValidationError, match="discharged_at is required"):
            factories.build_patient_case(status=status, discharge_summary="Recovered fully.")

    @pytest.mark.parametrize("status", [CaseStatus.DISCHARGED, CaseStatus.DECEASED])
    def test_closing_without_summary_is_rejected(self, status: CaseStatus) -> None:
        """A closed case must record its clinical outcome."""
        with pytest.raises(ValidationError, match="discharge_summary is required"):
            factories.build_patient_case(status=status, discharged_at=utcnow())

    def test_fully_discharged_case_is_accepted(self) -> None:
        """A complete discharge passes and reports itself closed."""
        case = factories.build_patient_case(
            status=CaseStatus.DISCHARGED,
            discharged_at=utcnow(),
            discharge_summary="Recovered fully; advised rest for one week.",
        )
        assert case.is_open is False

    def test_open_case_with_discharge_time_is_rejected(self) -> None:
        """A discharge time on an open case would corrupt occupancy counts."""
        with pytest.raises(ValidationError, match="must not be set"):
            factories.build_patient_case(status=CaseStatus.ADMITTED, discharged_at=utcnow())

    def test_discharge_before_admission_is_rejected(self) -> None:
        """The timeline cannot run backwards."""
        # Arrange
        admitted = utcnow()
        discharged = admitted - timedelta(hours=5)

        # Act / Assert
        with pytest.raises(ValidationError, match="cannot precede"):
            factories.build_patient_case(
                admitted_at=admitted,
                status=CaseStatus.DISCHARGED,
                discharged_at=discharged,
                discharge_summary="Summary.",
            )

    @pytest.mark.parametrize(
        "status", [CaseStatus.ADMITTED, CaseStatus.ICU, CaseStatus.OBSERVATION]
    )
    def test_open_statuses_report_as_open(self, status: CaseStatus) -> None:
        """Non-terminal statuses keep occupying capacity."""
        assert factories.build_patient_case(status=status).is_open is True


class TestCaseContent:
    """Symptoms, vitals history, and prescriptions."""

    def test_case_without_symptoms_is_rejected(self) -> None:
        """A case with no presenting complaint cannot be triaged."""
        with pytest.raises(ValidationError):
            factories.build_patient_case(chief_symptoms=[])

    def test_case_with_symptoms_is_accepted(self) -> None:
        """Recorded symptoms are preserved."""
        case = factories.build_patient_case(chief_symptoms=["chest pain"])
        assert case.chief_symptoms == ["chest pain"]

    def test_latest_vitals_returns_none_when_empty(self) -> None:
        """A case with no observations reports none."""
        assert factories.build_patient_case().latest_vitals is None

    def test_latest_vitals_returns_most_recent_reading(self) -> None:
        """Deterioration tracking depends on picking the newest reading."""
        # Arrange
        now = utcnow()
        older = factories.build_vitals(pulse_bpm=70, recorded_at=now - timedelta(hours=2))
        newer = factories.build_vitals(pulse_bpm=110, recorded_at=now)

        # Act: deliberately out of order to prove ordering is by timestamp
        case = factories.build_patient_case(vitals=[newer, older])

        # Assert
        assert case.latest_vitals is not None
        assert case.latest_vitals.pulse_bpm == 110

    def test_prescriptions_default_to_empty(self) -> None:
        """A case begins with no medication orders."""
        assert factories.build_patient_case().prescriptions == []

    def test_case_defaults_to_admitted(self) -> None:
        """New cases start admitted."""
        assert factories.build_patient_case().status is CaseStatus.ADMITTED
