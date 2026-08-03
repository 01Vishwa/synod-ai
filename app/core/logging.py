"""
core/logging.py — Structured JSON logging + request-lifecycle middleware.

Design choices:
  - JSONFormatter: every log line is a valid JSON object so log aggregators
    (Datadog, CloudWatch, Supabase Logflare) can parse fields without regex.
  - LoggingMiddleware: attaches a UUID request-id to every request, captures
    method, path, status, latency, and propagates exc_info on 5xx.
  - setup_logging() is idempotent — safe to call multiple times (e.g. in tests).

Pattern: Decorator (middleware wraps call_next), Observer (middleware emits
structured events for every request transition).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


# ── JSON formatter ─────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """
    Renders log records as single-line JSON objects.

    Standard fields:
        timestamp, level, logger, message

    Optional context fields (injected by middleware / LoggerAdapter):
        request_id, method, path, status_code, latency_ms

    Error fields (added automatically when exc_info is present):
        exc_info
    """

    _ALWAYS: tuple[str, ...] = ("timestamp", "level", "logger", "message")

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        log_obj: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Context fields — added by LoggerAdapter or direct extra= kwarg
        for field in ("request_id", "method", "path", "status_code", "latency_ms"):
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)

        # Full stack trace for any error-level record
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


# ── Logging bootstrap ──────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger with a JSON handler.

    - Idempotent: clears existing handlers before adding ours so multiple
      calls (e.g. in tests) don't double-emit every line.
    - Forces uvicorn's access / error loggers to propagate so they also
      emit JSON through our single handler.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any pre-existing handlers (avoids double output)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONFormatter())
    root.addHandler(stream_handler)

    # Let uvicorn / fastapi / sqlalchemy logs flow through our root handler
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy.engine"):
        log = logging.getLogger(name)
        log.handlers = []
        log.propagate = True


# ── Request-lifecycle middleware ───────────────────────────────────────────

class LoggingMiddleware:
    """
    Pure ASGI middleware (no BaseHTTPMiddleware) so SSE / streaming responses
    are not buffered in memory.

    Attaches a UUID request-id, logs method/path/status/latency on completion,
    and injects X-Request-ID into response headers.
    """

    _LOGGER_NAME = "synod.api"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        adapter = logging.LoggerAdapter(
            logging.getLogger(self._LOGGER_NAME),
            extra={"request_id": request_id},
        )

        method = request.method
        path = request.url.path
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            adapter.info(
                "%s %s → %s (%.1fms)",
                method,
                path,
                status_code,
                elapsed_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": elapsed_ms,
                },
            )
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            adapter.error(
                "%s %s → 500 (%.1fms) — unhandled exception",
                method,
                path,
                elapsed_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "latency_ms": elapsed_ms,
                },
                exc_info=True,
            )
            raise
