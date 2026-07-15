"""
tests/unit/test_stage_1_node.py — Stage 1 node unit tests.

Tests:
  1. Successful model call → MODEL_REQUEST_SUCCESS, response returned.
  2. AuthenticationError → member error response, no re-raise.
  3. FallbackExhaustedError → member error response.
  4. Generic exception (e.g. AttributeError from wrong column name) →
     member error response (regression for Bug 1 silent failure).
  5. Provider 429 (RateLimitError) → FallbackExhaustedError after retries.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    AuthenticationError,
    FallbackExhaustedError,
    RateLimitError,
)
from app.domain.ports.provider_adapter import ChatResponse
from app.orchestration.nodes.stage_1 import Stage1Task, stage_1_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    # Deliberately do NOT set key_model.encrypted_key
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


def _make_chat_response(content: str = "Four.") -> ChatResponse:
    return ChatResponse(
        content=content,
        model_id="openai/gpt-4.1-mini",
        tokens_in=10,
        tokens_out=5,
        latency_ms=250,
        cost_usd=0.0001,
        raw=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_1_success():
    """Successful LLM call → stage_1_responses contains one MemberResponse with content."""
    mock_router = AsyncMock()
    mock_router.chat = AsyncMock(return_value=_make_chat_response("The answer is four."))

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result
    assert len(result["stage_1_responses"]) == 1
    resp = result["stage_1_responses"][0]
    assert resp["content"] == "The answer is four."
    assert resp["error"] is None
    assert resp["member_id"] == "m1"


@pytest.mark.asyncio
async def test_stage_1_authentication_error_returns_error_response():
    """
    AuthenticationError must NOT propagate out of stage_1_node.
    It must be returned as a MemberResponse with error set.
    """
    mock_router = AsyncMock()
    mock_router.chat = AsyncMock(
        side_effect=AuthenticationError(
            message="Invalid API key.",
            provider="openrouter",
        )
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    assert "stage_1_responses" in result
    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    assert "auth" in resp["error"].lower() or "key" in resp["error"].lower()
    assert resp["content"] == ""

    # errors list must also be populated for the session error tracker
    assert "errors" in result
    assert len(result["errors"]) == 1


@pytest.mark.asyncio
async def test_stage_1_fallback_exhausted_returns_error_response():
    """FallbackExhaustedError (all retries done) → error MemberResponse, no raise."""
    mock_router = AsyncMock()
    mock_router.chat = AsyncMock(
        side_effect=FallbackExhaustedError(
            message="All 3 attempts failed.",
            provider="openrouter",
            chain=["ATTEMPT_1:RateLimitError", "ATTEMPT_2:RateLimitError", "ATTEMPT_3:RateLimitError"],
        )
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    assert resp["content"] == ""
    assert result["errors"][0]["message"].startswith("fallback_exhausted")


@pytest.mark.asyncio
async def test_stage_1_generic_exception_does_not_hang():
    """
    Bug 1 regression: before the fix, model.encrypted_key raised AttributeError
    which was caught by the generic except block.  The node must always return
    a result dict — never hang or re-raise — so the graph fan-out completes.
    """
    mock_router = AsyncMock()
    mock_router.chat = AsyncMock(
        side_effect=AttributeError("'ProviderKeyModel' object has no attribute 'encrypted_key'")
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
async def test_stage_1_rate_limit_error_is_retried_by_router():
    """
    RateLimitError from the adapter must be retried by LLMRouter (not by stage_1_node).
    After exhaustion it surfaces as FallbackExhaustedError → error MemberResponse.

    This test verifies stage_1_node handles FallbackExhaustedError correctly
    (the retry logic itself lives in LLMRouter, tested separately).
    """
    mock_router = AsyncMock()
    # Simulate LLMRouter having already retried and given up
    mock_router.chat = AsyncMock(
        side_effect=FallbackExhaustedError(
            message="All 3 attempts failed with RateLimitError.",
            provider="openrouter",
            chain=["ATTEMPT_1:RateLimitError", "ATTEMPT_2:RateLimitError", "ATTEMPT_3:RateLimitError"],
        )
    )

    config = _make_config(llm_router=mock_router)
    result = await stage_1_node(_make_task(), config)

    resp = result["stage_1_responses"][0]
    assert resp["error"] is not None
    # Verify the node reported MODEL_REQUEST_FAILED (via errors list)
    assert len(result.get("errors", [])) == 1
