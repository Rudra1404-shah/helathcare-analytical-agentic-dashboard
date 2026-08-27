"""Helpers shared by every service.

Three concerns recur in all of them: fetching a document that must exist,
confirming a hospital-scoped actor is allowed to touch it, and turning a
MongoDB duplicate-key error into a message a human can act on.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from beanie import Document, PydanticObjectId
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from src.core.errors import ConflictError, NotFoundError, PermissionDeniedError, UnprocessableError
from src.domain.enums import UserRole
from src.domain.models import User

__all__ = [
    "apply_atomic_update",
    "apply_partial_update",
    "ensure_hospital_match",
    "get_or_404",
    "guard_duplicate",
    "hospital_scope_of",
    "translate_validation_error",
]

UNSCOPED_ROLES = frozenset({UserRole.GOVT_ADMIN, UserRole.CITIZEN})
"""Roles that are not confined to a single hospital."""

DocumentT = TypeVar("DocumentT", bound=Document)
ResultT = TypeVar("ResultT")


async def get_or_404(
    model: type[DocumentT],
    document_id: PydanticObjectId,
    label: str,
) -> DocumentT:
    """Fetch a document by id or raise :class:`NotFoundError`.

    Args:
        model: The Beanie document class.
        document_id: Identifier to look up.
        label: Human-readable noun used in the error, e.g. ``"hospital"``.

    Returns:
        The stored document.

    Raises:
        NotFoundError: If no document with that id exists.
    """
    document = await model.get(document_id)
    if document is None:
        msg = f"no {label} exists with id {document_id}"
        raise NotFoundError(msg)
    return document


def hospital_scope_of(actor: User) -> PydanticObjectId | None:
    """Return the hospital an actor is confined to.

    ``None`` means unconfined: a ministry official sees every hospital, and a
    citizen is filtered by their own identity rather than by tenancy.
    """
    if actor.role in UNSCOPED_ROLES:
        return None
    return actor.hospital_id


def ensure_hospital_match(
    record_hospital_id: PydanticObjectId | None,
    actor_hospital_id: PydanticObjectId | None,
    label: str,
) -> None:
    """Refuse cross-hospital access for a hospital-scoped actor.

    ``actor_hospital_id`` of ``None`` means the caller is a ministry account,
    which sees every hospital by design.

    Raises:
        PermissionDeniedError: If the actor belongs to a different hospital.
    """
    if actor_hospital_id is None:
        return
    if record_hospital_id is None or record_hospital_id != actor_hospital_id:
        msg = (
            f"this {label} belongs to another hospital; an account is scoped to "
            f"the hospital that issued it"
        )
        raise PermissionDeniedError(msg)


def apply_partial_update(document: Document, changes: dict[str, Any]) -> bool:
    """Assign non-``None`` changes onto a document, reporting whether it moved.

    Assignment goes through Pydantic because every document sets
    ``validate_assignment=True``; a change that would break an invariant raises
    here rather than reaching MongoDB.

    Returns:
        ``True`` if at least one field actually changed.
    """
    mutated = False
    for field, value in changes.items():
        if value is None:
            continue
        if getattr(document, field, None) == value:
            continue
        try:
            setattr(document, field, value)
        except ValidationError as exc:
            raise translate_validation_error(exc) from exc
        mutated = True
    return mutated


def apply_atomic_update(document: DocumentT, changes: dict[str, Any]) -> DocumentT:
    """Move several fields at once, validating the result as a whole.

    Assignment-time validation is right for a single-field edit but wrong for a
    transition where two fields must move together. Discharging a case is the
    reference case: ``status`` alone is invalid without ``discharged_at``, and
    ``discharged_at`` alone is invalid while the status is still open. Setting
    them one at a time fails whichever order is chosen.

    A fresh document is built from the merged data and validated in one pass,
    then given the stored identity so saving it replaces the original.

    Raises:
        UnprocessableError: If the merged state breaks a domain rule.
    """
    merged = document.model_dump()
    merged.update(changes)
    model: type[DocumentT] = type(document)
    try:
        # Beanie's model_validate is untyped, so the result is narrowed back to
        # the document type the caller passed in.
        updated = cast(DocumentT, model.model_validate(merged))
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc
    updated.id = document.id
    return updated


def translate_validation_error(exc: ValidationError) -> UnprocessableError:
    """Convert a Pydantic failure into a domain error carrying the reason."""
    reasons = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'payload'}: {error['msg']}"
        for error in exc.errors()
    )
    return UnprocessableError(reasons or str(exc))


async def guard_duplicate(
    operation: Callable[[], Awaitable[ResultT]],
    message: str,
) -> ResultT:
    """Run a write, converting a unique-index violation into a clear conflict.

    Pre-checking uniqueness still leaves a race between the check and the
    write; the index is the real guarantee, so its error is translated rather
    than allowed to surface as a 500.

    Raises:
        ConflictError: If the write violated a unique index.
        UnprocessableError: If the document failed validation on the way in.
    """
    try:
        return await operation()
    except DuplicateKeyError as exc:
        raise ConflictError(message) from exc
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc
