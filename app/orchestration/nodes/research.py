"""
orchestration/nodes/research.py — Research node.

Executes an optional web research pass before the council begins deliberation.
Updates the `research_digest` field in CouncilState.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.adapters.research_providers.factory import ResearchProviderAdapterFactory
from app.domain.council_state import CouncilState, ResearchDigest
from app.orchestration.context import get_deps
from app.orchestration.utils import fetch_decrypted_key

logger = logging.getLogger(__name__)


async def research_node(state: CouncilState, config: RunnableConfig) -> dict[str, Any]:
    """
    Fetch live context using the user's selected research provider.
    
    If research_enabled is False, this node should be skipped by the edge router,
    but we include a guard clause just in case.
    """
    if not state.get("research_enabled") or not state.get("research_provider"):
        return {}

    deps = get_deps(config)
    provider = state["research_provider"]
    user_id = state.get("user_id", "")  # type: ignore

    span = await deps.tracer.start_span(
        name="Research Gather",
        parent=deps.root_span,
        metadata={"provider": provider, "query": state["user_query"]},
    )

    try:
        api_key = await fetch_decrypted_key(deps, user_id, provider)
        adapter = ResearchProviderAdapterFactory.create(provider)
        
        response = await adapter.search(
            query=state["user_query"],
            api_key=api_key,
            max_results=5,
            include_full_content=False,
        )

        digest = ResearchDigest(
            provider=provider,  # type: ignore
            query_terms=[state["user_query"]],
            sources=[
                {
                    "url": r.url,
                    "title": r.title,
                    "snippet": r.snippet,
                    "retrieved_at": r.retrieved_at,
                }
                for r in response.results
            ],
            summary=response.ai_summary or "No summary provided.",
        )

        await deps.tracer.end_span(span, output={"digest": digest})
        return {"research_digest": digest}

    except Exception as exc:
        logger.error("Research failed: %s", exc)
        await deps.tracer.end_span(span, error=exc)
        # We don't abort the council if research fails; we log the error
        # and proceed without context.
        return {
            "errors": state.get("errors", []) + [{
                "member_id": "research",
                "stage": "research",
                "message": f"Research failed: {exc}",
                "timestamp": ""  # Ideally ISO string, simplified for brevity
            }]
        }
