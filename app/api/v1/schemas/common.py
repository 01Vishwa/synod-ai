"""
api/v1/schemas/common.py — Shared Pydantic response envelope types.

Every API response wraps its payload in a consistent envelope so the frontend
can always rely on the same top-level shape regardless of endpoint.

Pattern: Value Object (immutable response shapes), consistent error contract.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Machine-readable error detail included in every error response."""
    code: str = Field(description="snake_case error identifier for client branching")
    message: str = Field(description="Human-readable error description")
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard error envelope — matches setup_exception_handlers output."""
    error: ErrorDetail
    request_id: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "not_found",
                    "message": "Session 'abc-123' not found.",
                    "details": {"session_id": "abc-123"},
                },
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list wrapper."""
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total


class MessageResponse(BaseModel):
    """Simple acknowledgement response for fire-and-forget operations."""
    message: str
    success: bool = True
