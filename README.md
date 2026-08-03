# Synod — Where Models Convene, Truth Concludes.

## What It Is

Synod is a self-hosted, supervisor-orchestrated council of language models that debate a single question and hand you back one synthesized answer. You submit a query and pick 3–6 models (from OpenRouter and/or NVIDIA NIM, using your own API keys); the system runs them through three stages — **First Opinions** (every model answers independently and in parallel), **Peer Review** (each model blind-critiques and ranks the other models' anonymized answers, so no model can favor a "trusted" brand), and **Chairman Synthesis** (the highest-ranked model, or one you pin, writes the final report from everything the council produced). Progress streams live to the browser over Server-Sent Events, and a finished session can optionally be archived to Notion.

## Architecture Overview

The backend is a hexagonal (ports & adapters) FastAPI application: `app/domain` holds framework-free business rules and state, `app/orchestration` runs the deliberation as a LangGraph state machine with `Send`-based fan-out for the parallel stages, and `app/adapters` implements the domain's ports against real providers (OpenRouter, NVIDIA NIM, Tavily, Anakin, Notion, Postgres). Each session's progress is published to an in-process async event bus and streamed to the frontend as SSE. See [docs/CODEBASE_REPORT.md](docs/CODEBASE_REPORT.md) for full detail.

## Tech Stack

| Layer | Stack |
|---|---|
| Backend | Python 3.11+, FastAPI, LangGraph, LangChain-core, SQLAlchemy (async), PyJWT, `cryptography` (Fernet), Uvicorn |
| Frontend | Next.js 14.2.5, React 18.3.1, TypeScript 5.5.3, Tailwind CSS 3.4.4, Zod 3.23.8, `@json-render/core`/`@json-render/react` 0.19.0 |
| Database | PostgreSQL (via SQLAlchemy async + `asyncpg`), accessed through Supabase (Auth + Postgres) |
| Observability | LangSmith (implemented, real tracer); Langfuse config exists but is currently unimplemented — see Known Limitations |

## Prerequisites

- **Python ≥ 3.11** (`pyproject.toml` → `requires-python = ">=3.11"`)
- **Node.js** — no version is pinned in `frontend/package.json` (no `engines` field); Next.js 14.2.5 requires Node 18.17+ upstream. Not confirmed in this repo — verify before publishing if you need an exact minimum.
- **PostgreSQL** — a Supabase project (recommended) or any Postgres instance reachable via `DATABASE_URL`

## Environment Variables

Read from `.env.example` and `app/core/config.py`. All fields in `Settings` have a Python-level default, but `SUPABASE_URL` and `CREDENTIAL_ENCRYPTION_KEY` are enforced non-empty by a validator whenever `ENVIRONMENT != "development"` — treat those two as required outside local dev.

### Required (outside local development)

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL, used for JWT verification (JWKS) and the Postgres connection |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key used to encrypt stored provider API keys |
| `DATABASE_URL` | Direct Postgres connection string (rewritten internally to `postgresql+asyncpg://`) |

### Optional (have working defaults)

| Variable | Default | Description |
|---|---|---|
| `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_ANON_KEY` | `""` | Supabase anon key |
| `SUPABASE_SECRET_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | `""` | Supabase service-role key |
| `LANGSMITH_TRACING` | `true` | Enables LangSmith tracing (also needs `LANGSMITH_API_KEY`) |
| `LANGSMITH_API_KEY` | none | LangSmith API key — tracing is a no-op until this is set |
| `LANGSMITH_PROJECT` | `evidentia-council` (`.env.example`) / `synod-ai` (code default) | LangSmith project name |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | LangSmith API endpoint |
| `LANGFUSE_TRACING` | `false` (`true` in `.env.example` comment) | Gate for Langfuse — **no tracer implementation currently reads this**, see Known Limitations |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | none / none / `https://cloud.langfuse.com` | Langfuse credentials |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | `""` | Notion OAuth app credentials |
| `NOTION_REDIRECT_URI` | `http://localhost:3000/settings/notion/callback` (code default; `.env.example` shows a backend URL — see Known Limitations) | Must be registered exactly in the Notion integration dashboard |
| `NOTION_PARENT_PAGE_ID` | none | Notion page to file archived reports under |
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` |
| `FRONTEND_URL` | `http://localhost:3000` | Used for CORS and OAuth redirects |

## Local Setup

1. **Clone**
   ```bash
   git clone <repo-url> synod-ai && cd synod-ai
   ```
2. **Backend setup**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   cp .env.example .env   # then fill in DATABASE_URL, SUPABASE_URL, CREDENTIAL_ENCRYPTION_KEY, etc.
   ```
3. **Database** — there is no Alembic migration tooling in this repo (`alembic.ini` and any `alembic/`/`migrations/` directory are absent). In development, tables are created automatically on backend startup via `Base.metadata.create_all` (gated on `ENVIRONMENT=development`). For any non-development environment, the schema must currently be created by another means — this is a real gap, see Known Limitations.
4. **Run backend**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
5. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```
   Create `frontend/.env.local` with:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_SUPABASE_URL=<your supabase url>
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<your supabase anon key>
   ```
6. **Run frontend**
   ```bash
   npm run dev
   ```
7. **Verify**
   - Swagger UI: http://localhost:8000/docs
   - OpenAPI schema: http://localhost:8000/api/v1/openapi.json
   - Health check: http://localhost:8000/health
   - Frontend: http://localhost:3000

## Running Tests

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

As of the last run: **155 passed, 0 failed, 1 cosmetic warning** (an unawaited `AsyncMock` coroutine in one identity test — not a functional issue).

## API Reference

See [docs/api-contract.md](docs/api-contract.md).

## Known Limitations

- **No Alembic migrations.** `alembic.ini` and any migrations directory have been removed from the repo. Schema creation only happens via `Base.metadata.create_all` in development; there is currently no supported production migration path.
- **Langfuse tracing is unimplemented.** `app/adapters/observability/langfuse_tracer.py` is an empty file — no `LangfuseTracer` class exists anywhere in the codebase, despite `LANGFUSE_*` settings and a frontend API client method (`saveLangfuseKeys`) that has no UI consumer. LangSmith is the only working tracer.
- **Single-operator sessions only** — no real-time multi-user collaboration on a session.
- **Text-only queries** — no voice or image/multimodal input.
- **Only two LLM providers are actually wired up**: OpenRouter and NVIDIA NIM. GitHub Models is not implemented (`ProviderAdapterFactory` does not support it, despite a stale docstring mentioning it).
- **The `/settings/integrations` page is orphaned from navigation** — it exists and works (research provider keys, Notion connect) but has no link from the main app nav or the settings sub-nav; it's reachable only via direct URL or the post-OAuth redirect.
- **Two dead orchestration code paths exist but aren't executed**: `app/orchestration/nodes/archive.py` (`archive_node`) is superseded by `notion_archivist_node.py` and is never wired into the graph; `sessions.py` defines an `_emit_terminal` SSE helper with no call site.

## License

Not confirmed — no LICENSE file exists in the repository. Verify before publishing.
