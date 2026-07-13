"""
application/handlers/publish_handler.py — PublishHandler.

The handler is the application boundary that translates a PublishNotionCommand
into a domain port call. It knows nothing about MCP, HTTP, or databases —
those concerns live in the adapter layer.

Pattern: Command Handler, Dependency Injection (port injected at construction).
"""
from __future__ import annotations

import logging

from app.application.commands.publish_notion import PublishNotionCommand
from app.domain.ports.notion_port import NotionPort, NotionPublishResult

logger = logging.getLogger(__name__)


class PublishHandler:
    """
    Executes a PublishNotionCommand against the NotionPort.

    Args:
        port: The concrete NotionPort implementation (injected, never
              instantiated inside this class).

    Design: Single Responsibility — this class does exactly one thing.
    It is intentionally simple so the Command-Handler boundary is clear.
    """

    def __init__(self, port: NotionPort) -> None:
        self._port = port

    async def execute(self, command: PublishNotionCommand) -> NotionPublishResult:
        """
        Execute the publish command.

        Args:
            command: An immutable PublishNotionCommand containing the full
                     deliberation state and decrypted access token.

        Returns:
            NotionPublishResult with the URL of the created Notion page.

        Raises:
            Any exception raised by the NotionPort — callers are responsible
            for error isolation.
        """
        logger.info(
            "publish_handler: executing publish command",
            extra={
                "session_id": command.state.get("session_id"),
                "has_parent": command.parent_page_id is not None,
            },
        )
        return await self._port.publish_report(
            state=command.state,
            access_token=command.access_token,
            parent_page_id=command.parent_page_id,
        )
