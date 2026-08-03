"""
adapters/persistence/models.py — SQLAlchemy ORM models for Supabase PostgreSQL.

These are the concrete table definitions.  Only this module and the Alembic
migration files should reference table schema details — all other layers
interact with the domain's TypedDicts, not these ORM classes.

Tables:
  - council_sessions: one row per council session; stores the full
    CouncilState as a JSONB snapshot plus indexed metadata columns for fast
    history queries.
  - provider_keys: encrypted API keys per (user_id, provider).

Pattern: Repository (models are the persistence representation; the Repository
         adapter translates between these ORM objects and domain TypedDicts).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# ── PostgreSQL enum types (create_type=False — enum already exists in DB) ────

# Matches the 'council_stage' enum in Supabase:
#   stage_1 | stage_2 | stage_3 | archiving | done | error
# Values must stay in sync with CouncilState.stage Literal in domain/council_state.py.
from app.core.config import settings as _settings

_COUNCIL_STAGE_ENUM = Enum(
    "stage_1", "stage_2", "stage_3", "archiving", "done", "error",
    name="council_stage",
    create_type=_settings.is_development,
)

# Matches the 'provider_name' enum in Supabase: openrouter | nvidia_nim | github_models
_PROVIDER_NAME_ENUM = Enum(
    "openrouter", "nvidia_nim", "github_models", "notion",
    name="provider_name",
    create_type=_settings.is_development,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Base ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Council Sessions ──────────────────────────────────────────────────────

class CouncilSessionModel(Base):
    """
    Persists one council session.

    The `state` column stores the full serialised CouncilState JSONB blob.
    Indexed metadata columns (user_id, stage, created_at) allow efficient
    listing and filtering without deserialising the full blob.
    """
    __tablename__ = "council_sessions"

    # Primary key — matches CouncilState.session_id
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Owning user (Supabase auth.users UUID)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)

    # Denormalised stage for fast filtering — maps to the 'council_stage' PG enum.
    # Using _COUNCIL_STAGE_ENUM (create_type=False) tells asyncpg the correct
    # OID so the wire type is 'council_stage', not VARCHAR.
    stage: Mapped[str] = mapped_column(_COUNCIL_STAGE_ENUM, nullable=False, default="stage_1")

    # Full CouncilState snapshot (JSONB for rich querying / partial extraction)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Denormalised quick-read columns (avoid deserialising state for list views)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Cost / token accounting (summed from aggregate_scores after Stage 3)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Optional Notion archive
    notion_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LangSmith / Langfuse trace deep-link
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Soft-delete flag
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps (set by the DB for accuracy)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_sessions_user_id_created_at", "user_id", "created_at"),
        Index("ix_sessions_stage", "stage"),
    )

    def __repr__(self) -> str:
        return f"<CouncilSessionModel id={self.id} stage={self.stage}>"


# ── Provider Keys ─────────────────────────────────────────────────────────

class ProviderKeyModel(Base):
    """
    Mirrors the actual Supabase `provider_keys` table exactly.

    Column mapping (DB → Python):
        id              UUID PK
        user_id         UUID FK → auth.users(id) ON DELETE CASCADE
        provider        provider_name enum (openrouter | nvidia_nim | github_models)
        ciphertext_b64  TEXT — Fernet-encrypted + base64-encoded API key
        key_fingerprint TEXT — safe display hint, e.g. "••••abcd" (last 4 chars)
        last_tested_at  TIMESTAMPTZ — set when /test or auto-verify is called
        last_test_ok    BOOLEAN  — NULL = never tested, True = ok, False = failed
        last_test_error TEXT     — provider error message on last failure (no secrets)
        created_at      TIMESTAMPTZ
        updated_at      TIMESTAMPTZ

    The raw plaintext API key is NEVER stored in any column.
    """
    __tablename__ = "provider_keys"

    # UUID primary key — stored as lowercase hyphenated string in Python,
    # postgres uuid type in the DB (asyncpg handles the conversion).
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Owning Supabase user — must match auth.users.id (UUID)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )

    # PostgreSQL enum — must be one of the values in the 'provider_name' type
    provider: Mapped[str] = mapped_column(
        _PROVIDER_NAME_ENUM,
        nullable=False,
    )

    # Fernet-encrypted, base64-encoded API key ciphertext — never returned to client
    ciphertext_b64: Mapped[str] = mapped_column(Text, nullable=False)

    # Safe display hint for the frontend — e.g. "••••r4Mk"
    # Computed from the last 4 chars of the plaintext key at write time.
    key_fingerprint: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Test result columns — populated by POST /{provider}/test or auto-verify
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # Matches the DB constraint name: provider_keys_user_id_provider_key
        UniqueConstraint("user_id", "provider", name="provider_keys_user_id_provider_key"),
    )

    def __repr__(self) -> str:
        return f"<ProviderKeyModel user={self.user_id} provider={self.provider}>"
