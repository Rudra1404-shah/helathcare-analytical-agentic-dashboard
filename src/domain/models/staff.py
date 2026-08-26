"""The ``staff`` collection: admin/support and medical support workforce.

Backs two hospital forms -- the **Admin & Support Staff Intake Form** and the
**Medical Staff Intake Form**. They share roughly eighty percent of their
fields, so one collection carries both, discriminated by ``staff_category``.
Doctors are deliberately *not* here; they carry council licences,
specialisations, and patient caps, and live in their own collection.
"""

from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, model_validator
from pymongo import IndexModel

from src.domain.enums import ShiftType, StaffCategory, StaffRole, StaffStatus
from src.domain.models.base import ProtectedNationalId, TimestampedDocument
from src.domain.types import PersonName, PhoneNumber, RegistrationNumber, ShortText

__all__ = ["Staff"]


class Staff(TimestampedDocument):
    """A non-doctor employee of a hospital."""

    hospital_id: PydanticObjectId = Field(description="Employing hospital.")
    employee_id: str = Field(
        min_length=1,
        max_length=40,
        description="Hospital-issued employee number, unique within the hospital.",
    )
    full_name: PersonName
    phone: PhoneNumber

    # --- Protected identity ------------------------------------------------ #
    national_id: ProtectedNationalId | None = Field(
        default=None,
        description="Encrypted National ID plus deterministic lookup hash. "
        "Plaintext is never stored.",
    )

    # --- Role -------------------------------------------------------------- #
    staff_category: StaffCategory = Field(description="ADMIN_SUPPORT or MEDICAL.")
    role: StaffRole = Field(description="Concrete job role; must match staff_category.")
    registration_no: RegistrationNumber | None = Field(
        default=None,
        description="Nursing or pharmacy registration number; required for MEDICAL staff.",
    )

    # --- Assignment -------------------------------------------------------- #
    department_id: PydanticObjectId | None = Field(
        default=None, description="Assigned department, where applicable."
    )
    assigned_ward_area: ShortText | None = Field(
        default=None, description="Ward or area this staff member covers."
    )
    shift: ShiftType = Field(default=ShiftType.GENERAL)
    is_emergency_on_call: bool = Field(default=False)
    status: StaffStatus = Field(default=StaffStatus.ACTIVE)

    class Settings:
        """Beanie collection configuration."""

        name = "staff"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("employee_id", pymongo.ASCENDING)],
                unique=True,
                name="uq_staff_hospital_employee",
            ),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("staff_category", pymongo.ASCENDING)],
                name="ix_staff_hospital_category",
            ),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("shift", pymongo.ASCENDING)],
                name="ix_staff_hospital_shift",
            ),
            IndexModel([("department_id", pymongo.ASCENDING)], name="ix_staff_department"),
            IndexModel(
                [("national_id.lookup_hash", pymongo.ASCENDING)],
                name="ix_staff_national_id_lookup",
                sparse=True,
            ),
        ]

    @model_validator(mode="after")
    def _validate_role_matches_category(self) -> Self:
        """Reject a role that does not belong to the declared category.

        Without this, a 'CLEANER' could be filed as MEDICAL staff and would then
        appear in clinical staffing counts.
        """
        if self.role.category is not self.staff_category:
            msg = (
                f"role {self.role} belongs to category {self.role.category}, "
                f"but staff_category is {self.staff_category}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_medical_registration(self) -> Self:
        """Require a registration number for medical staff."""
        if self.staff_category is StaffCategory.MEDICAL and not self.registration_no:
            msg = "registration_no is required for MEDICAL staff"
            raise ValueError(msg)
        return self
