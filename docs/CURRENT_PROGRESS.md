# Current Progress

This document tracks the actual implementation progress of the Synod platform, strictly derived from codebase analysis.

## ✅ Completed Features

### 1. Hexagonal Backend Architecture
- **Description:** A rigid separation of concerns implementing Ports and Adapters.
- **Current Status:** Completed.
- **Details:** The `app` folder strictly separates `domain`, `orchestration`, `adapters`, and `api`. The domain contains pure Python rules (`council_state.py`) independent of any I/O framework.

### 2. Secure Supabase JWT Authentication
- **Description:** Verifying JWTs directly from the Supabase JWKS endpoint.
- **Current Status:** Completed.
- **Details:** Implemented in `deps.py`. It securely decodes ES256 tokens and enforces standard claims (`sub`, `iss`, `aud`), strictly preventing unauthenticated API access.

### 3. Server-Sent Events (SSE) Streaming
- **Description:** Real-time polling to stream session state updates to the frontend.
- **Current Status:** Completed.
- **Details:** Found in `sessions.py`. The endpoint polls Postgres (`SessionRepository`) every 500ms and yields JSON payloads (`state_delta`, `dashboard_spec_update`) to the Next.js frontend.

### 4. Background Graph Execution
- **Description:** Utilizing LangGraph for multi-stage workflow orchestration.
- **Current Status:** Completed.
- **Details:** FastAPI's `BackgroundTasks` executes `run_council_graph` while returning `201 Created` immediately, preventing timeout issues on long-running LLM inferences.

### 5. Supabase Row-Level Security (RLS) DB Context
- **Description:** Pushing the user identity context into PostgreSQL.
- **Current Status:** Completed.
- **Details:** The `set_rls_context` dependency injects the JWT sub claim into Postgres configuration limits, enforcing multi-tenant isolation at the database layer.

### 6. Dynamic Generative UI (Json-Render)
- **Description:** Frontend renders components dynamically based on backend specifications.
- **Current Status:** Completed.
- **Details:** Frontend package includes `@json-render/core` and backend creates dashboard specs. 

## 🚧 Features Currently Under Development

### 1. Robust Contract & Unit Testing
- **What's completed:** Directories established (`tests/unit`, `tests/contract`, `tests/integration`). Basic dashboard safety test exists.
- **What's missing:** Thorough coverage of all API routes, graph transitions, and adapter logic.
- **What remains:** Comprehensive mocking of the LLM responses for test suites.

## ❌ Planned / Missing Features

### 1. Provider Adapter Replacements (GitHub Models Sunset)
- **Why it is needed:** Upstream retirement of GitHub Models.
- **Where it integrates:** `app/adapters/llm_providers`.
- **Implementation priority:** **High**. Must be addressed immediately to ensure three functional providers are maintained.

### 2. Asynchronous Publish/Subscribe for SSE
- **Why it is needed:** The current 500ms polling interval for SSE causes unnecessary database reads. 
- **Where it integrates:** `app/api/v1/routers/sessions.py` and Postgres models.
- **Implementation priority:** **Medium**. Replacing polling with Postgres LISTEN/NOTIFY would drastically increase efficiency.
