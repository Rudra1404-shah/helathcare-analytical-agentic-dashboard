"""Public Complaint Form schemas.

**Evidence is mandatory to submit.** ``evidence`` is declared ``min_length=1``
and re-checked by a validator that states the rule in policy terms. This is the
*first* of two enforcement layers; the stored
:class:`~src.domain.models.complaint.Complaint` enforces it again so the rule
holds even for code paths that never touch this schema.
"""

from datetime import datetime
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, HttpUrl, model_validator

from src.domain.enums import (
    ActionTaken,
    ComplaintCategory,
    EvidenceType,
    InvestigationStatus,
)
from src.domain.models.complaint import (
    MAX_COMPLAINT_DESCRIPTION_LENGTH,
    MIN_COMPLAINT_DESCRIPTION_LENGTH,
    EvidenceAttachment,
)
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import NonEmptyStr, ShortText

__all__ = [
    "ComplaintResponse",
    "ComplaintSubmissionRequest",
    "EvidenceAttachmentRequest",
]

_EXPECTED_CONTENT_TYPE_PREFIX: dict[EvidenceType, str] = {
    EvidenceType.PHOTO: "image/",
    EvidenceType.VIDEO: "video/",
}


class EvidenceAttachmentRequest(RequestSchema):
    """One photo or video uploaded with a complaint."""

    url: HttpUrl = Field(description="Location of the uploaded media.")
    evidence_type: EvidenceType
    content_type: NonEmptyStr = Field(description="MIME type, e.g. 'image/jpeg'.")
    file_name: ShortText | None = Field(default=None)
    size_bytes: int = Field(gt=0, description="Uploaded media must not be empty.")
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_content_type_matches_declared_kind(self) -> Self:
        """Reject a video filed as a photo, or vice versa.

        A mismatch here would break the evidence viewer in the ministry
        investigation form, which renders by declared type.
        """
        expected_prefix = _EXPECTED_CONTENT_TYPE_PREFIX[self.evidence_type]
        if not self.content_type.lower().startswith(expected_prefix):
            msg = (
                f"evidence_type {self.evidence_type} requires a content_type starting "
                f"with '{expected_prefix}', got '{self.content_type}'"
            )
            raise ValueError(msg)
        return self

    def to_attachment(self) -> EvidenceAttachment:
        """Convert to the stored embedded document."""
        return EvidenceAttachment(
            url=self.url,
            evidence_type=self.evidence_type,
            content_type=self.content_type,
            file_name=self.file_name,
            size_bytes=self.size_bytes,
            checksum_sha256=self.checksum_sha256,
        )


class ComplaintSubmissionRequest(RequestSchema):
    """Public Complaint Form submitted by a citizen."""

    hospital_id: PydanticObjectId = Field(description="Hospital the complaint is against.")
    department_id: PydanticObjectId | None = Field(default=None)
    incident_at: datetime = Field(description="When the incident occurred.")
    category: ComplaintCategory
    description: str = Field(
        min_length=MIN_COMPLAINT_DESCRIPTION_LENGTH,
        max_length=MAX_COMPLAINT_DESCRIPTION_LENGTH,
        description=(
            f"Account of the incident, at least {MIN_COMPLAINT_DESCRIPTION_LENGTH} characters."
        ),
    )
    evidence: list[EvidenceAttachmentRequest] = Field(
        min_length=1,
        description="MANDATORY. At least one photo or video is required to submit.",
    )

    @model_validator(mode="after")
    def _validate_evidence_present(self) -> Self:
        """State the mandatory-evidence rule as policy, not as a length error."""
        if not self.evidence:
            msg = (
                "a complaint cannot be submitted without evidence: at least one "
                "photo or video attachment is mandatory"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_incident_not_in_future(self) -> Self:
        """An incident cannot be reported before it happens."""
        now = datetime.now(self.incident_at.tzinfo)
        if self.incident_at > now:
            msg = "incident_at cannot be in the future"
            raise ValueError(msg)
        return self


class ComplaintResponse(IdentifiedResponse):
    """A complaint and its investigation trail as returned by the API."""

    complaint_number: str
    citizen_user_id: PydanticObjectId
    hospital_id: PydanticObjectId
    department_id: PydanticObjectId | None = None
    incident_at: datetime
    category: ComplaintCategory
    description: str
    evidence: list[EvidenceAttachment]
    investigation_status: InvestigationStatus
    assigned_officer_id: PydanticObjectId | None = None
    hospital_explanation: str | None = None
    action_taken: ActionTaken | None = None
    closure_remarks: str | None = None
    closed_at: datetime | None = None
