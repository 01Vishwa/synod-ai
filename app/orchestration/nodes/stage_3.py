"""
orchestration/nodes/stage_3.py — Chairman Synthesis Node.

Executes Stage 3: The elected Chairman receives all de-anonymised opinions and
peer reviews, and produces a final consolidated Markdown report.

Streaming:
  - Uses llm_router.stream_chat to yield token deltas.
  - Publishes ChairmanStarted, ChairmanStreamChunk, ChairmanCompleted, and
    SessionCompleted (or SessionFailed on error) to the session EventBus so
    the SSE endpoint can relay the report to the browser token by token.
  - The event bus is closed after a short delay (asyncio.create_task) once
    all subscribers have had time to drain.

LangGraph topology:
  - stage_3_node is a single node — no fan-out.
  - finish_session (blocking, in graph.py) handles the final checkpoint and
    sets stage="done" / session_status="completed".
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.core.event_bus import (
    ChairmanCompleted,
    ChairmanStarted,
    ChairmanStreamChunk,
    SessionCompleted,
    SessionFailed,
    close_bus,
    get_or_create_bus,
)
from app.core.exceptions import AuthenticationError, FallbackExhaustedError
from app.domain.council_state import CouncilState
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import get_deps
from app.orchestration.utils import _sanitize_error, fetch_decrypted_key

logger = logging.getLogger(__name__)


def _build_prompt(state: CouncilState) -> str:
    prompt = f"Original Query: {state['user_query']}\n\n"
    
    if state.get("research_digest"):
        prompt += "--- Background Research ---\n"
        prompt += state["research_digest"]["summary"] + "\n\n"

    prompt += "--- Stage 1: Initial Opinions ---\n"
    # Create a lookup for display labels
    labels = {m["member_id"]: m["display_label"] for m in state["members"]}
    
    for resp in state["stage_1_responses"]:
        if not resp["error"] and resp["content"]:
            label = labels.get(resp["member_id"], "Unknown Member")
            prompt += f"[{label}]:\n{resp['content']}\n\n"

    prompt += "--- Stage 2: Peer Review & Rankings ---\n"
    for resp in state["stage_2_responses"]:
        if not resp["error"] and resp["content"]:
            label = labels.get(resp["member_id"], "Unknown Member")
            prompt += f"[{label}'s Review]:\n{resp['content']}\n\n"

    prompt += (
        "You have been elected as the Chairman of this council based on your peer reviews.\n"
        "Your task is to synthesize the above deliberation into a single, comprehensive final report.\n\n"
        "Requirements:\n"
        "1. Write the report in clean Markdown format.\n"
        "2. Synthesize the differing viewpoints and highlight the strongest arguments.\n"
        "3. Produce a clear, actionable conclusion or summary based on the council's consensus (or highlight the core disagreement if no consensus exists).\n"
        "4. Do not include your internal chain-of-thought, just the final report.\n"
    )
    
    return prompt


async def _close_bus_after_delay(session_id: str, delay_s: float = 5.0) -> None:
    """
    Close the session event bus after a short delay.

    Gives all SSE subscribers time to drain the final events (ChairmanCompleted,
    SessionCompleted) before the bus is torn down.  Runs as asyncio.create_task
    so it never blocks the LangGraph node from returning.
    """
    await asyncio.sleep(delay_s)
    await close_bus(session_id)
    logger.debug("Stage 3: event bus closed for session %s (after %.1fs delay)", session_id, delay_s)


async def stage_3_node(state: CouncilState, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute the Chairman synthesis streaming LLM call.

    Event sequence emitted to the session bus:
      ChairmanStarted → ChairmanStreamChunk × N → ChairmanCompleted → SessionCompleted
      (or SessionFailed on error)
    """
    deps = get_deps(config)
    chairman_id = state["chairman_member_id"]
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    
    if not chairman_id:
        raise ValueError("Cannot execute Stage 3 without a Chairman.")

    # Find the chairman configuration
    member = next((m for m in state["members"] if m["member_id"] == chairman_id), None)
    if not member:
        raise ValueError(f"Chairman {chairman_id} not found in council members.")

    span = await deps.tracer.start_span(
        name=f"Stage 3 (Synthesis) - {member['display_label']}",
        parent=deps.root_span,
        metadata={"provider": member["provider"], "model_id": member["model_id"], "is_llm_call": True},
    )

    messages = [
        ChatMessage(role="system", content="You are the Chairman of an expert AI council."),
        ChatMessage(role="user", content=_build_prompt(state)),
    ]

    # ── Key fetch ──────────────────────────────────────────────────────────
    try:
        api_key = await fetch_decrypted_key(
            deps,
            state.get("user_id", ""),  # type: ignore[arg-type]
            member["provider"],
            session_id=session_id,
            member_id=chairman_id,
        )
    except Exception as exc:
        await deps.tracer.end_span(span, error=exc)
        error_msg = _sanitize_error(exc, member["provider"])
        bus = await get_or_create_bus(session_id)
        await bus.publish(SessionFailed(
            session_id=session_id,
            error=error_msg,
        ))
        asyncio.create_task(_close_bus_after_delay(session_id, delay_s=5.0))
        return {
            "errors": (state.get("errors") or []) + [{
                "member_id": chairman_id,
                "stage": "stage_3",
                "message": f"{type(exc).__name__}:{exc}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }

    # ── Streaming call with event-bus publishing ───────────────────────────
    bus = await get_or_create_bus(session_id)
    start_time = time.monotonic()
    accumulated = ""
    token_count = 0

    logger.info(
        "MODEL_REQUEST_START",
        extra={
            "session_id": session_id,
            "member_id": chairman_id,
            "provider": member["provider"],
            "model": member["model_id"],
        },
    )

    await bus.publish(ChairmanStarted(
        session_id=session_id,
        chairman_id=chairman_id,
    ))

    try:
        async for delta in deps.llm_router.stream_chat(
            member_config=member,
            messages=messages,
            user_id=state.get("user_id", ""),  # type: ignore[arg-type]
            api_key=api_key,
            timeout_s=120,  # Chairman synthesis gets a longer timeout
            temperature=0.5,
            session_id=session_id,
        ):
            accumulated += delta
            token_count += 1
            await bus.publish(ChairmanStreamChunk(
                session_id=session_id,
                delta=delta,
            ))

    except Exception as exc:
        error_msg = _sanitize_error(exc, member["provider"])
        logger.exception(
            "MODEL_REQUEST_FAILED",
            extra={
                "session_id": session_id,
                "member_id": chairman_id,
                "provider": member["provider"],
            },
        )
        await deps.tracer.end_span(span, error=exc)
        await bus.publish(SessionFailed(
            session_id=session_id,
            error=error_msg,
        ))
        asyncio.create_task(_close_bus_after_delay(session_id, delay_s=5.0))

        errors_entry: dict[str, Any] = {
            "member_id": chairman_id,
            "stage": "stage_3",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(exc, AuthenticationError):
            errors_entry["message"] = f"authentication_error:{exc}"
        elif isinstance(exc, FallbackExhaustedError):
            errors_entry["message"] = f"fallback_exhausted:{exc}"
        else:
            errors_entry["message"] = error_msg

        return {"errors": (state.get("errors") or []) + [errors_entry]}

    # ── Success path ───────────────────────────────────────────────────────
    latency_ms = int((time.monotonic() - start_time) * 1000)
    tokens_in_approx = sum(len(m.content) for m in messages) // 4

    logger.info(
        "MODEL_REQUEST_SUCCESS",
        extra={
            "session_id": session_id,
            "member_id": chairman_id,
            "provider": member["provider"],
        },
    )

    await deps.tracer.end_span(
        span,
        output={"content_length": len(accumulated)},
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        latency_ms=latency_ms,
        cost_usd=0.0,
    )

    # Citations: no extraction helper exists yet — return empty list.
    # When _extract_citations is implemented, swap in: citations = _extract_citations(accumulated)
    citations: list[dict] = []

    await bus.publish(ChairmanCompleted(session_id=session_id))
    await bus.publish(SessionCompleted(session_id=session_id))

    # Close the bus after a short delay to let subscribers drain the final events.
    asyncio.create_task(_close_bus_after_delay(session_id, delay_s=5.0))

    return {
        "final_report_md": accumulated,
        "citations": citations,
    }
