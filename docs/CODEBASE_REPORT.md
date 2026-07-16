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
                  |           APPLICATION / SERVICE LAYER             |
                  |   (CQRS Commands, Handlers, Notion Services)     |
                  +-------------------------+-------------------------+
                                            |
                                            v
                  +---------------------------------------------------+
                  |                 ORCHESTRATION LAYER               |
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
3. **Application / Service Layer:** Implements commands (`PublishNotionCommand`) and handlers (`PublishHandler`) to publish final reports.
4. **Presentation Layer:** FastAPI exposing REST API endpoints and Server-Sent Events (SSE) streaming.
5. **Infrastructure / Adapters Layer:** Concrete implementations of database persistence (PostgreSQL/SQLAlchemy), key storage (AES KeyVault), search utilities (Tavily/Anakin), tracing (Langfuse/Langsmith), and third-party integrations (Notion via Notion MCP server spawned in a stdio subprocess).

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

### 3.3 Application / Service Layer (`app/application`)

*   **`services/`**
    *   *   **[`notion_service.py`](file:///d:/synod-ai/app/application/services/notion_service.py):** Handles OAuth 2.0 PKCE redirection generation, state storage verification, token exchange, and encapsulates the PublishHandler report generation command.
*   **`commands/`**
    *   *   **[`publish_notion.py`](file:///d:/synod-ai/app/application/commands/publish_notion.py):** Models the `PublishNotionCommand` carrying state, access tokens, and page IDs.
*   **`handlers/`**
    *   *   **[`publish_handler.py`](file:///d:/synod-ai/app/application/handlers/publish_handler.py):** Executes the publishing command, mapping the domain state to Notion blocks using the `NotionPort` adapter.

---

### 3.4 Presentation Layer (`app/api`)

*   **[`v1/routers/sessions.py`](file:///d:/synod-ai/app/api/v1/routers/sessions.py)**
    *   **Role:** Exposes session CRUD endpoints and SSE streaming.
    *   **Implementation:**
        *   `POST /sessions`: Initializes `CouncilState`, spins up a Langfuse/Langsmith span trace, commits the record to the database, and schedules `run_council_graph` as a FastAPI background task.
        *   `GET /sessions/{id}/stream`: Exposes an `EventSourceResponse` that polls the database every 500 ms. If it detects a stage change, it emits a `state_delta` event. If the dashboard spec changes, it yields `dashboard_spec_update`.

---

### 3.5 Infrastructure & Adapters Layer (`app/adapters`)

*   **`llm_providers/`**
    *   *   **[`openrouter_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/openrouter_adapter.py):** Concrete implementation for OpenRouter REST endpoints, parsing usage statistics and error codes.
    *   *   **[`nvidia_nim_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/nvidia_nim_adapter.py):** Concrete implementation for local/cloud NVIDIA NIM models.
    *   *   **[`github_models_adapter.py`](file:///d:/synod-ai/app/adapters/llm_providers/github_models_adapter.py):** Adapter targeting GitHub Models (noted for deprecation).

*   **`notion/`**
    *   *   **[`notion_mcp_adapter.py`](file:///d:/synod-ai/app/adapters/notion/notion_mcp_adapter.py):** Implements `NotionPort` by spawning the official Notion MCP server (`@notionhq/notion-mcp-server`) as a stdio subprocess via `npx` and calling `create_page` and `append_block_children`.

*   **`persistence/`**
    *   *   **[`models.py`](file:///d:/synod-ai/app/adapters/persistence/models.py):** SQLAlchemy models:
        *   `council_sessions`: Stores `session_id`, `user_id`, `stage`, denormalized statistics, Notion URLs, trace links, and the full state document as a JSONB payload.
        *   `provider_keys`: Encrypted key mapping. Declares `ciphertext_b64` for storing the encrypted API key.
        *   *Warning/Discrepancy:* Custom routers `notion.py` and `research.py` try to set and access `encrypted_key`, `label`, and `is_verified` properties on the `ProviderKeyModel` class, which are not mapped columns on the class definition.

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
1. A user triggers a new session by posting a JSON payload to `POST /api/v1/sessions`.
2. The router queries the user's Supabase authenticated identity, begins a LangSmith/Langfuse tracer run, saves the initial `CouncilState` record to the PostgreSQL database, and launches the execution flow in the background. It returns the session meta to the frontend immediately.

### Phase 2: Live Orchestration Loop
1. **Research Gathering (Optional):** If search is enabled, the `research` node queries Tavily or Anakin.
2. **First Opinions (Stage 1):** The orchestrator fans out requests. In parallel, `stage_1_node` obtains draft responses from each model.
3. **Anonymization & Setup (Stage 2 Setup):** The pipeline transitions to Stage 2. The server shuffles and assigns random identifiers ("Member A", "Member B", etc.) to each model. Prose responses are cleaned of provider-specific signatures and branding.
4. **Peer Review (Stage 2):** Each model receives a uniquely shuffled bundle of the redacted opinions from other members. Models critique and rank these opinions.
5. **Dashboard Generation (Post-Stage 2):** The `dashboard_builder_node` reads the collected reviews and performance metadata, computes Borda count scores, constructs dashboard widgets (`RankBar`, `MetricCard`, `TokenTable`), and writes the resulting `dashboard_spec` to the state.
6. **Chairman Synthesis (Stage 3):** The model with the highest normalized Borda count is elected Chairman and synthesizes them into a final Markdown report.
7. **Final Assembly & Publishing:** The dashboard builder runs again to merge final metrics. If Notion connection metadata is active, the `notion_archivist_node` posts the Markdown compilation to Notion by spawning the Notion MCP server.
8. **Completion:** The session stage changes to `done`, final trace data is saved, and the state machine stops.

### Phase 3: Client Streaming
*   While the background graph executes, the frontend Next.js client connects to `GET /api/v1/sessions/{id}/stream`.
*   The API's SSE generator periodically checks the database and pushes state changes (`state_delta`) and visual dashboard changes (`dashboard_spec_update`) to the client.
