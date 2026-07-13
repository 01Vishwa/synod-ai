"""
adapters/llm_providers/openrouter_adapter.py — OpenRouter ProviderAdapter.

Wraps OpenRouter's OpenAI-compatible chat completions API behind the domain's
ProviderAdapter interface.  Only this file imports the openai SDK (pointed at
OpenRouter's base URL) — the orchestration layer never touches it.

Endpoint: https://openrouter.ai/api/v1
Auth:     Authorization: Bearer <user's OPENROUTER_API_KEY>

Pattern: Adapter (Hexagonal Architecture), Decorator (circuit breaker wraps
         the underlying call via the core module).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from openai import AsyncOpenAI, APIError, AuthenticationError, RateLimitError as OpenAIRateLimitError

from app.core.exceptions import ProviderError, RateLimitError
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
    their base URL.  Auth is via a Bearer token in the Authorization header.
    """

    def _client(self, api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=_BASE_URL,
            api_key=api_key,
            http_client=httpx.AsyncClient(timeout=120.0),
        )

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
        client = self._client(api_key)
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]

        start = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=oai_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_s,
            )
        except AuthenticationError as exc:
            raise ProviderError(
                message="OpenRouter authentication failed — check your API key.",
                provider="openrouter",
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="OpenRouter rate limit exceeded.",
                details={"provider": "openrouter"},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"OpenRouter call failed: {exc}",
                provider="openrouter",
            ) from exc
        finally:
            await client.close()

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = response.usage

        # OpenRouter may include cost in the response headers / usage object
        cost_usd = 0.0
        if hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
            pass  # cost calculation is provider-specific; left for v2 billing module

        return ChatResponse(
            content=response.choices[0].message.content or "",
            model_id=response.model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

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
            
            # Identify if it's free
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
                    capabilities=["text"]
                )
            )
        return models

    async def validate_key(self, api_key: str) -> bool:
        """1-token dry-run to verify the key is valid."""
        try:
            await self.chat(
                messages=[ChatMessage(role="user", content="ping")],
                model_id="openai/gpt-4.1-mini",
                api_key=api_key,
                max_tokens=1,
            )
            return True
        except (ProviderError, RateLimitError):
            return False


def _to_float(v: object) -> Optional[float]:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
