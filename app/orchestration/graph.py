"""
orchestration/graph.py — LangGraph State Machine.

Constructs the multi-agent execution graph for the Council session.
"""
from __future__ import annotations

import logging
import operator
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from langchain_core.runnables.config import RunnableConfig

from app.domain.council_state import CouncilState
from app.domain.rules.anonymization import build_anonymization_map, shuffle_responses_for_reviewer
from app.domain.rules.ranking import borda_count, elect_chairman
from app.orchestration.context import get_deps
from app.orchestration.nodes.research import research_node
from app.orchestration.nodes.stage_1 import stage_1_node, Stage1Task
from app.orchestration.nodes.stage_2 import stage_2_node, Stage2Task
from app.orchestration.nodes.stage_3 import stage_3_node
from app.orchestration.nodes.notion_archivist_node import notion_archivist_node
from app.orchestration.nodes.dashboard_builder_node import dashboard_builder_node
from app.core.event_bus import PeerReviewStarted, get_or_create_bus

logger = logging.getLogger(__name__)


# ── LangGraph State definition ─────────────────────────────────────────────
# We wrap CouncilState with LangGraph's Annotated reducers so that lists
# are appended to rather than overwritten during parallel fan-out steps.
class OrchestratorState(CouncilState):
    stage_1_responses: Annotated[list, operator.add] # type: ignore
    stage_2_responses: Annotated[list, operator.add] # type: ignore
    rankings: Annotated[list, operator.add] # type: ignore
    errors: Annotated[list, operator.add] # type: ignore


# ── Edge Functions & Reducers ─────────────────────────────────────────────

def should_research(state: OrchestratorState) -> str:
    """Determine if we should route to research or directly to Stage 1."""
    if state.get("research_enabled") and state.get("research_provider"):
        return "research"
    return "stage_1_setup"


async def setup_stage_1(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Saves the checkpoint indicating stage_1 has started."""
    deps = get_deps(config)
    logger.info(
        "STAGE_1_SETUP_ENTERED",
        extra={
            "session_id": state.get("session_id", ""),
            "user_id": state.get("user_id", "<missing>"),
        },
    )
    updates = {
        "stage": "stage_1",
        "session_status": "running",
        "stage_1_status": "running",
        "stage_2_status": "pending",
        "stage_3_status": "pending",
    }
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state)
    return updates


def route_stage_1(state: OrchestratorState) -> list[Any]:
    """Fan-out to all council members for Stage 1."""
    # We use LangGraph's Send API to execute stage_1_node in parallel
    from langgraph.types import Send

    # user_id is now a declared field in CouncilState — safe to access directly.
    # Never use .get("user_id", "") — an empty default silently breaks persistence.
    session_id: str = state["session_id"]
    user_id: str = state["user_id"]

    tasks = []
    for member in state["members"]:
        task: Stage1Task = {
            "member": member,
            "user_query": state["user_query"],
            "research_digest": state.get("research_digest"),
            "user_id": user_id,
            "session_id": session_id,
        }
        tasks.append(Send("stage_1_draft", task))
    return tasks


async def validate_stage_1(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Validate Stage 1 results and determine next stage routing."""
    deps = get_deps(config)
    responses = state.get("stage_1_responses", []) or []
    
    successful_member_ids = []
    excluded_member_ids = []
    
    for member in state["members"]:
        resp = next((r for r in responses if r["member_id"] == member["member_id"]), None)
        if resp and not resp.get("error") and resp.get("content"):
            successful_member_ids.append(member["member_id"])
        else:
            excluded_member_ids.append(member["member_id"])
            
    num_success = len(successful_member_ids)
    
    updates = {
        "successful_member_ids": successful_member_ids,
        "excluded_member_ids": excluded_member_ids,
    }
    
    if num_success == 0:
        updates.update({
            "stage": "error",
            "session_status": "failed",
            "stage_1_status": "failed",
            "stage_2_status": "skipped",
            "stage_3_status": "skipped",
            "terminal_error": {
                "code": "NO_VALID_STAGE_1_RESPONSES",
                "message": "All Council members failed to produce a valid response.",
            }
        })
    elif num_success == 1:
        updates.update({
            "stage": "stage_3",
            "session_status": "degraded",
            "stage_1_status": "degraded",
            "stage_2_status": "skipped",
            "stage_3_status": "running",
        })
    else:
        updates.update({
            "stage_1_status": "completed",
            "stage_2_status": "running",
        })
        
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state)
    return updates


def route_after_stage_1(state: OrchestratorState) -> str:
    num_success = len(state.get("successful_member_ids", []))
    if num_success == 0:
        return "finish"
    elif num_success == 1:
        return "stage_3_setup"
    else:
        return "stage_2_setup"


async def setup_stage_2(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """
    Transition from Stage 1 to Stage 2.
    Builds the anonymisation map and saves the checkpoint.
    """
    deps = get_deps(config)
    logger.info(
        "STAGE_2_SETUP_ENTERED",
        extra={
            "session_id": state.get("session_id", ""),
            "user_id": state.get("user_id", "<missing>"),
        },
    )

    # Anonymise mapping ONLY for successful members
    successful_member_ids = state.get("successful_member_ids", [])
    active_members = [m for m in state["members"] if m["member_id"] in successful_member_ids]
    anon_map = build_anonymization_map(active_members)

    updates = {
        "stage": "stage_2",
        "anonymization_map": anon_map,
    }

    # Apply local updates for the checkpoint save
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore

    # Publish PeerReviewStarted before the fan-out so the SSE endpoint
    # can show the peer-review phase starting in real time.
    bus = await get_or_create_bus(state["session_id"])
    await bus.publish(PeerReviewStarted(session_id=state["session_id"]))

    return updates


def route_stage_2(state: OrchestratorState) -> list[Any]:
    """Fan-out to all council members for Stage 2 (Peer Review)."""
    from langgraph.types import Send

    # user_id is a declared field — access directly, never use empty-string default.
    user_id: str = state["user_id"]

    anon_map = state["anonymization_map"]
    stage_1_responses = state["stage_1_responses"]

    successful_member_ids = state.get("successful_member_ids")
    if successful_member_ids is None:
        successful_member_ids = [
            r["member_id"] for r in stage_1_responses
            if not r.get("error") and r.get("content")
        ]

    valid_responses = [r for r in stage_1_responses if r["member_id"] in successful_member_ids]
    active_members = [m for m in state["members"] if m["member_id"] in successful_member_ids]

    tasks = []
    for member in active_members:
        # Each member gets a uniquely shuffled, anonymised bundle of Stage 1 responses
        shuffled = shuffle_responses_for_reviewer(
            responses=valid_responses,
            anonymization_map=anon_map,
            reviewer_member_id=member["member_id"],
        )

        task: Stage2Task = {
            "member": member,
            "user_query": state["user_query"],
            "shuffled_responses": shuffled,
            "user_id": user_id,
            "session_id": state["session_id"],
            "total_reviewers": len(active_members),
        }
        tasks.append(Send("stage_2_review", task))
    return tasks


async def validate_stage_2(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Validate Stage 2 results and determine if we can proceed to Stage 3 or degrade."""
    deps = get_deps(config)
    stage_2_responses = state.get("stage_2_responses", []) or []
    
    valid_peer_reviews = [
        r for r in stage_2_responses
        if not r.get("error") and r.get("content")
    ]
    
    updates = {}
    if len(valid_peer_reviews) == 0:
        updates.update({
            "stage_2_status": "failed",
            "session_status": "degraded",
        })
        logger.warning("validate_stage_2: 0 valid peer reviews. Degrading session.")
    else:
        updates.update({
            "stage_2_status": "completed",
        })
        
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state)
    return updates


async def setup_stage_3(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """
    Transition from Stage 2 to Stage 3.
    Computes Borda count rankings, elects Chairman, and saves checkpoint.
    """
    deps = get_deps(config)
    logger.info(
        "STAGE_3_SETUP_ENTERED",
        extra={
            "session_id": state.get("session_id", ""),
            "user_id": state.get("user_id", "<missing>"),
        },
    )

    successful_member_ids = state.get("successful_member_ids", []) or []
    
    # Compute aggregate scores only if we have active members and valid rankings
    scores = {}
    stage_2_responses = state.get("stage_2_responses", []) or []
    valid_peer_reviews = [
        r for r in stage_2_responses
        if not r.get("error") and r.get("content")
    ]

    if len(valid_peer_reviews) > 0 and len(successful_member_ids) >= 2:
        scores = borda_count(
            ballots=state["rankings"],
            member_ids=successful_member_ids,
            anon_map=state["anonymization_map"] or {},
        )

    updates = {
        "stage": "stage_3",
        "aggregate_scores": scores,
    }

    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore
    return updates


async def validate_chairman(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Validate that we have an executable Chairman for Stage 3 synthesis."""
    deps = get_deps(config)
    original_chairman_id = state.get("chairman_member_id") or ""
    successful_member_ids = state.get("successful_member_ids", []) or []
    
    effective_chairman_id = ""
    chairman_fallback_used = False
    
    if original_chairman_id in successful_member_ids:
        effective_chairman_id = original_chairman_id
    else:
        # Pinned Chairman failed or is unavailable. Fallback deterministic policy
        if successful_member_ids:
            scores = state.get("aggregate_scores") or {}
            valid_scores = {k: v for k, v in scores.items() if k in successful_member_ids}
            if valid_scores:
                effective_chairman_id = max(valid_scores, key=lambda mid: valid_scores[mid])
            else:
                effective_chairman_id = successful_member_ids[0]
            chairman_fallback_used = True

    updates = {
        "effective_chairman_id": effective_chairman_id,
        "chairman_member_id": effective_chairman_id,
        "chairman_fallback_used": chairman_fallback_used,
        "original_chairman_id": original_chairman_id,
    }

    if not effective_chairman_id:
        updates.update({
            "stage": "error",
            "session_status": "failed",
            "stage_3_status": "failed",
            "terminal_error": {
                "code": "NO_EXECUTABLE_CHAIRMAN",
                "message": "No valid Council member could be elected as Chairman.",
            }
        })
    else:
        updates.update({
            "stage_3_status": "running",
        })

    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state)
    return updates


def route_after_chairman_validation(state: OrchestratorState) -> str:
    if not state.get("effective_chairman_id"):
        return "finish"
    return "stage_3_synthesis"


async def finish_session(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal node: marks the session as done and saves the final checkpoint."""
    deps = get_deps(config)
    
    stage = "done"
    session_status = "completed"
    
    if state.get("stage") == "error":
        stage = "error"
        session_status = "failed"
    elif state.get("session_status") == "degraded":
        session_status = "degraded"
        
    stage_1_status = state.get("stage_1_status")
    stage_2_status = state.get("stage_2_status")
    stage_3_status = state.get("stage_3_status")
    
    if stage_1_status == "running":
        stage_1_status = "completed"
    if stage_2_status == "running":
        stage_2_status = "completed"
    if stage_3_status == "running":
        stage_3_status = "completed"
        
    updates = {
        "stage": stage,
        "session_status": session_status,
        "stage_1_status": stage_1_status,
        "stage_2_status": stage_2_status,
        "stage_3_status": stage_3_status,
    }
    
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore
    
    # Close the root trace
    await deps.tracer.end_trace(deps.root_span, output={"status": stage})
    
    return updates


# ── Graph Builder ──────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Builds and compiles the StateGraph for the Council."""
    builder = StateGraph(OrchestratorState)
    
    # Nodes
    builder.add_node("research", research_node)
    builder.add_node("stage_1_setup", setup_stage_1)
    builder.add_node("stage_1_draft", stage_1_node)
    builder.add_node("validate_stage_1", validate_stage_1)
    builder.add_node("stage_2_setup", setup_stage_2)
    builder.add_node("stage_2_review", stage_2_node)
    builder.add_node("validate_stage_2", validate_stage_2)
    builder.add_node("stage_3_setup", setup_stage_3)
    builder.add_node("validate_chairman", validate_chairman)
    builder.add_node("stage_3_synthesis", stage_3_node)
    builder.add_node("dashboard_build_s2", dashboard_builder_node)
    builder.add_node("dashboard_build_s3", dashboard_builder_node)
    builder.add_node("archive", notion_archivist_node)
    builder.add_node("finish", finish_session)

    # Edges
    builder.add_conditional_edges(START, should_research)
    
    # Research -> Stage 1 Setup
    builder.add_edge("research", "stage_1_setup")
    
    # Stage 1 Setup -> Stage 1 Drafts (Fan-out)
    builder.add_conditional_edges("stage_1_setup", route_stage_1)
    
    # Stage 1 Drafts -> Validate Stage 1 (Fan-in)
    builder.add_edge("stage_1_draft", "validate_stage_1")
    
    # Validate Stage 1 -> Setup Stage 2 OR Stage 3 Setup OR Finish
    builder.add_conditional_edges("validate_stage_1", route_after_stage_1)
    
    # Stage 2 Setup -> Stage 2 Reviews (Fan-out)
    builder.add_conditional_edges("stage_2_setup", route_stage_2)
    
    # Stage 2 Reviews -> Dashboard Build S2 (Fan-in) -> Validate Stage 2 -> Stage 3 Setup
    builder.add_edge("stage_2_review", "dashboard_build_s2")
    builder.add_edge("dashboard_build_s2", "validate_stage_2")
    builder.add_edge("validate_stage_2", "stage_3_setup")
    
    # Stage 3 Setup -> Validate Chairman
    builder.add_edge("stage_3_setup", "validate_chairman")
    
    # Validate Chairman -> Stage 3 Synthesis OR Finish
    builder.add_conditional_edges("validate_chairman", route_after_chairman_validation)
    
    # Stage 3 Synthesis -> Dashboard Build S3 -> Archive
    builder.add_edge("stage_3_synthesis", "dashboard_build_s3")
    builder.add_edge("dashboard_build_s3", "archive")
    
    # Archive -> Finish
    builder.add_edge("archive", "finish")
    
    builder.add_edge("finish", END)

    return builder.compile()


graph = build_graph()
