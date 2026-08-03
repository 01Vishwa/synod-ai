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

    # ── Supabase ────────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""             # public anon key — safe to expose to client
    SUPABASE_SERVICE_ROLE_KEY: str = ""     # service role key — backend-only, never sent to client

    # ── Direct PostgreSQL (for SQLAlchemy + LangGraph checkpointer) ─────────
    DATABASE_URL: str = ""

    # ── LangSmith observability ─────────────────────────────────────────────
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "synod-ai"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    # ── Langfuse observability (optional — no-op if keys are absent) ─────────
    LANGFUSE_TRACING: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # ── Application security ────────────────────────────────────────────────
    # Fernet-compatible 32-byte URL-safe base64 key for provider-key encryption
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # ── Notion OAuth (Notion integration settings) ───────────────────────────
    NOTION_CLIENT_ID: str = ""
    NOTION_CLIENT_SECRET: str = ""
    # Must match the redirect URI registered in your Notion integration
    NOTION_REDIRECT_URI: str = "http://localhost:3000/settings/notion/callback"
    NOTION_PARENT_PAGE_ID: Optional[str] = None

    # ── CORS ────────────────────────────────────────────────────────────────
    # Accepts a comma-separated string from env or a JSON list
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── Rate-limiting defaults ───────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60           # requests per (user × provider) per minute

    # ── Per-member request timeout ───────────────────────────────────────────
    COUNCIL_MEMBER_TIMEOUT_SECONDS: int = 60
    COUNCIL_MEMBER_MAX_RETRIES: int = 2
    GRAPH_TIMEOUT_SECONDS: int = 300

    # ── SSE streaming ────────────────────────────────────────────────────────
    SSE_POLL_INTERVAL_SECONDS: float = 0.5    # how often event_generator polls the DB
    SSE_MAX_POLL_SECONDS: float = 10.0        # backoff ceiling for the poll interval
    SSE_MAX_DURATION_SECONDS: float = 300.0   # hard wall-clock cap (5 minutes)
    SSE_PING_INTERVAL_SECONDS: float = 15.0   # sse_starlette keepalive ping cadence
    SSE_SEND_TIMEOUT_SECONDS: float = 300.0   # sse_starlette per-send timeout

    # ── OpenRouter ───────────────────────────────────────────────────────────
    # Model used for the 1-token validation ping in validate_key().
    # gpt-4o-mini is OpenRouter's most stable, cheapest always-available model.
    OPENROUTER_VALIDATION_MODEL: str = "openai/gpt-4o-mini"

    # ── NVIDIA NIM ───────────────────────────────────────────────────────────
    # Model used for the 1-token validation ping in validate_key().
    NVIDIA_NIM_VALIDATION_MODEL: str = "meta/llama-3.1-8b-instruct"

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

    @field_validator("CREDENTIAL_ENCRYPTION_KEY", mode="after")
    @classmethod
    def _validate_encryption_key(cls, v: str, info) -> str:
        env = (info.data or {}).get("ENVIRONMENT", "development")
        if not v and env.lower() != "development":
            raise ValueError(
                "CREDENTIAL_ENCRYPTION_KEY must be set in non-development environments. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return v

    @field_validator("SUPABASE_URL", mode="after")
    @classmethod
    def _validate_supabase_url(cls, v: str, info) -> str:
        env = (info.data or {}).get("ENVIRONMENT", "development")
        if not v and env.lower() != "development":
            raise ValueError(
                "SUPABASE_URL must be set in non-development environments."
            )
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
