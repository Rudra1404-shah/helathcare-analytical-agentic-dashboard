"""MongoDB connection management and Beanie initialisation.

This is the **only** module in the platform that touches the MongoDB driver
directly. Everything else works through Beanie documents. Keeping driver contact
in one file means a future driver migration is a single-file change.

A note on the driver: Beanie 2.x dropped Motor in favour of PyMongo's native
``AsyncMongoClient``. Motor reached end of life after MongoDB folded its async
support back into PyMongo, so ``AsyncMongoClient`` *is* the current async
driver, not a substitute for one.
"""

import logging
from typing import Any

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from src.core.config import Settings, get_settings
from src.domain.models import ALL_DOCUMENT_MODELS

__all__ = ["MongoConnection", "mongo"]

logger = logging.getLogger(__name__)


class MongoConnection:
    """Owns the MongoDB client lifecycle for the running process."""

    def __init__(self) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] | None = None
        self._database: AsyncDatabase[dict[str, Any]] | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether a client has been created."""
        return self._client is not None

    @property
    def database(self) -> AsyncDatabase[dict[str, Any]]:
        """Return the active database handle.

        Raises:
            RuntimeError: If accessed before :meth:`connect`.
        """
        if self._database is None:
            msg = "database accessed before connect(); call connect() during app startup"
            raise RuntimeError(msg)
        return self._database

    async def connect(self, settings: Settings | None = None) -> None:
        """Open the client and register every document model with Beanie.

        Safe to call once per process. Calling it again while connected is a
        no-op, so an accidental double-startup does not leak a client.

        Raises:
            PyMongoError: If the server is unreachable or initialisation fails.
        """
        if self._client is not None:
            logger.debug("MongoDB already connected; skipping reconnect")
            return

        active = settings or get_settings()
        logger.info("Connecting to MongoDB database %s", active.mongo_db_name)

        # tz_aware is not optional. BSON stores datetimes without a zone, so a
        # naive client hands back naive values -- and every model validator that
        # compares a stored timestamp against utcnow() (discharge before
        # admission, incident not in the future) raises TypeError on the first
        # document it reads back. Aware UTC in, aware UTC out.
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(active.mongo_uri, tz_aware=True)
        try:
            await init_beanie(
                database=client[active.mongo_db_name],
                document_models=ALL_DOCUMENT_MODELS,
            )
        except PyMongoError:
            await client.close()
            logger.exception("Failed to initialise Beanie against MongoDB")
            raise

        self._client = client
        self._database = client[active.mongo_db_name]
        logger.info("MongoDB ready with %d registered collections", len(ALL_DOCUMENT_MODELS))

    async def disconnect(self) -> None:
        """Close the client if one is open."""
        if self._client is None:
            return
        await self._client.close()
        self._client = None
        self._database = None
        logger.info("MongoDB connection closed")

    async def ping(self) -> bool:
        """Return whether the server currently answers a ping."""
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
        except PyMongoError:
            logger.warning("MongoDB ping failed", exc_info=True)
            return False
        return True


mongo = MongoConnection()
"""Process-wide MongoDB connection."""
