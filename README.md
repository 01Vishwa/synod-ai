# Synod-Ai - *Where Models Convene, Truth Concludes.*

## Project Description
Synod is a supervisor-orchestrated council of independent AI models that debate, critique, and rank each other's answers — anonymously — before a designated Chairman agent synthesizes the strongest, most defensible response to your question. Instead of blindly trusting a single LLM, Synod fans your query out to a diverse panel, enforces blind peer review, and yields a single evidence-grounded final answer.

## Project Goals
- **Model Diversity:** Leverage independent reasoning from OpenRouter, NVIDIA NIM, and GitHub Models.
- **Blind Peer Review:** Prevent model "brand bias" by anonymously ranking each other's answers.
- **Supervisor Control:** Ensure a strict, predictable state machine instead of unpredictable agent-to-agent chat.
- **Evidence Over Eloquence:** Ground answers using live web research integrations (Tavily/Anakin).
- **Security & Privacy:** Bring-your-own-keys (BYOK) stored securely at rest via AES encryption, linked only to your user identity via Supabase.
- **Full Observability:** Provide end-to-end tracing of all model latency, token counts, and cost via Langfuse.

## Key Features
- **Multi-Model Deliberation:** Send one prompt, receive N*N parallel opinions.
- **Anonymized Ranking:** Models rank each other purely on merit, not model name.
- **Chairman Synthesis:** A designated top-performing model synthesizes a final conclusion.
- **Strict Role-Based Architecture:** Uses LangGraph's Supervisor pattern; models never talk directly to one another.
- **Dynamic Data UI:** Black & white generative UI components stream via `@json-render/core`.
- **Zero Platform Lock-In:** Configurable API Keys for LLM inference (OpenRouter, NVIDIA NIM, GitHub Models) and Research (Tavily, Anakin).

## Current Status
**In Development** The backend orchestration (LangGraph, FastAPI) and core domain (ports/adapters) are implemented. Session polling, RLS with Supabase JWTs, and secure KeyVault storage are complete. The frontend (Next.js) session dashboards, history screens, and settings panels are implemented and functionally consuming SSE deltas. 

## Architecture Overview
Synod utilizes **Hexagonal Architecture (Ports and Adapters)** for the backend:
- **Presentation:** FastAPI routers (REST/SSE).
- **Orchestration:** LangGraph `StateGraph` supervisor.
- **Domain:** Pure Python `CouncilState`, ranking rules, and ABC Ports.
- **Adapters:** Concrete implementations (OpenRouter, Tavily, Langfuse, Postgres).
The entire workflow is state-driven rather than conversational.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, LangGraph, SQLAlchemy (Async), PyJWKClient.
- **Frontend:** Next.js 14, React, TailwindCSS, @json-render.
- **Database:** PostgreSQL (Supabase) with Row-Level Security (RLS).
- **Observability:** Langfuse, LangSmith (configurable).

## Project Structure
```
synod-ai/
├── app/                  # Backend Hexagonal Architecture
│   ├── api/              # FastAPI Routers & Dependencies
│   ├── domain/           # Pure Python state & business rules
│   ├── orchestration/    # LangGraph StateGraph nodes
│   └── adapters/         # DB, Provider SDKs, Tracing implementations
├── frontend/             # Next.js Application
│   ├── src/app/          # App Router pages (sessions, history, settings)
│   ├── src/components/   # B&W UI Components & json-render registry
│   └── src/lib/          # API Clients and SSE hooks
```

## Prerequisites
- **Node.js:** v18 or later.
- **Python:** 3.11 or later.
- **PostgreSQL:** (Or a Supabase project).
- **API Keys:** Provide your own OpenRouter/NVIDIA NIM and Tavily keys for full functionality.

## Installation Guide
For a full installation guide, please refer to [INSTALLATION_GUIDE.md](docs/INSTALLATION_GUIDE.md).

## Running the Project
### Development Mode
1. **Backend:** Run the FastAPI server using `uvicorn app.main:app --reload`.
2. **Frontend:** Run the Next.js server using `npm run dev` in the `frontend/` directory.

### Production Build
1. Build the Next.js frontend: `npm run build` followed by `npm start`.
2. Deploy the backend as a containerized service (Dockerfile included).

## Database Setup & Authentication Setup
Synod uses PostgreSQL. Migrations are managed via Alembic (`alembic upgrade head`). Authentication is fully delegated to Supabase via ES256 JWKS; the backend API inherently relies on a `Bearer` token signed by the Supabase project. Setup RLS natively in your Supabase dashboard.

## API Overview
- `POST /api/v1/sessions` - Create a deliberation session.
- `GET /api/v1/sessions/{id}/stream` - SSE endpoint for live LangGraph updates.
- `POST /api/v1/providers/{provider}/test` - Test LLM connection credentials.

## Scripts
See `package.json` and `pyproject.toml` for standard npm and Python scripts (e.g. `npm run dev`, `npm run lint`).

## Deployment Guide
1. Host the Next.js frontend on Vercel or your preferred Node provider.
2. Host the FastAPI backend on a capable container service (e.g. AWS Fargate, Render).
3. Connect both to a managed Supabase Postgres instance. 

## Known Limitations
- Single-operator sessions only (no real-time multi-user editing).
- Text-only queries (no multimodal support in v1).
- GitHub Models integration is slated for deprecation by Microsoft/GitHub.
