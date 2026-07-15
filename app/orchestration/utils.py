"""
orchestration/utils.py — Helper utilities for LangGraph nodes.
"""
from __future__ import annotations

from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.core.exceptions import ProviderError
from app.orchestration.context import GraphDependencies


async def fetch_decrypted_key(
    deps: GraphDependencies,
    user_id: str,
    provider: str,
) -> str:
    """
    Fetch and decrypt the API key for `provider` owned by `user_id`.
    Raises ProviderError if the key is missing.
    """
    async with deps.db_session_factory() as session:
        stmt = select(ProviderKeyModel).where(
            ProviderKeyModel.user_id == user_id,
            ProviderKeyModel.provider == provider,
        )
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()

    if not model:
        raise ProviderError(
            message=f"Missing API key for {provider}. Please configure it in Settings.",
            provider=provider,
        )

    return deps.vault.decrypt(model.ciphertext_b64)
