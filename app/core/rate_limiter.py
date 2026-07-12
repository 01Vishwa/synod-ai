"""
core/rate_limiter.py — In-process token-bucket rate limiter.

Provides per-(user_id, provider) backpressure before a provider's own
rate limit (e.g. NVIDIA NIM free-tier RPM ceiling) returns a 429.

Design:
  - Token-Bucket algorithm: refills tokens at a constant rate; bursts up to
    `capacity` are absorbed; excess requests raise RateLimitError immediately.
  - Thread-safe via asyncio.Lock (FastAPI runs in an async event loop).
  - Singleton registry keyed by (user_id, provider) so each pair gets its own
    independent bucket — no cross-user interference.
  - The registry itself is a module-level dict — one per process, consistent
    with FastAPI's single-process dev/staging model.  For multi-process
    deployments, swap the dict for a Redis-backed sliding window.

Pattern: Strategy (RateLimiter is an injectable strategy), Singleton (registry).
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.core.exceptions import RateLimitError


# ── Token Bucket ──────────────────────────────────────────────────────────

@dataclass
class _TokenBucket:
    """
    A single token bucket for one (user_id, provider) pair.

    Args:
        rate:     Tokens added per second (requests/min ÷ 60).
        capacity: Maximum number of tokens (burst limit = per-minute ceiling).
    """
    rate: float                          # tokens per second
    capacity: float                      # max burst
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: float = 1.0) -> None:
        """
        Attempt to consume `tokens` from the bucket.

        Raises:
            RateLimitError: if the bucket is exhausted.
        """
        async with self._lock:
            self._refill()
            if self._tokens < tokens:
                raise RateLimitError(
                    message="Rate limit exceeded. Please slow down your requests.",
                    details={"available_tokens": round(self._tokens, 2)},
                )
            self._tokens -= tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now


# ── Registry (Singleton per process) ─────────────────────────────────────

_buckets: dict[tuple[str, str], _TokenBucket] = {}
_registry_lock = asyncio.Lock()


async def _get_or_create_bucket(
    user_id: str,
    provider: str,
    rpm: int,
) -> _TokenBucket:
    key = (user_id, provider)
    if key not in _buckets:
        async with _registry_lock:
            if key not in _buckets:          # double-checked locking
                _buckets[key] = _TokenBucket(
                    rate=rpm / 60.0,
                    capacity=float(rpm),
                )
    return _buckets[key]


# ── Public API ────────────────────────────────────────────────────────────

async def check_rate_limit(
    user_id: str,
    provider: str,
    rpm: Optional[int] = None,
) -> None:
    """
    Enforce rate limit for (user_id, provider).

    Args:
        user_id:  Stable identifier for the authenticated user.
        provider: Provider slug (e.g. "openrouter", "nvidia_nim", "tavily").
        rpm:      Requests-per-minute ceiling. Defaults to the global setting.

    Raises:
        RateLimitError: if the per-(user, provider) bucket is exhausted.
    """
    effective_rpm = rpm or settings.RATE_LIMIT_PER_MINUTE
    bucket = await _get_or_create_bucket(user_id, provider, effective_rpm)
    await bucket.consume()


def reset_bucket(user_id: str, provider: str) -> None:
    """Remove a bucket from the registry (used in tests to reset state)."""
    _buckets.pop((user_id, provider), None)
