"""Authentication endpoints for all three portals.

The Government master login is a separate endpoint from the general one because
it pins the expected role: a citizen who has somehow learned a ministry URL
still cannot sign in there, and the failure is indistinguishable from a wrong
password so the endpoint cannot be used to probe which accounts are ministry
accounts.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, status

from src.api.deps import CurrentUser, GovtAdmin, SettingsDep
from src.domain.enums import UserRole
from src.domain.schemas.auth import (
    CitizenRegistrationRequest,
    GovtLoginRequest,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from src.domain.schemas.common import ApiResponse
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(
    request: Annotated[LoginRequest, Body()],
    settings: SettingsDep,
) -> ApiResponse[TokenResponse]:
    """Sign in to the hospital or citizen portal."""
    user = await auth_service.authenticate(
        email=request.email,
        password=request.password.get_secret_value(),
        settings=settings,
    )
    return ApiResponse.ok(auth_service.issue_token(user, settings))


@router.post("/govt/login", response_model=ApiResponse[TokenResponse])
async def govt_login(
    request: Annotated[GovtLoginRequest, Body()],
    settings: SettingsDep,
) -> ApiResponse[TokenResponse]:
    """Health Ministry master login."""
    user = await auth_service.authenticate(
        email=request.official_email,
        password=request.password.get_secret_value(),
        expected_role=UserRole.GOVT_ADMIN,
        settings=settings,
    )
    return ApiResponse.ok(auth_service.issue_token(user, settings))


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_citizen(
    request: Annotated[CitizenRegistrationRequest, Body()],
    settings: SettingsDep,
) -> ApiResponse[UserResponse]:
    """Citizen self-registration.

    The National ID is encrypted before storage and never returned; it becomes
    the key that later unifies this citizen's records across hospitals.
    """
    user = await auth_service.register_citizen(request, settings)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.post(
    "/users",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request: Annotated[UserCreateRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[UserResponse]:
    """Provision an account for a colleague.

    A government admin may create any account; a hospital admin may create only
    hospital-scoped accounts inside their own hospital.
    """
    user = await auth_service.create_user(request, actor)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.get("/me", response_model=ApiResponse[UserResponse])
async def read_me(actor: CurrentUser) -> ApiResponse[UserResponse]:
    """Return the signed-in account."""
    return ApiResponse.ok(UserResponse.model_validate(actor))


@router.post("/password", response_model=ApiResponse[UserResponse])
async def change_password(
    request: Annotated[PasswordChangeRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[UserResponse]:
    """Change the signed-in account's password."""
    await auth_service.change_password(actor, request)
    return ApiResponse.ok(UserResponse.model_validate(actor))


@router.get("/users/{user_id}", response_model=ApiResponse[UserResponse])
async def read_user(user_id: PydanticObjectId, _actor: GovtAdmin) -> ApiResponse[UserResponse]:
    """Look up any account. Ministry only."""
    user = await auth_service.get_user(user_id)
    return ApiResponse.ok(UserResponse.model_validate(user))
