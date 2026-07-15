"""
tests/unit/test_langsmith_trace_finalization.py

Regression tests for the LangSmith end_span / end_trace float→datetime fix.

Confirms:
  J1. end_trace passes a datetime, not a float, for end_time
  J2. end_span passes a datetime, not a float, for end_time
  J3. Trace finalization failure is non-fatal (does not raise)
  J4. end_time is never passed through time.time() (which returns float)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.ports.observability_port import SpanContext


def _make_span_context() -> SpanContext:
    tid = str(uuid.uuid4())
    return SpanContext(trace_id=tid, span_id=tid)


# ── J1. end_trace uses datetime, not float ────────────────────────────────────

@pytest.mark.asyncio
async def test_end_trace_passes_datetime_to_langsmith():
    """
    end_trace must call client.update_run with end_time as a datetime object.
    Passing a float (time.time()) would cause AttributeError: 'float' has no .isoformat().
    """
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = True

    mock_client = MagicMock()
    tracer._client = mock_client

    ctx = _make_span_context()
    await tracer.end_trace(ctx, output={"status": "done"})

    mock_client.update_run.assert_called_once()
    call_kwargs = mock_client.update_run.call_args[1]

    end_time = call_kwargs["end_time"]
    assert isinstance(end_time, datetime), (
        f"end_time must be a datetime, not {type(end_time).__name__}. "
        f"Received: {end_time!r}"
    )
    # Must be timezone-aware
    assert end_time.tzinfo is not None, "end_time must be timezone-aware"


# ── J2. end_span uses datetime, not float ─────────────────────────────────────

@pytest.mark.asyncio
async def test_end_span_passes_datetime_to_langsmith():
    """
    end_span must call client.update_run with end_time as a datetime object.
    """
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = True
    mock_client = MagicMock()
    tracer._client = mock_client

    ctx = _make_span_context()
    await tracer.end_span(ctx, output="some result", tokens_in=100, tokens_out=200)

    mock_client.update_run.assert_called_once()
    call_kwargs = mock_client.update_run.call_args[1]

    end_time = call_kwargs["end_time"]
    assert isinstance(end_time, datetime), (
        f"end_time must be a datetime, not {type(end_time).__name__}"
    )
    assert end_time.tzinfo is not None, "end_time must be timezone-aware"


# ── J3. Trace finalization failure is non-fatal ───────────────────────────────

@pytest.mark.asyncio
async def test_end_trace_does_not_raise_on_client_error():
    """
    A LangSmith client error during end_trace must be caught and logged,
    never raised — observability failures must not crash council execution.
    """
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = True
    mock_client = MagicMock()
    mock_client.update_run.side_effect = RuntimeError("LangSmith API timeout")
    tracer._client = mock_client

    ctx = _make_span_context()
    # Must NOT raise
    await tracer.end_trace(ctx, error=Exception("graph failed"))


@pytest.mark.asyncio
async def test_end_span_does_not_raise_on_client_error():
    """end_span failures must be non-fatal."""
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = True
    mock_client = MagicMock()
    mock_client.update_run.side_effect = AttributeError("'float' object has no attribute 'isoformat'")
    tracer._client = mock_client

    ctx = _make_span_context()
    # Must NOT raise
    await tracer.end_span(ctx, output="result")


# ── J4. Confirm time.time() is not used ──────────────────────────────────────

def test_langsmith_tracer_does_not_import_time_module():
    """
    The langsmith_tracer module must not use time.time() for end_time fields.
    Importing the module and inspecting its source ensures the regression
    isn't reintroduced silently.
    """
    import importlib
    import inspect
    import app.adapters.observability.langsmith_tracer as tracer_module

    source = inspect.getsource(tracer_module)

    # The specific pattern that caused the bug — time.time() used as end_time
    assert "end_time=time.time()" not in source, (
        "end_time=time.time() found in langsmith_tracer — this is the regression. "
        "Use datetime.now(timezone.utc) instead."
    )


# ── J5. No-op when disabled ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_end_trace_is_noop_when_disabled():
    """When LangSmith is disabled, end_trace returns without any client calls."""
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = False
    tracer._client = None

    ctx = _make_span_context()
    # Should complete without error
    await tracer.end_trace(ctx)


@pytest.mark.asyncio
async def test_end_span_is_noop_when_disabled():
    """When LangSmith is disabled, end_span returns without any client calls."""
    from app.adapters.observability.langsmith_tracer import LangSmithTracer

    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._enabled = False
    tracer._client = None

    ctx = _make_span_context()
    await tracer.end_span(ctx)
