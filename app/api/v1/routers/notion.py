"""
api/v1/routers/notion.py — Notion Integration Management.

Endpoints for securely storing the user's Notion OAuth token, handling
the OAuth callback, and manually republishing reports.
"""
from __future__ import annotations

import datetime
import logging
import urllib.parse
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.adapters.persistence.models import ProviderKeyModel
from app.api.v1.deps import CurrentUserId, DbSession, Vault, NotionSvc, SessionRepo
from app.api.v1.schemas.providers import (
    NotionConnectResponse,
    ProviderKeyResponse,
    OAuthAuthorizeResponse,
    NotionPublishResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notion", tags=["notion"])


@router.post("/connect", response_model=OAuthAuthorizeResponse)
async def connect_notion(
    user_id: CurrentUserId,
    notion_svc: NotionSvc,
) -> Any:
    """
    Start the Notion OAuth flow.
    Returns the Notion authorization URL (PKCE and state included).
    """
    from app.core.config import settings
    try:
        url = await notion_svc.start_oauth(
            user_id=user_id,
            parent_page_id=settings.NOTION_PARENT_PAGE_ID,
        )
        return OAuthAuthorizeResponse(auth_url=url)
    except Exception as exc:
        logger.error("Failed to start Notion OAuth: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/oauth/callback", include_in_schema=False)
async def notion_oauth_callback(
    code: str,
    state: str,
    notion_svc: NotionSvc,
    db: DbSession,
    vault: Vault,
) -> Any:
    """
    Handle the OAuth redirect from Notion.

    OAuth flow (backend-first):
      1. User clicks "Connect Notion" → frontend calls POST /notion/connect.
      2. Backend builds the Notion auth URL with NOTION_REDIRECT_URI pointing here
         (http://localhost:8000/api/v1/notion/oauth/callback) and a server-side
         CSRF state token.
      3. Notion redirects back here with `code` + `state`.
      4. Backend validates the state token, exchanges the code for an access token
         using NOTION_CLIENT_SECRET (which must never leave the server), and stores
         the encrypted token in the database.
      5. Browser is redirected to the frontend confirmation page.

    ⚠️ MANUAL STEP: The redirect URI registered in your Notion integration dashboard
    (https://www.notion.so/my-integrations → "Redirect URIs") must exactly match
    NOTION_REDIRECT_URI in .env (scheme, host, port, path, no trailing slash):
        http://localhost:8000/api/v1/notion/oauth/callback
    """
    from app.core.config import settings
    frontend_base = settings.FRONTEND_URL.rstrip("/")

    try:
        access_token, user_id, workspace_name, parent_page_id = await notion_svc.complete_oauth(
            code=code,
            state_token=state,
        )
    except Exception as exc:
        logger.error("OAuth callback failed: %s", exc)
        safe_error = urllib.parse.quote(str(exc)[:200])
        return RedirectResponse(f"{frontend_base}/settings/integrations?notion_error={safe_error}")

    # Encrypt the token for storage
    encrypted = vault.encrypt(access_token)
    fingerprint = f"••••{access_token[-4:]}" if len(access_token) >= 4 else "••••"
    now = datetime.datetime.now(datetime.timezone.utc)

    # Upsert into DB
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == "notion",
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.ciphertext_b64 = encrypted
        existing.key_fingerprint = fingerprint
        existing.last_test_ok = True
        existing.last_tested_at = now
        existing.last_test_error = None
    else:
        model = ProviderKeyModel(
            user_id=user_id,
            provider="notion",
            ciphertext_b64=encrypted,
            key_fingerprint=fingerprint,
            last_test_ok=True,
            last_tested_at=now,
            last_test_error=None,
        )
        db.add(model)

    await db.flush()
    return RedirectResponse(f"{frontend_base}/settings/integrations?notion=connected")


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


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
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


@router.post("/publish/{session_id}", response_model=NotionPublishResponse)
async def manual_publish(
    session_id: str,
    user_id: CurrentUserId,
    repo: SessionRepo,
    notion_svc: NotionSvc,
    vault: Vault,
    db: DbSession,
) -> Any:
    """
    Manually push a completed report to Notion.
    """
    # 1. Load session
    state = await repo.load(session_id, user_id=user_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    if state.get("stage") != "done":
        raise HTTPException(
            status_code=400,
            detail="Session is not complete. Cannot publish yet."
        )

    # 2. Fetch Notion key
    stmt = select(ProviderKeyModel).where(
        ProviderKeyModel.user_id == user_id,
        ProviderKeyModel.provider == "notion",
    )
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=400,
            detail="Notion is not connected. Please connect Notion in settings first."
        )

    from app.core.config import settings
    access_token = vault.decrypt(model.ciphertext_b64)
    parent_page_id = settings.NOTION_PARENT_PAGE_ID

    # 3. Publish
    try:
        res = await notion_svc.publish_report(
            state=state,
            access_token=access_token,
            parent_page_id=parent_page_id,
        )
    except Exception as exc:
        logger.error("Manual publish failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}")

    # 4. Update session
    state["notion_page_url"] = res.page_url
    state["archive_status"] = "done"
    await repo.save_checkpoint(state) # type: ignore

    return NotionPublishResponse(notion_page_url=res.page_url)
