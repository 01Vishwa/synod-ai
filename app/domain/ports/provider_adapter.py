"""
domain/ports/provider_adapter.py — Port for LLM provider adapters.

Defines the interface (ABC) that every LLM provider adapter must satisfy.
The domain layer depends ONLY on this interface; it never imports OpenAI,
httpx, or any provider SDK.

Pattern: Adapter + Port (Hexagonal Architecture driving port).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChatMessage:
    """Immutable message record used across provider calls."""
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatResponse:
    """Normalised response from any LLM provider."""
    content: str
    model_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    raw: Optional[dict] = None              # provider-specific payload for debugging


@dataclass(frozen=True)
class ModelInfo:
    """Catalogue entry returned by list_models()."""
    id: str
    name: str
    provider: str
    publisher: str
    is_free: bool
    capabilities: list[str]


class ProviderAdapter(ABC):
    """
    Port interface for all LLM provider adapters.

    Concrete implementations live in adapters/llm_providers/.
    The domain / orchestration layer only ever holds a reference to this ABC.
    """

    @abstractmethod
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
        """
        Send a chat-completion request to the provider.

        Args:
            messages:    Ordered list of conversation messages.
            model_id:    Provider-specific model identifier string.
            api_key:     User-supplied decrypted API key — never persisted here.
            timeout_s:   Per-call timeout in seconds.
            temperature: Sampling temperature.
            max_tokens:  Optional hard token ceiling for the response.

        Returns:
            A normalised ChatResponse.

        Raises:
            ProviderError: on any provider-side failure.
        """
        ...

    @abstractmethod
    async def list_models(self, api_key: str) -> list[ModelInfo]:
        """
        Return the live model catalogue for this provider.

        Used to populate the frontend model picker without hardcoding IDs.
        """
        ...

    @abstractmethod
    async def validate_key(self, api_key: str) -> bool:
        """
        Perform a minimal probe call to verify the key is valid.

        Returns True on success; raises ProviderError on failure.
        """
        ...
