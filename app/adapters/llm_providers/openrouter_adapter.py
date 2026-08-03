"""
adapters/llm_providers/openrouter_adapter.py — OpenRouter ProviderAdapter.

Wraps OpenRouter's OpenAI-compatible chat completions API behind the domain's
ProviderAdapter interface.  Only this file imports the openai SDK (pointed at
OpenRouter's base URL) — the orchestration layer never touches it.

Endpoint: https://openrouter.ai/api/v1
Auth:     Authorization: Bearer <user's OPENROUTER_API_KEY>

Connection reuse:
  A single httpx.AsyncClient (and the AsyncOpenAI wrapper around it) is created
  once in __init__ and reused for every call.  The ProviderAdapterFactory caches
  one adapter instance per provider slug, so this client is effectively a
  process-level singleton shared across all concurrent requests to OpenRouter.
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

_BASE_URL = "https://openrouter.ai/api/v1"
_MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterAdapter(ProviderAdapter):
    """
    Adapter for the OpenRouter inference API.

    OpenRouter is OpenAI-compatible; we use the official openai SDK pointed at
    their base URL.  Auth is via a per-call Bearer token in an extra header so
    that the shared client instance works correctly for all users.
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
        # constructor argument but OpenRouter overrides it per-call via the
        # extra Authorization header below, so we use a placeholder here.
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
                message="OpenRouter authentication failed — check your API key.",
                provider="openrouter",
                details={"provider_message": exc.message},
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="OpenRouter rate limit exceeded.",
                details={"provider": "openrouter", "provider_message": exc.message},
            ) from exc
        except (httpx.TimeoutException, openai.APITimeoutError) as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "OpenRouter call timed out after %dms (limit=%ds) model=%s",
                elapsed_ms,
                timeout_s,
                model_id,
            )
            raise ProviderTimeoutError(
                message=f"OpenRouter call timed out after {elapsed_ms}ms (limit {timeout_s}s).",
                provider="openrouter",
                details={"elapsed_ms": elapsed_ms, "timeout_s": timeout_s},
            ) from exc
        except APIError as exc:
            retryable = exc.status_code is not None and exc.status_code >= 500
            raise ProviderError(
                message=f"OpenRouter API error ({exc.status_code}): {exc.message}",
                provider="openrouter",
                retryable=retryable,
                details={"provider_message": exc.message, "status_code": exc.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"OpenRouter call failed: {exc}",
                provider="openrouter",
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
            cost_usd=0.0,
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
        Yield token delta strings as they arrive from the OpenRouter stream.

        Uses the openai SDK's async streaming context manager.  Empty deltas
        (e.g. role-only chunks at stream start) are filtered out — only
        non-empty content strings are yielded.
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
                message="OpenRouter authentication failed — check your API key.",
                provider="openrouter",
                details={"provider_message": exc.message},
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="OpenRouter rate limit exceeded.",
                details={"provider": "openrouter", "provider_message": exc.message},
            ) from exc
        except (httpx.TimeoutException, openai.APITimeoutError) as exc:
            elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
            logger.warning(
                "OpenRouter stream timed out after %dms (limit=%ds) model=%s",
                elapsed_ms,
                timeout_s,
                model_id,
            )
            raise ProviderTimeoutError(
                message=f"OpenRouter stream timed out after {elapsed_ms}ms (limit {timeout_s}s).",
                provider="openrouter",
                details={"elapsed_ms": elapsed_ms, "timeout_s": timeout_s},
            ) from exc
        except APIError as exc:
            retryable = exc.status_code is not None and exc.status_code >= 500
            raise ProviderError(
                message=f"OpenRouter API error ({exc.status_code}): {exc.message}",
                provider="openrouter",
                retryable=retryable,
                details={"provider_message": exc.message, "status_code": exc.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"OpenRouter stream failed: {exc}",
                provider="openrouter",
                details={"provider_message": str(exc)},
            ) from exc

    # ── list_models ───────────────────────────────────────────────────────

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        """Fetch the live OpenRouter model catalogue."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(
                    _MODELS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                message=f"Failed to fetch OpenRouter models: {exc.response.status_code}",
                provider="openrouter",
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"Failed to fetch OpenRouter models: {exc}",
                provider="openrouter",
            ) from exc

        models: list[ModelInfo] = []
        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            prompt_cost = _to_float(pricing.get("prompt"))
            completion_cost = _to_float(pricing.get("completion"))

            is_free = False
            if prompt_cost == 0.0 and completion_cost == 0.0:
                is_free = True
            elif "free" in m.get("id", "").lower():
                is_free = True

            model_id = m.get("id", "")
            publisher = model_id.split("/")[0] if "/" in model_id else "openrouter"

            models.append(
                ModelInfo(
                    id=model_id,
                    name=m.get("name", model_id),
                    provider="openrouter",
                    publisher=publisher,
                    is_free=is_free,
                    capabilities=["text"],
                )
            )
        return models

    # ── validate_key ──────────────────────────────────────────────────────

    async def validate_key(self, api_key: str) -> bool:
        """1-token dry-run to verify the key is valid."""
        try:
            await asyncio.wait_for(
                self._do_validate(api_key),
                timeout=10.0
            )
            return True
        except asyncio.TimeoutError:
            raise ProviderTimeoutError(
                message="OpenRouter did not respond within 10 seconds. The key may be valid but the service is slow. Try again or check OpenRouter's status page.",
                provider="openrouter"
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderError(message=f"Validation failed: {type(exc).__name__}", provider="openrouter") from exc

    async def _do_validate(self, api_key: str) -> None:
        await self.chat(
            messages=[ChatMessage(role="user", content="ping")],
            model_id=settings.OPENROUTER_VALIDATION_MODEL,
            api_key=api_key,
            max_tokens=1,
            timeout_s=8,
        )


def _to_float(v: object) -> Optional[float]:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
