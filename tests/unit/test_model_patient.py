"""Patient and case type rules."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from src.domain.enums import BloodGroup, DiseaseCategory, TriageLevel
from src.domain.models.base import utcnow
from tests import factories


class TestPatientAgeSignals:
    """Every patient needs at least one age signal for triage."""

    def test_age_only_is_accepted(self) -> None:
        """Emergency intake often records age rather than a birth date."""
        patient = factories.build_patient(age_years=34, date_of_birth=None)
        assert patient.effective_age_years == 34

    def test_date_of_birth_only_is_accepted(self) -> None:
        """A birth date alone is sufficient and more precise."""
        # Arrange
        birth_date = date(utcnow().year - 40, 1, 1)

        # Act
        patient = factories.build_patient(age_years=None, date_of_birth=birth_date)

        # Assert
        assert patient.effective_age_years in (39, 40)

    def test_neither_age_nor_birth_date_is_rejected(self) -> None:
        """A record with no age cannot be triaged safely."""
        with pytest.raises(ValidationError, match="either date_of_birth or age_years"):
            factories.build_patient(age_years=None, date_of_birth=None)

    def test_date_of_birth_takes_precedence_over_recorded_age(self) -> None:
        """The precise signal wins when both are present."""
        # Arrange
        birth_date = date(utcnow().year - 40, 1, 1)

        # Act
        patient = factories.build_patient(age_years=99, date_of_birth=birth_date)

        # Assert
        assert patient.effective_age_years != 99

    def test_future_birth_date_is_rejected(self) -> None:
        """A patient cannot be born in the future."""
        future = utcnow().date() + timedelta(days=1)
        with pytest.raises(ValidationError, match="cannot be in the future"):
            factories.build_patient(date_of_birth=future)

    def test_implausible_age_is_rejected(self) -> None:
        """An age beyond the human maximum is a data entry error."""
        with pytest.raises(ValidationError):
            factories.build_patient(age_years=200)

    def test_newborn_age_zero_is_accepted(self) -> None:
        """Age zero is valid for a newborn."""
        assert factories.build_patient(age_years=0).age_years == 0


class TestPatientRecord:
    """Identity and clinical background fields."""

    def test_mrn_is_upper_cased(self) -> None:
        """MRNs normalise so hospital-scoped lookups are case-insensitive."""
        patient = factories.build_patient(mrn="mrn-abc-1")
        assert patient.mrn == "MRN-ABC-1"

    def test_blood_group_defaults_to_unknown(self) -> None:
        """Blood group is often unknown at intake."""
        patient = factories.build_patient(blood_group=BloodGroup.UNKNOWN)
        assert patient.blood_group is BloodGroup.UNKNOWN

    def test_allergies_default_to_empty(self) -> None:
        """A patient with no recorded allergies has an empty list, not None."""
        assert factories.build_patient().allergies == []

    def test_allergies_are_recorded(self) -> None:
        """Recorded allergies are preserved."""
        patient = factories.build_patient(allergies=["penicillin", "sulfa"])
        assert len(patient.allergies) == 2

    def test_emergency_contact_is_optional(self) -> None:
        """Intake may proceed without next of kin."""
        assert factories.build_patient().emergency_contact is None

    def test_emergency_contact_is_recorded(self) -> None:
        """A supplied emergency contact is preserved."""
        # Arrange
        from src.domain.models.patient import EmergencyContact

        contact = EmergencyContact(
            name="Test Relative", phone="+919812345678", relationship="Spouse"
        )

        # Act
        patient = factories.build_patient(emergency_contact=contact)

        # Assert
        assert patient.emergency_contact is not None
        assert patient.emergency_contact.relationship == "Spouse"

    def test_short_name_is_rejected(self) -> None:
        """A one-character name is a data entry error."""
        with pytest.raises(ValidationError):
            factories.build_patient(full_name="A")

    def test_patient_starts_active(self) -> None:
        """New patient records are active."""
        assert factories.build_patient().is_active is True


class TestCaseType:
    """Disease classification and triage rules."""

    def test_valid_case_type_is_accepted(self) -> None:
        """The default case type is valid."""
        case_type = factories.build_case_type()
        assert case_type.icd10_code == "A09"
        assert case_type.triage_level is TriageLevel.URGENT

    def test_case_type_without_hospital_is_a_national_standard(self) -> None:
        """A null hospital scopes the definition nationally."""
        assert factories.build_case_type().is_national_standard is True

    def test_hospital_scoped_case_type_is_not_national(self) -> None:
        """A hospital-owned definition is not a national standard."""
        case_type = factories.build_case_type(hospital_id=factories.object_id())
        assert case_type.is_national_standard is False

    @pytest.mark.parametrize("code", ["A09", "J18.9", "E11.65"])
    def test_valid_icd10_codes_are_accepted(self, code: str) -> None:
        """Well-formed ICD-10 codes pass."""
        assert factories.build_case_type(icd10_code=code).icd10_code == code

    @pytest.mark.parametrize("code", ["09", "AA9", "A9", "A093333", "not-a-code"])
    def test_malformed_icd10_codes_are_rejected(self, code: str) -> None:
        """A malformed code would break outbreak grouping."""
        with pytest.raises(ValidationError):
            factories.build_case_type(icd10_code=code)

    def test_icd10_code_is_upper_cased(self) -> None:
        """ICD-10 codes normalise to upper case."""
        assert factories.build_case_type(icd10_code="j18.9").icd10_code == "J18.9"

    @pytest.mark.parametrize("level", [1, 2, 3, 4])
    def test_valid_triage_levels_are_accepted(self, level: int) -> None:
        """Levels 1 through 4 are the defined range."""
        assert int(factories.build_case_type(triage_level=level).triage_level) == level

    @pytest.mark.parametrize("level", [0, 5, -1, 99])
    def test_out_of_range_triage_levels_are_rejected(self, level: int) -> None:
        """A level outside 1-4 has no defined clinical meaning."""
        with pytest.raises(ValidationError):
            factories.build_case_type(triage_level=level)

    def test_notifiable_flag_is_recorded(self) -> None:
        """The outbreak module keys off this flag."""
        assert factories.build_case_type(is_notifiable=True).is_notifiable is True

    @pytest.mark.parametrize("category", list(DiseaseCategory))
    def test_all_disease_categories_are_accepted(self, category: DiseaseCategory) -> None:
        """Every declared category must be usable."""
        assert factories.build_case_type(disease_category=category) is not None
