"""
orchestration/utils.py — Helper utilities for LangGraph nodes.

Includes:
  - fetch_decrypted_key: resolve & decrypt provider API keys from the DB.
  - _sanitize_error:     map provider exceptions to user-friendly messages;
                         reused by stage_1, stage_2, and stage_3 nodes.
"""
from __future__ import annotations

from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.core.exceptions import AuthenticationError, ProviderError
from app.orchestration.context import GraphDependencies


import logging

logger = logging.getLogger(__name__)

async def fetch_decrypted_key(
    deps: GraphDependencies,
    user_id: str,
    provider: str,
    session_id: str = "",
    member_id: str = "",
) -> str:
    """
    Fetch and decrypt the API key for `provider` owned by `user_id`.
    Raises ProviderError if the key is missing.
    """
    extra = {
        "provider": provider,
        "user_id": user_id,
        "session_id": session_id,
        "member_id": member_id,
        "key_fingerprint": "",
    }
    logger.info("API_KEY_LOOKUP_STARTED", extra=extra)

    async with deps.db_session_factory() as session:
        stmt = select(ProviderKeyModel).where(
            ProviderKeyModel.user_id == user_id,
            ProviderKeyModel.provider == provider,
        )
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()

    if not model:
        logger.warning("API_KEY_LOOKUP_FAILED", extra=extra)
        raise ProviderError(
            message=f"Missing API key for {provider}. Please configure it in Settings.",
            provider=provider,
        )

    extra["key_fingerprint"] = model.key_fingerprint
    logger.info("API_KEY_LOOKUP_SUCCESS", extra=extra)

    try:
        decrypted = deps.vault.decrypt(model.ciphertext_b64)
        logger.info("API_KEY_DECRYPT_SUCCESS", extra=extra)
    except Exception as exc:
        logger.error("API_KEY_DECRYPT_FAILED", extra=extra)
        raise ProviderError(
            message=f"Failed to decrypt API key for {provider}.",
            provider=provider,
        ) from exc

    if not decrypted or len(decrypted) < 8:
        raise AuthenticationError(
            message=f"Stored {provider} key is missing or corrupt. "
            "Please re-enter your key in Settings → Providers & API Keys.",
            provider=provider
        )

    if model.last_test_ok:
        logger.info("API_KEY_RUNTIME_VALIDATION_SKIPPED_VALID_RECENT_TEST", extra=extra)

    return decrypted


def _sanitize_error(exc: Exception, provider: str) -> str:
    """
    Convert a provider exception into a user-facing, non-technical message.

    All messages omit raw tracebacks and Python internals so they are safe
    to return in the MemberResponse.error field and surface in the UI.

    Used by stage_1_node, stage_2_node, and stage_3_node.
    """
    from app.core.exceptions import (
        AuthenticationError,
        RateLimitError,
        ProviderTimeoutError,
        ProviderError,
    )

    if isinstance(exc, AuthenticationError):
        return (
            f"API credentials for {provider} were rejected. "
            "Please update your key in Settings \u2192 Providers & API Keys."
        )
    if isinstance(exc, RateLimitError):
        return (
            f"{provider} rate limit exceeded. "
            "This member has been excluded from ranking."
        )
    if isinstance(exc, ProviderTimeoutError):
        return (
            f"{provider} did not respond within the timeout window. "
            "This member has been excluded from ranking."
        )
    if isinstance(exc, ProviderError):
        return (
            f"A provider error occurred with {provider}. "
            "This member has been excluded from ranking."
        )
    return (
        "An unexpected error occurred communicating with this provider. "
        "This member has been excluded from ranking."
    )
