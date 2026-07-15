"""
orchestration/runner.py — Graph execution wrapper.

Provides the entrypoint for launching the LangGraph orchestrator as a background
task from the FastAPI route handler.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from app.adapters.observability.langsmith_tracer import LangSmithTracer
from app.adapters.persistence.database import async_session_factory
from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
from app.adapters.security.key_vault import KeyVault
from app.core.config import settings
from app.core.exceptions import CouncilStateValidationError, StateIdentityMismatchError
from app.core.llm_router import LLMRouter
from app.domain.council_state import CouncilState
from app.domain.identity import require_uuid
from app.domain.ports.observability_port import SpanContext
from app.orchestration.context import GraphDependencies
from app.orchestration.graph import graph

logger = logging.getLogger(__name__)

# Module-level reference to the process singleton — set by set_llm_router_singleton
# during app startup (see main.py lifespan).  Background tasks run outside the
# FastAPI request lifecycle so we cache the reference here.
_llm_router: LLMRouter | None = None


def _get_llm_router() -> LLMRouter:
    """
    Return the process-level LLMRouter singleton.

    Prefer the instance registered via set_llm_router_singleton().
    If not yet set, create a default instance (mainly useful in tests).
    """
    global _llm_router
    if _llm_router is None:
        logger.warning(
            "LLMRouter singleton not pre-set — creating with default settings. "
            "Call set_llm_router_singleton() during app startup to avoid this."
        )
        _llm_router = LLMRouter(max_attempts=settings.COUNCIL_MEMBER_MAX_RETRIES + 1)
    return _llm_router


def set_llm_router_singleton(router: LLMRouter) -> None:
    """Called from main.py lifespan to register the process singleton."""
    global _llm_router
    _llm_router = router


def _build_langfuse_callback() -> Any | None:
    """
    Conditionally build a Langfuse CallbackHandler.

    Returns a handler instance when LANGFUSE_TRACING=true and both
    LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set; returns None otherwise
    so callers can safely do ``[h for h in [_build_langfuse_callback()] if h]``.

    The handler is compatible with the LangChain callback interface and is passed
    directly into the graph's RunnableConfig so every node execution and LLM call
    is automatically captured as a span in the Langfuse dashboard.
    """
    if not settings.LANGFUSE_TRACING:
        return None
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        logger.warning(
            "LANGFUSE_TRACING=true but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY "
            "are not set — Langfuse tracing disabled."
        )
        return None

    try:
        from langfuse.callback import CallbackHandler  # noqa: PLC0415
        handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("Langfuse tracing enabled. Host: %s", settings.LANGFUSE_HOST)
        return handler
    except ImportError:
        logger.warning(
            "langfuse package not installed — tracing disabled. "
            "Install with: pip install langfuse"
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialise Langfuse callback handler: %s", exc)
        return None


async def run_council_graph(
    initial_state: CouncilState,
    trace_context: SpanContext,
    user_id: str,
) -> None:
    """
    Execute the council session graph in the background.

    Lifecycle:
        1. Validate authoritative user_id — abort immediately if invalid.
        2. Validate state identity consistency (state user_id must match arg).
        3. Inject validated user_id into state.
        4. Open a fresh db_session (independent of the HTTP request lifecycle).
        5. Write and COMMIT running marker — abort if this fails (precondition).
        6. Invoke graph.ainvoke with full timeout guard.
        7. COMMIT after success (persists all save_checkpoint flush() calls).
        8. On failure: open a NEW independent session to persist the error state.

    Running-marker is a HARD precondition (Phase 7):
        If the runner cannot write the running marker, the session row is not
        visible in the DB (transaction race) or the identity is wrong.
        The graph must NOT execute — doing so would call LLMs against a session
        the runner cannot persist to, wasting tokens and failing loudly later.

    Fix summary:
        Bug 1 — transaction race: callers must commit before calling this function.
        Bug 2 — user_id="": validated and injected explicitly; state field declared.
        Bug 3 — running marker non-fatal: now an abort precondition.
    """
    session_id = initial_state.get("session_id", "")

    # ── Step 1: Validate authoritative user_id ────────────────────────────
    # user_id is a required positional argument (no default). Validate format.
    try:
        authoritative_uuid = require_uuid(user_id, field_name="user_id")
    except CouncilStateValidationError:
        logger.error(
            "COUNCIL_START_PRECONDITION_FAILED",
            extra={
                "session_id": str(session_id),
                "reason": "authoritative user_id is not a valid UUID",
            },
        )
        return

    authoritative_user_id = str(authoritative_uuid)

    # ── Step 2: Validate state identity consistency ───────────────────────
    state_user_id = initial_state.get("user_id")
    if state_user_id is not None and str(state_user_id).strip():
        # Non-empty state user_id must match the authoritative user_id.
        try:
            state_uuid = require_uuid(state_user_id, field_name="state.user_id")
        except CouncilStateValidationError:
            logger.error(
                "STATE_IDENTITY_INVALID",
                extra={
                    "session_id": str(session_id),
                    "reason": "state.user_id is not a valid UUID",
                },
            )
            return

        if state_uuid != authoritative_uuid:
            logger.error(
                "STATE_IDENTITY_MISMATCH",
                extra={
                    "session_id": str(session_id),
                    "reason": "state user_id does not match authoritative user_id",
                },
            )
            await _write_error_to_repo(
                session_id=session_id,
                user_id=authoritative_user_id,
                error_msg=(
                    "StateIdentityMismatchError: state user_id does not match "
                    "the authoritative user_id supplied to the runner."
                ),
            )
            return

    # ── Step 2.5: Validate council members exist ──────────────────────────
    if not initial_state.get("members"):
        logger.error(
            "COUNCIL_MEMBERS_EMPTY",
            extra={
                "session_id": str(session_id),
                "reason": "initial_state has no members configured",
            },
        )
        await _write_error_to_repo(
            session_id=session_id,
            user_id=authoritative_user_id,
            error_msg="COUNCIL_MEMBERS_EMPTY: No council members were resolved or configured for this session.",
        )
        return

    # ── Step 3: Inject validated user_id into state ───────────────────────
    # Propagate the validated user_id into the state so every graph node and
    # repository call has access to it via the declared CouncilState field.
    initial_state = {**initial_state, "user_id": authoritative_user_id}  # type: ignore[assignment]

    logger.info(
        "COUNCIL_ORCHESTRATOR_STARTED",
        extra={
            "session_id": str(session_id),
            "user_id": authoritative_user_id,
        },
    )
    logger.info(
        "COUNCIL_EXECUTION_IDENTITY_VALIDATED",
        extra={
            "session_id": str(session_id),
            "user_id": authoritative_user_id,
        },
    )

    tracer = None

    async with async_session_factory() as db_session:
        repository = PostgresSessionRepository(db_session)

        # ── Step 5: Running-marker — HARD precondition ────────────────────
        # If this fails, the session row is not yet visible (transaction race)
        # or the identity is wrong. Either way the graph must NOT run.
        logger.info(
            "RUNNING_MARKER_WRITE_STARTED",
            extra={"session_id": str(session_id)},
        )
        try:
            running_marker = dict(initial_state)
            running_marker["_execution_status"] = "running"
            await repository.save_checkpoint(running_marker)  # type: ignore[arg-type]
            await db_session.commit()
            logger.info(
                "RUNNING_MARKER_COMMITTED",
                extra={"session_id": str(session_id)},
            )
        except Exception as marker_exc:
            logger.error(
                "COUNCIL_START_PRECONDITION_FAILED",
                extra={
                    "session_id": str(session_id),
                    "reason": str(marker_exc),
                },
            )
            try:
                await db_session.rollback()
            except Exception:
                pass
            # Attempt to write error state through an independent session.
            # This may also fail if the row is not yet visible — that is
            # expected and logged internally by _write_error_to_repo.
            await _write_error_to_repo(
                session_id=session_id,
                user_id=authoritative_user_id,
                error_msg=(
                    f"Council execution aborted: could not write running marker. "
                    f"Cause: {marker_exc}"
                ),
            )
            return  # DO NOT invoke the graph

        try:
            vault = KeyVault.instance()
            tracer = LangSmithTracer.instance()

            deps = GraphDependencies(
                vault=vault,
                tracer=tracer,
                repository=repository,
                root_span=trace_context,
                llm_router=_get_llm_router(),
                db_session_factory=async_session_factory,
            )

            # Build optional Langfuse callback list (empty when Langfuse is not configured)
            langfuse_handler = _build_langfuse_callback()
            callbacks = [langfuse_handler] if langfuse_handler else []

            config: RunnableConfig = {
                "configurable": {
                    "deps": deps,
                },
                "recursion_limit": 50,  # Prevent infinite loops in the graph
                "callbacks": callbacks,  # Langfuse (and any future) callback handlers
            }

            logger.info(
                "MODEL_ROUTER_ENTERED",
                extra={
                    "session_id": str(session_id),
                    "member_count": len(initial_state.get("members", [])),
                },
            )

            # Run with a hard timeout so we never hang forever.
            await asyncio.wait_for(
                graph.ainvoke(initial_state, config=config),
                timeout=settings.GRAPH_TIMEOUT_SECONDS,
            )

            # ── CRITICAL FIX (Bug 2) ──────────────────────────────────────
            # save_checkpoint() only calls flush() — data lives in the DB
            # transaction buffer but is NOT durable until this commit.
            # Without this line every checkpoint write is rolled back when the
            # async_session_factory context manager exits, leaving the DB row
            # permanently at stage=stage_1, updated_at=created_at.
            await db_session.commit()
            logger.info(
                "Graph execution completed and persisted for session %s.", session_id
            )

        except asyncio.TimeoutError:
            error_msg = (
                f"Graph execution timed out after {settings.GRAPH_TIMEOUT_SECONDS}s. "
                "The LLM provider(s) may be unreachable or the models may be too slow."
            )
            logger.error(
                "COUNCIL_GRAPH_FAILED",
                extra={
                    "session_id": str(session_id),
                    "error_type": "TimeoutError",
                    "error_message": error_msg,
                },
            )
            # Rollback the in-flight transaction before opening an independent
            # error-persistence session.
            try:
                await db_session.rollback()
            except Exception:
                pass
            await _write_error_to_repo(session_id, authoritative_user_id, error_msg)
            if tracer:
                await tracer.end_trace(trace_context, error=Exception(error_msg))

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "COUNCIL_GRAPH_FAILED",
                extra={
                    "session_id": str(session_id),
                    "error_type": type(exc).__name__,
                },
            )
            try:
                await db_session.rollback()
            except Exception:
                pass
            await _write_error_to_repo(session_id, authoritative_user_id, error_msg)
            if tracer:
                await tracer.end_trace(trace_context, error=exc)


async def _write_error_to_repo(
    session_id: str,
    user_id: str,
    error_msg: str,
) -> None:
    """
    Persist a terminal error state to the database.

    Always opens its OWN independent async_session_factory() session.
    Must never reuse the graph's db_session — it may be rolled back or
    in an inconsistent state after a graph failure.
    """
    try:
        async with async_session_factory() as err_session:
            repository = PostgresSessionRepository(err_session)
            error_state = await repository.load(session_id, user_id=user_id)
            if error_state:
                error_state = dict(error_state)
                error_state["stage"] = "error"
                existing_errors = list(error_state.get("errors", []) or [])
                existing_errors.append({
                    "member_id": "orchestrator",
                    "stage": "system",
                    "code": "EXECUTION_FAILED",
                    "message": error_msg,
                    "timestamp": "",
                })
                error_state["errors"] = existing_errors
                await repository.save_checkpoint(error_state)  # type: ignore[arg-type]
                await err_session.commit()
                logger.info(
                    "SESSION_ERROR_STATE_COMMITTED",
                    extra={"session_id": session_id},
                )
            else:
                logger.warning(
                    "Could not load session %s to write error state — session not found. "
                    "This may indicate the session creation was not yet committed when "
                    "the runner started (transaction race).",
                    session_id,
                )
    except Exception as inner_exc:
        logger.error(
            "Failed to persist error state for session %s: %s",
            session_id,
            inner_exc,
        )
