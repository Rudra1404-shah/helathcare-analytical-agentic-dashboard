"""Shared pytest fixtures.

**Why these tests need no MongoDB.** Beanie 2.x resolves a document's collection
inside ``Document.__init__``, so constructing any document before
``init_beanie`` raises ``CollectionWasNotInitialized``. But ``init_beanie``
itself issues a ``buildInfo`` command, which needs a live server.

The session fixture below breaks that dependency: it stubs the one initialiser
step that talks to the server, then runs the rest of registration against a lazy
client that never opens a socket. Documents end up fully registered, every
validator runs for real, and the suite still runs on a clean checkout with no
infrastructure.

The stub reaches into a Beanie internal, so :func:`test_document_registry_is_live`
in ``tests/unit/test_bootstrap.py`` fails loudly if a future Beanie upgrade
changes that path.
"""

import asyncio
import base64
import os
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from beanie import init_beanie
from beanie.odm.utils.init import Initializer
from pymongo import AsyncMongoClient

from src.core.config import Environment, Settings
from src.domain.models import ALL_DOCUMENT_MODELS

# A deterministic, obviously-fake 32-byte key. Never used outside tests.
TEST_ENCRYPTION_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
TEST_HMAC_SECRET = "test-hmac-secret-not-for-production"

# Points at a port nothing listens on, to prove no connection is attempted.
UNREACHABLE_MONGO_URI = "mongodb://127.0.0.1:59999"


@pytest.fixture(scope="session", autouse=True)
def isolate_settings_from_the_environment() -> Iterator[None]:
    """Keep a developer's local ``.env`` and shell exports out of the tests.

    Without this, running the API locally is enough to break the test suite:
    a real ``UNHP_JWT_SECRET`` in ``.env`` makes the placeholder-secret guard
    tests pass their check and fail their assertion. Tests must describe the
    code, not whatever happens to be configured on one machine.
    """
    original_env_file = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None

    overridden = {key: value for key, value in os.environ.items() if key.startswith("UNHP_")}
    for key in overridden:
        del os.environ[key]

    try:
        yield
    finally:
        Settings.model_config["env_file"] = original_env_file
        os.environ.update(overridden)


@pytest.fixture(scope="session", autouse=True)
def beanie_document_registry() -> Iterator[None]:
    """Register every document model with Beanie without contacting MongoDB."""

    async def _register() -> None:
        client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(
            UNREACHABLE_MONGO_URI, serverSelectionTimeoutMS=200
        )
        with patch.object(Initializer, "_load_cached_info", new=AsyncMock(return_value=None)):
            await init_beanie(
                database=client["unhp_test"],
                document_models=ALL_DOCUMENT_MODELS,
                skip_indexes=True,
            )

    asyncio.run(_register())
    yield


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Settings carrying real, test-only crypto keys."""
    return Settings(
        mongo_uri=UNREACHABLE_MONGO_URI,
        mongo_db_name="unhp_test",
        environment=Environment.DEVELOPMENT,
        debug=True,
        national_id_encryption_key=TEST_ENCRYPTION_KEY,  # type: ignore[arg-type]
        national_id_hmac_secret=TEST_HMAC_SECRET,  # type: ignore[arg-type]
    )
