# Synod API Contract

This document defines the exact data expectations and API contracts between the Synod frontend (Next.js) and the backend (FastAPI), reflecting the actual implemented endpoints.

---

## 1. Council Sessions (`/api/v1/sessions`)

All session orchestration routes are implemented in `app/api/v1/routers/sessions.py`.

### Create Deliberation Session
* **Endpoint:** `POST /api/v1/sessions`
* **Request Schema (`SessionCreateRequest`):**
  ```json
  {
    "user_query": "What is the training data size of GPT-4o?",
    "members": [
      {
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3-70b-instruct",
        "display_label": "Llama 3 70B",
        "role": "member"
      }
    ],
    "chairman_member_id": "member_xyz",
    "research_enabled": true,
    "research_provider": "tavily",
    "archive_to_notion": false
  }
  ```
* **Response Schema (`SessionResponse`):**
  ```json
  {
    "session_id": "sess_12345678-1234-1234-1234-1234567890ab",
    "user_query": "What is the training data size of GPT-4o?",
    "stage": "stage_1",
    "created_at": "2026-07-16T12:00:00Z",
    "updated_at": "2026-07-16T12:00:00Z",
    "member_count": 1,
    "total_cost_usd": 0.0,
    "notion_page_url": null,
    "trace_id": "trace_12345"
  }
  ```

### List User Sessions
* **Endpoint:** `GET /api/v1/sessions`
* **Response:**
  ```json
  [
    {
      "session_id": "sess_12345678-1234-1234-1234-1234567890ab",
      "user_query": "What is the training data size of GPT-4o?",
      "stage": "done",
      "created_at": "2026-07-16T12:00:00Z",
      "updated_at": "2026-07-16T12:05:00Z",
      "member_count": 1,
      "total_cost_usd": 0.0015,
      "notion_page_url": "https://notion.so/...",
      "trace_id": "trace_12345",
      "headline": "GPT-4o Analysis"
    }
  ]
  ```

### Get Session State
* **Endpoint:** `GET /api/v1/sessions/{session_id}`
* **Response:** Returns the full `CouncilState` JSON snapshot including stage responses, research digests, and current execution stage.

### Stream Progress (SSE)
* **Endpoint:** `GET /api/v1/sessions/{session_id}/stream`
* **Details:** Server-Sent Events (SSE) connection that polls the PostgreSQL database.
* **Events Emitted:**
  - `state_delta`: Incremental updates to `CouncilState` (excludes server-only fields like `anonymization_map` and `user_id`).
  - `dashboard_spec_update`: Updates to the dynamic UI specification blocks (`RankBar`, `MetricCard`, etc.).
  - `done` / `error`: Connection termination signals.

---

## 2. LLM Providers (`/api/v1/providers`)

All LLM provider endpoints are implemented in `app/api/v1/routers/providers.py`.

### List Configured Provider Keys
* **Endpoint:** `GET /api/v1/providers`
* **Response:**
  ```json
  [
    {
      "id": "key_uuid_abc",
      "provider": "openrouter",
      "key_fingerprint": "••••mnop",
      "last_tested_at": "2026-07-16T10:00:00Z",
      "last_test_ok": true,
      "last_test_error": null
    }
  ]
  ```

### Save/Upsert Provider Key
* **Endpoint:** `POST /api/v1/providers`
* **Request Schema (`ProviderKeyCreateRequest`):**
  ```json
  {
    "provider": "openrouter",
    "api_key": "sk-or-v1-..."
  }
  ```
* **Response:** Returns the configured `ProviderKeyResponse` (excluding plaintext API keys).

### Delete Provider Key
* **Endpoint:** `DELETE /api/v1/providers/{provider}`
* **Response:** `204 No Content` on success.

### Test Key Connection
* **Endpoint:** `POST /api/v1/providers/{provider}/test`
* **Request Schema (`TestConnectionRequest`):**
  ```json
  {
    "api_key": "sk-or-v1-..."
  }
  ```
* **Response Schema (`TestConnectionResponse`):**
  ```json
  {
    "provider": "openrouter",
    "success": true,
    "message": "Connection successful.",
    "latency_ms": 142
  }
  ```

### Get Live Model Catalog
* **Endpoint:** `GET /api/v1/providers/{provider}/models`
* **Response Schema (`ModelCatalogResponse`):**
  ```json
  {
    "provider": "openrouter",
    "models": [
      {
        "id": "meta-llama/llama-3-70b-instruct",
        "name": "Llama 3 70B",
        "context_length": 8192,
        "pricing": {
          "prompt": 0.0005,
          "completion": 0.0015
        }
      }
    ]
  }
  ```

---

## 3. Research Providers (`/api/v1/research/keys`)

All research credentials endpoints are implemented in `app/api/v1/routers/research.py`.

### Save/Upsert Research Key
* **Endpoint:** `POST /api/v1/research/keys`
* **Request Schema (`ResearchKeyCreateRequest`):**
  ```json
  {
    "provider": "tavily",
    "api_key": "tvly-...",
    "label": "Primary Tavily Key"
  }
  ```
* **Response:** Returns the saved `ProviderKeyResponse` metadata.

### List Configured Research Keys
* **Endpoint:** `GET /api/v1/research/keys`
* **Response:** List of configured research provider key metadata rows.

### Delete Research Key
* **Endpoint:** `DELETE /api/v1/research/keys/{provider}`
* **Response:** `204 No Content` on success.

### Test Research Connection
* **Endpoint:** `POST /api/v1/research/keys/{provider}/test`
* **Request Schema (`TestConnectionRequest`):**
  ```json
  {
    "api_key": "tvly-..."
  }
  ```
* **Response:** Connection success/failure and roundtrip latency status.

---

## 4. Notion Integration (`/api/v1/notion`)

All Notion OAuth and manual publishing endpoints are implemented in `app/api/v1/routers/notion.py`.

### Connect Notion (OAuth Link Creation)
* **Endpoint:** `POST /api/v1/notion/connect`
* **Response Schema (`OAuthAuthorizeResponse`):**
  ```json
  {
    "auth_url": "https://api.notion.com/v1/oauth/authorize?..."
  }
  ```

### Notion OAuth Callback
* **Endpoint:** `GET /api/v1/notion/oauth/callback`
* **Parameters:** `code` (string), `state` (string)
* **Details:** Invoked by Notion redirection. Exchanges the code for an access token and redirects the browser back to `FRONTEND_URL/settings/integrations?notion=connected`.

### Check Notion Connection Status
* **Endpoint:** `GET /api/v1/notion/status`
* **Response:** Returns connection label, connection metadata, and verification status.

### Disconnect Notion
* **Endpoint:** `DELETE /api/v1/notion/disconnect`
* **Response:** `204 No Content` on success.

### Manual Report Publish
* **Endpoint:** `POST /api/v1/notion/publish/{session_id}`
* **Response Schema (`NotionPublishResponse`):**
  ```json
  {
    "notion_page_url": "https://notion.so/..."
  }
  ```

---

## 5. Observability (`/api/v1/observability`)

Implemented in `app/api/v1/routers/observability.py`.

### Get Observability Trace URL
* **Endpoint:** `GET /api/v1/observability/trace/{trace_id}/url`
* **Response:**
  ```json
  {
    "trace_url": "https://api.smith.langchain.com/o/default/projects/p/synod-ai/traces/..."
  }
  ```
