"""FastAPI application entrypoint.

Phase 1 exposes only health endpoints; the portal routers arrive in Phase 2.
The MongoDB connection is opened and closed by the lifespan handler so the
process never leaks a client.

Run with: ``uvicorn src.main:app --reload``
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.core.config import Settings, get_settings
from src.domain.models import ALL_DOCUMENT_MODELS
from src.infrastructure.database import mongo

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

API_TITLE = "Unified National Health Platform"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Unified national platform bridging public and private healthcare: "
    "hospital governance, operational workflows, patient health records, "
    "and public grievance resolution."
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Open the MongoDB connection on startup and close it on shutdown."""
    await mongo.connect()
    try:
        yield
    finally:
        await mongo.disconnect()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Optional settings override, primarily for tests.

    Returns:
        A configured FastAPI application.
    """
    active = settings or get_settings()

    application = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        debug=active.debug,
        lifespan=lifespan,
    )

    @application.get("/health", tags=["health"])
    async def health() -> dict[str, Any]:
        """Return liveness information. Does not touch the database."""
        return {
            "status": "ok",
            "service": API_TITLE,
            "version": API_VERSION,
            "environment": active.environment,
        }

    @application.get("/health/ready", tags=["health"])
    async def readiness() -> dict[str, Any]:
        """Return readiness, including whether MongoDB answers a ping."""
        database_ok = await mongo.ping()
        return {
            "status": "ready" if database_ok else "degraded",
            "database": "up" if database_ok else "down",
            "registered_collections": len(ALL_DOCUMENT_MODELS),
        }

    return application


app = create_app()
