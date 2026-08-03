"""
orchestration/nodes/stage_1.py — First Opinions (Fan-out Node).

This node is mapped concurrently over every council member using LangGraph's
Send API. Each instance of this node runs in parallel to fetch one LLM's draft.

Streaming:
  - Uses llm_router.stream_chat to yield token deltas.
  - Publishes ProviderConnecting, FirstToken, StreamChunk, MemberCompleted,
    and MemberFailed events to the session EventBus so the SSE endpoint can
    relay them to the browser in real time.
  - DB persistence (_persist_member_response) is fire-and-forget — it does
    NOT block SSE delivery.

LangGraph topology:
  - The Send() fan-out is preserved exactly as-is.
  - validate_stage_1 (blocking) is still responsible for the stage-level
    checkpoint; no checkpoint is attempted inside this node.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core.runnables.config import RunnableConfig

from app.core.event_bus import (
    FirstToken,
    MemberCompleted,
    MemberFailed,
    ProviderConnecting,
    StreamChunk,
    get_or_create_bus,
)
from app.core.exceptions import AuthenticationError, FallbackExhaustedError
from app.domain.council_state import CouncilMemberConfig, MemberResponse, ResearchDigest
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import GraphDependencies, get_deps
from app.orchestration.utils import _sanitize_error, fetch_decrypted_key

logger = logging.getLogger(__name__)


class Stage1Task(TypedDict):
    """The payload sent to each parallel instance of the Stage 1 node."""
    member: CouncilMemberConfig
    user_query: str
    research_digest: ResearchDigest | None
    user_id: str
    session_id: str


def _build_prompt(query: str, research: ResearchDigest | None) -> str:
    prompt = "You are participating in a council deliberation.\n\n"
    if research:
        prompt += "Here is some preliminary research context to inform your response:\n"
        prompt += f"Summary: {research['summary']}\n"
        for idx, src in enumerate(research["sources"]):
            prompt += f"[{idx+1}] {src['title']} ({src['url']}): {src['snippet']}\n"
        prompt += "\n"
        
    prompt += f"Please provide your initial analysis and response to the following query:\n\n{query}\n\n"
    prompt += "Draft a clear, comprehensive, and well-reasoned argument."
    return prompt


async def _persist_member_response(
    deps: GraphDependencies,
    session_id: str,
    member_resp: MemberResponse,
) -> None:
    """
    Fire-and-forget: write the member response to the DB.

    Runs as asyncio.create_task so the SSE stream is not blocked waiting
    for the DB write to finish.  Errors are logged but never re-raised.
    """
    try:
        # Build a minimal checkpoint payload the repository understands.
        # We pass the single-member slice; validate_stage_1 will persist
        # the full stage checkpoint after all members complete.
        await deps.repository.save_member_response(session_id, member_resp)
    except AttributeError:
        # repository may not yet implement save_member_response — safe no-op
        pass
    except Exception as exc:
        logger.warning(
            "Stage 1: background DB persist failed for member %s session %s: %s",
            member_resp["member_id"],
            session_id,
            exc,
        )


async def stage_1_node(task: Stage1Task, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute a single streaming LLM call for Stage 1.

    Returns a dict with a single key ``stage_1_responses`` containing a list
    of one MemberResponse. The LangGraph state reducer aggregates these lists
    after all parallel Send() instances complete.

    Event sequence emitted to the session bus:
      ProviderConnecting → FirstToken → StreamChunk × N → MemberCompleted
      (or MemberFailed on error)
    """
    deps = get_deps(config)
    member = task["member"]
    member_id: str = member["member_id"]
    session_id: str = task.get("session_id", "")

    span = await deps.tracer.start_span(
        name=f"Stage 1 - {member['display_label']}",
        parent=deps.root_span,
        metadata={"provider": member["provider"], "model_id": member["model_id"], "is_llm_call": True},
    )

    messages = [
        ChatMessage(role="system", content="You are an expert AI council member."),
        ChatMessage(role="user", content=_build_prompt(task["user_query"], task["research_digest"])),
    ]

    # ── Key fetch ──────────────────────────────────────────────────────────
    try:
        api_key = await fetch_decrypted_key(
            deps,
            task["user_id"],
            member["provider"],
            session_id=session_id,
            member_id=member_id,
        )
    except Exception as exc:
        await deps.tracer.end_span(span, error=exc)
        error_msg = _sanitize_error(exc, member["provider"])
        bus = await get_or_create_bus(session_id)
        await bus.publish(MemberFailed(
            session_id=session_id,
            member_id=member_id,
            stage="stage_1",
            error_class=type(exc).__name__,
            error_message=error_msg,
        ))
        error_resp = MemberResponse(
            member_id=member_id,
            stage="stage_1",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=error_msg,
            error_class=type(exc).__name__,
        )
        return {
            "stage_1_responses": [error_resp],
            "errors": [{
                "member_id": member_id,
                "stage": "stage_1",
                "message": f"{type(exc).__name__}:{exc}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    logger.info(
        "MODEL_REQUEST_START",
        extra={
            "session_id": session_id,
            "member_id": member_id,
            "provider": member["provider"],
            "model": member["model_id"],
        },
    )

    # ── Streaming call with event-bus publishing ───────────────────────────
    bus = await get_or_create_bus(session_id)
    start_time = time.monotonic()
    accumulated = ""
    token_count = 0
    first_token_emitted = False

    await bus.publish(ProviderConnecting(
        session_id=session_id,
        member_id=member_id,
    ))

    try:
        member_timeout = 90 if member["model_id"].endswith(":free") else 60
        async for delta in deps.llm_router.stream_chat(
            member_config=member,
            messages=messages,
            user_id=task["user_id"],
            api_key=api_key,
            timeout_s=member_timeout,
            temperature=0.7,
            session_id=session_id,
        ):
            if not first_token_emitted:
                await bus.publish(FirstToken(
                    session_id=session_id,
                    member_id=member_id,
                    stage="stage_1",
                ))
                first_token_emitted = True

            accumulated += delta
            token_count += 1

            await bus.publish(StreamChunk(
                session_id=session_id,
                member_id=member_id,
                stage="stage_1",
                delta=delta,
                token_count=token_count,
            ))

    except Exception as exc:
        error_msg = _sanitize_error(exc, member["provider"])
        
        provider_msg = getattr(exc, "details", {}).get("provider_message") if hasattr(exc, "details") else None
        if provider_msg:
            error_msg = f"{error_msg} ({type(exc).__name__}: {provider_msg})"
            
        logger.exception(
            "MODEL_REQUEST_FAILED",
            extra={
                "session_id": session_id,
                "member_id": member_id,
                "provider": member["provider"],
            },
        )
        await deps.tracer.end_span(span, error=exc)
        await bus.publish(MemberFailed(
            session_id=session_id,
            member_id=member_id,
            stage="stage_1",
            error_class=type(exc).__name__,
            error_message=error_msg,
        ))
        error_resp = MemberResponse(
            member_id=member_id,
            stage="stage_1",
            content="",
            anonymized_label=None,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=error_msg,
            error_class=type(exc).__name__,
        )
        # Determine whether this is a "known" structured error for the errors list
        errors_entry: dict[str, Any] = {
            "member_id": member_id,
            "stage": "stage_1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(exc, AuthenticationError):
            errors_entry["message"] = f"authentication_error:{exc}"
        elif isinstance(exc, FallbackExhaustedError):
            errors_entry["message"] = f"fallback_exhausted:{exc}"
        else:
            errors_entry["message"] = error_msg

        return {
            "stage_1_responses": [error_resp],
            "errors": [errors_entry],
        }

    # ── Success path ───────────────────────────────────────────────────────
    latency_ms = int((time.monotonic() - start_time) * 1000)

    # Cost estimation: streaming does not return token counts from the provider,
    # so we approximate tokens_in from message char-lengths (÷ 4 ≈ tokens)
    # and use the streamed token_count as tokens_out.
    tokens_in_approx = sum(len(m.content) for m in messages) // 4

    member_resp = MemberResponse(
        member_id=member_id,
        stage="stage_1",
        content=accumulated,
        anonymized_label=None,  # Not anonymised yet — set during stage 2
        latency_ms=latency_ms,
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        cost_usd=0.0,  # Streaming path does not receive cost from provider
        error=None,
    )

    logger.info(
        "MODEL_REQUEST_SUCCESS",
        extra={
            "session_id": session_id,
            "member_id": member_id,
            "provider": member["provider"],
        },
    )

    await deps.tracer.end_span(
        span,
        output={"content": accumulated},
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        latency_ms=latency_ms,
        cost_usd=0.0,
    )

    # Fire-and-forget: DB write does not block SSE delivery.
    asyncio.create_task(_persist_member_response(deps, session_id, member_resp))

    await bus.publish(MemberCompleted(
        session_id=session_id,
        member_id=member_id,
        stage="stage_1",
        latency_ms=latency_ms,
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        cost_usd=0.0,
    ))

    return {"stage_1_responses": [member_resp]}
