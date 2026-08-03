"""
api/v1/routers/providers.py — LLM Provider Key Management.

Endpoints for adding, retrieving, and testing LLM provider API keys.
Keys are encrypted at rest via KeyVault and never returned in plaintext.

Schema contract (actual Supabase provider_keys table):
  id              UUID PK
  user_id         UUID FK → auth.users(id)
  provider        provider_name enum (openrouter | nvidia_nim | github_models)
  ciphertext_b64  TEXT  — Fernet-encrypted API key
  key_fingerprint TEXT  — safe display hint: "••••<last4>"
  last_tested_at  TIMESTAMPTZ (nullable)
  last_test_ok    BOOLEAN (nullable)
  last_test_error TEXT (nullable)
  created_at / updated_at TIMESTAMPTZ
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

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
from app.core.exceptions import ProviderError, AuthenticationError, ProviderTimeoutError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])


def _compute_fingerprint(api_key: str) -> str:
    """
    Return a safe, non-secret display hint for an API key.

    Takes the last 4 characters (sufficient to visually confirm a key
    without revealing anything actionable) and prepends bullet characters.

    Example:  "sk-or-v1-abcdefghijklmnop"  →  "••••mnop"
    """
    tail = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"\u2022\u2022\u2022\u2022{tail}"


# ── GET /providers ────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProviderKeyResponse])
async def list_provider_keys(
    user_id: CurrentUserId,
    db: DbSession,
) -> Any:
    """
    List all configured LLM provider keys for the current user.

    Returns 200 with an empty list [] for a new user with no keys.
    Never returns ciphertext_b64, plaintext keys, or encryption material.
    """
    logger.debug("GET /providers entered", extra={"user_id": user_id})

    try:
        stmt = select(ProviderKeyModel).where(
            ProviderKeyModel.user_id == user_id,
            ProviderKeyModel.provider.in_(ProviderAdapterFactory.supported_providers()),
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        logger.debug(
            "GET /providers query succeeded",
            extra={"user_id": user_id, "count": len(rows)},
        )
        return rows

    except OperationalError:
        logger.exception(
            "GET /providers — database unavailable",
            extra={"user_id": user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Provider settings could not be loaded.",
            },
        )

    except SQLAlchemyError:
        logger.exception(
            "GET /providers — database query failed",
            extra={"user_id": user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Provider settings could not be loaded.",
            },
        )


# ── POST /providers ───────────────────────────────────────────────────────────

@router.post("", response_model=ProviderKeyResponse, status_code=status.HTTP_201_CREATED)
async def upsert_provider_key(
    req: ProviderKeyCreateRequest,
    user_id: CurrentUserId,
    db: DbSession,
    vault: Vault,
) -> Any:
    """
    Store or update an encrypted LLM provider API key.

    Flow:
        1. Validate provider is in the LLM allow-list (Pydantic + factory check).
        2. Encrypt the API key via KeyVault (Fernet AES-128-CBC).
        3. Compute a safe display fingerprint (last 4 chars, no secret).
        4. Upsert: update existing row OR insert new row — atomic.
        5. Return safe metadata only (no ciphertext, no plaintext).
    """
    logger.debug(
        "POST /providers entered",
        extra={"user_id": user_id, "provider": req.provider},
    )

    # ── 1. Provider allow-list check ────────────────────────────────────────
    if req.provider not in ProviderAdapterFactory.supported_providers():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_PROVIDER",
                "message": f"Unsupported LLM provider: '{req.provider}'.",
            },
        )

    # Normalize and reject empty keys
    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMPTY_API_KEY",
                "message": "API key cannot be empty.",
            },
        )

    # Validate the plaintext key against the provider before persistence
    try:
        adapter = ProviderAdapterFactory.create(req.provider)
        await adapter.validate_key(api_key)
    except AuthenticationError:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_api_key",
                "message": "The API key was rejected by the provider. Please check the key and try again."
            }
        )
    except ProviderTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "provider_timeout",
                "message": str(exc.message)
            }
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "provider_error",
                "message": str(exc.message)
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "provider_validation_error",
                "message": f"Failed to validate key with provider: {exc}"
            }
        )

    # ── 2. Encrypt — fail fast if vault is misconfigured ────────────────────
    try:
        ciphertext = vault.encrypt(api_key)
    except Exception:
        logger.exception(
            "POST /providers — encryption failed",
            extra={"user_id": user_id, "provider": req.provider},
            # NOTE: req.api_key is intentionally NOT logged
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "ENCRYPTION_FAILED",
                "message": "Could not store provider key. Contact support.",
            },
        )

    # ── 3. Compute safe display fingerprint ─────────────────────────────────
    fingerprint = _compute_fingerprint(api_key)

    # ── 4. Upsert via select + update or insert ──────────────────────────────
    try:
        stmt = select(ProviderKeyModel).where(
            ProviderKeyModel.user_id == user_id,
            ProviderKeyModel.provider == req.provider,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)

        if existing:
            # Update existing row — preserves the row's id and created_at
            existing.ciphertext_b64 = ciphertext
            existing.key_fingerprint = fingerprint
            # Key validation succeeded, save the positive test results
            existing.last_test_ok = True
            existing.last_tested_at = now
            existing.last_test_error = None
            model = existing
            logger.info(
                "POST /providers — updated existing key",
                extra={"user_id": user_id, "provider": req.provider},
            )
        else:
            model = ProviderKeyModel(
                user_id=user_id,
                provider=req.provider,
                ciphertext_b64=ciphertext,
                key_fingerprint=fingerprint,
                last_test_ok=True,
                last_tested_at=now,
                last_test_error=None,
            )
            db.add(model)
            logger.info(
                "POST /providers — inserted new key",
                extra={"user_id": user_id, "provider": req.provider},
            )

        await db.flush()
        await db.refresh(model)
        return model

    except IntegrityError:
        logger.exception(
            "POST /providers — integrity constraint violated",
            extra={"user_id": user_id, "provider": req.provider},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "A key for this provider already exists. Try again.",
            },
        )

    except OperationalError:
        logger.exception(
            "POST /providers — database unavailable",
            extra={"user_id": user_id, "provider": req.provider},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Provider key could not be saved.",
            },
        )

    except SQLAlchemyError:
        logger.exception(
            "POST /providers — database error during upsert",
            extra={"user_id": user_id, "provider": req.provider},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Provider key could not be saved.",
            },
        )


# ── DELETE /providers/{provider} ─────────────────────────────────────────────

@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
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


# ── POST /providers/{provider}/test ──────────────────────────────────────────

@router.post("/{provider}/test", response_model=TestConnectionResponse)
async def test_connection(
    provider: str,
    req: TestConnectionRequest,
    user_id: CurrentUserId,
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


# ── GET /providers/{provider}/models ─────────────────────────────────────────

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

    logger.info(
        "Catalog request started",
        extra={"user_id": user_id, "provider": provider},
    )

    if not key_model:
        logger.warning(
            "Catalog request failed: no API key",
            extra={"user_id": user_id, "provider": provider},
        )
        raise HTTPException(
            status_code=404,
            detail=f"No API key configured for '{provider}'. Please add one first.",
        )

    try:
        api_key = vault.decrypt(key_model.ciphertext_b64)
        adapter = ProviderAdapterFactory.create(provider)
        models = await adapter.list_models(api_key)

        import datetime as _dt
        key_model.last_test_ok = True
        key_model.last_tested_at = _dt.datetime.now(_dt.timezone.utc)
        key_model.last_test_error = None
        await db.flush()

        logger.info(
            "Catalog request completed",
            extra={"user_id": user_id, "provider": provider, "count": len(models)},
        )

        return ModelCatalogResponse.from_model_infos(models)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc.message)) from exc
    except Exception as exc:
        logger.exception(
            "GET /providers/%s/models — unexpected error",
            provider,
            extra={"user_id": user_id, "provider": provider},
        )
        raise HTTPException(status_code=500, detail="Failed to fetch model catalog.") from exc
