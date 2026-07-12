"""
core/exceptions.py — Application exception hierarchy + global FastAPI handlers.

Design:
  - AppException is the base for all domain / application errors. It carries a
    machine-readable `error_code`, a human-readable `message`, and an optional
    `details` dict — so the frontend can react to specific codes without parsing
    strings.
  - Concrete sub-classes map 1-to-1 with HTTP semantics (404, 409, 422, 429…).
  - setup_exception_handlers() wires all handlers into the FastAPI app via the
    standard exception_handler decorator — zero magic, fully observable.

Pattern: Chain of Responsibility (handlers are registered in priority order;
         FastAPI picks the most specific match first).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ── Base domain exception ──────────────────────────────────────────────────

class AppException(Exception):
    """
    Base class for all Synod application exceptions.

    Attributes:
        error_code: snake_case identifier for client-side branching.
        message:    Human-readable description.
        details:    Optional structured context (field errors, resource IDs…).
        status_code: HTTP status that should be returned.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "internal_error",
        details: dict[str, Any] | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code


# ── Concrete exception types ───────────────────────────────────────────────

class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="not_found",
            details=details,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "Resource already exists", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="conflict",
            details=details,
            status_code=status.HTTP_409_CONFLICT,
        )


class DomainValidationError(AppException):
    def __init__(self, message: str = "Validation error", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="validation_error",
            details=details,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Authentication required", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="unauthorized",
            details=details,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Insufficient permissions", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="forbidden",
            details=details,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class RateLimitError(AppException):
    def __init__(self, message: str = "Rate limit exceeded", details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="rate_limit_exceeded",
            details=details,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ProviderError(AppException):
    """Raised when an external LLM / research provider call fails."""
    def __init__(self, message: str, provider: str, details: dict | None = None) -> None:
        super().__init__(
            message=message,
            error_code="provider_error",
            details={"provider": provider, **(details or {})},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class CircuitOpenError(AppException):
    """Raised by the Circuit Breaker when a provider is in OPEN state."""
    def __init__(self, provider: str) -> None:
        super().__init__(
            message=f"Provider '{provider}' is temporarily unavailable (circuit open).",
            error_code="circuit_open",
            details={"provider": provider},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SessionError(AppException):
    """Raised for invalid council session state transitions."""
    def __init__(self, message: str, session_id: str | None = None) -> None:
        super().__init__(
            message=message,
            error_code="session_error",
            details={"session_id": session_id} if session_id else {},
            status_code=status.HTTP_409_CONFLICT,
        )


# ── Response helper ────────────────────────────────────────────────────────

def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a consistent error envelope for all exception handlers."""
    body: dict[str, Any] = {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
        }
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body)


# ── Handler registration ───────────────────────────────────────────────────

def setup_exception_handlers(app: FastAPI) -> None:
    """
    Register all global exception handlers on the FastAPI application.

    Handlers are tried most-specific first (FastAPI convention):
        AppException subtypes → AppException → StarletteHTTPException
        → RequestValidationError → Exception (catch-all)
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        if exc.status_code >= 500:
            logger.error(
                "AppException: %s — %s",
                exc.error_code,
                exc.message,
                extra={"request_id": request_id},
                exc_info=True,
            )
        else:
            logger.warning(
                "AppException: %s — %s",
                exc.error_code,
                exc.message,
                extra={"request_id": request_id},
            )
        return _error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "HTTP %s: %s",
            exc.status_code,
            exc.detail,
            extra={"request_id": request_id},
        )
        return _error_response(
            status_code=exc.status_code,
            error_code="http_error",
            message=str(exc.detail),
            request_id=request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "Request validation failed",
            extra={"request_id": request_id},
        )
        # Flatten Pydantic v2 error list into a field→messages dict
        field_errors: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = " → ".join(str(p) for p in err.get("loc", []))
            field_errors.setdefault(loc, []).append(err["msg"])
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="validation_error",
            message="Request validation failed.",
            details={"fields": field_errors},
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.critical(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            extra={"request_id": request_id},
            exc_info=True,
        )
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_error",
            message="An unexpected error occurred. Please try again later.",
            request_id=request_id,
        )
