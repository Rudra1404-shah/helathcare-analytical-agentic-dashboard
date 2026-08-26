"""The ``complaints`` collection: citizen grievances and ministry investigation.

Backs the Citizen Public Complaint Form and the Government Complaint
Investigation & Resolution Form.

**Evidence is mandatory.** ``evidence`` is declared ``min_length=1``, so a
complaint with no photo or video cannot be constructed at all -- not through the
API, not through a script, not through a direct ``Complaint(...)`` call. The
same rule is repeated on the submission schema so the API rejects it earlier
with a friendlier message, but this model is the layer that cannot be bypassed.
"""

from datetime import datetime
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, HttpUrl, model_validator
from pymongo import IndexModel

from src.domain.enums import (
    CLOSED_INVESTIGATION_STATUSES,
    ActionTaken,
    ComplaintCategory,
    EvidenceType,
    InvestigationStatus,
)
from src.domain.models.base import TimestampedDocument, ValueObject, utcnow
from src.domain.types import NonEmptyStr, ShortText

__all__ = ["MIN_COMPLAINT_DESCRIPTION_LENGTH", "Complaint", "EvidenceAttachment"]

MIN_COMPLAINT_DESCRIPTION_LENGTH = 50
"""Citizens must describe the incident in at least this many characters."""

MAX_COMPLAINT_DESCRIPTION_LENGTH = 5000


class EvidenceAttachment(ValueObject):
    """A photo or video substantiating a complaint.

    Only the pointer and integrity metadata are stored; the media itself lives
    in the object store chosen in a later phase.
    """

    url: HttpUrl = Field(description="Location of the stored media file.")
    evidence_type: EvidenceType
    content_type: NonEmptyStr = Field(description="MIME type, e.g. 'image/jpeg'.")
    file_name: ShortText | None = Field(default=None)
    size_bytes: int = Field(ge=0)
    checksum_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Hex SHA-256 of the media, for tamper detection.",
    )
    uploaded_at: datetime = Field(default_factory=utcnow)


class Complaint(TimestampedDocument):
    """A citizen grievance against a hospital, and its investigation trail."""

    # --- Identity ---------------------------------------------------------- #
    complaint_number: str = Field(
        min_length=3,
        max_length=40,
        description="Human-facing complaint identifier, unique across the platform.",
    )
    citizen_user_id: PydanticObjectId = Field(description="Complainant's citizen account.")
    hospital_id: PydanticObjectId = Field(description="Hospital the complaint is against.")
    department_id: PydanticObjectId | None = Field(
        default=None, description="Department involved, when the citizen knows it."
    )

    # --- The complaint ----------------------------------------------------- #
    incident_at: datetime = Field(description="When the incident occurred.")
    category: ComplaintCategory
    description: str = Field(
        min_length=MIN_COMPLAINT_DESCRIPTION_LENGTH,
        max_length=MAX_COMPLAINT_DESCRIPTION_LENGTH,
        description="Citizen's account of the incident.",
    )
    evidence: list[EvidenceAttachment] = Field(
        min_length=1,
        description="MANDATORY. At least one photo or video is required to file.",
    )

    # --- Investigation ----------------------------------------------------- #
    investigation_status: InvestigationStatus = Field(default=InvestigationStatus.SUBMITTED)
    assigned_officer_id: PydanticObjectId | None = Field(
        default=None, description="Ministry officer running the inquiry."
    )
    hospital_explanation: str | None = Field(default=None, max_length=5000)
    action_taken: ActionTaken | None = Field(default=None)
    closure_remarks: str | None = Field(default=None, max_length=5000)
    closed_at: datetime | None = Field(default=None)

    class Settings:
        """Beanie collection configuration."""

        name = "complaints"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("complaint_number", pymongo.ASCENDING)],
                unique=True,
                name="uq_complaints_number",
            ),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("investigation_status", pymongo.ASCENDING)],
                name="ix_complaints_hospital_status",
            ),
            IndexModel([("citizen_user_id", pymongo.ASCENDING)], name="ix_complaints_citizen"),
            IndexModel(
                [("category", pymongo.ASCENDING), ("incident_at", pymongo.DESCENDING)],
                name="ix_complaints_category_incident",
            ),
            IndexModel([("investigation_status", pymongo.ASCENDING)], name="ix_complaints_status"),
        ]

    @model_validator(mode="after")
    def _validate_evidence_present(self) -> Self:
        """Reassert the mandatory-evidence rule with a domain-specific message.

        ``min_length=1`` on the field already blocks an empty list. This
        validator exists so the failure reads as a policy violation rather than
        a generic length error, and so the rule survives any future refactor
        that loosens the field constraint.
        """
        if not self.evidence:
            msg = (
                "a complaint cannot be filed without evidence: at least one "
                "photo or video attachment is mandatory"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_incident_not_in_future(self) -> Self:
        """An incident cannot be reported before it happens."""
        if self.incident_at > utcnow():
            msg = "incident_at cannot be in the future"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_closure_details(self) -> Self:
        """A closed investigation must record the decision and the reasoning."""
        is_closed = self.investigation_status in CLOSED_INVESTIGATION_STATUSES
        if not is_closed:
            return self

        if self.action_taken is None:
            msg = (
                f"action_taken is required when investigation_status is {self.investigation_status}"
            )
            raise ValueError(msg)
        if not self.closure_remarks:
            msg = (
                f"closure_remarks are required when investigation_status is "
                f"{self.investigation_status}"
            )
            raise ValueError(msg)
        return self

    @property
    def is_closed(self) -> bool:
        """Return whether the investigation has concluded."""
        return self.investigation_status in CLOSED_INVESTIGATION_STATUSES

    @property
    def evidence_count(self) -> int:
        """Return how many attachments substantiate this complaint."""
        return len(self.evidence)
