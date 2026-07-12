"""
adapters/research_providers/anakin_adapter.py — Anakin ResearchProviderAdapter.

Wraps the Anakin API (web search + scrape) behind the domain's
ResearchProviderAdapter interface.  Anakin's handler chain (fast HTTP →
browser → external API fallback) mirrors our own Chain of Responsibility
pattern in the failure-handling layer — a good conceptual fit.

Auth: X-Anakin-Api-Key header

Pattern: Adapter (Hexagonal Architecture).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.exceptions import ProviderError, RateLimitError
from app.domain.ports.research_adapter import (
    ResearchProviderAdapter,
    SearchResponse,
    SearchResult,
)

logger = logging.getLogger(__name__)

# Anakin API base URL — update if the provider publishes a versioned endpoint
_BASE_URL = "https://api.anakin.ai/v1"


class AnakinAdapter(ResearchProviderAdapter):
    """
    Adapter for the Anakin web-search / scraping API.

    The user supplies their own Anakin API key in Settings → Integrations.
    """

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "X-Anakin-Api-Key": api_key,
            "Content-Type": "application/json",
        }

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def search(
        self,
        query: str,
        api_key: str,
        *,
        max_results: int = 5,
        include_full_content: bool = False,
    ) -> SearchResponse:
        payload: dict = {
            "query": query,
            "limit": max_results,
            "scrape": include_full_content,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{_BASE_URL}/websearch",
                    json=payload,
                    headers=self._headers(api_key),
                )
                if resp.status_code == 429:
                    raise RateLimitError(
                        message="Anakin rate limit exceeded.",
                        details={"provider": "anakin"},
                    )
                if resp.status_code == 401:
                    raise ProviderError(
                        message="Anakin authentication failed — check your API key.",
                        provider="anakin",
                    )
                resp.raise_for_status()
                data = resp.json()
        except (RateLimitError, ProviderError):
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                message=f"Anakin search failed: HTTP {exc.response.status_code}",
                provider="anakin",
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"Anakin search failed: {exc}",
                provider="anakin",
            ) from exc

        retrieved_at = self._now_iso()
        results: list[SearchResult] = [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", r.get("description", "")),
                retrieved_at=retrieved_at,
                full_content=r.get("content") if include_full_content else None,
            )
            for r in data.get("results", data.get("data", []))
        ]

        return SearchResponse(
            query=query,
            results=results,
            ai_summary=data.get("summary"),
            provider="anakin",
        )

    async def extract(
        self,
        urls: list[str],
        api_key: str,
    ) -> list[SearchResult]:
        """Use Anakin's scrape endpoint to extract content from known URLs."""
        if not urls:
            return []

        results: list[SearchResult] = []
        retrieved_at = self._now_iso()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for url in urls:
                try:
                    resp = await client.post(
                        f"{_BASE_URL}/scrape",
                        json={"url": url},
                        headers=self._headers(api_key),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    results.append(
                        SearchResult(
                            url=url,
                            title=data.get("title", url),
                            snippet=data.get("content", "")[:500],
                            retrieved_at=retrieved_at,
                            full_content=data.get("content"),
                        )
                    )
                except Exception as exc:
                    logger.warning("Anakin scrape failed for %s: %s", url, exc)
                    # Partial failures are tolerated — skip the URL
                    continue

        return results

    async def validate_key(self, api_key: str) -> bool:
        """1-result probe to verify the Anakin API key."""
        try:
            await self.search("test", api_key, max_results=1)
            return True
        except (ProviderError, RateLimitError):
            return False
