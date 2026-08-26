"""Department Registration Form schemas."""

from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import ShortText

__all__ = ["DepartmentCreateRequest", "DepartmentResponse", "DepartmentUpdateRequest"]


class DepartmentCreateRequest(RequestSchema):
    """Department Registration Form."""

    name: ShortText = Field(description="Department name, e.g. 'Cardiology'.")
    code: str = Field(min_length=2, max_length=20, description="Unique within the hospital.")
    floor: str | None = Field(default=None, max_length=30)
    wing: str | None = Field(default=None, max_length=50)
    hod_doctor_id: PydanticObjectId | None = Field(default=None)
    bed_count: int = Field(default=0, ge=0)


class DepartmentUpdateRequest(RequestSchema):
    """Partial update to a department. The code is immutable once registered."""

    name: ShortText | None = Field(default=None)
    floor: str | None = Field(default=None, max_length=30)
    wing: str | None = Field(default=None, max_length=50)
    hod_doctor_id: PydanticObjectId | None = Field(default=None)
    bed_count: int | None = Field(default=None, ge=0)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class DepartmentResponse(IdentifiedResponse):
    """A department as returned by the API."""

    hospital_id: PydanticObjectId
    name: str
    code: str
    floor: str | None = None
    wing: str | None = None
    hod_doctor_id: PydanticObjectId | None = None
    bed_count: int
    is_active: bool
