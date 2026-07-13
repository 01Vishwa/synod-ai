"""
api/v1/deps.py — FastAPI Dependency Injection root.

This is the single place where concrete adapters, repositories, and services
are wired into route handlers.  Route handlers declare what they need via type
hints + Depends(); they never import a concrete class directly.

This pattern:
  - Makes every route handler trivially unit-testable by injecting fakes.
  - Ensures the KeyVault singleton is the only path to plaintext keys.
  - Gives us one place to swap adapters (e.g., replace LangSmith with Langfuse)
    without touching any route file.

Pattern: Dependency Injection (FastAPI Depends), Facade (each dep function is a
         one-line facade hiding construction complexity from the route handler).
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.observability.langsmith_tracer import LangSmithTracer
from app.adapters.persistence.database import get_db
from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
from app.adapters.security.key_vault import KeyVault
from app.adapters.notion.oauth_state_store import OAuthStateStore
from app.adapters.notion.notion_mcp_adapter import NotionMcpAdapter
from app.application.handlers.publish_handler import PublishHandler
from app.application.services.notion_service import NotionService
from app.domain.ports.observability_port import TracerPort
from app.domain.ports.session_repository import SessionRepository
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Supabase JWKS client (module-level singleton, caches public keys) ───────

_SUPABASE_ISSUER = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
_SUPABASE_JWKS_URL = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

_jwks_client = PyJWKClient(_SUPABASE_JWKS_URL, cache_keys=True)


# ── Database session ───────────────────────────────────────────────────────

async def set_rls_context(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[Optional[str], Header()] = None,
) -> None:
    """
    Sets the Supabase RLS JWT claims on the database connection if a token is present.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return

    token = authorization.removeprefix("Bearer ").strip()
    try:
        # We reuse the JWKS client to verify and extract the sub claim
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=_SUPABASE_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
        user_id = payload.get("sub")
        if user_id:
            import json
            from sqlalchemy import text
            claims = json.dumps({"sub": user_id, "role": "authenticated"})
            await db.execute(
                text("SELECT set_config('request.jwt.claims', :claims, true)"), 
                {"claims": claims}
            )
    except Exception:
        pass  # Token validation errors are strictly handled by get_current_user_id

async def get_db_with_rls(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(set_rls_context),
) -> AsyncSession:
    """Yield the DB session after ensuring RLS context is set."""
    return db

async def get_session(
    db: Annotated[AsyncSession, Depends(get_db_with_rls)],
) -> SessionRepository:
    """
    Inject a request-scoped PostgresSessionRepository.

    The AsyncSession is committed/rolled back by get_db()'s context manager,
    so this dependency doesn't need to manage the transaction boundary.
    """
    return PostgresSessionRepository(db)


# ── Observability (Tracer) ─────────────────────────────────────────────────

def get_tracer() -> TracerPort:
    """
    Inject the process-level LangSmith tracer singleton.

    The tracer is a singleton because creating a Client per-request would be
    wasteful; the singleton is thread-safe once initialised.
    """
    return LangSmithTracer.instance()


# ── Security (KeyVault) ───────────────────────────────────────────────────

def get_key_vault() -> KeyVault:
    """Inject the process-level KeyVault singleton."""
    return KeyVault.instance()


# ── Services ──────────────────────────────────────────────────────────────

async def get_notion_service() -> NotionService:
    """
    Inject the NotionService.
    Assembles the required adapters (state store, MCP adapter, publish handler).
    """
    port = NotionMcpAdapter()
    handler = PublishHandler(port=port)
    store = OAuthStateStore.instance()
    return NotionService(publish_handler=handler, state_store=store)


# ── Supabase auth (ES256 JWKS verification) ───────────────────────────────

async def get_current_user_id(
    authorization: Annotated[Optional[str], Header()] = None,
) -> str:
    """
    Extract and verify the Supabase JWT from the Authorization header.

    Verifies the ES256 signature against Supabase's public JWKS endpoint,
    validates issuer, audience ("authenticated"), and expiry.

    Returns the authenticated user's UUID (sub claim).

    Raises:
        HTTPException 401: if no token is provided or validation fails.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "missing_token",
                "message": "Authentication is required.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    # Log only safe header metadata — never the token itself
    try:
        unverified_header = jwt.get_unverified_header(token)
        logger.debug(
            "JWT verification attempt",
            extra={
                "algorithm": unverified_header.get("alg"),
                "kid": unverified_header.get("kid"),
                "expected_issuer": _SUPABASE_ISSUER,
            },
        )
    except Exception:
        pass  # header decode failure will be caught below

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=_SUPABASE_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )

        user_id: str = payload.get("sub", "")
        if not user_id:
            raise InvalidTokenError("JWT 'sub' claim is missing.")
        return user_id

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "token_expired",
                "message": "Your session has expired.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_audience",
                "message": "Invalid authentication token.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_issuer",
                "message": "Invalid authentication token.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidTokenError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "Invalid authentication token.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except Exception as exc:
        logger.error("Unexpected JWT verification error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "Invalid authentication token.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Convenience type aliases for route signatures ─────────────────────────

CurrentUserId = Annotated[str, Depends(get_current_user_id)]
SessionRepo = Annotated[SessionRepository, Depends(get_session)]
Tracer = Annotated[TracerPort, Depends(get_tracer)]
Vault = Annotated[KeyVault, Depends(get_key_vault)]
DbSession = Annotated[AsyncSession, Depends(get_db_with_rls)]
NotionSvc = Annotated[NotionService, Depends(get_notion_service)]
