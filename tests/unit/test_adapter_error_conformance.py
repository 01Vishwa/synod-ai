"""
tests/unit/test_adapter_error_conformance.py — Adapter conformance test suite.

Regression guard that runs against EVERY registered provider adapter.
For each adapter it verifies:

  1. A 401 (OpenAI AuthenticationError) → domain AuthenticationError
       with a non-empty provider_message in details.
  2. A 429 (OpenAI RateLimitError) → domain RateLimitError
       with a non-empty provider_message in details.
  3. A 500 (OpenAI APIError) → domain ProviderError
       with retryable=True and a non-empty provider_message in details.
  4. A 422 non-retryable (OpenAI APIError) → domain ProviderError
       with retryable=False and a non-empty provider_message in details.
  5. A timeout (httpx.TimeoutException) → domain ProviderTimeoutError (alias
       of UpstreamTimeoutError) with elapsed_ms in details.
  6. An UpstreamTimeoutError MemberResponse.error message says
       "did not respond" or "timed out" — NOT "credential rejected."

This file prevents the exact class of bug where an error-detail fix is applied
to one adapter but silently missing from the next one added.

To add a new adapter: add it to ALL_ADAPTERS below and run this test.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from app.adapters.llm_providers.factory import ProviderAdapterFactory
from app.adapters.llm_providers.nvidia_nim_adapter import NvidiaNimAdapter
from app.adapters.llm_providers.openrouter_adapter import OpenRouterAdapter
from app.core.exceptions import (
    AuthenticationError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    UpstreamTimeoutError,
)
from app.domain.ports.provider_adapter import ChatMessage, ProviderAdapter
from app.orchestration.utils import _sanitize_error


# ---------------------------------------------------------------------------
# Registry — add every new adapter here
# ---------------------------------------------------------------------------

ALL_ADAPTERS: list[tuple[str, ProviderAdapter]] = [
    ("openrouter", OpenRouterAdapter()),
    ("nvidia_nim", NvidiaNimAdapter()),
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Hello")]


def _fake_openai_auth_error(message: str = "Invalid API key") -> openai.AuthenticationError:
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 401
    fake_response.headers = httpx.Headers({})
    fake_response.request = MagicMock(spec=httpx.Request)
    return openai.AuthenticationError(
        message=message,
        response=fake_response,
        body={"error": {"message": message}},
    )


def _fake_openai_rate_limit_error(message: str = "Rate limit exceeded") -> openai.RateLimitError:
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 429
    fake_response.headers = httpx.Headers({})
    fake_response.request = MagicMock(spec=httpx.Request)
    return openai.RateLimitError(
        message=message,
        response=fake_response,
        body={"error": {"message": message}},
    )


def _fake_openai_api_error(status_code: int, message: str) -> openai.APIStatusError:
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = status_code
    fake_response.headers = httpx.Headers({})
    fake_response.request = MagicMock(spec=httpx.Request)
    # APIStatusError is the concrete base for 4xx/5xx errors in the openai SDK
    return openai.APIStatusError(
        message=message,
        response=fake_response,
        body={"error": {"message": message}},
    )


def _make_raising_chat_ctx(adapter: ProviderAdapter, exc: Exception):
    """Patch adapter._client.chat.completions.create to raise exc."""
    async def _raise(*args, **kwargs):
        raise exc
    return patch.object(adapter._client.chat.completions, "create", new=_raise)


@asynccontextmanager
async def _make_raising_stream_ctx(exc: Exception) -> AsyncIterator[MagicMock]:
    """Async context manager that raises exc on iteration."""
    async def _aiter_raising():
        raise exc
        yield  # make it a generator

    stream_obj = MagicMock()
    stream_obj.__aiter__ = lambda self: _aiter_raising()
    yield stream_obj


def _make_raising_stream_patch(adapter: ProviderAdapter, exc: Exception):
    """Patch adapter._client.chat.completions.stream to raise exc on enter."""
    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        raise exc
        yield  # type: ignore[misc]

    return patch.object(adapter._client.chat.completions, "stream", new=_ctx)


def _has_non_empty_provider_message(exc: Exception) -> bool:
    """
    Return True if the exception has a non-empty provider_message in details.
    Accepts the detail on .details dict (AppException subclasses) or
    directly on the exception.
    """
    details = getattr(exc, "details", {}) or {}
    msg = details.get("provider_message", "")
    return bool(msg and str(msg).strip())


# ---------------------------------------------------------------------------
# Parametrised conformance tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_chat_401_raises_authentication_error_with_provider_message(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    A 401 from the provider SDK must map to AuthenticationError and carry a
    non-empty provider_message in details so the UI can display the real cause.
    """
    raw_exc = _fake_openai_auth_error(f"{provider_name}: Invalid API key — bad credentials")

    with _make_raising_chat_ctx(adapter, raw_exc):
        with pytest.raises(AuthenticationError) as exc_info:
            await adapter.chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="bad-key",
            )

    raised = exc_info.value
    assert isinstance(raised, AuthenticationError), (
        f"[{provider_name}] Expected AuthenticationError, got {type(raised).__name__}"
    )
    assert _has_non_empty_provider_message(raised), (
        f"[{provider_name}] AuthenticationError must carry non-empty provider_message "
        f"in details. Got details={raised.details!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_chat_429_raises_rate_limit_error_with_provider_message(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    A 429 from the provider SDK must map to RateLimitError and carry a
    non-empty provider_message in details.
    """
    raw_exc = _fake_openai_rate_limit_error(f"{provider_name}: You have exceeded your rate limit.")

    with _make_raising_chat_ctx(adapter, raw_exc):
        with pytest.raises(RateLimitError) as exc_info:
            await adapter.chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="sk-test",
            )

    raised = exc_info.value
    assert isinstance(raised, RateLimitError), (
        f"[{provider_name}] Expected RateLimitError, got {type(raised).__name__}"
    )
    assert _has_non_empty_provider_message(raised), (
        f"[{provider_name}] RateLimitError must carry non-empty provider_message "
        f"in details. Got details={raised.details!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_chat_500_raises_retryable_provider_error_with_provider_message(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    A 5xx API error must map to ProviderError(retryable=True) with a
    non-empty provider_message in details.
    """
    raw_exc = _fake_openai_api_error(500, f"{provider_name}: Internal server error")

    with _make_raising_chat_ctx(adapter, raw_exc):
        with pytest.raises(ProviderError) as exc_info:
            await adapter.chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="sk-test",
            )

    raised = exc_info.value
    assert isinstance(raised, ProviderError), (
        f"[{provider_name}] Expected ProviderError, got {type(raised).__name__}"
    )
    assert getattr(raised, "retryable", False) is True, (
        f"[{provider_name}] 5xx ProviderError must be retryable=True"
    )
    assert _has_non_empty_provider_message(raised), (
        f"[{provider_name}] 5xx ProviderError must carry non-empty provider_message "
        f"in details. Got details={raised.details!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_chat_422_raises_non_retryable_provider_error_with_provider_message(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    A 4xx (non-401/429) API error must map to ProviderError(retryable=False) with
    a non-empty provider_message in details.
    """
    raw_exc = _fake_openai_api_error(422, f"{provider_name}: Unprocessable entity — bad model param")

    with _make_raising_chat_ctx(adapter, raw_exc):
        with pytest.raises(ProviderError) as exc_info:
            await adapter.chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="sk-test",
            )

    raised = exc_info.value
    assert isinstance(raised, ProviderError), (
        f"[{provider_name}] Expected ProviderError, got {type(raised).__name__}"
    )
    assert getattr(raised, "retryable", True) is False, (
        f"[{provider_name}] 4xx ProviderError must be retryable=False"
    )
    assert _has_non_empty_provider_message(raised), (
        f"[{provider_name}] 4xx ProviderError must carry non-empty provider_message "
        f"in details. Got details={raised.details!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_chat_timeout_raises_provider_timeout_error_with_elapsed_ms(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    An httpx timeout must map to ProviderTimeoutError (= UpstreamTimeoutError) and
    must carry elapsed_ms in details so logs show actual wait time.
    """
    raw_exc = httpx.TimeoutException("read timeout")

    with _make_raising_chat_ctx(adapter, raw_exc):
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await adapter.chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="sk-test",
                timeout_s=30,
            )

    raised = exc_info.value
    assert isinstance(raised, (ProviderTimeoutError, UpstreamTimeoutError)), (
        f"[{provider_name}] Expected ProviderTimeoutError, got {type(raised).__name__}"
    )
    details = getattr(raised, "details", {}) or {}
    assert "elapsed_ms" in details, (
        f"[{provider_name}] ProviderTimeoutError must carry elapsed_ms in details. "
        f"Got details={details!r}"
    )
    assert isinstance(details["elapsed_ms"], int), (
        f"[{provider_name}] elapsed_ms must be an int, got {type(details['elapsed_ms'])}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_stream_chat_401_raises_authentication_error_with_provider_message(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    stream_chat: a 401 must map to AuthenticationError with provider_message.
    """
    raw_exc = _fake_openai_auth_error(f"{provider_name}: bad key in stream")

    with _make_raising_stream_patch(adapter, raw_exc):
        with pytest.raises(AuthenticationError) as exc_info:
            async for _ in adapter.stream_chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="bad-key",
            ):
                pass

    raised = exc_info.value
    assert isinstance(raised, AuthenticationError), (
        f"[{provider_name}] stream_chat 401 must raise AuthenticationError"
    )
    assert _has_non_empty_provider_message(raised), (
        f"[{provider_name}] stream_chat AuthenticationError must carry provider_message. "
        f"Got details={raised.details!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
async def test_stream_chat_timeout_raises_provider_timeout_error_with_elapsed_ms(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    stream_chat: a timeout must map to ProviderTimeoutError with elapsed_ms in details.
    """
    raw_exc = httpx.TimeoutException("read timeout mid-stream")

    with _make_raising_stream_patch(adapter, raw_exc):
        with pytest.raises(ProviderTimeoutError) as exc_info:
            async for _ in adapter.stream_chat(
                messages=_make_messages(),
                model_id="any/model",
                api_key="sk-test",
                timeout_s=45,
            ):
                pass

    raised = exc_info.value
    assert isinstance(raised, (ProviderTimeoutError, UpstreamTimeoutError)), (
        f"[{provider_name}] stream_chat timeout must raise ProviderTimeoutError"
    )
    details = getattr(raised, "details", {}) or {}
    assert "elapsed_ms" in details, (
        f"[{provider_name}] stream_chat ProviderTimeoutError must carry elapsed_ms. "
        f"Got details={details!r}"
    )


# ---------------------------------------------------------------------------
# Conformance: sanitize_error for UpstreamTimeoutError is not "credential rejected"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider_name,adapter", ALL_ADAPTERS, ids=[a[0] for a in ALL_ADAPTERS])
def test_sanitized_timeout_message_is_not_credential_rejected(
    provider_name: str, adapter: ProviderAdapter
) -> None:
    """
    _sanitize_error must produce a message that says "timeout" or "did not respond"
    for UpstreamTimeoutError — never "credential rejected."

    This guards against future mis-categorisation in _sanitize_error().
    """
    exc = UpstreamTimeoutError(
        message=f"{provider_name} timed out",
        provider=provider_name,
        details={"elapsed_ms": 61000, "timeout_s": 60},
    )
    msg = _sanitize_error(exc, provider_name)

    assert "credential" not in msg.lower() or "rejected" not in msg.lower(), (
        f"[{provider_name}] UpstreamTimeoutError must NOT produce a 'credential rejected' "
        f"message. Got: {msg!r}"
    )
    assert "timeout" in msg.lower() or "respond" in msg.lower(), (
        f"[{provider_name}] UpstreamTimeoutError message should mention timeout or "
        f"respond. Got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Registry completeness check
# ---------------------------------------------------------------------------

def test_all_registered_adapters_are_in_conformance_suite() -> None:
    """
    The ALL_ADAPTERS list must contain every provider returned by
    ProviderAdapterFactory.supported_providers().  If a new provider is
    added to the factory but not to ALL_ADAPTERS, this test will fail and
    the developer must add conformance coverage.
    """
    supported = set(ProviderAdapterFactory.supported_providers())
    tested = {name for name, _ in ALL_ADAPTERS}
    missing = supported - tested
    assert not missing, (
        f"The following providers are registered in the factory but NOT covered "
        f"by the adapter conformance test suite: {missing!r}. "
        f"Add them to ALL_ADAPTERS in test_adapter_error_conformance.py."
    )
