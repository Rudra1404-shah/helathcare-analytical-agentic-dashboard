"""Fixtures for API tests that run against a real MongoDB.

``tests/conftest.py`` deliberately registers every document *without* a server,
so unit tests need no infrastructure. These tests need the opposite: real
indexes, so uniqueness and compound-key rules are actually enforced, and real
queries, so a filter that MongoDB rejects fails here rather than in production.

Re-running ``init_beanie`` against the live database rebinds every document to
it for the rest of the session. That is safe: unit tests only construct and
validate documents, they never query.

The whole test database is dropped at session start and end. It is named
``unhp_test`` and is never the database the application settings point at.
"""

import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from src.api.deps import settings_dependency
from src.core.config import Environment, Settings
from src.core.security import hash_password
from src.domain.enums import UserRole
from src.domain.models import ALL_DOCUMENT_MODELS, User
from src.main import create_app

pytestmark = pytest.mark.integration

TEST_DATABASE = "unhp_test"
TEST_MONGO_URI = "mongodb://localhost:27017"

# Deterministic, obviously-fake keys. Never used outside tests.
TEST_ENCRYPTION_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
TEST_HMAC_SECRET = "test-hmac-secret-not-for-production"
TEST_JWT_SECRET = "test-jwt-secret-not-for-production"

STRONG_PASSWORD = "Str0ngPassword!"


@pytest.fixture(scope="session")
def api_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Settings pointing at the throwaway test database and a temp upload dir."""
    uploads: Path = tmp_path_factory.mktemp("uploads")
    return Settings(
        mongo_uri=TEST_MONGO_URI,
        mongo_db_name=TEST_DATABASE,
        environment=Environment.DEVELOPMENT,
        debug=True,
        national_id_encryption_key=TEST_ENCRYPTION_KEY,  # type: ignore[arg-type]
        national_id_hmac_secret=TEST_HMAC_SECRET,  # type: ignore[arg-type]
        jwt_secret=TEST_JWT_SECRET,  # type: ignore[arg-type]
        upload_dir=uploads,
        upload_base_url="http://testserver/uploads",
    )


@pytest_asyncio.fixture(scope="session")
async def database(api_settings: Settings) -> AsyncIterator[AsyncMongoClient[dict[str, Any]]]:
    """Connect to the live server, build real indexes, and clean up afterwards."""
    # tz_aware mirrors src.infrastructure.database: without it MongoDB returns
    # naive datetimes and every timestamp comparison in a model validator fails.
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        api_settings.mongo_uri, serverSelectionTimeoutMS=3000, tz_aware=True
    )
    await client.drop_database(TEST_DATABASE)
    await init_beanie(
        database=client[TEST_DATABASE],
        document_models=ALL_DOCUMENT_MODELS,
    )
    try:
        yield client
    finally:
        await client.drop_database(TEST_DATABASE)
        await client.close()


@pytest_asyncio.fixture(scope="session")
async def client(
    api_settings: Settings,
    database: AsyncMongoClient[dict[str, Any]],
) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound straight to the ASGI app.

    The app's lifespan is not run, because this module owns the database
    connection; running it would open a second client against the real
    application database.
    """
    _ = database
    app = create_app(api_settings)
    app.dependency_overrides[settings_dependency] = lambda: api_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


# --------------------------------------------------------------------------- #
# Account fixtures
# --------------------------------------------------------------------------- #
async def _make_account(
    email: str,
    role: UserRole,
    hospital_id: Any = None,
    doctor_id: Any = None,
) -> User:
    """Insert an account directly, bypassing the API's own provisioning rules."""
    user = User(
        email=email,
        hashed_password=hash_password(STRONG_PASSWORD),
        role=role,
        full_name=f"Test {role.value.title().replace('_', ' ')}",
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        is_verified=True,
    )
    await user.insert()
    return user


async def _token(http: AsyncClient, email: str) -> str:
    """Sign in and return the bearer token."""
    response = await http.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["data"]["access_token"]
    return token


def auth(token: str) -> dict[str, str]:
    """Build the Authorization header for a token."""
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def govt_admin(client: AsyncClient) -> dict[str, Any]:
    """A Health Ministry account and its bearer token."""
    user = await _make_account("ministry@health.gov.example.com", UserRole.GOVT_ADMIN)
    return {"user": user, "token": await _token(client, "ministry@health.gov.example.com")}


@pytest_asyncio.fixture(scope="session")
async def world(client: AsyncClient, govt_admin: dict[str, Any]) -> Any:
    """A registered hospital with a department, a doctor, and bed inventory.

    Built once through the real API, so the scaffolding is itself a test of
    hospital registration, department setup, doctor onboarding, and inventory.
    """
    from tests.integration.world import build_world

    return await build_world(client, govt_admin["token"], _make_account, _token)


@pytest_asyncio.fixture(scope="session")
async def rival(client: AsyncClient, govt_admin: dict[str, Any]) -> Any:
    """A second hospital, used to prove one hospital cannot read another's data."""
    from tests.integration.world import build_world

    return await build_world(client, govt_admin["token"], _make_account, _token, suffix="02")


@pytest_asyncio.fixture(scope="session")
async def citizen(client: AsyncClient) -> dict[str, Any]:
    """A registered citizen account and its bearer token.

    Registered through the public endpoint so the National ID is protected the
    same way a real citizen's would be.
    """
    email = "asha.citizen@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Asha Kulkarni",
            "phone": "+919820011223",
            "email": email,
            "password": STRONG_PASSWORD,
            "national_id": "4321-8765-2109",
            "address": {
                "line1": "12 Linking Road",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400050",
            },
        },
    )
    assert response.status_code == 201, response.text
    return {
        "id": response.json()["data"]["_id"],
        "email": email,
        "national_id": "4321-8765-2109",
        "token": await _token(client, email),
    }
