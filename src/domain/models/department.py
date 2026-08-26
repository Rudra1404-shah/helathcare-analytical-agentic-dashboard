"""The ``departments`` collection: the clinical unit registry within a hospital.

Backs the Hospital Department Registration Form.
"""

from typing import ClassVar

import pymongo
from beanie import PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from src.domain.models.base import TimestampedDocument
from src.domain.types import ShortText

__all__ = ["Department"]


class Department(TimestampedDocument):
    """A department or clinical unit inside one hospital.

    ``code`` is unique per hospital rather than globally, so two hospitals may
    both run a department coded ``CARD``.
    """

    hospital_id: PydanticObjectId = Field(description="Owning hospital.")
    name: ShortText = Field(description="Department name, e.g. 'Cardiology'.")
    code: str = Field(
        min_length=2,
        max_length=20,
        description="Short department code, unique within the hospital.",
    )
    floor: str | None = Field(default=None, max_length=30)
    wing: str | None = Field(default=None, max_length=50)
    hod_doctor_id: PydanticObjectId | None = Field(
        default=None, description="Head of Department; references a Doctor document."
    )
    bed_count: int = Field(default=0, ge=0, description="Beds allocated to this department.")
    is_active: bool = Field(default=True)

    class Settings:
        """Beanie collection configuration."""

        name = "departments"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("code", pymongo.ASCENDING)],
                unique=True,
                name="uq_departments_hospital_code",
            ),
            IndexModel([("hospital_id", pymongo.ASCENDING)], name="ix_departments_hospital"),
            IndexModel([("hod_doctor_id", pymongo.ASCENDING)], name="ix_departments_hod"),
        ]
