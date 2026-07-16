# Technology Stack

Synod utilizes a structured stack dividing concerns between a stateless Python backend, an interactive Next.js frontend, and a managed PostgreSQL datastore.

## Backend (Python)

### Core Frameworks
- **Python:** 3.11+
- **FastAPI:** High-performance async web framework exposing REST endpoints and SSE (Server-Sent Events) for real-time dashboard updates.
- **Pydantic / Pydantic Settings:** For strict environment variable parsing, API validation, and UI component schema constraints.

### AI & Orchestration
- **LangGraph:** Controls the core workflow. Defines the `StateGraph` which manages transitions between the Decision Orchestrator, Council Members, and the Chairman via a single `CouncilState`.
- **LangChain:** Used primarily for its chat model wrappers and tool-calling scaffolds, standardizing interfaces to LLMs.
- **Langfuse / LangSmith:** Advanced observability platforms that trace every node execution, logging token ingestion, execution duration, and per-call monetary costs.

### Database & Persistence
- **PostgreSQL:** Primary relational datastore for saving graph checkpoints and encrypted keys.
- **SQLAlchemy (Async):** The ORM utilized within the persistence adapters.
- **Alembic:** Database migration management.

### Security
- **PyJWT:** Directly queries the Supabase JSON Web Key Set to asynchronously decode and verify ES256 JSON Web Tokens (JWT).
- **Cryptography (Fernet):** AES-based encryption for securing user-provided API keys (OpenRouter, NVIDIA NIM, etc.) at rest in the database.

## Frontend (TypeScript)

### Core Frameworks
- **Next.js 14:** React framework utilizing the App Router for server-side rendering, routing, and layout definitions.
- **React 18:** Component-based UI library.
- **TypeScript:** Strict typing ensuring interface alignment with the backend models.

### Authentication & UI
- **@supabase/ssr:** Handles user sessions seamlessly across the server and client components in Next.js.
- **TailwindCSS:** Enforces the black-and-white monochromatic design system.
- **Lucide React:** Iconography.

### Dynamic Rendering
- **@json-render/core & @json-render/react:** Generative UI framework by Vercel Labs. It ingests the `dashboard_spec` JSON blob emitted via SSE from the backend and dynamically constructs metrics, charts, and tables without hardcoded React logic.

## Third-Party Integrations
- **Authentication:** Supabase (JWT / RLS).
- **Inference Providers:** OpenRouter, NVIDIA NIM, GitHub Models.
- **Research Providers:** Tavily, Anakin API.
- **Document Export:** Notion API via standard OAuth 2.0 PKCE.
