# Current Progress

This document tracks the actual implementation progress of the Synod platform, strictly derived from codebase analysis.

## ✅ Completed Features

### 1. Hexagonal Backend Architecture
- **Description:** A rigid separation of concerns implementing Ports and Adapters.
- **Current Status:** Completed.
- **Details:** The `app` folder strictly separates `domain`, `orchestration`, `application`, `core`, `adapters`, and `api`. The domain contains pure Python rules (`rules/anonymization.py`, `rules/ranking.py`, `council_state.py`) independent of any I/O framework.

### 2. Secure Supabase JWT Authentication
- **Description:** Verifying JWTs directly from the Supabase JWKS endpoint.
- **Current Status:** Completed.
- **Details:** Implemented in `app/api/v1/deps.py`. It securely decodes ES256 tokens and enforces standard claims, strictly preventing unauthenticated API access.

### 3. Server-Sent Events (SSE) Streaming
- **Description:** Real-time polling to stream session state updates to the frontend.
- **Current Status:** Completed.
- **Details:** Found in `app/api/v1/routers/sessions.py`. The endpoint polls Postgres (`SessionRepository`) every 500ms and yields JSON payloads (`state_delta`, `dashboard_spec_update`) to the Next.js frontend.

### 4. Background Graph Execution
- **Description:** Utilizing LangGraph for multi-stage workflow orchestration.
- **Current Status:** Completed.
- **Details:** FastAPI's `BackgroundTasks` executes `run_council_graph` while returning `201 Created` immediately, preventing timeout issues on long-running LLM inferences.

### 5. Supabase Row-Level Security (RLS) DB Context
- **Description:** Pushing the user identity context into PostgreSQL.
- **Current Status:** Completed.
- **Details:** The backend injects the authenticated JWT sub claim into Postgres configuration limits, enforcing multi-tenant isolation at the database layer.

### 6. Dynamic Generative UI (Json-Render)
- **Description:** Frontend renders components dynamically based on backend specifications.
- **Current Status:** Completed.
- **Details:** Frontend package includes `@json-render/core` and backend creates dashboard specs. 

### 7. Robust Test Suite
- **Description:** Full coverage of unit, integration, and contract tests.
- **Current Status:** Completed.
- **Details:** A comprehensive suite of 96 tests passes successfully (covering schemas, SSE terminal events, database key decryption, stage 1/2 nodes, LangSmith trace finalization, and end-to-end endpoint verification).

## 🚧 Features Currently Under Development / Known Issues

### 1. Database Model Schema Discrepancy
- **Issue:** The `ProviderKeyModel` SQL mapping uses `ciphertext_b64` to store encrypted API keys. However, the Notion and Research routers (`notion.py` and `research.py`) contain code referencing `encrypted_key` and other unmapped attributes (`label`, `is_verified`). 
- **Status:** Requires code alignment to avoid database transaction crashes on Notion and Research key operations.

## ❌ Planned / Missing Features

### 1. Provider Adapter Replacements (GitHub Models Sunset)
- **Why it is needed:** Upstream retirement of GitHub Models.
- **Where it integrates:** `app/adapters/llm_providers`.
- **Implementation priority:** **High**.

### 2. Asynchronous Publish/Subscribe for SSE
- **Why it is needed:** The current 500ms polling interval for SSE causes unnecessary database reads. 
- **Where it integrates:** `app/api/v1/routers/sessions.py` and Postgres models.
- **Implementation priority:** **Medium**. Replacing polling with Postgres LISTEN/NOTIFY would drastically increase efficiency.
