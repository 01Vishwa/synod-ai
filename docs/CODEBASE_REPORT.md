# Synod Codebase Report

A technical architecture reference for engineers working on this codebase. Every claim below was verified against the current source tree, not against prior drafts of this document.

---

## Architecture: Hexagonal (Ports & Adapters)

```
app/
├── domain/            # framework-free business rules and state — no I/O
│   ├── council_state.py
│   ├── identity.py
│   └── ports/         # abstract interfaces the domain depends on
│       ├── provider_adapter.py
│       ├── research_adapter.py
│       ├── observability_port.py
│       ├── session_repository.py
│       └── notion_port.py
│   └── rules/         # pure functions
│       ├── ranking.py
│       └── anonymization.py
├── orchestration/      # LangGraph state machine that drives a session
│   ├── graph.py
│   ├── nodes/
│   ├── runner.py
│   ├── utils.py
│   └── context.py
├── adapters/           # concrete implementations of domain/ports
│   ├── llm_providers/  (openrouter, nvidia_nim, factory)
│   ├── research_providers/ (tavily, anakin, factory)
│   ├── observability/  (langsmith — real; langfuse — empty file)
│   ├── persistence/    (models, database, postgres_session_repository)
│   ├── security/       (key_vault)
│   └── notion/
├── application/         # thin use-case layer (Notion publish command/handler/service)
├── api/v1/              # FastAPI routers, schemas, deps
└── core/                # cross-cutting: config, event bus, llm router, circuit breaker,
                          # rate limiter, exceptions, logging
```

The dependency direction is inward: `api/` and `adapters/` depend on `domain/`, never the reverse. `orchestration/` depends on `domain/` (for `CouncilState`, rules) and on the ports (for `deps.repository`, `deps.vault`, etc.), receiving concrete adapter instances via a `GraphDependencies` container injected through LangGraph's `config["configurable"]["deps"]` rather than importing adapters directly.

---

## LangGraph Execution Graph

`app/orchestration/graph.py` builds a `StateGraph(OrchestratorState)`, where `OrchestratorState(CouncilState)` marks four fields with LangGraph's `Annotated[list, operator.add]` reducer — `stage_1_responses`, `stage_2_responses`, `rankings`, `errors` — so that parallel branches append to these lists instead of overwriting each other.

**Nodes** (`add_node(name, fn)`):

| Node name | Function | Purpose |
|---|---|---|
| `research` | `research_node` | Optional live web research (Tavily/Anakin), runs before Stage 1 |
| `stage_1_setup` | `setup_stage_1` (in `graph.py`) | Prepares Stage 1 fan-out |
| `stage_1_draft` | `stage_1_node` | One member's independent first answer |
| `validate_stage_1` | `validate_stage_1` (in `graph.py`) | Computes `successful_member_ids`/`excluded_member_ids`, checkpoints |
| `stage_2_setup` | `setup_stage_2` (in `graph.py`) | Builds the anonymization map, publishes `peer_review.started` |
| `stage_2_review` | `stage_2_node` | One successful member's blind peer review + ranking |
| `validate_stage_2` | `validate_stage_2` (in `graph.py`) | Marks degraded/failed status if no valid reviews |
| `stage_3_setup` | `setup_stage_3` (in `graph.py`) | Computes Borda-count `aggregate_scores` |
| `validate_chairman` | `validate_chairman` (in `graph.py`) | Resolves the effective chairman, with fallback policy |
| `stage_3_synthesis` | `stage_3_node` | Chairman's final report |
| `dashboard_build_s2` | `dashboard_builder_node` | Builds a json-render dashboard spec after Stage 2 |
| `dashboard_build_s3` | `dashboard_builder_node` (same function, reused) | Merges Stage 3 widgets on top of the Stage 2 spec |
| `archive` | `notion_archivist_node` | Publishes to Notion if `archive_to_notion` is set |
| `finish` | `finish_session` (in `graph.py`) | Finalizes stage/status, ends the observability trace |

`app/orchestration/nodes/archive.py` defines a separate `archive_node` function that is **not wired into the graph at all** — it is dead code from an earlier implementation, superseded by `notion_archivist_node.py`.

**Topology:**

```
START --(should_research)--> research | stage_1_setup
research --> stage_1_setup
stage_1_setup --(route_stage_1, Send fan-out: 1 per member)--> stage_1_draft
stage_1_draft --> validate_stage_1                              [fan-in]
validate_stage_1 --(route_after_stage_1)--> finish | stage_3_setup | stage_2_setup
    # finish if 0 successful members; stage_3_setup directly if exactly 1 (Stage 2 skipped);
    # stage_2_setup if >=2 successful members
stage_2_setup --(route_stage_2, Send fan-out: 1 per successful member)--> stage_2_review
stage_2_review --> dashboard_build_s2                            [fan-in]
dashboard_build_s2 --> validate_stage_2
validate_stage_2 --> stage_3_setup                                # unconditional — proceeds even if 0 valid reviews
stage_3_setup --> validate_chairman
validate_chairman --(route_after_chairman_validation)--> finish | stage_3_synthesis
stage_3_synthesis --> dashboard_build_s3
dashboard_build_s3 --> archive
archive --> finish
finish --> END
```

Parallel fan-out (LangGraph `Send` API) happens at exactly two points: Stage 1 (one `Send("stage_1_draft", task)` per configured council member) and Stage 2 (one `Send("stage_2_review", task)` per member that *survived* Stage 1). Everything else — research, every `setup_*`/`validate_*` node, both dashboard-builder invocations, chairman synthesis, archiving, and finish — runs sequentially, once.

The graph is compiled with `builder.compile()` and **no `checkpointer` argument** — there is no LangGraph-native checkpointing. Durability is entirely application-level (see Runner below).

---

## Event Bus & SSE Streaming

`app/core/event_bus.py` implements `SessionEventBus`: an in-memory, per-session, asyncio pub/sub with one `asyncio.Queue` per subscriber (default `maxsize=1000`, publishes drop silently on a full queue rather than blocking). A module-level registry (`get_or_create_bus`, `get_bus`, `close_bus`) keys buses by `session_id`.

15 frozen dataclasses make up the `SessionEvent` union, each carrying a `ClassVar[str] event_type` string constant plus `session_id` and event-specific fields: `MemberQueued`, `MemberStarted`, `ProviderConnecting`, `FirstToken`, `StreamChunk`, `MemberCompleted`, `MemberFailed`, `PeerReviewStarted`, `PeerReviewProgress`, `RankingUpdated`, `ChairmanStarted`, `ChairmanStreamChunk`, `ChairmanCompleted`, `SessionCompleted`, `SessionFailed`. Of these, `MemberQueued`, `MemberStarted`, and `RankingUpdated` are defined but never published by any current orchestration node — reserved/unused.

Flow: an orchestration node (e.g. `stage_1_node`) calls `bus.publish(SomeEvent(...))`. The SSE endpoint (`GET /sessions/{id}/stream` in `sessions.py`) calls `bus.subscribe()` and forwards each event to the browser as `_event_to_sse(event)`, which serializes via `dataclasses.asdict()` plus a manually re-injected `event_type` field, framed as `{"event": event.event_type, "data": json.dumps(payload)}`. The stream ends when a `SessionCompleted`/`SessionFailed` event arrives. If no bus exists yet (or the session already finished before the client connected), the endpoint falls back to polling the DB every 5s for up to 300s. See [docs/api-contract.md](api-contract.md) for the full per-event payload table.

---

## State Management: CouncilState

`app/domain/council_state.py` defines `CouncilState` as a `TypedDict`, plus sub-record TypedDicts `CouncilMemberConfig`, `MemberResponse`, `RankingEntry`, `ResearchDigest`.

| Field | Type | Purpose |
|---|---|---|
| `session_id` | `str` | Identity |
| `user_id` | `str` | Supabase auth.users UUID — tenant isolation |
| `trace_id` | `str` | LangSmith/Langfuse trace id |
| `user_query` | `str` | The user's question |
| `members` | `list[CouncilMemberConfig]` | Configured council seats |
| `stage` | `Literal["stage_1","stage_2","stage_3","archiving","done","error"]` | Graph control state |
| `research_enabled` | `bool` | Research toggle |
| `research_provider` | `Optional[Literal["tavily","anakin"]]` | Chosen research provider |
| `research_digest` | `Optional[ResearchDigest]` | Research evidence gathered before Stage 1 |
| `stage_1_responses` | `list[MemberResponse]` | First Opinions outputs |
| `anonymization_map` | `dict[str,str]` | `member_id → anonymized_label`; server-side only, stripped from SSE |
| `stage_2_responses` | `list[MemberResponse]` | Blind peer review outputs |
| `rankings` | `list[RankingEntry]` | Peer review ballots |
| `aggregate_scores` | `dict[str,float]` | `member_id → normalized Borda score` |
| `chairman_member_id` | `str` | Pinned chairman, if any |
| `final_report_md` | `Optional[str]` | Stage 3 synthesis |
| `citations` | `list[dict]` | Always `[]` currently — citation extraction is unimplemented |
| `archive_to_notion` | `bool` | Gates the archive node |
| `notion_page_url` | `Optional[str]` | Archived page URL |
| `archive_status` | `Optional[str]` | `"done"` \| `"failed"` \| `"skipped"` |
| `archive_error` | `Optional[str]` | Structured archive error |
| `dashboard_spec` | `Optional[dict]` | json-render spec from `dashboard_builder_node` |
| `errors` | `list[dict]` | `{member_id, stage, message, timestamp}` entries |
| `session_status` | `Optional[Literal["pending","running","completed","degraded","failed"]]` | Overall status |
| `stage_1_status`/`stage_2_status`/`stage_3_status` | same status literal set | Per-stage status |
| `terminal_error` | `Optional[dict]` | `{code, message}` |
| `successful_member_ids` | `Optional[list[str]]` | Members that survived Stage 1 |
| `excluded_member_ids` | `Optional[list[str]]` | Members excluded (error or empty response) |
| `effective_chairman_id` | `Optional[str]` | Actual chairman used (may differ from pinned) |
| `created_at`/`updated_at` | `str` | ISO-8601 timestamps |

Helpers: `STAGE_ORDER = ["stage_1","stage_2","stage_3","archiving","done"]`, `stage_index(stage)`, `is_terminal(stage)` (true for `"done"`/`"error"`).

`OrchestratorState(CouncilState)` (in `graph.py`) is the actual graph-runtime type — it overrides `stage_1_responses`, `stage_2_responses`, `rankings`, `errors` with `Annotated[list, operator.add]` so parallel `Send` branches append rather than clobber.

---

## Security Model

**KeyVault** (`app/adapters/security/key_vault.py`): Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256, per the module's own docstring). `KeyVault.instance()` lazily builds a process singleton from `settings.CREDENTIAL_ENCRYPTION_KEY`, raising `KeyVaultError` if the value isn't valid Fernet key material. `encrypt`/`decrypt` operate on UTF-8 strings; `decrypt` raises `KeyVaultError` on `InvalidToken` (tampered/wrong-key ciphertext). Only user-supplied provider/research/Notion credentials are ever encrypted this way — plaintext keys are never persisted (enforced by storing only `ciphertext_b64` on `ProviderKeyModel`).

**JWT verification** (`app/api/v1/deps.py`): `get_current_user_id` verifies a Supabase-issued JWT via ES256 against Supabase's JWKS endpoint (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, cached via `PyJWKClient`), checking issuer `{SUPABASE_URL}/auth/v1` and audience `"authenticated"`. `get_current_user_id_sse` is a variant for the SSE route that also accepts the token as a `?token=` query param (since `EventSource` can't set custom headers). Both raise structured 401s (`missing_token`, `token_expired`, `invalid_audience`, `invalid_issuer`, `invalid_token`).

**RLS:** `set_rls_context` (in `deps.py`) best-effort sets the Postgres `request.jwt.claims` session config from the verified token, intended to activate Supabase Row-Level Security policies at the DB level. It swallows all exceptions — actual tenant isolation is *also*, and more reliably, enforced in application code: every repository query filters by both `session_id` and the authenticated `user_id` (see `PostgresSessionRepository`), and `app/domain/identity.py`'s `require_uuid` gate is called before any identity value touches SQL.

**Key/PII scrubbing:** the SSE `state_snapshot` event explicitly excludes `anonymization_map`, `user_id`, and `_execution_status` before serialization (`_STATE_DELTA_EXCLUDE` in `sessions.py`). `app/domain/rules/anonymization.py`'s `redact_identity()` regex-scrubs model self-disclosure (provider/brand names, "I am a large language model", training-cutoff mentions) out of Stage 2 peer-review text so a model can't out itself by name. `LangSmithTracer` explicitly omits `user_id` from trace metadata (commented in the adapter as an intentional PII decision).

---

## Provider Adapters

Both LLM adapters are OpenAI-SDK-based (`AsyncOpenAI`), pass the API key per-call via `extra_headers={"Authorization": f"Bearer {api_key}"}` rather than baking it into the shared client, report `cost_usd=0.0` always (neither provider returns cost data), and share the same error mapping: SDK `AuthenticationError`→domain `AuthenticationError`, SDK `RateLimitError`→domain `RateLimitError`, timeout→`ProviderTimeoutError`, other `APIError`→`ProviderError` (retryable if `status_code >= 500`).

| | OpenRouter | NVIDIA NIM |
|---|---|---|
| Base URL | `https://openrouter.ai/api/v1` | `https://integrate.api.nvidia.com/v1` |
| Auth header | `Authorization: Bearer <key>` | `Authorization: Bearer <key>` (nvapi-...) |
| Model ID format | OpenRouter slug, e.g. `anthropic/claude-sonnet-4.5`; free-tier models end in `:free` | NIM slug, e.g. `meta/llama-3.1-8b-instruct` |
| Timeout | `connect=10s`, `read=90s` if `:free` else the call's `timeout_s`, `write=10s`, `pool=5s`; shared client default `120s` | identical pattern |
| `validate_key()` | Calls `chat()` with `model_id=settings.OPENROUTER_VALIDATION_MODEL` (default `openai/gpt-4o-mini`), `max_tokens=1`, `timeout_s=8`, wrapped in an outer `asyncio.wait_for(..., 10.0)` | Calls `chat()` with `model_id=settings.NVIDIA_NIM_VALIDATION_MODEL` (default `meta/llama-3.1-8b-instruct`), same `max_tokens=1`/`timeout_s=8`/outer 10s pattern |

`ProviderAdapterFactory` (`factory.py`) caches one instance per provider string; `_build()` `match`es `"openrouter"`/`"nvidia_nim"` and raises `DomainValidationError` for anything else. Its docstring mentions `"github_models"` as a third supported provider, but that is stale — `github_models` is not implemented in `_build()` or `supported_providers()`.

**Research adapters** (`app/adapters/research_providers/`): `TavilyAdapter` calls the real, documented Tavily API (`POST /search`, `POST /extract` against `https://api.tavily.com`, `Authorization: Bearer tvly-...`). `AnakinAdapter` calls `POST /websearch` and `POST /scrape` against `https://api.anakin.ai/v1` with an `X-Anakin-Api-Key` header — its own source comment flags the base URL as provisional ("update if the provider publishes a versioned endpoint"), so treat Anakin as implemented-against-an-assumed-shape rather than confirmed-stable. Both adapters' `validate_key()` does a real 1-result probe search and returns a bool rather than raising.

---

## Test Architecture

18 test files, **155 test cases, all passing** as of the last run (`PYTHONPATH=. python -m pytest tests/ -q`, ~20s, one cosmetic `AsyncMock` warning).

- **`tests/contract/`** (1 file, `test_member_id_contract.py`) — locks in the `member_id` regex contract (`^member_[a-z0-9]+$`) on `SessionCreateRequest`, including chairman-selection edge cases and backward-compat with older numeric IDs.
- **`tests/integration/`** (1 file, `test_sessions_endpoint.py`) — full `POST /sessions` request/response behavior via `TestClient` with auth/repo/tracer/runner dependency-overridden; covers 201 paths, chairman validation, 401/422 error paths.
- **`tests/unit/`** (16 files) covering, module by module: identity propagation and commit ordering in the runner and graph routing (`test_council_execution_identity.py`); circuit breaker fail-fast behavior, LLM router routing, Borda-count exclusion (`test_council_orchestration_fixes.py`); dashboard spec validation (`test_dashboard_safety.py`); the event bus pub/sub contract (`test_event_bus.py`); the `ProviderKeyModel.ciphertext_b64` column-name regression (`test_fetch_decrypted_key.py`); Fernet encryption round-trips (`test_key_vault.py`); LangSmith trace finalization datetime handling (`test_langsmith_trace_finalization.py`); the Notion OAuth router (`test_notion_router.py`); the identity-redaction regex rules per provider (`test_redact_identity.py`); the research-keys router's `ciphertext_b64` regression (`test_research_router.py`); runner commit/rollback semantics (`test_runner_commit.py`); the `chairman_member_id` schema field naming regression (`test_session_create_request_schema.py`); SSE terminal-event shapes (`test_sse_terminal_events.py`); Stage 1 node streaming/error handling (`test_stage_1_node.py`); Stage 2 candidate exclusion (`test_stage_2_exclusion_fixes.py`); and the OpenRouter/NVIDIA NIM streaming adapters (`test_streaming_adapters.py`).

Adding a new LLM provider adapter should follow the pattern exercised by `test_streaming_adapters.py`: implement the `ProviderAdapter` ABC (`chat`, `stream_chat`, `list_models`, `validate_key`), map SDK-specific exceptions onto the domain exceptions in `app/core/exceptions.py` (`AuthenticationError`, `RateLimitError`, `ProviderTimeoutError`, `ProviderError`), register it in `ProviderAdapterFactory._build()`, and add equivalent streaming/auth-error/timeout test cases.

---

## Known Technical Debt

- **Alembic is completely absent.** `alembic.ini` and any migrations directory have been removed from the repo (confirmed via `git status` and filesystem search). `database.py`'s own docstring for `create_all_tables()` says production should use `alembic upgrade head`, but no such tooling currently exists — the only working schema-creation path is `create_all_tables()`, gated to `ENVIRONMENT=development`.
- **`app/adapters/observability/langfuse_tracer.py` is a 0-byte empty file.** No `LangfuseTracer` class exists anywhere in the codebase (confirmed via grep), despite `LANGFUSE_TRACING`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST` all being live config fields, and a frontend `integrationsApi.saveLangfuseKeys()` client method with no UI consumer. LangSmith is the only implemented tracer.
- **`app/orchestration/nodes/archive.py` (`archive_node`) is dead code** — not referenced anywhere in `graph.py`; superseded by `notion_archivist_node.py`, which is the function actually wired to the `"archive"` graph node.
- **`sessions.py` defines `_emit_terminal()` with no call site** inside `_stream_events` — appears to be vestigial from an earlier SSE implementation.
- **Three event types are defined but never emitted**: `MemberQueued`, `MemberStarted`, `RankingUpdated` exist in the `SessionEvent` union in `event_bus.py` but no orchestration node currently publishes them.
- **`citations` is always `[]`** — Stage 3's citation-extraction logic is referenced in a comment but not implemented; the field exists on `CouncilState`/`SessionResponse` and is always returned empty.
- **`ProviderAdapterFactory`'s docstring references `"github_models"`** as a supported provider even though it was removed from `_build()`/`supported_providers()` — only `openrouter` and `nvidia_nim` work.
- **SSE fallback polling** interval is 5.0s with a 300s idle timeout (`_stream_events` in `sessions.py`) — used only when no live event bus exists for the session (session already finished, or the bus hasn't been created yet by the running graph).
- **Research-key validation asymmetry**: `POST /providers` validates the key live before storing; `POST /research/keys` does not — it persists unconditionally with `last_test_ok=None`. Worth reconciling if this wasn't an intentional design choice.
