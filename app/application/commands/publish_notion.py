"""
application/commands/publish_notion.py — PublishNotionCommand.

A Value Object (immutable data bag) that encapsulates everything the
PublishHandler needs to execute a Notion archiving operation.

Pattern: Command (encapsulates a single intent as a data object),
         Value Object (immutable — never mutated after construction).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.council_state import CouncilState


@dataclass(frozen=True)
class PublishNotionCommand:
    """
    Everything required to publish one council report to Notion.

    Frozen to prevent mutation — handlers receive, execute, and discard it.

    Attributes:
        state:          Terminal CouncilState containing the full deliberation.
        access_token:   Decrypted Notion OAuth access token (plaintext).
                        NEVER log or persist this field.
        parent_page_id: Notion page ID to create the report as a child of.
                        If None, the adapter will attempt workspace-root creation.
    """
    state: CouncilState
    access_token: str
    parent_page_id: Optional[str] = None
