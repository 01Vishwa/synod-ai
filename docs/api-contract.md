# Synod API Contract

All routes below are mounted under the `/api/v1` prefix by `app/main.py`, except `/health` and `/readiness`, which are mounted twice: once unprefixed at the root, and once again under `/api/v1` (both `app/main.py` and `app/api/v1/api.py` register the health router). Both `/health` and `/api/v1/health` work identically.

Auth: unless stated otherwise, "Required" means the route depends on `CurrentUserId` (`app/api/v1/deps.py`), which verifies a Supabase JWT (`Authorization: Bearer <token>`, ES256/JWKS) and returns 401 on `missing_token` / `token_expired` / `invalid_audience` / `invalid_issuer` / `invalid_token`.

---

## Health

### GET /health

**Auth:** None
**Request body:** —
**Response:** `{"status": "ok", "version": <str>, "environment": <str>}`
**Errors:** none — always 200 if the process is alive.

### GET /readiness

**Auth:** None
**Request body:** —
**Response:** `{"status": "ready" | "not_ready", "checks": {"database": {"status": "ok", "latency_ms": <float>} | {"status": "error", "detail": "Database unreachable"}}, "version": <str>}`
**Errors:** Returns HTTP 503 (with `"status": "not_ready"`) if a `SELECT 1` against Postgres fails.

---

## Sessions (`sessions.py`)

### POST /sessions

**Auth:** Required
**Request body** (`SessionCreateRequest`):
- `user_query: str` (1–4000 chars)
- `members: list[CouncilMemberConfigSchema]` (3–6 items) — each: `member_id: str` (pattern `^member_[a-z0-9]+$`), `provider: "openrouter" | "nvidia_nim"`, `model_id: str` (1–256 chars; for `nvidia_nim` must start with one of `meta/, nvidia/, mistralai/, google/, microsoft/, deepseek/, qwen/, writer/, baichuan/, aisingapore/, snowflake/, tokyotech-llm/`), `display_label: str` (1–64 chars), `role: "member" | "chairman" = "member"`, `api_key: Optional[str] = None`
- `research_enabled: bool = False`
- `research_provider: Optional["tavily" | "anakin"] = None` (required if `research_enabled`)
- `chairman_member_id: Optional[str] = None` (must reference a member with `role="chairman"`; at most one member may have `role="chairman"`)
- `archive_to_notion: bool = False`

**Response:** `SessionResponse`, HTTP 201 — includes `session_id, stage, user_query, member_count, members, research_enabled, research_provider, stage_1_responses, stage_2_responses, rankings, aggregate_scores, chairman_member_id, final_report_md, citations, total_cost_usd, notion_page_url, trace_url, dashboard_spec, session_status, stage_1_status, stage_2_status, stage_3_status, terminal_error, successful_member_ids, excluded_member_ids, effective_chairman_id, errors, created_at, updated_at`. Session creation commits the initial row, then schedules graph execution as a FastAPI background task (`run_council_graph`) — the response returns immediately with `stage="stage_1"` before any model has answered; poll `GET /sessions/{id}` or use the SSE stream for progress.

**Errors:** 422 (Pydantic validation — bad member count, duplicate/missing chairman, bad NVIDIA model prefix, etc.), 500 `{"code": "session_creation_failed", ...}` on unhandled failure.

### GET /sessions

**Auth:** Required
**Request:** query params `limit: int = 20`, `offset: int = 0`
**Response:** `SessionListResponse` — `{"items": [SessionSummary...], "has_more": bool, "limit": int, "offset": int}`. Each `SessionSummary`: `session_id, stage, user_query, member_count, total_cost_usd, created_at, updated_at, notion_page_url`. `has_more` is a heuristic (`len(items) == limit`), not a real count query.
**Errors:** none beyond auth.

### GET /sessions/{session_id}

**Auth:** Required
**Response:** `SessionResponse` (same shape as POST)
**Errors:** 404 `"Session not found."`

### GET /sessions/{session_id}/stream

**Auth:** Required — via `CurrentUserIdSse`: JWT passed as `?token=<jwt>` query param (checked first) or `Authorization` header.
**Response:** `text/event-stream` (SSE), via `EventSourceResponse`.
**Errors:** 404 `"Session not found."` before the stream opens.

**Behavior:** immediately sends a `state_snapshot` event (full `CouncilState` minus `anonymization_map`, `user_id`, `_execution_status`). Then, if a live event bus exists for the session, streams events until `session.completed` or `session.failed` is received (closing the stream), or the client disconnects. If no live bus exists (session already finished, or graph hasn't started publishing yet), falls back to polling the DB every 5s (up to a 300s idle timeout) and emits a final `state_snapshot` once `stage` reaches `done`/`error`, or a `timeout` event after 300s of no terminal state.

**SSE event types** (`event:` field → payload shape):

| `event:` | Payload fields | When |
|---|---|---|
| `state_snapshot` | Full sanitized `CouncilState` dict | Immediately on connect, and on the DB-polling fallback path once the session reaches a terminal stage |
| `error` | `{"message": "Session not found"}` | Session vanished between the initial load and stream start |
| `timeout` | `{"message": "Stream idle timeout"}` | Fallback-poll path idle for 300s with no terminal stage |
| `member.connecting` | `{member_id}` | Stage 1/2 node, right before calling the provider |
| `member.first_token` | `{member_id, stage}` | Stage 1/2 node, on first streamed delta |
| `member.stream_chunk` | `{member_id, stage, delta, token_count}` | Stage 1/2 node, per streamed delta |
| `member.completed` | `{member_id, stage, latency_ms, tokens_in, tokens_out, cost_usd}` | Stage 1/2 node, on success |
| `member.failed` | `{member_id, stage, error_class, error_message}` | Stage 1/2 node, on key-lookup or provider failure (`error_class` ∈ `timeout`/`auth`/`rate_limit`/`unknown`) |
| `peer_review.started` | `{}` | Before Stage 2 fan-out begins |
| `peer_review.progress` | `{completed, total}` | After each Stage 2 reviewer finishes (success or failure) |
| `chairman.started` | `{chairman_id}` | Start of Stage 3 |
| `chairman.stream_chunk` | `{delta}` | Stage 3, per streamed delta |
| `chairman.completed` | `{}` | Stage 3 success |
| `session.completed` | `{}` | Whole session finished successfully — ends the stream |
| `session.failed` | `{error}` | Stage 3 key-lookup or streaming failure — ends the stream |

All event payloads also carry `session_id` and `event_type` fields (added by the serializer). Three event types are defined in `app/core/event_bus.py` (`member.queued`, `member.started`, `ranking.updated`) but are never published by any orchestration node in the current code — they will not appear on the stream today.

### DELETE /sessions/{session_id}

**Auth:** Required
**Response:** 204, no body (soft delete — sets `is_deleted=True`, row is not physically removed)
**Errors:** 404 `"Session not found."`

---

## Providers (`providers.py`, prefix `/providers`)

### GET /providers

**Auth:** Required
**Response:** `list[ProviderKeyResponse]` — each: `id, provider, key_fingerprint, last_test_ok, last_tested_at, created_at, updated_at`
**Errors:** 503 `{"code": "DATABASE_UNAVAILABLE", ...}`, 500 `{"code": "INTERNAL_ERROR", ...}`

### POST /providers

**Auth:** Required
**Request body** (`ProviderKeyCreateRequest`): `provider: "openrouter" | "nvidia_nim"`, `api_key: str` (1–512 chars), `label: Optional[str]` (≤128 chars)
**Response:** `ProviderKeyResponse`, HTTP 201. The key is validated live against the provider (`adapter.validate_key()`) **before** being encrypted and stored.
**Errors:** 400 `{"code": "UNSUPPORTED_PROVIDER"}`, 400 `{"code": "EMPTY_API_KEY"}`, 401 `{"code": "invalid_api_key"}`, 504 `{"code": "provider_timeout"}`, 502 `{"code": "provider_error"}`, 400 `{"code": "provider_validation_error"}`, 500 `{"code": "ENCRYPTION_FAILED"}`, 409 `{"code": "CONFLICT"}`, 503 `{"code": "DATABASE_UNAVAILABLE"}`, 500 `{"code": "INTERNAL_ERROR"}`

### DELETE /providers/{provider}

**Auth:** Required
**Response:** 204, no body
**Errors:** 404 `"Key not found"`

### POST /providers/{provider}/test

**Auth:** Required
**Request body** (`TestConnectionRequest`): `api_key: str` (1–512 chars)
**Response:** `TestConnectionResponse` — `{provider, success, message, latency_ms}`
**Errors:** 400 (`str(exc)`) if the provider is unsupported.

### GET /providers/{provider}/models

**Auth:** Required
**Response:** `ModelCatalogResponse` — `{items: [{id, name, provider, publisher, is_free, capabilities}]}`. Also updates the stored key's `last_test_ok`/`last_tested_at`/`last_test_error`.
**Errors:** 404 `"No API key configured for '{provider}'. Please add one first."`, 502 (provider error message), 500 `"Failed to fetch model catalog."`

---

## Research (`research.py`, prefix `/research/keys`)

### POST /research/keys

**Auth:** Required
**Request body** (`ResearchKeyCreateRequest`): `provider: "tavily" | "anakin"`, `api_key: str` (1–512 chars), `label: Optional[str]` (≤128 chars)
**Response:** `ProviderKeyResponse`, HTTP 201. **Note:** unlike the LLM providers endpoint, this does not call `adapter.validate_key()` before storing — the key is persisted unconditionally with `last_test_ok=None`.
**Errors:** 400 (`"Unsupported research provider: {provider}"`)

### GET /research/keys

**Auth:** Required
**Response:** `list[ProviderKeyResponse]`
**Errors:** none beyond auth.

### DELETE /research/keys/{provider}

**Auth:** Required
**Response:** 204, no body
**Errors:** 404 `"Key not found"`

### POST /research/keys/{provider}/test

**Auth:** Required
**Request body** (`TestConnectionRequest`): `api_key: str`
**Response:** `TestConnectionResponse`
**Errors:** 400 (`str(exc)`) if the provider is unsupported.

---

## Notion (`notion.py`, prefix `/notion`)

### POST /notion/connect

**Auth:** Required
**Response:** `OAuthAuthorizeResponse` — `{auth_url: str}`
**Errors:** 500 (`str(exc)`)

### GET /notion/oauth/callback

**Auth:** None — this is the OAuth redirect target Notion calls directly (`include_in_schema=False`).
**Request:** query params `code: str`, `state: str`
**Response:** `RedirectResponse` to `{FRONTEND_URL}/settings/integrations?notion=connected` on success, or `{FRONTEND_URL}/settings/integrations?notion_error=<message, ≤200 chars>` on failure (no HTTP error is raised — errors surface as a redirect).

### GET /notion/status

**Auth:** Required
**Response:** `ProviderKeyResponse`
**Errors:** 404 `"Notion is not connected."`

### DELETE /notion/disconnect

**Auth:** Required
**Response:** 204, no body
**Errors:** 404 `"Notion is not connected."`

### POST /notion/publish/{session_id}

**Auth:** Required
**Response:** `NotionPublishResponse` — `{notion_page_url: str}`. On success, updates the session's `notion_page_url` and `archive_status` fields.
**Errors:** 404 `"Session not found."`, 400 `"Session is not complete. Cannot publish yet."` (session `stage != "done"`), 400 `"Notion is not connected. Please connect Notion in settings first."`, 500 (`"Publish failed: {exc}"`)

---

## Observability (`observability.py`, prefix `/observability`)

### GET /observability/trace/{trace_id}/url

**Auth:** None — this route has no user-auth dependency, only a `Tracer` dependency (`LangSmithTracer.instance()`).
**Response:** `{"trace_url": <str>}`
**Errors:** 404 `"Tracing is disabled or trace URL is not available."` if tracing is disabled or the trace ID is unknown.
