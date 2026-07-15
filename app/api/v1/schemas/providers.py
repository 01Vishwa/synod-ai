"""
api/v1/schemas/providers.py — Pydantic schemas for provider key management.

These schemas validate the Settings → Providers and Settings → Integrations
flows: storing encrypted keys, listing configured providers, running
test-connection probes, and fetching the live model catalogue.

Security note: the raw API key is accepted on write (POST/PUT) but NEVER
returned on any read operation — the response schema deliberately omits it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── LLM Provider keys ─────────────────────────────────────────────────────

ProviderSlug = Literal["openrouter", "nvidia_nim"]
ResearchProviderSlug = Literal["tavily", "anakin"]
IntegrationSlug = Literal["notion"]

AnyProviderSlug = Literal["openrouter", "nvidia_nim", "tavily", "anakin", "notion"]


class ProviderKeyCreateRequest(BaseModel):
    """POST /api/v1/providers — store an encrypted API key."""
    provider: AnyProviderSlug = Field(description="Provider slug")
    api_key: str = Field(
        description="Raw API key — encrypted at rest, never returned",
        min_length=1,
        max_length=512,
    )
    label: Optional[str] = Field(
        default=None,
        description="Optional human-readable label for this key",
        max_length=128,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "openrouter",
                "api_key": "sk-or-v1-...",
                "label": "My OpenRouter key",
            }
        }
    )


class ProviderKeyResponse(BaseModel):
    """
    Safe read-back of a stored provider key.

    The raw api_key / ciphertext is intentionally absent — only metadata is exposed.
    key_fingerprint is the masked last-4-chars hint (e.g. "••••r4Mk") — safe to show.

    NOTE: created_at / updated_at / last_tested_at are typed as `datetime` so
    Pydantic v2 reads them directly from the SQLAlchemy ORM model (native datetime
    objects) and serialises them to ISO 8601 strings automatically.
    """
    id: str
    provider: str
    key_fingerprint: str
    last_test_ok: Optional[bool] = None
    last_tested_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestConnectionRequest(BaseModel):
    """POST /api/v1/providers/{provider}/test — validate a key without storing it."""
    api_key: str = Field(min_length=1, max_length=512)


class TestConnectionResponse(BaseModel):
    provider: str
    success: bool
    message: str
    latency_ms: Optional[int] = None


# ── Model catalogue ────────────────────────────────────────────────────────

class ModelCatalogEntry(BaseModel):
    id: str
    name: str
    provider: str
    publisher: str
    is_free: bool
    capabilities: list[str]


class ModelCatalogResponse(BaseModel):
    items: list[ModelCatalogEntry]

    @classmethod
    def from_model_infos(cls, infos: list) -> "ModelCatalogResponse":
        return cls(
            items=[
                ModelCatalogEntry(
                    id=m.id,
                    name=m.name,
                    provider=m.provider,
                    publisher=m.publisher,
                    is_free=m.is_free,
                    capabilities=m.capabilities,
                )
                for m in infos
            ]
        )


# ── Research + Notion integration schemas ─────────────────────────────────

class ResearchKeyCreateRequest(BaseModel):
    """POST /api/v1/research/keys — store a Tavily or Anakin key."""
    provider: ResearchProviderSlug
    api_key: str = Field(min_length=1, max_length=512)
    label: Optional[str] = Field(default=None, max_length=128)


class NotionConnectRequest(BaseModel):
    """POST /api/v1/notion/connect — store a Notion OAuth token."""
    access_token: str = Field(min_length=1, max_length=1024)
    workspace_name: Optional[str] = Field(default=None, max_length=128)


class NotionConnectResponse(BaseModel):
    workspace_name: Optional[str] = None
    connected: bool = True
    message: str = "Notion connected successfully."


class OAuthAuthorizeResponse(BaseModel):
    """GET /api/v1/notion/oauth/authorize — return the Notion OAuth URL."""
    auth_url: str


class NotionPublishResponse(BaseModel):
    """POST /api/v1/notion/publish/{session_id} — return the published URL."""
    notion_page_url: str
