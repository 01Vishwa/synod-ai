"""
adapters/notion/notion_page_builder.py — Notion Block Payload Builder.

Converts a terminal CouncilState into a Notion API page payload:
title (string) + a list of Notion block objects.

Design:
  - Pure function: reads state, returns a NotionPage dataclass.
    Zero side effects, zero network calls, fully unit-testable in isolation.
  - Builder Pattern: each section is built by a private helper, composed
    by the public build() method.
  - Content limits: Notion rich_text items cap at 2000 chars. Long markdown
    is chunked into sequential paragraph blocks.
  - Block limit: append_block_children accepts ≤100 blocks per call.
    The adapter is responsible for batching; the builder outputs the full list.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

from app.domain.council_state import CouncilState, MemberResponse

_RICH_TEXT_MAX = 1990          # Notion limit is 2000; leave buffer
_HEADING_1 = "heading_1"
_HEADING_2 = "heading_2"
_PARAGRAPH  = "paragraph"
_TOGGLE     = "toggle"
_DIVIDER    = "divider"
_CODE       = "code"
_TABLE      = "table"
_TABLE_ROW  = "table_row"


# ── Value Objects ─────────────────────────────────────────────────────────────

@dataclass
class NotionPage:
    """
    The payload the MCP adapter will use to create and populate a Notion page.

    Attributes:
        title:          The page title string.
        blocks:         Ordered list of Notion block dicts (max ~2000 per batch).
        parent_page_id: Notion page ID of the parent, if any.
    """
    title: str
    blocks: list[dict[str, Any]]
    parent_page_id: str | None = None


# ── Block Construction Helpers ────────────────────────────────────────────────

def _rich_text(content: str) -> list[dict]:
    """Return a Notion rich_text array from a plain string, chunked safely."""
    chunks = textwrap.wrap(content, width=_RICH_TEXT_MAX, break_long_words=True)
    if not chunks:
        chunks = [""]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _heading(level: str, text: str) -> dict:
    return {
        "object": "block",
        "type": level,
        level: {"rich_text": _rich_text(text)},
    }


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": _PARAGRAPH,
        _PARAGRAPH: {"rich_text": _rich_text(text)},
    }


def _divider() -> dict:
    return {"object": "block", "type": _DIVIDER, _DIVIDER: {}}


def _code_block(text: str, language: str = "markdown") -> dict:
    """Wrap long text in a code block (2000 char cap still applies)."""
    content = text[:_RICH_TEXT_MAX] if len(text) > _RICH_TEXT_MAX else text
    return {
        "object": "block",
        "type": _CODE,
        _CODE: {
            "rich_text": [{"type": "text", "text": {"content": content}}],
            "language": language,
        },
    }


def _toggle(title: str, children: list[dict]) -> dict:
    return {
        "object": "block",
        "type": _TOGGLE,
        _TOGGLE: {
            "rich_text": _rich_text(title),
            "children": children,
        },
    }


def _table(rows: list[list[str]], has_header: bool = True) -> dict:
    """Build a Notion table block with optional column header."""
    width = max(len(r) for r in rows) if rows else 1
    table_rows = [
        {
            "object": "block",
            "type": _TABLE_ROW,
            _TABLE_ROW: {
                "cells": [
                    [{"type": "text", "text": {"content": cell}}]
                    for cell in row
                ]
            },
        }
        for row in rows
    ]
    return {
        "object": "block",
        "type": _TABLE,
        _TABLE: {
            "table_width": width,
            "has_column_header": has_header,
            "has_row_header": False,
            "children": table_rows,
        },
    }


# ── Section Builders ──────────────────────────────────────────────────────────

def _build_header_blocks(state: CouncilState) -> list[dict]:
    """Section 1: Original question."""
    return [
        _heading(_HEADING_1, "Original Question"),
        _paragraph(state["user_query"]),
        _divider(),
    ]


def _build_report_blocks(state: CouncilState) -> list[dict]:
    """Section 2: Chairman Report (markdown rendered as code block chunks)."""
    report_md = state.get("final_report_md") or "_No report generated._"
    blocks: list[dict] = [_heading(_HEADING_1, "Chairman Report")]

    # Split on double newlines (paragraphs) to create natural Notion blocks
    paragraphs = [p.strip() for p in report_md.split("\n\n") if p.strip()]
    for para in paragraphs:
        if len(para) > _RICH_TEXT_MAX:
            blocks.append(_code_block(para))
        else:
            blocks.append(_paragraph(para))

    blocks.append(_divider())
    return blocks


def _build_ranking_table(state: CouncilState) -> list[dict]:
    """Section 3: Final Rankings table."""
    scores = state.get("aggregate_scores") or {}
    members = state.get("members") or []
    label_map = {m["member_id"]: m["display_label"] for m in members}

    sorted_members = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    rows = [["Rank", "Member", "Score"]]
    for rank, (member_id, score) in enumerate(sorted_members, start=1):
        rows.append([
            str(rank),
            label_map.get(member_id, member_id),
            f"{score:.4f}",
        ])

    if len(rows) == 1:
        return []   # No scores yet — omit section

    return [
        _heading(_HEADING_1, "Final Rankings"),
        _table(rows),
        _divider(),
    ]


def _build_stage1_toggles(state: CouncilState) -> list[dict]:
    """Section 4: Stage 1 Responses in collapsible toggles."""
    responses: list[MemberResponse] = state.get("stage_1_responses") or []
    members = state.get("members") or []
    label_map = {m["member_id"]: m["display_label"] for m in members}

    if not responses:
        return []

    blocks: list[dict] = [_heading(_HEADING_1, "Stage 1 Responses")]

    for resp in responses:
        label = label_map.get(resp["member_id"], resp["member_id"])
        if resp.get("error"):
            children = [_paragraph(f"⚠ Error: {resp['error']}")]
        else:
            content = resp.get("content") or "_No response._"
            children = []
            for para in content.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                if len(para) > _RICH_TEXT_MAX:
                    children.append(_code_block(para))
                else:
                    children.append(_paragraph(para))
            children = children or [_paragraph("_No content._")]

        blocks.append(_toggle(f"▸ {label}", children))

    blocks.append(_divider())
    return blocks


def _build_metadata_block(state: CouncilState) -> list[dict]:
    """Section 5: Session metadata (ID, cost, tokens)."""
    all_responses = (
        list(state.get("stage_1_responses") or []) +
        list(state.get("stage_2_responses") or [])
    )
    total_tokens = sum(
        r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in all_responses
    )
    total_cost = sum(r.get("cost_usd", 0.0) for r in all_responses)
    total_latency = sum(r.get("latency_ms", 0) for r in all_responses)

    lines = [
        f"Session ID: {state.get('session_id', 'N/A')}",
        f"Created: {state.get('created_at', 'N/A')}",
        f"Members: {len(state.get('members') or [])}",
        f"Total Tokens: {total_tokens:,}",
        f"Total Cost: ${total_cost:.4f}",
        f"Total Latency: {total_latency:,} ms",
        f"Research Enabled: {state.get('research_enabled', False)}",
    ]

    return [
        _heading(_HEADING_1, "Session Metadata"),
        _code_block("\n".join(lines), language="plain text"),
    ]


# ── Public Builder ────────────────────────────────────────────────────────────

class NotionPageBuilder:
    """
    Converts a terminal CouncilState into a Notion page payload.

    Usage:
        builder = NotionPageBuilder()
        page = builder.build(state, parent_page_id="abc-123")
        # page.title, page.blocks, page.parent_page_id
    """

    def build(
        self,
        state: CouncilState,
        parent_page_id: str | None = None,
    ) -> NotionPage:
        """
        Build the complete Notion page payload.

        Args:
            state:          Terminal CouncilState (post-Stage 3).
            parent_page_id: Notion page to create the report under.

        Returns:
            NotionPage with title and full block list.
        """
        query_preview = (state.get("user_query") or "")[:60]
        title = f"Synod Report — {query_preview}"

        blocks: list[dict] = []
        blocks.extend(_build_header_blocks(state))
        blocks.extend(_build_report_blocks(state))
        blocks.extend(_build_ranking_table(state))
        blocks.extend(_build_stage1_toggles(state))
        blocks.extend(_build_metadata_block(state))

        return NotionPage(
            title=title,
            blocks=blocks,
            parent_page_id=parent_page_id,
        )
