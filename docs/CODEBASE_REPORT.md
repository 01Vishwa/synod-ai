# Synod-AI Codebase Report: End-to-End Architectural & Code Analysis

This document provides a line-by-line and file-by-file end-to-end analysis of the Synod-AI codebase. It details the underlying architectural patterns, security posture, flow of data/control, and visual rendering mechanics.

---

## 1. Executive Summary & Core Paradigm

**Synod-AI** is a multi-agent orchestration platform that processes queries by fanning them out to N independent AI models (Council Members). These models anonymize and review/critique each other's opinions under a strict peer-review protocol, and compile a final, evidence-grounded report using an elected **Chairman** agent. 

### Core Design Goals
1. **Model Diversity & Open Standards:** Allows leveraging multiple inference backends (OpenRouter, NVIDIA NIM, GitHub Models).
2. **Blind Peer Review:** Eliminates brand bias (e.g., model name recognition) by shuffling, anonymizing, and redacting responses during critique stages.
3. **Supervisor Orchestration (LangGraph):** Avoids chatty, unpredictable agent-to-agent loops. The pipeline behaves as a deterministic, state-driven state machine.
4. **Evidence-Grounded Answers:** Incorporates search tools (Tavily, Anakin) to retrieve live research digests before council deliberations.
5. **Bring-Your-Own-Key (BYOK):** Stores API keys securely at rest via AES Fernet encryption.
6. **Full Observability:** Emits traces to LangSmith/Langfuse for monitoring latency, costs, and token consumption.
7. **Generative UI:** Renders rich greyscale dashboard widgets dynamically via `@json-render/core`.

---

## 2. Hexagonal Architecture Map (Ports & Adapters)

Synod-AI implements a strict **Hexagonal Architecture** (also known as Ports and Adapters) in its backend to keep business logic independent of external databases, APIs, frameworks, and user interfaces.

```
                  +---------------------------------------------------+
                  |                 PRESENTATION LAYER                |
                  |     (FastAPI REST Endpoints, SSE Streaming)       |
                  +-------------------------+-------------------------+
                                            |
                                            v
                  +---------------------------------------------------+
                  |           APPLICATION / ORCHESTRATION             |
                  |    (LangGraph State Machine, Background Runner)   |
                  +-------------------------+-------------------------+
                                            |
                                            v
                  +---------------------------------------------------+
                  |                    DOMAIN LAYER                   |
                  | (CouncilState, Anonymization & Borda Ranking Rules)|
                  |                         +                         |
                  |     (Ports / Interfaces: Notion, Provider, etc.)  |
                  +-------------------------+-------------------------+
                                            |
                                            v
                  +---------------------------------------------------+
                  |                  ADAPTERS LAYER                   |
                  | (KeyVault, PostgresRepo, LLMAdapters, Observability)|
                  +---------------------------------------------------+
```

1. **Domain Layer:** Pure Python (no external dependencies like FastAPI, SQLAlchemy, or LangGraph). It contains data schemas (`CouncilState`), algorithmic rules (ranking, anonymization), and abstract base classes representing ports.
2. **Orchestration / Application Layer:** LangGraph workflows that transition `CouncilState` through Stage 1 (First Opinions), Stage 2 (Peer Review), and Stage 3 (Chairman Synthesis).
3. **Presentation Layer:** FastAPI exposing REST API endpoints and Server-Sent Events (SSE) streaming.
4. **Infrastructure / Adapters Layer:** Concrete implementations of database persistence (PostgreSQL/SQLAlchemy), key storage (AES KeyVault), search utilities (Tavily/Anakin), tracing (Langfuse/Langsmith), and third-party integrations (Notion).

---

## 3. Directory and File-by-File Breakdown

### 3.1 Domain Layer (`app/domain`)

*   **[`council_state.py`](file:///d:/synod-ai/app/domain/council_state.py)**
    *   **Role:** The single source of truth for the entire graph state.
    *   **Implementation:** Defines immutable-by-convention `TypedDict` objects. 
        *   `CouncilMemberConfig`: Contains member configurations (`member_id`, `provider`, `model_id`, `display_label`, `role`).
        *   `MemberResponse`: Captures a member's stage outputs, performance telemetry (`latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`), and error records.
        *   `RankingEntry`: Stores Borda ballot rankings (`ranking_order` list of anonymized labels) and justification prose.
        *   `ResearchDigest`: Contains query terms, sources array (`url`, `title`, `snippet`), and an AI-generated summary.
        *   `CouncilState`: Contains identity fields, stage control tags, research details, Stage 1/2 responses, anonymization mapping keys, aggregate scores, and notion metadata.
    *   **Helpers:** `stage_index()` and `is_terminal()` manage control flow transitions.

*   **[`rules/anonymization.py`](file:///d:/synod-ai/app/domain/rules/anonymization.py)**
    *   **Role:** Enforces anonymous peer-review logic.
    *   **Implementation:** Pure, side-effect-free algorithms.
        *   `_generate_labels(n)`: Generates labels "Member A", "Member B", etc.
        *   `build_anonymization_map(...)`: Shuffles the order and maps `member_id` to letters.
        *   `shuffle_responses_for_reviewer(...)`: Custom shuffles response packages for each reviewer so that no two members receive reviews in the same visual order (eliminating position bias).
        *   `redact_identity(text, member_id)`: Uses regular expressions (`_IDENTITY_PATTERNS`) to strip mentions of model brands (e.g., Claude, GPT, Gemini), provider names (e.g., Anthropic, OpenAI), AI assistant disclaimers, or cut-off dates.

*   **[`rules/ranking.py`](file:///d:/synod-ai/app/domain/rules/ranking.py)**
    *   **Role:** Aggregates rankings into scores.
    *   **Implementation:** Implements the Borda Count election method.
        *   `borda_count(...)`: Reverses the anonymization map, scores ballots (higher positions get more points: `(n - 1) - rank_index`), sums them up, and normalizes scores to the range `[0.0, 1.0]`.
        *   `elect_chairman(...)`: Elects the member with the highest Borda count, falling back to Python dictionary insertion order to break ties (unless a user pins a specific chairman).

*   **`ports/`**
    *   **Role:** Establishes standard abstract base classes (interfaces) that infrastructure components must satisfy.
    *   *   **[`provider_adapter.py`](file:///d:/synod-ai/app/domain/ports/provider_adapter.py):** Interface for Chat LLMs.
    *   *   **[`research_adapter.py`](file:///d:/synod-ai/app/domain/ports/research_adapter.py):** Interface for web search tools.
    *   *   **[`notion_port.py`](file:///d:/synod-ai/app/domain/ports/notion_port.py):** Interface for writing pages to Notion workspace.
    *   *   **[`session_repository.py`](file:///d:/synod-ai/app/domain/ports/session_repository.py):** Interface for load, delete, list, and checkpointing.
    *   *   **[`observability_port.py`](file:///d:/synod-ai/app/domain/ports/observability_port.py):** Interface for custom telemetry spans.

---

### 3.2 Orchestration Layer (`app/orchestration`)

*   **[`graph.py`](file:///d:/synod-ai/app/orchestration/graph.py)**
    *   **Role:** Defines the LangGraph state machine.
    *   **Implementation:**
        *   Defines `OrchestratorState` wrapping `CouncilState` with LangGraph's list accumulation reducers (`Annotated[list, operator.add]`).
        *   Wires nodes: `research`, `stage_1_setup`, `stage_1_draft`, `stage_2_setup`, `stage_2_review`, `stage_3_setup`, `stage_3_synthesis`, `dashboard_build_s2`, `dashboard_build_s3`, `archive`, `finish`.
        *   Utilizes conditional routing: `should_research` switches on/off the research pass; `route_stage_1` and `route_stage_2` dynamically fan out concurrent child requests using LangGraph’s `Send` API.

*   **[`runner.py`](file:///d:/synod-ai/app/orchestration/runner.py)**
    *   **Role:** Entrypoint wrapper to launch a graph run.
    *   **Implementation:** `run_council_graph(...)` instantiates request-scoped dependencies (KeyVault, LangSmithTracer, PostgresSessionRepository), configures recursion limits (50), invokes `graph.ainvoke(...)`, captures unexpected crashes, logs error states, and closes traces.

*   **`nodes/`**
    *   **Role:** Discrete tasks executed at state machine steps.
    *   *   **[`research.py`](file:///d:/synod-ai/app/orchestration/nodes/research.py):** Uses the research provider factory to execute queries and record a search summary.
    *   *   **[`stage_1.py`](file:///d:/synod-ai/app/orchestration/nodes/stage_1.py):** Fans out parallel chat prompts to obtain draft responses from each model.
    *   *   **[`stage_2.py`](file:///d:/synod-ai/app/orchestration/nodes/stage_2.py):** Feeds anonymized and redacted Stage 1 responses to members, prompting for rankings wrapped in a `<RANKING>...</RANKING>` block.
    *   *   **[`stage_3.py`](file:///d:/synod-ai/app/orchestration/nodes/stage_3.py):** Triggers the elected Chairman model to synthesize arguments and compile the final report.
    *   *   **[`dashboard_builder_node.py`](file:///d:/synod-ai/app/orchestration/nodes/dashboard_builder_node.py):** Dynamically assembles and validates visual widgets (`RankBar`, `MetricCard`, `TokenTable`, `SourceList`) against Pydantic models.
    *   *   **[`notion_archivist_node.py`](file:///d:/synod-ai/app/orchestration/nodes/notion_archivist_node.py):** Idempotently exports final Markdown reports to Notion via the Notion MCP adapter.

---

### 3.3 Presentation Layer (`app/api`)

*   **[`v1/routers/sessions.py`](file:///d:/synod-ai/app/api/v1/routers/sessions.py)**
    *   **Role:** Exposes session CRUD endpoints and SSE streaming.
    *   **Implementation:**
        *   `POST /sessions`: Initializes `CouncilState`, spins up a Langfuse/Langsmith span trace, commits the record to the database, and schedules `run_council_graph` as a FastAPI background task to return a 201 immediately.
        *   `GET /sessions/{id}/stream`: Exposes an `EventSourceResponse` that polls the database every 500 ms. If it detects a stage change, it emits a `state_delta` event (excluding internal state like `anonymization_map` and `user_id` for security). If the dashboard spec changes, it yields `dashboard_spec_update`. On done or error, it closes with a `done` event.

*   **[`v1/deps.py`](file:///d:/synod-ai/app/api/v1/deps.py)**
    *   **Role:** Handles FastAPI dependency injections.
    *   **Implementation:** Decodes Supabase JWT tokens via `PyJWKClient` using ES256 credentials to enforce Row-Level Security context (`CurrentUserId`), and injects DB repositories.

*   **[`main.py`](file:///d:/synod-ai/app/main.py)**
    *   **Role:** Backend server root.
    *   **Implementation:** Wires routers, sets up global exception handling, and defines middleware (CORS, timing, logging).

---

### 3.4 Infrastructure & Adapters Layer (`app/adapters`)

*   **`llm_providers/`**
    *   **Role:** Implements adapters for the provider interface.
    *   *   **[`openrouter_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/openrouter_adapter.py):** Concrete implementation for OpenRouter REST endpoints, parsing usage statistics and error codes.
    *   *   **[`nvidia_nim_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/nvidia_nim_adapter.py):** Concrete implementation for local/cloud NVIDIA NIM models.
    *   *   **[`github_models_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/github_models_adapter.py):** Adapter targeting GitHub Models (noted for deprecation).
    *   *   **[`factory.py`](file:///d:/synod-ai/app/adapters/llm_providers/factory.py):** Resolves adapter lookups dynamically.

*   **`persistence/`**
    *   **Role:** Handles database storage.
    *   *   **[`models.py`](file:///d:/synod-ai/app/adapters/persistence/models.py):** SQLAlchemy models for database tables:
        *   `council_sessions`: Stores `session_id`, `user_id`, `stage`, denormalized statistics, Notion URLs, trace links, and the full state document as a JSONB payload.
        *   `provider_keys`: Encrypted key mapping.
    *   *   **[`postgres_session_repository.py`](file:///d:/synod-ai/app/adapters/persistence/postgres_session_repository.py):** Handles async operations like loading sessions, listing active user runs, and saving checkpoint states.

*   **[`security/key_vault.py`](file:///d:/synod-ai/app/adapters/security/key_vault.py)**
    *   **Role:** Encryption at rest.
    *   **Implementation:** Fernet AES symmetric encryption. Uses a server-side `ENCRYPTION_KEY` to secure customer keys before they hit Postgres columns.

*   **`observability/`**
    *   **Role:** Pipeline tracing.
    *   *   **[`langsmith_tracer.py`](file:///d:/synod-ai/app/adapters/observability/langsmith_tracer.py):** Manages runs, nested spans, and telemetry logging (latencies, token counts, cost models).

---

### 3.5 Frontend Client (`frontend/`)

*   **[`src/app/sessions/[sessionId]/page.tsx`](file:///d:/synod-ai/frontend/src/app/sessions/%5BsessionId%5D/page.tsx)**
    *   **Role:** Renders active/historic council runs.
    *   **Implementation:** Uses a client-side component displaying headers, cost meters, a stage progress strip, research summaries, and content cards (stage tabs, ranking tables, final reports, and metrics dashboard).

*   **[`src/hooks/useCouncilSession.ts`](file:///d:/synod-ai/frontend/src/hooks/useCouncilSession.ts)**
    *   **Role:** Client-side SSE stream connection hook.
    *   **Implementation:** Connects to `/sessions/{id}/stream`. Listens to incoming event frames to update state, handles network failures with automatic reconnections, and computes running sums of cumulative token consumption and session expenses.

*   **[`src/components/dashboard/registry.tsx`](file:///d:/synod-ai/frontend/src/components/dashboard/registry.tsx)**
    *   **Role:** Visual Generative UI Registry.
    *   **Implementation:** Maps component strings (`MetricCard`, `RankBar`, `LatencyChart`, `CostGauge`, `TokenTable`, `SourceList`) to React visual components. Ensures accessible styling guidelines (e.g., indicating budget overruns via border thickness rather than color).

---

### 3.6 Tooling & Test Suites

*   **[`scripts/check_schema_router_drift.py`](file:///d:/synod-ai/scripts/check_schema_router_drift.py)**
    *   **Role:** Compile-time CI guard script.
    *   **Implementation:** Scans python code for "ghost fields" (attributes deleted or renamed on Pydantic schemas) to prevent runtime failures.

*   **`tests/`**
    *   *   **`unit/`:** Unit tests verifying schema shapes (`test_session_create_request_schema.py`) and widget properties (`test_dashboard_safety.py`).
    *   *   **`integration/`:** Endpoint integration tests (`test_sessions_endpoint.py`).
    *   *   **`contract/`:** Multi-model compatibility checks (`test_member_id_contract.py`).

---

## 4. End-to-End Execution & Data Flow

```
+------------+               +------------+              +---------------+               +-------------------+
|  Frontend  |   HTTP POST   |  FastAPI   |  Spawn Task  |   LangGraph   |  Async Query  |    LLM API /      |
|  Next.js   | ------------> |   Router   | -----------> |    Runner     | ------------> | Research Provider |
+------------+               +------------+              +---------------+               +-------------------+
      ^                            |                            |                                  |
      |                            v                            |                                  |
      |                      Store Initial                      |                                  |
      |                      Session State                      |                                  |
      |                            |                            |                                  |
      |                            v                            |                                  |
      |                      +------------+                     v                                  v
      |                      | PostgreSQL | <------------ Checkpoint Nodes                  Collect Outputs
      |                      |  Database  |               & Error States                           |
      |                      +------------+                     |                                  |
      |                            ^                            |                                  |
      |                            |                            +<---------------------------------+
      |                        DB Polling                       |
      |                        Every 500ms                      v
      |                            |                    Publish Report
      |                            |                            |
      +----------------------------+                            v
                                SSE                          +--------+
                               Stream                        | Notion |
                                                             +--------+
```

### Phase 1: Request Initialization
1. A user triggers a new session by posting a JSON payload to `POST /api/v1/sessions` containing:
    *   `user_query`: "What is the training data size of GPT-4o?"
    *   `members`: A list of selected models.
    *   `research_enabled`: `true` or `false`.
    *   `archive_to_notion`: `true` or `false`.
2. The router queries the user's Supabase authenticated identity, begins a LangSmith tracer run, saves the initial `CouncilState` record to the PostgreSQL database, and launches the execution flow in the background. It returns the session meta to the frontend immediately.

### Phase 2: Live Orchestration Loop
1. **Research Gathering (Optional):** If search is enabled, the `research` node queries Tavily or Anakin, receives source pages, writes a research summary, and appends results to `research_digest`.
2. **First Opinions (Stage 1):** The orchestrator fans out requests. In parallel, `stage_1_node` is sent to each active member with the query and research context. The nodes execute chat queries, collect outputs, record latency and cost statistics, and append these metrics to `stage_1_responses`.
3. **Anonymization & Setup (Stage 2 Setup):** The pipeline transitions to Stage 2. The server shuffles and assigns random identifiers ("Member A", "Member B", etc.) to each model. Prose responses are cleaned of provider-specific signatures and branding.
4. **Peer Review (Stage 2):** Each model receives a uniquely shuffled bundle of the redacted opinions from other members. Models critique and rank these opinions, returning a final ranking enclosed in `<RANKING>` tags.
5. **Dashboard Generation (Post-Stage 2):** The `dashboard_builder_node` reads the collected reviews and performance metadata, computes Borda count scores, constructs dashboard widgets (`RankBar`, `MetricCard`, `TokenTable`), validates them, and writes the resulting `dashboard_spec` to the state.
6. **Chairman Synthesis (Stage 3):** The model with the highest normalized Borda count is elected Chairman. The Chairman receives de-anonymized initial answers along with the corresponding peer reviews and synthesizes them into a final Markdown report.
7. **Final Assembly & Publishing:** The dashboard builder runs again to merge final metrics. If Notion connection metadata is active, the `notion_archivist_node` posts the Markdown compilation directly to the user's connected workspace database.
8. **Completion:** The session stage changes to `done`, final trace data is saved, and the state machine stops.

### Phase 3: Client Streaming
*   While the background graph executes, the frontend Next.js client connects to `GET /sessions/{id}/stream`.
*   The API's SSE generator periodically checks the database and pushes state changes (`state_delta`) and visual dashboard changes (`dashboard_spec_update`) to the client.
*   The client consumes these updates in real-time, displaying live streaming feedback and updating progress bars, cost metrics, and dynamic dashboards as stage checkpoints are written.

---

## 5. Security & Design Patterns Summary

| Pattern / Concept | Description & Implementation |
| :--- | :--- |
| **Hexagonal Separation** | Ensures domain rules (`rules/ranking.py`) remain pure and decoupled from API routing frameworks (`fastapi`) or persistence layers (`sqlalchemy`). |
| **Borda Ranking Strategy** | Normalizes reviews to the range `[0.0, 1.0]`, keeping voting behavior consistent regardless of the size of the council. |
| **Error Isolation** | Captures individual model failures. If a single model times out, the error is recorded, and the council proceeds with the remaining active members instead of halting. |
| **Data Redaction** | Strips model names, training cutoffs, and provider brands during peer-review stages to prevent brand bias. |
| **Bring-Your-Own-Key** | Plaintext API keys are never stored in the database. Credentials are encrypted on ingestion using AES-256 Fernet keys and decrypted in-memory only during model calls. |
| **Generative UI** | Component props generated by the LLM pipeline are validated against Pydantic models before being streamed, preventing schema mismatch issues on the frontend. |
