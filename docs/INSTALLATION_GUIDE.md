# Installation Guide

A complete, from-zero setup guide for running Synod locally. The project is a Python/FastAPI backend paired with a Next.js frontend, using Supabase for auth and Postgres.

## System Requirements

- **Python ≥ 3.11** (`pyproject.toml`: `requires-python = ">=3.11"`)
- **Node.js** — not pinned anywhere in the repo (`frontend/package.json` has no `engines` field). Next.js 14.2.5 requires Node 18.17+ upstream — treat that as the practical floor, but this is not enforced by the project itself.
- **PostgreSQL** — version not pinned in code. A Supabase-managed Postgres instance is recommended (the auth layer already assumes Supabase JWTs); any Postgres reachable via `DATABASE_URL` will work for the database layer itself.

## Cloning and Structure

```bash
git clone <repo-url> synod-ai
cd synod-ai
```

Top-level layout:
- `app/` — FastAPI backend (hexagonal architecture: `domain/`, `orchestration/`, `adapters/`, `api/`, `application/`, `core/`)
- `frontend/` — Next.js 14 app
- `tests/` — pytest suite (`unit/`, `integration/`, `contract/`)
- `docs/` — this guide, the API contract, and the codebase report
- `pyproject.toml`, `.env.example` — backend dependencies and env template

## Backend Installation

### 1. Create and activate a virtualenv

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

This is the correct command per `pyproject.toml` — `[project.optional-dependencies].dev` includes `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`; the base `dependencies` list includes `fastapi`, `uvicorn`, `langgraph`, `langchain-core`, `SQLAlchemy`, `cryptography`, `PyJWT`, `langfuse`, `langsmith`, `openai`, `httpx`, `tenacity`, `cachetools`, `sse-starlette`, `alembic`, `mcp`, `langchain-mcp-adapters`, `pydantic`, `pydantic-settings`. There is no `requirements.txt` in this repo — do not use `pip install -r requirements.txt`.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in every variable below. Descriptions and defaults come from `app/core/config.py`.

**Required outside local development** (enforced by a validator when `ENVIRONMENT != "development"`):

| Variable | Example | Notes |
|---|---|---|
| `SUPABASE_URL` | `https://xxxx.supabase.co` | Used for JWT/JWKS verification and DB connectivity |
| `CREDENTIAL_ENCRYPTION_KEY` | (generated, see below) | Must be a valid Fernet key |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/postgres` | Rewritten internally to `postgresql+asyncpg://` |

Generate `CREDENTIAL_ENCRYPTION_KEY` with:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Optional** (all have working defaults in `Settings`):

| Variable | Default | Notes |
|---|---|---|
| `SUPABASE_PUBLISHABLE_KEY` | `""` | Supabase anon/publishable key |
| `SUPABASE_SECRET_KEY` | `""` | Supabase service-role key |
| `LANGSMITH_TRACING` | `true` | No-op unless `LANGSMITH_API_KEY` is also set |
| `LANGSMITH_API_KEY` | none | Enables real LangSmith tracing |
| `LANGSMITH_PROJECT` | `evidentia-council` / `synod-ai` | Project name shown in LangSmith |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | |
| `LANGFUSE_TRACING` | `false` | **No effect currently** — no `LangfuseTracer` implementation exists in the codebase, this is dead config |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | none / none / `https://cloud.langfuse.com` | See above |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | `""` | From your Notion integration dashboard |
| `NOTION_REDIRECT_URI` | `http://localhost:8000/api/v1/notion/oauth/callback` (`.env.example`) | Must be registered exactly (no trailing slash) in the Notion integration dashboard |
| `NOTION_PARENT_PAGE_ID` | none | Optional Notion page to file reports under |
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` — gates table auto-creation and strict env-var validation |
| `FRONTEND_URL` | `http://localhost:3000` | Used for CORS and post-OAuth redirects |

## Database Setup

Synod's schema is two tables — `council_sessions` and `provider_keys` (see `app/adapters/persistence/models.py`). There is **no Alembic configuration in this repository** — `alembic.ini` and any `alembic/`/`migrations/` directory have been removed. The only schema-creation mechanism present is `create_all_tables()` (`Base.metadata.create_all`), which runs automatically on backend startup **only when `ENVIRONMENT=development`** (see `app/main.py` lifespan hook). For any non-development deployment, you must create the schema through some other means — this is a genuine gap in the current codebase, not a documentation oversight.

To verify the DB connection works, start the backend (next section) and check:

```bash
curl http://localhost:8000/readiness
```

A `{"status": "ready", ...}` response with `"database": {"status": "ok", ...}` confirms connectivity; a 503 with `"not_ready"` means Postgres is unreachable.

## Running the Backend

```bash
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/api/v1/openapi.json
- Health check (liveness, no DB check): http://localhost:8000/health
- Readiness check (includes a DB ping): http://localhost:8000/readiness

## Frontend Installation

1. ```bash
   cd frontend
   npm install
   ```
2. Create `frontend/.env.local`:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<your supabase anon key>
   ```
   These three are the only `NEXT_PUBLIC_*` variables referenced anywhere in `frontend/src`.
3. ```bash
   npm run dev
   ```
4. App: http://localhost:3000

## Verifying the Full Stack

- [ ] `curl http://localhost:8000/health` returns `{"status": "ok", ...}`
- [ ] `curl http://localhost:8000/readiness` returns `{"status": "ready", ...}`
- [ ] http://localhost:8000/docs loads Swagger UI
- [ ] http://localhost:3000 loads the frontend
- [ ] Sign in, then visit **Settings → Providers & API Keys** (`/settings/providers`) and confirm the OpenRouter and NVIDIA NIM cards render
- [ ] Enter an OpenRouter key and save — it is validated live against OpenRouter before being stored
- [ ] Submit a new session with 3+ council members and confirm it streams progress

Note: **Settings → Integrations** (`/settings/integrations` — research provider keys, Notion connect) has no link in the app's navigation; reach it by typing the URL directly.

## Running Tests

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

Expected output (as of the last verified run): `155 passed, 1 warning` in ~20 seconds. The one warning is a cosmetic `RuntimeWarning: coroutine ... was never awaited` inside an `AsyncMock`-based identity test — it does not indicate a failure.

## Common Issues

- **`CREDENTIAL_ENCRYPTION_KEY` invalid format** — `KeyVault.__init__` raises `KeyVaultError` if the value isn't valid Fernet key material. Regenerate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and paste the exact output (no quotes, no extra whitespace).
- **Database connection refused** — check `DATABASE_URL` is a real Postgres URL; the backend rewrites `postgres://`/`postgresql://` to `postgresql+asyncpg://` automatically, but a wrong host/port/credentials will surface as a 503 from `GET /readiness` or a startup failure. If using Supabase's pooled connection string, note the app disables server-side prepared statements (`prepared_statement_cache_size: 0`) specifically to work with PgBouncer transaction-mode pooling.
- **NVIDIA NIM key validation is slow** — `validate_key()` calls a real chat completion against the configured validation model (default `meta/llama-3.1-8b-instruct`) with an 8-second per-call timeout wrapped in a 10-second outer `asyncio.wait_for`; a slow/cold NIM endpoint can take close to that ceiling before you see a result.
- **Free-tier OpenRouter models are slow to respond** — any model ID ending in `:free` gets a 90-second read timeout instead of the normal per-call timeout (`_build_timeout` in `openrouter_adapter.py`/`nvidia_nim_adapter.py`), because free-tier OpenRouter models can sit in a shared queue.
- **`/settings/integrations` seems unreachable from the UI** — this is expected in the current build; there is no nav link to it (see Known Limitations in the README). Navigate to it directly.
