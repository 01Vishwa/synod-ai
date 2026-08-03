"""
tests/unit/test_streaming_adapters.py — Unit tests for stream_chat() in both
OpenRouter and NVIDIA NIM adapters.

All network I/O is mocked — no real API calls are made.  Each test patches
the underlying openai SDK stream context manager or error constructor to verify
that the adapter:
  1. Yields only non-empty delta strings.
  2. Correctly maps openai exceptions to domain exceptions.
  3. Never leaks raw SDK types through the adapter boundary.

Test matrix:
  test_openrouter_stream_chat_yields_deltas
  test_openrouter_stream_chat_auth_error_raises_authentication_error
  test_openrouter_stream_chat_timeout_raises_provider_timeout_error
  test_nvidia_stream_chat_yields_deltas
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

from app.adapters.llm_providers.nvidia_nim_adapter import NvidiaNimAdapter
from app.adapters.llm_providers.openrouter_adapter import OpenRouterAdapter
from app.core.exceptions import (
    AuthenticationError,
    ProviderTimeoutError,
)
from app.domain.ports.provider_adapter import ChatMessage


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Hello")]


def _make_chunk(content: str) -> MagicMock:
    """
    Build a minimal mock that looks like an openai streaming chunk.

    chunk.choices[0].delta.content = content
    """
    delta = MagicMock()
    delta.content = content
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _make_empty_chunk() -> MagicMock:
    """A chunk with no choices (e.g. role-only initial chunk) — must be skipped."""
    chunk = MagicMock()
    chunk.choices = []
    return chunk


def _make_stream_ctx(chunks: list[MagicMock]):
    """
    Build an async context manager that yields `chunks` when iterated.

    This mocks the pattern:
        async with client.chat.completions.stream(...) as stream:
            async for chunk in stream:
                ...
    """
    async def _aiter():
        for c in chunks:
            yield c

    stream_obj = MagicMock()
    stream_obj.__aiter__ = lambda self: _aiter()

    @asynccontextmanager
    async def _ctx(*args, **kwargs) -> AsyncIterator[MagicMock]:
        yield stream_obj

    return _ctx


def _make_raising_stream_ctx(exc: Exception):
    """
    Build an async context manager whose `__aiter__` raises `exc` on the
    first iteration — simulating a mid-stream error from the openai SDK.
    """
    async def _aiter_raising():
        raise exc
        yield  # make it an async generator

    stream_obj = MagicMock()
    stream_obj.__aiter__ = lambda self: _aiter_raising()

    @asynccontextmanager
    async def _ctx(*args, **kwargs) -> AsyncIterator[MagicMock]:
        yield stream_obj

    return _ctx


def _make_raising_ctx_on_enter(exc: Exception):
    """
    Build an async context manager that raises `exc` on __aenter__ —
    simulating an error before the stream starts (e.g. auth failure).
    """
    @asynccontextmanager
    async def _ctx(*args, **kwargs) -> AsyncIterator[MagicMock]:
        raise exc
        yield  # type: ignore[misc]

    return _ctx


# ── OpenRouter tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openrouter_stream_chat_yields_deltas() -> None:
    """
    stream_chat yields exactly the non-empty delta strings from the provider
    stream, in order, with no filtering or modification of content.
    """
    chunks = [
        _make_empty_chunk(),          # role-only chunk — must be skipped
        _make_chunk("Hello"),
        _make_chunk(" world"),
        _make_chunk("!"),
    ]
    ctx = _make_stream_ctx(chunks)

    adapter = OpenRouterAdapter()
    with patch.object(adapter._client.chat.completions, "stream", new=ctx):
        collected = []
        async for delta in adapter.stream_chat(
            messages=_make_messages(),
            model_id="openai/gpt-4o-mini",
            api_key="sk-test",
        ):
            collected.append(delta)

    assert collected == ["Hello", " world", "!"], (
        f"Expected ['Hello', ' world', '!'], got {collected}"
    )


@pytest.mark.asyncio
async def test_openrouter_stream_chat_auth_error_raises_authentication_error() -> None:
    """
    An openai.AuthenticationError from the provider stream is translated to
    the domain's AuthenticationError — the raw SDK exception never escapes.

    openai.AuthenticationError requires (message, response, body) in the
    current SDK.  We build a minimal real instance using a mocked httpx.Response
    so we can actually raise it inside the context manager.
    """
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 401
    fake_response.headers = httpx.Headers({})
    fake_response.request = MagicMock(spec=httpx.Request)
    raw_exc = openai.AuthenticationError(
        message="Invalid API key",
        response=fake_response,
        body={"error": {"message": "Invalid API key"}},
    )
    ctx = _make_raising_ctx_on_enter(raw_exc)

    adapter = OpenRouterAdapter()
    with patch.object(adapter._client.chat.completions, "stream", new=ctx):
        with pytest.raises(AuthenticationError):
            async for _ in adapter.stream_chat(
                messages=_make_messages(),
                model_id="openai/gpt-4o-mini",
                api_key="bad-key",
            ):
                pass



@pytest.mark.asyncio
async def test_openrouter_stream_chat_timeout_raises_provider_timeout_error() -> None:
    """
    An httpx.TimeoutException mid-stream is translated to ProviderTimeoutError
    (which is an alias of UpstreamTimeoutError).
    """
    ctx = _make_raising_stream_ctx(httpx.TimeoutException("read timeout"))

    adapter = OpenRouterAdapter()
    with patch.object(adapter._client.chat.completions, "stream", new=ctx):
        with pytest.raises(ProviderTimeoutError):
            async for _ in adapter.stream_chat(
                messages=_make_messages(),
                model_id="openai/gpt-4o-mini",
                api_key="sk-test",
            ):
                pass


# ── NVIDIA NIM tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nvidia_stream_chat_yields_deltas() -> None:
    """
    NvidiaNimAdapter.stream_chat yields exactly the non-empty delta strings from
    the provider stream, in order — identical contract to OpenRouter.
    """
    chunks = [
        _make_chunk("Hello"),
        _make_empty_chunk(),          # must be skipped
        _make_chunk(" from"),
        _make_chunk(" NVIDIA"),
    ]
    ctx = _make_stream_ctx(chunks)

    adapter = NvidiaNimAdapter()
    with patch.object(adapter._client.chat.completions, "stream", new=ctx):
        collected = []
        async for delta in adapter.stream_chat(
            messages=_make_messages(),
            model_id="meta/llama-3.3-70b-instruct",
            api_key="nvapi-test",
        ):
            collected.append(delta)

    assert collected == ["Hello", " from", " NVIDIA"], (
        f"Expected ['Hello', ' from', ' NVIDIA'], got {collected}"
    )
