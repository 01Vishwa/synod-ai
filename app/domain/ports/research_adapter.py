"""
domain/ports/research_adapter.py — Port for research provider adapters.

Defines the interface every research provider adapter (Tavily, Anakin) must
satisfy. The domain layer never imports any search SDK.

Pattern: Adapter + Port.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SearchResult:
    """A single document returned from a search query."""
    url: str
    title: str
    snippet: str
    retrieved_at: str               # ISO-8601 UTC timestamp
    relevance_score: Optional[float] = None
    full_content: Optional[str] = None


@dataclass
class SearchResponse:
    """Aggregated result set from one search call."""
    query: str
    results: list[SearchResult] = field(default_factory=list)
    ai_summary: Optional[str] = None    # provider-generated summary (Tavily AI answer)
    provider: str = ""


class ResearchProviderAdapter(ABC):
    """
    Port interface for all web-research provider adapters.

    Concrete implementations live in adapters/research_providers/.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        api_key: str,
        *,
        max_results: int = 5,
        include_full_content: bool = False,
    ) -> SearchResponse:
        """
        Execute a web search for `query`.

        Args:
            query:               The search query string.
            api_key:             User-supplied decrypted API key.
            max_results:         Maximum number of results to return.
            include_full_content: If True, fetch and return raw page content.

        Returns:
            A SearchResponse with ranked results.
        """
        ...

    @abstractmethod
    async def extract(
        self,
        urls: list[str],
        api_key: str,
    ) -> list[SearchResult]:
        """
        Extract clean Markdown/text from a list of known URLs.

        Used when the Council has specific cited URLs that need full content.
        """
        ...

    @abstractmethod
    async def validate_key(self, api_key: str) -> bool:
        """Probe the provider to confirm the key is valid."""
        ...
