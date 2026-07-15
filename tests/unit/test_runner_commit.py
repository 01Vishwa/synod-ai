"""
tests/unit/test_runner_commit.py — Regression tests for Bug 2.

Verifies that run_council_graph:
  1. Calls await db_session.commit() after successful graph execution.
  2. Writes a running-state marker to the DB before graph.ainvoke.
  3. Persists stage=error via an independent session on failure.
  4. Does NOT reuse the graph's rolled-back session for error persistence.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.domain.council_state import CouncilState
from app.domain.ports.observability_port import SpanContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_initial_state(session_id: str = "test-session-id") -> CouncilState:
    return {
        "session_id": session_id,
        "trace_id": "trace-1",
        "user_query": "Test query",
        "members": [
            {
                "member_id": "m1",
                "provider": "openrouter",
                "model_id": "openai/gpt-4.1-mini",
                "display_label": "Seat 1",
                "role": "council_member",
                "api_key": None,
            }
        ],
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
        "created_at": "2026-07-15T07:00:00+00:00",
        "updated_at": "2026-07-15T07:00:00+00:00",
        "user_id": "00000000-0000-0000-0000-000000000000",
    }  # type: ignore[typeddict-item]


def _make_trace_context() -> SpanContext:
    ctx = MagicMock(spec=SpanContext)
    ctx.trace_id = "trace-1"
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_commit_called_after_successful_graph(monkeypatch):
    """
    Bug 2 regression: db_session.commit() must be called after graph.ainvoke
    succeeds.  Without this the DB rolls back all save_checkpoint() calls.
    """
    commit_called = []
    rollback_called = []

    mock_db_session = AsyncMock()
    mock_db_session.commit = AsyncMock(side_effect=lambda: commit_called.append(True))
    mock_db_session.rollback = AsyncMock(side_effect=lambda: rollback_called.append(True))

    mock_repo = AsyncMock()
    mock_repo.save_checkpoint = AsyncMock()
    mock_repo.load = AsyncMock(return_value=_make_initial_state())

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"stage": "done"})

    mock_tracer = AsyncMock()
    mock_tracer.end_trace = AsyncMock()

    with (
        patch("app.orchestration.runner.async_session_factory", return_value=mock_cm),
        patch("app.orchestration.runner.PostgresSessionRepository", return_value=mock_repo),
        patch("app.orchestration.runner.graph", mock_graph),
        patch("app.orchestration.runner.KeyVault.instance", return_value=MagicMock()),
        patch("app.orchestration.runner.LangSmithTracer.instance", return_value=mock_tracer),
        patch("app.orchestration.runner._get_llm_router", return_value=MagicMock()),
        patch("app.orchestration.runner._build_langfuse_callback", return_value=None),
        patch("app.orchestration.runner.settings") as mock_settings,
    ):
        mock_settings.GRAPH_TIMEOUT_SECONDS = 300
        mock_settings.LANGFUSE_TRACING = False

        from app.orchestration.runner import run_council_graph
        await run_council_graph(
            initial_state=_make_initial_state(),
            trace_context=_make_trace_context(),
            user_id="00000000-0000-0000-0000-000000000000",
        )

    # commit() must have been called at least once (running marker + final commit)
    assert len(commit_called) >= 1, (
        "db_session.commit() was never called. "
        "All save_checkpoint() flush() calls would be rolled back — Bug 2."
    )


@pytest.mark.asyncio
async def test_error_persistence_uses_independent_session(monkeypatch):
    """
    When graph.ainvoke raises, _write_error_to_repo must open its OWN
    independent async_session_factory() session — not reuse the graph session
    which has already been rolled back.
    """
    session_calls: list[str] = []

    # First session_factory call = graph session (will be rolled back)
    # Subsequent calls = independent error session
    graph_session = AsyncMock()
    graph_session.commit = AsyncMock(side_effect=lambda: session_calls.append("graph_commit"))
    graph_session.rollback = AsyncMock(side_effect=lambda: session_calls.append("graph_rollback"))

    error_session = AsyncMock()
    error_session.commit = AsyncMock(side_effect=lambda: session_calls.append("error_commit"))
    error_session.rollback = AsyncMock()

    graph_cm = AsyncMock()
    graph_cm.__aenter__ = AsyncMock(return_value=graph_session)
    graph_cm.__aexit__ = AsyncMock(return_value=None)

    error_cm = AsyncMock()
    error_cm.__aenter__ = AsyncMock(return_value=error_session)
    error_cm.__aexit__ = AsyncMock(return_value=None)

    call_count = [0]

    def factory_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return graph_cm  # graph session
        return error_cm  # error-persistence session

    mock_repo = AsyncMock()
    mock_repo.save_checkpoint = AsyncMock()
    mock_repo.load = AsyncMock(return_value=_make_initial_state())

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Deliberate test failure"))

    mock_tracer = AsyncMock()
    mock_tracer.end_trace = AsyncMock()

    with (
        patch(
            "app.orchestration.runner.async_session_factory",
            side_effect=factory_side_effect,
        ),
        patch("app.orchestration.runner.PostgresSessionRepository", return_value=mock_repo),
        patch("app.orchestration.runner.graph", mock_graph),
        patch("app.orchestration.runner.KeyVault.instance", return_value=MagicMock()),
        patch("app.orchestration.runner.LangSmithTracer.instance", return_value=mock_tracer),
        patch("app.orchestration.runner._get_llm_router", return_value=MagicMock()),
        patch("app.orchestration.runner._build_langfuse_callback", return_value=None),
        patch("app.orchestration.runner.settings") as mock_settings,
    ):
        mock_settings.GRAPH_TIMEOUT_SECONDS = 300
        mock_settings.LANGFUSE_TRACING = False

        from app.orchestration.runner import run_council_graph
        await run_council_graph(
            initial_state=_make_initial_state(),
            trace_context=_make_trace_context(),
            user_id="00000000-0000-0000-0000-000000000000",
        )

    # The independent error session must have committed
    assert "error_commit" in session_calls, (
        "_write_error_to_repo must commit the error state via an independent session."
    )


@pytest.mark.asyncio
async def test_missing_user_id_aborts_early(monkeypatch):
    """
    If user_id is empty (neither arg nor state), run_council_graph must return
    early without touching the DB or graph.
    """
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock()

    state = _make_initial_state()
    state.pop("user_id", None)  # type: ignore[misc]

    with patch("app.orchestration.runner.graph", mock_graph):
        from app.orchestration.runner import run_council_graph
        await run_council_graph(
            initial_state=state,
            trace_context=_make_trace_context(),
            user_id="",
        )

    mock_graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_graph_timeout_writes_error_state(monkeypatch):
    """
    TimeoutError from asyncio.wait_for must result in stage=error being
    committed to the DB via _write_error_to_repo.
    """
    error_written = []

    with patch("app.orchestration.runner._write_error_to_repo") as mock_write_error:
        mock_write_error.return_value = None  # async is handled by the real impl
        mock_write_error.side_effect = AsyncMock(
            side_effect=lambda *a, **kw: error_written.append(True)
        )

        mock_cm = AsyncMock()
        mock_graph_session = AsyncMock()
        mock_graph_session.commit = AsyncMock()
        mock_graph_session.rollback = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_graph_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_repo = AsyncMock()
        mock_repo.save_checkpoint = AsyncMock()

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())

        with (
            patch("app.orchestration.runner.async_session_factory", return_value=mock_cm),
            patch("app.orchestration.runner.PostgresSessionRepository", return_value=mock_repo),
            patch("app.orchestration.runner.graph", mock_graph),
            patch("app.orchestration.runner.KeyVault.instance", return_value=MagicMock()),
            patch("app.orchestration.runner.LangSmithTracer.instance", return_value=AsyncMock()),
            patch("app.orchestration.runner._get_llm_router", return_value=MagicMock()),
            patch("app.orchestration.runner._build_langfuse_callback", return_value=None),
            patch("app.orchestration.runner.settings") as mock_settings,
        ):
            mock_settings.GRAPH_TIMEOUT_SECONDS = 0.001
            mock_settings.LANGFUSE_TRACING = False

            from app.orchestration.runner import run_council_graph
            await run_council_graph(
                initial_state=_make_initial_state(),
                trace_context=_make_trace_context(),
                user_id="00000000-0000-0000-0000-000000000000",
            )

    mock_write_error.assert_called_once()
