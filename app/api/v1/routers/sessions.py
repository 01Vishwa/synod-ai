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

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.api.v1.deps import CurrentUserId, SessionRepo, Tracer
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
_STATE_DELTA_EXCLUDE = frozenset({"anonymization_map", "user_id"})


def _safe_state_delta(state: CouncilState) -> dict[str, Any]:
    """Return a copy of state with server-only fields stripped."""
    return {k: v for k, v in state.items() if k not in _STATE_DELTA_EXCLUDE}

@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: SessionCreateRequest,
    user_id: CurrentUserId,
    repo: SessionRepo,
    tracer: Tracer,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Start a new council deliberation session.

    Initialises the state, saves it to Postgres, and spawns the LangGraph
    orchestrator in the background. The client connects to the /stream endpoint
    using the returned session_id to receive live updates.
    """
    session_id = str(uuid.uuid4())

    # Build initial domain state
    initial_state: CouncilState = {
        "session_id": session_id,
        "trace_id": "",  # populated below
        "user_query": req.user_query,
        "members": [
            {
                "member_id": m.member_id,
                "provider": m.provider,
                "model_id": m.model_id,
                "display_label": m.display_label,
                "role": m.role,
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
        "chairman_member_id": req.pinned_chairman_member_id or "",
        "final_report_md": None,
        "citations": [],
        "notion_page_url": None,
        "dashboard_spec": None,
        "errors": [],
        "archive_to_notion": req.archive_to_notion,
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

    # Add user context so the repository can properly associate the session
    initial_state["user_id"] = user_id  # type: ignore

    # Persist the initial state
    persisted_state = await repo.create(initial_state)

    # Dispatch the LangGraph execution to a background task so this
    # HTTP endpoint returns immediately with the created session metadata.
    background_tasks.add_task(run_council_graph, persisted_state, trace_context)

    # Return the REST-friendly response schema
    return SessionResponse(**persisted_state)


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

        
    response = SessionResponse(**state)
    response.trace_url = tracer.get_trace_url(state["trace_id"])
    return response


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    user_id: CurrentUserId,
    repo: SessionRepo,
) -> EventSourceResponse:
    """
    Server-Sent Events (SSE) endpoint for live council updates.

    Polls the session repository every 500 ms and emits typed SSE events:
      - ``state_delta``           — emitted on every stage transition
      - ``dashboard_spec_update`` — emitted whenever dashboard_spec changes
      - ``done``                  — emitted once the session reaches a terminal state

    The graph runs as a background task (started by POST /sessions). This endpoint
    observes state transitions by polling the DB checkpoint written after each node.

    Design: polling avoids re-architecting the background-task runner and is
    imperceptible to users since each LLM call takes multiple seconds.
    """
    # ── Auth guard ────────────────────────────────────────────────────────────
    initial = await repo.load(session_id, user_id=user_id)
    if not initial:
        raise HTTPException(status_code=404, detail="Session not found.")

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        _POLL_INTERVAL_SECS = 0.5
        _TERMINAL_STAGES = {"done", "error"}
        _MAX_IDLE_POLLS = 600   # 5 minutes at 500 ms — hard cap against hung sessions

        prev_stage: str = ""
        prev_dashboard_spec: Any = _SENTINEL
        idle_polls: int = 0

        # Emit initial state so the client has a starting snapshot
        snapshot = await repo.load(session_id)
        if snapshot:
            yield _sse_event("state_delta", _safe_state_delta(snapshot))
            prev_stage = snapshot.get("stage", "")
            prev_dashboard_spec = snapshot.get("dashboard_spec")

        while idle_polls < _MAX_IDLE_POLLS:
            await asyncio.sleep(_POLL_INTERVAL_SECS)

            try:
                state = await repo.load(session_id, user_id=user_id)
            except Exception as exc:
                logger.warning(
                    "stream_session: repo.load failed for %s: %s", session_id, exc
                )
                idle_polls += 1
                continue

            if not state:
                idle_polls += 1
                continue

            current_stage: str = state.get("stage", "")
            current_spec: Any = state.get("dashboard_spec")

            # ── Stage change → emit state_delta ──────────────────────────────
            if current_stage != prev_stage:
                logger.debug(
                    "stream_session: stage transition %s → %s for session %s",
                    prev_stage,
                    current_stage,
                    session_id,
                )
                yield _sse_event("state_delta", _safe_state_delta(state))
                prev_stage = current_stage
                idle_polls = 0  # reset idle counter on real activity

            # ── dashboard_spec changed → emit dashboard_spec_update ───────────
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
                idle_polls = 0

            # ── Terminal stage → emit done and close ──────────────────────────
            if current_stage in _TERMINAL_STAGES:
                logger.info(
                    "stream_session: session %s reached terminal stage '%s' — closing SSE",
                    session_id,
                    current_stage,
                )
                yield _sse_event("done", {"status": current_stage})
                return

            idle_polls += 1

        # Hard cap reached — close the stream gracefully
        logger.warning(
            "stream_session: max idle polls reached for session %s — closing SSE",
            session_id,
        )
        yield _sse_event("done", {"status": "timeout"})

    return EventSourceResponse(event_generator())


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
