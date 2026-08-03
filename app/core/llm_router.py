"""
core/llm_router.py — LLM Router: the single gateway for all LLM provider calls.

Every LangGraph node that needs to call an LLM goes through this class, never
through the adapters directly.  It adds:

  1. Circuit-breaker gating    — short-circuits immediately if the provider
                                  is known-bad (OPEN state).
  2. Retry with back-off       — retries transient failures (timeouts, 429s,
                                  retryable 5xx) with exponential jitter.
  3. Failure recording         — on exhaustion, records the failure in the
                                  circuit breaker so the provider's state
                                  machine advances toward OPEN.
  4. Typed error propagation   — auth errors (401) are never retried and
                                  propagate immediately to the caller.

Design notes:
  - This is a thin orchestration layer; it does NOT own HTTP connections or
    crypto.  Those still live in the adapters and KeyVault respectively.
  - One LLMRouter instance is shared across the entire process (singleton,
    instantiated in main.py lifespan and injected via GraphDependencies).
  - The retry predicate (is_retryable_error) is a plain function so it can
    be imported and unit-tested in isolation.

Pattern: Decorator (retry wraps adapter call), Proxy (router is transparent
         to callers — returns ChatResponse unchanged), Singleton (one instance
         per process injected via DI).
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

import tenacity
from cachetools import TTLCache
from tenacity import (
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from app.adapters.llm_providers.factory import ProviderAdapterFactory
from app.core.circuit_breaker import get_breaker
from app.core.exceptions import (
    AuthenticationError,
    CircuitOpenError,
    FallbackExhaustedError,
    ProviderError,
    RateLimitError,
    UpstreamTimeoutError,
)
from app.domain.council_state import CouncilMemberConfig
from app.domain.ports.provider_adapter import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

_AUTH_FAILURE_CACHE_MAX = 1024
_AUTH_FAILURE_TTL_SECONDS = 600  # 10 minutes


# ── Retry predicate ────────────────────────────────────────────────────────────

def is_retryable_error(exc: BaseException) -> bool:
    """
    Return True for errors where an immediate retry *might* succeed.

    Non-retryable by design:
      - AuthenticationError  — the key is wrong; retrying won't fix it.
      - CircuitOpenError     — the breaker is open; retrying won't help.
      - ProviderError(retryable=False) — deterministic provider rejection
                                         (e.g. model not found, bad param).
    """
    if isinstance(exc, (UpstreamTimeoutError, RateLimitError)):
        return True
    if isinstance(exc, ProviderError):
        return getattr(exc, "retryable", False)
    return False


# ── Router ────────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Production gateway for all LLM inference calls in Synod.

    Usage (inside a LangGraph node):
        response = await deps.llm_router.chat(
            messages=messages,
            model_id=member["model_id"],
            provider=member["provider"],
            api_key=api_key,
            user_id=task["user_id"],
            temperature=0.7,
            max_tokens=2000,
        )

    Raises:
        AuthenticationError    — key rejected; never retried.
        FallbackExhaustedError — all retry attempts failed (wraps last error).
        CircuitOpenError       — provider circuit is OPEN; call not attempted.
    """

    def __init__(self, max_attempts: int = 3) -> None:
        """
        Args:
            max_attempts: Total attempts per call (1 attempt + N-1 retries).
                          Defaults to 3 (matches settings.COUNCIL_MEMBER_MAX_RETRIES + 1).
        """
        self._max_attempts = max_attempts
        self._auth_failures: TTLCache[tuple[str, str, str], AuthenticationError] = TTLCache(
            maxsize=_AUTH_FAILURE_CACHE_MAX,
            ttl=_AUTH_FAILURE_TTL_SECONDS,
        )
        logger.info("LLMRouter initialised (max_attempts=%d).", max_attempts)

    async def chat(
        self,
        messages: list[ChatMessage],
        model_id: str,
        provider: str,
        api_key: str,
        user_id: str,
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_s: int = 60,
        session_id: str = "",
    ) -> ChatResponse:
        """
        Execute a single chat-completion call with retry + circuit-breaker.

        The circuit-breaker key is (user_id, provider) so one user's bad key
        never affects another user's healthy bucket (per PRD Section 5.3).

        Args:
            messages:    Conversation messages.
            model_id:    Provider-specific model identifier.
            provider:    Provider slug (\"openrouter\", \"nvidia_nim\", …).
            api_key:     Decrypted API key — never stored by the router.
            user_id:     Stable user identifier (used for breaker bucketing).
            temperature: Sampling temperature.
            max_tokens:  Optional hard ceiling on response tokens.
            timeout_s:   Per-call HTTP timeout in seconds.
            session_id:  Stable session identifier for run-scoped auth fast-fail.

        Returns:
            ChatResponse from the adapter.

        Raises:
            AuthenticationError    — 401 from provider; propagates immediately.
            CircuitOpenError       — breaker is OPEN; call not attempted.
            FallbackExhaustedError — all retry attempts exhausted.
        """
        # Run-scoped auth fail-fast
        if session_id and (session_id, provider, model_id) in self._auth_failures:
            logger.warning(
                "LLMRouter: Fast-failing request for provider '%s' model '%s' (session '%s') due to previous auth failure.",
                provider,
                model_id,
                session_id,
            )
            raise self._auth_failures[(session_id, provider, model_id)]

        breaker = await get_breaker(user_id=user_id, provider=provider)
        adapter = ProviderAdapterFactory.create(provider)

        attempt_log: list[str] = []

        # Build the tenacity retry decorator dynamically so max_attempts is
        # instance-configurable rather than module-level fixed.
        retry_decorator = tenacity.retry(
            reraise=False,  # we catch tenacity.RetryError ourselves below
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(initial=1, max=10),
            retry=retry_if_exception(is_retryable_error),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )

        @retry_decorator
        async def _attempt() -> ChatResponse:
            return await adapter.chat(
                messages=messages,
                model_id=model_id,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
            )

        try:
            # Gate: raise CircuitOpenError immediately if OPEN
            result: ChatResponse = await breaker.call(_attempt)
        except AuthenticationError as exc:
            # Auth errors are not retried and do NOT trip the circuit breaker
            # (a bad key is a user config issue, not a provider outage).
            logger.error(
                "LLMRouter: AuthenticationError for provider '%s' user '%s'. "
                "Not retrying — key must be updated in Settings.",
                provider,
                user_id,
            )
            if session_id:
                self._auth_failures[(session_id, provider, model_id)] = exc

            await self._mark_user_provider_credential_invalid(user_id, provider, str(exc))
            raise
        except CircuitOpenError:
            logger.warning(
                "LLMRouter: circuit OPEN for provider '%s' (user '%s'). Skipping call.",
                provider,
                user_id,
            )
            raise
        except tenacity.RetryError as retry_exc:
            # All retry attempts exhausted — record failure in breaker and re-raise
            # as our domain exception with the attempt audit trail.
            last: BaseException = retry_exc.last_attempt.exception()  # type: ignore[union-attr]
            attempt_log = [
                f"ATTEMPT_{i + 1}:{type(a.exception()).__name__}"
                for i, a in enumerate(retry_exc.last_attempt.retry_state.retry_object.statistics.get("attempt_number", []))  # type: ignore[attr-defined]
            ] if hasattr(retry_exc.last_attempt, "retry_state") else []

            logger.error(
                "LLMRouter: all %d attempts exhausted for provider '%s' model '%s'. "
                "Last error: %s",
                self._max_attempts,
                provider,
                model_id,
                last,
            )
            raise FallbackExhaustedError(
                message=(
                    f"All {self._max_attempts} attempt(s) failed for "
                    f"{provider}/{model_id}. Last error: {last}"
                ),
                provider=provider,
                chain=attempt_log or [f"EXHAUSTED:{type(last).__name__}"],
            ) from last
        except Exception:
            # Any non-retryable exception (ProviderError(retryable=False),
            # ModelNotFoundError, etc.) propagates directly.
            raise
        else:
            logger.debug(
                "LLMRouter: success — provider '%s' model '%s' latency=%dms",
                provider,
                model_id,
                result.latency_ms,
            )
            return result

    async def stream_chat(
        self,
        member_config: CouncilMemberConfig,
        messages: list[ChatMessage],
        user_id: str,
        api_key: str,
        *,
        timeout_s: int = 60,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        session_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Stream token deltas from the provider, applying the same circuit-breaker
        and auth-failure gating as chat().

        Key differences from chat():
          - No tenacity retry: streaming is inherently single-attempt.  A partial
            stream cannot be rewound and replayed from the beginning, so retrying
            would deliver duplicate or truncated content to the caller.
          - Circuit breaker failures are recorded explicitly via
            _record_stream_failure() rather than via breaker.call(), because the
            asyncio.Lock inside CircuitBreaker cannot be held across yield points.

        Args:
            member_config: Council member configuration dict (provider, model_id, etc.).
            messages:      Conversation messages to send.
            user_id:       Stable user identifier for circuit-breaker bucketing.
            api_key:       Decrypted API key — never stored by the router.
            timeout_s:     Per-call HTTP timeout in seconds.
            temperature:   Sampling temperature.
            max_tokens:    Optional hard token ceiling.
            session_id:    Run-scoped session identifier for auth fast-fail.

        Yields:
            str — each non-empty token delta from the provider, in order.

        Raises:
            AuthenticationError — key rejected; never retried; cached for session.
            CircuitOpenError    — breaker is OPEN; stream not attempted.
            ProviderError       — non-retryable provider failure mid-stream.
            UpstreamTimeoutError — stream timed out.
        """
        provider: str = member_config["provider"]
        model_id: str = member_config["model_id"]

        # ── 1. Run-scoped auth fail-fast ────────────────────────────────
        if session_id and (session_id, provider, model_id) in self._auth_failures:
            logger.warning(
                "LLMRouter.stream_chat: fast-failing provider '%s' model '%s' (session '%s') "
                "due to previous auth failure.",
                provider,
                model_id,
                session_id,
            )
            raise self._auth_failures[(session_id, provider, model_id)]

        # ── 2. Circuit-breaker gate (read-only check — no lock held across yields) ─
        breaker = await get_breaker(user_id=user_id, provider=provider)
        # Manually inspect state rather than calling breaker.call() so we never
        # hold the breaker's asyncio.Lock across a yield point.
        async with breaker._lock:
            await breaker._maybe_recover()
            from app.core.circuit_breaker import CircuitState
            if breaker.state == CircuitState.OPEN:
                raise CircuitOpenError(provider=provider)

        # ── 3. Resolve adapter ──────────────────────────────────────────
        adapter = ProviderAdapterFactory.create(provider)

        # ── 4. Stream, recording failures to the breaker on error ───────
        try:
            async for delta in adapter.stream_chat(
                messages=messages,
                model_id=model_id,
                api_key=api_key,
                timeout_s=timeout_s,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield delta
        except AuthenticationError as exc:
            # Auth errors are not retried and do NOT trip the circuit breaker.
            logger.error(
                "LLMRouter.stream_chat: AuthenticationError for provider '%s' "
                "user '%s'. Not retrying.",
                provider,
                user_id,
            )
            if session_id:
                self._auth_failures[(session_id, provider, model_id)] = exc
            # Fire-and-forget DB mark (non-blocking — we must not await inside
            # the except block of an async generator because the generator frame
            # stays alive until GC.  Schedule as a task instead).
            import asyncio
            asyncio.create_task(
                self._mark_user_provider_credential_invalid(user_id, provider, str(exc))
            )
            raise
        except CircuitOpenError:
            logger.warning(
                "LLMRouter.stream_chat: circuit OPEN for provider '%s' (user '%s').",
                provider,
                user_id,
            )
            raise
        except Exception as exc:
            # Record failure in the circuit breaker so repeated stream failures
            # can trip it toward OPEN, matching chat() behaviour.
            await self._record_stream_failure(breaker, provider, model_id, exc)
            raise
        else:
            # Successful stream completion — record success to reset failure count.
            async with breaker._lock:
                breaker._record_success()
            logger.debug(
                "LLMRouter.stream_chat: completed — provider '%s' model '%s'.",
                provider,
                model_id,
            )

    async def _record_stream_failure(
        self,
        breaker,  # CircuitBreaker — avoid import cycle in type hint
        provider: str,
        model_id: str,
        exc: BaseException,
    ) -> None:
        """Record a stream error in the circuit breaker (mirrors chat() failure path)."""
        async with breaker._lock:
            breaker._record_failure()
        logger.error(
            "LLMRouter.stream_chat: stream error for provider '%s' model '%s': %s",
            provider,
            model_id,
            exc,
        )

    async def _mark_user_provider_credential_invalid(
        self,
        user_id: str,
        provider: str,
        error_msg: str,
    ) -> None:
        """Mark provider credential invalid in the database when it fails at runtime."""
        from app.adapters.persistence.database import async_session_factory
        from app.adapters.persistence.models import ProviderKeyModel
        from sqlalchemy import select
        import datetime

        try:
            async with async_session_factory() as session:
                stmt = select(ProviderKeyModel).where(
                    ProviderKeyModel.user_id == user_id,
                    ProviderKeyModel.provider == provider,
                )
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                if model:
                    model.last_test_ok = False
                    model.last_tested_at = datetime.datetime.now(datetime.timezone.utc)
                    model.last_test_error = error_msg[:200]
                    await session.commit()
                    logger.info("Marked DB key invalid for provider '%s' (user '%s').", provider, user_id)
        except Exception as e:
            logger.warning("Failed to mark provider key invalid in DB: %s", e)
