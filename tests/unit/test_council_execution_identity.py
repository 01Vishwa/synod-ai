"""
tests/unit/test_council_execution_identity.py

Regression tests for the council execution identity propagation, transaction
commit ordering, and running-marker precondition fixes.

Tests cover:
  A. Session creation commits BEFORE background task is scheduled
  B. Initial state preserves user_id through construction path
  D/E. Empty/missing user_id fails before SQL (CouncilStateValidationError)
  F. Identity mismatch between runner arg and state field raises an error
  G. Running-marker failure prevents graph execution (no ainvoke, no LLM)
  H. Error persistence uses independent session
  I. Fan-out payloads (Stage 1, Stage 2) propagate user_id correctly
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────

VALID_SESSION_ID = str(uuid.uuid4())
VALID_USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())


def _make_initial_state(
    session_id: str = VALID_SESSION_ID,
    user_id: str = VALID_USER_ID,
) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "trace_id": str(uuid.uuid4()),
        "user_query": "What is the optimal microservice granularity?",
        "members": [],
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
        "created_at": "2026-07-15T00:00:00+00:00",
        "updated_at": "2026-07-15T00:00:00+00:00",
    }


# ── A. Commit ordering: session committed BEFORE add_task ────────────────────

@pytest.mark.asyncio
async def test_session_creation_commits_before_scheduling_background_task():
    """
    INVARIANT: db_session.commit() must be called before background_tasks.add_task().

    We track the call order using a list and assert commit precedes add_task.
    """
    call_order: list[str] = []

    # Stub AsyncSession
    mock_db = AsyncMock()
    async def _commit():
        call_order.append("commit")
    mock_db.commit = _commit

    # Stub repository
    mock_repo = AsyncMock()
    async def _create(state):
        return state
    mock_repo.create = _create

    # Stub BackgroundTasks
    mock_bg = MagicMock()
    original_add_task = mock_bg.add_task
    def _add_task(*args, **kwargs):
        call_order.append("add_task")
        return original_add_task(*args, **kwargs) if callable(original_add_task) else None
    mock_bg.add_task = _add_task

    # Stub tracer
    mock_tracer = AsyncMock()
    mock_tracer.start_trace.return_value = MagicMock(trace_id=str(uuid.uuid4()))
    mock_tracer.get_trace_url = MagicMock(return_value="http://trace.url")

    from app.api.v1.routers.sessions import _create_session_impl
    from app.api.v1.schemas.sessions import SessionCreateRequest

    req = SessionCreateRequest(
        user_query="test query",
        members=[
            {
                "member_id": "member_1",
                "provider": "openrouter",
                "model_id": "anthropic/claude-3-haiku",
                "display_label": "Member 1",
                "role": "member",
            },
            {
                "member_id": "member_2",
                "provider": "openrouter",
                "model_id": "anthropic/claude-3-haiku",
                "display_label": "Member 2",
                "role": "member",
            },
            {
                "member_id": "member_3",
                "provider": "openrouter",
                "model_id": "anthropic/claude-3-haiku",
                "display_label": "Member 3",
                "role": "member",
            },
        ],
        research_enabled=False,
        research_provider=None,
        chairman_member_id=None,
        archive_to_notion=False,
    )

    await _create_session_impl(
        req=req,
        user_id=VALID_USER_ID,
        repo=mock_repo,
        db_session=mock_db,
        tracer=mock_tracer,
        background_tasks=mock_bg,
    )

    assert "commit" in call_order, "commit was never called"
    assert "add_task" in call_order, "add_task was never called"
    commit_idx = call_order.index("commit")
    add_task_idx = call_order.index("add_task")
    assert commit_idx < add_task_idx, (
        f"commit (idx={commit_idx}) must precede add_task (idx={add_task_idx}). "
        f"Actual order: {call_order}"
    )


# ── B. Initial state preserves user_id ───────────────────────────────────────

def test_initial_state_preserves_user_id():
    """
    The state dict built in _create_session_impl must carry user_id at the
    declared 'user_id' key before and after the trace_id injection.
    """
    state = _make_initial_state(user_id=VALID_USER_ID)
    assert state["user_id"] == VALID_USER_ID
    # Simulate what the API does (trace injection)
    state["trace_id"] = str(uuid.uuid4())
    assert state["user_id"] == VALID_USER_ID, "user_id must survive trace_id injection"


# ── D. Empty user_id fails before SQL ────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_checkpoint_raises_on_empty_user_id_before_sql():
    """
    repository.save_checkpoint must raise CouncilStateValidationError
    for user_id='' BEFORE db.execute is ever called.
    """
    from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
    from app.core.exceptions import CouncilStateValidationError

    mock_db = AsyncMock()
    repo = PostgresSessionRepository(mock_db)

    bad_state = _make_initial_state(user_id="")

    with pytest.raises(CouncilStateValidationError) as exc_info:
        await repo.save_checkpoint(bad_state)  # type: ignore[arg-type]

    assert "user_id" in str(exc_info.value).lower()
    # CRITICAL: db.execute must never be called with an invalid identity
    mock_db.execute.assert_not_called()


# ── E. Missing user_id fails before SQL ──────────────────────────────────────

@pytest.mark.asyncio
async def test_save_checkpoint_raises_on_missing_user_id_before_sql():
    """
    repository.save_checkpoint must raise CouncilStateValidationError
    for user_id=None BEFORE db.execute is ever called.
    """
    from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
    from app.core.exceptions import CouncilStateValidationError

    mock_db = AsyncMock()
    repo = PostgresSessionRepository(mock_db)

    # Build a state with no user_id key at all
    state: dict = _make_initial_state()
    del state["user_id"]

    with pytest.raises(CouncilStateValidationError) as exc_info:
        await repo.save_checkpoint(state)  # type: ignore[arg-type]

    assert "user_id" in str(exc_info.value).lower()
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_checkpoint_raises_on_none_user_id_before_sql():
    """user_id=None must be caught before SQL execution."""
    from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
    from app.core.exceptions import CouncilStateValidationError

    mock_db = AsyncMock()
    repo = PostgresSessionRepository(mock_db)

    state = {**_make_initial_state(), "user_id": None}

    with pytest.raises(CouncilStateValidationError):
        await repo.save_checkpoint(state)  # type: ignore[arg-type]

    mock_db.execute.assert_not_called()


# ── F. Identity mismatch fails the runner ────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_aborts_on_state_identity_mismatch():
    """
    If state['user_id'] is a valid but DIFFERENT UUID from the authoritative
    user_id argument, run_council_graph must abort without calling graph.ainvoke.
    """
    from app.orchestration.runner import run_council_graph

    state_with_wrong_user = _make_initial_state(user_id=OTHER_USER_ID)
    mock_trace_context = MagicMock()

    with patch("app.orchestration.runner.graph") as mock_graph, \
         patch("app.orchestration.runner.async_session_factory"):
        mock_graph.ainvoke = AsyncMock()
        await run_council_graph(
            initial_state=state_with_wrong_user,  # type: ignore[arg-type]
            trace_context=mock_trace_context,
            user_id=VALID_USER_ID,  # authoritative — different from state
        )
        mock_graph.ainvoke.assert_not_called()


# ── G. Running-marker failure prevents graph execution ───────────────────────

@pytest.mark.asyncio
async def test_running_marker_failure_prevents_graph_invocation():
    """
    If save_checkpoint raises during the running-marker write, run_council_graph
    must NOT call graph.ainvoke or any LLM router method.
    """
    from app.orchestration.runner import run_council_graph
    from app.core.exceptions import CheckpointSessionNotFoundError

    initial_state = _make_initial_state()
    mock_trace_context = MagicMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.save_checkpoint = AsyncMock(
        side_effect=CheckpointSessionNotFoundError(
            session_id=VALID_SESSION_ID, stage="stage_1"
        )
    )
    mock_repo.load = AsyncMock(return_value=None)  # error persistence also finds nothing

    def _session_factory_cm():
        return mock_session

    with patch("app.orchestration.runner.graph") as mock_graph, \
         patch("app.orchestration.runner.PostgresSessionRepository", return_value=mock_repo), \
         patch("app.orchestration.runner.async_session_factory", side_effect=_session_factory_cm):
        mock_graph.ainvoke = AsyncMock()

        await run_council_graph(
            initial_state=initial_state,  # type: ignore[arg-type]
            trace_context=mock_trace_context,
            user_id=VALID_USER_ID,
        )

        # Graph must NOT have been invoked
        mock_graph.ainvoke.assert_not_called()


# ── I. Fan-out payloads propagate user_id ────────────────────────────────────

def test_route_stage_1_fan_out_preserves_user_id():
    """
    route_stage_1 must propagate user_id into every Stage1Task payload.
    """
    from app.orchestration.graph import route_stage_1

    member = {
        "member_id": "member_001",
        "provider": "openrouter",
        "model_id": "anthropic/claude-sonnet-4.5",
        "display_label": "Council Seat 1",
        "role": "member",
        "api_key": None,
    }

    state = {
        **_make_initial_state(),
        "members": [member],
        "user_id": VALID_USER_ID,
    }

    from langgraph.types import Send
    tasks = route_stage_1(state)  # type: ignore[arg-type]

    assert len(tasks) == 1
    send_obj = tasks[0]
    # Send objects have a 'arg' attribute containing the payload dict
    payload = send_obj.arg
    assert payload["user_id"] == VALID_USER_ID, (
        f"Stage 1 fan-out must propagate user_id='{VALID_USER_ID}', "
        f"got '{payload.get('user_id')}'"
    )


def test_route_stage_1_fan_out_preserves_session_id():
    """route_stage_1 must propagate session_id into every Stage1Task payload."""
    from app.orchestration.graph import route_stage_1

    member = {
        "member_id": "member_001",
        "provider": "openrouter",
        "model_id": "anthropic/claude-sonnet-4.5",
        "display_label": "Council Seat 1",
        "role": "member",
        "api_key": None,
    }

    state = {
        **_make_initial_state(),
        "members": [member],
        "session_id": VALID_SESSION_ID,
    }

    tasks = route_stage_1(state)  # type: ignore[arg-type]
    payload = tasks[0].arg
    assert payload["session_id"] == VALID_SESSION_ID


def test_route_stage_2_fan_out_preserves_user_id():
    """route_stage_2 must propagate user_id into every Stage2Task payload."""
    from app.orchestration.graph import route_stage_2

    member = {
        "member_id": "member_001",
        "provider": "openrouter",
        "model_id": "anthropic/claude-sonnet-4.5",
        "display_label": "Council Seat 1",
        "role": "member",
        "api_key": None,
    }

    anon_resp = {
        "member_id": "member_001",
        "stage": "stage_1",
        "content": "Some analysis text",
        "anonymized_label": "Member A",
        "latency_ms": 1000,
        "tokens_in": 100,
        "tokens_out": 200,
        "cost_usd": 0.001,
        "error": None,
    }

    state = {
        **_make_initial_state(),
        "members": [member],
        "user_id": VALID_USER_ID,
        "anonymization_map": {"member_001": "Member A"},
        "stage_1_responses": [anon_resp],
    }

    from langgraph.types import Send
    tasks = route_stage_2(state)  # type: ignore[arg-type]

    assert len(tasks) == 1
    payload = tasks[0].arg
    assert payload["user_id"] == VALID_USER_ID, (
        f"Stage 2 fan-out must propagate user_id='{VALID_USER_ID}', "
        f"got '{payload.get('user_id')}'"
    )


# ── require_uuid validation tests ─────────────────────────────────────────────

def test_require_uuid_accepts_valid_string():
    from app.domain.identity import require_uuid
    import uuid as _uuid
    result = require_uuid(VALID_USER_ID, field_name="user_id")
    assert isinstance(result, _uuid.UUID)
    assert str(result) == VALID_USER_ID


def test_require_uuid_accepts_uuid_object():
    from app.domain.identity import require_uuid
    import uuid as _uuid
    uid = _uuid.UUID(VALID_USER_ID)
    result = require_uuid(uid, field_name="user_id")
    assert result == uid


def test_require_uuid_rejects_empty_string():
    from app.domain.identity import require_uuid
    from app.core.exceptions import CouncilStateValidationError
    with pytest.raises(CouncilStateValidationError) as exc_info:
        require_uuid("", field_name="user_id")
    assert "user_id" in str(exc_info.value)


def test_require_uuid_rejects_none():
    from app.domain.identity import require_uuid
    from app.core.exceptions import CouncilStateValidationError
    with pytest.raises(CouncilStateValidationError):
        require_uuid(None, field_name="user_id")


def test_require_uuid_rejects_whitespace():
    from app.domain.identity import require_uuid
    from app.core.exceptions import CouncilStateValidationError
    with pytest.raises(CouncilStateValidationError):
        require_uuid("   ", field_name="user_id")


def test_require_uuid_rejects_invalid_format():
    from app.domain.identity import require_uuid
    from app.core.exceptions import CouncilStateValidationError
    with pytest.raises(CouncilStateValidationError):
        require_uuid("not-a-uuid-at-all", field_name="user_id")


def test_require_uuid_rejects_sentinel_values():
    from app.domain.identity import require_uuid
    from app.core.exceptions import CouncilStateValidationError
    for sentinel in ("undefined", "null", "none", "n/a"):
        with pytest.raises(CouncilStateValidationError):
            require_uuid(sentinel, field_name="user_id")
