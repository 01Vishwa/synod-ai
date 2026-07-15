"""
main.py — FastAPI Application Bootstrap.

This module defines the application factory `create_app()`, wiring together:
  - Global configuration (CORS, environment)
  - Structured logging middleware
  - Global exception handlers
  - Database lifecycle (startup/shutdown)
  - API routers

Pattern: Application Factory.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.persistence.database import create_all_tables, dispose_engine
from app.api.v1.api import api_router
from app.api.v1.routers.health import router as health_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.llm_router import LLMRouter
from app.core.logging import LoggingMiddleware, setup_logging

logger = logging.getLogger("synod.bootstrap")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    Startup:
      - Initialises structured JSON logging.
      - Ensures database tables are created (in development).
    Shutdown:
      - Disposes the async database engine cleanly.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
    logger.info("Starting up %s (env=%s)...", settings.PROJECT_NAME, settings.ENVIRONMENT)

    # In development, auto-create tables if they don't exist.
    # In production, this should be handled by Alembic migrations.
    if settings.is_development:
        await create_all_tables()

    # Instantiate LLMRouter as a process singleton.
    # max_attempts = retries + 1 (e.g. COUNCIL_MEMBER_MAX_RETRIES=2 → 3 total attempts)
    app.state.llm_router = LLMRouter(
        max_attempts=settings.COUNCIL_MEMBER_MAX_RETRIES + 1
    )
    logger.info(
        "LLMRouter initialised (max_attempts=%d).",
        settings.COUNCIL_MEMBER_MAX_RETRIES + 1,
    )
    # Register with the runner module so background tasks share this instance
    from app.orchestration.runner import set_llm_router_singleton
    set_llm_router_singleton(app.state.llm_router)


    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Shutting down...")
    await dispose_engine()


def create_app() -> FastAPI:
    """
    Constructs and configures the FastAPI application instance.

    This factory function ensures the app is built purely from the environment
    configuration via pydantic-settings, making it environment-driven.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.DESCRIPTION,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS Configuration ───────────────────────────────────────────────
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ── Middleware ───────────────────────────────────────────────────────
    app.add_middleware(LoggingMiddleware)

    # ── Exception Handlers ───────────────────────────────────────────────
    setup_exception_handlers(app)

    # ── Routers ──────────────────────────────────────────────────────────
    # Top-level health endpoints (often required at / for load balancers)
    app.include_router(health_router)
    
    # API v1 routes
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


# The ASGI application instance for uvicorn to serve.
app = create_app()
