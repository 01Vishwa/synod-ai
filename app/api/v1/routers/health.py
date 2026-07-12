"""
api/v1/routers/health.py — Liveness and readiness endpoints.

/health   → liveness probe  (are we running?)
/readiness → readiness probe (can we serve traffic? checks DB connectivity)

These are the only endpoints that do NOT require authentication — they exist
for load balancers, Kubernetes probes, and uptime monitors.

Pattern: Health Endpoint (Michael Nygard's "Release It!"), separate liveness
         from readiness so k8s/ALB can distinguish "restart me" from "stop
         sending me traffic".
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.adapters.persistence.database import async_session_factory
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    description="Returns 200 if the application process is alive. "
                "Does NOT check external dependencies.",
    responses={200: {"description": "Application is alive"}},
)
async def health() -> dict:
    """
    Liveness check — always fast, always succeeds if the process is running.

    Kubernetes liveness probe: restart the pod only if this fails.
    """
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get(
    "/readiness",
    summary="Readiness probe",
    description="Returns 200 if the application is ready to serve traffic "
                "(database connection verified). Returns 503 if not ready.",
    responses={
        200: {"description": "Application is ready"},
        503: {"description": "Application is not ready — database unavailable"},
    },
)
async def readiness() -> JSONResponse:
    """
    Readiness check — verifies critical infrastructure before accepting traffic.

    Currently checks:
        - PostgreSQL (Supabase) connectivity via a lightweight 'SELECT 1' query.

    Kubernetes readiness probe: stop routing traffic until this succeeds.
    """
    checks: dict[str, object] = {}
    all_ok = True

    # ── Database check ────────────────────────────────────────────────────
    db_start = time.perf_counter()
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - db_start) * 1000, 1),
        }
    except Exception as exc:
        logger.error("Readiness check — database FAILED: %s", exc)
        checks["database"] = {"status": "error", "detail": "Database unreachable"}
        all_ok = False

    payload = {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "version": settings.VERSION,
    }
    return JSONResponse(
        content=payload,
        status_code=200 if all_ok else 503,
    )
