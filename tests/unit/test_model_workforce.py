"""Staff and doctor rules, including the role/category consistency guard."""

import pytest
from pydantic import ValidationError

from src.domain.enums import (
    MEDICAL_STAFF_ROLES,
    ShiftType,
    StaffCategory,
    StaffRole,
    StaffStatus,
)
from src.domain.models.base import ProtectedNationalId
from tests import factories


class TestStaffRoleCategory:
    """A role must belong to the category it is filed under."""

    @pytest.mark.parametrize("role", sorted(MEDICAL_STAFF_ROLES))
    def test_medical_roles_report_medical_category(self, role: StaffRole) -> None:
        """Every clinical role maps to MEDICAL."""
        assert role.category is StaffCategory.MEDICAL

    @pytest.mark.parametrize(
        "role",
        [r for r in StaffRole if r not in MEDICAL_STAFF_ROLES],
        ids=lambda r: r.value,
    )
    def test_support_roles_report_admin_support_category(self, role: StaffRole) -> None:
        """Every non-clinical role maps to ADMIN_SUPPORT."""
        assert role.category is StaffCategory.ADMIN_SUPPORT

    def test_mismatched_role_and_category_is_rejected(self) -> None:
        """A cleaner filed as medical staff would inflate clinical staffing counts."""
        with pytest.raises(ValidationError, match="belongs to category"):
            factories.build_support_staff(
                staff_category=StaffCategory.MEDICAL, registration_no="NUR-1"
            )

    def test_nurse_filed_as_support_is_rejected(self) -> None:
        """The reverse mismatch must fail too."""
        with pytest.raises(ValidationError, match="belongs to category"):
            factories.build_medical_staff(staff_category=StaffCategory.ADMIN_SUPPORT)


class TestMedicalStaffRegistration:
    """Clinical staff must carry a registration number."""

    def test_medical_staff_without_registration_is_rejected(self) -> None:
        """An unregistered nurse must not be recorded as practising."""
        with pytest.raises(ValidationError, match="registration_no is required"):
            factories.build_medical_staff(registration_no=None)

    def test_medical_staff_with_registration_is_accepted(self) -> None:
        """A registered nurse passes."""
        staff = factories.build_medical_staff()
        assert staff.registration_no == "NUR-55512"

    def test_support_staff_needs_no_registration(self) -> None:
        """Support roles have no council registration."""
        assert factories.build_support_staff().registration_no is None

    def test_registration_number_is_upper_cased(self) -> None:
        """Registration numbers normalise for consistent lookup."""
        staff = factories.build_medical_staff(registration_no="nur-abc")
        assert staff.registration_no == "NUR-ABC"


class TestStaffDefaults:
    """Assignment and lifecycle defaults."""

    def test_new_staff_are_active(self) -> None:
        """Staff start active."""
        assert factories.build_support_staff().status is StaffStatus.ACTIVE

    def test_shift_is_recorded(self) -> None:
        """The assigned shift is preserved."""
        assert factories.build_medical_staff().shift is ShiftType.NIGHT

    def test_invalid_phone_is_rejected(self) -> None:
        """Contact numbers must be well formed."""
        with pytest.raises(ValidationError):
            factories.build_support_staff(phone="abc")

    def test_national_id_is_stored_protected(self, test_settings: object) -> None:
        """A staff National ID must never be stored as plaintext."""
        # Arrange
        protected = ProtectedNationalId.protect("1234-5678-9012", test_settings)  # type: ignore[arg-type]

        # Act
        staff = factories.build_support_staff(national_id=protected)

        # Assert
        assert staff.national_id is not None
        assert "123456789012" not in staff.national_id.ciphertext
        assert len(staff.national_id.lookup_hash) == 64

    def test_protected_national_id_rejects_malformed_lookup_hash(self) -> None:
        """The lookup hash must be a real SHA-256 digest."""
        with pytest.raises(ValidationError):
            ProtectedNationalId(ciphertext="abc", lookup_hash="too-short")


class TestDoctor:
    """Doctor onboarding rules."""

    def test_valid_doctor_is_accepted(self) -> None:
        """The default doctor is valid and available."""
        doctor = factories.build_doctor()
        assert doctor.is_available is True
        assert doctor.max_daily_patients == 40

    def test_duplicate_shifts_are_rejected(self) -> None:
        """A duplicated shift would double-count availability."""
        with pytest.raises(ValidationError, match="must not contain duplicates"):
            factories.build_doctor(shifts=[ShiftType.MORNING, ShiftType.MORNING])

    def test_multiple_distinct_shifts_are_accepted(self) -> None:
        """A doctor may cover more than one shift."""
        doctor = factories.build_doctor(shifts=[ShiftType.MORNING, ShiftType.NIGHT])
        assert len(doctor.shifts) == 2

    def test_empty_shift_list_is_rejected(self) -> None:
        """A doctor with no shifts could never be rostered."""
        with pytest.raises(ValidationError):
            factories.build_doctor(shifts=[])

    def test_zero_max_daily_patients_is_rejected(self) -> None:
        """A cap of zero would make the doctor unusable for allocation."""
        with pytest.raises(ValidationError):
            factories.build_doctor(max_daily_patients=0)

    def test_absurd_max_daily_patients_is_rejected(self) -> None:
        """An implausible cap indicates a data entry error."""
        with pytest.raises(ValidationError):
            factories.build_doctor(max_daily_patients=5000)

    @pytest.mark.parametrize(
        "status",
        [StaffStatus.INACTIVE, StaffStatus.ON_LEAVE, StaffStatus.SUSPENDED],
    )
    def test_non_active_doctor_is_unavailable(self, status: StaffStatus) -> None:
        """Only active doctors may be allocated patients."""
        assert factories.build_doctor(status=status).is_available is False

    def test_licence_number_is_upper_cased(self) -> None:
        """Licence numbers normalise for consistent lookup."""
        doctor = factories.build_doctor(license_no="mci-001")
        assert doctor.license_no == "MCI-001"
