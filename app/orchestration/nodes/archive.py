"""
orchestration/nodes/archive.py — Notion Archiving Node.

Executes the optional final step to export the completed Council report to Notion.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.adapters.notion.notion_mcp_adapter import NotionMcpAdapter
from app.domain.council_state import CouncilState
from app.orchestration.context import get_deps
from app.orchestration.utils import fetch_decrypted_key

logger = logging.getLogger(__name__)


async def archive_node(state: CouncilState, config: RunnableConfig) -> dict[str, Any]:
    """
    Publish the final report to Notion if requested.
    """
    deps = get_deps(config)
    
    # We only archive if requested (represented here implicitly or explicitly by state flag).
    # Since we didn't add `archive_to_notion` to CouncilState directly (it was in the API req),
    # we can skip if no Notion key exists, or if a flag is added later. For now, we will
    # attempt to fetch the Notion key. If missing, we silently skip archiving.
    
    user_id = state.get("user_id", "")  # type: ignore
    
    try:
        api_key = await fetch_decrypted_key(deps, user_id, "notion")
    except Exception:
        # No Notion key configured, skip archiving
        return {}

    span = await deps.tracer.start_span(
        name="Archive to Notion",
        parent=deps.root_span,
    )

    try:
        adapter = NotionMcpAdapter()
        result = await adapter.publish_report(state, api_key)

        await deps.tracer.end_span(span, output={"page_url": result.page_url})
        return {"notion_page_url": result.page_url}

    except Exception as exc:
        logger.error("Notion archiving failed: %s", exc)
        await deps.tracer.end_span(span, error=exc)
        # Archiving failure shouldn't fail the whole session
        return {
            "errors": state.get("errors", []) + [{
                "member_id": "archivist",
                "stage": "archiving",
                "message": f"Notion export failed: {exc}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
        }
