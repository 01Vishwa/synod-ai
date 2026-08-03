"""
adapters/notion/notion_mcp_adapter.py — Notion MCP Adapter.

Implements NotionPort using the official Notion MCP server
(@notionhq/notion-mcp-server) via langchain-mcp-adapters.

The adapter:
  1. Spawns the Notion MCP server as a stdio subprocess per operation.
  2. Discovers available tools via the MCP handshake.
  3. Calls `create_page` to create the report page.
  4. Calls `append_block_children` in batches of ≤ 100 blocks to populate it.
  5. Returns NotionPublishResult with the canonical Notion page URL.

Security:
  - The access_token is passed ONLY as an environment variable to the
    subprocess — it never appears in any log line or return value.
  - Only two MCP tools are ever called: create_page and append_block_children.
  - No delete, update, search, or read tools are invoked.

Prerequisites:
  - Node.js must be available in the PATH (for `npx`).
  - `langchain-mcp-adapters` and `mcp` must be installed (see pyproject.toml).

MCP server env var:
  The official Notion MCP server reads auth headers from OPENAPI_MCP_HEADERS:
    {"Authorization": "Bearer <token>", "Notion-Version": "2022-06-28"}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.adapters.notion.notion_page_builder import NotionPage, NotionPageBuilder
from app.domain.council_state import CouncilState
from app.domain.ports.notion_port import NotionPort, NotionPublishResult

logger = logging.getLogger(__name__)

# Batch limit for append_block_children Notion API calls
_BLOCK_BATCH_SIZE = 90          # Safety margin below Notion's 100 limit

# Notion API version header
_NOTION_API_VERSION = "2022-06-28"

# MCP tool name fragments used for discovery
_TOOL_CREATE_PAGE    = ("create", "page")
_TOOL_APPEND_BLOCKS  = ("append", "block")


def _build_mcp_config(access_token: str) -> dict:
    """
    Build the MultiServerMCPClient server configuration for Notion.

    The Notion MCP server is spawned as a stdio subprocess via npx.
    Auth is injected through OPENAPI_MCP_HEADERS — never via args.
    """
    headers = json.dumps({
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": _NOTION_API_VERSION,
    })
    return {
        "notion": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {"OPENAPI_MCP_HEADERS": headers},
        }
    }


def _find_tool(tools: list, *name_fragments: str) -> Any | None:
    """
    Discover a tool from the MCP tool list by partial name match.

    Args:
        tools:          List of LangChain tool objects from the MCP client.
        name_fragments: Substrings that must ALL appear in the tool name.

    Returns:
        The first matching tool, or None.
    """
    for tool in tools:
        name_lower = tool.name.lower()
        if all(frag in name_lower for frag in name_fragments):
            return tool
    return None


def _build_page_payload(page: NotionPage) -> dict:
    """
    Build the `create_page` MCP tool input payload.

    Uses a page parent if a parent_page_id is provided; otherwise falls back
    to workspace-level creation (requires broader OAuth scope).
    """
    parent = (
        {"page_id": page.parent_page_id}
        if page.parent_page_id
        else {"workspace": True}
    )
    return {
        "parent": parent,
        "properties": {
            "title": {
                "title": [
                    {"type": "text", "text": {"content": page.title}}
                ]
            }
        },
    }


class NotionMcpAdapter(NotionPort):
    """
    Production Notion adapter using the official Notion MCP server.

    Responsibilities:
      - Spawn + connect to the Notion MCP server via stdio.
      - Build the Notion page payload using NotionPageBuilder.
      - Execute create_page + append_block_children MCP tool calls.
      - Translate MCP responses into the domain's NotionPublishResult.

    Never:
      - Calls delete, update, search, or any other tool.
      - Logs access tokens.
      - Leaks MCP types outside this class.
    """

    def __init__(self) -> None:
        self._builder = NotionPageBuilder()

    async def publish_report(
        self,
        state: CouncilState,
        access_token: str,
        *,
        database_id: Optional[str] = None,
        parent_page_id: Optional[str] = None,
    ) -> NotionPublishResult:
        """
        Publish the council report to a new Notion page via MCP.

        Steps:
          1. Build the Notion page payload (title + blocks).
          2. Connect to the Notion MCP server.
          3. Call create_page → obtain page_id + page_url.
          4. Call append_block_children in batches.

        Args:
            state:          Terminal CouncilState.
            access_token:   Decrypted Notion OAuth token (plaintext). NOT logged.
            parent_page_id: Notion page to file the report under.

        Returns:
            NotionPublishResult(page_url, page_id).

        Raises:
            RuntimeError: if required MCP tools are not discovered.
            Exception:    propagated from MCP server on tool call failure.
        """
        session_id = state.get("session_id", "unknown")

        logger.info(
            "notion_mcp_adapter: starting publish",
            extra={
                "session_id": session_id,
                "has_parent_page": parent_page_id is not None,
            },
        )

        # Build the page payload (pure — no network)
        page = self._builder.build(state, parent_page_id=parent_page_id)

        # Connect to the Notion MCP server and execute tool calls
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            raise RuntimeError(
                "langchain-mcp-adapters is not installed. "
                "Run: pip install langchain-mcp-adapters mcp"
            ) from exc

        mcp_config = _build_mcp_config(access_token)

        async with MultiServerMCPClient(mcp_config) as client:
            tools = client.get_tools()

            page_id, page_url = await self._create_page(tools, page, session_id)
            await self._append_blocks(tools, page_id, page.blocks, session_id)

        logger.info(
            "notion_mcp_adapter: publish complete",
            extra={"session_id": session_id, "page_id": page_id},
        )
        return NotionPublishResult(page_url=page_url, page_id=page_id)

    async def validate_token(self, access_token: str) -> bool:
        """
        Verify the Notion OAuth token is valid and has write access.

        Spawns the MCP server and checks that the expected tools are available.
        A valid token will return a non-empty tool list.

        Returns:
            True if the token is valid and write-capable.
        """
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            async with MultiServerMCPClient(_build_mcp_config(access_token)) as client:
                tools = client.get_tools()
                has_create = _find_tool(tools, *_TOOL_CREATE_PAGE) is not None
                logger.debug(
                    "notion_mcp_adapter: token validation — has_create_page=%s",
                    has_create,
                )
                return has_create

        except Exception as exc:
            logger.warning(
                "notion_mcp_adapter: token validation failed: %s", exc
            )
            return False

    # ── Private MCP Tool Callers ──────────────────────────────────────────────

    async def _create_page(
        self,
        tools: list,
        page: NotionPage,
        session_id: str,
    ) -> tuple[str, str]:
        """
        Call the create_page MCP tool and extract page_id + page_url.

        Returns:
            (page_id, page_url) tuple.

        Raises:
            RuntimeError: if the tool is not found or returns unexpected data.
        """
        create_tool = _find_tool(tools, *_TOOL_CREATE_PAGE)
        if not create_tool:
            tool_names = [t.name for t in tools]
            raise RuntimeError(
                f"Notion MCP server did not expose a create_page tool. "
                f"Available tools: {tool_names}"
            )

        payload = _build_page_payload(page)

        logger.debug(
            "notion_mcp_adapter: calling %s for session %s",
            create_tool.name,
            session_id,
        )
        result = await create_tool.ainvoke(payload)

        # MCP tool results are typically dicts; extract page_id and url
        page_id = _extract_str(result, "id") or _extract_str(result, "page_id")
        page_url = (
            _extract_str(result, "url")
            or (f"https://notion.so/{page_id.replace('-', '')}" if page_id else "")
        )

        if not page_id:
            raise RuntimeError(
                f"create_page MCP tool returned no page_id. Raw: {result!r}"
            )

        logger.info(
            "notion_mcp_adapter: page created",
            extra={"session_id": session_id, "page_id": page_id},
        )
        return page_id, page_url

    async def _append_blocks(
        self,
        tools: list,
        page_id: str,
        blocks: list[dict],
        session_id: str,
    ) -> None:
        """
        Append content blocks to the newly created page in batches.

        Batching is required because Notion's append_block_children API
        accepts at most 100 blocks per call.

        Args:
            tools:      MCP tool list from the connected client.
            page_id:    The Notion page to append blocks to.
            blocks:     All content blocks (may exceed 100).
            session_id: For structured logging only.
        """
        if not blocks:
            return

        append_tool = _find_tool(tools, *_TOOL_APPEND_BLOCKS)
        if not append_tool:
            tool_names = [t.name for t in tools]
            logger.warning(
                "notion_mcp_adapter: append_block_children tool not found; "
                "page %s will have no content. Available: %s",
                page_id,
                tool_names,
            )
            return

        batches = [
            blocks[i : i + _BLOCK_BATCH_SIZE]
            for i in range(0, len(blocks), _BLOCK_BATCH_SIZE)
        ]

        for batch_idx, batch in enumerate(batches):
            logger.debug(
                "notion_mcp_adapter: appending batch %d/%d (%d blocks) to %s",
                batch_idx + 1,
                len(batches),
                len(batch),
                page_id,
            )
            await append_tool.ainvoke({
                "block_id": page_id,
                "children": batch,
            })


# ── Utilities ─────────────────────────────────────────────────────────────────

def _extract_str(data: Any, key: str) -> str | None:
    """Safely extract a string value from a dict (or dict-like) result."""
    if isinstance(data, dict):
        val = data.get(key)
        return str(val) if val is not None else None
    return None
