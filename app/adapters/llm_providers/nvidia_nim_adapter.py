"""
adapters/llm_providers/nvidia_nim_adapter.py — NVIDIA NIM ProviderAdapter.

Wraps NVIDIA's NIM inference API behind the domain's ProviderAdapter interface.
NVIDIA NIM is OpenAI-compatible — same SDK, different base URL and auth header.

Endpoint: https://integrate.api.nvidia.com/v1
Auth:     Authorization: Bearer <user's nvapi-... key>

Design:
  - Identical structure to OpenRouterAdapter so the contract test suite can
    run the same tests against both (just swapping the adapter instance).
  - Respects NVIDIA's free-tier RPM ceiling via the circuit breaker / rate
    limiter in core/ — the adapter itself only handles per-call logic.

Pattern: Adapter (Hexagonal Architecture).
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

_BASE_URL = "https://integrate.api.nvidia.com/v1"
# NVIDIA exposes a models list endpoint under the same base URL
_MODELS_PATH = "/models"


class NvidiaNimAdapter(ProviderAdapter):
    """
    Adapter for the NVIDIA NIM hosted inference API.

    Auth: `nvapi-...` key passed as Bearer token.
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
                message="NVIDIA NIM authentication failed — check your nvapi key.",
                provider="nvidia_nim",
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message="NVIDIA NIM rate limit exceeded. The free tier has a modest RPM ceiling.",
                details={"provider": "nvidia_nim"},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"NVIDIA NIM call failed: {exc}",
                provider="nvidia_nim",
            ) from exc
        finally:
            await client.close()

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = response.usage

        return ChatResponse(
            content=response.choices[0].message.content or "",
            model_id=response.model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            cost_usd=0.0,   # NIM free tier has no direct cost reporting
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

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
                name=m.get("id", ""),   # NVIDIA doesn't expose display names in this endpoint
                provider="nvidia_nim",
                publisher="nvidia",
                is_free=False, # We don't have free info for NIM currently
                capabilities=["text"]
            )
            for m in data.get("data", [])
        ]

    async def validate_key(self, api_key: str) -> bool:
        """1-token probe to verify the nvapi key."""
        try:
            await self.chat(
                messages=[ChatMessage(role="user", content="ping")],
                model_id="meta/llama-3.3-70b-instruct",
                api_key=api_key,
                max_tokens=1,
            )
            return True
        except (ProviderError, RateLimitError):
            return False
