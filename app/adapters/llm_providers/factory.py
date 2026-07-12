"""
adapters/llm_providers/factory.py — ProviderAdapterFactory.

Given a provider slug from the user's stored configuration, returns the correct
concrete ProviderAdapter instance.  Callers never import a concrete adapter
class directly — they always go through this factory.

Pattern: Factory (creational), Singleton (each adapter type is instantiated
         once and cached — adapters are stateless, so sharing is safe).
"""
from __future__ import annotations

from typing import Literal

from app.core.exceptions import DomainValidationError
from app.domain.ports.provider_adapter import ProviderAdapter

# Valid provider slugs — this is the UI allow-list the PRD mandates.
ProviderSlug = Literal["openrouter", "nvidia_nim", "github_models"]


class ProviderAdapterFactory:
    """
    Creates and caches ProviderAdapter instances by provider slug.

    Usage:
        adapter = ProviderAdapterFactory.create("openrouter")
        response = await adapter.chat(messages, model_id, api_key)
    """

    _cache: dict[str, ProviderAdapter] = {}

    @classmethod
    def create(cls, provider: str) -> ProviderAdapter:
        """
        Return the ProviderAdapter for `provider`.

        Args:
            provider: One of "openrouter", "nvidia_nim", "github_models".

        Returns:
            The cached adapter instance for the given provider.

        Raises:
            DomainValidationError: if the provider slug is not in the allow-list.
        """
        if provider in cls._cache:
            return cls._cache[provider]

        adapter = cls._build(provider)
        cls._cache[provider] = adapter
        return adapter

    @classmethod
    def _build(cls, provider: str) -> ProviderAdapter:
        # Imports are deferred to this private method so top-level imports
        # don't pull in all three SDK dependencies at startup.
        match provider:
            case "openrouter":
                from app.adapters.llm_providers.openrouter_adapter import OpenRouterAdapter
                return OpenRouterAdapter()

            case "nvidia_nim":
                from app.adapters.llm_providers.nvidia_nim_adapter import NvidiaNimAdapter
                return NvidiaNimAdapter()

            case "github_models":
                from app.adapters.llm_providers.github_models_adapter import GitHubModelsAdapter
                return GitHubModelsAdapter()

            case _:
                raise DomainValidationError(
                    message=f"Unknown LLM provider: '{provider}'. "
                            "Allowed values: openrouter, nvidia_nim, github_models.",
                    details={"provider": provider, "allowed": ["openrouter", "nvidia_nim", "github_models"]},
                )

    @classmethod
    def supported_providers(cls) -> list[str]:
        """Return the current allow-list of provider slugs."""
        return ["openrouter", "nvidia_nim", "github_models"]
