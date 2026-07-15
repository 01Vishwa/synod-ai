"""
orchestration/utils.py — Helper utilities for LangGraph nodes.
"""
from __future__ import annotations

from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.core.exceptions import ProviderError
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

    if model.last_test_ok:
        logger.info("API_KEY_RUNTIME_VALIDATION_SKIPPED_VALID_RECENT_TEST", extra=extra)

    return decrypted
