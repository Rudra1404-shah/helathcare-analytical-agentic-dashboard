"""Authentication, account provisioning, and role checks.

Passwords are verified against Argon2 hashes and silently upgraded when the
stored hash was made with outdated parameters, so raising the work factor later
does not lock anyone out.

A citizen's National ID is captured at registration and stored only as a
:class:`~src.domain.models.base.ProtectedNationalId`. That deterministic lookup
hash is what later resolves the citizen to every hospital-local patient record
created for them, which is what makes the unified health record work.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.config import Settings, get_settings
from src.core.errors import AuthenticationError, ConflictError, PermissionDeniedError
from src.core.security import hash_password, needs_rehash, verify_password
from src.core.tokens import TOKEN_TYPE, create_access_token
from src.domain.enums import UserRole
from src.domain.models import ProtectedNationalId, User
from src.domain.models.base import utcnow
from src.domain.models.user import HOSPITAL_SCOPED_ROLES
from src.domain.schemas.auth import (
    CitizenRegistrationRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserCreateRequest,
)
from src.services.common import get_or_404, guard_duplicate, translate_validation_error

__all__ = [
    "authenticate",
    "change_password",
    "create_user",
    "ensure_role",
    "get_user",
    "issue_token",
    "register_citizen",
]

_COLLECTION = "users"


async def authenticate(
    email: str,
    password: str,
    expected_role: UserRole | None = None,
    settings: Settings | None = None,
) -> User:
    """Verify credentials and return the account.

    The same error is raised for an unknown email and a wrong password, so the
    endpoint cannot be used to enumerate which accounts exist.

    Args:
        email: Submitted login identity.
        password: Submitted plaintext password.
        expected_role: When set, the account must hold exactly this role. The
            Government master login uses it so a citizen cannot sign in there.
        settings: Optional settings override.

    Returns:
        The authenticated, active user.

    Raises:
        AuthenticationError: On any credential or role mismatch.
    """
    _ = settings
    normalised = email.lower().strip()
    user = await User.find_one(User.email == normalised)
    generic = "email or password is incorrect"

    if user is None or not verify_password(password, user.hashed_password):
        audit_event(AuditAction.LOGIN_FAILED, _COLLECTION, detail=f"email={normalised}")
        raise AuthenticationError(generic)

    if not user.is_active:
        audit_event(
            AuditAction.LOGIN_FAILED,
            _COLLECTION,
            actor_id=user.id,
            actor_role=user.role,
            detail="account deactivated",
        )
        msg = "this account has been deactivated; contact your administrator"
        raise AuthenticationError(msg)

    if expected_role is not None and user.role is not expected_role:
        audit_event(
            AuditAction.LOGIN_FAILED,
            _COLLECTION,
            actor_id=user.id,
            actor_role=user.role,
            detail=f"wrong portal, expected {expected_role}",
        )
        raise AuthenticationError(generic)

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)

    user.last_login_at = utcnow()
    user.touch()
    await user.save()

    audit_event(
        AuditAction.LOGIN,
        _COLLECTION,
        actor_id=user.id,
        actor_role=user.role,
        document_id=user.id,
        hospital_id=user.hospital_id,
    )
    return user


def issue_token(user: User, settings: Settings | None = None) -> TokenResponse:
    """Mint an access token for an already-authenticated account."""
    active = settings or get_settings()
    token, ttl = create_access_token(
        user_id=_require_id(user),
        role=user.role,
        hospital_id=user.hospital_id,
        settings=active,
    )
    return TokenResponse(
        access_token=token,
        token_type=TOKEN_TYPE,
        expires_in_seconds=ttl,
        role=user.role,
    )


async def register_citizen(
    request: CitizenRegistrationRequest,
    settings: Settings | None = None,
) -> User:
    """Create a citizen account from the public registration form.

    Raises:
        ConflictError: If the email or the National ID is already registered.
    """
    active = settings or get_settings()
    await _reject_existing_email(request.email)

    protected = ProtectedNationalId.protect(request.national_id, active)
    existing = await User.find_one({"national_id.lookup_hash": protected.lookup_hash})
    if existing is not None:
        msg = "a citizen account already exists for this National ID"
        raise ConflictError(msg)

    try:
        user = User(
            email=request.email.lower().strip(),
            hashed_password=hash_password(request.password.get_secret_value()),
            role=UserRole.CITIZEN,
            full_name=request.full_name,
            phone=request.phone,
            address=request.address,
            national_id=protected,
            is_verified=False,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(user.insert, "this email address is already registered")
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=user.id,
        actor_role=user.role,
        document_id=user.id,
        detail="citizen self-registration",
    )
    return user


async def create_user(request: UserCreateRequest, actor: User) -> User:
    """Provision an account on behalf of another portal user.

    Government admins may create any account. A hospital admin may create
    accounts only inside their own hospital, and only hospital-scoped ones.

    Raises:
        PermissionDeniedError: If the actor may not create this account.
        ConflictError: If the email is taken.
    """
    _authorise_provisioning(request, actor)
    await _reject_existing_email(request.email)

    try:
        user = User(
            email=request.email.lower().strip(),
            hashed_password=hash_password(request.password.get_secret_value()),
            role=request.role,
            full_name=request.full_name,
            phone=request.phone,
            hospital_id=request.hospital_id,
            is_verified=True,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(user.insert, "this email address is already registered")
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=user.id,
        hospital_id=user.hospital_id,
        detail=f"provisioned {request.role}",
    )
    return user


async def change_password(user: User, request: PasswordChangeRequest) -> None:
    """Replace an account's password after confirming the current one.

    Raises:
        AuthenticationError: If the current password does not match.
    """
    if not verify_password(request.current_password.get_secret_value(), user.hashed_password):
        msg = "current password is incorrect"
        raise AuthenticationError(msg)

    user.hashed_password = hash_password(request.new_password.get_secret_value())
    user.touch()
    await user.save()
    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=user.id,
        actor_role=user.role,
        document_id=user.id,
        hospital_id=user.hospital_id,
        detail="password changed",
    )


async def get_user(user_id: PydanticObjectId) -> User:
    """Fetch an account by id.

    Raises:
        NotFoundError: If no such account exists.
    """
    return await get_or_404(User, user_id, "user")


def ensure_role(actor: User, *allowed: UserRole) -> None:
    """Refuse an actor whose role is not in ``allowed``.

    Raises:
        PermissionDeniedError: If the actor holds none of the allowed roles.
    """
    if actor.role in allowed:
        return
    permitted = ", ".join(sorted(role.value for role in allowed))
    msg = f"role {actor.role} may not perform this action; it requires one of: {permitted}"
    raise PermissionDeniedError(msg)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _require_id(user: User) -> PydanticObjectId:
    """Return a persisted account's id, or fail loudly if it has none."""
    if user.id is None:
        msg = "cannot issue a token for an account that has not been saved"
        raise AuthenticationError(msg)
    return user.id


async def _reject_existing_email(email: str) -> None:
    """Raise a friendly conflict before the unique index does."""
    if await User.find_one(User.email == email.lower().strip()) is not None:
        msg = "this email address is already registered"
        raise ConflictError(msg)


def _authorise_provisioning(request: UserCreateRequest, actor: User) -> None:
    """Check that ``actor`` is allowed to create the requested account."""
    if actor.role is UserRole.GOVT_ADMIN:
        return

    if actor.role is not UserRole.HOSPITAL_ADMIN:
        msg = f"role {actor.role} may not provision accounts"
        raise PermissionDeniedError(msg)

    if request.role not in HOSPITAL_SCOPED_ROLES:
        msg = f"a hospital admin may not provision a {request.role} account"
        raise PermissionDeniedError(msg)

    if request.hospital_id != actor.hospital_id:
        msg = "a hospital admin may only provision accounts within their own hospital"
        raise PermissionDeniedError(msg)
