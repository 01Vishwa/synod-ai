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
    Column,
    DateTime,
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
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Owning user (Supabase auth.users UUID)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Denormalised stage for fast filtering ("stage_1", "done", "error", …)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="stage_1")

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
    Stores one encrypted provider API key per (user_id, provider) pair.

    The encrypted_key column holds the Fernet-encrypted ciphertext; the
    raw plaintext key is NEVER stored.
    """
    __tablename__ = "provider_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Owning Supabase user
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Provider slug: "openrouter" | "nvidia_nim" | "tavily" | "anakin" | "notion"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # Fernet-encrypted API key ciphertext
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Human-readable label the user assigned (e.g. "My OpenRouter key")
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Whether this key has been verified via a test-connection call
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
        # One key per (user, provider) — users can only have one active key per provider
        UniqueConstraint("user_id", "provider", name="uq_provider_keys_user_provider"),
    )

    def __repr__(self) -> str:
        return f"<ProviderKeyModel user={self.user_id} provider={self.provider}>"
