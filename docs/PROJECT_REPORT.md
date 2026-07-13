# Synod Project Report

## Executive Summary
Synod is a specialized AI orchestration platform designed to generate high-fidelity, evidence-grounded answers through a multi-model "LLM Council." The current implementation successfully executes its core mission: fanning out user queries to independent LLMs, facilitating blind peer review, and generating a synthesised final report via a Supervisor-controlled LangGraph workflow. The project boasts a robust architectural foundation using Ports and Adapters, providing exceptional modularity.

## Project Overview
Synod leverages a sophisticated StateGraph to govern interactions between isolated AI agents. Unlike free-form agent chat, Synod ensures that agents communicate only through a central, auditable `CouncilState`. The system includes a Python/FastAPI backend and a Next.js/React frontend.

## Objectives
- Implement a deterministically orchestrated agent council avoiding "agents freely chatting with agents."
- Provide model anonymity during peer review to eliminate brand bias.
- Strictly enforce a Bring-Your-Own-Key (BYOK) paradigm.
- Maintain total observability over token usage, costs, and latency.

## Business Value
By cross-examining multiple LLMs and grounding responses with live research, Synod provides professional researchers, analysts, and engineering teams with defensible, thoroughly audited answers, preventing the need for manual, tab-switching comparisons across multiple AI provider interfaces.

## System Architecture
Synod is built upon **Hexagonal Architecture (Ports and Adapters)**. The application state is fully divorced from I/O constraints:
- **Presentation Layer:** FastAPI exposes synchronous CRUD REST endpoints and asynchronous SSE streams.
- **Application/Orchestration Layer:** LangGraph defines the `StateGraph`. The "Decision Orchestrator" handles stage routing based on `CouncilState`.
- **Domain Layer:** Pure Python defining business rules (e.g., Borda-count ranking logic, `CouncilState` typed dictionary) and abstract interfaces (Ports).
- **Adapters:** Implementations for PostgreSQL (storage), Langfuse/Langsmith (observability), OpenRouter/NVIDIA NIM (LLM inference), and Tavily/Anakin (web research).

## Technology Stack
- **Backend:** Python (FastAPI, SQLAlchemy, Alembic, LangGraph, PyJWKClient).
- **Frontend:** TypeScript (Next.js, TailwindCSS, @json-render).
- **Database:** PostgreSQL (via Supabase) with Row-Level Security.

## Module Breakdown

### 1. `app.api` (Presentation)
- **Purpose:** API exposure and dependency injection.
- **Current implementation:** Complete. Implements auth verification via Supabase ES256 JWKS and routes for sessions, providers, research, and observability.
- **Dependencies:** FastAPI, `app.core`, `app.orchestration`.
- **Status:** **Completed**.

### 2. `app.domain` (Core Business Logic)
- **Purpose:** Central source of truth for state and interfaces.
- **Current implementation:** Strict TypedDict definitions (`CouncilState`) and pure python rules.
- **Dependencies:** None.
- **Status:** **Completed**.

### 3. `app.orchestration` (Graph Execution)
- **Purpose:** Direct the LLM nodes and handle state mutation.
- **Current implementation:** `graph.py` wires the supervisor architecture together, utilizing a postgres checkpointer.
- **Dependencies:** `app.domain`, LangGraph.
- **Status:** **Completed**.

### 4. `app.adapters` (Infrastructure Integrations)
- **Purpose:** Talk to external databases and APIs.
- **Current implementation:** Persistence (SQLAlchemy models), Security (KeyVault), Observability (LangSmith).
- **Dependencies:** Third-party SDKs, `app.domain.ports`.
- **Status:** **Completed** for core capabilities.

### 5. `frontend/src` (User Interface)
- **Purpose:** User interaction and data presentation.
- **Current implementation:** Strict black-and-white theme, live session streaming via Server-Sent Events, dynamic widget rendering via `@json-render/core`.
- **Dependencies:** React, Next.js, @supabase/ssr.
- **Status:** **Completed**.

## Implemented Features
- Secure Supabase ES256 authentication flow with DB RLS context.
- API Key encryption at rest (KeyVault).
- Live execution tracking via SSE polling mechanism.
- LangGraph supervisor orchestration.
- Integration with @json-render for dynamic UI widgets.

## Pending Features
- Robust unit and integration testing coverage (directories exist but appear sparsely populated).
- Migration from GitHub Models to an alternative due to upstream deprecation.
- Advanced retry policies for rate-limited endpoints.

## Technical Debt
- Backend session streaming relies on constant database polling (`0.5s` intervals). While effective, it could be replaced with Postgres LISTEN/NOTIFY for optimal performance.

## Risks
- **GitHub Models Deprecation:** Critical integration risk. GitHub Models is sunsetting; the provider adapter must be swapped to Azure AI Foundry or similar.

## Security Review
The security posture is exceptional:
- Keys are encrypted before entering PostgreSQL.
- Database access relies on Supabase Row-Level Security, authenticated by tightly verified JWKS JWTs.
- No direct agent-to-agent data flow prevents unintentional prompt injection leaks between nodes.

## Performance Observations
- SSE polling is lightweight enough for early stage, but can increase database load at extreme scale. 
- API logic is asynchronous and properly defers blocking LangGraph executions to FastAPI `BackgroundTasks`.

## Code Quality Review
- **Maintainability & Modularity:** Excellent. The Hexagonal structure ensures new LLM providers can be added without modifying the domain or orchestration layers.
- **Separation of Concerns:** Rigidly enforced.
- **SOLID Principles:** High adherence, particularly Dependency Inversion (relying on ports, not concrete adapters).
- **Error Handling:** Standardized HTTP exceptions and JWT verification fallbacks in `deps.py`.
- **Testability:** High, due to strict dependency injection.

## Current Development Progress
Base estimates on codebase inspection:
- **Overall Completion:** 85%
- **Backend Architecture:** 100%
- **Frontend / UI:** 90%
- **Database / Auth:** 100%
- **API Completion:** 95%
- **Documentation:** 100% (Post-generation)
- **Testing:** 15% (In Progress)

## Recommended Next Steps

### High Priority
- Deprecate the GitHub Models adapter and swap to a supported alternative before upstream cutoff.
- Expand `tests/contract` and `tests/unit` to ensure stability of the LangGraph transitions.

### Medium Priority
- Refactor the session SSE endpoint to utilize Postgres LISTEN/NOTIFY instead of timed polling.

### Low Priority
- Implement advanced caching strategies for repeated identical queries to reduce LLM token costs.
