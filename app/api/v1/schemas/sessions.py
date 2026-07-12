"""
api/v1/schemas/sessions.py — Request/response schemas for council sessions.

These Pydantic models are the API boundary — they validate inbound requests
before anything reaches the domain layer, and serialise domain TypedDicts
into JSON for the client.

Pattern: Data Transfer Object (DTO), Schema-First API Design.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Request schemas ───────────────────────────────────────────────────────

class CouncilMemberConfigSchema(BaseModel):
    """One seat in the council — validated at the API boundary."""
    member_id: str = Field(
        description="Stable internal identifier, e.g. 'member_1'",
        pattern=r"^member_\d+$",
    )
    provider: Literal["openrouter", "nvidia_nim", "github_models"] = Field(
        description="LLM provider for this seat"
    )
    model_id: str = Field(
        description="Provider-specific model string, e.g. 'anthropic/claude-sonnet-4.5'",
        min_length=1,
        max_length=256,
    )
    display_label: str = Field(
        description="User-facing name for this seat",
        min_length=1,
        max_length=64,
    )
    role: Literal["member", "chairman"] = "member"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "member_id": "member_1",
                "provider": "openrouter",
                "model_id": "anthropic/claude-sonnet-4.5",
                "display_label": "Council Seat 1",
                "role": "member",
            }
        }
    )


class SessionCreateRequest(BaseModel):
    """
    POST /api/v1/sessions — start a new council deliberation.

    Validates member count (3–6), ensures at most one chairman is designated,
    and confirms the research provider is set if research is enabled.
    """
    user_query: str = Field(
        description="The question the council will deliberate on",
        min_length=1,
        max_length=4000,
    )
    members: list[CouncilMemberConfigSchema] = Field(
        description="3–6 council members",
        min_length=2,
        max_length=6,
    )
    research_enabled: bool = Field(
        default=False,
        description="If true, the Research Sub-Agent fetches live web evidence before Stage 1",
    )
    research_provider: Optional[Literal["tavily", "anakin"]] = Field(
        default=None,
        description="Which research provider to use (required if research_enabled=true)",
    )
    # Optional: pin a specific model as Chairman instead of electing the top scorer
    pinned_chairman_member_id: Optional[str] = Field(
        default=None,
        description="member_id of the model to designate as Chairman unconditionally",
    )
    # Idempotency key — duplicate requests with the same key return the existing session
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-supplied idempotency key to prevent duplicate billing",
        max_length=128,
    )
    # Notion archiving
    archive_to_notion: bool = Field(
        default=False,
        description="If true, the completed report is pushed to Notion via MCP",
    )

    @model_validator(mode="after")
    def _validate_research_provider(self) -> "SessionCreateRequest":
        if self.research_enabled and not self.research_provider:
            raise ValueError(
                "research_provider must be specified when research_enabled is true."
            )
        return self

    @field_validator("members")
    @classmethod
    def _validate_members(
        cls, members: list[CouncilMemberConfigSchema]
    ) -> list[CouncilMemberConfigSchema]:
        chairmen = [m for m in members if m.role == "chairman"]
        if len(chairmen) > 1:
            raise ValueError("At most one council member may have role='chairman'.")
        ids = [m.member_id for m in members]
        if len(ids) != len(set(ids)):
            raise ValueError("All member_id values must be unique within a session.")
        return members

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_query": "What are the trade-offs between microservices and a modular monolith?",
                "members": [
                    {"member_id": "member_1", "provider": "openrouter",
                     "model_id": "anthropic/claude-sonnet-4.5", "display_label": "Claude Seat", "role": "member"},
                    {"member_id": "member_2", "provider": "nvidia_nim",
                     "model_id": "meta/llama-3.3-70b-instruct", "display_label": "Llama Seat", "role": "member"},
                    {"member_id": "member_3", "provider": "openrouter",
                     "model_id": "openai/gpt-4.1", "display_label": "GPT Seat", "role": "member"},
                ],
                "research_enabled": True,
                "research_provider": "tavily",
            }
        }
    )


# ── Response schemas ──────────────────────────────────────────────────────

class MemberResponseSchema(BaseModel):
    """Serialised MemberResponse — safe to send to the frontend."""
    member_id: str
    stage: str
    content: str
    anonymized_label: Optional[str] = None
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: Optional[str] = None


class RankingEntrySchema(BaseModel):
    ranked_by_member_id: str
    ranking_order: list[str]
    justification: str


class SessionResponse(BaseModel):
    """
    Full session state returned by GET /sessions/{id}.

    Mirrors CouncilState but with optional fields for stages not yet reached.
    """
    session_id: str
    stage: str
    user_query: str
    member_count: int
    research_enabled: bool
    research_provider: Optional[str] = None

    stage_1_responses: list[MemberResponseSchema] = Field(default_factory=list)
    stage_2_responses: list[MemberResponseSchema] = Field(default_factory=list)
    rankings: list[RankingEntrySchema] = Field(default_factory=list)
    aggregate_scores: dict[str, float] = Field(default_factory=dict)
    chairman_member_id: Optional[str] = None
    final_report_md: Optional[str] = None
    citations: list[dict] = Field(default_factory=list)

    total_cost_usd: float = 0.0
    notion_page_url: Optional[str] = None
    trace_url: Optional[str] = None
    dashboard_spec: Optional[dict] = None

    errors: list[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class SessionSummary(BaseModel):
    """Lightweight session record for list views — avoids deserialising full state."""
    session_id: str
    stage: str
    user_query: str
    member_count: int
    total_cost_usd: float
    created_at: str
    updated_at: str
    notion_page_url: Optional[str] = None


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int
