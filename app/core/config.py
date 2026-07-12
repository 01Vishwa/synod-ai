"""
core/config.py — Centralised, environment-driven configuration.

Uses pydantic-settings so every value is type-validated on startup and can
be overridden by environment variables or a .env file.  Nothing outside this
module should ever import `os.environ` or read `.env` directly.

Pattern: Configuration Object (single source of truth for all env knobs)
"""
from __future__ import annotations

import os
from typing import List, Optional

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Application identity ────────────────────────────────────────────────
    PROJECT_NAME: str = "Synod-ai"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DESCRIPTION: str = "Supervisor-controlled, multi-LLM deliberation platform"

    # ── Runtime environment ─────────────────────────────────────────────────
    ENVIRONMENT: str = "development"           # development | staging | production
    DEBUG: bool = False
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Supabase (new publishable / secret key model) ───────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""             # backend-only — never sent to client

    # ── Direct PostgreSQL (for SQLAlchemy + LangGraph checkpointer) ─────────
    DATABASE_URL: str = ""

    # ── LangSmith observability ─────────────────────────────────────────────
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "synod-ai"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    # ── Application security ────────────────────────────────────────────────
    # Fernet-compatible 32-byte URL-safe base64 key for provider-key encryption
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # ── CORS ────────────────────────────────────────────────────────────────
    # Accepts a comma-separated string from env or a JSON list
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── Rate-limiting defaults ───────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60           # requests per (user × provider) per minute

    # ── Per-member request timeout ───────────────────────────────────────────
    COUNCIL_MEMBER_TIMEOUT_SECONDS: int = 60
    COUNCIL_MEMBER_MAX_RETRIES: int = 2

    # ── Database pool settings ───────────────────────────────────────────────
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> List[str]:
        """Accept a comma-separated string or a list from .env."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Extra env vars are silently ignored so we don't break on provider keys
        # stored in .env (e.g. OPENROUTER_API_KEY) that aren't declared here.
        extra="ignore",
    )


# Singleton — import this, never instantiate Settings directly.
settings = Settings()
