# Implementation Status (as of current build)

*This section was added by an audit of the actual codebase; it does not modify the original PRD text below the horizontal rule.*

## What Is Built and Working

- **Multi-model Stage 1 fan-out** — `app/orchestration/graph.py`'s `route_stage_1` dispatches one parallel LangGraph `Send("stage_1_draft", ...)` per configured council member (3–6 members).
- **Blind peer review (Stage 2)** — `route_stage_2` fans out one `Send("stage_2_review", ...)` per member that survived Stage 1, each reviewing a uniquely shuffled, anonymized bundle of the others' answers (`build_anonymization_map`, `shuffle_responses_for_reviewer`).
- **Chairman synthesis (Stage 3)** — `stage_3_node`, with a documented fallback policy (`validate_chairman`) if the pinned chairman failed in Stage 1.
- **OpenRouter provider** — confirmed real, working `ProviderAdapter` implementation (`app/adapters/llm_providers/openrouter_adapter.py`).
- **NVIDIA NIM provider** — confirmed real, working `ProviderAdapter` implementation (`app/adapters/llm_providers/nvidia_nim_adapter.py`).
- **SSE streaming with an event bus** — `app/core/event_bus.py` + `GET /sessions/{id}/stream`; 12 of 15 defined event types are actually published by orchestration nodes today.
- **KeyVault encryption** — Fernet-based (`app/adapters/security/key_vault.py`), used for all stored provider/research/Notion credentials; no plaintext key is ever persisted.
- **Supabase Auth + JWT verification** — `app/api/v1/deps.py` verifies Supabase-issued JWTs (ES256/JWKS) on every protected route; RLS context is set best-effort as a secondary layer, with application-level `user_id` filtering as the primary tenant-isolation mechanism.
- **Research providers** — both Tavily and Anakin have real, working `ResearchProviderAdapter` implementations (`app/adapters/research_providers/`), though the Anakin adapter's base URL is flagged in its own source comment as provisional/unconfirmed.
- **Notion integration** — OAuth connect/callback/status/disconnect and publish-on-completion are implemented (`app/api/v1/routers/notion.py`, `notion_archivist_node.py`); the settings page for it exists but is not linked from any app navigation.
- **Settings pages that exist**: `/settings/providers` (linked in nav), `/settings/appearance` (linked in nav), `/settings/integrations` (exists, functional, **not linked** in nav), `/settings/notion/callback` (OAuth redirect target only).

## What Is Explicitly Out of Scope (v1)

Still not implemented, per the original PRD's non-goals:
- Fine-tuning or self-hosting model weights.
- Arbitrary/self-hosted model endpoints outside the supported provider list.
- Real-time multi-user collaboration on a single session (sessions remain single-operator).
- Voice or image/multimodal input (queries remain text-only).
- A self-built web-search index (Tavily/Anakin remain the only research paths).

## Deviations From Original PRD

- **GitHub Models was removed as a provider.** The original PRD's Goal G4 named OpenRouter, NVIDIA NIM, and GitHub Models as the three supported providers. Only OpenRouter and NVIDIA NIM are implemented in `ProviderAdapterFactory`; GitHub Models does not exist as a working adapter (a stale docstring in `factory.py` still mentions it).
- **The json-render dashboard spec (Goal G9) is implemented**, via `dashboard_builder_node` producing a `dashboard_spec` (root + `RankBar`/`MetricCard`/`TokenTable`/`SourceList` elements), rendered by the frontend's `@json-render/core`/`@json-render/react` integration (`frontend/src/components/dashboard/`).
- **Alembic (referenced throughout the original PRD's data/persistence sections) is not present.** `alembic.ini` and any migrations directory have been removed from the repository; the only schema-creation path remaining is a dev-only `Base.metadata.create_all` call.
- **LangSmith was added as the primary observability implementation, not merely an alternative to Langfuse.** The original PRD specified Langfuse (Goal G7); in the current codebase, LangSmith (`app/adapters/observability/langsmith_tracer.py`) is the only tracer that actually works — the Langfuse adapter file exists but is empty, with no implementation behind the Langfuse config fields.
- **Citations (Goal G3, "cites which sub-answers it drew from") are not implemented.** `CouncilState.citations` and `SessionResponse.citations` always return `[]`; there is no citation-extraction logic in `stage_3_node`.
- **A dead alternate Notion-archiving code path exists** (`app/orchestration/nodes/archive.py`) alongside the one actually used (`notion_archivist_node.py`) — not a deviation in behavior, but worth noting as leftover code from a prior iteration.

---

# SYNOD
### *Where Models Convene, Truth Concludes.*

**Product Requirements Document (PRD) — v1.1**
**Author:** AI Product Management (drafted on behalf of the requester)
**Date:** July 12, 2026
**Status:** Draft for engineering review

---

## 0. Document Purpose

This PRD defines the end-to-end product, architecture, design patterns, project structure, agent workflow, tech stack, data contracts, UI, and rollout plan for **Synod** — a supervisor-controlled, multi-LLM deliberation system ("LLM Council"). It is written to be handed directly to an engineering team to begin implementation. Every external dependency named in this document (OpenRouter, NVIDIA NIM, GitHub Models, Notion MCP, Tavily, Anakin API, `@json-render/core`/`@json-render/react`, LangChain/LangGraph, Langfuse) has been verified against current, publicly available documentation as of July 12, 2026, and material risks (in particular, an imminent third-party deprecation) are flagged explicitly in **Section 15**.

**v1.1 changelog:** added Section 7 (Design Patterns & System Design Principles), Section 8 (Project Structure), and substantially expanded Section 12 (UI/UX Design) with layout, navigation, component hierarchy, state handling, responsive, and accessibility detail. All subsequent sections renumbered accordingly.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project Name** | **Synod** |
| **Tagline** | *Where Models Convene, Truth Concludes.* |
| **Category** | Multi-agent LLM deliberation / decision-support platform |
| **One-line description** | Synod is a supervisor-orchestrated council of independent AI models that debate, critique, and rank each other's answers — anonymously — before a designated Chairman agent synthesizes the strongest, most defensible response to your question. |

**Extended description:**
Instead of asking one model and trusting it blindly, Synod convenes a panel of language models you choose — sourced only from OpenRouter, NVIDIA NIM, and GitHub Models — and runs them through a three-stage deliberation process modeled on how expert panels, editorial boards, and academic peer review actually work: independent first opinions, blind peer evaluation, and a final synthesis by a Chairman. A supervisor (the **Decision Orchestrator**) — not the models themselves — controls every hand-off, so no agent ever free-talks to another; all coordination happens through a single, auditable, structured state object. Research sub-agents can pull live web evidence into the debate, and finished council reports can be archived straight to Notion.

---

## 2. Background & Problem Statement

Single-model answers carry a single model's blind spots, training biases, and failure modes. Power users increasingly copy the same prompt into three or four different chat windows (ChatGPT, Gemini, Claude, Grok) and manually compare answers — a process that is slow, ad hoc, un-auditable, and impossible to reproduce or share with a team.

There is no lightweight, self-hosted, provider-agnostic tool that:
1. Fans a single query out to a user-configured panel of models,
2. Has the models **anonymously** critique and rank each other (removing the "I trust brand X" bias),
3. Produces one synthesized, evidence-grounded final answer, and
4. Logs/archives the whole deliberation for later audit.

Synod fills that gap using a strict, non-conversational, supervisor-controlled agent architecture — deliberately avoiding the unpredictability of "agents freely chatting with agents."

---

## 3. Goals & Non-Goals

### 3.1 Goals
- G1: Let a user submit one question and receive independent answers from N user-selected models in parallel (Stage 1).
- G2: Have each model blind-rank the other models' anonymized answers on accuracy and insight (Stage 2).
- G3: Produce a single, synthesized "Chairman" answer that cites which sub-answers it drew from (Stage 3).
- G4: Restrict all model access to exactly three providers: **OpenRouter, NVIDIA NIM, GitHub Models** — configured only via user-supplied API keys entered in the UI, never hardcoded or defaulted server-side.
- G5: Optionally ground any stage with **live web research**, using a research provider the user chooses between **Tavily** and **Anakin** (user-supplied API key for whichever they prefer — not both required).
- G6: Optionally archive any completed council session to **Notion** via MCP.
- G7: Provide full observability (per-model latency, cost, token usage, failure) via **Langfuse**.
- G8: Ship a strictly **black-and-white** UI — no other hues anywhere in the product surface.
- G9: Render every dashboard, graph, and numerical readout (rankings, cost, latency, token usage) as a **dynamic, data-driven UI** using `@json-render/core` + `@json-render/react`, rather than hardcoded chart components — so the same backend-emitted spec can add/reorder/resize widgets without a frontend redeploy.
- G10: Build the system on well-established, named design patterns and a clean, layered (hexagonal) project structure so the codebase is testable, swappable at every external boundary, and maintainable by engineers who did not write it.

### 3.2 Non-Goals (v1)
- NG1: Fine-tuning or hosting any model weights ourselves.
- NG2: Supporting arbitrary/self-hosted model endpoints outside the three named providers.
- NG3: Real-time multi-user collaborative editing of a single council session (single-operator sessions only in v1).
- NG4: Voice or multimodal (image/audio) input in v1 — text-only queries.
- NG5: Building our own web-search index (Tavily and Anakin exist precisely so we don't have to).

---

## 4. Users & Personas

| Persona | Need |
|---|---|
| **Research analyst / consultant** | Wants a defensible, cross-checked answer to cite in a client deliverable, with a paper trail. |
| **Engineering lead** | Wants to compare how differently-priced/differently-sized models reason about the same technical question before committing budget to one vendor. |
| **Solo founder / power user** | Already pays for OpenRouter credits and a free NVIDIA NIM key; wants one interface instead of five browser tabs. |
| **Knowledge team / PMM** | Wants finished council reports to land directly in the team's Notion knowledge base. |

---

## 5. Product Principles (the "Council Doctrine")

1. **No agent talks to another agent directly.** All input/output passes through the Decision Orchestrator's structured state. This is a hard architectural constraint, not a style choice — it keeps every hand-off inspectable, replayable, and testable.
2. **Anonymity in judgment.** During Stage 2, a model never knows which provider/model produced the answer it is grading — including its own. This is enforced by the Orchestrator, not requested via prompt.
3. **Bring your own keys.** Synod stores zero platform-level model credentials. Every model call is billed to the user's own OpenRouter / NVIDIA NIM / GitHub Models account.
4. **Evidence over eloquence.** Where research tools are enabled, the Chairman must prefer cited, retrieved evidence over an unsupported model claim.
5. **Everything is traced.** Every LLM call, every tool call, every state transition is a Langfuse span. If it isn't traced, it didn't happen.
6. **Every external system is behind a port.** Nothing outside the `domain/` layer is trusted directly — providers, research vendors, Notion, and the observability platform are all reached only through an interface the domain defines, never a concrete SDK call. (Elaborated in Section 7.)

---

## 6. System Architecture

### 6.1 Architectural Style

Synod uses a **supervisor-controlled specialist (hub-and-spoke) architecture**, implemented as a single **LangGraph `StateGraph`**. There is exactly one node authorized to decide "what happens next": the **Decision Orchestrator**. All other nodes — Council Member agents, the Research sub-agent, the Anonymizer, the Ranking Aggregator, the Chairman, and the Notion Archivist — are **specialists** that receive a scoped slice of state, do one job, write their output back to state, and return control to the Orchestrator. No specialist can invoke another specialist directly.

```
                              ┌───────────────────────────┐
                              │      DECISION ORCHESTRATOR     │
                              │   (LangGraph Supervisor Node)  │
                              │  reads/writes CouncilState only│
                              └──────────────┬────────────────┘
                                             │  routes on state.stage
              ┌───────────────┬─────────────┼─────────────┬───────────────┐
              ▼               ▼             ▼             ▼               ▼
     ┌────────────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────────┐
     │ Research Sub-   │ │ Council  │ │  Anonymizer  │ │  Ranking  │ │   Chairman    │
     │ Agent (Tavily/  │ │ Members  │ │  & Redactor  │ │Aggregator │ │  Synthesizer  │
     │  Anakin)        │ │          │ │              │ │           │ │               │
     │ optional, stage │ │ (N × LLM)│ │  (Stage 1→2) │ │ (Stage 2) │ │  (Stage 3)    │
     │ 1 & 3 pre-fetch │ │ Stage 1  │ │              │ │           │ │               │
     └────────────────┘ └──────────┘ └──────────────┘ └───────────┘ └───────┬───────┘
                                                                             │
                                                                             ▼
                                                                  ┌─────────────────────┐
                                                                  │ Notion Archivist Sub-│
                                                                  │ Agent (MCP, optional)│
                                                                  └─────────────────────┘
```

Every arrow above is a **state hand-off**, not a message between two agents. A Council Member never sees another Council Member's identity; the Orchestrator strips and re-injects data as it moves through `CouncilState`.

### 6.2 Why Supervisor-Controlled (not free multi-agent chat)

A free-form "agents talking to agents" pattern (e.g., AutoGen-style group chat) is non-deterministic, hard to cost-cap, and hard to audit — an agent can loop, defer, or hallucinate a hand-off. A supervisor graph gives us:
- **Deterministic routing** — the Orchestrator's routing function is plain code, testable independently of any LLM.
- **Central cost/timeout control** — one place enforces per-stage timeouts and per-session token/cost ceilings.
- **Clean checkpointing** — LangGraph's built-in state persistence lets a crashed run resume from the last completed stage instead of re-billing every model from scratch.
- **Single source of truth for tracing** — Langfuse renders the whole run as one graph because it is, in fact, one graph.

### 6.3 Agents & Sub-Agents (roles)

| Node | Type | Responsibility | Model calls? |
|---|---|---|---|
| **Decision Orchestrator** | Supervisor | Owns `CouncilState`; decides next node based on `stage`, error flags, and user config; enforces timeouts/retries/cost ceiling. | No (rule-based + optional lightweight routing call) |
| **Council Member (×N)** | Specialist agent | One per user-selected model/provider pair. Receives the raw query (+ optional research digest), returns an independent first opinion. Fan-out is parallel. | Yes — 1 call per member per stage-1 pass |
| **Research Sub-Agent** | Specialist / tool-agent | Invoked by the Orchestrator when "Enable live research" is on. Calls whichever research provider the user configured — **Tavily** or **Anakin** (search + scrape), via LangChain tool wrappers — and returns a citation-tagged evidence digest into state. | Optional small LLM call to compress/rank sources |
| **Anonymizer & Redactor** | Deterministic utility node | Maps each Council Member's real identity to a random label (`Member A`, `Member B`, ...) for the duration of Stage 2 only; strips identifying strings (model name mentions, provider-specific formatting tics) before hand-off. | No |
| **Peer Reviewer (reuses Council Member)** | Specialist agent | Each Council Member is re-invoked in Stage 2, given the anonymized set of all answers (including a randomized copy of its own), and asked to rank for accuracy + insight with justification. | Yes — 1 call per member per stage-2 pass |
| **Ranking Aggregator** | Deterministic utility node | Computes a normalized score per member (e.g., Borda count / weighted rank), de-anonymizes for the *record* (not for the models), writes `rankings` to state. | No |
| **Chairman Synthesizer** | Specialist agent (elected role) | Receives all Stage 1 answers, all Stage 2 rankings + justifications, and any research digest; produces the single final report with inline attribution ("per the highest-ranked response...") and citations. Chairman model is user-selectable and defaults to the top-ranked Stage 2 member. | Yes — 1 call |
| **Notion Archivist Sub-Agent** | Specialist / tool-agent | Optional. Invoked post-Stage-3 if the user has connected Notion MCP; formats the final report + full deliberation trail into a new Notion page. | No (tool-only, via MCP) |

### 6.4 State, Not Conversation

The single artifact all nodes read and write is `CouncilState`. Nothing is passed "in conversation" — a Council Member never receives another Council Member's raw text with attribution; it receives whatever slice of `CouncilState` the Orchestrator decides is appropriate for that stage.

```python
class CouncilMemberConfig(TypedDict):
    member_id: str            # internal stable id, e.g. "member_1"
    provider: Literal["openrouter", "nvidia_nim", "github_models"]
    model_id: str              # e.g. "anthropic/claude-sonnet-4.5" (OpenRouter form)
    display_label: str         # user-facing name, e.g. "Council Seat 1"
    role: Literal["member", "chairman"]

class MemberResponse(TypedDict):
    member_id: str
    stage: Literal["stage_1", "stage_2"]
    content: str
    anonymized_label: Optional[str]   # e.g. "Member C" — set only during stage 2 hand-off
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: Optional[str]

class RankingEntry(TypedDict):
    ranked_by_member_id: str
    ranking_order: list[str]          # ordered list of anonymized labels, best -> worst
    justification: str

class ResearchDigest(TypedDict):
    provider: Literal["tavily", "anakin"]
    query_terms: list[str]
    sources: list[dict]                # {url, title, snippet, retrieved_at}
    summary: str

class CouncilState(TypedDict):
    session_id: str
    trace_id: str                      # Langfuse trace id
    user_query: str
    stage: Literal["stage_1", "stage_2", "stage_3", "archiving", "done", "error"]
    research_enabled: bool
    research_provider: Optional[Literal["tavily", "anakin"]]
    research_digest: Optional[ResearchDigest]
    dashboard_spec: Optional[dict]      # json-render Spec (root + elements) for the live results dashboard
    members: list[CouncilMemberConfig]
    stage_1_responses: list[MemberResponse]
    anonymization_map: dict[str, str]  # member_id -> anonymized_label (server-side only, never sent to models except mapped)
    stage_2_responses: list[MemberResponse]
    rankings: list[RankingEntry]
    aggregate_scores: dict[str, float] # member_id -> normalized score
    chairman_member_id: str
    final_report_md: Optional[str]
    citations: list[dict]
    notion_page_url: Optional[str]
    errors: list[dict]
    created_at: str
    updated_at: str
```

### 6.5 Sequence of a Single Council Run

1. **Intake** — User submits a query + selects 3–6 Council Members (provider + model each) + optionally a Chairman + optionally enables Research + optionally enables Notion archiving. Orchestrator creates `CouncilState`, opens a Langfuse trace.
2. **Stage 1 — First Opinions** (parallel fan-out)
   - If research is enabled, Orchestrator first invokes the Research Sub-Agent once; the resulting `research_digest` is appended to every Council Member's prompt context identically (fairness: every member sees the same evidence).
   - Orchestrator fans out N parallel calls, one per Council Member, each fully isolated (no member sees another's output).
   - Responses land in `stage_1_responses`. UI renders this as **tabs**, one per model, as they stream in.
3. **Stage 2 — Blind Peer Review**
   - Anonymizer relabels all `stage_1_responses` (`Member A..N`, shuffled per member so no one can infer identity from ordering) and strips any self-identifying text.
   - Orchestrator re-invokes each Council Member with the *same anonymized bundle* (including a shuffled copy of its own answer) and asks it to rank all answers for accuracy and insight, with justification, returned as structured JSON (see `RankingEntry`).
   - Ranking Aggregator computes a normalized score per member (e.g., Borda count across all N rankings), writes `aggregate_scores`.
4. **Stage 3 — Chairman Synthesis**
   - Chairman (default: highest-scoring member from Stage 2, or a user-pinned model) receives all de-anonymized Stage 1 answers, all Stage 2 justifications, `aggregate_scores`, and the research digest.
   - Chairman produces one final Markdown report: a direct answer, a short "where the council agreed / disagreed" note, and a citations list.
   - `final_report_md` and `citations` are written to state; `stage` -> `done` (or `archiving` if Notion is enabled).
5. **Archiving (optional)** — Notion Archivist Sub-Agent pushes the report + an appendix of the full deliberation trail to a Notion page via MCP; `notion_page_url` is written back to state.
6. **Delivery** — Frontend renders Stage 1 tabs, Stage 2 ranking table, and the Stage 3 final report, plus a "View full trace" link into Langfuse.

### 6.6 Failure Handling
- Per-member timeout (configurable, default 60s) and 2 retries with exponential backoff at the Orchestrator level.
- A Council Member that errors twice is excluded from that stage with `error` recorded in its `MemberResponse`; Stage 2/3 proceed with the surviving members, and the Chairman's report explicitly notes any excluded member.
- If **all** members fail Stage 1, the run halts at `stage: "error"` and the UI surfaces a clear, actionable message (e.g., invalid API key vs. provider outage) rather than a silent hang.

---

## 7. Design Patterns & System Design Principles

This section names the specific, established software-design patterns Synod is built on, and why each was chosen. Nothing here is decorative — every pattern maps to a concrete requirement from Sections 5–6 (bring-your-own-key, provider-agnostic, no-agent-to-agent-chat, fully-traced).

### 7.1 Overall Style: Hexagonal Architecture (Ports & Adapters)

Synod's backend is organized as **Ports & Adapters** (a.k.a. Hexagonal Architecture), with a strict dependency direction: outer layers depend on inner layers, never the reverse.

```
                     ┌───────────────────────────────────────────┐
                     │            PRESENTATION (Driving)          │
                     │     FastAPI routers · SSE endpoints        │
                     └───────────────────┬─────────────────────────┘
                                         │  calls into
                     ┌───────────────────▼─────────────────────────┐
                     │      APPLICATION / ORCHESTRATION LAYER        │
                     │   LangGraph StateGraph · nodes · routing      │
                     └───────────────────┬─────────────────────────┘
                                         │  depends only on
                     ┌───────────────────▼─────────────────────────┐
                     │              DOMAIN (the core)                │
                     │  CouncilState · ranking rules · anonymization │
                     │  ── defines PORTS (interfaces) here ──        │
                     │  ProviderAdapter · ResearchProviderAdapter    │
                     │  NotionPort · TracerPort · SessionRepository  │
                     └───────────────────┬─────────────────────────┘
                                         │  implemented by (Driven)
                     ┌───────────────────▼─────────────────────────┐
                     │                  ADAPTERS                     │
                     │ OpenRouterAdapter · NvidiaNimAdapter ·         │
                     │ GithubModelsAdapter · TavilyAdapter ·          │
                     │ AnakinAdapter · NotionMcpAdapter ·             │
                     │ LangfuseTracer · PostgresSessionRepository     │
                     └───────────────────────────────────────────────┘
```

The **domain** layer never imports an SDK — it only knows about the **ports** (Python `ABC` interfaces) it needs. The **adapters** layer is the only place that imports `openai`-compatible clients, the Tavily SDK, the Notion MCP client, or the Langfuse SDK. This is precisely what makes the GitHub Models retirement risk (Section 10.3) a one-file swap rather than a rewrite, and what lets contract tests run the exact same test suite against every `ProviderAdapter`/`ResearchProviderAdapter` implementation.

### 7.2 Named Patterns Applied

| Pattern | Where it's used | Why |
|---|---|---|
| **Mediator / Supervisor** | Decision Orchestrator (Section 6.1) | Centralizes all inter-agent coordination in one node so specialists never reference each other directly. |
| **Adapter** | `ProviderAdapter` (OpenRouter/NVIDIA NIM/GitHub Models), `ResearchProviderAdapter` (Tavily/Anakin), `NotionPort` | Normalizes three different OpenAI-compatible LLM APIs and two different search APIs behind one call signature each. |
| **Factory** | `ProviderAdapterFactory`, `ResearchProviderAdapterFactory` | Given a user's stored config (`provider: "tavily"`), returns the correct concrete adapter instance without callers ever importing a concrete class. |
| **Facade** | `ChatModelFacade` in the orchestration layer | Gives every Council Member node one uniform `.chat(messages) -> Response` call regardless of which of the three providers is behind it. |
| **Strategy** | Ranking aggregation (`rules/ranking.py`), Chairman-selection rule | The scoring algorithm (Borda count today) and the default-Chairman rule are swappable strategies, not hardcoded logic — a future weighted-ranking strategy is a new class, not a rewrite. |
| **Chain of Responsibility** | Per-node failure handling: timeout → retry (×2) → exclude-member → continue | Mirrors the same fallback-chain idea used by scraping APIs like Anakin's own handler chain (fast HTTP → browser → external API) — each handler in the chain gets a chance before escalating. |
| **Command** | json-render `actions` (e.g. `export_report`, `refresh_data`) on the frontend; `PublishToNotionCommand` on the backend | Encapsulates a user- or system-triggered action as an object that can be validated, logged, and dispatched uniformly. |
| **Observer / Publish–Subscribe** | SSE stream to the browser; Langfuse span ingestion | Both are subscribers to the same underlying `CouncilState`-delta event stream — the Orchestrator publishes, it doesn't know or care who's listening. |
| **Repository** | `SessionRepository` port / `PostgresSessionRepository` adapter | LangGraph nodes never write SQL directly; all persistence goes through one repository interface, keeping the orchestration layer storage-agnostic. |
| **Unit of Work** | Checkpoint writes at each stage transition | Each stage's state mutation + checkpoint write is committed as one atomic transaction, so a crash never leaves `CouncilState` half-written. |
| **Decorator** | `LangfuseTracer` wrapping every LLM/tool call | Adds tracing/timing/cost-capture around a call without the calling code (Council Member node) knowing tracing exists. |
| **Circuit Breaker** | Per-(user, provider) breaker in `core/circuit_breaker.py` | After N consecutive provider failures within a session, short-circuits further calls to that provider immediately instead of retrying into a known outage — directly mitigates the GitHub Models retirement risk during its brownout windows. |
| **Singleton** | Langfuse client, DB connection pool, `KeyVault` encryption manager | Exactly one instance per process for expensive, stateful resources. |
| **Dependency Injection** | FastAPI's `Depends()` throughout `api/v1/deps.py` | Adapters, DB sessions, and the current user are injected into route handlers rather than hand-constructed, which is also what makes route handlers trivially unit-testable with fake adapters. |
| **CQRS-flavored read/write split** | Write path: `POST /council/sessions` (mutates state via the graph). Read path: `GET /council/sessions/{id}` and `.../stream` (only ever read persisted checkpoints) | Keeps the expensive, multi-model graph execution path separate from cheap, frequent polling/history reads, so read traffic can scale independently. |
| **Event-Driven state propagation** | Every LangGraph node transition emits a `CouncilStateDelta` event | One event feeds both the SSE bridge (Observer) and the Langfuse span writer (Decorator/Observer), so UI updates and tracing can never drift out of sync. |

### 7.3 System Design Principles

- **Statelessness at the API tier.** FastAPI worker processes hold no in-memory session state; everything lives in Postgres via the LangGraph checkpointer, so the API layer scales horizontally behind a plain load balancer with no sticky sessions.
- **Idempotency.** `POST /council/sessions` accepts an idempotency key; a retried client request with the same key returns the existing session instead of re-billing every model provider a second time.
- **Backpressure & rate limiting.** A token-bucket limiter per `(user, provider)` pair throttles outbound calls before a provider's own rate limit (e.g., NVIDIA NIM's free-tier RPM ceiling) returns a 429.
- **Caching.** Research digests are cached for a short TTL, keyed by `(provider, normalized_query)`, so near-duplicate queries within a short window don't re-bill the search provider.
- **Observability as a first-class design input, not an afterthought.** Three pillars from Phase 0 onward: structured JSON logs, Langfuse traces (Section 6, Section 9), and lightweight counters (sessions/min, cost/session, per-provider failure rate).
- **Security by design.** Provider keys encrypted at rest (Section 10.5); least-privilege OAuth scopes for Notion (Section 9.2); all inbound request bodies validated against Pydantic schemas at the API boundary before anything reaches the domain layer.
- **A clear scale-out path.** v1 runs the LangGraph graph in-process inside the FastAPI worker handling the request; because orchestration logic lives in its own `orchestration/` package with no FastAPI imports, v2 can lift the same graph into a dedicated worker/queue (Celery, RQ, or a durable task queue) without touching adapters, routers, or the domain layer.

---

## 8. Project Structure

Synod is built as a two-package monorepo: `backend/` (FastAPI + LangGraph, Python) and `frontend/` (Next.js + json-render, TypeScript). The backend's folder layout is a direct, literal mapping of the Hexagonal Architecture in Section 7.1 — you can point at any folder and name which layer it belongs to.

```
synod/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app factory; mounts routers; startup/shutdown hooks
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── routers/
│   │   │       │   ├── sessions.py           # POST/GET /council/sessions, SSE stream endpoint
│   │   │       │   ├── providers.py          # LLM provider key CRUD + test-connection + model catalog
│   │   │       │   ├── research.py           # Tavily/Anakin key CRUD + test-connection
│   │   │       │   ├── notion.py             # Notion OAuth connect + publish
│   │   │       │   └── observability.py      # Langfuse trace redirect endpoint
│   │   │       ├── deps.py                   # FastAPI Depends() providers — Dependency Injection root
│   │   │       └── schemas/                  # Pydantic request/response models (API boundary validation)
│   │   │
│   │   ├── domain/                            # ── CORE (hexagon center), framework-agnostic ──
│   │   │   ├── council_state.py               # CouncilState, MemberResponse, RankingEntry, ResearchDigest
│   │   │   ├── rules/
│   │   │   │   ├── ranking.py                  # Borda-count aggregation Strategy
│   │   │   │   └── anonymization.py             # Anonymizer/Redactor pure functions
│   │   │   └── ports/                           # ── PORTS: interfaces the domain depends on ──
│   │   │       ├── provider_adapter.py           # ProviderAdapter ABC: chat(), list_models()
│   │   │       ├── research_adapter.py           # ResearchProviderAdapter ABC: search(), extract()
│   │   │       ├── notion_port.py                 # NotionPort ABC: publish_report()
│   │   │       ├── observability_port.py          # TracerPort ABC: start_span(), end_span()
│   │   │       └── session_repository.py           # SessionRepository ABC: save_checkpoint(), load(), list()
│   │   │
│   │   ├── orchestration/                      # LangGraph graph + nodes (application/use-case layer)
│   │   │   ├── graph.py                        # builds the StateGraph; wires nodes + conditional edges
│   │   │   ├── checkpointer.py                 # Postgres-backed LangGraph checkpointer (Unit of Work)
│   │   │   └── nodes/
│   │   │       ├── orchestrator.py              # Decision Orchestrator / supervisor routing function
│   │   │       ├── council_member.py             # Stage-1 + Stage-2 node (parametrized per member)
│   │   │       ├── research_node.py               # invokes whichever ResearchProviderAdapter is active
│   │   │       ├── anonymizer_node.py
│   │   │       ├── ranking_aggregator_node.py
│   │   │       ├── chairman_node.py
│   │   │       ├── notion_archivist_node.py
│   │   │       └── dashboard_builder_node.py      # builds dashboard_spec (json-render Spec) each stage
│   │   │
│   │   ├── adapters/                           # ── ADAPTERS: concrete implementations of the ports ──
│   │   │   ├── llm_providers/
│   │   │   │   ├── openrouter_adapter.py
│   │   │   │   ├── nvidia_nim_adapter.py
│   │   │   │   ├── github_models_adapter.py
│   │   │   │   └── factory.py                   # ProviderAdapterFactory (Factory pattern)
│   │   │   ├── research_providers/
│   │   │   │   ├── tavily_adapter.py
│   │   │   │   ├── anakin_adapter.py
│   │   │   │   └── factory.py
│   │   │   ├── notion/
│   │   │   │   └── notion_mcp_adapter.py         # wraps the Notion MCP client behind NotionPort
│   │   │   ├── observability/
│   │   │   │   └── langfuse_tracer.py            # implements TracerPort; Decorator over LLM/tool calls
│   │   │   ├── persistence/
│   │   │   │   ├── postgres_session_repository.py # implements SessionRepository
│   │   │   │   ├── models.py                       # SQLAlchemy ORM models
│   │   │   │   └── migrations/                      # Alembic migrations
│   │   │   └── security/
│   │   │       └── key_vault.py                   # Fernet/KMS-wrapped key encryption (Singleton)
│   │   │
│   │   └── core/
│   │       ├── config.py                        # pydantic-settings, env-driven, no provider defaults
│   │       ├── logging.py                        # structured JSON logging setup
│   │       ├── rate_limiter.py                    # token-bucket limiter (backpressure)
│   │       └── circuit_breaker.py                 # per-provider Circuit Breaker
│   │
│   ├── tests/
│   │   ├── unit/                                 # domain + rules only, zero I/O
│   │   ├── integration/                          # adapters against sandboxed/mocked provider APIs
│   │   └── contract/                             # one shared suite every ProviderAdapter/ResearchProviderAdapter must pass
│   │
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── Dockerfile
│
└── frontend/
    ├── package.json                              # npm install / npm run dev
    ├── next.config.js
    └── src/
        ├── app/                                  # Next.js App Router
        │   ├── layout.tsx                         # root layout — B&W ThemeProvider, design tokens
        │   ├── page.tsx                           # "New Session" screen
        │   ├── sessions/
        │   │   └── [sessionId]/
        │   │       └── page.tsx                    # live Stage 1 / 2 / 3 session view
        │   ├── history/
        │   │   └── page.tsx                        # Session History screen
        │   └── settings/
        │       ├── providers/page.tsx               # Settings → Providers (LLM keys)
        │       └── integrations/page.tsx             # Settings → Integrations (research/Notion/Langfuse)
        │
        ├── components/
        │   ├── council/
        │   │   ├── MemberTabs.tsx                   # Stage 1 tab view
        │   │   ├── RankingTable.tsx                  # Stage 2 anonymized ranking table
        │   │   ├── ChairmanReport.tsx                 # Stage 3 markdown report renderer
        │   │   └── CostMeter.tsx                       # always-visible cost meter
        │   ├── dashboard/
        │   │   ├── catalog.ts                        # json-render defineCatalog() — MetricCard, RankBar, ...
        │   │   ├── registry.tsx                       # json-render defineRegistry() — B&W React components
        │   │   └── DashboardRenderer.tsx                # thin wrapper around json-render's <Renderer>
        │   ├── settings/
        │   │   ├── ProviderKeyCard.tsx
        │   │   ├── ResearchProviderCard.tsx
        │   │   └── NotionConnectCard.tsx
        │   └── layout/
        │       ├── AppShell.tsx                      # header + sidebar + content frame (Section 12.2)
        │       └── SessionHistorySidebar.tsx
        │
        ├── lib/
        │   ├── api-client.ts                        # typed fetch client for the FastAPI backend
        │   ├── sse.ts                                 # SSE subscription helper (client-side Observer)
        │   └── theme/
        │       └── tokens.ts                          # greyscale ramp, spacing scale, type scale — single source of truth
        │
        ├── hooks/
        │   ├── useCouncilSession.ts                   # subscribes to CouncilState stream; exposes stage/data
        │   └── useDashboardSpec.ts                     # extracts the current dashboard_spec slice for the Renderer
        │
        └── styles/
            └── globals.css                            # CSS variables bound to theme/tokens.ts; enforces B&W only
```

**Why this layout matters:**
- Anyone can find "where does OpenRouter get called" in one place (`adapters/llm_providers/openrouter_adapter.py`) and know that swapping it out never touches `orchestration/` or `api/`.
- `domain/` has zero third-party imports, so the ranking/anonymization rules can be unit-tested with plain Python objects — no mocked HTTP calls needed.
- `tests/contract/` guarantees that any new provider (or a GitHub Models replacement, per Section 10.3) is a drop-in as long as it satisfies the same `ProviderAdapter` contract test suite.
- On the frontend, `components/dashboard/` is intentionally isolated from `components/council/` — the json-render catalog/registry is a self-contained module that could be extracted and reused in a future admin or analytics surface.

---

## 9. Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend framework | **FastAPI** (Python 3.11+) | Exposes REST + Server-Sent Events (SSE) for streaming stage progress to the frontend. |
| Agent orchestration | **LangGraph** (`StateGraph` + supervisor pattern) | Implements Section 6's graph exactly; built-in checkpointing (e.g., Postgres or SQLite checkpointer) enables resume-after-crash. |
| Model/tool abstraction | **LangChain** | Chat model wrappers, tool-calling scaffolding, and the LangChain callback handler used to feed Langfuse. |
| Observability | **Langfuse** (self-hosted or Langfuse Cloud) | One trace per council session; every node call is a nested span/generation; multi-agent graph view is native for LangGraph traces. Captures latency, token counts, and cost per model call. |
| Frontend | **React** (Next.js recommended) | Run via standard `npm install` then `npm run dev` for local development. |
| Dynamic dashboard rendering | **`@json-render/core` + `@json-render/react`** (Vercel Labs' Generative UI framework) | `npm install @json-render/core @json-render/react`. See Section 11.3. |
| UI styling | Strict **black & white** design system (see Section 12) | No color tokens anywhere except pure black/white/greyscale. |
| Model providers (exclusive allow-list) | **OpenRouter**, **NVIDIA NIM**, **GitHub Models** | See Section 10. No other provider may appear in the provider dropdown. |
| Live research (user's choice of provider) | **Tavily** *or* **Anakin API** (web search + scrape) | User picks one (or both) in Settings and supplies their own key for each. See Section 11.1. |
| Report storage | **Notion**, via **Notion MCP** | See Section 11.2. |
| Secrets | Encrypted at rest (e.g., Fernet/KMS-wrapped) in the backend's datastore; never logged, never sent to Langfuse. | |
| Datastore | PostgreSQL (sessions, state checkpoints, encrypted keys) | |

---

## 10. Model Providers — Exclusive, User-Supplied Keys

Synod deliberately restricts itself to **three** OpenAI-compatible inference providers. All three are added, edited, and validated exclusively from the **Settings → Providers** screen in the UI — never via server-side environment defaults, and never silently substituted.

### 10.1 OpenRouter
- Endpoint: `https://openrouter.ai/api/v1/chat/completions` (OpenAI-compatible schema; the same request/response shape used by the OpenAI SDK, just pointed at a different `base_url`).
- Model selection is a string like `"anthropic/claude-sonnet-4.5"` or `"openai/gpt-5.4"`; Synod should fetch the live catalog from OpenRouter's models endpoint so the UI dropdown is always accurate rather than hardcoded.
- Supports an optional `"plugins": [{"id": "web"}]` flag for provider-side web search — Synod does **not** rely on this for its own Research Sub-Agent (that's Tavily's/Anakin's job, per Section 11.1) but may expose it as an advanced per-member toggle later.
- Requires only the user's `OPENROUTER_API_KEY`, entered in-app.

### 10.2 NVIDIA NIM
- Endpoint: `https://integrate.api.nvidia.com/v1` — also OpenAI-compatible (`/chat/completions`), via NVIDIA's `build.nvidia.com` hosted catalog.
- Auth: an `nvapi-...` key the user generates for free on `build.nvidia.com`; NVIDIA's free developer tier currently grants a starting allotment of inference credits and a modest requests-per-minute ceiling — Synod's Orchestrator must respect provider-reported rate limits and back off gracefully rather than hammering retries.
- Model IDs are catalog strings such as `"meta/llama-3.3-70b-instruct"` or `"nvidia/nemotron-3-super-120b-a12b"`.

### 10.3 GitHub Models
- Endpoint: `https://models.github.ai/inference/chat/completions` (also OpenAI Chat-Completions compatible), authenticated with a GitHub Personal Access Token carrying `models: read`.

> ### ⚠️ CRITICAL PROVIDER RISK — READ BEFORE BUILDING
> GitHub confirmed on **July 1, 2026** that **GitHub Models is being fully retired on July 30, 2026** — this includes the playground, model catalog, inference API, and bring-your-own-key access, for **all** customers, with no exceptions for existing active usage. GitHub scheduled brownout drills on **July 16 and July 23, 2026** ahead of the hard cutoff. Because today's date is July 12, 2026, this provider will very likely be **non-functional before Synod ships**, or will die within weeks of launch.
>
> **Recommendation to stakeholders:** keep GitHub Models in the allow-list and in the provider-abstraction layer exactly as requested (so the architecture is provider-agnostic and future-proof), but:
> 1. Build the provider adapter interface so a fourth or replacement provider can be added by implementing one adapter class — do **not** hardcode "exactly 3 providers" into business logic, only into the UI allow-list, which is a one-line config change. (This is exactly what the Adapter + Factory patterns in Section 7.2 buy you.)
> 2. Ship a UI banner on the GitHub Models provider card noting the retirement date and linking to GitHub's changelog.
> 3. Confirm with the requester before/at launch whether GitHub Models should be swapped for a like-for-like OpenAI-compatible alternative (e.g., Azure AI Foundry, which GitHub itself points departing users toward) so the "three strict providers" requirement can still be satisfied post-July-30.
> This is flagged here rather than silently "fixed" because it materially affects a hard requirement in the original brief.

### 10.4 Provider Abstraction Layer (engineering note)
All three (and any future) providers are OpenAI-compatible chat-completions endpoints, so a single `ProviderAdapter` interface (base URL + auth header shape + model-list endpoint) is sufficient — Synod does **not** need three bespoke SDKs. LangChain's OpenAI-compatible chat model class can be pointed at any of the three base URLs with per-provider auth headers. Concretely, this is the Adapter + Factory pair from Section 7.2 living in `backend/app/adapters/llm_providers/`.

### 10.5 Key Handling Rules
- Keys are entered only in **Settings → Providers**, sent over TLS, encrypted at rest, and used only for that user's sessions.
- A "Test Connection" action performs a 1-token dry-run call and reports success/failure without ever displaying the key back to the UI.
- Keys are **never** included in Langfuse traces, logs, or the Notion archive.

---

## 11. Auxiliary Integrations

### 11.1 Live Web Search & Scraping — User-Selectable Provider (Tavily or Anakin)

Synod does not lock the Research Sub-Agent to a single search vendor. In **Settings → Integrations**, the user chooses which live-research provider(s) to enable and enters **their own API key** for each — Synod stores neither key server-side by default and never bills its own account. If both are configured, a per-session dropdown ("Research provider: Tavily / Anakin") lets the user pick which one powers that run; if only one is configured, it is used automatically and the picker is hidden.

**Option A — Tavily.** Tavily is a web-access API purpose-built for AI agents, authenticated with a `tvly-...` key, exposing `/search` (ranked, LLM-ready results with optional AI-generated answer and optional full raw content per source), `/extract` (clean Markdown/text from one or more known URLs), `/map` and `/crawl` (site-structure discovery), and a `/research` endpoint that runs an autonomous multi-step search-and-synthesize job and can stream progress over SSE. Tavily also ships an official `langchain-tavily` package, so it drops straight into the Research Sub-Agent as a LangChain tool with almost no glue code. Tavily's free tier includes a monthly credit allowance, which is enough for prototyping and light usage before the user needs to add billing on their own account.

**Option B — Anakin API.** Anakin.io provides an agent-oriented API surface for web work: URL scraping to Markdown/JSON/HTML, full-site crawling, and a **search API that returns full page content (not just links)**, plus an **agentic research mode** that runs its own plan → search → read → verify → answer-with-citations pipeline. Because Anakin's deeper crawl/agentic-research flows are async/job-based, the Research Sub-Agent should default to Anakin's lightweight synchronous search+read path and only fall back to job polling when the user has explicitly requested a deep-research pass.

**Provider abstraction.** Both providers are wrapped behind one internal `ResearchProviderAdapter` interface (`search(query) -> sources[]`, `extract(urls) -> content[]`) so the Research Sub-Agent's LangGraph node code is identical regardless of which vendor is active; only the adapter implementation differs. Whichever adapter runs, the output normalizes into the same `ResearchDigest` shape (query terms, source list with URLs/titles/snippets, synthesized summary) before being written into `CouncilState`, so Stage 1/Stage 3 prompts never need to know which search vendor produced the evidence.

### 11.2 Notion MCP — Report Archiving
Notion's **official hosted MCP server** exposes a small, AI-tuned toolset (page search, page read, page creation/append, in Notion-flavored Markdown) over the Model Context Protocol, authenticated via OAuth to the user's own workspace, with access limited to whatever pages/databases the user has explicitly shared with the integration. The **Notion Archivist Sub-Agent** connects as an MCP client (LangChain has first-class MCP adapter support to expose MCP tools as LangChain tools), and on a successful Stage 3 completion (only if the user has toggled "Archive to Notion" and connected their workspace), creates one new page per council session containing: the original query, the final Chairman report, the Stage 2 ranking table, and a collapsible appendix with every Stage 1 raw answer. The page URL is written back to `CouncilState.notion_page_url` and shown in the UI.

- Least-privilege by default: request **read + insert** capabilities only; do not request delete.
- The user must explicitly share a destination Notion page/database with the Synod integration before archiving is enabled in the UI (the Settings screen surfaces this as a one-click "Connect Notion" OAuth flow with a follow-up "Share a page with Synod" instruction, matching Notion's own guidance).

### 11.3 Dynamic Dashboard Rendering — `@json-render/core` + `@json-render/react`

All graphs and numerical readouts in Synod (Stage 2 ranking bars, aggregate score gauges, per-model latency/cost/token metrics, research-source counts) are rendered through **json-render**, Vercel Labs' Generative-UI framework, rather than a fixed set of hardcoded chart components. This is what makes the results dashboard "dynamic": the backend emits a small JSON **spec** describing which widgets to show and what data feeds them, and the frontend renders it live — new widget types, reordering, or added metrics ship as a backend change, with no frontend redeploy required.

**Install (frontend):**
```bash
npm install @json-render/core @json-render/react
```

**How it fits Synod's architecture:**
1. **Catalog** — a fixed, Zod-validated vocabulary of allowed dashboard components is defined once, e.g. `MetricCard` (label + numeric value + optional unit), `RankBar` (horizontal bar per Council Member, greyscale-only fill), `LatencyChart`, `CostGauge`, `TokenTable`, `SourceList`. Because the catalog is schema-constrained, the backend (or, later, a model) can only ever emit widgets Synod's designers have explicitly approved and styled for the black-and-white system.
2. **Registry** — each catalog component is mapped to a real, black-and-white-themed React implementation (`registry.tsx`), matching Section 12's design tokens exactly (no color props are exposed in any dashboard component's schema).
3. **Spec** — after Stage 2 (ranking) and again after Stage 3 (final report), the Decision Orchestrator's Ranking Aggregator / Chairman nodes build a small `dashboard_spec` object (flat `{ root, elements }` map, per json-render's React schema) containing that stage's metrics — e.g., one `RankBar` per Council Member bound to `aggregate_scores`, one `MetricCard` per member for latency/cost/tokens — and write it to `CouncilState.dashboard_spec`.
4. **Render** — the frontend's `<Renderer spec={dashboard_spec} registry={registry} />` call renders the dashboard as soon as the spec arrives over the SSE stream; because json-render supports progressive/streamed spec updates, the dashboard can grow widget-by-widget as Stage 1 responses land, rather than popping in all at once.
5. **State binding, not re-fetching** — numeric values are bound via json-render's state-path binding (`statePath: "/rankings/member_1/score"`) rather than baked into the spec as static numbers, so a widget can be wired to live-update if `CouncilState` changes mid-stream (e.g., a retry updates one member's latency) without the Orchestrator re-emitting the whole spec.

This keeps the "show graphs and numbers" requirement fully dynamic and backend-driven while still guaranteeing every rendered pixel obeys the strict black-and-white constraint, since the component registry is the single place color could ever be introduced — and it deliberately never accepts one.

---

## 12. UI/UX Design

### 12.1 Visual Language — Strict Black & White

- **No color anywhere** in the product chrome, charts, or data visualizations — pure `#000000`, `#FFFFFF`, and a constrained greyscale ramp for hierarchy, borders, disabled states, and hover states.
- Status/severity that would normally use color (success/error/warning) is communicated instead via **typography weight, icons, borders, and text labels** (e.g., an error state uses a bold border + an explicit "Failed" label + an X icon, never red).
- Typography-led hierarchy: a strong monospace or grotesk display face for session titles/model names (evokes a "minutes of the council" register), a clean humanist sans for body text.
- High contrast throughout for accessibility (WCAG AA minimum contrast even within a greyscale palette).

**Design tokens (single source of truth: `frontend/src/lib/theme/tokens.ts`):**

| Token group | Values | Used for |
|---|---|---|
| Greyscale ramp | `--grey-0` (#000) … `--grey-100` (#FFF) in 7 steps | Backgrounds, borders, text, dividers — the *only* color values allowed anywhere in `globals.css` or component styles. |
| Spacing scale | `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64px` | All margin/padding/gap values; no arbitrary pixel values in components. |
| Type scale | `12 / 14 / 16 / 20 / 24 / 32 / 40px`, two families (display + body) | Headings, body copy, metric numerals, code/model-id labels. |
| Radius scale | `0 / 4 / 8px` | Cards, buttons, inputs — deliberately small/sharp to keep the "council minutes" register rather than a soft consumer-app feel. |
| Elevation | Border-only (`1px solid --grey-30`) at rest; `2px solid --grey-0` on focus/active | No drop-shadow-as-color-substitute; hierarchy comes from border weight and spacing, not shadow color. |

### 12.2 Layout & Grid System

Synod uses a fixed **three-region app shell** on desktop, collapsing to a single-column stack on mobile (Section 12.7):

```
┌───────────────────────────────────────────────────────────────────┐
│  HEADER  — Synod wordmark · session title · cost meter · avatar    │
├───────────┬───────────────────────────────────────────────────────┤
│           │                                                       │
│  SIDEBAR  │                  MAIN CONTENT AREA                    │
│  (240px)  │        (New Session / Stage 1-3 / Settings)           │
│           │                                                       │
│  Session  │   ┌─────────────────────────────────────────────┐    │
│  History  │   │   Stage indicator strip (1 → 2 → 3)          │    │
│  list +   │   ├─────────────────────────────────────────────┤    │
│  New      │   │                                                │  │
│  Session  │   │        Primary content (tabs / table /        │  │
│  button   │   │        report / form) — 12-column grid,        │  │
│           │   │        content max-width 960px, centered        │  │
│           │   │                                                │  │
│           │   ├─────────────────────────────────────────────┤    │
│           │   │   Dynamic dashboard region (json-render)       │  │
│           │   │   — RankBar / MetricCard grid, 2–4 columns     │  │
│           │   └─────────────────────────────────────────────┘    │
└───────────┴───────────────────────────────────────────────────────┘
```

- The **12-column grid** (960px max content width, 24px gutters) governs the primary content region; the dashboard region below it uses its own responsive card grid (2 columns on tablet, up to 4 on wide desktop) so json-render's emitted widgets can reflow without the surrounding chrome changing.
- The **sidebar** is persistent on desktop, becomes a slide-over drawer on tablet/mobile (Section 12.7).
- The **header**'s cost meter and stage indicator are the only two elements visible on every screen of an active session — deliberately, so cost and progress are never more than a glance away.

### 12.3 Navigation Model

- **Primary navigation** lives in the sidebar: `New Session`, `History` (past sessions), `Settings` (Providers / Integrations sub-tabs). This is a flat, shallow model — no more than two levels deep anywhere in the app, since council sessions are the only real "content" and everything else is configuration.
- **Within an active session**, navigation is *linear and stage-gated*, not free-roaming: a stage indicator strip (`① First Opinions → ② Peer Review → ③ Chairman Report`) shows progress, and the user can click backward to review a completed stage but cannot skip forward past the current live stage — this mirrors the backend's own state machine (`CouncilState.stage`) exactly, so the UI can never claim to be "on Stage 3" while the backend is still on Stage 1.
- **Deep linking**: every session has a stable URL (`/sessions/{sessionId}`) that reopens directly onto whatever stage that session is currently at (or its final state, if done) — this is what session history links, Notion archive links, and Langfuse trace cross-links all point back to.

### 12.4 Component Hierarchy

The frontend's component tree mirrors the project structure in Section 8 directly:

```
<AppShell>                                  (layout/AppShell.tsx)
 ├─ <Header>                                  cost meter, stage strip
 ├─ <SessionHistorySidebar>                   (layout/SessionHistorySidebar.tsx)
 └─ <MainContent>
     ├─ NewSessionForm                        (app/page.tsx)
     ├─ <MemberTabs>                          (components/council/MemberTabs.tsx) — Stage 1
     ├─ <RankingTable> + <DashboardRenderer>  (components/council/RankingTable.tsx +
     │                                          components/dashboard/DashboardRenderer.tsx) — Stage 2
     ├─ <ChairmanReport> + <DashboardRenderer> (components/council/ChairmanReport.tsx +
     │                                          components/dashboard/DashboardRenderer.tsx) — Stage 3
     └─ <SettingsPanels>
         ├─ <ProviderKeyCard> × 3              (Settings → Providers)
         └─ <ResearchProviderCard> × 2 + <NotionConnectCard>  (Settings → Integrations)
```

`<DashboardRenderer>` is the one component that is *not* hand-written per screen — it is the same thin wrapper around json-render's `<Renderer spec={dashboardSpec} registry={registry} />` reused on both the Stage 2 and Stage 3 screens (and any future screen), fed by `useDashboardSpec()`.

### 12.5 Core Screens (detailed)

1. **New Session** — query input (multi-line, auto-grow textarea), Council Member picker (provider + model chips, 3–6 selectable), optional Chairman pin, Research toggle (with provider sub-picker if both Tavily and Anakin are configured), Notion-archive toggle, "Convene the Council" primary action (disabled until at least 3 members are selected, with inline validation text — not a color change — explaining why).
2. **Stage 1 — First Opinions (Tab View)** — one tab per Council Member, each streaming its answer independently as it arrives via SSE; a per-tab status indicator (`Streaming… / Done / Failed`, text-based, not colored) sits next to each model's name; the stage indicator strip shows `① First Opinions` as active.
3. **Stage 2 — Peer Review** — an anonymized ranking table (`Member A..N`) with each member's ranking + justification, and a **json-render-driven** dashboard of `RankBar` + `MetricCard` widgets (aggregate score, latency, token cost per member), rendered live from the backend-emitted `dashboard_spec` (Section 11.3) — all in greyscale, never colored charts.
4. **Stage 3 — Final Report** — the Chairman's synthesized Markdown report, an "agreement / disagreement" summary strip, inline citations, a de-anonymized "who said what" reveal (identity is only ever revealed to the *human*, never back to the models), and an updated dashboard reflecting final session totals (total cost, total tokens, wall-clock time, research-source count if enabled).
5. **Session History** — a left sidebar list of past council sessions (searchable by query text), each linking to its full trace in Langfuse and its Notion page if archived; each row shows the session's stage-3 "headline" (first line of the Chairman report) as a preview.
6. **Settings → Providers** — the three provider cards (OpenRouter / NVIDIA NIM / GitHub Models — with the retirement banner per Section 10.3), each with a masked key field + "Test Connection."
7. **Settings → Integrations** — a **Research Providers** panel with two independent cards, **Tavily** (masked `tvly-...` key field + Test Connection) and **Anakin** (masked API key field + Test Connection) — either, both, or neither can be enabled; when both are enabled the per-session provider picker appears (Section 11.1). Below that: Notion "Connect Workspace" OAuth button, and Langfuse project keys (public/secret) for self-hosted observability.

### 12.6 UI States (loading / empty / error / success)

Every data-bearing region in Synod defines all four states explicitly — the frontend never shows a bare spinner with no text, nor a blank screen with no explanation:

| State | Treatment |
|---|---|
| **Loading** | A skeleton (grey-ramp block, no shimmer color) matching the shape of the eventual content, plus a short text label ("Waiting for Council Seat 2…") — never a bare spinner. |
| **Empty** | An explicit empty-state message + a single primary action (e.g., History screen with no past sessions shows "No sessions yet" + a `New Session` button), never a blank white page. |
| **Partial / degraded** | When some Council Members failed but others succeeded (Section 6.6), the affected tab shows a bold-bordered "Failed — excluded from ranking" panel with the raw error class (timeout / auth / rate-limit), and the rest of the UI proceeds normally. |
| **Error (session-level)** | If all members fail Stage 1, the whole session view shows one clear, actionable message (e.g., "All Council Members failed — check your provider keys in Settings") rather than a silent hang, matching Section 6.6. |
| **Success** | Stage 3's report view is the terminal success state; a persistent "Archived to Notion ✓ (text label, not a green check)" line appears once archiving completes. |

### 12.7 Responsive Behavior

- **Desktop (≥1200px)** — full three-region shell (Section 12.2); dashboard grid at up to 4 columns.
- **Tablet (768–1199px)** — sidebar collapses into a hamburger-triggered slide-over drawer; dashboard grid drops to 2 columns; Stage 1 tabs become a horizontally-scrollable strip instead of full-width tabs.
- **Mobile (<768px)** — single-column stack: header (compact, cost meter moves into a tappable summary chip) → stage strip → primary content → dashboard cards stacked 1-per-row → sidebar accessible only via drawer. Council Member tabs become a vertical accordion instead of horizontal tabs, since 3–6 full model responses do not fit comfortably side-by-side on a phone width.

### 12.8 Interaction & Motion Principles

- Every stage transition is streamed via SSE so the user watches the council "in session" rather than staring at a spinner.
- Since color cannot carry meaning, **motion and weight** do the work color normally would: a newly-arrived Stage 1 tab briefly increases border weight (not color) and fades in; a failed member's tab gets a persistent bold border rather than a flash of red.
- A visible, always-present **cost meter** (estimated token spend so far this session, in the user's own provider currency) — critical since parallel N-model fan-out plus a second peer-review pass roughly doubles-to-triples token spend versus a single-model chat.
- Keyboard-first affordances (⌘/Ctrl+Enter to convene, `[` / `]` to move between Stage-1 tabs).

### 12.9 Accessibility

- WCAG AA contrast is verified for every greyscale pairing actually used (not just black-on-white) since several UI states rely on mid-grey borders/backgrounds for hierarchy.
- Every non-text status signal (Failed / Streaming / Archived) ships with a real text label, not an icon or color alone — this is a direct consequence of the black-and-white constraint and doubles as a screen-reader-friendly design for free.
- Full keyboard navigability across the stage-gated flow (Section 12.3), including the json-render-rendered dashboard widgets, which expose the same semantic HTML/ARIA roles as any hand-written component since the registry (Section 8) controls their implementation.

---

## 13. API Design (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/providers/keys` | Store/update an encrypted provider API key (OpenRouter / NVIDIA NIM / GitHub Models). |
| `POST` | `/api/v1/providers/test` | Dry-run a stored key against its provider. |
| `GET` | `/api/v1/providers/{provider}/models` | Live model catalog for the picker UI. |
| `POST` | `/api/v1/council/sessions` | Create + kick off a new council run (`user_query`, `members[]`, `chairman_member_id?`, `research_enabled`, `research_provider?: "tavily" \| "anakin"`, `archive_to_notion`). |
| `GET` | `/api/v1/council/sessions/{session_id}/stream` | SSE stream of `CouncilState` deltas — including incremental `dashboard_spec` updates — as the graph executes. |
| `GET` | `/api/v1/council/sessions/{session_id}` | Full current state / final report / current `dashboard_spec`. |
| `GET` | `/api/v1/council/sessions` | List past sessions for the user. |
| `POST` | `/api/v1/integrations/notion/connect` | Kick off Notion OAuth for MCP. |
| `POST` | `/api/v1/integrations/notion/publish/{session_id}` | Manually (re-)publish a session's report to Notion. |
| `POST` | `/api/v1/integrations/research/tavily/keys` | Store the user's Tavily (`tvly-...`) API key. |
| `POST` | `/api/v1/integrations/research/anakin/keys` | Store the user's Anakin API key. |
| `POST` | `/api/v1/integrations/research/test` | Dry-run a stored research-provider key (`provider: "tavily" \| "anakin"`). |
| `GET` | `/api/v1/observability/trace/{trace_id}` | Redirect/link to the Langfuse trace UI for a session. |

---

## 14. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **GitHub Models full retirement on July 30, 2026** (see 10.3) | **High / imminent** | Provider-agnostic Adapter + Factory (Section 7.2) so the provider can be swapped with a config change, not a rewrite; surface a UI warning now; confirm replacement provider with stakeholders before/at launch. |
| Parallel N-model + 2-pass (Stage 1 + Stage 2) fan-out multiplies token cost | Medium | Visible cost meter; per-session cost ceiling with a hard stop; let users pick 3 members instead of 6 for cheaper runs. |
| Anonymization leakage — a model recognizes another model's "voice"/formatting tics despite label-stripping | Medium | Redactor node normalizes formatting (heading style, list markers, disclaimers) before Stage 2 hand-off; treat any residual leakage as a known limitation disclosed in-product, not a promise of perfect anonymity. |
| Provider rate limits (e.g., NVIDIA NIM's free-tier RPM ceiling) stall a run | Medium | Token-bucket rate limiter (Section 7.3) + Orchestrator-level backoff + queueing; clear "rate limited, retrying" state surfaced to the user instead of a silent hang. |
| Chairman bias toward its own earlier Stage-1 answer | Low–Medium | Chairman is prompted only with de-anonymized *aggregate* rankings and justifications, not "which one was mine"; default Chairman selection favors the *highest peer-ranked* member rather than a fixed model, reducing self-preference incentives. |
| Single Orchestrator node as a bottleneck/single point of failure | Low | LangGraph checkpointing (Unit of Work, Section 7.2) allows resume-from-last-good-stage; horizontal scaling of the stateless FastAPI/worker layer (Section 7.3) is independent of the Orchestrator logic. |
| Secrets exposure via logs/traces | High if it occurs | Explicit allow-list scrubber on every Langfuse span; keys never enter LangChain message payloads, only HTTP client auth headers; `KeyVault` Singleton is the only place plaintext keys briefly exist in memory. |
| Notion MCP over-broad access | Medium | Least-privilege OAuth scopes; user must explicitly share a destination page/DB, matching Notion's own recommended MCP posture. |
| Dual research-provider paths (Tavily / Anakin) drift in output shape, breaking downstream prompts | Low–Medium | Both adapters normalize into the same `ResearchDigest` shape (Section 11.1) before touching `CouncilState`; the shared `tests/contract/` suite (Section 8) runs against both providers in CI. |
| A malformed or unexpected `dashboard_spec` crashes the live dashboard | Low | json-render's catalog is Zod-validated — only pre-registered, pre-styled B&W components can ever appear in a spec; an invalid spec fails a schema check server-side before it is ever streamed to the client. |
| Retry storms against a provider that is genuinely down (e.g., GitHub Models mid-brownout) | Medium | Circuit Breaker (Section 7.2) trips after N consecutive failures per provider per session, stopping further calls immediately rather than retrying into a known outage. |

---

## 15. Success Metrics

- **Time-to-first-report**: median wall-clock time from "Convene" to Stage 3 completion for a 4-member council (target: < 60s for non-research runs).
- **Council completion rate**: % of sessions that reach `stage: done` without unrecoverable error.
- **Anonymity-adjusted ranking spread**: variance in aggregate scores across members (sanity check that peer review isn't just unanimous "everyone's fine").
- **Archival adoption**: % of completed sessions that are pushed to Notion.
- **Cost per session** vs. a naive "ask every model separately, no synthesis" baseline (Synod should be transparent, not necessarily cheaper — but the meter must be accurate).

---

## 16. Roadmap / Phased Delivery

| Phase | Scope |
|---|---|
| **Phase 0 — Foundations** | Backend hexagonal skeleton per Section 8 (`domain/`, `ports/`, empty `adapters/`), FastAPI app + DI wiring, LangGraph `StateGraph` scaffold with stub nodes, OpenRouter adapter first, black-and-white design tokens (`tokens.ts`), Next.js shell, `@json-render/core`/`@json-render/react` installed with an initial B&W component catalog (`MetricCard`, `RankBar`). |
| **Phase 1 — MVP Council** | Stage 1 (parallel first opinions) + Stage 3 (Chairman synthesis) only, no peer-review yet; NVIDIA NIM + GitHub Models adapters added behind the same `ProviderAdapter` port; Settings → Providers with encrypted key storage (`KeyVault`) and Test Connection. |
| **Phase 2 — Full Deliberation** | Stage 2 anonymized peer review + Ranking Aggregator (Strategy pattern); session history; SSE streaming UI end-to-end (Section 12.5–12.6 states implemented); first live `dashboard_spec` rendering (ranking bars + per-member metrics). |
| **Phase 3 — Research & Archiving** | Research Sub-Agent with both Tavily and Anakin adapters behind the shared `ResearchProviderAdapter` port + Settings UI for both keys; Notion MCP Archivist; Langfuse tracing (Decorator pattern) wired through every node; dashboard extended with research-source and cost/latency widgets. |
| **Phase 4 — Hardening** | Circuit Breaker + rate-limit/backoff handling per provider, cost ceilings, resumable checkpointing, full accessibility pass on the B&W UI (Section 12.9), responsive pass (Section 12.7), GitHub Models contingency swap if not already resolved. |

---

## 17. Glossary

- **Decision Orchestrator** — the single LangGraph supervisor node that owns `CouncilState` and routes execution; the only "brain" allowed to decide what happens next.
- **Council Member** — one configured (provider, model) pair participating in a session.
- **Chairman** — the Council Member elected (by default, top Stage-2 score) to write the final synthesized report.
- **Anonymization map** — the server-side-only mapping from real member identity to a randomized label, used exclusively during Stage 2 and never exposed to the models outside that stage.
- **CouncilState** — the single structured state object all nodes read/write; the sole channel of inter-agent communication.
- **Port** — a domain-defined interface (e.g., `ProviderAdapter`, `NotionPort`) that the core depends on but never implements; see Section 7.1.
- **Adapter** — a concrete implementation of a port for one specific external system (e.g., `OpenRouterAdapter`, `TavilyAdapter`); see Section 7.1–7.2.
- **`dashboard_spec`** — the backend-emitted json-render `{root, elements}` object describing the current live dashboard; the only place numeric/graph UI is defined.
- **Research provider** — whichever of Tavily or Anakin the user has enabled and selected for a given session's Research Sub-Agent calls.
- **json-render catalog / registry / spec** — the three-part contract (allowed component vocabulary → real React implementations → the JSON instance describing one screen) that makes Synod's dashboards dynamic without sacrificing the black-and-white design constraint.

---

## 18. Appendix — Sample Chairman Prompt Skeleton

```
You are the Chairman of a council of independent AI reviewers.
You will receive:
1) The original question.
2) Each council member's independent first answer (identified).
3) Each member's blind peer ranking + justification of an anonymized answer set.
4) An aggregate score per member.
5) (Optional) A research digest with cited sources.

Write ONE final answer that:
- Directly answers the question.
- Notes explicitly where the council agreed and where it diverged.
- Prefers claims backed by the research digest's citations over unsupported assertions.
- Does not simply repeat the highest-ranked answer verbatim — synthesize.
- Ends with a short "Dissenting views" section if aggregate scores were close or justifications conflicted sharply.
```

---

*End of PRD.*