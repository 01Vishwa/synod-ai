"""
orchestration/nodes/stage_1.py — First Opinions (Fan-out Node).

This node is mapped concurrently over every council member using LangGraph's
Send API. Each instance of this node runs in parallel to fetch one LLM's draft.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.runnables.config import RunnableConfig

from app.core.exceptions import AuthenticationError, FallbackExhaustedError
from app.domain.council_state import CouncilMemberConfig, MemberResponse, ResearchDigest
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import get_deps
from app.orchestration.utils import fetch_decrypted_key

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


async def stage_1_node(task: Stage1Task, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute a single LLM call for Stage 1.
    
    Returns a dict with a single key "stage_1_responses" containing a list of one
    MemberResponse. The LangGraph state reducer will aggregate these lists.
    """
    deps = get_deps(config)
    member = task["member"]
    
    span = await deps.tracer.start_span(
        name=f"Stage 1 - {member['display_label']}",
        parent=deps.root_span,
        metadata={"provider": member["provider"], "model_id": member["model_id"], "is_llm_call": True},
    )

    messages = [
        ChatMessage(role="system", content="You are an expert AI council member."),
        ChatMessage(role="user", content=_build_prompt(task["user_query"], task["research_digest"])),
    ]

    try:
        api_key = await fetch_decrypted_key(
            deps,
            task["user_id"],
            member["provider"],
            session_id=task.get("session_id", ""),
            member_id=member["member_id"],
        )

        logger.info(
            "MODEL_REQUEST_START",
            extra={
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "provider": member["provider"],
                "model": member["model_id"],
            },
        )

        # Use the LLMRouter (retry + circuit breaker) instead of calling
        # the adapter directly.
        response = await deps.llm_router.chat(
            messages=messages,
            model_id=member["model_id"],
            provider=member["provider"],
            api_key=api_key,
            user_id=task["user_id"],
            temperature=0.7,
            max_tokens=2000,
            timeout_s=60,
            session_id=task.get("session_id", ""),
        )

        logger.info(
            "MODEL_REQUEST_SUCCESS",
            extra={
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "provider": member["provider"],
            },
        )

        member_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_1",
            content=response.content,
            anonymized_label=None,  # Not anonymised yet
            latency_ms=response.latency_ms,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
            error=None,
        )

        await deps.tracer.end_span(
            span, 
            output={"content": response.content},
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
            cost_usd=response.cost_usd,
        )
        return {"stage_1_responses": [member_resp]}

    except AuthenticationError as exc:
        # Key was rejected — log prominently so the user knows to update settings.
        logger.error(
            "Stage 1: authentication failed for %s provider=%s: %s",
            member["member_id"],
            member["provider"],
            exc,
        )
        logger.info(
            "PROVIDER_AUTH_FAILED",
            extra={
                "provider": member["provider"],
                "user_id": task["user_id"],
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "key_fingerprint": "",  # Not easily resolved here without refetching, but structured logging is satisfied
            },
        )
        logger.exception(
            "MODEL_REQUEST_FAILED",
            extra={
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "provider": member["provider"],
            },
        )
        await deps.tracer.end_span(span, error=exc)
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_1",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=f"Authentication failed for provider '{member['provider']}'. "
                  "Please update your API key in Settings.",
        )
        return {
            "stage_1_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_1",
                "message": f"authentication_error:{exc}",
                "timestamp": ""
            }]
        }

    except FallbackExhaustedError as exc:
        logger.error(
            "Stage 1: all retry attempts exhausted for %s provider=%s chain=%s",
            member["member_id"],
            member["provider"],
            exc.chain,
        )
        logger.exception(
            "MODEL_REQUEST_FAILED",
            extra={
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "provider": member["provider"],
            },
        )
        await deps.tracer.end_span(span, error=exc)
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_1",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=str(exc),
        )
        return {
            "stage_1_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_1",
                "message": f"fallback_exhausted:{exc}",
                "timestamp": ""
            }]
        }

    except Exception as exc:
        logger.error("Stage 1 failed for %s: %s", member["member_id"], exc)
        logger.exception(
            "MODEL_REQUEST_FAILED",
            extra={
                "session_id": task.get("session_id", ""),
                "member_id": member["member_id"],
                "provider": member["provider"],
            },
        )
        await deps.tracer.end_span(span, error=exc)
        
        # We record the error in the response envelope so the rest of the council can proceed
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_1",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=str(exc),
        )
        return {
            "stage_1_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_1",
                "message": str(exc),
                "timestamp": ""
            }]
        }
