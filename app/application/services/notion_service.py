"""
application/services/notion_service.py — NotionService Orchestrator.

This service acts as the orchestration layer for all Notion operations.
It handles the OAuth 2.0 PKCE flow (start and complete) and encapsulates
the PublishHandler invocation.

Pattern: Service Layer (orchestrates domain/adapter logic, manages transactions),
         Facade (simplifies complex API interactions for the routers/nodes).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Optional

import httpx

from app.adapters.notion.oauth_state_store import OAuthStateStore
from app.application.commands.publish_notion import PublishNotionCommand
from app.application.handlers.publish_handler import PublishHandler
from app.core.config import settings
from app.domain.council_state import CouncilState
from app.domain.ports.notion_port import NotionPublishResult

logger = logging.getLogger(__name__)


class NotionOAuthError(Exception):
    """Raised when the OAuth flow fails."""


class NotionService:
    """
    Service for Notion OAuth flows and report publishing.
    """

    def __init__(
        self,
        publish_handler: PublishHandler,
        state_store: OAuthStateStore,
    ) -> None:
        self._publish_handler = publish_handler
        self._state_store = state_store

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish_report(
        self,
        state: CouncilState,
        access_token: str,
        parent_page_id: Optional[str] = None,
    ) -> NotionPublishResult:
        """
        Execute the publish operation using the command pattern.
        """
        command = PublishNotionCommand(
            state=state,
            access_token=access_token,
            parent_page_id=parent_page_id,
        )
        return await self._publish_handler.execute(command)

    # ── OAuth 2.0 PKCE Flow ───────────────────────────────────────────────────

    async def start_oauth(
        self, user_id: str, parent_page_id: Optional[str] = None
    ) -> str:
        """
        Generate the Notion OAuth authorization URL with PKCE and CSRF state.

        Args:
            user_id:        Supabase UUID of the user starting the flow.
            parent_page_id: Optional page to file reports under.

        Returns:
            The authorization URL to redirect the user to.
        """
        if not settings.NOTION_CLIENT_ID:
            raise NotionOAuthError(
                "Notion integration is not configured (missing NOTION_CLIENT_ID)."
            )

        # 1. Generate CSRF state token
        state_token = secrets.token_urlsafe(32)

        # 2. Generate PKCE verifier and challenge
        code_verifier = secrets.token_urlsafe(96)
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )

        # 3. Store state securely (TTL 10 mins)
        await self._state_store.save(
            state_token=state_token,
            code_verifier=code_verifier,
            user_id=user_id,
            parent_page_id=parent_page_id,
        )

        # 4. Construct Notion auth URL
        params = {
            "client_id": settings.NOTION_CLIENT_ID,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": settings.NOTION_REDIRECT_URI,
            "state": state_token,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        
        url_params = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://api.notion.com/v1/oauth/authorize?{url_params}"

    async def complete_oauth(
        self,
        code: str,
        state_token: str,
    ) -> tuple[str, str, Optional[str], Optional[str]]:
        """
        Exchange the OAuth code for an access token using PKCE.

        Args:
            code:        The authorization code returned by Notion.
            state_token: The CSRF state token returned by Notion.

        Returns:
            Tuple of (access_token, user_id, workspace_name, parent_page_id).

        Raises:
            NotionOAuthError: if the state is invalid, or the exchange fails.
        """
        # 1. Retrieve and consume the state token (prevents replay/CSRF)
        oauth_state = await self._state_store.retrieve_and_delete(state_token)
        if not oauth_state:
            raise NotionOAuthError("Invalid, expired, or already-used state token.")

        # 2. Basic auth header for the token exchange
        client_creds = f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}"
        basic_auth = base64.b64encode(client_creds.encode()).decode()

        # 3. Exchange code + verifier for token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.notion.com/v1/oauth/token",
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/json",
                },
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.NOTION_REDIRECT_URI,
                    "code_verifier": oauth_state.code_verifier,
                },
                timeout=10.0,
            )

        if not resp.is_success:
            logger.error("Notion token exchange failed: %s", resp.text)
            raise NotionOAuthError(f"Token exchange failed: HTTP {resp.status_code}")

        data = resp.json()
        access_token = data.get("access_token")
        workspace_name = data.get("workspace_name")

        if not access_token:
            raise NotionOAuthError("Notion response missing access_token.")

        logger.info(
            "notion_service: successfully completed OAuth for user %s",
            oauth_state.user_id,
        )

        return (
            access_token,
            oauth_state.user_id,
            workspace_name,
            oauth_state.parent_page_id,
        )
