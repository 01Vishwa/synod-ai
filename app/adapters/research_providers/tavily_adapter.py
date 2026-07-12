"""
adapters/research_providers/tavily_adapter.py — Tavily ResearchProviderAdapter.

Wraps the Tavily API behind the domain's ResearchProviderAdapter interface.
Tavily is purpose-built for AI agents: it returns ranked, LLM-ready results
with optional full content extraction.

Endpoints used:
  POST /search  — web search with optional AI summary
  POST /extract — extract clean Markdown from known URLs

Auth: Authorization: Bearer tvly-...

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

_BASE_URL = "https://api.tavily.com"


class TavilyAdapter(ResearchProviderAdapter):
    """
    Adapter for the Tavily web-research API.

    The user supplies their own `tvly-...` API key, entered in
    Settings → Integrations.  Synod never stores or charges for Tavily calls.
    """

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
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
            "max_results": max_results,
            "include_raw_content": include_full_content,
            "include_answer": True,         # Tavily AI-generated answer
            "search_depth": "advanced",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{_BASE_URL}/search",
                    json=payload,
                    headers=self._headers(api_key),
                )
                if resp.status_code == 429:
                    raise RateLimitError(
                        message="Tavily rate limit exceeded.",
                        details={"provider": "tavily"},
                    )
                resp.raise_for_status()
                data = resp.json()
        except (RateLimitError, ProviderError):
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                message=f"Tavily search failed: HTTP {exc.response.status_code}",
                provider="tavily",
            ) from exc
        except Exception as exc:
            raise ProviderError(
                message=f"Tavily search failed: {exc}",
                provider="tavily",
            ) from exc

        results: list[SearchResult] = []
        retrieved_at = self._now_iso()
        for r in data.get("results", []):
            results.append(
                SearchResult(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),
                    retrieved_at=retrieved_at,
                    relevance_score=r.get("score"),
                    full_content=r.get("raw_content") if include_full_content else None,
                )
            )

        return SearchResponse(
            query=query,
            results=results,
            ai_summary=data.get("answer"),
            provider="tavily",
        )

    async def extract(
        self,
        urls: list[str],
        api_key: str,
    ) -> list[SearchResult]:
        """Use Tavily's /extract endpoint to pull clean content from known URLs."""
        if not urls:
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{_BASE_URL}/extract",
                    json={"urls": urls},
                    headers=self._headers(api_key),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ProviderError(
                message=f"Tavily extract failed: {exc}",
                provider="tavily",
            ) from exc

        retrieved_at = self._now_iso()
        return [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("url", ""),   # Extract doesn't return titles
                snippet=r.get("raw_content", "")[:500],
                retrieved_at=retrieved_at,
                full_content=r.get("raw_content"),
            )
            for r in data.get("results", [])
        ]

    async def validate_key(self, api_key: str) -> bool:
        """1-result probe search to verify the Tavily key."""
        try:
            await self.search("test", api_key, max_results=1)
            return True
        except (ProviderError, RateLimitError):
            return False
