"""
orchestration/nodes/dashboard_builder_node.py — Dashboard Spec Builder Node.

Generates a json-render DashboardSpec after Stage 2 (rankings available) and
again after Stage 3 (final synthesis complete). The spec is written to
CouncilState.dashboard_spec for the frontend DashboardRenderer to consume.

Design decisions:
  - Pure function: reads state, returns {"dashboard_spec": spec}. Never mutates.
  - Pydantic validation mirrors the frontend catalog.ts schemas — invalid specs
    are rejected server-side before they reach the SSE stream.
  - Phase detection: the node checks whether `final_report_md` is set to decide
    whether it is running post-Stage-2 or post-Stage-3.
  - Stage 3 MERGES on top of the Stage 2 spec (never recreates unchanged widgets).
  - Each helper is capped at ~50 lines per the project architecture rules.

Widget ID conventions (stable keys used by json-render):
  rank_bar_{member_id}          — RankBar per member
  metric_latency_{member_id}    — MetricCard: average latency
  metric_tokens_{member_id}     — MetricCard: total token usage
  metric_cost_{member_id}       — MetricCard: total cost
  token_table                   — TokenTable (session-wide)
  source_list                   — SourceList (research only, Stage 3)
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Literal

from langchain_core.runnables.config import RunnableConfig
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.domain.council_state import CouncilState, MemberResponse

logger = logging.getLogger(__name__)

# ── Build Phase ───────────────────────────────────────────────────────────────

BuildPhase = Literal["stage_2", "stage_3"]

_PHASE_STAGE2: BuildPhase = "stage_2"
_PHASE_STAGE3: BuildPhase = "stage_3"


# ── Pydantic Validation Models (mirrors frontend catalog.ts) ─────────────────

class _RankBarProps(BaseModel):
    # PRD §14: extra='forbid' ensures no unregistered prop (e.g. 'color') silently passes.
    model_config = ConfigDict(extra='forbid')
    label: str
    score: float
    maxScore: float


class _MetricCardProps(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    value: Any          # str | int | float
    unit: str | None = None
    description: str | None = None

    @field_validator("value")
    @classmethod
    def value_must_be_scalar(cls, v: Any) -> Any:
        if not isinstance(v, (str, int, float)):
            raise ValueError("MetricCard value must be str, int, or float")
        return v


class _TokenTableMember(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    tokensIn: int
    tokensOut: int
    costUsd: float


class _TokenTableProps(BaseModel):
    model_config = ConfigDict(extra='forbid')
    members: list[_TokenTableMember]


class _SourceItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str | None = None
    title: str
    snippet: str | None = None


class _SourceListProps(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sources: list[_SourceItem]


class _LatencyChartMember(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    latencyMs: float  # matches frontend LatencyChartSchema.members[].latencyMs


class _LatencyChartProps(BaseModel):
    """Mirrors frontend LatencyChartSchema (catalog.ts). PRD §11.3."""
    model_config = ConfigDict(extra='forbid')
    members: list[_LatencyChartMember]
    unit: str | None = None


class _CostGaugeProps(BaseModel):
    """Mirrors frontend CostGaugeSchema (catalog.ts). PRD §11.3."""
    model_config = ConfigDict(extra='forbid')
    label: str
    costUsd: float
    budgetUsd: float | None = None
    description: str | None = None


class _DashboardElement(BaseModel):
    component: str
    props: dict[str, Any]


class _DashboardSpec(BaseModel):
    root: str
    elements: dict[str, _DashboardElement]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _label_for(member_id: str, members: list[dict]) -> str:
    """Return the display_label for a member_id, falling back to member_id."""
    for m in members:
        if m["member_id"] == member_id:
            return m["display_label"]
    return member_id


def _aggregate_responses(
    responses: list[MemberResponse],
    member_id: str,
) -> dict[str, Any]:
    """
    Aggregate latency, tokens, and cost for a single member across a list of responses.
    Returns a dict with keys: latency_ms, tokens_in, tokens_out, cost_usd.
    """
    relevant = [r for r in responses if r["member_id"] == member_id and not r.get("error")]
    if not relevant:
        return {"latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
    return {
        "latency_ms": sum(r["latency_ms"] for r in relevant),
        "tokens_in": sum(r["tokens_in"] for r in relevant),
        "tokens_out": sum(r["tokens_out"] for r in relevant),
        "cost_usd": round(sum(r["cost_usd"] for r in relevant), 6),
    }


def build_rank_widgets(state: CouncilState) -> dict[str, Any]:
    """
    Build one RankBar element per council member from aggregate_scores.
    Returns a dict of element_id → element dict (json-render format).
    """
    scores: dict[str, float] = state.get("aggregate_scores") or {}
    members: list[dict] = state.get("members") or []

    if not scores:
        return {}

    max_score = max(scores.values(), default=1.0) or 1.0
    elements: dict[str, Any] = {}

    for member_id, score in scores.items():
        widget_id = f"rank_bar_{member_id}"
        elements[widget_id] = {
            "component": "RankBar",
            "props": {
                "label": _label_for(member_id, members),
                "score": round(score, 4),
                "maxScore": round(max_score, 4),
            },
        }

    return elements


def build_metric_widgets(
    state: CouncilState,
    phase: BuildPhase,
) -> dict[str, Any]:
    """
    Build MetricCard elements for latency, token usage, and cost per member.

    Stage 2: uses stage_1_responses (first opinions cost/latency).
    Stage 3: uses stage_1_responses + stage_2_responses combined (full session).
    """
    members: list[dict] = state.get("members") or []
    s1_responses: list[MemberResponse] = state.get("stage_1_responses") or []
    s2_responses: list[MemberResponse] = state.get("stage_2_responses") or []

    all_responses = s1_responses if phase == _PHASE_STAGE2 else s1_responses + s2_responses
    elements: dict[str, Any] = {}

    for member in members:
        mid = member["member_id"]
        label = member["display_label"]
        agg = _aggregate_responses(all_responses, mid)

        elements[f"metric_latency_{mid}"] = {
            "component": "MetricCard",
            "props": {
                "label": f"{label} — Latency",
                "value": agg["latency_ms"],
                "unit": "ms",
                "description": "Total response time",
            },
        }
        elements[f"metric_tokens_{mid}"] = {
            "component": "MetricCard",
            "props": {
                "label": f"{label} — Tokens",
                "value": agg["tokens_in"] + agg["tokens_out"],
                "unit": "tok",
                "description": f"In: {agg['tokens_in']}  Out: {agg['tokens_out']}",
            },
        }
        elements[f"metric_cost_{mid}"] = {
            "component": "MetricCard",
            "props": {
                "label": f"{label} — Cost",
                "value": f"${agg['cost_usd']:.4f}",
                "description": "Accumulated USD cost",
            },
        }

    return elements


def build_token_table(state: CouncilState, phase: BuildPhase) -> dict[str, Any]:
    """
    Build a single TokenTable element aggregating all member responses.
    Stage 2: Stage 1 responses only. Stage 3: all responses combined.
    """
    members: list[dict] = state.get("members") or []
    s1_responses: list[MemberResponse] = state.get("stage_1_responses") or []
    s2_responses: list[MemberResponse] = state.get("stage_2_responses") or []

    all_responses = s1_responses if phase == _PHASE_STAGE2 else s1_responses + s2_responses
    table_members = []

    for member in members:
        mid = member["member_id"]
        agg = _aggregate_responses(all_responses, mid)
        table_members.append({
            "label": member["display_label"],
            "tokensIn": agg["tokens_in"],
            "tokensOut": agg["tokens_out"],
            "costUsd": agg["cost_usd"],
        })

    return {
        "token_table": {
            "component": "TokenTable",
            "props": {"members": table_members},
        }
    }


def build_source_widgets(state: CouncilState) -> dict[str, Any]:
    """
    Build a SourceList element when research is enabled and sources exist.
    Only called during Stage 3.
    """
    if not state.get("research_enabled"):
        return {}

    digest = state.get("research_digest")
    if not digest or not digest.get("sources"):
        return {}

    sources = [
        {
            "url": src.get("url"),
            "title": src.get("title", "Untitled"),
            "snippet": src.get("snippet"),
        }
        for src in digest["sources"]
    ]

    return {
        "source_list": {
            "component": "SourceList",
            "props": {"sources": sources},
        }
    }


def compose_dashboard_spec(elements: dict[str, Any]) -> dict[str, Any]:
    """
    Assemble the final json-render spec from a flat elements dict.
    The root is set to the first element key (arbitrary — Renderer walks all elements).
    """
    if not elements:
        raise ValueError("Cannot compose an empty dashboard spec — no widgets generated.")

    root_key = next(iter(elements))
    return {
        "root": root_key,
        "elements": elements,
    }


def validate_dashboard_spec(spec: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate the generated spec against Pydantic models.
    Returns (is_valid, error_messages).
    Never raises — errors are returned for structured logging.
    """
    errors: list[str] = []

    try:
        parsed = _DashboardSpec.model_validate(spec)
    except ValidationError as exc:
        return False, [str(e) for e in exc.errors()]

    # Per-element props validation
    _PROP_MODELS: dict[str, type[BaseModel]] = {
        "RankBar":       _RankBarProps,
        "MetricCard":    _MetricCardProps,
        "LatencyChart":  _LatencyChartProps,
        "CostGauge":     _CostGaugeProps,
        "TokenTable":    _TokenTableProps,
        "SourceList":    _SourceListProps,
    }

    for elem_id, element in parsed.elements.items():
        model_cls = _PROP_MODELS.get(element.component)
        if model_cls is None:
            errors.append(f"Unknown component '{element.component}' in element '{elem_id}'")
            continue
        try:
            model_cls.model_validate(element.props)
        except ValidationError as exc:
            for e in exc.errors():
                errors.append(f"Element '{elem_id}' ({element.component}): {e['msg']}")

    return len(errors) == 0, errors


# ── LangGraph Node ────────────────────────────────────────────────────────────

async def dashboard_builder_node(
    state: CouncilState,
    config: RunnableConfig,  # noqa: ARG001 — required by LangGraph node signature
) -> dict[str, Any]:
    """
    LangGraph node: build or update the dashboard_spec in CouncilState.

    Execution phases:
        Stage 2 — called after stage_2_review fan-in:
            Generates RankBar + MetricCard + TokenTable.
        Stage 3 — called after stage_3_synthesis:
            Merges final metrics, updates rankings, adds SourceList if research enabled.

    Returns:
        {"dashboard_spec": spec}   on success
        {}                          on validation failure (previous spec preserved)

    Never raises — all errors are logged and swallowed to protect graph continuity.
    """
    # Determine build phase from state
    phase: BuildPhase = _PHASE_STAGE3 if state.get("final_report_md") else _PHASE_STAGE2

    session_id = state.get("session_id", "unknown")
    logger.info(
        "dashboard_builder_node: building spec",
        extra={"session_id": session_id, "phase": phase},
    )

    try:
        # Collect all widget elements for this phase
        elements: dict[str, Any] = {}

        # RankBar widgets — always present if aggregate_scores exist
        elements.update(build_rank_widgets(state))

        # MetricCard + TokenTable — always present
        elements.update(build_metric_widgets(state, phase))
        elements.update(build_token_table(state, phase))

        # SourceList — Stage 3 only, research enabled
        if phase == _PHASE_STAGE3:
            elements.update(build_source_widgets(state))

        # Guard: nothing to render yet (e.g. Stage 2 ran before any scores)
        if not elements:
            logger.warning(
                "dashboard_builder_node: no widgets generated — scores may be empty",
                extra={"session_id": session_id, "phase": phase},
            )
            return {}

        # Assemble the spec
        # Stage 3: merge on top of existing Stage 2 spec (immutable merge)
        if phase == _PHASE_STAGE3 and state.get("dashboard_spec"):
            existing_elements = copy.deepcopy(
                state["dashboard_spec"].get("elements", {})  # type: ignore[index]
            )
            existing_elements.update(elements)      # new widgets overwrite old; Stage 2 unchanged
            elements = existing_elements

        spec = compose_dashboard_spec(elements)

        # Server-side validation before writing to state
        is_valid, validation_errors = validate_dashboard_spec(spec)
        if not is_valid:
            logger.error(
                "dashboard_builder_node: spec failed validation — preserving previous spec",
                extra={
                    "session_id": session_id,
                    "phase": phase,
                    "validation_errors": validation_errors,
                },
            )
            return {}   # Preserve whatever dashboard_spec was there before

        logger.info(
            "dashboard_builder_node: spec built successfully",
            extra={
                "session_id": session_id,
                "phase": phase,
                "widget_count": len(spec["elements"]),
            },
        )
        return {"dashboard_spec": spec}

    except Exception as exc:
        logger.error(
            "dashboard_builder_node: unexpected error — graph execution continues",
            extra={"session_id": session_id, "phase": phase, "error": str(exc)},
            exc_info=True,
        )
        return {}   # Never crash the graph
