"""Smoke test proving the live-database harness works at all."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth

pytestmark = pytest.mark.integration


async def test_health_endpoint_answers(client: AsyncClient) -> None:
    """The app builds and serves over the ASGI transport."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_govt_admin_can_read_own_account(
    client: AsyncClient, govt_admin: dict[str, Any]
) -> None:
    """A signed-in ministry account resolves through the bearer dependency."""
    response = await client.get("/api/v1/auth/me", headers=auth(govt_admin["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["role"] == "GOVT_ADMIN"


async def test_unauthenticated_request_is_refused(client: AsyncClient) -> None:
    """An endpoint requiring a token answers 401 in the standard envelope."""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["success"] is False
