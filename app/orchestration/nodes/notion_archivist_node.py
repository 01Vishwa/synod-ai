"""
orchestration/nodes/notion_archivist_node.py — Notion Archivist Node.

A pure LangGraph node responsible for invoking the NotionService to
publish the final report.

Features:
  - Idempotency gate: Exits immediately if `archive_to_notion` is False.
  - Error Isolation: Never raises exceptions. If Notion fails, it sets
    `archive_status="failed"` and `archive_error="..."` and continues.
  - Dependency Injection: Instantiates the adapters and service inline for
    the LangGraph execution context, fetching the encrypted token from the DB.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.adapters.notion.notion_mcp_adapter import NotionMcpAdapter
from app.adapters.notion.oauth_state_store import OAuthStateStore
from app.adapters.persistence.models import ProviderKeyModel
from app.application.handlers.publish_handler import PublishHandler
from app.application.services.notion_service import NotionService
from app.domain.council_state import CouncilState
from app.orchestration.context import GraphDependencies

logger = logging.getLogger(__name__)


async def notion_archivist_node(
    state: CouncilState, config: dict[str, Any]
) -> dict[str, Any]:
    """
    LangGraph node: Push the final report to Notion via MCP.

    Returns:
        dict containing state delta (notion_page_url, archive_status, etc.)
    """
    session_id = state.get("session_id", "unknown")
    user_id = state.get("user_id")

    # 1. Gate check
    if not state.get("archive_to_notion"):
        logger.debug("notion_archivist_node: skipping (archive_to_notion=False)")
        return {"archive_status": "skipped"}

    logger.info("notion_archivist_node: starting for session %s", session_id)
    deps: GraphDependencies = config["configurable"]["deps"]

    try:
        # 2. Fetch Notion API token + metadata from the database
        async with deps.db_session_factory() as session:
            stmt = select(ProviderKeyModel).where(
                ProviderKeyModel.user_id == user_id,
                ProviderKeyModel.provider == "notion",
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

        if not model:
            msg = "User requested Notion archive, but no Notion connection found."
            logger.warning(f"notion_archivist_node: {msg}")
            return {"archive_status": "failed", "archive_error": msg}

        access_token = deps.vault.decrypt(model.encrypted_key)
        
        meta = model.connection_meta or {}
        parent_page_id = meta.get("parent_page_id")

        # 3. Assemble application dependencies
        port = NotionMcpAdapter()
        handler = PublishHandler(port=port)
        store = OAuthStateStore.instance()
        service = NotionService(publish_handler=handler, state_store=store)

        # 4. Execute the publish operation
        result_obj = await service.publish_report(
            state=state,
            access_token=access_token,
            parent_page_id=parent_page_id,
        )

        logger.info(
            "notion_archivist_node: success for session %s. URL: %s",
            session_id,
            result_obj.page_url,
        )
        return {
            "archive_status": "done",
            "notion_page_url": result_obj.page_url,
        }

    except Exception as exc:
        # 5. Error Isolation — NEVER fail the graph
        logger.exception("notion_archivist_node: failed to publish to Notion")
        return {
            "archive_status": "failed",
            "archive_error": str(exc),
        }
