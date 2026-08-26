"""Staff intake schemas for both the admin/support and medical intake forms.

The two forms differ mainly in which roles they accept and whether a
registration number is required, so they are modelled as two request schemas
over one shared base -- and both resolve to the same ``staff`` collection.
"""

from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import ShiftType, StaffCategory, StaffRole, StaffStatus
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import PersonName, PhoneNumber, RegistrationNumber, ShortText

__all__ = [
    "AdminSupportStaffIntakeRequest",
    "MedicalStaffIntakeRequest",
    "StaffResponse",
    "StaffUpdateRequest",
]


class _StaffIntakeBase(RequestSchema):
    """Fields common to both staff intake forms."""

    full_name: PersonName
    employee_id: str = Field(min_length=1, max_length=40)
    phone: PhoneNumber
    national_id: str | None = Field(
        default=None,
        min_length=6,
        max_length=32,
        description="Plaintext National ID; encrypted before storage.",
    )
    department_id: PydanticObjectId | None = Field(default=None)
    assigned_ward_area: ShortText | None = Field(default=None)
    shift: ShiftType = Field(default=ShiftType.GENERAL)
    status: StaffStatus = Field(default=StaffStatus.ACTIVE)


class AdminSupportStaffIntakeRequest(_StaffIntakeBase):
    """Admin & Support Staff Intake Form.

    Accepts only ADMIN_SUPPORT roles: Cleaner, Security, Driver, Desk Admin,
    Liftman, Helper, Admin, Accountant.
    """

    role: StaffRole

    @model_validator(mode="after")
    def _validate_role_is_admin_support(self) -> Self:
        """Reject a medical role submitted on the admin/support form."""
        if self.role.category is not StaffCategory.ADMIN_SUPPORT:
            msg = (
                f"{self.role} is a {self.role.category} role and cannot be filed "
                f"on the Admin & Support Staff intake form"
            )
            raise ValueError(msg)
        return self


class MedicalStaffIntakeRequest(_StaffIntakeBase):
    """Medical Staff Intake Form.

    Accepts only MEDICAL roles: Staff Nurse, Matron, Lab Assistant, Ward Boy,
    Compounder. A nursing or pharmacy registration number is mandatory.
    """

    role: StaffRole
    registration_no: RegistrationNumber = Field(
        description="Nursing or pharmacy registration number; mandatory for medical staff."
    )
    is_emergency_on_call: bool = Field(default=False)

    @model_validator(mode="after")
    def _validate_role_is_medical(self) -> Self:
        """Reject an admin/support role submitted on the medical form."""
        if self.role.category is not StaffCategory.MEDICAL:
            msg = (
                f"{self.role} is a {self.role.category} role and cannot be filed "
                f"on the Medical Staff intake form"
            )
            raise ValueError(msg)
        return self


class StaffUpdateRequest(RequestSchema):
    """Partial update to a staff record."""

    phone: PhoneNumber | None = Field(default=None)
    department_id: PydanticObjectId | None = Field(default=None)
    assigned_ward_area: ShortText | None = Field(default=None)
    shift: ShiftType | None = Field(default=None)
    is_emergency_on_call: bool | None = Field(default=None)
    status: StaffStatus | None = Field(default=None)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        """Reject an update that would change nothing."""
        if not self.model_dump(exclude_none=True):
            msg = "at least one field must be provided to update"
            raise ValueError(msg)
        return self


class StaffResponse(IdentifiedResponse):
    """A staff record as returned by the API.

    The National ID is absent: responses never carry it, encrypted or otherwise.
    """

    hospital_id: PydanticObjectId
    employee_id: str
    full_name: str
    phone: str
    staff_category: StaffCategory
    role: StaffRole
    registration_no: str | None = None
    department_id: PydanticObjectId | None = None
    assigned_ward_area: str | None = None
    shift: ShiftType
    is_emergency_on_call: bool
    status: StaffStatus
