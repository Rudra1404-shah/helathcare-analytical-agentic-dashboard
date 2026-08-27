"""The ``users`` collection: authentication and authorisation for all portals."""

from datetime import datetime
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import EmailStr, Field, field_validator, model_validator
from pymongo import IndexModel

from src.domain.enums import UserRole
from src.domain.models.base import Address, ProtectedNationalId, TimestampedDocument
from src.domain.types import ARGON2_HASH_PREFIX, PersonName, PhoneNumber

__all__ = ["HOSPITAL_SCOPED_ROLES", "User"]

HOSPITAL_SCOPED_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.HOSPITAL_ADMIN, UserRole.HOSPITAL_STAFF, UserRole.DOCTOR}
)
"""Roles that only make sense in the context of a specific hospital."""


class User(TimestampedDocument):
    """An account on any of the three portals.

    A single collection backs Government, Hospital, and Citizen logins; the
    ``role`` field decides which portal the account belongs to and which
    ownership link is required.

    Passwords are stored only as Argon2 hashes -- see
    :func:`src.core.security.hash_password`. The plaintext never reaches this
    document, and a validator refuses anything that is not an Argon2 hash.
    """

    email: EmailStr = Field(description="Login identity; unique across the platform.")
    hashed_password: str = Field(description="Argon2 encoded password hash.")
    role: UserRole = Field(description="Authorisation role.")
    full_name: PersonName
    phone: PhoneNumber | None = Field(default=None)
    address: Address | None = Field(
        default=None, description="Postal address, captured on citizen registration."
    )

    # --- Protected identity ------------------------------------------------ #
    national_id: ProtectedNationalId | None = Field(
        default=None,
        description="Encrypted National ID plus deterministic lookup hash. "
        "The join key that resolves a citizen account to every hospital-local "
        "patient record created for them. Plaintext is never stored, and "
        "UserResponse deliberately has nowhere to put it.",
    )

    # --- Ownership links -------------------------------------------------- #
    hospital_id: PydanticObjectId | None = Field(
        default=None,
        description="Required for hospital-scoped roles; forbidden otherwise.",
    )
    staff_id: PydanticObjectId | None = Field(
        default=None, description="Set when this account belongs to a staff member."
    )
    doctor_id: PydanticObjectId | None = Field(
        default=None, description="Set when this account belongs to a doctor."
    )

    # --- Lifecycle -------------------------------------------------------- #
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    last_login_at: datetime | None = Field(default=None)

    class Settings:
        """Beanie collection configuration."""

        name = "users"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("email", pymongo.ASCENDING)], unique=True, name="uq_users_email"),
            IndexModel([("role", pymongo.ASCENDING)], name="ix_users_role"),
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("role", pymongo.ASCENDING)],
                name="ix_users_hospital_role",
            ),
            IndexModel(
                [("national_id.lookup_hash", pymongo.ASCENDING)],
                name="ix_users_national_id_lookup",
                sparse=True,
            ),
        ]

    @field_validator("hashed_password")
    @classmethod
    def _reject_plaintext_password(cls, value: str) -> str:
        """Refuse to persist anything that is not an Argon2 hash.

        This is the last line of defence against a caller accidentally assigning
        a plaintext password to the field.
        """
        if not value.startswith(ARGON2_HASH_PREFIX):
            msg = (
                "hashed_password must be an Argon2 hash produced by "
                "src.core.security.hash_password; plaintext is never stored"
            )
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_role_scoping(self) -> Self:
        """Enforce that hospital-scoped roles carry a hospital, and others do not."""
        if self.role in HOSPITAL_SCOPED_ROLES and self.hospital_id is None:
            msg = f"hospital_id is required for role {self.role}"
            raise ValueError(msg)
        if self.role not in HOSPITAL_SCOPED_ROLES and self.hospital_id is not None:
            msg = f"hospital_id must not be set for role {self.role}"
            raise ValueError(msg)
        if self.role is UserRole.DOCTOR and self.doctor_id is None:
            msg = "doctor_id is required for role DOCTOR"
            raise ValueError(msg)
        return self
