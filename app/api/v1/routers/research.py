"""
api/v1/routers/research.py — Research Provider Key Management.

Endpoints for managing Tavily and Anakin API keys.
Separated from the LLM providers router to keep the UI configuration distinct
(Settings -> Integrations vs Settings -> Providers).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.adapters.research_providers.factory import ResearchProviderAdapterFactory
from app.api.v1.deps import CurrentUserId, DbSession, Vault
from app.api.v1.schemas.providers import (
    ProviderKeyResponse,
    ResearchKeyCreateRequest,
    TestConnectionRequest,
    TestConnectionResponse,
)

router = APIRouter(prefix="/research/keys", tags=["research"])


@router.post("", response_model=ProviderKeyResponse, status_code=status.HTTP_201_CREATED)
async def upsert_research_key(
    req: ResearchKeyCreateRequest,
    user_id: CurrentUserId,
    db: DbSession,
    vault: Vault,
) -> Any:
    """Store or update an encrypted research provider API key."""
    if req.provider not in ResearchProviderAdapterFactory.supported_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported research provider: {req.provider}",
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
        existing.is_verified = False
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
async def list_research_keys(
    user_id: CurrentUserId,
    db: DbSession,
) -> Any:
    """List all configured research keys for the current user."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider.in_(ResearchProviderAdapterFactory.supported_providers()),
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_key(
    provider: str,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """Remove a configured research provider key."""
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
async def test_research_connection(
    provider: str,
    req: TestConnectionRequest,
) -> Any:
    """Test a raw API key against a research provider."""
    try:
        adapter = ResearchProviderAdapterFactory.create(provider)
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
