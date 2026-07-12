"""
domain/ports/notion_port.py — Port for Notion archiving.

Defines the interface the Notion Archivist Sub-Agent uses to publish a
completed council report. The domain never imports any Notion SDK.

Pattern: Port (Hexagonal Architecture driven port), Command (the publish
         call encapsulates all archive intent as a single operation).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.domain.council_state import CouncilState


@dataclass
class NotionPublishResult:
    """Result returned after successfully archiving a session to Notion."""
    page_url: str
    page_id: str
    database_id: Optional[str] = None


class NotionPort(ABC):
    """
    Driven port: interface for publishing council reports to Notion.

    Concrete implementation: adapters/notion/notion_mcp_adapter.py
    """

    @abstractmethod
    async def publish_report(
        self,
        state: CouncilState,
        access_token: str,
        *,
        database_id: Optional[str] = None,
        parent_page_id: Optional[str] = None,
    ) -> NotionPublishResult:
        """
        Publish the final report and deliberation trail to a Notion page.

        Args:
            state:          The terminal CouncilState containing the report.
            access_token:   User's Notion OAuth access token (decrypted).
            database_id:    Target Notion database ID (if archiving to a DB).
            parent_page_id: Parent Notion page ID (if archiving as a child page).

        Returns:
            NotionPublishResult with the URL of the created page.

        Raises:
            ProviderError: if the Notion API call fails.
        """
        ...

    @abstractmethod
    async def validate_token(self, access_token: str) -> bool:
        """Verify the Notion OAuth token is still valid and has write access."""
        ...
