"""Complaint model rules, above all the mandatory-evidence requirement.

The platform's grievance mechanism depends on every complaint carrying proof.
These tests exist so that rule can never regress silently.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.enums import ActionTaken, EvidenceType, InvestigationStatus
from src.domain.models.complaint import (
    MIN_COMPLAINT_DESCRIPTION_LENGTH,
    Complaint,
    EvidenceAttachment,
)
from tests import factories


class TestMandatoryEvidence:
    """A complaint cannot exist without at least one photo or video."""

    def test_complaint_with_evidence_is_accepted(self) -> None:
        """The happy path: one attachment is enough to file."""
        # Arrange / Act
        complaint = factories.build_complaint()

        # Assert
        assert complaint.evidence_count == 1
        assert complaint.evidence[0].evidence_type is EvidenceType.PHOTO

    def test_complaint_with_empty_evidence_list_is_rejected(self) -> None:
        """THE mandatory-evidence rule: an empty list must not be storable."""
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc_info:
            factories.build_complaint(evidence=[])

        errors = exc_info.value.errors()
        assert any(error["type"] == "too_short" for error in errors), (
            f"expected a too_short error on evidence, got {errors}"
        )

    def test_complaint_with_missing_evidence_field_is_rejected(self) -> None:
        """Omitting evidence entirely must fail; it has no default."""
        # Arrange
        payload = {
            "complaint_number": "CMP-0002",
            "citizen_user_id": factories.object_id(),
            "hospital_id": factories.object_id(),
            "incident_at": factories.PAST_INCIDENT,
            "category": "NEGLIGENCE",
            "description": factories.VALID_COMPLAINT_DESCRIPTION,
        }

        # Act / Assert
        with pytest.raises(ValidationError) as exc_info:
            Complaint(**payload)  # type: ignore[arg-type]

        assert any(error["type"] == "missing" for error in exc_info.value.errors())

    def test_evidence_cannot_be_emptied_after_construction(self) -> None:
        """Reassigning an empty list must not bypass the rule.

        Beanie documents validate on assignment, so the rule holds for mutation
        as well as construction.
        """
        # Arrange
        complaint = factories.build_complaint()

        # Act / Assert
        with pytest.raises(ValidationError):
            complaint.evidence = []

    def test_multiple_evidence_attachments_are_accepted(self) -> None:
        """Citizens may attach both a photo and a video."""
        # Arrange
        video = factories.build_evidence(
            url="https://storage.example.test/evidence/clip.mp4",
            evidence_type=EvidenceType.VIDEO,
            content_type="video/mp4",
            file_name="clip.mp4",
        )

        # Act
        complaint = factories.build_complaint(evidence=[factories.build_evidence(), video])

        # Assert
        assert complaint.evidence_count == 2


class TestComplaintDescription:
    """Description length rules."""

    def test_description_at_minimum_length_is_accepted(self) -> None:
        """Exactly the minimum must pass; the boundary is inclusive."""
        # Arrange
        description = "x" * MIN_COMPLAINT_DESCRIPTION_LENGTH

        # Act
        complaint = factories.build_complaint(description=description)

        # Assert
        assert len(complaint.description) == MIN_COMPLAINT_DESCRIPTION_LENGTH

    def test_description_below_minimum_length_is_rejected(self) -> None:
        """One character short of the minimum must fail."""
        # Arrange
        description = "x" * (MIN_COMPLAINT_DESCRIPTION_LENGTH - 1)

        # Act / Assert
        with pytest.raises(ValidationError) as exc_info:
            factories.build_complaint(description=description)

        assert any(error["type"] == "string_too_short" for error in exc_info.value.errors())


class TestComplaintTiming:
    """Incidents cannot be reported before they happen."""

    def test_past_incident_is_accepted(self) -> None:
        """A complaint about a past incident is the normal case."""
        # Arrange / Act
        complaint = factories.build_complaint()

        # Assert
        assert complaint.incident_at < datetime.now(UTC)

    def test_future_incident_is_rejected(self) -> None:
        """A future incident date indicates a client clock error or bad data."""
        # Arrange
        future = datetime.now(UTC) + timedelta(days=1)

        # Act / Assert
        with pytest.raises(ValidationError, match="cannot be in the future"):
            factories.build_complaint(incident_at=future)


class TestInvestigationClosure:
    """Closing an investigation requires a decision and reasoning."""

    def test_open_complaint_needs_no_closure_details(self) -> None:
        """A newly submitted complaint has neither action nor remarks."""
        # Arrange / Act
        complaint = factories.build_complaint()

        # Assert
        assert complaint.investigation_status is InvestigationStatus.SUBMITTED
        assert complaint.is_closed is False
        assert complaint.action_taken is None

    @pytest.mark.parametrize(
        "status",
        [InvestigationStatus.ACTION_TAKEN, InvestigationStatus.DISMISSED],
    )
    def test_closing_without_action_taken_is_rejected(self, status: InvestigationStatus) -> None:
        """A closed investigation must record what was decided."""
        with pytest.raises(ValidationError, match="action_taken is required"):
            factories.build_complaint(
                investigation_status=status,
                closure_remarks="Investigation complete.",
            )

    @pytest.mark.parametrize(
        "status",
        [InvestigationStatus.ACTION_TAKEN, InvestigationStatus.DISMISSED],
    )
    def test_closing_without_remarks_is_rejected(self, status: InvestigationStatus) -> None:
        """A closed investigation must record why."""
        with pytest.raises(ValidationError, match="closure_remarks are required"):
            factories.build_complaint(
                investigation_status=status,
                action_taken=ActionTaken.WARNING,
            )

    def test_fully_closed_complaint_is_accepted(self) -> None:
        """A complete closure passes and reports itself as closed."""
        # Arrange / Act
        complaint = factories.build_complaint(
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.LICENSE_SUSPENSION,
            closure_remarks="Licence suspended for 30 days.",
        )

        # Assert
        assert complaint.is_closed is True
        assert complaint.action_taken is ActionTaken.LICENSE_SUSPENSION

    @pytest.mark.parametrize(
        "status",
        [
            InvestigationStatus.SUBMITTED,
            InvestigationStatus.UNDER_REVIEW,
            InvestigationStatus.INQUIRY_ASSIGNED,
        ],
    )
    def test_open_statuses_do_not_require_closure_details(
        self, status: InvestigationStatus
    ) -> None:
        """In-progress statuses must not demand closure fields."""
        complaint = factories.build_complaint(investigation_status=status)
        assert complaint.is_closed is False


class TestEvidenceAttachment:
    """Attachment-level integrity rules."""

    def test_negative_size_is_rejected(self) -> None:
        """A negative byte count is impossible."""
        with pytest.raises(ValidationError):
            factories.build_evidence(size_bytes=-1)

    def test_malformed_checksum_is_rejected(self) -> None:
        """A checksum that is not 64 hex characters is not SHA-256."""
        with pytest.raises(ValidationError):
            factories.build_evidence(checksum_sha256="not-a-sha256")

    def test_valid_checksum_is_accepted(self) -> None:
        """A well-formed SHA-256 digest passes."""
        # Arrange
        digest = "a" * 64

        # Act
        evidence = factories.build_evidence(checksum_sha256=digest)

        # Assert
        assert evidence.checksum_sha256 == digest

    def test_attachment_is_immutable(self) -> None:
        """Evidence is frozen so a stored attachment cannot be swapped in place."""
        # Arrange
        evidence = factories.build_evidence()

        # Act / Assert
        with pytest.raises(ValidationError):
            evidence.size_bytes = 1

    def test_non_url_is_rejected(self) -> None:
        """Evidence must point at a real location."""
        with pytest.raises(ValidationError):
            EvidenceAttachment(
                url="not-a-url",  # type: ignore[arg-type]
                evidence_type=EvidenceType.PHOTO,
                content_type="image/jpeg",
                size_bytes=100,
            )
