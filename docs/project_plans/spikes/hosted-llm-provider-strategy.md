---
schema_version: 2
doc_type: spike
title: "Hosted LLM Provider Strategy — Findings & Design"
description: "Resolves RQ-1..RQ-7 for CCDash's hosted-LLM strategy. Recommends keeping httpx behind a provider-agnostic seam with the Anthropic wire format as the hosted lane (ICA-compatible); rejects Agent SDK, OpenAI SDK, and a bare provider SDK. Settles session_embeddings ownership with code evidence."
status: completed
created: 2026-08-06
updated: 2026-08-06
completed_date: 2026-08-06
feature_slug: hosted-llm-provider-strategy
charter_ref: docs/project_plans/spikes/hosted-llm-provider-strategy-charter.md
open_questions_ref: docs/project_plans/spikes/hosted-llm-provider-strategy-open-questions.md
prd_ref: null
plan_ref: null
itt_node_id: node_01KZCA2MAA0K0TWEPW0KZGC4WF
intenttree_workspace: ws_01KV8VMWX9EJ6VDQKEBMYQZRXG
related_documents:
  - docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
  - docs/guides/redaction-tuning.md
  - docs/guides/aar-review-loop.md
  - docs/guides/external-api-lan-deployment.md
  - docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/ccdash-aar-review-semantic-triage-tier-feasibility-brief.md
adrs_proposed:
  - "ADR-016 — Provider-agnostic LLM client seam over httpx (no provider SDK)"
  - "ADR-017 — Anthropic wire format as the canonical hosted lane (ICA + Anthropic direct)"
  - "ADR-018 — Redaction provenance is carried by type, not by convention"
verification_note: >
  Every env var, file path, function name and line number below was grep-verified against
  main 65747be on 2026-08-06 unless explicitly tagged PROPOSAL or UNVERIFIED. Items that could
  not be verified are recorded in the open-questions doc rather than asserted here.
---

# Hosted LLM Provider Strategy — Findings & Design

> Charter: [`hosted-llm-provider-strategy-charter.md`](./hosted-llm-provider-strategy-charter.md) ·
> Open questions: [`hosted-llm-provider-strategy-open-questions.md`](./hosted-llm-provider-strategy-open-questions.md)

## Recommendation

**Adopt option (c) + (d): keep `httpx`, introduce a provider-agnostic client seam, and make the
Anthropic wire format the canonical hosted lane — pointed at ICA by default.**

Concretely:

1. **No provider SDK.** Not `anthropic`, not `openai`, not `claude-agent-sdk`. Every lane stays a
   thin `httpx` adapter behind one port. The entire current hosted-LLM surface is **773 lines across
   three files** (`ai_insight.py` 105, `session_naming_hosted_backend.py` 286,
   `session_naming_local_backend.py` 382 — `grep -c ""`), and a provider call body is **~28 lines**
   (`session_naming_hosted_backend.py:257-286`). An SDK would replace ~28 lines per lane with a
   dependency, a vendored HTTP stack, and an auth/retry surface CCDash does not need.
2. **One seam, three lanes.** A single port with three adapters: `ollama` (local, zero-egress),
   `anthropic` (wire format — reaches **both** ICA and Anthropic direct via base-URL override), and
   `gemini` (retained for the already-shipped surfaces, not extended).
3. **The port does not accept a bare `str`.** It accepts a typed prompt envelope that carries
   redaction provenance. This is the load-bearing design decision — see
   [Redaction Enforcement](#redaction-enforcement).
4. **ICA is the default hosted endpoint**, because the trust boundary is already crossed and the
   free tier removes the metered-cost objection for a systematic sweep.

**Why one option and not a menu**: the four charter options are not peers. (c) is a *seam shape*,
(d) is an *endpoint choice*, and (a)/(b) are *dependency choices*. The recommendation takes the seam
from (c), the endpoint from (d), and rejects both dependency options.

### The three strongest reasons

1. **An Anthropic-shaped client reaches two providers with one adapter.** ICA is
   Anthropic-API-compatible (`ANTHROPIC_BASE_URL=https://api.nextgen-beta.ica.ibm.com/ica`), so a
   single wire-format adapter serves the free internal gateway *and* metered Anthropic direct with
   nothing but a base-URL and credential swap. No other choice buys two lanes for one adapter.
2. **The workload does not exercise anything an SDK is for.** No surface streams; no surface needs
   tool-use loops, sessions, or sandboxes; both surfaces are single-shot, short-output, and
   *fail-soft by contract* (absent key → disabled; any exception → error field, never a raise).
   An SDK's retry/streaming/agentic machinery is dead weight against a worker job that already has
   its own circuit breaker (threshold 3, `session_naming_local_backend.py:111`) and quota gate.
3. **The seam is cheap and the status quo is actively fragile.** Three distinct outbound-HTTP idioms
   already coexist (`httpx` for LLM lanes, `aiohttp` for auth/telemetry/GitHub, blocking
   `urllib.request` for the pricing scrape at `provider_pricing.py:44-46`), `httpx` is **undeclared**
   in `backend/requirements.txt`, and the naming lane is **dead in every container**. The seam is the
   natural place to fix all three at once.

### Rejection reasons

| Option | Verdict | Why |
|---|---|---|
| **(a) Anthropic Agent SDK** (`claude-agent-sdk`) | **Reject** | It exists for agentic loops — multi-turn tool orchestration, session state, sandboxed execution. CCDash's two surfaces are "summarize these aggregates in 2 sentences" and "name this session in a few words". Neither has a loop, a tool, or state. Adopting it would import an orchestration framework to make one POST. It would also sit awkwardly against the hard constraint that no model call may touch a read/render path — the Agent SDK's value is in long-running interaction, which is exactly what CCDash forbids on-request. |
| **(b) OpenAI SDK** | **Reject** | Its one real argument is that `/v1/chat/completions` is the de-facto lingua franca, and Ollama does expose an OpenAI-compatible surface — so an OpenAI-shaped client could plausibly cover local + hosted. But ICA, the endpoint CCDash actually wants, is **Anthropic**-compatible, and ICA is the lane that makes a systematic sweep affordable. Choosing OpenAI shape to gain Ollama compatibility while losing ICA compatibility optimizes the wrong axis: the local lane already works and is 382 lines of shipped, circuit-broken, tested code. **UNVERIFIED**: whether Gemini's OpenAI-compat endpoint would also be reachable — see open questions; it does not change the verdict. |
| **(c) alone** (httpx seam, no endpoint decision) | **Insufficient** | Correct on shape but leaves the actual strategy question — *which hosted provider* — unanswered, which is the ad-hoc状態 this SPIKE exists to end. Adopted **with** (d). |
| **(d) alone** (ICA, no seam) | **Insufficient** | Would add a fourth hand-rolled call site and make the sprawl worse. ICA is the right endpoint only once there is a seam to put it behind. Adopted **with** (c). |
| **Bare `anthropic` SDK** (not a charter option, evaluated anyway) | **Reject** | Closer to defensible than (a) or (b): it supports base-URL override, so it would reach ICA. But it buys retry/error-typing/token-counting that this workload either doesn't need or already has, vendors its own HTTP stack alongside the `httpx`/`aiohttp`/`urllib` trio, and its structured-output mechanism (tool-use) is heavier than the 3-line string sanitize the naming surface actually uses (`sanitize_title`, `session_naming_prompt.py:95`). Net negative at ~100 calls/day. |

## Q1 Settled — Embeddings Ownership

**Verdict: CCDash produces and stores embedding *text blocks with metadata*, but has NO code path
anywhere in `backend/` that calls an embedding model to produce a vector. The `embedding` column is
written as literal `NULL` by CCDash's only insert statement. `bge-m3` on the agentic node is not
reachable from any CCDash call path.**

The decisive evidence is the insert itself:

- `backend/db/repositories/postgres/session_embeddings.py:53-58` — the
  `INSERT INTO app.session_embeddings (... embedding_dimensions, embedding, metadata_json)` statement
  passes the **literal SQL token `NULL`** for the `embedding` column. The Python parameter list
  (`:60-71`) supplies no vector value at all. This is unconditional; there is no branch that writes
  a real vector.
- `backend/db/repositories/session_embeddings.py:31-32` — the SQLite `replace_session_embeddings` is
  a literal no-op (`_ = session_id, blocks`), `authoritative=False` (`:23`), `supported=False`
  (`:20-29`).

The write path, traced end to end:

1. `backend/application/services/session_intelligence.py:1006` —
   `embedding_blocks = build_session_embedding_blocks(canonical_rows)`.
2. `build_session_embedding_blocks` (`session_intelligence.py:884`) computes `content`,
   `content_hash` (a dedup key), `message_ids`, and block windowing (`:891-907`). **No model call,
   no numeric vector.**
3. `session_intelligence.py:1007-1008` — gated by
   `if bool(getattr(embedding_capability, "supported", False))`, then
   `await session_embedding_repo.replace_session_embeddings(session_id, embedding_blocks)`. So the
   path only runs at all on the Postgres/enterprise adapter.
4. Corroborating placeholders in the same file: `"embedding_model": ""` and
   `"embedding_dimensions": 0` are hardcoded at `session_intelligence.py:1117-1118`.

Supporting negative evidence:

- **No embedding config exists.** `backend/config.py` has no embedding/vector env var (grep over
  AI/LLM/Ollama/Gemini/naming vars returned only the nine listed in
  [Config Surface](#config-surface)).
- **No embedding client exists.** Grep across `backend/` for `bge`, `sentence_transformers`,
  `/embeddings`, `embed_text`, `vector_dim`, `EMBEDDING` (case-insensitive) returns only the files
  already named above plus storage adapters, `data_domains.py`, `data_domain_layout.py`,
  `db/factory.py`, `db/postgres_migrations.py`, `db/migration_governance.py` — all
  ownership/DDL-governance metadata. **No HTTP call to any `/embeddings` endpoint anywhere.**
- **No embedding port exists.** `backend/application/ports/core.py:108` and `:175` declare
  `def session_embeddings(self) -> Any: ...` — an untyped repository passthrough. There is no
  `embed(...)`-shaped port method.
- **The rollout script does not call a model either.** `backend/scripts/agentic_intelligence_rollout.py`
  only reports `embeddingSessionsBackfilled` / `embeddingBlocksBackfilled` counters (`:167-168`) and
  drives the same `backfill_session_intelligence` path.
- `backend/data_domain_layout.py:289-297` registers `session_embeddings` as a `RepositoryOwnership`
  entry (sqlite + postgres modules) — governance metadata only, no model reference. It is an
  enterprise-only concern (`backend/tests/test_data_domain_ownership.py:144-156`).
- The table lives in Postgres schema `app` and requires pgvector — `docker-compose.yml:96-99` pins
  `pgvector/pgvector:pg15` explicitly "required for app.session_embeddings.embedding vector column".
  So the *column* is real and the extension is provisioned; only the *producer* is absent.

**Consequence for this SPIKE**: an embedding lane is **out of scope for the seam's v1**. There is no
existing caller to migrate and no measured need. The seam should be *shaped* so an embedding adapter
can be added later (a separate port method, not a repurposed completion port — embeddings return
vectors, not text), but building one now would be speculative. Who, if anyone, is expected to
populate that column remains unresolved — see open question **OQ-1**.

## Current State — Verified Inventory

### The three LLM call sites

| Surface | Entry | Provider call | Model literal | Trigger | Degradation |
|---|---|---|---|---|---|
| Dashboard insight | `routers/ai.py:34` `POST /api/ai/insight` → `services/ai_insight.py:47` `generate_dashboard_insight` | `_call` inline, `httpx.AsyncClient(timeout=30)` at `:86-89` | `gemini-2.0-flash` (`ai_insight.py:19`) | **user-triggered request** | key unset → `AIInsightResult(disabled=True)` (`:58-60`); any exception → `error=...` (`:100-104`); never raises |
| Session naming — Lane A (default) | `services/session_naming_local_backend.py:76` `LocalOllamaNamingBackend` | `_call_ollama` (`:264`), `httpx.AsyncClient` | `CCDASH_OLLAMA_MODEL` (`gemma2:2b`) | **worker sweep job** | circuit breaker, consecutive-failure threshold 3 (`:111`) |
| Session naming — Lane B (opt-in) | `services/session_naming_hosted_backend.py:108` `HostedGeminiNamingBackend` | `_call_gemini` (`:257-286`) | `gemini-2.0-flash` (`:96`) | **worker sweep job** | fail-open per candidate → `session_name` stays NULL |

Shared prompt builder: `services/session_naming_prompt.py:53` `build_prompt_text(items: list[dict[str, Any]]) -> str`;
output sanitizer `sanitize_title` at `:95`.

**No other outbound model call exists.** Grep across `backend/` and `packages/` for
`api.openai.com`, `api.anthropic.com`, `ANTHROPIC`, `OPENAI`, `ica.ibm.com` alongside
`httpx.post`/`AsyncClient` returns only: provider-name *classifiers* that make no network call
(`model_identity.py`, `services/pricing_catalog.py`, `services/provider_pricing.py`,
`session_badges.py`, `db/repositories/feature_rollup.py`), redaction/rollup string matching
(`agent_queries/redaction.py`, `routing_rollup.py`), and the CCDash ingest daemon's own client
(`packages/ccdash_cli/src/ccdash_cli/daemon/runner.py` → `POST /api/v1/ingest/sessions`, not a model).

### Worker-only invocation is already enforced structurally

Naming derivation cannot run on a request path. `SessionNamingSweepJob`
(`adapters/jobs/session_naming_sweep_job.py:153`) is constructed only for
`_WORKER_JOB_PROFILES = {"worker", "worker-watch"}` (`runtime/container.py:70`, gate at `:124-152`),
and its periodic loop starts only under the plain `worker` profile
(`adapters/jobs/runtime.py:2863-2941`, profile check `:2898`, interval
`CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS` default 1800 at `config.py:224-226`). The `api`
profile never constructs it (`container.py:144-145`). **AOS constraint 4 is satisfied by
construction, not convention** — the seam must preserve this.

Correcting a detail: the sweep **does** fan out across every registered project
(`session_naming_sweep_job.py:188-221`, `_resolve_projects_to_sweep` at `:223` mirroring
`AARReviewSweepJob` per ADR-006), with a `(project_id, trigger)`-keyed coalescing guard
(`:201-218`). A per-project loop with the project object already in hand is the natural hook for
per-project consent.

### The existing hosted gate is already well designed — generalize it, don't reinvent it

`resolve_naming_backend` (`session_naming_local_backend.py:296`) is the model to copy:

- Reads `CCDASH_SESSION_NAMING_BACKEND` (`:345`); unknown values fall through to
  `LocalOllamaNamingBackend` (`:382`).
- For `hosted`, **requires** `redaction_patterns_enabled()` (`:347`); if redaction is off it returns
  **`None`** — the sweep no-ops entirely and, per the docstring at `:338-343`, this is "a deliberate
  no-op, never a silent fallback to sending."
- Logs a one-time **WARNING** at construction (`:363-381`) explicitly stating that off-box egress is
  now *reachable* — deliberately louder than the module's usual INFO, so the posture is discoverable
  from the log stream rather than only from config.

`ai_insight` is the ad-hoc outlier: it has **no** redaction gate (verified — no `redact` reference in
`routers/ai.py` or `ai_insight.py`), which is defensible only because it sends aggregates rather than
transcripts. See [Redaction Enforcement](#redaction-enforcement) for why that asymmetry is the
central design constraint.

### Six defects the seam should absorb

These are all grep-verified and all pre-existing. None is caused by this SPIKE; each is cheapest to
fix while the seam is being built.

1. **`httpx` is an undeclared dependency of the backend.** It is absent from
   `backend/requirements.txt` (21 lines, verified) and arrives transitively via `mcp`
   (`pip show httpx` → `Required-by: ccdash-cli, mcp, pytest-httpx, respx`). It **is** declared in
   `packages/ccdash_cli/pyproject.toml:13` (`httpx>=0.27`). So `ai_insight.py:5`'s claim — "already a
   project dependency" — is true only undeclared-transitively. Every hosted egress path rests on a
   dependency no manifest asks for.
2. **Three outbound HTTP idioms coexist.** `httpx` (LLM lanes), `aiohttp` (declared,
   `requirements.txt:7`; used by `adapters/auth/providers/clerk.py`, `oidc.py`,
   `application/services/authentication.py`, `services/integrations/sam_telemetry_client.py`,
   `services/repo_workspaces/github_client.py`), and **blocking** `urllib.request.urlopen` in
   `services/provider_pricing.py:44-46` (pricing-page scrape, `timeout=20`, on an async server).
3. **`POST /api/ai/insight` is unauthenticated and forwards arbitrary caller-supplied content.**
   `AIInsightRequest` (`routers/ai.py:19-23`) accepts `metrics: list[dict[str, Any]]` and
   `tasks: list[dict[str, Any]]` with no schema constraint; `ai_insight.py:62-74` stringifies both
   into the prompt. `ai_router` is registered at `runtime/bootstrap.py:761` with **no** router-level
   dependency, and the only middleware is CORS (`bootstrap.py:187-193`). By contrast every
   `/api/v1` route carries `dependencies=[Depends(require_v1_auth)]`
   (`routers/client_v1.py:99`, ADR-008). Net effect on any non-loopback deployment: an open LLM proxy
   spending the server's key on caller-chosen text. `docs/guides/external-api-lan-deployment.md`
   never mentions this endpoint. Compose defaults to loopback
   (`docker-compose.yml:171-173`) which mitigates but does not remove it.
4. **API keys travel in the URL query string.** `ai_insight.py:76` and
   `session_naming_hosted_backend.py:269` both build `...:generateContent?key={api_key}`. URLs are
   the most-logged part of an HTTP request. Anthropic/OpenAI/ICA all use headers instead — a strict
   improvement.
5. **Provider error bodies are logged verbatim.** `ai_insight.py:101` logs `exc.response.text` at
   WARNING. A provider echoing request content in an error body would land it in the log.
6. **No LLM env var is passed into any container.** Neither `docker-compose.yml`'s
   `x-shared-backend-env` anchor (`:68-91`) nor `deploy/runtime/compose.hosted.yml` (88 lines)
   contains `CCDASH_SESSION_NAMING_*`, `CCDASH_OLLAMA_*`, or `CCDASH_GEMINI_API_KEY`. Compose passes
   an explicit allowlist, so **the entire naming lane — local and hosted — silently no-ops in every
   containerized deployment.** The naming PRD's FR-18 flagged this for the Gemini key only; it is
   broader. Combined with `CCDASH_SESSION_NAMING_ENABLED` defaulting to `False`
   (`config.py:199`), the derive lane is currently dormant everywhere.

## Provider Seam Design

> Everything in this section is a **PROPOSAL**. No file named here exists today except where it is
> explicitly identified as an existing symbol.

### Placement

CCDash already has a ports-and-adapters spine, and an LLM provider is an *outbound infrastructure
dependency* — the same category as `adapters/auth/providers/` and `adapters/jobs/`. It is not a
transport-neutral read, so it does **not** belong in `application/services/agent_queries/` (that
package is for query surfaces shared by REST/CLI/MCP).

| Layer | Path | Contents |
|---|---|---|
| Port | `backend/application/ports/llm.py` **(PROPOSAL)** | `TextCompletionPort` Protocol, `PromptEnvelope`, `CompletionResult` |
| Adapters | `backend/adapters/llm/ollama.py`, `anthropic.py`, `gemini.py` **(PROPOSAL)** | one thin `httpx` adapter each |
| Resolution | `backend/adapters/llm/resolver.py` **(PROPOSAL)** | generalization of the existing `resolve_naming_backend` gate |
| Composition | `backend/runtime/container.py` **(EXISTING)** | resolver invoked per surface; worker-profile gate unchanged |

Existing symbols that move behind the port: `_call_gemini`
(`session_naming_hosted_backend.py:257`), `_call_ollama` (`session_naming_local_backend.py:264`), and
the inline call in `ai_insight.py:86-89`. The *policy* around them — circuit breaker, fail-open
wrapper `derive_name_fail_open` (`session_naming_sweep_job.py:117`), quota gate, the WARNING —
**stays where it is**. The seam replaces transport only.

### The port — chat completion only, plus one capability probe

```python
# backend/application/ports/llm.py — PROPOSAL
@dataclass(frozen=True)
class CompletionResult:
    text: str
    input_tokens: int | None = None      # None when the provider does not report usage
    output_tokens: int | None = None
    model: str = ""                      # the id actually served, for provenance

class TextCompletionPort(Protocol):
    @property
    def lane(self) -> str: ...           # "ollama" | "anthropic" | "gemini"
    @property
    def egress(self) -> bool: ...        # False for ollama — drives the consent gate
    async def complete(
        self,
        envelope: PromptEnvelope,        # NOT a bare str — see Redaction Enforcement
        *,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> CompletionResult: ...
```

**Argued minimum: chat completion only.** Deliberately excluded from v1 —

- **Streaming.** No surface streams today, and none plausibly can: the hard constraint forbids model
  calls on a read/render path, which is the only place streaming pays. The one user-triggered surface
  returns a 2-sentence blurb. Streaming is excluded on *constraint* grounds, not just current-need
  grounds.
- **Structured output.** The naming surface wants one short string and already post-processes with
  `sanitize_title` (`session_naming_prompt.py:95`). The three lanes' mechanisms are mutually
  incompatible in shape (Ollama `format`, Gemini `responseSchema`, Anthropic tool-use), so
  abstracting them would mean inventing a fourth vocabulary to serve a need that a 3-line sanitize
  already meets. Excluded until a surface genuinely needs a multi-field object.
- **Embeddings.** No producer and no caller exist (see [Q1](#q1-settled--embeddings-ownership)). When
  one is needed it gets its **own** port method returning vectors — not a repurposed text port.
- **Token counting.** Recorded opportunistically via `CompletionResult` when the provider volunteers
  usage; no dedicated count-tokens call. Nothing in CCDash budgets against a pre-flight count.

**`egress: bool` is the one capability flag that earns its place** — it is what lets the consent and
blast-radius gates be written once against the port instead of re-deriving "is this lane local?" at
each call site.

### Answer to RQ-3: no, an Anthropic-shaped *client* does not justify a dependency — but the *wire format* does

Separate the two questions the charter conflates:

- **Wire format: adopt Anthropic. Yes.** One adapter reaches ICA (free, internal, already-trusted)
  and Anthropic direct (metered, external) by base-URL swap. That is a genuine two-for-one and is the
  strongest single argument in this SPIKE.
- **SDK: reject.** The concrete deltas an SDK offers over `_call_gemini`'s 28-line shape are
  retry/backoff, typed errors, token counting, prompt caching, and structured output. Against this
  workload: retry is *undesirable* on a sweep that already has a circuit breaker and a fail-open
  per-candidate contract (a silent SDK retry storm would defeat both); typed errors are unused
  because every caller collapses to `except Exception` by design; token counting is opportunistic;
  prompt caching is worthless at ~100 distinct prompts/day with no shared prefix; structured output is
  over-spec'd as above. An SDK would also vendor a fourth HTTP stack alongside the three already
  present (defect 2).

**Net: writing the Anthropic wire format by hand is ~30 lines and zero new dependencies.** The one
non-negotiable is that the version header and endpoint path must be verified against live Anthropic
docs at implementation time — see **OQ-2**; this SPIKE does not assert them from memory.

### Migration of existing call sites

| Call site | Change |
|---|---|
| `session_naming_local_backend.py` / `session_naming_hosted_backend.py` | `_call_ollama` / `_call_gemini` bodies move to adapters; `derive_name`'s `get_session_detail` read, fail-open, breaker, and WARNING are untouched. The two classes collapse toward one `DerivedNamingBackend` holding a `TextCompletionPort`. |
| `ai_insight.py` | `generate_dashboard_insight` keeps its signature and its `AIInsightResult(disabled=/error=)` contract verbatim; only the `httpx` block (`:76-104`) is replaced by a port call. **Behaviour-identical by design** — this is what makes Phase 1 reversible. |
| `routers/ai.py` | Unchanged in Phase 1. Its auth/payload defect (defect 3) is Phase 2. |
| `provider_pricing.py` | **Out of scope** — a docs scrape, not a model call. Its blocking-`urllib` problem is noted, not adopted. |

## Redaction Enforcement

### The problem is not "is redaction called" — it is "the port erases the distinction"

Two surfaces send materially different things, under different obligations:

- **Naming (Lane B)** sends transcript-derived text. It **must** be redacted. It is —
  `session_naming_hosted_backend.py:174-180` reads via
  `get_session_detail(..., include={INCLUDE_TRANSCRIPT})`, and the code comment at `:195-197` states
  "``bundle.transcript.items`` has already been through ``redact_entries`` inside
  ``get_session_detail`` -- this is the text this Lane B prompt is built from; nothing raw is read
  here."
- **Insight** sends aggregates — but not *purely* numeric ones. `ai_insight.py:62-66` interpolates
  task **titles**, statuses, and costs. It has no redaction gate at all, which is defensible for that
  content class but is an un-gated egress surface nonetheless.

**That comment is the entire enforcement mechanism.** A port typed `complete(prompt: str)` erases the
difference between those two content classes, so the very first refactor that routes insight and
naming through one `str`-shaped port creates a path for transcript text to reach an un-gated lane
with no type, test, or reviewer noticing. This is why the port takes an envelope.

### Verified gaps in the current "single choke point" claim

The module docstring of `agent_queries/session_detail.py:1-17` asserts
`SessionTranscriptService.list_session_logs` is "the **only** transcript reader." That is a
convention, and it is already violated inside the very function that enforces it:

1. **The redacted path**: `session_detail.py:447` fetches via `_transcript_service.list_session_logs(...)`,
   then `:455` passes the page through `redact_entries(page_items)`. Correct.
2. **The un-redacted path**: `session_detail.py:557-565` — when the transcript segment was not
   requested, `get_session_detail` calls `_transcript_service.list_session_logs(session_row, ports, limit=1000, offset=0)`
   **again**, for `aosCorrelation` derivation, and **does not** route that read through
   `redact_entries`. Not currently exposed to a naming backend, but it proves the choke point is not
   mechanically enforced.
3. **No type distinguishes the two.** `list_session_logs` returns `list[dict[str, Any]]` whether or
   not it has been redacted. Nothing at the type level prevents a caller consuming the raw return.
4. **Redaction fails open, deliberately.** `session_detail.py:456-462` catches a `redact_entries`
   exception, logs a warning, and "proceed[s] without redaction for this page" — documented at
   `:374-375` as "delivery safety > potential partial secret exposure in edge cases". Defensible for a
   *read* surface; **materially different when the consumer is an egress lane.** A provider adapter
   must not inherit that trade-off silently.

Raw readers a future lane could call by accident: `backend/parsers/sessions.py:11 parse_session_file`,
`:16 scan_sessions`, and `SessionTranscriptService.list_session_logs` itself
(`application/services/sessions.py:93`, instantiated as `_transcript_service` at `session_detail.py:93`).

### Recommended mechanism: primary + cheap complement

**Primary — `PromptEnvelope`, a frozen dataclass carrying redaction provenance, as the only accepted
port input (PROPOSAL).**

```python
# backend/application/ports/llm.py — PROPOSAL
class PromptProvenance(StrEnum):
    AGGREGATE = "aggregate"                  # no transcript content (insight)
    TRANSCRIPT_REDACTED = "transcript_redacted"   # via redact_entries, redaction confirmed ON

@dataclass(frozen=True)
class PromptEnvelope:
    text: str
    provenance: PromptProvenance
    redaction_events: int = 0    # COUNT only — never payload (existing rule)
```

Rules that make it structural rather than decorative:

- `PromptEnvelope` is constructible **only** by two named factories in the seam:
  `envelope_from_aggregate(text)` and `envelope_from_redacted_transcript(page)`. The latter takes the
  transcript page **and the `redact_entries` event count**, and raises if
  `redaction_patterns_enabled()` is False — converting redaction's *fail-open read* posture into a
  **fail-closed egress** posture at the boundary, which is where the trade-off should differ.
- Any adapter whose `egress` is `True` **rejects** an envelope it is not configured to accept. A
  hosted lane configured for redacted-transcript material refuses an `AGGREGATE` envelope and vice
  versa, so a future call site cannot quietly widen what a lane sends.
- `build_prompt_text(items: list[dict[str, Any]])` (`session_naming_prompt.py:53`, **existing**) is
  the exact single retype point: it is the one function that turns transcript items into prompt text,
  so having it return an envelope instead of `str` converts the code comment at
  `session_naming_hosted_backend.py:195-197` into a type the compiler checks.

**Would it have caught the `session_detail.py:560` gap?** Not directly — that read never reaches a
provider. But it makes the gap *harmless by construction*: if anyone later routes that
un-redacted second read toward a lane, there is no factory that will wrap it, so it cannot become an
envelope. **The mechanism converts a latent egress bug into a compile-time impossibility.**

**Complement — an architecture guardrail test (cheap, catches the import-level mistake).** A unit test
asserting that no module under `backend/adapters/llm/` imports `backend.parsers.sessions` or
`SessionTranscriptService`. This is the same genre as the existing
`backend/tests/test_session_naming_read_path_no_model_client.py` (**existing** — it already asserts a
read path holds no model client), so the pattern and its precedent are established. Pair it with a
positive test asserting every hosted-lane prompt carries `TRANSCRIPT_REDACTED` or `AGGREGATE`
provenance — the naming PRD already requires such a test before the flag may be flipped on
(`automatic-session-naming-v1.md:244`).

**Rejected alternatives**: a runtime assertion inside each adapter (correct but re-implemented per
adapter, and silent if one is forgotten); leaving it as convention (the status quo — already
demonstrably violated at `session_detail.py:560`).

## Config Surface

> All names below are **PROPOSAL** except the nine existing vars in the first table, which are
> grep-verified with line numbers.

### Existing vars — verified, none renamed

| Var | Default | Type | Defined at |
|---|---|---|---|
| `CCDASH_SESSION_NAMING_ENABLED` | `False` | bool | `config.py:199` |
| `CCDASH_SESSION_NAMING_QUOTA` | `200` | int | `config.py:206` |
| `CCDASH_SESSION_NAMING_WINDOW_HOURS` | `24` | int | `config.py:213` |
| `CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS` | `1800` | int | `config.py:224-226` |
| `CCDASH_SESSION_NAMING_BACKEND` | `"local"` | str (lowercased) | `config.py:234` |
| `CCDASH_OLLAMA_BASE_URL` | `"http://localhost:11434"` | str | `config.py:242` |
| `CCDASH_OLLAMA_MODEL` | `"gemma2:2b"` | str | `config.py:248` |
| `CCDASH_OLLAMA_TIMEOUT_SECONDS` | `15` | int | `config.py:253` |
| `CCDASH_GEMINI_API_KEY` | `""` | str | `config.py:1409` |

Plus, defined in `agent_queries/redaction.py` rather than `config.py`:
`CCDASH_REDACTION_PATTERNS_ENABLED` (default `True`, `redaction.py:55`) and
`CCDASH_REDACTION_TOOL_AWARE_ENABLED` (default `True`, `redaction.py:248`/`:302`).

**Discrepancy to note**: the charter's decision inputs state `CCDASH_OLLAMA_TIMEOUT_SECONDS` "is now
60". The **code default is 15** (`config.py:253`) and no in-repo file sets 60 — not `.env.example`,
not either compose file. The 60 is an operator-local/node override that is not represented in the
repo. Recorded as **OQ-5**.

### The combinatorial problem, and the scheme that avoids it

Naive expansion is *N surfaces × M providers × per-provider credentials*. Avoid it by separating
three orthogonal axes and never crossing them in a var name:

1. **Credentials are per-provider, never per-surface.** One credential block per provider, shared by
   every surface that uses it.
2. **Lane selection is per-surface, with a global default.** A surface names a *lane*, not a
   provider+model+key tuple.
3. **Model choice is per-provider-default with an optional per-surface override**, because a naming
   task and an insight task may legitimately want different sizes from the same provider.

This is *M credential blocks + N lane selectors + a small number of overrides* — linear in both, not
multiplicative.

| Var (**PROPOSAL**) | Type | Default | Meaning | Relationship to existing |
|---|---|---|---|---|
| `CCDASH_LLM_DEFAULT_LANE` | str | `"local"` | Fallback lane for any surface without an explicit selector. `local` keeps zero-egress the default. | new |
| `CCDASH_LLM_SESSION_NAMING_LANE` | str | *(unset → falls back)* | Lane for the naming sweep. | **aliases** `CCDASH_SESSION_NAMING_BACKEND`; see compatibility below |
| `CCDASH_LLM_INSIGHT_LANE` | str | *(unset → falls back)* | Lane for dashboard insight. | new — insight has no selector today |
| `CCDASH_LLM_ANTHROPIC_BASE_URL` | str | `"https://api.anthropic.com"` | Anthropic-compat endpoint. **Set to the ICA base URL to use ICA.** | new |
| `CCDASH_LLM_ANTHROPIC_API_KEY` | str | `""` | Credential for whichever Anthropic-compat endpoint is configured. Empty → lane unreachable. | new |
| `CCDASH_LLM_ANTHROPIC_MODEL` | str | *(no default — see OQ-2)* | Default model id for the lane. Must be an ICA-suffixed id when pointed at ICA. | new |
| `CCDASH_LLM_ANTHROPIC_TIMEOUT_SECONDS` | int | `30` | Matches the existing insight timeout (`ai_insight.py:20`). | new |
| `CCDASH_LLM_SESSION_NAMING_MODEL` | str | *(unset → lane default)* | Per-surface model override. | new |
| `CCDASH_LLM_INSIGHT_MODEL` | str | *(unset → lane default)* | Per-surface model override. | new |
| `CCDASH_LLM_EGRESS_CONSENT` | bool | `False` | Master gate: no lane with `egress=True` may be constructed unless true. See [Blast-Radius Controls](#blast-radius-controls). | new |

Lane values: `local` \| `anthropic` \| `gemini`. Unknown → resolve to `local` with a WARNING, matching
the existing tolerant fallback at `session_naming_local_backend.py:382`.

**Compatibility story (no renames, no breakage).** `CCDASH_OLLAMA_*` and `CCDASH_GEMINI_API_KEY` keep
their exact names and meanings — they simply become the `local` and `gemini` lanes' credential
blocks. `CCDASH_SESSION_NAMING_BACKEND` stays readable forever: the resolver reads
`CCDASH_LLM_SESSION_NAMING_LANE` first and falls back to `CCDASH_SESSION_NAMING_BACKEND`, whose
existing values (`local`, `hosted`) map to `local` and `gemini` — so an existing deployment's config
means exactly what it meant before, including "hosted means Gemini". Only a *new* var opts into the
Anthropic lane. Every quota/window/interval var is unchanged and lane-independent.

### Worked configurations

```bash
# (i) All-local, zero egress — this is also the default with NO config at all.
CCDASH_SESSION_NAMING_ENABLED=true
# CCDASH_LLM_DEFAULT_LANE=local        (default)
# CCDASH_LLM_EGRESS_CONSENT=false      (default) — hosted lanes cannot even construct

# (ii) Insight hosted (ICA), naming stays local + zero-egress.
CCDASH_SESSION_NAMING_ENABLED=true
CCDASH_LLM_EGRESS_CONSENT=true
CCDASH_LLM_INSIGHT_LANE=anthropic
CCDASH_LLM_ANTHROPIC_BASE_URL=https://api.nextgen-beta.ica.ibm.com/ica
CCDASH_LLM_ANTHROPIC_API_KEY=<ica-token>
CCDASH_LLM_ANTHROPIC_MODEL=<verify per OQ-2>
# naming inherits CCDASH_LLM_DEFAULT_LANE=local

# (iii) Everything hosted via ICA, cheap model for the sweep.
CCDASH_SESSION_NAMING_ENABLED=true
CCDASH_LLM_EGRESS_CONSENT=true
CCDASH_LLM_DEFAULT_LANE=anthropic
CCDASH_LLM_ANTHROPIC_BASE_URL=https://api.nextgen-beta.ica.ibm.com/ica
CCDASH_LLM_ANTHROPIC_API_KEY=<ica-token>
CCDASH_LLM_ANTHROPIC_MODEL=<mid-tier, verify per OQ-2>
CCDASH_LLM_SESSION_NAMING_MODEL=<cheap-tier, verify per OQ-2>
# CCDASH_REDACTION_PATTERNS_ENABLED must stay true or naming's hosted lane no-ops
```

**Compose plumbing is a first-class deliverable, not a follow-up.** Per defect 6, every var above —
*including the existing nine* — must be added to `docker-compose.yml`'s `x-shared-backend-env` anchor
(`:68-91`) and to `deploy/runtime/compose.hosted.yml`, or the whole feature is a silent no-op in
every container. This generalizes the naming PRD's FR-18 from one key to the whole surface.

## Blast-Radius Controls

The operator input is right that ICA does not cross a *new* trust boundary, and right that the
remaining difference is blast radius: delegation sends what an agent **chose** to read; a naming
sweep sends **every eligible session, systematically**. The design must gate on volume and
systematicity, not on trust.

### Two egress shapes, two gate sets

| | User-triggered (insight) | Systematic sweep (naming) |
|---|---|---|
| Volume | 1 per click | ~100/day steady; ~20k for a backfill |
| Content | caller-supplied aggregates + task titles | transcript-derived, redacted |
| Who decides | the person clicking | a config flag set once |
| Primary risk | **open proxy** (defect 3) — an unauthenticated endpoint spending the server's key | **fan-out** — one flag flip egresses the whole corpus |
| Needs | authentication + a request-rate cap | opt-in + per-project consent + quota + an explicit backfill gate |

### Gates — reuse what exists, add four things

**Already shipped and sufficient; keep as-is:**
- `CCDASH_SESSION_NAMING_ENABLED` default `False` (`config.py:199`) — the sweep is off by default.
- `CCDASH_SESSION_NAMING_QUOTA` = 200 / `CCDASH_SESSION_NAMING_WINDOW_HOURS` = 24
  (`config.py:206`, `:213`) — a standing rate cap already sized just above the ~100/day estimate.
- Circuit breaker, threshold 3 (`session_naming_local_backend.py:111`) — provider-failure containment.
- Worker-profile-only construction (`runtime/container.py:144-145`) — no request path can trigger it.
- The fail-closed redaction gate returning `None` (`session_naming_local_backend.py:347-353`).

**Add (all PROPOSAL):**

1. **`CCDASH_LLM_EGRESS_CONSENT` (bool, default `False`) — a master switch distinct from the lane
   selector.** Today selecting `hosted` is *simultaneously* the "which provider" choice and the "yes,
   send data off-box" choice. Separating them means a lane can be fully configured (URL, key, model)
   without egress being live, and turning egress on is a single reviewable, greppable act. Enforced in
   the resolver: any adapter with `egress=True` returns `None` when consent is false — reusing the
   existing "deliberate no-op, never a silent fallback to sending" contract verbatim.
2. **Per-project consent.** `SessionNamingSweepJob.execute` already loops per project with the project
   object in hand (`session_naming_sweep_job.py:197-221`), so the hook is free. Add a nullable
   `llm_egress_consent` column to `projects` via the established `_ensure_column` ALTER pattern
   (precedent: v38 `repo_path` at `sqlite_migrations.py:4187`; table DDL at `:1230`), **with dual
   SQLite+Postgres DDL in the same change set** per the column-parity rule. Semantics: `NULL`/false →
   that project is skipped by any egress lane; the local lane ignores the column entirely. This is
   what makes a shared multi-project deployment safe — 12 projects are currently registered, and one
   operator's consent should not speak for all of them.
3. **A separate, explicitly-bounded backfill gate.** The 20k-call historical backfill is a different
   operation from the 100/day steady sweep and must not be reachable by raising the standing quota.
   Recommend a one-shot CLI entry point (`backend/cli/`, **PROPOSAL**) that requires an explicit
   `--limit N` with no default, prints a cost estimate and the target project(s), and requires
   confirmation — never a config flag the scheduler can pick up. The existing
   `backend/scripts/agentic_intelligence_rollout.py` is the shape precedent for an operator-driven
   one-shot.
4. **Egress observability.** Emit per sweep tick, at INFO: lane, model id actually served, project id,
   candidates considered, calls made, quota remaining, and **redaction event COUNT only**. The
   count-not-content rule is existing policy and is already how redaction logs behave; it must extend
   to the provider adapter. Explicitly **never** log: prompt text, completion text, or the provider's
   error body — which closes defect 5 (`ai_insight.py:101` currently logs `exc.response.text`). Keep
   the one-time reachability WARNING (`session_naming_local_backend.py:363-381`) and generalize its
   wording to name the resolved lane.

**Also required, and it is a gate not a nicety:** fix defect 3 before any lane is added to the insight
surface. An unauthenticated `POST /api/ai/insight` that forwards caller-supplied dicts is an open
proxy today with a Gemini key; pointing it at an ICA credential would expose an *internal gateway
token* to the same surface. Minimum: apply the existing `require_v1_auth`-style router dependency
(pattern at `routers/client_v1.py:99`) and constrain the request model to the fields the prompt
actually uses instead of `dict[str, Any]`.

### What is deliberately NOT gated

Per-request latency and cost for the *local* lane. `egress=False` means no consent gate, no per-project
column check, and no egress logging — zero-egress stays frictionless, which is the point of keeping it
first-class rather than a fallback.

## Empirical Larger-Model Test

### Surface: session naming only

Naming is the only defensible test surface, for three reasons that are properties of the surface
rather than conveniences: it has a **deterministic-fallback baseline already shipped** (provider-
persisted names and deterministic exclusions per the naming PRD), so "better than nothing" is already
measurable; it has a **corpus** (thousands of sessions, ~58.6% structurally excluded per the PRD, so
the eligible pool is large and pre-classified); and its output is **short and comparable**, so scoring
is tractable. Dashboard insight is explicitly excluded: N=1 per click, no ground truth, and a
2-sentence free-text output that cannot be scored without a human per sample.

### Design

- **N = 200 sessions**, drawn from a **single frozen sample** — the *same* sessions through every arm,
  so arms are paired rather than independently sampled. Stratify across the dimensions already
  captured in the `sessions` table (provider/platform, `launcher`, interactive vs not) so one arm
  cannot win by getting easier inputs.
- **Arms (3):** (A) local `gemma2:2b` — the shipped baseline; (B) a hosted **small/cheap** tier; (C) a
  hosted **mid** tier. Concrete model ids for B and C must be resolved at run time against live
  pricing/model docs — **this SPIKE deliberately does not name them (OQ-2)**. Run B and C through ICA
  where its catalog covers the tier, so the experiment itself is free.
- **Prompt held constant** across arms: `build_prompt_text` (`session_naming_prompt.py:53`) unchanged,
  `sanitize_title` (`:95`) applied identically. Only the lane and model vary. Same redacted input via
  `get_session_detail` — the experiment must not bypass the egress seam it is evaluating.
- **Run offline-ish and idempotent:** results written to a scratch table or NDJSON, not to
  `sessions.session_name`, so the experiment never mutates product state and can be re-scored.

### Scoring rubric — how to score without a human per sample

The trap is "it's better" as an outcome. Three of the four measures are fully mechanical; only one
needs human effort, and it is bounded.

| Measure | How | Mechanical? |
|---|---|---|
| **M1 — Validity rate** | Fraction of the 200 that produced a non-empty name surviving `sanitize_title`, within length bounds, and not a refusal/echo/boilerplate string (regex denylist). | Yes |
| **M2 — Discriminability** | Fraction of names unique within the sample, plus a check that names are not degenerate-generic (a stop-list of "Session", "Debugging", "Code Changes"). A namer that labels 40 sessions "Bug Fix" has failed regardless of fluency. | Yes |
| **M3 — Keyword grounding** | Overlap between the name's content words and high-signal tokens from the session's own material (file paths touched, feature id, git branch — `git_branch` is already a captured column). Proxy for "is the name about *this* session". | Yes |
| **M4 — Blind pairwise preference** | **Bounded human step**: 40 of the 200 (random subsample), names from two arms shown side-by-side, arm labels hidden, order randomized. Record only which is more useful for finding the session again. ~40 binary judgments, one sitting. | No — but capped |
| Latency | p50/p95 per call. Baseline: `gemma2:2b` measured 20.0s cold / 6.9s warm. | Yes |
| Cost | Calls × measured tokens × rate; $0 on the local lane and on ICA free tier. | Yes |
| Failure rate | Timeouts, 4xx/5xx, circuit-breaker trips. | Yes |

### Decision rule — stated before the run

Promote a hosted model over local `gemma2:2b` **only if all three hold**:

1. **M1 ≥ local + 5 percentage points**, *or* M1 is already ≥95% on both arms (ceiling reached, so
   validity stops discriminating and M2/M4 decide).
2. **M4 win rate ≥ 60%** against local in blind pairwise preference (i.e. clearly better, not
   coin-flip). A 50–60% result is **"no meaningful difference — stay local"**, not a marginal win.
3. **Cost is $0** (ICA free tier) **or** measured monthly cost at the observed call rate is under an
   operator-set ceiling agreed *before* the run.

**Tie-breaker between hosted small and hosted mid**: if the small tier's M4 win rate against local is
within 5 points of the mid tier's, **choose small** — the mid tier's extra cost buys nothing at this
task. Explicit anti-goal: do not promote a larger model because its names *read* better while M2 and
M3 show it is no more grounded or discriminating.

**Latency is a constraint, not a score.** Any arm whose p95 exceeds `CCDASH_OLLAMA_TIMEOUT_SECONDS`'s
practical envelope is disqualified regardless of quality — the sweep is designed to fail a candidate
fast rather than stall a tick (`config.py:250-252`).

### Cost model — formula and assumptions, not asserted rates

Per-call token assumption to state explicitly: **~4,000 input tokens + ~30 output tokens** (a truncated
transcript window in, a few words out). Then:

```
monthly_cost  = calls_per_day × 30 × (4000/1e6 × rate_in + 30/1e6 × rate_out)
backfill_cost = 20000        ×      (4000/1e6 × rate_in + 30/1e6 × rate_out)
```

At 100 calls/day that is 3,000 calls/month ≈ **12M input tokens + 0.09M output tokens**; the 20k
backfill is ≈ **80M input + 0.6M output**. Output cost is negligible at this shape — **this workload is
almost purely input-token-priced**, which is the single most useful planning fact here and is
rate-independent. Concrete per-MTok rates are deliberately not asserted (**OQ-2**); on ICA free tier
both figures are **$0**, which is why ICA is the recommended endpoint for any systematic run.

Local-lane cost is $0 in dollars but non-zero in capacity: node has 23 GB RAM / ~14 GB free, and
`gemma2:2b` at 6.9s warm × 100/day ≈ 12 minutes of daily compute — comfortably inside a 1800s sweep
interval (`config.py:224-226`).

## Phased Implementation Shape

High-level only — **not a Tier-3 plan**. A real plan is a separate artifact; this is the ordering
argument and the reversibility boundary.

### P1 — Seam lands with zero behaviour change *(reversible)*

Introduce `TextCompletionPort` + `PromptEnvelope` + the `ollama` and `gemini` adapters; move
`_call_ollama`, `_call_gemini`, and `ai_insight`'s inline block behind them. Retype
`build_prompt_text` to return an envelope. **No new provider, no new egress, no config change.**

- **Exit:** existing tests pass unmodified — including
  `test_session_naming_hosted_backend`, `test_session_naming_local_backend`,
  `test_ai_insight_router`, and critically `test_session_naming_read_path_no_model_client` (all
  **existing**). `ai_insight` still returns `{disabled:true}` with no key and an `error` string on
  failure, byte-identically.
- **This is the one phase that is trivially revertible**, because it is a pure transport refactor.
  Everything after it changes observable behaviour.

### P2 — Close the six defects *(no new capability)*

Declare `httpx` in `backend/requirements.txt`; add auth + a constrained request model to
`POST /api/ai/insight`; move credentials from URL query strings into headers where the provider allows
it; stop logging provider error bodies; add **every** LLM env var to both compose files' env
allowlists; add the redaction-provenance guardrail test.

- **Exit:** the naming lane actually runs in a container (today it cannot — defect 6); an
  unauthenticated request to `/api/ai/insight` is rejected; a grep for `?key=` in `backend/services/`
  returns nothing; the guardrail test fails if an `adapters/llm/` module imports `parsers.sessions`.
- **Sequencing is load-bearing here**: compose plumbing must precede any hosted-lane work, or every
  subsequent phase is untestable on the node and will appear to "work" locally while silently
  no-opping in deployment. This is exactly how the naming lane became dormant.

### P3 — Anthropic lane + gating *(first new egress path)*

Add the `anthropic` adapter (base-URL configurable → ICA or Anthropic direct), the
`CCDASH_LLM_*` config surface with its compatibility fallbacks, `CCDASH_LLM_EGRESS_CONSENT`, the
per-project `llm_egress_consent` column (**dual SQLite+Postgres DDL, same change set**), and egress
observability.

- **Exit:** with consent false, no egress adapter constructs and the sweep no-ops with a log line;
  with consent true and one project consented, only that project's sessions egress; a positive test
  asserts every outbound prompt carries `TRANSCRIPT_REDACTED` or `AGGREGATE` provenance.
- **Gate:** this phase's surface hits two of the three second-lens triggers — `irreversible-outward`
  (data leaves the system) and `authz-boundary` (credentials + a consent boundary). It warrants a
  second review lens; the earlier phases do not.

### P4 — Run the experiment, then decide

Execute the [empirical test](#empirical-larger-model-test) with the pre-registered decision rule, on
the frozen N=200 sample, via the one-shot bounded CLI entry point.

- **Exit:** a recorded result table plus a decision — promote a hosted model, or keep local. **A
  "keep local" outcome is a success**, not a wasted phase: it converts an assumption into a citable
  finding and leaves the hosted lane built, gated, and off.
- The 20k backfill is **not** in this phase and is not authorized by it. It is a separate operator
  decision that the experiment's cost model informs.

**Not in any phase:** an embedding lane (no producer, no caller — Q1); making the AAR loop
model-driven (settled NO-GO); anything that puts a model call on a render path.

## ADR Candidates

Highest existing ADR is `adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md` (verified by
directory listing), so new numbering starts at **016**. All three are `status: proposed` until the
recommendation is accepted.

### ADR-016 — Provider-agnostic LLM client seam over httpx; no provider SDK

**Seals**: CCDash routes all model calls through one `TextCompletionPort` with thin `httpx` adapters,
and adopts **no** provider SDK (`anthropic`, `openai`, `claude-agent-sdk` all rejected).
**Why it needs an ADR**: it is a standing prohibition, not a one-off implementation choice. Without a
recorded decision, the next contributor facing a retry or streaming need will reach for an SDK, and the
rationale (workload shape, existing breaker/fail-open contracts, three-HTTP-idiom sprawl) will have to
be re-derived. It also records the `httpx`-must-be-declared corollary.

### ADR-017 — Anthropic wire format is the canonical hosted lane; ICA is the default endpoint

**Seals**: hosted egress speaks the Anthropic Messages wire format with a configurable base URL, so one
adapter serves ICA and Anthropic direct; the Gemini lane is retained for shipped surfaces but not
extended; ICA is the default because the trust boundary is already crossed and the free tier makes a
systematic sweep affordable.
**Why it needs an ADR**: this is the actual strategy decision the tracker node asked for, and it
forecloses the OpenAI-compat path — which has a real counter-argument (Ollama serves an
OpenAI-compatible surface) that a future reader will otherwise re-litigate. The reasoning that ICA
compatibility outweighs Ollama compatibility must be written down.

### ADR-018 — Redaction provenance is carried by type, not by convention

**Seals**: the LLM port accepts only a `PromptEnvelope` carrying `PromptProvenance`, constructible
solely via two named factories; the transcript factory is **fail-closed** on redaction being disabled,
deliberately diverging from `get_session_detail`'s fail-open read posture
(`session_detail.py:456-462`); an architecture guardrail test forbids provider modules from importing
raw transcript readers.
**Why it needs an ADR**: it establishes a project-wide invariant about how egress boundaries are
enforced, and it *intentionally contradicts* an existing documented trade-off in a specific context.
A future reader who finds the fail-open comment at `session_detail.py:374-375` and the fail-closed
factory needs the recorded reason they differ — otherwise one will be "fixed" to match the other.

### Not ADR-worthy

Config var naming (mechanical, follows `config.py` idiom); the per-project consent column (a schema
detail governed by the existing dual-DDL rule, ADR-006/ADR-007); the experiment design (a one-off
protocol, lives in this SPIKE); the six defect fixes (bug fixes, not decisions — though ADR-016 records
the `httpx` declaration as a corollary).

---

## Constraint Compliance

| Constraint | How the recommendation satisfies it |
|---|---|
| No model call on read/render/recall path | Naming stays worker-profile-only by construction (`container.py:144-145`); insight stays the single explicitly user-triggered endpoint; the port has no streaming surface, so there is no shape that invites a render-path call. |
| Every provider optional; degrade never fail | Port returns `None`/raises into the existing fail-open wrappers; `resolve_*` returns `None` when a lane is unreachable — the shipped "deliberate no-op, never a silent fallback to sending" contract (`session_naming_local_backend.py:338-343`) is generalized, not replaced. `{disabled:true}` preserved byte-identically in P1. |
| Redaction preserved as the egress gate | Strengthened from a code comment to a type (ADR-018) + guardrail test; hosted lanes still read only via `get_session_detail`. |
| Local (Ollama) stays first-class | `local` is `CCDASH_LLM_DEFAULT_LANE`'s default, is the arm every hosted model must **beat** in P4, is exempt from every egress gate, and is the outcome a null result preserves. |
| AAR loop stays deterministic | Untouched — not a call site, not in any phase; NO-GO cited, not re-explored. |
