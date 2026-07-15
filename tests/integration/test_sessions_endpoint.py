"""
tests/integration/test_sessions_endpoint.py

Integration tests for POST /api/v1/sessions.

These tests verify that the create_session endpoint:

  1. Returns 201 and does NOT 500 when chairman_member_id is omitted
     (regression test for the `req.pinned_chairman_member_id` AttributeError).
  2. Returns 201 and does NOT 500 when a valid chairman_member_id is provided.
  3. Returns 401 when no auth token is present.
  4. Returns 422 when the request body fails schema validation.

All external dependencies (auth JWT, Postgres repo, tracer, LangGraph runner)
are overridden via FastAPI's dependency injection so tests remain hermetic
and do not require a live database, Supabase, or LangSmith.

Run with: pytest tests/integration/test_sessions_endpoint.py -v
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.api.v1.deps import get_current_user_id, get_session, get_tracer


# ── Fake stub implementations ────────────────────────────────────────────────

FAKE_USER_ID = "test-user-00000000-0000-0000-0000-000000000001"

# Minimal CouncilState-shaped dict the stub repo returns after create()
def _fake_state(extra: dict | None = None) -> dict:
    _members = [
        {
            "member_id": "member_a1b2c3d",
            "provider": "openrouter",
            "model_id": "anthropic/claude-sonnet-4.5",
            "display_label": "Seat A",
            "role": "member",
        },
        {
            "member_id": "member_e4f5g6h",
            "provider": "nvidia_nim",
            "model_id": "meta/llama-3.3-70b-instruct",
            "display_label": "Seat B",
            "role": "member",
        },
        {
            "member_id": "member_j7k8m9n",
            "provider": "openrouter",
            "model_id": "openai/gpt-4.1",
            "display_label": "Seat C",
            "role": "member",
        },
    ]
    base: dict[str, Any] = {
        "session_id": "sess-aabbccdd-0000-0000-0000-000000000001",
        "trace_id": "trace-001",
        "user_id": FAKE_USER_ID,
        "user_query": "What are the trade-offs between microservices and a monolith?",
        "members": _members,
        # SessionResponse.member_count is a required field — must be included
        "member_count": len(_members),
        "stage": "stage_1",
        "research_enabled": False,
        "research_provider": None,
        "research_digest": None,
        "stage_1_responses": [],
        "anonymization_map": {},
        "stage_2_responses": [],
        "rankings": [],
        "aggregate_scores": {},
        "chairman_member_id": "",
        "final_report_md": None,
        "citations": [],
        "notion_page_url": None,
        "dashboard_spec": None,
        "errors": [],
        "archive_to_notion": False,
        "created_at": "2026-07-13T00:00:00Z",
        "updated_at": "2026-07-13T00:00:00Z",
    }
    if extra:
        base.update(extra)
    return base


class _FakeRepo:
    """Stub SessionRepository that never touches Postgres."""

    def __init__(self, state_override: dict | None = None):
        self._state_override = state_override

    async def create(self, state: dict) -> dict:  # noqa: D401
        persisted = _fake_state(self._state_override)
        # Echo back whatever chairman_member_id was set by the router
        persisted["chairman_member_id"] = state.get("chairman_member_id", "")
        return persisted

    async def load(self, session_id: str, **kwargs) -> dict | None:
        return _fake_state(self._state_override)

    async def save(self, state: dict) -> dict:
        return state

    async def list_sessions(self, **kwargs) -> list:
        return []

    async def delete(self, session_id: str, **kwargs) -> None:
        pass


class _FakeTracer:
    """Stub tracer that never calls LangSmith."""

    async def start_trace(self, **kwargs) -> Any:
        ctx = MagicMock()
        ctx.trace_id = "trace-001"
        return ctx

    def get_trace_url(self, trace_id: str) -> str:
        return f"https://smith.langchain.com/stub/{trace_id}"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    """
    A TestClient for the Synod FastAPI app with all external dependencies
    replaced by in-process stubs.

    The background task (run_council_graph) is also stubbed out so the
    endpoint returns immediately without spawning a real LangGraph run.
    """
    # Stub the LangGraph runner so BackgroundTasks.add_task is a no-op
    monkeypatch.setattr(
        "app.api.v1.routers.sessions.run_council_graph",
        AsyncMock(return_value=None),
    )

    app = create_app()

    fake_repo = _FakeRepo()
    fake_tracer = _FakeTracer()

    # Override FastAPI deps
    app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
    app.dependency_overrides[get_session] = lambda: fake_repo
    app.dependency_overrides[get_tracer] = lambda: fake_tracer

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def client_with_chairman(monkeypatch):
    """Like `client` but the repo echoes chairman_member_id from state."""
    monkeypatch.setattr(
        "app.api.v1.routers.sessions.run_council_graph",
        AsyncMock(return_value=None),
    )

    app = create_app()
    fake_repo = _FakeRepo(state_override={"chairman_member_id": "member_j7k8m9n"})
    fake_tracer = _FakeTracer()

    app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
    app.dependency_overrides[get_session] = lambda: fake_repo
    app.dependency_overrides[get_tracer] = lambda: fake_tracer

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Shared payload helpers ─────────────────────────────────────────────────────

_BASE_MEMBERS = [
    {
        "member_id": "member_a1b2c3d",
        "provider": "openrouter",
        "model_id": "anthropic/claude-sonnet-4.5",
        "display_label": "Seat A",
        "role": "member",
    },
    {
        "member_id": "member_e4f5g6h",
        "provider": "nvidia_nim",
        "model_id": "meta/llama-3.3-70b-instruct",
        "display_label": "Seat B",
        "role": "member",
    },
    {
        "member_id": "member_j7k8m9n",
        "provider": "openrouter",
        "model_id": "openai/gpt-4.1",
        "display_label": "Seat C",
        "role": "member",
    },
]


# ── Test cases ────────────────────────────────────────────────────────────────

class TestCreateSessionWithoutChairman:
    """
    PRD §6.5 step 4: when chairman_member_id is omitted the orchestrator
    elects the top Stage-2 scorer.  The HTTP layer must NOT 500.
    """

    def test_returns_201_not_500(self, client: TestClient) -> None:
        """
        Regression: accessing req.pinned_chairman_member_id raised AttributeError
        (500).  After fix, omitting chairman_member_id returns 201.
        """
        resp = client.post(
            "/api/v1/sessions",
            json={
                "user_query": "What are the trade-offs between microservices and a monolith?",
                "members": _BASE_MEMBERS,
                "research_enabled": False,
            },
            headers={"Authorization": f"Bearer stub-token"},
        )
        assert resp.status_code == 201, (
            f"Expected 201 Created, got {resp.status_code}. "
            f"Body: {resp.text}"
        )

    def test_response_body_has_session_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/sessions",
            json={
                "user_query": "Test query",
                "members": _BASE_MEMBERS,
                "research_enabled": False,
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "session_id" in body, "Response must contain session_id"

    def test_chairman_member_id_absent_does_not_500(self, client: TestClient) -> None:
        """Explicit check: the specific error reported in the bug must not recur."""
        resp = client.post(
            "/api/v1/sessions",
            json={
                "user_query": "Deliberate without a pinned chairman.",
                "members": _BASE_MEMBERS,
                # chairman_member_id intentionally absent — election mode
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        # Any status < 500 means the AttributeError is gone
        assert resp.status_code < 500, (
            f"Got {resp.status_code} — likely still hitting 'pinned_chairman_member_id' "
            f"AttributeError. Body: {resp.text}"
        )


class TestCreateSessionWithChairman:
    """When chairman_member_id is provided it must be forwarded correctly."""

    def test_returns_201_with_valid_chairman(
        self, client_with_chairman: TestClient
    ) -> None:
        # Promote one seat to chairman role so the validator accepts the field
        members = [
            {**m, "role": "chairman"} if m["member_id"] == "member_j7k8m9n" else m
            for m in _BASE_MEMBERS
        ]
        resp = client_with_chairman.post(
            "/api/v1/sessions",
            json={
                "user_query": "Which design is best?",
                "members": members,
                "chairman_member_id": "member_j7k8m9n",
                "research_enabled": False,
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 201, (
            f"Expected 201, got {resp.status_code}. Body: {resp.text}"
        )

    def test_chairman_member_id_present_in_response(
        self, client_with_chairman: TestClient
    ) -> None:
        members = [
            {**m, "role": "chairman"} if m["member_id"] == "member_j7k8m9n" else m
            for m in _BASE_MEMBERS
        ]
        resp = client_with_chairman.post(
            "/api/v1/sessions",
            json={
                "user_query": "Which design is best?",
                "members": members,
                "chairman_member_id": "member_j7k8m9n",
                "research_enabled": False,
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body.get("chairman_member_id") == "member_j7k8m9n"


class TestCreateSessionAuthGuard:
    """Endpoints must reject unauthenticated requests."""

    def test_missing_auth_returns_401(self, monkeypatch) -> None:
        # Build a fresh app with only the tracer/repo stubbed (not auth),
        # so the real get_current_user_id guard fires.
        # We must still stub the LangGraph runner and the repo to avoid
        # touching Postgres, but leave auth untouched.
        monkeypatch.setattr(
            "app.api.v1.routers.sessions.run_council_graph",
            AsyncMock(return_value=None),
        )
        app_real_auth = create_app()
        fake_repo = _FakeRepo()
        fake_tracer = _FakeTracer()
        # Override everything EXCEPT get_current_user_id
        app_real_auth.dependency_overrides[get_session] = lambda: fake_repo
        app_real_auth.dependency_overrides[get_tracer] = lambda: fake_tracer

        with TestClient(app_real_auth, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/sessions",
                json={
                    "user_query": "Test query",
                    "members": _BASE_MEMBERS,
                    "research_enabled": False,
                },
                # No Authorization header
            )
        assert resp.status_code == 401


class TestCreateSessionValidation:
    """The schema boundary must reject invalid payloads with 422."""

    def test_missing_user_query_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/sessions",
            json={"members": _BASE_MEMBERS, "research_enabled": False},
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 422

    def test_research_enabled_without_provider_returns_422(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/v1/sessions",
            json={
                "user_query": "Test query",
                "members": _BASE_MEMBERS,
                "research_enabled": True,
                # research_provider deliberately absent
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 422

    def test_invalid_chairman_member_id_returns_422(
        self, client: TestClient
    ) -> None:
        """chairman_member_id pointing at a non-existent member must 422, not 500."""
        resp = client.post(
            "/api/v1/sessions",
            json={
                "user_query": "Test query",
                "members": _BASE_MEMBERS,
                "chairman_member_id": "member_xxxxxxx",  # does not exist in members
                "research_enabled": False,
            },
            headers={"Authorization": "Bearer stub-token"},
        )
        assert resp.status_code == 422
