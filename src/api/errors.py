"""Exception handlers that normalise every failure into the response envelope.

Without these, three different shapes reach the client: FastAPI's
``{"detail": ...}`` for its own errors, a raw 500 for an unhandled service
error, and a nested ``{"detail": [...]}`` list for validation failures. A
dashboard would need three parsers for one API.

Everything here answers with :class:`~src.domain.schemas.common.ApiResponse`, so
a client reads ``success`` and then either ``data`` or ``error``, always.
"""

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.errors import AuthenticationError, DomainError

__all__ = ["envelope", "register_exception_handlers"]

logger = logging.getLogger(__name__)

_AUTH_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def envelope(
    status_code: int,
    error: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a failure response in the platform envelope."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": error, "meta": None},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler to the application."""

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
        """Map a deliberate service error onto the status it declares."""
        assert isinstance(exc, DomainError)
        headers = _AUTH_CHALLENGE if isinstance(exc, AuthenticationError) else None
        return envelope(exc.status_code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_request: Request, exc: Exception) -> JSONResponse:
        """Flatten FastAPI's nested validation errors into one readable line."""
        assert isinstance(exc, RequestValidationError)
        return envelope(HTTPStatus.UNPROCESSABLE_ENTITY, _describe(exc.errors()))

    @app.exception_handler(ValidationError)
    async def _model_validation(_request: Request, exc: Exception) -> JSONResponse:
        """Catch a domain rule raised by a model outside a service call.

        A ``ValidationError`` escaping this far means a document validator
        fired on a path that did not translate it -- the mandatory-evidence
        rule, for instance. It is the caller's fault, not the server's, so it
        answers 422 rather than 500.
        """
        assert isinstance(exc, ValidationError)
        return envelope(HTTPStatus.UNPROCESSABLE_ENTITY, _describe(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_request: Request, exc: Exception) -> JSONResponse:
        """Re-shape FastAPI's own errors -- 404 on an unknown path, and so on."""
        assert isinstance(exc, StarletteHTTPException)
        detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
        headers = dict(exc.headers) if exc.headers else None
        return envelope(exc.status_code, detail, headers)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Log the real cause and answer with something that leaks nothing.

        An exception message can carry a National ID, a connection string, or a
        stack path. The client gets a fixed sentence; the detail goes to the
        server log where an operator can correlate it by request path.
        """
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return envelope(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "an unexpected error occurred; the incident has been logged",
        )


def _describe(errors: Sequence[Any]) -> str:
    """Render Pydantic's error list as one human-readable sentence."""
    parts: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        message = error.get("msg", "is invalid")
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "the request payload is invalid"
