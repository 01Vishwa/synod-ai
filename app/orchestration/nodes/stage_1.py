"""
orchestration/nodes/stage_1.py — First Opinions (Fan-out Node).

This node is mapped concurrently over every council member using LangGraph's
Send API. Each instance of this node runs in parallel to fetch one LLM's draft.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.runnables.config import RunnableConfig

from app.adapters.llm_providers.factory import ProviderAdapterFactory
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
        api_key = await fetch_decrypted_key(deps, task["user_id"], member["provider"])
        adapter = ProviderAdapterFactory.create(member["provider"])
        
        # Max tokens capped high enough for a full draft, temperature moderate
        response = await adapter.chat(
            messages=messages,
            model_id=member["model_id"],
            api_key=api_key,
            temperature=0.7,
            max_tokens=2000,
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

    except Exception as exc:
        logger.error("Stage 1 failed for %s: %s", member["member_id"], exc)
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
