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
from app.orchestration.nodes.archive import archive_node

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
    await deps.repository.save_checkpoint(state) # type: ignore
    return {"stage": "stage_1"}


def route_stage_1(state: OrchestratorState) -> list[Any]:
    """Fan-out to all council members for Stage 1."""
    # We use LangGraph's Send API to execute stage_1_node in parallel
    from langgraph.constants import Send
    
    tasks = []
    for member in state["members"]:
        task: Stage1Task = {
            "member": member,
            "user_query": state["user_query"],
            "research_digest": state.get("research_digest"),
            "user_id": state.get("user_id", ""),  # type: ignore
        }
        tasks.append(Send("stage_1_draft", task))
    return tasks


async def setup_stage_2(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """
    Transition from Stage 1 to Stage 2.
    Builds the anonymisation map and saves the checkpoint.
    """
    deps = get_deps(config)
    
    # Anonymise mapping
    anon_map = build_anonymization_map(state["members"])
    
    updates = {
        "stage": "stage_2",
        "anonymization_map": anon_map,
    }
    
    # Apply local updates for the checkpoint save
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore
    return updates


def route_stage_2(state: OrchestratorState) -> list[Any]:
    """Fan-out to all council members for Stage 2 (Peer Review)."""
    from langgraph.constants import Send
    
    anon_map = state["anonymization_map"]
    stage_1_responses = state["stage_1_responses"]
    
    tasks = []
    for member in state["members"]:
        # Each member gets a uniquely shuffled, anonymised bundle of Stage 1 responses
        shuffled = shuffle_responses_for_reviewer(
            responses=stage_1_responses,
            anonymization_map=anon_map,
            reviewer_member_id=member["member_id"],
        )
        
        task: Stage2Task = {
            "member": member,
            "user_query": state["user_query"],
            "shuffled_responses": shuffled,
            "user_id": state.get("user_id", ""),  # type: ignore
        }
        tasks.append(Send("stage_2_review", task))
    return tasks


async def setup_stage_3(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """
    Transition from Stage 2 to Stage 3.
    Computes Borda count rankings, elects Chairman, and saves checkpoint.
    """
    deps = get_deps(config)
    
    member_ids = [m["member_id"] for m in state["members"]]
    
    # Compute aggregate scores
    scores = borda_count(
        ballots=state["rankings"],
        member_ids=member_ids,
        anon_map=state["anonymization_map"],
    )
    
    # Elect chairman
    chairman_id = elect_chairman(
        aggregate_scores=scores,
        pinned_member_id=state.get("chairman_member_id"),
    )
    
    updates = {
        "stage": "stage_3",
        "aggregate_scores": scores,
        "chairman_member_id": chairman_id,
    }
    
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore
    return updates


async def finish_session(state: OrchestratorState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal node: marks the session as done and saves the final checkpoint."""
    deps = get_deps(config)
    
    updates = {"stage": "done"}
    updated_state = {**state, **updates}
    await deps.repository.save_checkpoint(updated_state) # type: ignore
    
    # Close the root trace
    await deps.tracer.end_trace(deps.root_span, output={"status": "done"})
    
    return updates


# ── Graph Builder ──────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Builds and compiles the StateGraph for the Council."""
    builder = StateGraph(OrchestratorState)
    
    # Nodes
    builder.add_node("research", research_node)
    builder.add_node("stage_1_setup", setup_stage_1)
    builder.add_node("stage_1_draft", stage_1_node)
    builder.add_node("stage_2_setup", setup_stage_2)
    builder.add_node("stage_2_review", stage_2_node)
    builder.add_node("stage_3_setup", setup_stage_3)
    builder.add_node("stage_3_synthesis", stage_3_node)
    builder.add_node("archive", archive_node)
    builder.add_node("finish", finish_session)

    # Edges
    builder.add_conditional_edges(START, should_research)
    
    # Research -> Stage 1 Setup
    builder.add_edge("research", "stage_1_setup")
    
    # Stage 1 Setup -> Stage 1 Drafts (Fan-out)
    builder.add_conditional_edges("stage_1_setup", route_stage_1)
    
    # Stage 1 Drafts -> Stage 2 Setup (Fan-in)
    builder.add_edge("stage_1_draft", "stage_2_setup")
    
    # Stage 2 Setup -> Stage 2 Reviews (Fan-out)
    builder.add_conditional_edges("stage_2_setup", route_stage_2)
    
    # Stage 2 Reviews -> Stage 3 Setup (Fan-in)
    builder.add_edge("stage_2_review", "stage_3_setup")
    
    # Stage 3 Setup -> Stage 3 Synthesis
    builder.add_edge("stage_3_setup", "stage_3_synthesis")
    
    # Stage 3 Synthesis -> Archive
    builder.add_edge("stage_3_synthesis", "archive")
    
    # Archive -> Finish
    builder.add_edge("archive", "finish")
    
    builder.add_edge("finish", END)

    return builder.compile()


graph = build_graph()
