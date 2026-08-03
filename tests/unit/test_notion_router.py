"""
tests/unit/test_notion_router.py — Unit tests for the Notion integration router.

Endpoints covered:
  POST   /api/v1/notion/connect         → starts the OAuth flow, returns auth_url
  GET    /api/v1/notion/status          → reports connection status
  DELETE /api/v1/notion/disconnect      → removes the stored token

All external dependencies (DB session, KeyVault, NotionService, auth) are mocked.
No live HTTP calls, live DB connections, or real API keys are used.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.routers.notion import router as notion_router
from app.api.v1.deps import (
    get_current_user_id,
    get_key_vault,
    get_db_with_rls,
    get_notion_service,
)


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------

def _make_notion_app(
    fake_user_id: str = "00000000-0000-0000-0000-000000000002",
    notion_model: MagicMock | None = None,
    auth_url: str = "https://api.notion.com/v1/oauth/authorize?client_id=test",
) -> tuple[FastAPI, MagicMock, MagicMock]:
    """
    Build a minimal FastAPI app mounting only the Notion router.

    Returns (app, mock_db, mock_notion_svc).
    """
    app = FastAPI()
    app.include_router(notion_router, prefix="/api/v1")

    # ── Mock NotionService ────────────────────────────────────────────────
    mock_notion_svc = AsyncMock()
    mock_notion_svc.start_oauth = AsyncMock(return_value=auth_url)

    # ── Mock DB session ───────────────────────────────────────────────────
    mock_db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = notion_model
    mock_db.execute = AsyncMock(return_value=result_mock)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.delete = AsyncMock()

    # ── Mock Vault ────────────────────────────────────────────────────────
    mock_vault = MagicMock()
    mock_vault.encrypt.return_value = "FAKE_NOTION_CIPHER"

    # ── Override dependencies ─────────────────────────────────────────────
    app.dependency_overrides[get_current_user_id] = lambda: fake_user_id
    app.dependency_overrides[get_key_vault] = lambda: mock_vault
    app.dependency_overrides[get_db_with_rls] = lambda: mock_db
    app.dependency_overrides[get_notion_service] = lambda: mock_notion_svc

    return app, mock_db, mock_notion_svc


# ---------------------------------------------------------------------------
# Tests — POST /notion/connect
# ---------------------------------------------------------------------------

def test_notion_connect_returns_auth_url() -> None:
    """A valid POST to /notion/connect must return HTTP 200 with an 'auth_url' field."""
    expected_url = "https://api.notion.com/v1/oauth/authorize?client_id=test&state=abc"
    app, _, mock_notion_svc = _make_notion_app(auth_url=expected_url)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post("/api/v1/notion/connect")

    assert response.status_code == 200, (
        f"POST /notion/connect must return 200, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "auth_url" in body, f"Response must contain 'auth_url', got: {body}"
    assert body["auth_url"] == expected_url


def test_notion_connect_calls_notion_service_start_oauth() -> None:
    """POST /notion/connect must delegate to NotionService.start_oauth() exactly once."""
    app, _, mock_notion_svc = _make_notion_app()
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/api/v1/notion/connect")

    mock_notion_svc.start_oauth.assert_awaited_once()


def test_notion_connect_returns_500_when_service_raises() -> None:
    """When NotionService.start_oauth raises, the endpoint must return HTTP 500."""
    app, _, mock_notion_svc = _make_notion_app()
    mock_notion_svc.start_oauth.side_effect = RuntimeError("Notion OAuth misconfigured")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/notion/connect")

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Tests — GET /notion/status
# ---------------------------------------------------------------------------

def test_notion_status_unauthenticated_returns_404_when_not_connected() -> None:
    """GET /notion/status for a user with no stored token must return HTTP 404."""
    # Pass notion_model=None → scalar_one_or_none returns None → router raises 404
    app, _, _ = _make_notion_app(notion_model=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/notion/status")

    assert response.status_code == 404, (
        f"A user with no Notion token must get 404 'not connected', got {response.status_code}."
    )


def test_notion_status_returns_200_when_connected() -> None:
    """GET /notion/status for a user with a stored token must return HTTP 200."""
    import datetime

    connected_model = MagicMock()
    connected_model.id = "key-uuid-001"
    connected_model.provider = "notion"
    connected_model.key_fingerprint = "••••abcd"
    connected_model.last_test_ok = True
    connected_model.last_tested_at = datetime.datetime.now(datetime.timezone.utc)
    connected_model.created_at = datetime.datetime.now(datetime.timezone.utc)
    connected_model.updated_at = datetime.datetime.now(datetime.timezone.utc)
    connected_model.last_test_error = None

    app, _, _ = _make_notion_app(notion_model=connected_model)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.get("/api/v1/notion/status")

    assert response.status_code == 200, (
        f"A user with a stored Notion token must get 200, got {response.status_code}: {response.text}"
    )


# ---------------------------------------------------------------------------
# Tests — DELETE /notion/disconnect
# ---------------------------------------------------------------------------

def test_notion_disconnect_returns_404_when_not_connected() -> None:
    """DELETE /notion/disconnect for a user with no token must return HTTP 404."""
    app, _, _ = _make_notion_app(notion_model=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/api/v1/notion/disconnect")

    assert response.status_code == 404, (
        f"Disconnect with no Notion token must return 404, got {response.status_code}."
    )


def test_notion_disconnect_removes_token() -> None:
    """DELETE /notion/disconnect must call db.delete() on the stored token and return 204."""
    existing_model = MagicMock()
    existing_model.provider = "notion"

    app, mock_db, _ = _make_notion_app(notion_model=existing_model)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.delete("/api/v1/notion/disconnect")

    assert response.status_code == 204, (
        f"Disconnect with an existing token must return 204, got {response.status_code}: {response.text}"
    )
    mock_db.delete.assert_awaited_once_with(existing_model)
    mock_db.flush.assert_awaited()


def test_notion_disconnect_requires_auth() -> None:
    """DELETE /notion/disconnect without a valid auth token must return HTTP 401."""
    from fastapi import status as http_status

    app = FastAPI()
    app.include_router(notion_router, prefix="/api/v1")

    async def _reject_all():
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_token", "message": "Authentication is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user_id] = _reject_all

    client = TestClient(app, raise_server_exceptions=False)
    response = client.delete("/api/v1/notion/disconnect")

    assert response.status_code == 401, (
        f"Missing auth must yield HTTP 401, got {response.status_code}."
    )
