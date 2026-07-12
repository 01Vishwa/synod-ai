"""
adapters/persistence/database.py — Async SQLAlchemy engine + session factory.

This module is the ONLY place that constructs the database engine.  All
other layers receive an `AsyncSession` via FastAPI's Dependency Injection
and never import this module directly.

Design:
  - Uses SQLAlchemy 2.x async engine (asyncpg driver) for non-blocking I/O.
  - Engine is created once at process startup and lives for the process lifetime.
  - AsyncSession is scoped per-request via FastAPI Depends() in deps.py.

Pattern: Singleton (engine), Factory (session_factory), Unit of Work (the
         session itself is the UoW boundary — committed or rolled back as one).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.models import Base
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Engine Singleton ──────────────────────────────────────────────────────

def _build_async_url(sync_url: str) -> str:
    """
    Convert a standard postgres:// URL to asyncpg's postgresql+asyncpg:// scheme.

    Handles both postgres:// (legacy Heroku-style) and postgresql:// forms.
    """
    url = sync_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "postgresql+asyncpg://" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def create_engine() -> AsyncEngine:
    """
    Build the process-level async engine with connection pool settings
    drawn from Settings.
    """
    async_url = _build_async_url(settings.DATABASE_URL)
    return create_async_engine(
        async_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,          # verify connections before use
        echo=settings.is_development,  # SQL echo in dev only
        future=True,
    )


# Module-level singletons — initialised at first import; safe for multi-threaded use.
engine: AsyncEngine = create_engine()
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,   # keep ORM objects usable after commit
    autoflush=False,
)


# ── Session dependency ────────────────────────────────────────────────────

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session.

    Commits on clean exit; rolls back on any exception.
    Used both directly and wrapped by FastAPI's Depends().
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields one AsyncSession per request.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_db_session() as session:
        yield session


# ── Schema management ─────────────────────────────────────────────────────

async def create_all_tables() -> None:
    """
    Create all tables that are not yet present in the database.

    Called from main.py startup hook in development. In production, use
    Alembic migrations instead (`alembic upgrade head`).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")


async def dispose_engine() -> None:
    """Cleanly close all pooled connections (called on app shutdown)."""
    await engine.dispose()
    logger.info("Database engine disposed.")
