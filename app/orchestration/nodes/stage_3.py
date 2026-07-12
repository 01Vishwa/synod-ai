"""
orchestration/nodes/stage_3.py — Chairman Synthesis Node.

Executes Stage 3: The elected Chairman receives all de-anonymised opinions and
peer reviews, and produces a final consolidated Markdown report.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.adapters.llm_providers.factory import ProviderAdapterFactory
from app.domain.council_state import CouncilState
from app.domain.ports.provider_adapter import ChatMessage
from app.orchestration.context import get_deps
from app.orchestration.utils import fetch_decrypted_key

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


async def stage_3_node(state: CouncilState, config: RunnableConfig) -> dict[str, Any]:
    """
    Execute the Chairman synthesis LLM call.
    """
    deps = get_deps(config)
    chairman_id = state["chairman_member_id"]
    
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

    try:
        api_key = await fetch_decrypted_key(deps, state.get("user_id", ""), member["provider"]) # type: ignore
        adapter = ProviderAdapterFactory.create(member["provider"])
        
        # Final synthesis might be long
        response = await adapter.chat(
            messages=messages,
            model_id=member["model_id"],
            api_key=api_key,
            temperature=0.5,
            max_tokens=4000,
        )

        await deps.tracer.end_span(
            span, 
            output={"content_length": len(response.content)},
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
            cost_usd=response.cost_usd,
        )
        
        return {
            "final_report_md": response.content,
            # We don't have a dedicated cost field for Stage 3 in CouncilState, 
            # so we'll append a dummy MemberResponse to stage_2 just for cost tracking,
            # or rely on the LangSmith tracer for total cost.
            # We'll just update the DB model's total_cost directly in the repo checkpoint.
        }

    except Exception as exc:
        logger.error("Stage 3 failed for %s: %s", member["member_id"], exc)
        await deps.tracer.end_span(span, error=exc)
        return {
            "errors": state.get("errors", []) + [{
                "member_id": member["member_id"],
                "stage": "stage_3",
                "message": str(exc),
                "timestamp": ""
            }]
        }
