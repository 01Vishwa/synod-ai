"""
adapters/research_providers/factory.py — ResearchProviderAdapterFactory.

Mirror of the LLM provider factory — same pattern applied to research providers.
The Research Sub-Agent node only ever calls this factory; it never imports a
concrete adapter class.

Pattern: Factory, Singleton (cached instances).
"""
from __future__ import annotations

from app.core.exceptions import DomainValidationError
from app.domain.ports.research_adapter import ResearchProviderAdapter


class ResearchProviderAdapterFactory:
    """
    Creates and caches ResearchProviderAdapter instances by provider slug.

    Usage:
        adapter = ResearchProviderAdapterFactory.create("tavily")
        results = await adapter.search(query, api_key)
    """

    _cache: dict[str, ResearchProviderAdapter] = {}

    @classmethod
    def create(cls, provider: str) -> ResearchProviderAdapter:
        """
        Return the ResearchProviderAdapter for `provider`.

        Args:
            provider: One of "tavily", "anakin".

        Raises:
            DomainValidationError: for unknown slugs.
        """
        if provider in cls._cache:
            return cls._cache[provider]

        adapter = cls._build(provider)
        cls._cache[provider] = adapter
        return adapter

    @classmethod
    def _build(cls, provider: str) -> ResearchProviderAdapter:
        match provider:
            case "tavily":
                from app.adapters.research_providers.tavily_adapter import TavilyAdapter
                return TavilyAdapter()

            case "anakin":
                from app.adapters.research_providers.anakin_adapter import AnakinAdapter
                return AnakinAdapter()

            case _:
                raise DomainValidationError(
                    message=f"Unknown research provider: '{provider}'. Allowed: tavily, anakin.",
                    details={"provider": provider, "allowed": ["tavily", "anakin"]},
                )

    @classmethod
    def supported_providers(cls) -> list[str]:
        return ["tavily", "anakin"]
