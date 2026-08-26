"""The ``case_types`` collection: disease classification and triage priority.

Backs the Hospital Case Type Definition Form. A case type with
``is_notifiable`` set is one the outbreak-detection module watches for
anomalous clustering.

A case type with ``hospital_id`` of ``None`` is a national standard definition
available to every hospital; a non-null value scopes it to one hospital.
"""

from typing import ClassVar

import pymongo
from beanie import PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from src.domain.enums import DiseaseCategory, TriageLevel
from src.domain.models.base import TimestampedDocument
from src.domain.types import Icd10Code, ShortText

__all__ = ["CaseType"]


class CaseType(TimestampedDocument):
    """A named, ICD-10 coded, triage-rated kind of case."""

    hospital_id: PydanticObjectId | None = Field(
        default=None,
        description="Owning hospital, or None for a national standard definition.",
    )
    name: ShortText = Field(description="e.g. 'Acute Gastroenteritis'.")
    disease_category: DiseaseCategory
    icd10_code: Icd10Code
    triage_level: TriageLevel = Field(
        description="Clinical urgency, 1 (most urgent) through 4 (least urgent)."
    )
    description: str | None = Field(default=None, max_length=1000)
    is_notifiable: bool = Field(
        default=False,
        description="Whether this condition is reportable to the ministry and "
        "monitored for outbreak clustering.",
    )
    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "case_types"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("icd10_code", pymongo.ASCENDING)],
                unique=True,
                name="uq_case_types_hospital_icd10",
            ),
            IndexModel(
                [("disease_category", pymongo.ASCENDING), ("triage_level", pymongo.ASCENDING)],
                name="ix_case_types_category_triage",
            ),
            IndexModel([("is_notifiable", pymongo.ASCENDING)], name="ix_case_types_notifiable"),
        ]

    @property
    def is_national_standard(self) -> bool:
        """Return whether this definition is shared across all hospitals."""
        return self.hospital_id is None
