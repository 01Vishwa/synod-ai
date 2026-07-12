"""
adapters/observability/langsmith_tracer.py — LangSmith TracerPort implementation.

Implements the domain's TracerPort using the LangSmith SDK.  LangSmith is the
exclusive observability backend for Synod: every LLM call, every tool call,
and every stage transition is a span within one root trace per session.

LangSmith auto-captures traces when LANGSMITH_TRACING=true and the standard
env vars (LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_ENDPOINT) are set.
This adapter additionally provides explicit span management for the LangGraph
nodes that don't go through LangChain's callback mechanism directly.

Design:
  - Uses langsmith.Client for explicit run management.
  - The Decorator pattern: the adapter wraps LLM / tool calls with
    start_span / end_span bookends without the calling code knowing tracing exists.
  - Provider keys and user data are NEVER written to spans.

Pattern: Decorator, Adapter (Hexagonal driven port).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from app.core.config import settings
from app.domain.ports.observability_port import SpanContext, TracerPort

logger = logging.getLogger(__name__)


class LangSmithTracer(TracerPort):
    """
    LangSmith implementation of TracerPort.

    Uses the LangSmith Client for explicit run tree management.
    Falls back to a no-op if LANGSMITH_API_KEY is not set (e.g., local dev
    without a LangSmith account) — tracing is an enhancement, not a hard dep.
    """

    def __init__(self) -> None:
        self._client = None
        self._enabled = bool(settings.LANGSMITH_API_KEY and settings.LANGSMITH_TRACING)

        if self._enabled:
            try:
                from langsmith import Client  # noqa: PLC0415
                self._client = Client(
                    api_url=settings.LANGSMITH_ENDPOINT,
                    api_key=settings.LANGSMITH_API_KEY,
                )
                logger.info(
                    "LangSmith tracing enabled. Project: %s", settings.LANGSMITH_PROJECT
                )
            except ImportError:
                logger.warning(
                    "langsmith package not installed. Tracing disabled. "
                    "Install with: pip install langsmith"
                )
                self._enabled = False
        else:
            logger.info("LangSmith tracing disabled (LANGSMITH_API_KEY not set).")

    # ── TracerPort implementation ─────────────────────────────────────────

    async def start_trace(
        self,
        name: str,
        session_id: str,
        user_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SpanContext:
        trace_id = str(uuid.uuid4())

        if not self._enabled or self._client is None:
            return SpanContext(trace_id=trace_id, span_id=trace_id)

        try:
            self._client.create_run(
                id=trace_id,
                name=name,
                run_type="chain",
                project_name=settings.LANGSMITH_PROJECT,
                inputs={"session_id": session_id},
                tags=["synod", f"session:{session_id}"],
                extra={
                    "metadata": {
                        "session_id": session_id,
                        # user_id intentionally omitted from traces (PII)
                        **(metadata or {}),
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create LangSmith trace: %s", exc)

        return SpanContext(
            trace_id=trace_id,
            span_id=trace_id,
            metadata={"session_id": session_id},
        )

    async def start_span(
        self,
        name: str,
        parent: SpanContext,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SpanContext:
        span_id = str(uuid.uuid4())

        if not self._enabled or self._client is None:
            return SpanContext(
                trace_id=parent.trace_id,
                span_id=span_id,
                provider=parent.provider,
                model_id=parent.model_id,
            )

        try:
            self._client.create_run(
                id=span_id,
                name=name,
                run_type="llm" if metadata and metadata.get("is_llm_call") else "chain",
                parent_run_id=parent.span_id,
                project_name=settings.LANGSMITH_PROJECT,
                inputs=metadata or {},
                tags=["synod", name],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create LangSmith span '%s': %s", name, exc)

        return SpanContext(
            trace_id=parent.trace_id,
            span_id=span_id,
            provider=metadata.get("provider") if metadata else None,
            model_id=metadata.get("model_id") if metadata else None,
            metadata=metadata or {},
        )

    async def end_span(
        self,
        context: SpanContext,
        *,
        output: Optional[Any] = None,
        error: Optional[Exception] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        if not self._enabled or self._client is None:
            return

        try:
            self._client.update_run(
                run_id=context.span_id,
                outputs={"result": str(output)[:2000] if output else None},
                error=str(error) if error else None,
                extra={
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                    "cost_usd": cost_usd,
                },
                end_time=time.time(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to end LangSmith span: %s", exc)

    async def end_trace(
        self,
        context: SpanContext,
        *,
        output: Optional[Any] = None,
        error: Optional[Exception] = None,
    ) -> None:
        if not self._enabled or self._client is None:
            return

        try:
            self._client.update_run(
                run_id=context.trace_id,
                outputs={"summary": str(output)[:4000] if output else None},
                error=str(error) if error else None,
                end_time=time.time(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to end LangSmith trace: %s", exc)

    def get_trace_url(self, trace_id: str) -> Optional[str]:
        """Return a deep-link into the LangSmith project for this trace."""
        if not self._enabled:
            return None
        project = settings.LANGSMITH_PROJECT
        endpoint = settings.LANGSMITH_ENDPOINT.rstrip("/")
        # LangSmith deep-link format
        return f"{endpoint}/projects/{project}/runs/{trace_id}"

    @classmethod
    def instance(cls) -> "LangSmithTracer":
        """Process-level singleton accessor."""
        if not hasattr(cls, "_singleton"):
            cls._singleton = cls()
        return cls._singleton
