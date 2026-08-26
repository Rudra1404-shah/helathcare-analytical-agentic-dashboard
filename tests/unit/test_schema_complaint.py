"""Complaint submission schema: the API-facing half of the mandatory-evidence rule."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.enums import (
    ActionTaken,
    ComplaintCategory,
    EvidenceType,
    InvestigationStatus,
)
from src.domain.models.complaint import MIN_COMPLAINT_DESCRIPTION_LENGTH
from src.domain.schemas.complaint import (
    ComplaintSubmissionRequest,
    EvidenceAttachmentRequest,
)
from src.domain.schemas.govt import ComplaintInvestigationUpdateRequest
from tests import factories

PAST = datetime.now(UTC) - timedelta(days=2)


def _evidence(**overrides: object) -> EvidenceAttachmentRequest:
    """Build a valid photo evidence payload."""
    data: dict[str, object] = {
        "url": "https://storage.example.com/evidence/photo.jpg",
        "evidence_type": EvidenceType.PHOTO,
        "content_type": "image/jpeg",
        "size_bytes": 2048,
    }
    data.update(overrides)
    return EvidenceAttachmentRequest(**data)  # type: ignore[arg-type]


def _submission(**overrides: object) -> ComplaintSubmissionRequest:
    """Build a valid complaint submission payload."""
    data: dict[str, object] = {
        "hospital_id": factories.object_id(),
        "incident_at": PAST,
        "category": ComplaintCategory.BED_REFUSAL,
        "description": factories.VALID_COMPLAINT_DESCRIPTION,
        "evidence": [_evidence()],
    }
    data.update(overrides)
    return ComplaintSubmissionRequest(**data)  # type: ignore[arg-type]


class TestMandatoryEvidenceAtTheApiBoundary:
    """A complaint cannot be submitted without proof."""

    def test_submission_with_evidence_is_accepted(self) -> None:
        """The happy path: one attachment is enough."""
        assert len(_submission().evidence) == 1

    def test_submission_with_empty_evidence_is_rejected(self) -> None:
        """THE mandatory-evidence rule, enforced at the API boundary."""
        with pytest.raises(ValidationError) as exc_info:
            _submission(evidence=[])

        assert any(error["type"] == "too_short" for error in exc_info.value.errors())

    def test_submission_without_evidence_field_is_rejected(self) -> None:
        """Evidence has no default, so omitting it fails."""
        with pytest.raises(ValidationError) as exc_info:
            ComplaintSubmissionRequest(  # type: ignore[call-arg]
                hospital_id=factories.object_id(),
                incident_at=PAST,
                category=ComplaintCategory.HYGIENE,
                description=factories.VALID_COMPLAINT_DESCRIPTION,
            )

        assert any(error["type"] == "missing" for error in exc_info.value.errors())

    def test_both_layers_reject_missing_evidence(self) -> None:
        """The schema and the stored model must agree.

        Two independent layers enforce this rule, so loosening one does not
        silently open a path to an evidence-free complaint.
        """
        with pytest.raises(ValidationError):
            _submission(evidence=[])
        with pytest.raises(ValidationError):
            factories.build_complaint(evidence=[])


class TestEvidenceContentType:
    """A declared media kind must match its MIME type."""

    def test_photo_with_image_content_type_is_accepted(self) -> None:
        """The normal photo case passes."""
        assert _evidence().evidence_type is EvidenceType.PHOTO

    def test_video_with_video_content_type_is_accepted(self) -> None:
        """The normal video case passes."""
        evidence = _evidence(
            evidence_type=EvidenceType.VIDEO,
            content_type="video/mp4",
            url="https://storage.example.com/evidence/clip.mp4",
        )
        assert evidence.evidence_type is EvidenceType.VIDEO

    def test_photo_declared_with_video_content_type_is_rejected(self) -> None:
        """A mismatch would break the ministry's evidence viewer."""
        with pytest.raises(ValidationError, match="requires a content_type"):
            _evidence(evidence_type=EvidenceType.PHOTO, content_type="video/mp4")

    def test_video_declared_with_image_content_type_is_rejected(self) -> None:
        """The reverse mismatch fails too."""
        with pytest.raises(ValidationError, match="requires a content_type"):
            _evidence(evidence_type=EvidenceType.VIDEO, content_type="image/png")

    def test_zero_byte_evidence_is_rejected(self) -> None:
        """An empty file is not evidence."""
        with pytest.raises(ValidationError):
            _evidence(size_bytes=0)


class TestSubmissionRules:
    """Description length and incident timing."""

    def test_description_below_minimum_is_rejected(self) -> None:
        """Citizens must describe the incident in enough detail to investigate."""
        with pytest.raises(ValidationError):
            _submission(description="Too short.")

    def test_description_at_minimum_is_accepted(self) -> None:
        """The boundary is inclusive."""
        request = _submission(description="x" * MIN_COMPLAINT_DESCRIPTION_LENGTH)
        assert len(request.description) == MIN_COMPLAINT_DESCRIPTION_LENGTH

    def test_future_incident_is_rejected(self) -> None:
        """An incident cannot be reported before it happens."""
        future = datetime.now(UTC) + timedelta(days=1)
        with pytest.raises(ValidationError, match="cannot be in the future"):
            _submission(incident_at=future)

    def test_unknown_field_is_rejected(self) -> None:
        """A typo in the payload must surface rather than be dropped."""
        with pytest.raises(ValidationError):
            _submission(anonymous=True)

    def test_all_complaint_categories_are_accepted(self) -> None:
        """Every declared grievance category must be submittable."""
        for category in ComplaintCategory:
            assert _submission(category=category).category is category


class TestInvestigationUpdate:
    """The ministry's investigation form."""

    def test_moving_to_under_review_is_accepted(self) -> None:
        """An in-progress status needs no closure details."""
        request = ComplaintInvestigationUpdateRequest(
            investigation_status=InvestigationStatus.UNDER_REVIEW
        )
        assert request.action_taken is None

    def test_assigning_inquiry_without_officer_is_rejected(self) -> None:
        """An assigned inquiry must name who is running it."""
        with pytest.raises(ValidationError, match="assigned_officer_id is required"):
            ComplaintInvestigationUpdateRequest(
                investigation_status=InvestigationStatus.INQUIRY_ASSIGNED
            )

    def test_assigning_inquiry_with_officer_is_accepted(self) -> None:
        """A named officer satisfies the rule."""
        request = ComplaintInvestigationUpdateRequest(
            investigation_status=InvestigationStatus.INQUIRY_ASSIGNED,
            assigned_officer_id=factories.object_id(),
        )
        assert request.assigned_officer_id is not None

    @pytest.mark.parametrize(
        "status",
        [InvestigationStatus.ACTION_TAKEN, InvestigationStatus.DISMISSED],
    )
    def test_closing_without_action_is_rejected(self, status: InvestigationStatus) -> None:
        """Closure requires a recorded decision."""
        with pytest.raises(ValidationError, match="action_taken is required"):
            ComplaintInvestigationUpdateRequest(
                investigation_status=status, closure_remarks="Done."
            )

    @pytest.mark.parametrize(
        "status",
        [InvestigationStatus.ACTION_TAKEN, InvestigationStatus.DISMISSED],
    )
    def test_closing_without_remarks_is_rejected(self, status: InvestigationStatus) -> None:
        """Closure requires recorded reasoning."""
        with pytest.raises(ValidationError, match="closure_remarks are required"):
            ComplaintInvestigationUpdateRequest(
                investigation_status=status, action_taken=ActionTaken.FINE
            )

    def test_complete_closure_is_accepted(self) -> None:
        """A full closure passes."""
        request = ComplaintInvestigationUpdateRequest(
            investigation_status=InvestigationStatus.ACTION_TAKEN,
            action_taken=ActionTaken.FINE,
            closure_remarks="Fine of 50,000 levied.",
        )
        assert request.action_taken is ActionTaken.FINE
