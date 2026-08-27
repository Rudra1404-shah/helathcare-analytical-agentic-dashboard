"""Domain errors and their HTTP status mapping.

Services raise these rather than :class:`fastapi.HTTPException`, which keeps the
service layer usable from a script, a scheduled job, or a future GraphQL
surface without dragging the web framework along.

``src.api.errors`` translates each one into the platform response envelope, so
a client sees the same ``{success, data, error}`` shape whether a call
succeeded, was refused, or hit a duplicate key.
"""

from http import HTTPStatus

__all__ = [
    "AuthenticationError",
    "ConflictError",
    "DomainError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnprocessableError",
]


class DomainError(Exception):
    """Base for every error a service raises deliberately.

    Carries the HTTP status the API layer should surface, so the mapping lives
    with the error rather than in a lookup table that can drift.
    """

    status_code: int = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """A referenced record does not exist, or is not visible to this actor."""

    status_code = HTTPStatus.NOT_FOUND


class ConflictError(DomainError):
    """The write would violate a uniqueness rule or a lifecycle constraint."""

    status_code = HTTPStatus.CONFLICT


class AuthenticationError(DomainError):
    """The caller could not be identified, or their credentials were rejected."""

    status_code = HTTPStatus.UNAUTHORIZED


class PermissionDeniedError(DomainError):
    """The caller is known but is not allowed to perform this action.

    Raised in particular when a hospital-scoped actor reaches for a record
    belonging to a different hospital.
    """

    status_code = HTTPStatus.FORBIDDEN


class UnprocessableError(DomainError):
    """The payload is well-formed but violates a domain rule.

    Used where a model validator would otherwise surface as an unhandled
    ``ValueError`` -- mandatory complaint evidence being the reference case.
    """

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
