# Synod API Contract

This document defines the exact data expectations between the Synod frontend (Next.js) and the backend (FastAPI), ensuring no unresolved mock-data assumptions exist in the frontend UI.

## Council Sessions (`/`, `/sessions/[id]`, `/history`)

### New Council: Load models for a provider
**Frontend Action:** User selects a provider (e.g., OpenRouter) from the dropdown.
→ `GET /api/v1/providers/{provider}/models`
**Request:** None
**Response:**
```json
[
  {
    "id": "meta-llama/llama-3-70b-instruct",
    "name": "Llama 3 70B",
    "context_length": 8192,
    "pricing": { "prompt": 0.0005, "completion": 0.0015 }
  }
]
```

### New Council: Start Council
**Frontend Action:** User clicks "Convene Council".
→ `POST /api/v1/council/sessions`
**Request:**
```json
{
  "user_query": "What are the long-term impacts of AGI?",
  "members": [
    { "provider": "openrouter", "model_id": "meta-llama/llama-3-70b", "display_label": "Llama 3" }
  ],
  "chairman_member_id": "member_xyz",
  "research_enabled": true,
  "research_provider": "tavily",
  "archive_to_notion": true
}
```
**Response:** `CouncilState` object (initial state).

### Live Session: Load State
**Frontend Action:** User opens a session link or refreshes the page.
→ `GET /api/v1/council/sessions/{id}`
**Request:** None
**Response:** `CouncilState` object containing all historical stage responses, member data, and current stage.

### Live Session: Stream Progress
**Frontend Action:** Hook `useCouncilSession` subscribes for live deltas.
→ `GET /api/v1/council/sessions/{id}/stream`
**Request:** None
**Response:** Server-Sent Events (SSE) streaming incremental `CouncilState` updates.

### Session History: Load Sessions
**Frontend Action:** User navigates to `/history`.
→ `GET /api/v1/council/sessions`
**Request:** None
**Response:**
```json
[
  {
    "session_id": "sess_123",
    "user_query": "What are the long-term impacts of AGI?",
    "stage": "done",
    "created_at": "2026-07-12T10:00:00Z",
    "updated_at": "2026-07-12T10:05:00Z",
    "member_count": 3,
    "total_cost_usd": 0.015,
    "notion_page_url": "https://notion.so/...",
    "trace_id": "trace_abc",
    "headline": "Analysis of AGI Impacts"
  }
]
```


## Settings: Providers (`/settings/providers`)

### Providers: Load Configured Status
**Frontend Action:** Check which LLM providers have API keys set.
→ `GET /api/v1/providers/configured`
**Request:** None
**Response:**
```json
[
  { "provider": "openrouter", "configured": true },
  { "provider": "nvidia_nim", "configured": false },
  { "provider": "github_models", "configured": false }
]
```

### Providers: Save API Key
**Frontend Action:** User inputs API key for a provider.
→ `POST /api/v1/providers/keys`
**Request:**
```json
{
  "provider": "openrouter",
  "api_key": "sk-or-v1-..."
}
```
**Response:** `{ "ok": true }`

### Providers: Test Connection
**Frontend Action:** User clicks "Test Connection".
→ `POST /api/v1/providers/test`
**Request:**
```json
{ "provider": "openrouter" }
```
**Response:**
```json
{
  "success": true,
  "message": "Successfully authenticated.",
  "latency_ms": 150
}
```


## Settings: Integrations (`/settings/integrations`)

### Integrations: Load Configured Status
**Frontend Action:** (Resolves frontend mock logic in `fetchStatus()`) Load which integrations (Tavily, Anakin, Notion) are configured.
→ `GET /api/v1/integrations/status`
**Request:** None
**Response:**
```json
{
  "research": { "tavily": true, "anakin": false },
  "notion": { "connected": false },
  "langfuse": { "connected": true }
}
```

### Integrations: Save Research API Key
**Frontend Action:** User saves a Tavily or Anakin API key.
→ `POST /api/v1/integrations/research/{provider}/keys`
**Request:**
```json
{ "api_key": "tvly-..." }
```
**Response:** `{ "ok": true }`

### Integrations: Test Research Connection
**Frontend Action:** User tests Tavily or Anakin connection.
→ `POST /api/v1/integrations/research/test`
**Request:**
```json
{ "provider": "tavily" }
```
**Response:**
```json
{
  "success": true,
  "message": "Connection successful.",
  "latency_ms": 120
}
```

### Integrations: Connect Notion
**Frontend Action:** User initiates Notion OAuth flow.
→ `POST /api/v1/integrations/notion/connect`
**Request:** None
**Response:**
```json
{ "auth_url": "https://api.notion.com/v1/oauth/authorize?..." }
```

### Integrations: Publish to Notion (Manual/Retry)
**Frontend Action:** (Optional) User wants to retry publishing a past session.
→ `POST /api/v1/integrations/notion/publish/{id}`
**Request:** None
**Response:**
```json
{ "notion_page_url": "https://notion.so/..." }
```

### Integrations: Save Langfuse Keys
**Frontend Action:** User enters Langfuse keys.
→ `POST /api/v1/integrations/langfuse/keys`
**Request:**
```json
{
  "public_key": "pk-lf-...",
  "secret_key": "sk-lf-...",
  "host": "https://us.langfuse.com"
}
```
**Response:** `{ "ok": true }`
