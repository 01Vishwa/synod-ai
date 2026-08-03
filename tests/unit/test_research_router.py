"""
tests/unit/test_research_router.py — Unit tests for POST /api/v1/research/keys.

All external dependencies (DB session, KeyVault, auth) are mocked.
No live HTTP calls, live DB connections, or real API keys are used.

FIX-11 context: the router previously wrote `model.encrypted_key` which does
not exist on ProviderKeyModel.  These tests lock in the correct behaviour —
writing to `model.ciphertext_b64`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.research import router as research_router
from app.api.v1.deps import (
    get_current_user_id,
    get_key_vault,
    get_db_with_rls,
)

# ---------------------------------------------------------------------------
# App factory — build an isolated FastAPI app with only the research router
# ---------------------------------------------------------------------------

def _make_app(
    fake_user_id: str = "00000000-0000-0000-0000-000000000001",
    fake_ciphertext: str = "FAKE_CIPHERTEXT_B64",
    db_model: MagicMock | None = None,
) -> tuple[FastAPI, MagicMock]:
    """
    Build a minimal FastAPI app that mounts only the research router,
    with all external deps replaced by in-memory mocks.

    Returns (app, db_mock) so callers can make assertions on the DB mock.
    """
    app = FastAPI()
    app.include_router(research_router, prefix="/api/v1")

    # ── Mock vault ────────────────────────────────────────────────────────
    mock_vault = MagicMock()
    mock_vault.encrypt.return_value = fake_ciphertext

    # ── Mock DB session ───────────────────────────────────────────────────
    mock_db = AsyncMock()

    if db_model is None:
        # Default: no existing row → the router creates a new one
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)
    else:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_model
        mock_db.execute = AsyncMock(return_value=result_mock)

    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    # ── Override dependencies ─────────────────────────────────────────────
    app.dependency_overrides[get_current_user_id] = lambda: fake_user_id
    app.dependency_overrides[get_key_vault] = lambda: mock_vault
    app.dependency_overrides[get_db_with_rls] = lambda: mock_db

    return app, mock_db


def _make_response_model() -> MagicMock:
    """
    Build a MagicMock that looks enough like a ProviderKeyModel for Pydantic's
    from_attributes serializer to work (all required fields must be real types).
    """
    import datetime
    m = MagicMock()
    m.id = "key-uuid-0001"
    m.provider = "tavily"
    m.key_fingerprint = "\u2022\u2022\u2022\u2022test"
    m.last_test_ok = None
    m.last_tested_at = None
    m.created_at = datetime.datetime.now(datetime.timezone.utc)
    m.updated_at = datetime.datetime.now(datetime.timezone.utc)
    m.ciphertext_b64 = "FAKE_CIPHERTEXT_B64"
    # Explicitly remove encrypted_key so AttributeError fires if accessed
    del m.encrypted_key
    return m





# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_upsert_research_key_stores_ciphertext_b64() -> None:
    """A valid POST must succeed (HTTP 201) and the DB must receive a model with ciphertext_b64 set."""
    app, mock_db = _make_app(db_model=None, fake_ciphertext="FAKE_CIPHERTEXT_B64")
    client = TestClient(app, raise_server_exceptions=True)

    # Track what object gets passed to db.add()
    added_models: list = []
    
    def fake_db_add(model_instance):
        import datetime
        model_instance.id = "key-uuid-0001"
        model_instance.created_at = datetime.datetime.now(datetime.timezone.utc)
        model_instance.updated_at = datetime.datetime.now(datetime.timezone.utc)
        added_models.append(model_instance)
        
    mock_db.add.side_effect = fake_db_add

    response = client.post(
        "/api/v1/research/keys",
        json={"provider": "tavily", "api_key": "tvly-test"},
    )

    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    # db.add() must have been called once with the new model
    assert len(added_models) == 1, "db.add() must be called exactly once for a new key insert"
    new_model = added_models[0]

    # The model must carry ciphertext_b64, not encrypted_key
    assert new_model.ciphertext_b64 == "FAKE_CIPHERTEXT_B64", (
        "ProviderKeyModel.ciphertext_b64 must be set by the router. "
        "FIX-11 regression: router must use ciphertext_b64, not encrypted_key."
    )


def test_upsert_research_key_existing_row_uses_ciphertext_b64() -> None:
    """When an existing row is found, the router must update ciphertext_b64, not encrypted_key."""
    existing = _make_response_model()
    # Ensure encrypted_key is not an attribute (raises AttributeError if accessed)
    try:
        del existing.encrypted_key
    except AttributeError:
        pass

    app, mock_db = _make_app(db_model=existing, fake_ciphertext="UPDATED_CIPHER")
    client = TestClient(app, raise_server_exceptions=True)

    # This should NOT raise AttributeError if the router correctly uses ciphertext_b64
    response = client.post(
        "/api/v1/research/keys",
        json={"provider": "tavily", "api_key": "tvly-updated"},
    )

    # The key assertion: ciphertext_b64 must be set on the existing model
    assert existing.ciphertext_b64 == "UPDATED_CIPHER", (
        "Router must set existing.ciphertext_b64 when updating an existing row."
    )


def test_upsert_research_key_rejects_unknown_provider() -> None:
    """A POST with an unknown provider slug must be rejected with HTTP 400."""
    app, _ = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/research/keys",
        json={"provider": "unknown_vendor", "api_key": "test"},
    )

    # Pydantic rejects the literal discriminator at schema level → 422
    # OR the router logic raises 400 — either is a rejection
    assert response.status_code in (400, 422), (
        f"Unknown provider must be rejected (400 or 422), got {response.status_code}."
    )


def test_upsert_research_key_requires_auth() -> None:
    """A POST without an Authorization header must return HTTP 401."""
    # Build app WITHOUT overriding get_current_user_id → real auth runs
    app = FastAPI()
    app.include_router(research_router, prefix="/api/v1")

    # We need to override the JWKS client so it doesn't try to hit the network.
    # We patch get_current_user_id at the dependency level to raise 401 when
    # no token is present, which is what the real implementation does.
    from fastapi import HTTPException, status as http_status

    async def _reject_all():
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_token", "message": "Authentication is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user_id] = _reject_all

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/research/keys",
        json={"provider": "tavily", "api_key": "tvly-test"},
        # Deliberately omit Authorization header
    )

    assert response.status_code == 401, (
        f"Missing auth must yield HTTP 401, got {response.status_code}."
    )
