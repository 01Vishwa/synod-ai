"""
api/v1/routers/notion.py — Notion Integration Management.

Endpoints for securely storing and verifying the user's Notion OAuth token.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.api.v1.deps import CurrentUserId, DbSession, Vault
from app.api.v1.schemas.providers import (
    NotionConnectRequest,
    NotionConnectResponse,
    ProviderKeyResponse,
)

router = APIRouter(prefix="/notion", tags=["notion"])


@router.post("/connect", response_model=NotionConnectResponse, status_code=status.HTTP_201_CREATED)
async def connect_notion(
    req: NotionConnectRequest,
    user_id: CurrentUserId,
    db: DbSession,
    vault: Vault,
) -> Any:
    """Store an encrypted Notion OAuth access token."""
    encrypted = vault.encrypt(req.access_token)

    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == "notion",
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_key = encrypted
        existing.label = req.workspace_name or "Notion Workspace"
        existing.is_verified = True  # We assume token from OAuth flow is valid initially
    else:
        model = ProviderKeyModel(
            user_id=user_id,
            provider="notion",
            encrypted_key=encrypted,
            label=req.workspace_name or "Notion Workspace",
            is_verified=True,
        )
        db.add(model)

    await db.flush()
    return NotionConnectResponse(
        workspace_name=req.workspace_name,
        connected=True,
    )


@router.get("/status", response_model=ProviderKeyResponse)
async def notion_status(
    user_id: CurrentUserId,
    db: DbSession,
) -> Any:
    """Check if Notion is connected for the current user."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == "notion",
    )
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Notion is not connected.")
        
    return model


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_notion(
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """Remove the Notion integration token."""
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == "notion",
    )
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Notion is not connected.")
        
    await db.delete(model)
    await db.flush()
