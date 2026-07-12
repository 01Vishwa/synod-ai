"""
domain/ports/observability_port.py — Port for the tracing / observability backend.

Decouples the orchestration layer from any specific tracing SDK (LangSmith,
Langfuse, OpenTelemetry). Every LLM / tool call in the graph goes through
this port — the domain never knows which backend is listening.

Pattern: Decorator (the tracer wraps calls), Observer (spans are events),
         Port (Hexagonal Architecture driven port).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional


@dataclass
class SpanContext:
    """Identifies a running trace span so children can be nested under it."""
    trace_id: str
    span_id: str
    provider: Optional[str] = None
    model_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TracerPort(ABC):
    """
    Driven port: observability interface for LLM / tool call tracing.

    Concrete implementation: adapters/observability/langsmith_tracer.py
    """

    @abstractmethod
    async def start_trace(
        self,
        name: str,
        session_id: str,
        user_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SpanContext:
        """
        Open a new root trace for one council session run.

        Returns a SpanContext that child spans must reference.
        """
        ...

    @abstractmethod
    async def start_span(
        self,
        name: str,
        parent: SpanContext,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SpanContext:
        """Open a child span nested under `parent`."""
        ...

    @abstractmethod
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
        """Close a span, recording output, error, and cost metrics."""
        ...

    @abstractmethod
    async def end_trace(
        self,
        context: SpanContext,
        *,
        output: Optional[Any] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Close the root trace for a session."""
        ...

    def get_trace_url(self, trace_id: str) -> Optional[str]:
        """Return a deep-link URL into the observability backend, if available."""
        return None
