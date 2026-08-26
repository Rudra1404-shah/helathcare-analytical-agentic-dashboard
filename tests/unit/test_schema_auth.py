"""Authentication schema rules and credential-leak guards."""

import pytest
from pydantic import ValidationError

from src.domain.enums import UserRole
from src.domain.models.base import Address
from src.domain.schemas.auth import (
    CitizenRegistrationRequest,
    GovtLoginRequest,
    LoginRequest,
    PasswordChangeRequest,
    UserCreateRequest,
    UserResponse,
)

VALID_PASSWORD = "CorrectHorse9"
SAMPLE_ADDRESS = Address(
    line1="12 Test Street",
    city="Mumbai",
    state="Maharashtra",
    pincode="400001",
)


class TestPasswordPolicy:
    """Password strength is enforced on every schema that accepts one."""

    def test_strong_password_is_accepted(self) -> None:
        """A password with mixed case and a digit passes."""
        request = UserCreateRequest(
            email="user@example.com",
            password=VALID_PASSWORD,  # type: ignore[arg-type]
            role=UserRole.CITIZEN,
            full_name="Test User",
        )
        assert request.password.get_secret_value() == VALID_PASSWORD

    @pytest.mark.parametrize(
        ("password", "reason"),
        [
            ("Short1", "at least"),
            ("alllowercase9", "uppercase"),
            ("ALLUPPERCASE9", "lowercase"),
            ("NoDigitsHereAtAll", "digit"),
        ],
    )
    def test_weak_passwords_are_rejected(self, password: str, reason: str) -> None:
        """Each policy rule must actually reject its failure mode."""
        with pytest.raises(ValidationError, match=reason):
            UserCreateRequest(
                email="user@example.com",
                password=password,  # type: ignore[arg-type]
                role=UserRole.CITIZEN,
                full_name="Test User",
            )

    def test_password_change_enforces_policy_on_the_new_password(self) -> None:
        """A weak replacement password must be refused."""
        with pytest.raises(ValidationError, match="digit"):
            PasswordChangeRequest(
                current_password=VALID_PASSWORD,  # type: ignore[arg-type]
                new_password="NoDigitsHereAtAll",  # type: ignore[arg-type]
            )

    def test_password_change_with_strong_password_is_accepted(self) -> None:
        """A compliant replacement passes."""
        request = PasswordChangeRequest(
            current_password=VALID_PASSWORD,  # type: ignore[arg-type]
            new_password="AnotherGood9Pass",  # type: ignore[arg-type]
        )
        assert request.new_password.get_secret_value() == "AnotherGood9Pass"


class TestSecretsAreMasked:
    """Passwords must not appear in repr or serialised output."""

    def test_login_password_is_masked_in_repr(self) -> None:
        """A logged request object must not expose the credential."""
        request = LoginRequest(
            email="user@example.com",
            password=VALID_PASSWORD,  # type: ignore[arg-type]
        )
        assert VALID_PASSWORD not in repr(request)

    def test_registration_password_is_masked_in_repr(self) -> None:
        """The same guard applies to citizen registration."""
        request = CitizenRegistrationRequest(
            full_name="Test Citizen",
            phone="+919876543210",
            email="citizen@example.com",
            password=VALID_PASSWORD,  # type: ignore[arg-type]
            national_id="123456789012",
            address=SAMPLE_ADDRESS,
        )
        assert VALID_PASSWORD not in repr(request)


class TestUserResponseHasNoCredentials:
    """The response model must have nowhere to put a credential."""

    def test_response_has_no_password_field(self) -> None:
        """No field on UserResponse may hold a password or hash."""
        # Act
        field_names = set(UserResponse.model_fields)

        # Assert
        forbidden = {"password", "hashed_password", "hash", "secret"}
        assert not (field_names & forbidden), (
            f"UserResponse exposes credential fields: {field_names & forbidden}"
        )

    def test_response_rejects_a_password_field(self) -> None:
        """Even if a caller tries, there is no field to populate."""
        response = UserResponse.model_validate(
            {
                "_id": "507f1f77bcf86cd799439011",
                "email": "user@example.com",
                "role": UserRole.CITIZEN,
                "full_name": "Test User",
                "is_active": True,
                "is_verified": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "hashed_password": "$argon2id$leaked",
            }
        )
        assert "hashed_password" not in response.model_dump()

    def test_serialised_response_contains_no_hash(self) -> None:
        """Serialisation must not carry a credential through."""
        response = UserResponse.model_validate(
            {
                "_id": "507f1f77bcf86cd799439011",
                "email": "user@example.com",
                "role": UserRole.CITIZEN,
                "full_name": "Test User",
                "is_active": True,
                "is_verified": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
        assert "argon2" not in response.model_dump_json()


class TestRequestStrictness:
    """Unknown fields must fail rather than be silently dropped."""

    def test_unknown_field_is_rejected(self) -> None:
        """A typo in a form payload must surface, not vanish."""
        with pytest.raises(ValidationError):
            LoginRequest(
                email="user@example.com",
                password=VALID_PASSWORD,  # type: ignore[arg-type]
                remember_me=True,  # type: ignore[call-arg]
            )

    def test_invalid_email_is_rejected(self) -> None:
        """Login identity must be a valid address."""
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password=VALID_PASSWORD)  # type: ignore[arg-type]

    def test_govt_login_uses_official_email(self) -> None:
        """The ministry form names the field explicitly."""
        request = GovtLoginRequest(
            official_email="officer@ministry.example.com",
            password=VALID_PASSWORD,  # type: ignore[arg-type]
        )
        assert request.official_email == "officer@ministry.example.com"


class TestCitizenRegistration:
    """Citizen self-registration form rules."""

    def test_valid_registration_is_accepted(self) -> None:
        """A complete registration passes."""
        request = CitizenRegistrationRequest(
            full_name="Test Citizen",
            phone="+919876543210",
            email="citizen@example.com",
            password=VALID_PASSWORD,  # type: ignore[arg-type]
            national_id="123456789012",
            address=SAMPLE_ADDRESS,
        )
        assert request.national_id == "123456789012"

    def test_invalid_phone_is_rejected(self) -> None:
        """Phone numbers must be well formed."""
        with pytest.raises(ValidationError):
            CitizenRegistrationRequest(
                full_name="Test Citizen",
                phone="123",
                email="citizen@example.com",
                password=VALID_PASSWORD,  # type: ignore[arg-type]
                national_id="123456789012",
                address=SAMPLE_ADDRESS,
            )

    def test_malformed_pincode_is_rejected(self) -> None:
        """Indian PIN codes are exactly six digits."""
        with pytest.raises(ValidationError):
            Address(
                line1="12 Test Street",
                city="Mumbai",
                state="Maharashtra",
                pincode="4000",
            )

    def test_short_national_id_is_rejected(self) -> None:
        """A National ID that is too short is a data entry error."""
        with pytest.raises(ValidationError):
            CitizenRegistrationRequest(
                full_name="Test Citizen",
                phone="+919876543210",
                email="citizen@example.com",
                password=VALID_PASSWORD,  # type: ignore[arg-type]
                national_id="12",
                address=SAMPLE_ADDRESS,
            )
