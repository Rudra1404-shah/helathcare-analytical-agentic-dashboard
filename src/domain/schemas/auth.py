"""Authentication and account schemas for all three portals.

Covers the Government Master Login Form, the Citizen Registration & Login Form,
and the shared user representation.

:class:`UserResponse` deliberately has no password field of any kind. A hash
cannot leak through a response model that has nowhere to put it.
"""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import EmailStr, Field, SecretStr, field_validator

from src.domain.enums import UserRole
from src.domain.models.base import Address
from src.domain.schemas.common import IdentifiedResponse, RequestSchema, ResponseSchema
from src.domain.types import PersonName, PhoneNumber

__all__ = [
    "MIN_PASSWORD_LENGTH",
    "CitizenRegistrationRequest",
    "GovtLoginRequest",
    "LoginRequest",
    "PasswordChangeRequest",
    "TokenResponse",
    "UserCreateRequest",
    "UserResponse",
]

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


def _validate_password_strength(password: SecretStr) -> SecretStr:
    """Reject passwords that lack character-class variety.

    Length alone is a weak signal for the short passwords citizens tend to
    choose, so a mix of cases and digits is required as well.
    """
    revealed = password.get_secret_value()
    if len(revealed) < MIN_PASSWORD_LENGTH:
        msg = f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        raise ValueError(msg)
    if not any(char.islower() for char in revealed):
        msg = "password must contain a lowercase letter"
        raise ValueError(msg)
    if not any(char.isupper() for char in revealed):
        msg = "password must contain an uppercase letter"
        raise ValueError(msg)
    if not any(char.isdigit() for char in revealed):
        msg = "password must contain a digit"
        raise ValueError(msg)
    return password


class LoginRequest(RequestSchema):
    """Credentials submitted on any portal login form."""

    email: EmailStr
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)


class GovtLoginRequest(RequestSchema):
    """Health Ministry master login."""

    official_email: EmailStr = Field(description="Ministry-issued official email address.")
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)


class UserCreateRequest(RequestSchema):
    """Create an account on behalf of a portal user."""

    email: EmailStr
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
    role: UserRole
    full_name: PersonName
    phone: PhoneNumber | None = Field(default=None)
    hospital_id: PydanticObjectId | None = Field(default=None)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: SecretStr) -> SecretStr:
        """Apply the platform password policy."""
        return _validate_password_strength(value)


class CitizenRegistrationRequest(RequestSchema):
    """Citizen self-registration form.

    ``national_id`` is accepted here as plaintext because the citizen is typing
    it in. It is encrypted before storage and never persisted as given -- see
    :meth:`src.domain.models.base.ProtectedNationalId.protect`.
    """

    full_name: PersonName
    phone: PhoneNumber
    email: EmailStr
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
    national_id: str = Field(
        min_length=6,
        max_length=32,
        description="Plaintext National ID; encrypted before storage.",
    )
    address: Address

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: SecretStr) -> SecretStr:
        """Apply the platform password policy."""
        return _validate_password_strength(value)


class PasswordChangeRequest(RequestSchema):
    """Change the password on an existing account."""

    current_password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: SecretStr) -> SecretStr:
        """Apply the platform password policy to the replacement password."""
        return _validate_password_strength(value)


class TokenResponse(ResponseSchema):
    """Issued access token."""

    access_token: str
    token_type: str = Field(default="bearer")
    expires_in_seconds: int = Field(gt=0)
    role: UserRole


class UserResponse(IdentifiedResponse):
    """A user account as returned by the API.

    Contains no password field. There is no code path that can serialise a
    credential through this model.
    """

    email: EmailStr
    role: UserRole
    full_name: str
    phone: str | None = None
    hospital_id: PydanticObjectId | None = None
    is_active: bool
    is_verified: bool
    last_login_at: datetime | None = None
