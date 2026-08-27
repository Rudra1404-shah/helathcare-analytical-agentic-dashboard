"""FastAPI application entrypoint.

Wires together the three portals' routers, the CORS policy the dashboard needs,
the exception handlers that normalise every failure into one envelope, and the
static mount that serves uploaded evidence back to the ministry's viewer.

The MongoDB connection is opened and closed by the lifespan handler so the
process never leaks a client.

Run with: ``uvicorn src.main:app --reload``
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.errors import register_exception_handlers
from src.api.v1 import api_router
from src.core.config import Settings, get_settings
from src.domain.models import ALL_DOCUMENT_MODELS
from src.infrastructure.database import mongo

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

API_TITLE = "Unified National Health Platform"
API_VERSION = "0.2.0"
API_DESCRIPTION = (
    "Unified national platform bridging public and private healthcare: "
    "hospital governance, operational workflows, patient health records, "
    "and public grievance resolution."
)

UPLOADS_MOUNT = "/uploads"


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

    _configure_cors(application, active)
    register_exception_handlers(application)
    application.include_router(api_router)
    _mount_uploads(application, active)

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


def _configure_cors(application: FastAPI, settings: Settings) -> None:
    """Allow the dashboard's origin to call the API.

    Origins are listed explicitly rather than wildcarded: credentials are
    allowed, and a wildcard with credentials would let any site a signed-in
    official visits read ministry data through their browser.
    """
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


def _mount_uploads(application: FastAPI, settings: Settings) -> None:
    """Serve stored evidence and documents back over HTTP.

    Local disk is the Phase 2 backend; ``src.services.storage_service`` is the
    only module that writes here, so swapping in S3 or GridFS later means
    replacing that module and dropping this mount.
    """
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    application.mount(
        UPLOADS_MOUNT,
        StaticFiles(directory=directory),
        name="uploads",
    )


app = create_app()
