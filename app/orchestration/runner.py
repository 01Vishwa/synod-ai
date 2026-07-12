"""
orchestration/runner.py — Graph execution wrapper.

Provides the entrypoint for launching the LangGraph orchestrator as a background
task from the FastAPI route handler.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.adapters.observability.langsmith_tracer import LangSmithTracer
from app.adapters.persistence.database import async_session_factory
from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
from app.adapters.security.key_vault import KeyVault
from app.domain.council_state import CouncilState
from app.domain.ports.observability_port import SpanContext
from app.orchestration.context import GraphDependencies
from app.orchestration.graph import graph

logger = logging.getLogger(__name__)


async def run_council_graph(
    initial_state: CouncilState,
    trace_context: SpanContext,
) -> None:
    """
    Execute the council session graph in the background.
    """
    session_id = initial_state["session_id"]
    logger.info("Starting background graph execution for session %s", session_id)

    # We instantiate fresh, request-scoped dependencies for the background task
    # because it runs outside the FastAPI request lifecycle.
    vault = KeyVault.instance()
    tracer = LangSmithTracer.instance()

    async with async_session_factory() as db_session:
        repository = PostgresSessionRepository(db_session)
        
        deps = GraphDependencies(
            vault=vault,
            tracer=tracer,
            repository=repository,
            root_span=trace_context,
            db_session_factory=async_session_factory,
        )

        config: RunnableConfig = {
            "configurable": {
                "deps": deps,
            },
            "recursion_limit": 50,  # Prevent infinite loops in the graph
        }

        try:
            # Execute the graph
            # The LangGraph ainvoke method will run the state machine to completion.
            await graph.ainvoke(initial_state, config=config)
            logger.info("Graph execution completed successfully for session %s", session_id)
        except Exception as exc:
            logger.error("Graph execution failed for session %s: %s", session_id, exc)
            
            # Attempt to save the error state to the database
            try:
                error_state = await repository.load(session_id)
                if error_state:
                    error_state["stage"] = "error"
                    error_state["errors"].append({
                        "member_id": "orchestrator",
                        "stage": "system",
                        "message": f"Fatal graph error: {exc}",
                        "timestamp": "",
                    })
                    await repository.save_checkpoint(error_state)
                    await db_session.commit()
            except Exception as inner_exc:
                logger.error("Failed to save error state for session %s: %s", session_id, inner_exc)
            
            # Close the trace with the error
            await tracer.end_trace(trace_context, error=exc)
