"""Shared FastAPI dependencies: authentication, authorisation, and paging.

Authorisation is decided from the signed token claims and then re-checked
against the stored account, so deactivating a user takes effect immediately
rather than at the end of their token's lifetime.

The hospital-scope guard lives here and in every service. That is deliberate:
the dependency gives a clean 403 at the edge, and the service check means a
future caller that bypasses the router -- a seed script, a scheduled job -- still
cannot read across hospitals.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from beanie import PydanticObjectId
from fastapi import Depends, Path, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import Settings, get_settings
from src.core.errors import AuthenticationError, PermissionDeniedError
from src.core.tokens import TokenError, decode_access_token
from src.domain.enums import UserRole
from src.domain.models import User
from src.domain.models.user import HOSPITAL_SCOPED_ROLES
from src.domain.schemas.common import PageMeta

__all__ = [
    "CurrentUser",
    "GovtAdmin",
    "HospitalActor",
    "HospitalAdmin",
    "HospitalPath",
    "Pagination",
    "Paging",
    "SettingsDep",
    "current_user",
    "require_roles",
]

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50

_bearer = HTTPBearer(auto_error=False, description="Portal access token.")


def settings_dependency() -> Settings:
    """Return the process settings, overridable in tests via dependency override."""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dependency)]


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
) -> User:
    """Resolve the authenticated account from the ``Authorization`` header.

    Raises:
        AuthenticationError: If the token is missing, invalid, expired, or
            names an account that no longer exists or has been deactivated.
    """
    if credentials is None or not credentials.credentials:
        msg = "this endpoint requires a signed-in account"
        raise AuthenticationError(msg)

    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user = await User.get(claims.user_id)
    if user is None:
        msg = "the account this token was issued for no longer exists"
        raise AuthenticationError(msg)
    if not user.is_active:
        msg = "this account has been deactivated; contact your administrator"
        raise AuthenticationError(msg)

    # A token minted before a role or hospital change must not keep the old
    # privileges, so the stored account is the authority, not the claim.
    if user.role is not claims.role or user.hospital_id != claims.hospital_id:
        msg = "this token no longer matches the account; sign in again"
        raise AuthenticationError(msg)

    request.state.actor = user
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*allowed: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency that admits only the given roles.

    Returns:
        A FastAPI dependency yielding the account when its role is allowed.
    """

    async def guard(user: CurrentUser) -> User:
        if user.role not in allowed:
            permitted = ", ".join(sorted(role.value for role in allowed))
            msg = f"role {user.role} may not use this endpoint; it requires one of: {permitted}"
            raise PermissionDeniedError(msg)
        return user

    return guard


GovtAdmin = Annotated[User, Depends(require_roles(UserRole.GOVT_ADMIN))]
"""A Health Ministry account."""

HospitalAdmin = Annotated[
    User, Depends(require_roles(UserRole.GOVT_ADMIN, UserRole.HOSPITAL_ADMIN))
]
"""An account that may change a hospital's own configuration."""

HospitalActor = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.GOVT_ADMIN,
            UserRole.HOSPITAL_ADMIN,
            UserRole.HOSPITAL_STAFF,
            UserRole.DOCTOR,
        )
    ),
]
"""Any account entitled to work inside a hospital's operational modules."""


async def hospital_from_path(
    hospital_id: Annotated[PydanticObjectId, Path(description="Hospital the record belongs to.")],
    user: CurrentUser,
) -> PydanticObjectId:
    """Validate that a hospital-scoped actor is addressing their own hospital.

    Raises:
        PermissionDeniedError: If the path names a different hospital.
    """
    if user.role in HOSPITAL_SCOPED_ROLES and user.hospital_id != hospital_id:
        msg = (
            "this account is scoped to a different hospital; it cannot read or "
            "write records belonging to another"
        )
        raise PermissionDeniedError(msg)
    return hospital_id


HospitalPath = Annotated[PydanticObjectId, Depends(hospital_from_path)]


@dataclass(frozen=True)
class Pagination:
    """A validated page request, expressed as an offset for the query layer."""

    page: int
    limit: int

    @property
    def skip(self) -> int:
        """Return how many records to skip to reach this page."""
        return (self.page - 1) * self.limit

    def meta(self, total: int) -> PageMeta:
        """Build the response metadata for a page of ``total`` matches."""
        return PageMeta(total=total, page=self.page, limit=self.limit)


def paging(
    page: Annotated[int, Query(ge=1, description="1-indexed page number.")] = 1,
    limit: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Records per page.")
    ] = DEFAULT_PAGE_SIZE,
) -> Pagination:
    """Resolve the page query parameters shared by every list endpoint."""
    return Pagination(page=page, limit=limit)


Paging = Annotated[Pagination, Depends(paging)]
