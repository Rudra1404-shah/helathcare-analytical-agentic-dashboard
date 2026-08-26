"""User model rules: password storage and role scoping."""

import pytest
from pydantic import ValidationError

from src.domain.enums import UserRole
from src.domain.models.user import User
from tests import factories


class TestPasswordStorage:
    """A plaintext password must never reach the users collection."""

    def test_argon2_hash_is_accepted(self) -> None:
        """The normal path stores an Argon2 hash."""
        user = factories.build_user()
        assert user.hashed_password.startswith("$argon2")

    def test_plaintext_password_is_rejected(self) -> None:
        """Assigning a plaintext password must fail loudly.

        This is the guard against a caller wiring the raw form field straight
        into the document.
        """
        with pytest.raises(ValidationError, match="must be an Argon2 hash"):
            factories.build_user(hashed_password="hunter2")

    def test_bcrypt_hash_is_rejected(self) -> None:
        """Only Argon2 is accepted, so the algorithm cannot silently downgrade."""
        with pytest.raises(ValidationError, match="must be an Argon2 hash"):
            factories.build_user(hashed_password="$2b$12$abcdefghijklmnopqrstuv")

    def test_password_cannot_be_downgraded_after_construction(self) -> None:
        """Assignment is validated too, so mutation cannot bypass the rule."""
        user = factories.build_user()
        with pytest.raises(ValidationError):
            user.hashed_password = "plaintext"


class TestRoleScoping:
    """Hospital-scoped roles need a hospital; others must not have one."""

    @pytest.mark.parametrize("role", [UserRole.HOSPITAL_ADMIN, UserRole.HOSPITAL_STAFF])
    def test_hospital_roles_require_a_hospital_id(self, role: UserRole) -> None:
        """A hospital admin with no hospital could not be authorised against anything."""
        with pytest.raises(ValidationError, match="hospital_id is required"):
            factories.build_user(role=role, hospital_id=None)

    @pytest.mark.parametrize("role", [UserRole.GOVT_ADMIN, UserRole.CITIZEN])
    def test_non_hospital_roles_reject_a_hospital_id(self, role: UserRole) -> None:
        """A citizen scoped to one hospital would be an authorisation bug."""
        with pytest.raises(ValidationError, match="must not be set"):
            factories.build_user(role=role, hospital_id=factories.object_id())

    def test_doctor_requires_a_doctor_id(self) -> None:
        """A doctor account must point at its clinical record."""
        with pytest.raises(ValidationError, match="doctor_id is required"):
            factories.build_user(role=UserRole.DOCTOR, hospital_id=factories.object_id())

    def test_valid_doctor_account_is_accepted(self) -> None:
        """A fully linked doctor account passes."""
        user = factories.build_user(
            role=UserRole.DOCTOR,
            hospital_id=factories.object_id(),
            doctor_id=factories.object_id(),
        )
        assert user.role is UserRole.DOCTOR

    def test_citizen_account_is_accepted(self) -> None:
        """The default citizen account is valid."""
        assert factories.build_user().role is UserRole.CITIZEN

    def test_hospital_admin_account_is_accepted(self) -> None:
        """A hospital admin with a hospital is valid."""
        assert factories.build_hospital_user().hospital_id is not None


class TestUserDefaults:
    """Account lifecycle defaults."""

    def test_new_account_is_active_but_unverified(self) -> None:
        """Accounts start usable but unverified."""
        user = factories.build_user()
        assert user.is_active is True
        assert user.is_verified is False
        assert user.last_login_at is None

    def test_invalid_email_is_rejected(self) -> None:
        """Login identity must be a real address."""
        with pytest.raises(ValidationError):
            factories.build_user(email="not-an-email")

    def test_invalid_phone_is_rejected(self) -> None:
        """Phone numbers must match the E.164-style pattern."""
        with pytest.raises(ValidationError):
            factories.build_user(phone="12")

    def test_valid_phone_is_accepted(self) -> None:
        """A well-formed number passes."""
        user = factories.build_user(phone="+919876543210")
        assert user.phone == "+919876543210"

    def test_timestamps_are_populated(self) -> None:
        """Every document carries creation and update times."""
        user = factories.build_user()
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_touch_advances_updated_at(self) -> None:
        """touch() re-stamps the update time ahead of a write."""
        # Arrange
        user = factories.build_user()
        original = user.updated_at

        # Act
        user.touch()

        # Assert
        assert user.updated_at >= original


class TestUserRequiredFields:
    """Missing required fields must fail."""

    def test_missing_email_is_rejected(self) -> None:
        """An account with no login identity is unusable."""
        with pytest.raises(ValidationError):
            User(  # type: ignore[call-arg]
                hashed_password="$argon2id$v=19$m=1,t=1,p=1$abc$abc",
                role=UserRole.CITIZEN,
                full_name="No Email",
            )

    def test_short_name_is_rejected(self) -> None:
        """A one-character name is almost certainly a data entry error."""
        with pytest.raises(ValidationError):
            factories.build_user(full_name="X")
