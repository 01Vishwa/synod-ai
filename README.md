# Synod-Ai - *Where Models Convene, Truth Concludes.*

## Project Description
Synod is a supervisor-orchestrated council of independent AI models that debate, critique, and rank each other's answers — anonymously — before a designated Chairman agent synthesizes the strongest, most defensible response to your question. Instead of blindly trusting a single LLM, Synod fans your query out to a diverse panel, enforces blind peer review, and yields a single evidence-grounded final answer.

## Problem Statement
Standard single-LLM queries are susceptible to brand-specific biases, hallucination loops, and lack of rigorous peer critique. Existing multi-agent frameworks often allow unstructured, conversational loops that lead to agent drift and high token consumption. Synod-AI solves this by implementing a structured, deterministic state machine workflow utilizing LangGraph.

## Key Features
- **Multi-Model Deliberation:** Send one prompt, receive parallel opinions from multiple models.
- **Anonymized Ranking:** Models rank each other's answers anonymously based on merit preventing model name/brand bias.
- **Chairman Synthesis:** The highest-ranked model is elected as Chairman to synthesize the final evidence-grounded response.
- **Strict Role-Based Architecture:** Uses LangGraph's Supervisor pattern; models never talk directly to one another.
- **Dynamic Data UI:** Black-and-white generative UI components stream dynamically via `@json-render/core`.
- **Bring-Your-Own-Keys (BYOK):** API keys are encrypted at rest using AES-256 Fernet encryption and stored in PostgreSQL.
- **Full Observability:** End-to-end tracing of node executions, latency, token consumption, and cost via Langfuse/LangSmith.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, LangGraph, SQLAlchemy (Async), Alembic, PyJWT.
- **Frontend:** Next.js 14, React 18, TailwindCSS, @json-render/core.
- **Database:** PostgreSQL (Supabase) with Row-Level Security (RLS).
- **Observability:** Langfuse, LangSmith (configurable).

## Project Structure
```
synod-ai/
├── app/                      # Backend Implementation
│   ├── adapters/             # Concrete integrations (LLM Providers, DB, Notion, Research, Observability)
│   ├── api/                  # FastAPI Presentation Layer (REST, SSE v1 routes & dependencies)
│   ├── application/          # CQRS Commands, Handlers, and Services
│   ├── core/                 # Central configuration, exception mapping, security, rate limiters
│   ├── domain/               # Pure Python business entities, ports, and rules
│   ├── orchestration/        # LangGraph StateGraph, nodes, checkpointer, and runner
│   └── main.py               # FastAPI Bootstrap & Lifespan configuration
├── docs/                     # Project architectural reports & guides
├── frontend/                 # Next.js Frontend Application
│   ├── src/app/              # Next.js App Router pages (sessions, history, settings)
│   ├── src/components/       # Monochromatic UI Components & json-render registry
│   └── src/lib/              # SSE Client & API Client utilities
├── scripts/                  # CI checks & utility scripts
└── tests/                    # Unit, Integration, and Contract tests
```

## Prerequisites
- **Python:** 3.11 or later
- **Node.js:** v18 or later
- **PostgreSQL Database:** Supabase recommended (provides Auth/JWKS & Postgres)

## Environment Variables
The backend relies on the following environment variables (defined in `app/core/config.py`):
- `DATABASE_URL`: Direct PostgreSQL connection string (asyncpg driver required).
- `SUPABASE_URL`: Your Supabase project URL.
- `SUPABASE_ANON_KEY`: Public anon key for Supabase client.
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key (backend-only).
- `CREDENTIAL_ENCRYPTION_KEY`: Fernet-compatible 32-byte URL-safe base64 key for encrypting provider credentials.
- `FRONTEND_URL`: URL of the Next.js frontend (default: `http://localhost:3000`).
- `ENVIRONMENT`: `development` | `staging` | `production` (default: `development`).
- `DEBUG`: Enable debug-level logs (default: `False`).
- `LANGSMITH_TRACING`: Toggle LangSmith tracing (default: `True`).
- `LANGSMITH_API_KEY`: API key for LangSmith (optional).
- `LANGSMITH_PROJECT`: Project name in LangSmith (default: `synod-ai`).
- `LANGSMITH_ENDPOINT`: Endpoint for LangSmith (default: `https://api.smith.langchain.com`).
- `LANGFUSE_TRACING`: Toggle Langfuse tracing (default: `False`).
- `LANGFUSE_PUBLIC_KEY` & `LANGFUSE_SECRET_KEY`: Langfuse API credentials (optional).
- `LANGFUSE_HOST`: Langfuse host endpoint (default: `https://cloud.langfuse.com`).
- `NOTION_CLIENT_ID` & `NOTION_CLIENT_SECRET`: Notion API integration credentials.
- `NOTION_REDIRECT_URI`: OAuth callback URI registered with Notion (default: `http://localhost:3000/settings/notion/callback`).
- `NOTION_PARENT_PAGE_ID`: Parent Notion page ID to file reports under (optional).

## Running Locally

### 1. Database Setup
Synod-AI uses PostgreSQL with migrations managed via Alembic.
1. Run migrations against your database URL:
   ```bash
   alembic upgrade head
   ```

### 2. Backend Setup
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```
2. Configure `.env` in the root directory (based on `.env.example`).
3. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
   Backend runs at `http://localhost:8000`. Swagger docs are at `http://localhost:8000/docs`.

### 3. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Configure `.env.local` inside `frontend/` containing:
   ```env
   NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
   ```
4. Run Next.js in development mode:
   ```bash
   npm run dev
   ```
   Frontend runs at `http://localhost:3000`.

## Testing
Run the Python test suite with the current directory added to `PYTHONPATH`:
```bash
$env:PYTHONPATH="."; pytest
```
This runs the unit, integration, and contract tests (96 test cases).

## API Overview
- `POST /api/v1/sessions` - Convene a new deliberation session.
- `GET /api/v1/sessions` - List deliberation sessions for the authenticated user.
- `GET /api/v1/sessions/{session_id}` - Retrieve details and state of a session.
- `GET /api/v1/sessions/{session_id}/stream` - SSE stream of live orchestration states.
- `POST /api/v1/providers` - Encrypt and store an LLM provider API key.
- `GET /api/v1/providers` - List configured LLM provider key metadata.
- `DELETE /api/v1/providers/{provider}` - Remove an LLM provider key.
- `POST /api/v1/providers/{provider}/test` - Perform a 1-token ping test using a raw API key.
- `GET /api/v1/providers/{provider}/models` - Retrieve live catalogue of available models.
- `POST /api/v1/research/keys` - Store an encrypted research provider key.
- `GET /api/v1/research/keys` - List configured research provider keys.
- `DELETE /api/v1/research/keys/{provider}` - Remove a research provider key.
- `POST /api/v1/research/keys/{provider}/test` - Test validation of research credentials.
- `POST /api/v1/notion/connect` - Initiates Notion OAuth redirect URL compilation.
- `GET /api/v1/notion/status` - Check Notion integration status.
- `DELETE /api/v1/notion/disconnect` - Disconnect Notion integration.
- `POST /api/v1/notion/publish/{session_id}` - Manually publish a session report to Notion.
- `GET /api/v1/observability/trace/{trace_id}/url` - Get the LangSmith trace URL for a session.

## Known Limitations & Discrepancies
- **Database Column Discrepancy:** The database mapping for `ProviderKeyModel` utilizes `ciphertext_b64` to store encrypted API keys. However, the custom Notion and Research integration routers (`notion.py` and `research.py`) reference `encrypted_key`, `label`, and `is_verified` attributes, which are absent from the core SQLAlchemy model declaration.
- **Single-operator sessions:** Sessions are single-user only (no real-time multi-user collaboration).
- **Text-only queries:** No multimodal support in the current stage.

## License
Refer to license files or headers where applicable.
