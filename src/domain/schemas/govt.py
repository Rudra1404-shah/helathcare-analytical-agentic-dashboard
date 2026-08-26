"""Government (Health Ministry) portal schemas.

Covers the Zone/Area Management Form, accreditation changes made by the
ministry, and the Complaint Investigation & Resolution Form.
"""

from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import (
    CLOSED_INVESTIGATION_STATUSES,
    AccreditationStatus,
    ActionTaken,
    InvestigationStatus,
)
from src.domain.models.base import GeoLocation
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.schemas.hospital import GeoPointPayload
from src.domain.types import PersonName, ShortText

__all__ = [
    "ComplaintInvestigationUpdateRequest",
    "HospitalAccreditationUpdateRequest",
    "ZoneCreateRequest",
    "ZoneResponse",
    "ZoneUpdateRequest",
]


class ZoneCreateRequest(RequestSchema):
    """Zone/Area Management Form."""

    zone_code: str = Field(min_length=2, max_length=30)
    name: ShortText
    state: ShortText
    city: ShortText
    population_covered: int = Field(
        ge=0, description="Census population served, the denominator for per-capita rates."
    )
    centroid: GeoPointPayload | None = Field(default=None)


class ZoneUpdateRequest(RequestSchema):
    """Partial update to an existing zone. The zone code is immutable."""

    name: ShortText | None = Field(default=None)
    population_covered: int | None = Field(default=None, ge=0)
    centroid: GeoPointPayload | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class ZoneResponse(IdentifiedResponse):
    """A zone as returned by the API."""

    zone_code: str
    name: str
    state: str
    city: str
    population_covered: int
    centroid: GeoLocation | None = None
    is_active: bool


class HospitalAccreditationUpdateRequest(RequestSchema):
    """Ministry decision on a hospital's accreditation state."""

    accreditation_status: AccreditationStatus
    nodal_officer_id: PydanticObjectId | None = Field(default=None)
    nodal_officer_name: PersonName | None = Field(default=None)
    remarks: str | None = Field(default=None, max_length=2000)


class ComplaintInvestigationUpdateRequest(RequestSchema):
    """Complaint Investigation & Resolution Form.

    Closing an investigation requires both a decision and the reasoning behind
    it, mirroring the rule enforced on the stored complaint.
    """

    investigation_status: InvestigationStatus
    assigned_officer_id: PydanticObjectId | None = Field(default=None)
    hospital_explanation: str | None = Field(default=None, max_length=5000)
    action_taken: ActionTaken | None = Field(default=None)
    closure_remarks: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _validate_closure_details(self) -> Self:
        """Require a decision and remarks when closing the investigation."""
        if self.investigation_status not in CLOSED_INVESTIGATION_STATUSES:
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

    @model_validator(mode="after")
    def _require_officer_when_inquiry_assigned(self) -> Self:
        """An assigned inquiry must name the officer running it."""
        if (
            self.investigation_status is InvestigationStatus.INQUIRY_ASSIGNED
            and self.assigned_officer_id is None
        ):
            msg = "assigned_officer_id is required when status is INQUIRY_ASSIGNED"
            raise ValueError(msg)
        return self
