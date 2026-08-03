"""
tests/unit/test_stage_1_node.py — Stage 1 node unit tests.

Tests:
  1. Successful streaming call → stage_1_responses has content, bus events fired.
  2. AuthenticationError → member error response, MemberFailed event, no re-raise.
  3. FallbackExhaustedError → member error response, errors list populated.
  4. Generic exception (e.g. AttributeError) → member error response (regression).
  5. RateLimitError surfaces as FallbackExhaustedError → error MemberResponse.
  6. Key-fetch failure → MemberFailed on bus, error MemberResponse returned.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    AuthenticationError,
    FallbackExhaustedError,
    RateLimitError,
)
from app.orchestration.nodes.stage_1 import Stage1Task, stage_1_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _aiter(*items):
    """Yield items one at a time — simulates an async streaming generator."""
    for item in items:
        yield item


def _make_config(llm_router=None, vault=None, tracer=None, repo=None) -> dict:
    """Build a minimal LangGraph RunnableConfig with GraphDependencies."""
    from app.orchestration.context import GraphDependencies

    mock_tracer = tracer or AsyncMock()
    mock_tracer.start_span = AsyncMock(return_value=MagicMock())
    mock_tracer.end_span = AsyncMock()

    mock_repo = repo or AsyncMock()
    mock_root_span = MagicMock()

    mock_vault = vault or MagicMock()

    # db_session_factory context manager
    mock_session = AsyncMock()
    result_mock = MagicMock()
    # Simulate a valid provider key model with the correct column
    key_model = MagicMock()
    key_model.ciphertext_b64 = "FAKE_ENCRYPTED_KEY"
    key_model.last_test_ok = True
    key_model.key_fingerprint = "fp-test"
    # Deliberately do NOT set key_model.encrypted_key (old wrong attribute)
    result_mock.scalar_one_or_none.return_value = key_model
    mock_session.execute = AsyncMock(return_value=result_mock)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_vault.decrypt.return_value = "sk-decrypted-key"

    deps = GraphDependencies(
        vault=mock_vault,
        tracer=mock_tracer,
        repository=mock_repo,
        root_span=mock_root_span,
        llm_router=llm_router or AsyncMock(),
        db_session_factory=MagicMock(return_value=mock_cm),
    )
    return {"configurable": {"deps": deps}}


def _make_task(member_id: str = "m1", model_id: str = "openai/gpt-4.1-mini") -> Stage1Task:
    return {
        "member": {
            "member_id": member_id,
            "provider": "openrouter",
            "model_id": model_id,
            "display_label": f"Seat {member_id}",
            "role": "council_member",
            "api_key": None,
        },
        "user_query": "What is 2+2?",
        "research_digest": None,
        "user_id": "user-abc",
        "session_id": "session-xyz",
    }


def _make_streaming_router(tokens: list[str] | None = None, side_effect=None):
    """
    Build a mock LLMRouter whose stream_chat is an async generator.

    If `side_effect` is given the generator raises it immediately.
    Otherwise it yields each token in `tokens`.
    """
    mock_router = MagicMock()

    if side_effect is not None:
        async def _stream_raises(*args, **kwargs):
            raise side_effect
            yield  # make it a generator function
        mock_router.stream_chat = _stream_raises
    else:
        deltas = tokens or ["The ", "answer ", "is ", "four."]
        async def _stream_ok(*args, **kwargs):
            for t in deltas:
                yield t
        mock_router.stream_chat = _stream_ok

    return mock_router


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_1_success(monkeypatch):
    """Successful streaming call → stage_1_responses contains one MemberResponse with content."""
    mock_router = _make_streaming_router(["The answer is four."])

    # Patch the event bus so we don't need a real asyncio.Queue
    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )
    # Suppress fire-and-forget task (close the coroutine to silence RuntimeWarning)
    monkeypatch.setattr("app.orchestration.nodes.stage_1.asyncio.create_task", lambda coro: coro.close() or None)

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result
    assert len(result["stage_1_responses"]) == 1
    resp = result["stage_1_responses"][0]
    assert resp["content"] == "The answer is four."
    assert resp["error"] is None
    assert resp["member_id"] == "m1"

    # Verify bus events were published
    published_types = [type(call.args[0]).__name__ for call in mock_bus.publish.call_args_list]
    assert "ProviderConnecting" in published_types
    assert "FirstToken" in published_types
    assert "StreamChunk" in published_types
    assert "MemberCompleted" in published_types


@pytest.mark.asyncio
async def test_stage_1_authentication_error_returns_error_response(monkeypatch):
    """
    AuthenticationError must NOT propagate out of stage_1_node.
    It must be returned as a MemberResponse with error set.
    A MemberFailed event must be published to the bus.
    """
    mock_router = _make_streaming_router(
        side_effect=AuthenticationError(message="Invalid API key.", provider="openrouter")
    )

    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result
    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    assert "credentials" in resp["error"].lower() or "key" in resp["error"].lower()
    assert resp["content"] == ""

    # errors list must also be populated for the session error tracker
    assert "errors" in result
    assert len(result["errors"]) == 1

    # MemberFailed must have been published
    published_types = [type(call.args[0]).__name__ for call in mock_bus.publish.call_args_list]
    assert "MemberFailed" in published_types


@pytest.mark.asyncio
async def test_stage_1_fallback_exhausted_returns_error_response(monkeypatch):
    """FallbackExhaustedError (all retries done) → error MemberResponse, no raise."""
    mock_router = _make_streaming_router(
        side_effect=FallbackExhaustedError(
            message="All 3 attempts failed.",
            provider="openrouter",
            chain=["ATTEMPT_1:RateLimitError", "ATTEMPT_2:RateLimitError", "ATTEMPT_3:RateLimitError"],
        )
    )

    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    assert resp["content"] == ""
    assert result["errors"][0]["message"].startswith("fallback_exhausted")


@pytest.mark.asyncio
async def test_stage_1_generic_exception_does_not_hang(monkeypatch):
    """
    Bug 1 regression: before the fix, model.encrypted_key raised AttributeError
    which was caught by the generic except block.  The node must always return
    a result dict — never hang or re-raise — so the graph fan-out completes.
    """
    mock_router = _make_streaming_router(
        side_effect=AttributeError("'ProviderKeyModel' object has no attribute 'encrypted_key'")
    )

    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )

    config = _make_config(llm_router=mock_router)
    # Must not raise — must return an error MemberResponse
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result, "stage_1_node must always return a result dict"
    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    # The error message must not contain a raw stack trace (sanitized)
    assert "Traceback" not in (resp["error"] or "")


@pytest.mark.asyncio
async def test_stage_1_rate_limit_error_is_retried_by_router(monkeypatch):
    """
    RateLimitError from the adapter must be retried by LLMRouter (not by stage_1_node).
    After exhaustion it surfaces as FallbackExhaustedError → error MemberResponse.

    This test verifies stage_1_node handles FallbackExhaustedError correctly
    (the retry logic itself lives in LLMRouter, tested separately).
    """
    mock_router = _make_streaming_router(
        # Simulate LLMRouter having already retried and given up
        side_effect=FallbackExhaustedError(
            message="All 3 attempts failed with RateLimitError.",
            provider="openrouter",
            chain=["ATTEMPT_1:RateLimitError", "ATTEMPT_2:RateLimitError", "ATTEMPT_3:RateLimitError"],
        )
    )

    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    # Verify the node reported MODEL_REQUEST_FAILED (via errors list)
    assert len(result.get("errors", [])) == 1


@pytest.mark.asyncio
async def test_stage_1_key_fetch_failure_publishes_member_failed(monkeypatch):
    """
    If the key cannot be decrypted (missing key / vault error), a MemberFailed
    event must be published and an error MemberResponse returned — never a raise.
    """
    from app.core.exceptions import ProviderError

    # Key vault will fail to decrypt
    mock_vault = MagicMock()
    mock_vault.decrypt.side_effect = ProviderError(
        message="Vault unavailable", provider="openrouter"
    )

    mock_bus = AsyncMock()
    monkeypatch.setattr(
        "app.orchestration.nodes.stage_1.get_or_create_bus",
        AsyncMock(return_value=mock_bus),
    )

    config = _make_config(vault=mock_vault)
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result
    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    assert resp["content"] == ""

    published_types = [type(call.args[0]).__name__ for call in mock_bus.publish.call_args_list]
    assert "MemberFailed" in published_types
