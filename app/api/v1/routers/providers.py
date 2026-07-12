"""
api/v1/routers/providers.py — LLM Provider Key Management.

Endpoints for adding, retrieving, and testing LLM provider API keys.
Keys are encrypted at rest via KeyVault and never returned in plaintext.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.adapters.llm_providers.factory import ProviderAdapterFactory
from app.adapters.persistence.models import ProviderKeyModel
from app.api.v1.deps import CurrentUserId, DbSession, Vault
from app.api.v1.schemas.providers import (
    ModelCatalogResponse,
    ProviderKeyCreateRequest,
    ProviderKeyResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.core.exceptions import ProviderError

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post("", response_model=ProviderKeyResponse, status_code=status.HTTP_201_CREATED)
async def upsert_provider_key(
    req: ProviderKeyCreateRequest,
    user_id: CurrentUserId,
    db: DbSession,
    vault: Vault,
) -> Any:
    """Store or update an encrypted LLM provider API key."""
    # Ensure provider is in our LLM allow-list
    if req.provider not in ProviderAdapterFactory.supported_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported LLM provider: {req.provider}",
        )

    encrypted = vault.encrypt(req.api_key)

    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == req.provider,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_key = encrypted
        if req.label:
            existing.label = req.label
        existing.is_verified = False  # requires re-verification
        model = existing
    else:
        model = ProviderKeyModel(
            user_id=user_id,
            provider=req.provider,
            encrypted_key=encrypted,
            label=req.label,
        )
        db.add(model)

    await db.flush()
    return model


@router.get("", response_model=list[ProviderKeyResponse])
async def list_provider_keys(
    user_id: CurrentUserId,
    db: DbSession,
) -> Any:
    """List all configured LLM keys for the current user (plaintext omitted)."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider.in_(ProviderAdapterFactory.supported_providers()),
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_key(
    provider: str,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """Remove a configured LLM provider key."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == provider,
    )
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Key not found")
        
    await db.delete(model)
    await db.flush()


@router.post("/{provider}/test", response_model=TestConnectionResponse)
async def test_connection(
    provider: str,
    req: TestConnectionRequest,
) -> Any:
    """Test a raw API key against a provider's inference endpoint (1-token ping)."""
    try:
        adapter = ProviderAdapterFactory.create(provider)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start = time.perf_counter()
    success = await adapter.validate_key(req.api_key)
    latency = int((time.perf_counter() - start) * 1000)

    if success:
        return TestConnectionResponse(
            provider=provider,
            success=True,
            message="Connection successful.",
            latency_ms=latency,
        )
    return TestConnectionResponse(
        provider=provider,
        success=False,
        message="Connection failed. Please check your API key.",
    )


@router.get("/{provider}/models", response_model=ModelCatalogResponse)
async def get_models(
    provider: str,
    user_id: CurrentUserId,
    db: DbSession,
    vault: Vault,
) -> Any:
    """Fetch the live catalogue of available models from the provider."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == provider,
    )
    result = await db.execute(stmt)
    key_model = result.scalar_one_or_none()

    if not key_model:
        raise HTTPException(
            status_code=404,
            detail=f"No API key configured for '{provider}'. Please add one first.",
        )

    try:
        api_key = vault.decrypt(key_model.encrypted_key)
        adapter = ProviderAdapterFactory.create(provider)
        models = await adapter.list_models(api_key)
        
        # Mark key as verified if we successfully listed models
        if not key_model.is_verified:
            key_model.is_verified = True
            await db.flush()
            
        return ModelCatalogResponse.from_model_infos(provider, models)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc.message)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to fetch model catalog.") from exc
