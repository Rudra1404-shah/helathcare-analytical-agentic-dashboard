"""Case Type Definition Form schemas."""

from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import DiseaseCategory, TriageLevel
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import Icd10Code, ShortText

__all__ = ["CaseTypeCreateRequest", "CaseTypeResponse", "CaseTypeUpdateRequest"]


class CaseTypeCreateRequest(RequestSchema):
    """Case Type Definition Form."""

    name: ShortText = Field(description="e.g. 'Acute Gastroenteritis'.")
    disease_category: DiseaseCategory
    icd10_code: Icd10Code = Field(description="ICD-10 code, e.g. 'A09' or 'J18.9'.")
    triage_level: TriageLevel = Field(description="1 (most urgent) through 4 (least urgent).")
    description: str | None = Field(default=None, max_length=1000)
    is_notifiable: bool = Field(
        default=False, description="Report to the ministry and monitor for outbreaks."
    )


class CaseTypeUpdateRequest(RequestSchema):
    """Partial update. The ICD-10 code is immutable once defined."""

    name: ShortText | None = Field(default=None)
    disease_category: DiseaseCategory | None = Field(default=None)
    triage_level: TriageLevel | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1000)
    is_notifiable: bool | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class CaseTypeResponse(IdentifiedResponse):
    """A case type as returned by the API."""

    hospital_id: PydanticObjectId | None = None
    name: str
    disease_category: DiseaseCategory
    icd10_code: str
    triage_level: TriageLevel
    description: str | None = None
    is_notifiable: bool
    is_active: bool
