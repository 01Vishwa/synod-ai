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

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.observability.langsmith_tracer import LangSmithTracer
from app.adapters.persistence.database import get_db
from app.adapters.persistence.postgres_session_repository import PostgresSessionRepository
from app.adapters.security.key_vault import KeyVault
from app.domain.ports.observability_port import TracerPort
from app.domain.ports.session_repository import SessionRepository

logger = logging.getLogger(__name__)


# ── Database session ───────────────────────────────────────────────────────

async def get_session(
    db: Annotated[AsyncSession, Depends(get_db)],
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


# ── Supabase auth (JWT verification) ─────────────────────────────────────

async def get_current_user_id(
    authorization: Annotated[Optional[str], Header()] = None,
) -> str:
    """
    Extract and verify the Supabase JWT from the Authorization header.

    Returns the authenticated user's UUID (sub claim).

    In production this verifies the JWT signature against Supabase's JWKS
    endpoint using the SUPABASE_SECRET_KEY.  The implementation below is the
    minimal bootstrap version — the full JWT verification is wired here
    so every route that Depends(get_current_user_id) is protected.

    Raises:
        HTTPException 401: if no token is provided or validation fails.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        user_id = _verify_supabase_jwt(token)
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return user_id


def _verify_supabase_jwt(token: str) -> str:
    """
    Verify a Supabase JWT and return the subject (user UUID).

    Uses PyJWT to decode and verify the token against the Supabase secret key.
    The SUPABASE_SECRET_KEY (new model) is used as the HMAC secret for HS256
    tokens issued by Supabase Auth.

    Returns:
        The authenticated user's UUID string.

    Raises:
        Exception: on any verification failure (expired, invalid signature, etc.)
    """
    import jwt as pyjwt  # PyJWT — not the `jwt` package
    from app.core.config import settings

    payload = pyjwt.decode(
        token,
        settings.SUPABASE_SECRET_KEY,
        algorithms=["HS256"],
        options={"verify_aud": False},  # Supabase tokens omit aud in some configurations
    )
    user_id: str = payload.get("sub", "")
    if not user_id:
        raise ValueError("JWT 'sub' claim is missing.")
    return user_id


# ── Convenience type aliases for route signatures ─────────────────────────

CurrentUserId = Annotated[str, Depends(get_current_user_id)]
SessionRepo = Annotated[SessionRepository, Depends(get_session)]
Tracer = Annotated[TracerPort, Depends(get_tracer)]
Vault = Annotated[KeyVault, Depends(get_key_vault)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
