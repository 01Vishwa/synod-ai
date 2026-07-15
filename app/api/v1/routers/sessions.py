"""
api/v1/routers/sessions.py — Council Session orchestration endpoints.

Endpoints to create, list, retrieve, and stream Council sessions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.adapters.persistence.database import async_session_factory
from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
from app.api.v1.deps import CurrentUserId, CurrentUserIdSse, DbSession, SessionRepo, Tracer
from app.api.v1.schemas.sessions import (
    SessionCreateRequest,
    SessionListResponse,
    SessionResponse,
)
from app.domain.council_state import CouncilState
from app.orchestration.runner import run_council_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# ── SSE helpers ───────────────────────────────────────────────────────────────

# Sentinel used to distinguish "never set" from None (spec can legitimately be None)
_SENTINEL = object()


def _sse_event(event_type: str, payload: Any) -> dict[str, str]:
    """Serialize a typed SSE event for sse_starlette."""
    return {
        "event": event_type,
        "data": json.dumps(payload),
    }


# Fields excluded from state_delta events sent to the frontend.
# anonymization_map is server-only and must never leave the backend.
_STATE_DELTA_EXCLUDE = frozenset({"anonymization_map", "user_id", "_execution_status"})


def _safe_state_delta(state: CouncilState) -> dict[str, Any]:
    """Return a copy of state with server-only fields stripped."""
    return {k: v for k, v in state.items() if k not in _STATE_DELTA_EXCLUDE}


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: SessionCreateRequest,
    user_id: CurrentUserId,
    repo: SessionRepo,
    db_session: DbSession,
    tracer: Tracer,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Start a new council deliberation session.

    Initialises the state, saves it to Postgres, and spawns the LangGraph
    orchestrator in the background. The client connects to the /stream endpoint
    using the returned session_id to receive live updates.
    """
    try:
        return await _create_session_impl(req, user_id, repo, db_session, tracer, background_tasks)
    except HTTPException:
        raise  # let FastAPI handle 4xx as-is
    except Exception as exc:
        logger.exception(
            "create_session: unhandled exception — session could not be created. "
            "user_id=%s error=%s",
            user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "session_creation_failed",
                "message": "Failed to create session. Check server logs for details.",
            },
        ) from exc


async def _create_session_impl(
    req: SessionCreateRequest,
    user_id: str,
    repo: SessionRepo,
    db_session: AsyncSession,
    tracer: Tracer,
    background_tasks: BackgroundTasks,
) -> Any:
    """Core logic isolated for testability and clean error propagation.

    Transaction ordering invariant:
        INSERT → flush → COMMIT → add_task

    The background runner opens an independent AsyncSession. That session will
    only see committed rows. We must commit the session creation before we
    schedule the background task — otherwise the runner starts before the row
    is visible and every subsequent DB operation fails with "session not found".
    """
    session_id = str(uuid.uuid4())

    logger.info(
        "SESSION_CREATE_STARTED",
        extra={"session_id": session_id, "user_id": str(user_id)},
    )

    # Build initial domain state
    initial_state: CouncilState = {
        "session_id": session_id,
        "user_id": user_id,        # declared field — will survive LangGraph serialisation
        "trace_id": "",            # populated below
        "user_query": req.user_query,
        "members": [
            {
                "member_id": m.member_id,
                "provider": m.provider,
                "model_id": m.model_id,
                "display_label": m.display_label,
                "role": m.role,
                "api_key": m.api_key,
            }
            for m in req.members
        ],
        "stage": "stage_1",
        "research_enabled": req.research_enabled,
        "research_provider": req.research_provider,
        "research_digest": None,
        "stage_1_responses": [],
        "anonymization_map": {},
        "stage_2_responses": [],
        "rankings": [],
        "aggregate_scores": {},
        "chairman_member_id": req.chairman_member_id or "",
        "final_report_md": None,
        "citations": [],
        "notion_page_url": None,
        "dashboard_spec": None,
        "errors": [],
        "archive_to_notion": req.archive_to_notion,
        "session_status": "pending",
        "stage_1_status": "pending",
        "stage_2_status": "pending",
        "stage_3_status": "pending",
        "terminal_error": None,
        "successful_member_ids": [],
        "excluded_member_ids": [],
        "effective_chairman_id": req.chairman_member_id or "",
        "created_at": "",  # set by repository
        "updated_at": "",  # set by repository
    }

    # Start observability trace
    trace_context = await tracer.start_trace(
        name=f"Synod Council Session - {session_id}",
        session_id=session_id,
        user_id=user_id,
    )
    initial_state["trace_id"] = trace_context.trace_id

    # Persist the initial state (flush within the current UoW — not yet committed)
    persisted_state = await repo.create(initial_state)

    logger.info(
        "SESSION_ROW_FLUSHED",
        extra={"session_id": session_id, "user_id": str(user_id)},
    )

    # ── CRITICAL: commit BEFORE scheduling the background task ─────────────
    # FastAPI background tasks run in the same event-loop iteration as the
    # response, but the get_db() context manager only commits when the route
    # handler returns (after the response has been sent). Because the runner
    # opens an *independent* AsyncSession, it will not see the uncommitted row.
    #
    # Explicit commit here makes the row durable before add_task() is called.
    # SQLAlchemy is idempotent: the get_db() context manager will call commit()
    # again on clean exit, which is a no-op on an already-clean session.
    logger.info(
        "SESSION_CREATION_COMMIT_STARTED",
        extra={"session_id": session_id, "user_id": str(user_id)},
    )
    await db_session.commit()
    logger.info(
        "SESSION_CREATION_COMMITTED",
        extra={"session_id": session_id, "user_id": str(user_id)},
    )

    logger.info(
        "SESSION_CREATED",
        extra={
            "session_id": str(session_id),
            "user_id": str(user_id),
        },
    )

    logger.info(
        "COUNCIL_EXECUTION_SCHEDULING",
        extra={
            "session_id": str(session_id),
            "user_id": str(user_id),
        },
    )

    # Dispatch the LangGraph execution to a background task so this
    # HTTP endpoint returns immediately with the created session metadata.
    background_tasks.add_task(run_council_graph, persisted_state, trace_context, user_id)

    # Return the REST-friendly response schema
    return _state_to_response(persisted_state, tracer)



# ── Helpers ───────────────────────────────────────────────────────────────────

def _state_to_response(state: dict[str, Any], tracer: Any | None = None) -> SessionResponse:
    """
    Translate a raw CouncilState dict into the SessionResponse schema.

    CouncilState does NOT carry a `member_count` field — it must be derived
    from ``len(state["members"])``.  This function is the single place that
    does that mapping so callers never accidentally pass the raw dict to
    ``SessionResponse(**state)`` (which would crash with a ValidationError).
    """
    trace_url: str | None = None
    if tracer is not None:
        try:
            trace_url = tracer.get_trace_url(state.get("trace_id", ""))
        except Exception:  # noqa: BLE001
            pass

    # Sum costs from both stages
    total_cost = sum(
        r.get("cost_usd", 0.0)
        for r in (
            state.get("stage_1_responses", []) + state.get("stage_2_responses", [])
        )
    )

    return SessionResponse(
        session_id=state["session_id"],
        stage=state["stage"],
        user_query=state["user_query"],
        member_count=len(state.get("members", [])),  # derived — not stored in CouncilState
        members=state.get("members", []),
        research_enabled=state.get("research_enabled", False),
        research_provider=state.get("research_provider"),
        stage_1_responses=state.get("stage_1_responses", []),
        stage_2_responses=state.get("stage_2_responses", []),
        rankings=state.get("rankings", []),
        aggregate_scores=state.get("aggregate_scores", {}),
        chairman_member_id=state.get("chairman_member_id") or None,
        final_report_md=state.get("final_report_md"),
        citations=state.get("citations", []),
        total_cost_usd=round(total_cost, 6),
        notion_page_url=state.get("notion_page_url"),
        trace_url=trace_url,
        dashboard_spec=state.get("dashboard_spec"),
        session_status=state.get("session_status"),
        stage_1_status=state.get("stage_1_status"),
        stage_2_status=state.get("stage_2_status"),
        stage_3_status=state.get("stage_3_status"),
        terminal_error=state.get("terminal_error"),
        successful_member_ids=state.get("successful_member_ids"),
        excluded_member_ids=state.get("excluded_member_ids"),
        effective_chairman_id=state.get("effective_chairman_id"),
        errors=state.get("errors", []),
        created_at=state.get("created_at", ""),
        updated_at=state.get("updated_at", ""),
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user_id: CurrentUserId,
    repo: SessionRepo,
    limit: int = 20,
    offset: int = 0,
) -> Any:
    """Paginated list of previous council sessions."""
    states = await repo.list_sessions(user_id=user_id, limit=limit, offset=offset)

    # We don't have a count query in the current repo interface, so we return a simplified total
    # For a real implementation, we'd add a `count_sessions` method to the repository.
    return SessionListResponse(
        items=[
            {
                "session_id": s["session_id"],
                "stage": s["stage"],
                "user_query": s["user_query"],
                "member_count": len(s.get("members", [])),
                "total_cost_usd": sum(
                    r.get("cost_usd", 0)
                    for r in s.get("stage_1_responses", []) + s.get("stage_2_responses", [])
                ),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "notion_page_url": s.get("notion_page_url"),
            }
            for s in states
        ],
        total=offset + len(states) + (1 if len(states) == limit else 0),
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: CurrentUserId,
    repo: SessionRepo,
    tracer: Tracer,
) -> Any:
    """Retrieve the full state of a session."""
    state = await repo.load(session_id, user_id=user_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")

    return _state_to_response(state, tracer)


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    user_id: CurrentUserIdSse,
) -> EventSourceResponse:
    """
    Server-Sent Events (SSE) endpoint for live council updates.

    Polls the session repository every 500 ms and emits typed SSE events:
      - ``state_delta``           — emitted on every stage transition
      - ``dashboard_spec_update`` — emitted whenever dashboard_spec changes
      - ``session.failed``        — emitted when the session reaches stage=error
      - ``session.completed``     — emitted when the session reaches stage=done
      - ``session.stream_timeout``— emitted when SSE max idle time is reached
      - ``done``                  — emitted on any terminal condition (legacy compat)

    Design: Each polling cycle opens and closes its own short-lived DB session
    so we never hold a single SQLAlchemy transaction open for 5 minutes. This
    prevents connection pool exhaustion and avoids stale transaction reads.

    SSE Auth: The JWT is passed via ?token= query parameter because the browser's
    native EventSource API cannot attach custom headers. The token is verified via
    the same JWKS path as the Authorization header — same security level.

    Security: The ?token= query parameter is NOT logged (LoggingMiddleware only
    logs request.url.path, not the full URL with query string).
    """
    # ── Auth guard — verify session ownership before opening the stream ───
    async with async_session_factory() as check_session:
        repo = PostgresSessionRepository(check_session)
        initial = await repo.load(session_id, user_id=user_id)

    if not initial:
        raise HTTPException(status_code=404, detail="Session not found.")

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        _INITIAL_POLL_SECS = 2.0
        _MAX_POLL_SECS = 10.0
        _MAX_IDLE_TIME_SECS = 300.0   # 5 minutes max wait
        _TERMINAL_STAGES = {"done", "error"}

        prev_stage: str = ""
        prev_dashboard_spec: Any = _SENTINEL

        current_poll_interval = _INITIAL_POLL_SECS
        idle_time_secs = 0.0

        # Emit initial state so the client has a starting snapshot.
        # Each load uses a fresh short-lived session — no long-lived transaction.
        async with async_session_factory() as poll_session:
            repo = PostgresSessionRepository(poll_session)
            snapshot = await repo.load(session_id, user_id=user_id)

        if snapshot:
            yield _sse_event("state_delta", _safe_state_delta(snapshot))
            prev_stage = snapshot.get("stage", "")
            prev_dashboard_spec = snapshot.get("dashboard_spec")

            # If the session was already terminal on first load, emit and exit.
            if prev_stage in _TERMINAL_STAGES:
                for ev in _emit_terminal(snapshot, prev_stage):
                    yield ev
                return

        while idle_time_secs < _MAX_IDLE_TIME_SECS:
            await asyncio.sleep(current_poll_interval)

            # ── Short-lived session per poll ──────────────────────────────
            # We open and close a new session for every poll cycle.
            # This avoids holding a DB connection open for the full 5-minute
            # SSE lifetime and ensures we always read the latest committed data.
            try:
                async with async_session_factory() as poll_session:
                    repo = PostgresSessionRepository(poll_session)
                    state = await repo.load(session_id, user_id=user_id)
            except asyncio.CancelledError:
                logger.info("stream_session: connection cancelled by client for %s", session_id)
                raise
            except Exception as exc:
                logger.warning(
                    "stream_session: repo.load failed for %s: %s", session_id, exc
                )
                idle_time_secs += current_poll_interval
                current_poll_interval = min(current_poll_interval * 1.5, _MAX_POLL_SECS)
                continue

            if not state:
                idle_time_secs += current_poll_interval
                current_poll_interval = min(current_poll_interval * 1.5, _MAX_POLL_SECS)
                continue

            current_stage: str = state.get("stage", "")
            current_spec: Any = state.get("dashboard_spec")

            state_changed = (current_stage != prev_stage) or (current_spec != prev_dashboard_spec)

            # ── Stage change → emit state_delta ──────────────────────────
            if current_stage != prev_stage:
                logger.debug(
                    "stream_session: stage transition %s → %s for session %s",
                    prev_stage,
                    current_stage,
                    session_id,
                )
                yield _sse_event("state_delta", _safe_state_delta(state))
                prev_stage = current_stage

            # ── dashboard_spec changed → emit dashboard_spec_update ───────
            if current_spec != prev_dashboard_spec:
                if current_spec is not None:
                    logger.info(
                        "stream_session: dashboard_spec_update for session %s "
                        "(widgets=%d)",
                        session_id,
                        len(current_spec.get("elements", {})),
                    )
                    yield _sse_event(
                        "dashboard_spec_update",
                        {"dashboard_spec": current_spec},
                    )
                prev_dashboard_spec = current_spec

            if state_changed:
                idle_time_secs = 0.0
                current_poll_interval = _INITIAL_POLL_SECS  # reset backoff on activity
            else:
                idle_time_secs += current_poll_interval
                current_poll_interval = min(current_poll_interval * 1.5, _MAX_POLL_SECS)

            # ── Terminal stage → emit structured terminal event and close ──
            if current_stage in _TERMINAL_STAGES:
                logger.info(
                    "stream_session: session %s reached terminal stage '%s' — closing SSE",
                    session_id,
                    current_stage,
                )
                for ev in _emit_terminal(state, current_stage):
                    yield ev
                return

        # ── Max idle cap reached ──────────────────────────────────────────
        # The session is still running (or stuck). Emit a structured timeout
        # event so the frontend can show an error instead of an infinite spinner.
        logger.warning(
            "stream_session: max idle time reached for session %s — closing SSE",
            session_id,
        )
        yield _sse_event(
            "session.stream_timeout",
            {
                "session_id": session_id,
                "stage": prev_stage or "stage_1",
                "error": {
                    "code": "STREAM_TIMEOUT",
                    "message": (
                        "The session stream timed out waiting for a state change. "
                        "The background worker may have failed silently. "
                        "Reload the page to see the latest session state."
                    ),
                },
            },
        )
        # Also emit the legacy done event for backwards compat
        yield _sse_event("done", {"status": "timeout"})

    return EventSourceResponse(event_generator())


def _emit_terminal(state: dict[str, Any], stage: str) -> list[dict[str, str]]:
    """
    Return a list of structured SSE events for a terminal session state.

    Returns both the typed semantic event (session.completed / session.failed)
    and the legacy 'done' event for backwards compatibility with older clients.

    Returns a list (not a generator) so it can be iterated inside an async
    generator without triggering the 'yield from inside async function' error.
    """
    events: list[dict[str, str]] = []

    if stage == "error":
        # Extract the most recent error for the frontend error display
        errors = state.get("errors", []) or []
        last_error = errors[-1] if errors else {}
        error_message = (
            last_error.get("message", "An unexpected error occurred during council execution.")
            if isinstance(last_error, dict)
            else str(last_error)
        )
        # Sanitize: never expose stack traces beyond 500 chars
        if len(error_message) > 500:
            error_message = error_message[:500] + "…"

        events.append(_sse_event(
            "session.failed",
            {
                "session_id": state.get("session_id", ""),
                "stage": stage,
                "state": "failed",
                "error": {
                    "code": "EXECUTION_FAILED",
                    "message": error_message,
                },
            },
        ))
        # Legacy compat
        events.append(_sse_event("done", {"status": "error"}))
    else:
        events.append(_sse_event(
            "session.completed",
            {
                "session_id": state.get("session_id", ""),
                "stage": stage,
                "state": "completed",
            },
        ))
        # Legacy compat
        events.append(_sse_event("done", {"status": "done"}))

    return events


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user_id: CurrentUserId,
    repo: SessionRepo,
) -> None:
    """Soft-delete a session."""
    state = await repo.load(session_id, user_id=user_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")

    await repo.delete(session_id, user_id=user_id)
