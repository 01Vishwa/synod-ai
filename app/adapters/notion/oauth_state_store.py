"""
adapters/notion/oauth_state_store.py — PKCE OAuth State Store.

Stores short-lived OAuth state tokens server-side to prevent CSRF attacks
and enable PKCE verification at callback time.

Design:
  - In-memory with asyncio.Lock for thread-safe concurrent access.
  - TTL of 10 minutes — longer than any realistic OAuth round-trip.
  - State tokens are consumed on retrieval (delete-on-read) to prevent replay.
  - Lazy cleanup: expired entries are pruned on each write, keeping memory lean.

Security:
  - State tokens are opaque random strings (secrets.token_urlsafe).
  - code_verifier is never logged — it is a security-sensitive value.
  - Entries auto-expire; expired entries cannot be replayed.

Production note:
  - For multi-instance deployments, replace _store with a Redis-backed store.
  - The interface is the same — only this file changes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_TTL_SECONDS: int = 600     # 10 minutes


@dataclass
class OAuthState:
    """
    Ephemeral PKCE state for one OAuth authorization attempt.

    Attributes:
        state_token:    The opaque CSRF token sent to Notion as `state=`.
        code_verifier:  PKCE code_verifier (never logged, never sent to client).
        user_id:        Supabase user UUID who initiated the flow.
        parent_page_id: Optional Notion page ID user wants reports filed under.
        created_at:     Unix timestamp for TTL calculation.
    """
    state_token: str
    code_verifier: str
    user_id: str
    parent_page_id: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)


class OAuthStateStore:
    """
    Thread-safe, TTL-bound store for OAuth PKCE state tokens.

    Singleton — one instance per process, shared across coroutines.
    """

    _instance: OAuthStateStore | None = None

    def __init__(self) -> None:
        self._store: dict[str, OAuthState] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def instance(cls) -> "OAuthStateStore":
        """Return the process-level singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def save(
        self,
        *,
        state_token: str,
        code_verifier: str,
        user_id: str,
        parent_page_id: Optional[str] = None,
    ) -> None:
        """
        Persist a new OAuth state entry.

        Args:
            state_token:    The CSRF token sent to Notion.
            code_verifier:  PKCE verifier (kept server-side only).
            user_id:        The authenticated user who started this flow.
            parent_page_id: Optional Notion page to file reports under.
        """
        async with self._lock:
            self._purge_expired()
            self._store[state_token] = OAuthState(
                state_token=state_token,
                code_verifier=code_verifier,
                user_id=user_id,
                parent_page_id=parent_page_id,
            )
            logger.debug(
                "oauth_state_store: saved state token for user %s", user_id
            )

    async def retrieve_and_delete(self, state_token: str) -> Optional[OAuthState]:
        """
        Retrieve and atomically delete an OAuth state entry.

        Returns None if the token is unknown, expired, or already consumed.
        This enforces single-use semantics (prevents replay attacks).

        Args:
            state_token: The `state` parameter returned from Notion's callback.

        Returns:
            OAuthState if valid and not expired; None otherwise.
        """
        async with self._lock:
            entry = self._store.pop(state_token, None)

        if entry is None:
            logger.warning(
                "oauth_state_store: unknown or already-consumed state token"
            )
            return None

        age = time.monotonic() - entry.created_at
        if age > _TTL_SECONDS:
            logger.warning(
                "oauth_state_store: state token expired (age=%.1f s)", age
            )
            return None

        logger.debug(
            "oauth_state_store: retrieved state token for user %s", entry.user_id
        )
        return entry

    def _purge_expired(self) -> None:
        """Remove expired entries. Must be called while holding self._lock."""
        cutoff = time.monotonic() - _TTL_SECONDS
        expired = [k for k, v in self._store.items() if v.created_at < cutoff]
        for k in expired:
            del self._store[k]
        if expired:
            logger.debug(
                "oauth_state_store: purged %d expired entries", len(expired)
            )
