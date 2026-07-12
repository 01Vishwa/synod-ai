"""
api/v1/routers/observability.py — Trace URL fetching.

Endpoint to retrieve the deep-link URL to LangSmith for a given trace ID.
This allows the frontend to show a "View Trace" button for completed sessions.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.v1.deps import Tracer

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/trace/{trace_id}/url")
async def get_trace_url(
    trace_id: str,
    tracer: Tracer,
) -> dict[str, str]:
    """
    Get the deep-link URL into the LangSmith project for a specific trace.
    Returns 404 if tracing is disabled or not configured.
    """
    url = tracer.get_trace_url(trace_id)
    if not url:
        raise HTTPException(
            status_code=404,
            detail="Tracing is disabled or trace URL is not available.",
        )
    return {"trace_url": url}
