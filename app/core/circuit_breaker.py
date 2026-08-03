"""
core/circuit_breaker.py — Per-(user, provider) Circuit Breaker.

Prevents cascading failures when a provider is in a known-bad state by
short-circuiting further calls instead of queuing retries into an outage.

State machine:
    CLOSED → normal operation; failures increment counter.
    OPEN   → all calls immediately raise CircuitOpenError; a recovery timer
             resets to HALF_OPEN after `recovery_timeout_s`.
    HALF_OPEN → one probe call is allowed; success → CLOSED, failure → OPEN.

Design:
  - Each (user_id, provider) pair gets an independent breaker instance so one
    user's bad key doesn't affect another user's healthy bucket.
  - Thread-safe via asyncio.Lock.
  - Directly mitigates the GitHub Models retirement brownout windows described
    in PRD Section 10.3.

Pattern: Circuit Breaker (Nygard), Singleton (registry per process).
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

from cachetools import TTLCache

from app.core.exceptions import CircuitOpenError, AuthenticationError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_BREAKER_CACHE_MAX = 2048
_BREAKER_TTL_SECONDS = 600  # 10 minutes


# ── State enum ────────────────────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


# ── Breaker ───────────────────────────────────────────────────────────────

@dataclass
class CircuitBreaker:
    """
    Circuit breaker for a single (user_id, provider) pair.

    Args:
        provider:           Provider slug used in error messages.
        failure_threshold:  Consecutive failures before tripping OPEN.
        recovery_timeout_s: Seconds before an OPEN circuit becomes HALF_OPEN.
    """
    provider: str
    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute `fn` through the circuit breaker.

        Raises:
            CircuitOpenError: if the circuit is OPEN.
            Exception: any exception raised by `fn` (recorded as a failure).
        """
        async with self._lock:
            await self._maybe_recover()

            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(provider=self.provider)

            if self._state == CircuitState.HALF_OPEN:
                # Transition to probe mode — only one call gets through
                pass

        try:
            result: T = await fn(*args, **kwargs)
        except AuthenticationError:
            raise
        except Exception as exc:
            async with self._lock:
                self._record_failure()
            logger.warning(
                "Circuit breaker recorded failure for provider '%s' (%d/%d): %s",
                self.provider,
                self._failure_count,
                self.failure_threshold,
                exc,
            )
            raise
        else:
            async with self._lock:
                self._record_success()
            return result

    async def _maybe_recover(self) -> None:
        """Transition OPEN → HALF_OPEN when the recovery timeout has elapsed."""
        if (
            self._state == CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout_s
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("Circuit for '%s' entering HALF_OPEN state.", self.provider)

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._failure_count = 0
            logger.warning("Circuit OPENED for provider '%s'.", self.provider)

    def _record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info("Circuit CLOSED for provider '%s'.", self.provider)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def reset(self) -> None:
        """Force-reset to CLOSED (used in tests and manual recovery flows)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0


# ── Registry (Singleton per process) ─────────────────────────────────────

_breakers: TTLCache[tuple[str, str], CircuitBreaker] = TTLCache(
    maxsize=_BREAKER_CACHE_MAX,
    ttl=_BREAKER_TTL_SECONDS,
)
_registry_lock = asyncio.Lock()


async def get_breaker(
    user_id: str,
    provider: str,
    failure_threshold: int = 3,
    recovery_timeout_s: float = 30.0,
) -> CircuitBreaker:
    """
    Retrieve (or create) the CircuitBreaker for (user_id, provider).

    Args:
        user_id:             Stable authenticated user identifier.
        provider:            Provider slug (e.g. "openrouter", "nvidia_nim").
        failure_threshold:   Consecutive failures before opening.
        recovery_timeout_s:  Seconds before recovery probe.
    """
    key = (user_id, provider)
    if key not in _breakers:
        async with _registry_lock:
            if key not in _breakers:
                _breakers[key] = CircuitBreaker(
                    provider=provider,
                    failure_threshold=failure_threshold,
                    recovery_timeout_s=recovery_timeout_s,
                )
    return _breakers[key]
