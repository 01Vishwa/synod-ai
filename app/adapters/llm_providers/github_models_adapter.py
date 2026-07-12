"""
adapters/llm_providers/github_models_adapter.py — GitHub Models stub adapter.

⚠️  DEPRECATION NOTICE (PRD Section 10.3):
GitHub confirmed on July 1, 2026 that GitHub Models will be fully retired
on July 30, 2026.  This adapter is kept in the codebase to satisfy the
Adapter + Factory pattern (so the provider slot exists and the contract test
suite can verify its interface) but it:
  1. Raises a deprecation warning on every call.
  2. Will be swapped for a replacement adapter (e.g. Azure AI Foundry) before
     or at launch by updating only this file and factory.py.

The architecture guarantee: swapping it requires ZERO changes to orchestration/,
api/, or domain/ — only this file and one line in factory.py.

Pattern: Adapter (placeholder), Chain of Responsibility (the UI banner is the
         first handler; this adapter is the last-resort fallback with a warning).
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

from app.core.exceptions import ProviderError
from app.domain.ports.provider_adapter import (
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderAdapter,
)

logger = logging.getLogger(__name__)

_RETIREMENT_NOTICE = (
    "GitHub Models has been retired as of July 30, 2026. "
    "This provider is no longer functional. Please configure OpenRouter "
    "or NVIDIA NIM in Settings → Providers. "
    "See: https://github.com/orgs/github-community/discussions/1"
)


class GitHubModelsAdapter(ProviderAdapter):
    """
    Stub adapter for GitHub Models (retired July 30, 2026).

    All methods raise ProviderError immediately with a clear migration message.
    The adapter class is preserved so:
      - The Factory pattern compiles without changes.
      - The contract test suite can document the expected error behaviour.
      - A replacement adapter (Azure AI Foundry) can be slotted in by inheriting
        or replacing this class while keeping the same interface.
    """

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
        warnings.warn(_RETIREMENT_NOTICE, DeprecationWarning, stacklevel=2)
        logger.error("Call attempted to retired GitHub Models provider.")
        raise ProviderError(
            message=_RETIREMENT_NOTICE,
            provider="github_models",
        )

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        raise ProviderError(
            message=_RETIREMENT_NOTICE,
            provider="github_models",
        )

    async def validate_key(self, api_key: str) -> bool:
        raise ProviderError(
            message=_RETIREMENT_NOTICE,
            provider="github_models",
        )
