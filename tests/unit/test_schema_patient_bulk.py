"""Patient intake and the Excel/CSV bulk upload contract.

Phase 1 ships the contract, not the parser. These tests pin the shape the
Phase 2 ingestion service must produce.
"""

import pytest
from pydantic import ValidationError

from src.domain.enums import Gender
from src.domain.schemas.patient import (
    BulkUploadReport,
    BulkUploadRowError,
    PatientBulkUploadRow,
    PatientIntakeRequest,
    PatientResponse,
)


def _row(**overrides: object) -> PatientBulkUploadRow:
    """Build a valid bulk upload row."""
    data: dict[str, object] = {
        "row_number": 1,
        "mrn": "MRN-1",
        "full_name": "Test Patient",
        "gender": Gender.FEMALE,
        "age_years": 34,
    }
    data.update(overrides)
    return PatientBulkUploadRow(**data)  # type: ignore[arg-type]


class TestManualIntake:
    """The manually entered intake form."""

    def test_valid_intake_is_accepted(self) -> None:
        """A complete intake form passes."""
        request = PatientIntakeRequest(
            mrn="MRN-1",
            full_name="Test Patient",
            gender=Gender.MALE,
            age_years=40,
        )
        assert request.mrn == "MRN-1"

    def test_intake_without_age_signal_is_rejected(self) -> None:
        """A record with no age cannot be triaged safely."""
        with pytest.raises(ValidationError, match="either date_of_birth or age_years"):
            PatientIntakeRequest(mrn="MRN-2", full_name="Test Patient", gender=Gender.MALE)

    def test_mrn_is_upper_cased(self) -> None:
        """MRNs normalise for case-insensitive lookup."""
        request = PatientIntakeRequest(
            mrn="mrn-lower", full_name="Test Patient", gender=Gender.OTHER, age_years=5
        )
        assert request.mrn == "MRN-LOWER"


class TestBulkUploadRow:
    """One spreadsheet row."""

    def test_valid_row_is_accepted(self) -> None:
        """A well-formed row passes."""
        assert _row().row_number == 1

    def test_row_number_must_be_positive(self) -> None:
        """Spreadsheet rows are 1-indexed."""
        with pytest.raises(ValidationError):
            _row(row_number=0)

    def test_row_without_age_signal_is_rejected(self) -> None:
        """The same age rule applies to bulk rows."""
        with pytest.raises(ValidationError, match="either date_of_birth or age_years"):
            PatientBulkUploadRow(
                row_number=1,
                mrn="MRN-3",
                full_name="Test Patient",
                gender=Gender.MALE,
            )

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("penicillin;sulfa", ["penicillin", "sulfa"]),
            ("penicillin, sulfa", ["penicillin", "sulfa"]),
            ("penicillin", ["penicillin"]),
            ("", []),
            (None, []),
            ("a;;b", ["a", "b"]),
            ("  a ;  b  ", ["a", "b"]),
        ],
    )
    def test_allergy_cell_splitting(self, raw: str | None, expected: list[str]) -> None:
        """Spreadsheet cells hold delimited text, not lists.

        Both semicolons and commas appear in real uploads, and empty fragments
        must be dropped rather than becoming blank allergies.
        """
        assert _row(allergies_csv=raw).split_allergies() == expected

    def test_condition_cell_splitting(self) -> None:
        """Conditions split the same way as allergies."""
        row = _row(conditions_csv="diabetes; hypertension")
        assert row.split_conditions() == ["diabetes", "hypertension"]

    def test_complete_emergency_contact_is_accepted(self) -> None:
        """All three contact columns supplied together is valid."""
        row = _row(
            emergency_contact_name="Test Relative",
            emergency_contact_phone="+919876543210",
            emergency_contact_relationship="Spouse",
        )
        assert row.emergency_contact_name == "Test Relative"

    def test_absent_emergency_contact_is_accepted(self) -> None:
        """No contact columns at all is valid."""
        assert _row().emergency_contact_name is None

    @pytest.mark.parametrize(
        "partial",
        [
            {"emergency_contact_name": "Test Relative"},
            {"emergency_contact_phone": "+919876543210"},
            {"emergency_contact_name": "X Y", "emergency_contact_phone": "+919876543210"},
        ],
    )
    def test_partial_emergency_contact_is_rejected(self, partial: dict[str, str]) -> None:
        """A half-filled contact is unusable in an emergency."""
        with pytest.raises(ValidationError, match="supply all three or none"):
            _row(**partial)


class TestBulkUploadReport:
    """The per-file outcome report."""

    def test_fully_successful_report_is_accepted(self) -> None:
        """Every row accepted, no errors."""
        report = BulkUploadReport(total_rows=100, accepted=100, rejected=0)
        assert report.errors == []

    def test_report_with_errors_is_accepted(self) -> None:
        """Rejected rows are reported individually."""
        report = BulkUploadReport(
            total_rows=10,
            accepted=8,
            rejected=2,
            errors=[
                BulkUploadRowError(row_number=3, field="mrn", message="missing"),
                BulkUploadRowError(row_number=7, field="age_years", message="invalid"),
            ],
        )
        assert len(report.errors) == 2

    def test_counts_that_do_not_reconcile_are_rejected(self) -> None:
        """Accepted plus rejected must account for every row."""
        with pytest.raises(ValidationError, match="must equal"):
            BulkUploadReport(total_rows=10, accepted=8, rejected=1)

    def test_error_count_mismatch_is_rejected(self) -> None:
        """Every rejected row needs a reported reason.

        Otherwise a partial import would silently drop patients.
        """
        with pytest.raises(ValidationError, match="errors list has"):
            BulkUploadReport(total_rows=10, accepted=8, rejected=2, errors=[])

    def test_empty_file_report_is_accepted(self) -> None:
        """An empty upload is a valid, if useless, outcome."""
        report = BulkUploadReport(total_rows=0, accepted=0, rejected=0)
        assert report.total_rows == 0


class TestPatientResponseOmitsNationalId:
    """A patient response must never carry the National ID."""

    def test_response_has_no_national_id_field(self) -> None:
        """Neither plaintext nor ciphertext may appear on the response model."""
        field_names = set(PatientResponse.model_fields)
        assert "national_id" not in field_names
        assert "national_id_hash" not in field_names
