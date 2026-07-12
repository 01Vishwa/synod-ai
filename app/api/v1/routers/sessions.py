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
    state = await repo.load(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    # Security check: ensure the user owns this session
    if state.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
        
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
    
    Yields JSON state deltas as the LangGraph orchestrator advances through stages.
    """
    # Verify access first
    state = await repo.load(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
    if state.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        # Implementation Note:
        # Once LangGraph is integrated, this will `async for` over the graph's async streamer.
        # For now, this is a placeholder that yields the current state and closes.
        current_state = await repo.load(session_id)
        if current_state:
            yield {
                "event": "state_update",
                "data": json.dumps(current_state),
            }
        
        if current_state and current_state["stage"] in ("done", "error"):
            yield {
                "event": "close",
                "data": json.dumps({"status": "complete"}),
            }

    return EventSourceResponse(event_generator())


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user_id: CurrentUserId,
    repo: SessionRepo,
) -> None:
    """Soft-delete a session."""
    state = await repo.load(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
    if state.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
        
    await repo.delete(session_id)
