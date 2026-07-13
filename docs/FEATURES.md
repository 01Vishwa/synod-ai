# Core Features

This document outlines the implemented core features of the Synod platform based on an analysis of the codebase.

## 1. Supervisor-Orchestrated Deliberation (LangGraph)
- **Role-Based Workflow:** Synod eschews free-form multi-agent chat. Every node (Council Member, Research Agent, Chairman) serves a specific function.
- **Decision Orchestrator:** A central LangGraph supervisor dictates the flow from initial opinions (Stage 1) to peer review (Stage 2) and final synthesis (Stage 3). Agents never communicate directly with each other, minimizing hallucination loops.

## 2. Blind Peer Review (Anonymity in Judgment)
- **Mitigating Brand Bias:** In Stage 2, all AI-generated answers are completely stripped of identifying strings (e.g., model or provider names).
- **Algorithmic Ranking:** Models act as peer reviewers and rank the anonymized bundle. The backend uses deterministic utilities like the `Ranking Aggregator` to calculate normalized scores (e.g., Borda Count).

## 3. Strict Bring-Your-Own-Key (BYOK) Architecture
- **Provider Agnosticism:** Synod supports OpenRouter, NVIDIA NIM, and GitHub Models out-of-the-box using the Adapter pattern.
- **Encrypted Storage:** Users input their API keys directly through the UI. These keys are Fernet-encrypted (via a `KeyVault` singleton) and stored in PostgreSQL securely. No keys are hard-coded or logged.

## 4. Live Web Grounding (Tavily & Anakin APIs)
- **Evidence Over Eloquence:** Users can configure Tavily or Anakin integrations to ground the deliberation.
- **Centralized Context:** The Decision Orchestrator invokes the Research Sub-Agent during Stage 1 and seamlessly appends the resulting citation-tagged evidence digest into the prompt context identically for all Council Members, ensuring a fair starting ground.

## 5. Enterprise-Grade Security & Isolation
- **Row-Level Security (RLS):** Database transactions are isolated on a per-user basis. The backend automatically injects the authenticated JWT `sub` claim into Postgres contexts.
- **Supabase Authentication:** Validates ES256 JSON Web Signatures directly against Supabase's public JWKS endpoint.

## 6. Real-Time Observability
- **Langfuse / LangSmith Integrations:** The platform captures deep metrics. Every LLM generation is traced, recording token ingestion, completion duration, and monetary cost via `LangfuseTracer`.
- **Server-Sent Events (SSE):** Users watch the deliberation unfold in real-time. The frontend hooks subscribe to state deltas emitted by the backend as each agent completes its task.

## 7. Dynamic Data UI
- **Generative Rendering:** All dashboards, cost meters, and ranking metrics are driven entirely by `@json-render/core` and `@json-render/react`. The backend dictates the UI composition, completely removing the need for frontend redeploys when new metrics are added.
- **Black-and-White Theme:** A strict monochromatic design system focused entirely on legibility and minimalism.
