"""
domain/council_state.py — The single shared data contract for the entire graph.

All LangGraph nodes read from and write to CouncilState. Nothing is passed
"in conversation" between agents — the Orchestrator decides which slice of
this state is appropriate for each node.

This module is intentionally framework-agnostic: no FastAPI, no LangChain,
no SQLAlchemy imports. It is plain Python so the domain rules are unit-testable
with zero I/O mocking.

Pattern: Value Object (all TypedDicts are immutable-by-convention data bags),
         Single Source of Truth (one state class governs the entire graph).
"""
from __future__ import annotations

from typing import Literal, Optional
from typing_extensions import TypedDict


# ── Sub-record types ──────────────────────────────────────────────────────

class CouncilMemberConfig(TypedDict):
    """Static configuration for one seat in the council."""
    member_id: str                          # stable internal id, e.g. "member_1"
    provider: Literal["openrouter", "nvidia_nim", "github_models"]
    model_id: str                           # e.g. "anthropic/claude-sonnet-4.5"
    display_label: str                      # user-facing name, e.g. "Council Seat 1"
    role: Literal["member", "chairman"]


class MemberResponse(TypedDict):
    """The output of one Council Member for one stage."""
    member_id: str
    stage: Literal["stage_1", "stage_2"]
    content: str
    anonymized_label: Optional[str]         # "Member C" — set only during stage 2
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: Optional[str]                    # set if this member errored


class RankingEntry(TypedDict):
    """One peer-reviewer's ranking ballot from Stage 2."""
    ranked_by_member_id: str
    ranking_order: list[str]                # anonymized labels, best → worst
    justification: str


class ResearchDigest(TypedDict):
    """Evidence collected by the Research Sub-Agent."""
    provider: Literal["tavily", "anakin"]
    query_terms: list[str]
    sources: list[dict]                     # {url, title, snippet, retrieved_at}
    summary: str


# ── Root state ────────────────────────────────────────────────────────────

class CouncilState(TypedDict):
    """
    The single artifact that all LangGraph nodes read and write.

    Lifecycle: created by the Orchestrator at session start; checkpointed
    to Postgres after every stage transition; delivered to the frontend
    incrementally via SSE deltas.
    """
    # Identity
    session_id: str
    trace_id: str                           # LangSmith / Langfuse trace id

    # User inputs
    user_query: str
    members: list[CouncilMemberConfig]

    # Graph control
    stage: Literal["stage_1", "stage_2", "stage_3", "archiving", "done", "error"]

    # Research (optional)
    research_enabled: bool
    research_provider: Optional[Literal["tavily", "anakin"]]
    research_digest: Optional[ResearchDigest]

    # Stage 1 — First Opinions
    stage_1_responses: list[MemberResponse]

    # Stage 2 — Blind Peer Review
    # anonymization_map is server-side only; never sent to a model
    anonymization_map: dict[str, str]       # member_id → anonymized_label
    stage_2_responses: list[MemberResponse]
    rankings: list[RankingEntry]
    aggregate_scores: dict[str, float]      # member_id → normalized Borda score

    # Stage 3 — Chairman Synthesis
    chairman_member_id: str
    final_report_md: Optional[str]
    citations: list[dict]                   # {url, title, excerpt}

    # Optional archiving
    archive_to_notion: bool                 # gates the archive step
    notion_page_url: Optional[str]
    archive_status: Optional[str]           # "done" | "failed" | "skipped"
    archive_error: Optional[str]            # structured error message if failed

    # Dynamic dashboard spec (json-render Spec emitted by dashboard_builder_node)
    dashboard_spec: Optional[dict]

    # Error log (appended; run continues with surviving members unless all fail)
    errors: list[dict]                      # {member_id, stage, message, timestamp}

    # Timestamps (ISO-8601 strings for JSON serializability)
    created_at: str
    updated_at: str


# ── Stage ordering helper ─────────────────────────────────────────────────

STAGE_ORDER: list[str] = ["stage_1", "stage_2", "stage_3", "archiving", "done"]


def stage_index(stage: str) -> int:
    """Return the ordinal position of a stage for forward/backward comparisons."""
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def is_terminal(stage: str) -> bool:
    """Return True if the session has reached a terminal state (done or error)."""
    return stage in {"done", "error"}
