"""
orchestration/nodes/stage_2.py — Blind Peer Review (Fan-out Node).

This node is mapped concurrently over every council member. Each member receives
an anonymised and independently shuffled bundle of the other members' Stage 1
responses, and is asked to review, critique, and rank them.
"""
from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from langchain_core.runnables.config import RunnableConfig

from app.core.exceptions import AuthenticationError, FallbackExhaustedError
from app.domain.council_state import (
    CouncilMemberConfig,
    MemberResponse,
    RankingEntry,
)
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import get_deps
from app.orchestration.utils import fetch_decrypted_key

logger = logging.getLogger(__name__)


class Stage2Task(TypedDict):
    """The payload sent to each parallel instance of the Stage 2 node."""
    member: CouncilMemberConfig
    user_query: str
    shuffled_responses: list[MemberResponse]
    user_id: str


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


async def stage_2_node(task: Stage2Task, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute a single LLM call for Stage 2 (Peer Review).
    """
    deps = get_deps(config)
    member = task["member"]
    responses = task["shuffled_responses"]
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

    try:
        api_key = await fetch_decrypted_key(deps, task["user_id"], member["provider"])
        
        # Use the LLMRouter (retry + circuit breaker) instead of calling
        # the adapter directly.
        response = await deps.llm_router.chat(
            messages=messages,
            model_id=member["model_id"],
            provider=member["provider"],
            api_key=api_key,
            user_id=task["user_id"],
            temperature=0.4,  # Lower temp for more analytical ranking
            max_tokens=1500,
            timeout_s=60,
        )

        ranking_order = _parse_ranking(response.content, expected_labels) # type: ignore

        member_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_2",
            content=response.content,
            anonymized_label=None,
            latency_ms=response.latency_ms,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
            error=None,
        )

        ranking_entry = RankingEntry(
            ranked_by_member_id=member["member_id"],
            ranking_order=ranking_order,
            justification=response.content,
        )

        await deps.tracer.end_span(
            span, 
            output={"ranking": ranking_order},
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
            cost_usd=response.cost_usd,
        )
        
        return {
            "stage_2_responses": [member_resp],
            "rankings": [ranking_entry],
        }

    except AuthenticationError as exc:
        logger.error(
            "Stage 2: authentication failed for %s provider=%s: %s",
            member["member_id"],
            member["provider"],
            exc,
        )
        await deps.tracer.end_span(span, error=exc)
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_2",
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
            "stage_2_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_2",
                "message": f"authentication_error:{exc}",
                "timestamp": ""
            }]
        }

    except FallbackExhaustedError as exc:
        logger.error(
            "Stage 2: all retry attempts exhausted for %s provider=%s chain=%s",
            member["member_id"],
            member["provider"],
            exc.chain,
        )
        await deps.tracer.end_span(span, error=exc)
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_2",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=str(exc),
        )
        return {
            "stage_2_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_2",
                "message": f"fallback_exhausted:{exc}",
                "timestamp": ""
            }]
        }

    except Exception as exc:
        logger.error("Stage 2 failed for %s: %s", member["member_id"], exc)
        await deps.tracer.end_span(span, error=exc)
        
        error_resp = MemberResponse(
            member_id=member["member_id"],
            stage="stage_2",
            content="",
            anonymized_label=None,
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=str(exc),
        )
        return {
            "stage_2_responses": [error_resp],
            "errors": [{
                "member_id": member["member_id"],
                "stage": "stage_2",
                "message": str(exc),
                "timestamp": ""
            }]
        }
