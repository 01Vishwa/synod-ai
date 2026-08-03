"""
orchestration/nodes/stage_2.py — Blind Peer Review (Fan-out Node).

This node is mapped concurrently over every council member. Each member receives
an anonymised and independently shuffled bundle of the other members' Stage 1
responses, and is asked to review, critique, and rank them.

Streaming:
  - Uses llm_router.stream_chat to yield token deltas.
  - Publishes ProviderConnecting, FirstToken, StreamChunk, MemberCompleted,
    MemberFailed, and PeerReviewProgress events to the session EventBus so
    the SSE endpoint can relay them to the browser in real time.
  - DB persistence (_persist_member_response) is fire-and-forget — it does
    NOT block SSE delivery.

LangGraph topology:
  - The Send() fan-out via route_stage_2() is preserved exactly as-is.
  - PeerReviewStarted is published by setup_stage_2() in graph.py, before
    the fan-out begins.
  - validate_stage_2 (blocking) is still responsible for the stage-level
    checkpoint; no checkpoint is attempted inside this node.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core.runnables.config import RunnableConfig

from app.core.event_bus import (
    FirstToken,
    MemberCompleted,
    MemberFailed,
    PeerReviewProgress,
    ProviderConnecting,
    StreamChunk,
    get_or_create_bus,
)
from app.core.exceptions import AuthenticationError, FallbackExhaustedError
from app.domain.council_state import (
    CouncilMemberConfig,
    MemberResponse,
    RankingEntry,
)
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import GraphDependencies, get_deps
from app.orchestration.utils import _sanitize_error, fetch_decrypted_key

logger = logging.getLogger(__name__)


class Stage2Task(TypedDict):
    """The payload sent to each parallel instance of the Stage 2 node."""
    member: CouncilMemberConfig
    user_query: str
    shuffled_responses: list[MemberResponse]
    user_id: str
    session_id: str
    total_reviewers: int   # total number of parallel peer-review tasks (for progress)


def _build_prompt(query: str, responses: list[MemberResponse]) -> str:
    prompt = f"Original Query: {query}\n\n"
    prompt += "Below are several anonymized responses to the original query.\n"
    prompt += "Please read them carefully, evaluate their arguments, and rank them from best to worst.\n\n"
    
    for resp in responses:
        if not resp["error"] and resp["content"]:
            prompt += f"--- {resp['anonymized_label']} ---\n{resp['content']}\n\n"

    prompt += (
        "Your task:\n"
        "1. Provide a brief critique of the responses.\n"
        "2. Provide your final ranking from best to worst.\n\n"
        "CRITICAL INSTRUCTION: You MUST output your final ranking exactly in the following format at the very end of your response:\n"
        "<RANKING>\n"
    )
    for i in range(len(responses)):
        prompt += f"{i+1}. Member X\n"
    prompt += "</RANKING>\n"
    
    return prompt


def _parse_ranking(content: str, expected_labels: list[str]) -> list[str]:
    """
    Extract the ranking order from the LLM's text output.
    Looks for the <RANKING>...</RANKING> block.
    """
    match = re.search(r"<RANKING>(.*?)</RANKING>", content, re.IGNORECASE | re.DOTALL)
    if not match:
        # Fallback: look for "1. Member X" lines anywhere at the end of the text
        lines = content.strip().split("\n")
        lines.reverse()
    else:
        lines = match.group(1).strip().split("\n")
        
    ranking = []
    # Basic extraction logic: look for labels in the lines
    for line in lines:
        for label in expected_labels:
            if label.lower() in line.lower() and label not in ranking:
                ranking.append(label)
                
    # If the LLM failed to rank everyone, append the missing ones
    for label in expected_labels:
        if label not in ranking:
            ranking.append(label)
            
    return ranking


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
        await deps.repository.save_member_response(session_id, member_resp)
    except AttributeError:
        # repository may not yet implement save_member_response — safe no-op
        pass
    except Exception as exc:
        logger.warning(
            "Stage 2: background DB persist failed for member %s session %s: %s",
            member_resp["member_id"],
            session_id,
            exc,
        )


async def stage_2_node(task: Stage2Task, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute a single streaming LLM call for Stage 2 (Peer Review).

    Returns a dict with keys ``stage_2_responses`` and ``rankings``.
    The LangGraph state reducer aggregates these lists after all parallel
    Send() instances complete.

    Event sequence emitted to the session bus:
      ProviderConnecting → FirstToken → StreamChunk × N
        → MemberCompleted + PeerReviewProgress
      (or MemberFailed + PeerReviewProgress on error)
    """
    deps = get_deps(config)
    member = task["member"]
    member_id: str = member["member_id"]
    session_id: str = task.get("session_id", "")
    responses = task["shuffled_responses"]
    total_reviewers: int = task.get("total_reviewers", 1)
    expected_labels = [r["anonymized_label"] for r in responses if r.get("anonymized_label")]

    span = await deps.tracer.start_span(
        name=f"Stage 2 - {member['display_label']}",
        parent=deps.root_span,
        metadata={"provider": member["provider"], "model_id": member["model_id"], "is_llm_call": True},
    )

    messages = [
        ChatMessage(role="system", content="You are a rigorous, objective peer reviewer on an AI council."),
        ChatMessage(role="user", content=_build_prompt(task["user_query"], responses)),
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
            stage="stage_2",
            error_class=type(exc).__name__,
            error_message=error_msg,
        ))
        # Still emit progress so the frontend knows this slot resolved
        await bus.publish(PeerReviewProgress(
            session_id=session_id,
            completed=1,
            total=total_reviewers,
        ))
        error_resp = MemberResponse(
            member_id=member_id,
            stage="stage_2",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=error_msg,
        )
        return {
            "stage_2_responses": [error_resp],
            "errors": [{
                "member_id": member_id,
                "stage": "stage_2",
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
            temperature=0.4,  # Lower temp for more analytical ranking
            session_id=session_id,
        ):
            if not first_token_emitted:
                await bus.publish(FirstToken(
                    session_id=session_id,
                    member_id=member_id,
                    stage="stage_2",
                ))
                first_token_emitted = True

            accumulated += delta
            token_count += 1

            await bus.publish(StreamChunk(
                session_id=session_id,
                member_id=member_id,
                stage="stage_2",
                delta=delta,
                token_count=token_count,
            ))

    except Exception as exc:
        error_msg = _sanitize_error(exc, member["provider"])
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
            stage="stage_2",
            error_class=type(exc).__name__,
            error_message=error_msg,
        ))
        # Emit progress even on failure so total always reaches 100%
        await bus.publish(PeerReviewProgress(
            session_id=session_id,
            completed=1,
            total=total_reviewers,
        ))
        error_resp = MemberResponse(
            member_id=member_id,
            stage="stage_2",
            content="",
            anonymized_label=None,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=error_msg,
        )
        errors_entry: dict[str, Any] = {
            "member_id": member_id,
            "stage": "stage_2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(exc, AuthenticationError):
            errors_entry["message"] = f"authentication_error:{exc}"
        elif isinstance(exc, FallbackExhaustedError):
            errors_entry["message"] = f"fallback_exhausted:{exc}"
        else:
            errors_entry["message"] = error_msg

        return {
            "stage_2_responses": [error_resp],
            "errors": [errors_entry],
        }

    # ── Success path ───────────────────────────────────────────────────────
    latency_ms = int((time.monotonic() - start_time) * 1000)
    tokens_in_approx = sum(len(m.content) for m in messages) // 4

    ranking_order = _parse_ranking(accumulated, expected_labels)

    member_resp = MemberResponse(
        member_id=member_id,
        stage="stage_2",
        content=accumulated,
        anonymized_label=None,
        latency_ms=latency_ms,
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        cost_usd=0.0,  # Streaming path does not receive cost from provider
        error=None,
    )

    ranking_entry = RankingEntry(
        ranked_by_member_id=member_id,
        ranking_order=ranking_order,
        justification=accumulated,
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
        output={"ranking": ranking_order},
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
        stage="stage_2",
        latency_ms=latency_ms,
        tokens_in=tokens_in_approx,
        tokens_out=token_count,
        cost_usd=0.0,
    ))

    # Emit peer-review progress after each member completes.
    # completed=1 because each node represents exactly one reviewer finishing;
    # the SSE layer or frontend accumulates these to show X/total progress.
    await bus.publish(PeerReviewProgress(
        session_id=session_id,
        completed=1,
        total=total_reviewers,
    ))

    return {
        "stage_2_responses": [member_resp],
        "rankings": [ranking_entry],
    }
