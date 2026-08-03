"""
adapters/llm_providers/nvidia_nim_adapter.py — NVIDIA NIM ProviderAdapter.

Wraps NVIDIA's NIM inference API behind the domain's ProviderAdapter interface.
NVIDIA NIM is OpenAI-compatible — same SDK, different base URL and auth header.

Endpoint: https://integrate.api.nvidia.com/v1
Auth:     Authorization: Bearer <user's nvapi-... key>

Connection reuse:
  A single httpx.AsyncClient (and the AsyncOpenAI wrapper around it) is created
  once in __init__ and reused for every call.  The ProviderAdapterFactory caches
  one adapter instance per provider slug, so this client is effectively a
  process-level singleton shared across all concurrent requests to NVIDIA NIM.
  The API key is NOT baked into the client — it is passed as an extra header on
  every call so multi-user keying works correctly.

Pattern: Adapter (Hexagonal Architecture), Singleton (client lifetime).
"""
from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, Optional
import asyncio

import httpx
import openai
from openai import AsyncOpenAI, APIError
from openai import AuthenticationError as OpenAIAuthError
from openai import RateLimitError as OpenAIRateLimitError

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)
from app.domain.ports.provider_adapter import (
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderAdapter,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MODELS_PATH = "/models"


class NvidiaNimAdapter(ProviderAdapter):
    """
    Adapter for the NVIDIA NIM hosted inference API.

    Auth: `nvapi-...` key passed as Bearer token via per-call extra_headers,
    matching the same pattern as OpenRouterAdapter so both adapters are
    interchangeable from the factory and router layers.
    """

    def __init__(self) -> None:
        # Create the shared HTTP client once.  Limits prevent connection storms;
        # keepalive connections avoid TLS renegotiation on every request.
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
        # AsyncOpenAI wraps the shared httpx client.  api_key is a required
        # constructor argument but is overridden per-call via extra_headers.
        self._client = AsyncOpenAI(
            base_url=_BASE_URL,
            api_key="placeholder-overridden-per-call",
            http_client=self._http_client,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client.  Call on adapter teardown."""
        await self._http_client.aclose()

    def _build_timeout(self, model_id: str, timeout_s: int) -> httpx.Timeout:
        """
        Free-tier models have long queue times before first token.
        Use a longer read timeout for them.
        """
        is_free = model_id.endswith(":free")
        read_timeout = 90.0 if is_free else float(timeout_s)
        return httpx.Timeout(
            connect=10.0,    # fail fast if endpoint unreachable
            read=read_timeout,
            write=10.0,
            pool=5.0,
        )

    # ── chat (non-streaming, full response) ──────────────────────────────

    async def chat(
        self,
        messages: list[ChatMessage],
        model_id: str,
        api_key: str,
        *,
        timeout_s: int = 60,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]

        start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=model_id,
                messages=oai_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._build_timeout(model_id, timeout_s),
                extra_headers={"Authorization": f"Bearer {api_key}"},
            )
        except OpenAIAuthError as exc:
            raise AuthenticationError(
                message="NVIDIA NIM authentication failed — check your nvapi key.",
                provider="nvidia_nim",
                details={"provider_message": exc.message},
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="NVIDIA NIM rate limit exceeded. The free tier has a modest RPM ceiling.",
                details={"provider": "nvidia_nim", "provider_message": exc.message},
            ) from exc
        except (httpx.TimeoutException, openai.APITimeoutError) as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "NVIDIA NIM call timed out after %dms (limit=%ds) model=%s",
                elapsed_ms,
                timeout_s,
                model_id,
            )
            raise ProviderTimeoutError(
                message=f"NVIDIA NIM call timed out after {elapsed_ms}ms (limit {timeout_s}s).",
                provider="nvidia_nim",
                details={"elapsed_ms": elapsed_ms, "timeout_s": timeout_s},
            ) from exc
        except APIError as exc:
            retryable = exc.status_code is not None and exc.status_code >= 500
            raise ProviderError(
                message=f"NVIDIA NIM API error ({exc.status_code}): {exc.message}",
                provider="nvidia_nim",
                retryable=retryable,
                details={"provider_message": exc.message, "status_code": exc.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"NVIDIA NIM call failed: {exc}",
                provider="nvidia_nim",
                details={"provider_message": str(exc)},
            ) from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = response.usage

        return ChatResponse(
            content=response.choices[0].message.content or "",
            model_id=response.model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            cost_usd=0.0,  # NIM free tier has no direct cost reporting
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    # ── stream_chat (token-level streaming) ───────────────────────────────

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model_id: str,
        api_key: str,
        *,
        timeout_s: int = 60,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Yield token delta strings as they arrive from the NVIDIA NIM stream.

        Uses the openai SDK's async streaming context manager (NVIDIA NIM is
        OpenAI-compatible).  Empty deltas are filtered — only non-empty content
        strings are yielded.
        """
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        stream_start = time.perf_counter()
        try:
            async with self._client.chat.completions.stream(
                model=model_id,
                messages=oai_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._build_timeout(model_id, timeout_s),
                extra_headers={"Authorization": f"Bearer {api_key}"},
            ) as stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        yield delta
        except OpenAIAuthError as exc:
            raise AuthenticationError(
                message="NVIDIA NIM authentication failed — check your nvapi key.",
                provider="nvidia_nim",
                details={"provider_message": exc.message},
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="NVIDIA NIM rate limit exceeded. The free tier has a modest RPM ceiling.",
                details={"provider": "nvidia_nim", "provider_message": exc.message},
            ) from exc
        except (httpx.TimeoutException, openai.APITimeoutError) as exc:
            elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
            logger.warning(
                "NVIDIA NIM stream timed out after %dms (limit=%ds) model=%s",
                elapsed_ms,
                timeout_s,
                model_id,
            )
            raise ProviderTimeoutError(
                message=f"NVIDIA NIM stream timed out after {elapsed_ms}ms (limit {timeout_s}s).",
                provider="nvidia_nim",
                details={"elapsed_ms": elapsed_ms, "timeout_s": timeout_s},
            ) from exc
        except APIError as exc:
            retryable = exc.status_code is not None and exc.status_code >= 500
            raise ProviderError(
                message=f"NVIDIA NIM API error ({exc.status_code}): {exc.message}",
                provider="nvidia_nim",
                retryable=retryable,
                details={"provider_message": exc.message, "status_code": exc.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"NVIDIA NIM stream failed: {exc}",
                provider="nvidia_nim",
                details={"provider_message": str(exc)},
            ) from exc

    # ── list_models ───────────────────────────────────────────────────────

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        """Fetch available NVIDIA NIM models."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(
                    f"{_BASE_URL}{_MODELS_PATH}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ProviderError(
                message=f"Failed to fetch NVIDIA NIM models: {exc}",
                provider="nvidia_nim",
            ) from exc

        return [
            ModelInfo(
                id=m.get("id", ""),
                name=m.get("id", ""),  # NVIDIA doesn't expose display names in this endpoint
                provider="nvidia_nim",
                publisher="nvidia",
                is_free=False,  # We don't have free info for NIM currently
                capabilities=["text"],
            )
            for m in data.get("data", [])
        ]

    # ── validate_key ──────────────────────────────────────────────────────

    async def validate_key(self, api_key: str) -> bool:
        """1-token probe to verify the nvapi key."""
        try:
            await asyncio.wait_for(
                self._do_validate(api_key),
                timeout=10.0   # 10 seconds maximum — fail fast
            )
            return True
        except asyncio.TimeoutError:
            raise ProviderTimeoutError(
                message="NVIDIA NIM did not respond within 10 seconds. The key may be valid but the service is slow. Try again or check NVIDIA's status page.",
                provider="nvidia_nim"
            )
        except AuthenticationError:
            raise   # re-raise — invalid key
        except Exception as exc:
            raise ProviderError(message=f"Validation failed: {type(exc).__name__}", provider="nvidia_nim") from exc

    async def _do_validate(self, api_key: str) -> None:
        await self.chat(
            messages=[ChatMessage(role="user", content="ping")],
            model_id=settings.NVIDIA_NIM_VALIDATION_MODEL,
            api_key=api_key,
            max_tokens=1,
            timeout_s=8,
        )
