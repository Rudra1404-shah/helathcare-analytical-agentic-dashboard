"""Access token issuing and verification for all three portals.

Tokens are short-lived JWTs signed with a symmetric secret. The claims carry
everything the authorisation layer needs to make a decision without a database
round trip on every request: who the actor is, what role they hold, and -- for
hospital-scoped roles -- which hospital they belong to.

The ``hospital_id`` claim is what stops a hospital admin from reading another
hospital's patients. It is signed, so a client cannot edit it.

Nothing here reads the environment directly; callers pass a
:class:`~src.core.config.Settings` instance so tests can supply their own keys.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from src.core.config import Settings, get_settings
from src.domain.enums import UserRole

__all__ = ["TOKEN_TYPE", "TokenClaims", "create_access_token", "decode_access_token"]

TOKEN_TYPE: Final = "bearer"
"""Authorization scheme name returned alongside every issued token."""


class TokenClaims(BaseModel):
    """The verified contents of an access token."""

    model_config = ConfigDict(frozen=True)

    user_id: PydanticObjectId
    role: UserRole
    hospital_id: PydanticObjectId | None = None
    expires_at: datetime


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or badly signed."""


def create_access_token(
    user_id: PydanticObjectId,
    role: UserRole,
    hospital_id: PydanticObjectId | None = None,
    settings: Settings | None = None,
) -> tuple[str, int]:
    """Issue a signed access token.

    Args:
        user_id: The authenticated account.
        role: Authorisation role carried in the token.
        hospital_id: Owning hospital for hospital-scoped roles.
        settings: Optional settings override; defaults to the process settings.

    Returns:
        A ``(token, expires_in_seconds)`` pair.
    """
    active = settings or get_settings()
    ttl = active.access_token_ttl_seconds
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "hospital_id": str(hospital_id) if hospital_id is not None else None,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(
        payload,
        active.jwt_secret.get_secret_value(),
        algorithm=active.jwt_algorithm,
    )
    return token, ttl


def decode_access_token(token: str, settings: Settings | None = None) -> TokenClaims:
    """Verify a token's signature and expiry, returning its claims.

    Args:
        token: The raw JWT, without the ``Bearer`` prefix.
        settings: Optional settings override; defaults to the process settings.

    Returns:
        The verified claims.

    Raises:
        TokenError: If the token is expired, tampered with, or missing a claim
            the authorisation layer depends on.
    """
    active = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            active.jwt_secret.get_secret_value(),
            algorithms=[active.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        msg = "access token has expired; sign in again"
        raise TokenError(msg) from exc
    except jwt.InvalidTokenError as exc:
        msg = "access token is invalid"
        raise TokenError(msg) from exc

    return _claims_from_payload(payload)


def _claims_from_payload(payload: dict[str, Any]) -> TokenClaims:
    """Convert a verified JWT payload into typed claims."""
    raw_role = payload.get("role")
    if not isinstance(raw_role, str):
        msg = "access token carries no role claim"
        raise TokenError(msg)
    try:
        role = UserRole(raw_role)
    except ValueError as exc:
        msg = f"access token carries an unknown role '{raw_role}'"
        raise TokenError(msg) from exc

    raw_hospital = payload.get("hospital_id")
    try:
        user_id = PydanticObjectId(payload["sub"])
        hospital_id = PydanticObjectId(raw_hospital) if raw_hospital else None
    except (ValueError, TypeError) as exc:
        msg = "access token carries a malformed identifier"
        raise TokenError(msg) from exc

    return TokenClaims(
        user_id=user_id,
        role=role,
        hospital_id=hospital_id,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
