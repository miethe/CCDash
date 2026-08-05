---
schema_version: 2
doc_type: spike
title: "Derived Session Naming (LLM / Embedding Lanes) — Feasibility Spike"
status: completed
created: 2026-08-04
feature_slug: automatic-session-naming
leg_id: derived-naming
confidence: 0.8
feasibility: feasible-with-constraints
incremental_points: 5          # exclusion (1) + one generative lane (4), on top of the 8-pt base
recommended_scope_points: 13   # THE PLANNING NUMBER: 8 base + 1 exclusion + 4 one generative lane
all_lanes_points: 18           # sum of every lane evaluated (1+4+4+9); includes the two deferred
recommended_tier: 2
recommended_lanes: [B]         # contested — see §2/§9; Lane A costs the same (4 pts) with strictly
                               # better constraint-3 posture. Orchestrator flagged for operator decision.
---

# Derived Session Naming — Feasibility Spike (4th leg)

Method: direct reads of `backend/runtime/container.py`, `backend/adapters/jobs/aar_review_sweep_job.py`
+ `aar_review_sweep_guards.py`, `backend/config.py`, `backend/application/services/agent_queries/
redaction.py` + `session_detail.py`, `backend/db/postgres_migrations.py` (session_embeddings DDL),
`backend/db/repositories/{session_embeddings.py,postgres/session_embeddings.py}`,
`backend/application/services/session_intelligence.py`, `backend/parsers/skill_provenance.py`,
`backend/db/sync_engine.py` (inheritance call site), `backend/routers/ai.py` +
`backend/services/ai_insight.py` (existing hosted-LLM precedent), `components/SessionCard.tsx`.

## 1. Extension point — worker-side, never on read path

`AARReviewSweepJob` (`backend/adapters/jobs/aar_review_sweep_job.py`) is the concrete precedent: a
`RuntimeJobAdapter`-registered job, conditionally constructed in `RuntimeContainer.startup()`
(`backend/runtime/container.py:210-218`) only when `profile.name in {"worker","worker-watch"}` AND
its flag is on — zero runtime cost when off. A `SessionNamingSweepJob` would live beside it at
`backend/adapters/jobs/session_naming_sweep_job.py`, registered in `container.py` next to the
`aar_review_sweep_job=` block, with its own `_export_profiles` gate. It reads eligible `sessions`
rows (`session_name IS NULL`), calls the derivation function (Lane-dependent), and **persists**
`session_name`/`session_name_source` via the existing `sessions` repository upsert path — reads
(`routers/api.py`, `session_detail.py`, `planning_sessions.py`, CLI/MCP/`ccdash_cli`) only ever see
the already-persisted column, exactly like `ai-title`/`thread_name_updated` today. This satisfies
constraint 4 by construction, identically to how AAR review's `get_review` triage never runs on a
request path.

**Input sourcing constraint (mirrors AAR's Hard Invariant #4):** the job must read the first-user
-message text via the **redacted** bundle (`session_detail.get_session_detail`, which already runs
`redact_entries` before returning — `session_detail.py:455`), never a raw JSONL read. This is a new,
explicit hard invariant for this feature, not yet enforced anywhere.

**Idempotency guard** mirrors `sync_engine.py:3307`'s `backfill_skill_name_inheritance` call
(`WHERE child.skill_name IS NULL`) exactly: any session with a non-null `session_name` — regardless
of source token — is never re-derived. Extending that same call site to also carry `session_name` is
the cheapest possible implementation for the deterministic subagent-inheritance slice (§5).

## 2. Constraint-3 / exfiltration — first-class, not a footnote

- **Lane A (local Ollama):** content never leaves the box. No exfiltration surface. Redaction gate is
  still recommended (defense-in-depth against a titled card literally rendering a leaked secret), not
  required for the off-box concern.
- **Lane B (hosted):** **acceptable only behind the redaction gate, and only for input text, never
  full transcripts.** `backend/application/services/agent_queries/redaction.py`'s Layer 1 pattern
  scan (`CCDASH_REDACTION_PATTERNS_ENABLED`, default true) is sufficient for this input shape — the
  extracted first user message is plain human text, not a tool call, so Layer 2
  (`CCDASH_REDACTION_TOOL_AWARE_ENABLED`) is not load-bearing here but should still run (it's on by
  default and free). **Existing precedent exists but does not already prove this safe**:
  `backend/services/ai_insight.py` already makes a server-side Gemini REST call
  (`CCDASH_GEMINI_API_KEY`, model `gemini-2.0-flash`, httpx, 30s timeout, graceful-disabled-on-no-key)
  — but it sends only aggregated numeric metrics/task titles, **never raw transcript content**, so it
  never needed the redaction layer. Wiring `redact_log_entry`-shaped scanning onto the extracted
  message before it is placed in the outbound prompt is genuinely new work for this feature.
- **Lane C:** no transcript content leaves the box for the *transfer* step (nearest-neighbour lookup
  is a local Postgres query). The *embedding-generation* step, if it uses a hosted embedding API, has
  the same exfiltration profile as Lane B and needs the same gate; a local embedding model avoids it
  entirely. Not yet decided because the embedding-generation step doesn't exist at all (§4).

## 3. Cost math (assumptions shown)

**Corpus scoping (see §5 for derivation):** the correctly-scoped candidate population — sessions
that are neither already provider-named nor structurally name-less (subagent/headless) — is
**3,145 of 10,958 local sessions (28.7%)**, extrapolated to **~4,764 of 16,600 node-PG sessions**
(ASSUMPTION: applies the local 28.7% ratio to the node corpus; the node's actual provider/subagent
mix is unmeasured).

| Lane | Assumption | Per-session | Local backfill (3,145) | Node backfill (~4,764, extrapolated) |
|---|---|---:|---:|---:|
| A (local, e.g. Ollama + small model) | warm daemon, ~200 in / 10 out tokens, ~1.5s amortized latency (untested locally — ASSUMPTION) | ~1.5s | ~79 min wall-clock | ~119 min wall-clock |
| B (hosted, Gemini Flash-class) | illustrative pricing $0.075/MTok in, $0.30/MTok out (ASSUMPTION — verify current pricing before implementation) | ~$0.000018 | ~$0.06 | ~$0.09 |
| B (hosted, Haiku-class) | illustrative pricing $1/MTok in, $5/MTok out (ASSUMPTION — verify current pricing) | ~$0.00025 | ~$0.79 | ~$1.19 |
| C (embedding transfer) | no generative $/token cost; embedding generation itself is cheap (embeddings have no output tokens) regardless of local/hosted choice | n/a | few cents total, if hosted embedding API used | n/a |

**Conclusion: $ cost is a non-issue at this scale for every lane.** The real cost drivers are
engineering effort (§8), exfiltration risk (§2), and — for Lane A — un-validated wall-clock/ops burden
of running a local model daemon. Naive full-corpus math (10,958/16,600 sessions, ignoring the
subagent/headless exclusion) is ~3.5× these numbers and still trivial — cost is not what should gate
lane selection.

## 4. Lane C specifics — `session_embeddings` exists, is schema-qualified, and is **structurally empty**

`app.session_embeddings` (Postgres schema `app`, `backend/db/postgres_migrations.py:1945-1966`) is
real DDL: `pgvector` extension, `embedding vector` column, unique index on
`(session_id, content_hash)`, lookup index on `(session_id, block_kind, block_index)`. It is
**enterprise/Postgres-only** — `migration_governance.py:112`'s
`_OBSERVED_ENTITY_ENTERPRISE_ONLY_CONCERNS = frozenset({"session_embeddings"})`, and the SQLite
compatibility repo (`backend/db/repositories/session_embeddings.py`) is a stub that always returns
`supported=False` and no-ops on write. **On local SQLite (the majority deployment target — repo-local
dev, most self-hosted single users), Lane C is categorically unavailable, not merely unpopulated.**

The row-population pipeline exists (`session_intelligence.py:build_session_embedding_blocks` chunks
each session's canonical messages into `message`/`window` text blocks with a `content_hash`,
inserted via `PostgresSessionEmbeddingRepository.replace_session_embeddings`), but the vector itself
is **never computed**: `session_intelligence.py:1117-1118` hardcodes `"embedding_model": ""` and
`"embedding_dimensions": 0`, and `postgres/session_embeddings.py:58`'s INSERT places a literal `NULL`
into the `embedding` column. Grep for any embedding-model call (`sentence_transformers`, `embed(`,
an embeddings REST endpoint) across `backend/` returns **zero hits** outside library internals. There
is also no ANN index (`hnsw`/`ivfflat`) on the `embedding` column — only the two non-vector btree
indexes above.

**This changes Lane C from "reuse" to "build."** The existing table is a *text-chunking scaffold*,
not an embedding store. Building Lane C requires: (a) choosing and wiring an embedding-generation
call (itself a Lane-A/B-shaped sub-decision — local model vs. hosted API, with the matching §2
exfiltration gate), (b) actually populating `embedding` for both the reference (named) corpus and the
candidate (unnamed) corpus, (c) adding an ANN index, (d) writing new nearest-neighbour query +
title-transfer logic (with a similarity-threshold gate, mirroring AAR's `CCDASH_AAR_REVIEW_MIN_
CONFIDENCE=0.64` pattern, to avoid transferring an unrelated title), and (e) accepting the
enterprise-Postgres-only ceiling as a permanent product constraint for this lane.

## 5. Excluding subagent/headless sessions — the real target population

Local corpus: 7,531 Claude Code + 3,427 Codex = 10,958 files.

| Segment | Count | % of local corpus | Naming path |
|---|---:|---:|---|
| Claude subagent sidechains | 5,462 | 49.8% | Deterministic — one-hop parent-title inheritance (extend `backfill_skill_name_inheritance`'s exact call site/shape, `sync_engine.py:3307`) or `agent-name` fallback. **Zero model calls.** |
| Codex `codex_exec` headless | 960 | 8.8% | Deterministic — `session_meta.payload.git.branch` fallback (95.0% coverage per the brief). **Zero model calls.** |
| **Subtotal, structurally name-less** | **6,422** | **58.6%** | Never a candidate for any generative/embedding lane. |
| Already provider-named (`ai-title` + `thread_name_updated`) | 1,391 | 12.7% | Already done; rank 1 in the fallback chain. |
| **Remaining candidate population (Lanes A/B/C target)** | **3,145** | **28.7%** | Claude top-level unnamed = 850 named/2,069 top-level → 1,219 unnamed; Codex non-headless unnamed = 3,427 − 960 − 541 = 1,926. |

**Only 28.7% of the local corpus is a genuine candidate for a derived-naming pass at all.** This
should further shrink once the deterministic fallback chain (rank 3: `last-prompt` 25.51% coverage,
slash-command extraction — both zero-model-call and untried before a generative call) is applied
first; that overlap was not measured in this leg and is a natural first sub-task of implementation.

## 6. Provenance vocabulary extension

Two new tokens, added to the same closed-vocabulary module recommended by the integration spike
(`backend/parsers/session_name_provenance.py`), following `skill_provenance.py`'s
frozenset-plus-fallback pattern exactly (unrecognised token → "unknown provenance", never hard-fail):

| Token | Trust rank vs. existing tokens | Meaning |
|---|---|---|
| `provider_persisted` | 1 (existing, strongest) | Unchanged. |
| `derived_deterministic` | 2 (existing) | Unchanged — zero-model-call extraction (last-prompt, slash-command, git-branch). |
| `derived_embedding_transfer` | 3 (new) | Lane C — nearest-neighbour title transfer. Ranked above generative because it is grounded in an actual similar, real, provider-named session rather than pure generation — but only when gated by a similarity threshold; an ungated transfer should not exist. |
| `derived_generative` | 4 (new) | Lanes A **and** B collapse to one token — the provenance column records "model-authored from thin input," not compute location. Weakest active tier: most likely to be generic or mildly off given ~200 input tokens. |
| `operator_set` | reserved (existing) | Unchanged, still out of scope. |

One token for both A and B keeps the closed vocabulary small (mirrors `KNOWN_SKILL_SOURCES`'s
few-entries shape); which model/lane produced a given `derived_generative` row is an operational
detail for logs, not a schema-contract concern.

## 7. Guards

- **Idempotency:** `WHERE session_name IS NULL` at the sweep's candidate-selection query — never
  re-derives a session with ANY existing name (provider, deterministic, or previously-derived).
- **Kill-switch + quota**, following the `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` /
  `CCDASH_AAR_ESCALATION_QUOTA` / `_WINDOW_HOURS` naming pattern exactly:
  - `CCDASH_SESSION_NAME_DERIVE_ENABLED` (recommend default **false** — unlike AAR's default-true,
    this feature introduces a genuinely new off-box-egress surface for Lane B and should launch
    opt-in).
  - `CCDASH_SESSION_NAME_DERIVE_LANE` (`"generative"` | `"embedding_transfer"`, absent → disabled;
    fail-closed on an unrecognised value, never a silent default-on).
  - `CCDASH_SESSION_NAME_DERIVE_QUOTA` (default 200/tick) + `CCDASH_SESSION_NAME_DERIVE_WINDOW_
    HOURS` (default 24) — bounds provider rate-limit exposure and blast radius of a misconfigured
    loop; not a $ concern per §3.
  - `CCDASH_SESSION_NAME_DERIVE_SWEEP_INTERVAL_SECONDS` (default 1800, mirrors
    `CCDASH_AAR_REVIEW_SWEEP_INTERVAL_SECONDS`).
- **Fail-open:** any model-call failure (timeout, 4xx/5xx, Ollama unreachable) leaves `session_name`
  NULL for that session and logs — never crashes the sweep tick, never blocks the next candidate
  (mirrors `AARReviewSweepJob`'s per-document try/except-and-continue shape).
- **Offline-CLI degradation:** per the existing offline-CLI contract (root CLAUDE.md, "Offline CLI
  mode"), worker-only enrichments degrade to null when there is no worker — `session_name` simply
  stays absent for offline-CLI-synced rows. Contract state, not a bug, identical to cost/analytics
  KPIs today.

## 8. Incremental story points (H1/H2/H6 applied on top of the 8-pt base)

| Item | Points | Rationale |
|---|---:|---|
| Base (from integration spike) | 8 | Schema/provenance/repo/parser/API/FE wiring — unchanged. |
| Deterministic subagent/headless exclusion (§5) | 1 | H1: near-free — extends an existing one-hop inheritance call site (`sync_engine.py:3307`) with the same shape; the base estimate assumed "no inheritance mechanism needed," which this leg revises. |
| Lane A (local LLM) | 4 | New worker job (mirrors `AARReviewSweepJob`'s shape) + new Ollama HTTP client (no existing precedent, unlike Gemini) + config flags + guard tests. H6: +~15% plumbing folded in. |
| Lane B (hosted, Gemini-class) | 4 | Reuses `ai_insight.py`'s transport pattern (H2-favorable: cuts what would otherwise be new-client cost) but adds the genuinely-new redaction-gate wiring + compose-allowlist fix for `CCDASH_GEMINI_API_KEY` (currently `.env.example`-only, not in the `x-backend-shared-env` allowlist — same class of gap `5cb8e00` fixed for five other flags) + quota/kill-switch config. |
| Lane C (embedding transfer) | 9 | H1+H6: not a reuse — embedding-generation call (itself an A/B-shaped sub-decision), ANN index migration, new kNN query + similarity-threshold transfer logic, enterprise-Postgres-only gating and messaging. Comparable in size to the entire base estimate because it is a new subsystem, not a field addition. |
| **Recommended near-term total** (base + exclusion + Lane B, flagged) | **13** (8 + 1 + 4) — reported as `incremental_points: 5` (exclusion + Lane B only, on top of the already-scoped 8-pt base) | |
| **Combined, all lanes evaluated** | **26** (8 + 1 + 4 + 4 + 9) — reported as `combined_points: 18` (sum of all incremental work, excluding the base) | |

**Tier recommendation: Tier 2** for the leg as a whole. The deterministic exclusion slice alone would
stay Tier 1 (additive, no behavior change), but Lane B introduces a new off-box network call and a
new worker job — a materially higher review/blast-radius bar than the base's pure-additive-column
scope, even default-off. Lane C, if ever built, would independently warrant its own Tier 2/3 review
(new subsystem, enterprise-only ceiling).

## 9. Recommendation

**Ship in phases; do not ship all three lanes.**

1. **Deterministic subagent/headless exclusion first** (1 pt, Tier 1) — closes 58.6% of the local
   corpus to "correctly has no derived name, by design" with zero model-call surface, zero exfiltration
   risk, and near-zero engineering cost (extends an existing call site). Ship unconditionally.
2. **One generative lane, default-off: Lane B (Gemini Flash-class)** (4 pts, Tier 2) — reuses the
   existing `CCDASH_GEMINI_API_KEY` + httpx transport precedent from `ai_insight.py`, is the cheapest
   $ lane, and requires no new local infrastructure dependency (unlike Lane A's Ollama daemon). Gate
   behind `CCDASH_SESSION_NAME_DERIVE_ENABLED=false` by default; the redaction-gate wiring (§2) is the
   one genuinely new, safety-critical piece and should get its own dedicated test file (mirrors
   `test_aar_review_no_llm_imports.py`'s static-walk-contract rigor, inverted: a **positive**
   assertion that every outbound prompt has passed `redact_entries` first).
3. **Defer Lane A** — same generative shape as Lane B with strictly more operational cost (a local
   model daemon to deploy/monitor/upgrade) and no exfiltration benefit large enough to justify it
   given Lane B's redaction gate already closes that gap. Revisit only if org policy tightens against
   *any* off-box call regardless of redaction.
4. **Defer Lane C** — it is a build, not a reuse (§4), it is permanently unavailable on local SQLite
   (the majority deployment target), and at 9 points it is as large as the entire base feature.
   Revisit only if `session_embeddings` is ever populated for an unrelated feature (making the
   embedding-generation half free) or if Lane B's title quality proves inadequate in practice.

This is a **deterministic-first, one-flagged-generative-lane** phasing — consistent with this
project's own AOS constraint-4/constraint-3 posture and with how the AAR-review and routing-feedback
workers were both shipped default-gated behind a single flag before wider rollout.

## 10. Risk register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Title quality/hallucination on thin input (~200 tokens, first message only) | Medium | Medium | `derived_generative`'s deliberately-lower trust rank (§6) signals FE/consumers to treat it as best-effort; consider a min-length gate (skip derivation, leave null, below N chars of first message) rather than forcing a low-quality title. |
| Cost runaway on backfill | Low | Low | §3 shows $ cost is trivial at this scale even unscoped; the real bound is the quota/window guard (§7), which caps request *rate*, not spend. |
| Exfiltration (Lane B off-box egress) | High | Low (with gate) / High (without) | Mandatory redaction-gate wiring (§2) before any outbound prompt; positive test asserting every egress path passed `redact_entries`; default-off flag until that test exists. |
| Provenance confusion between provider-set and derived names | Medium | Low | Closed-vocabulary tokens (§6) with strict trust ranking; FE should visually distinguish `provider_persisted`/`derived_deterministic` from `derived_generative`/`derived_embedding_transfer` (e.g. a subtle badge), though that is a polish decision, not a contract requirement. |
| Re-derivation churn (job re-runs and overwrites a name) | Medium | Low | `WHERE session_name IS NULL` idempotency guard (§7) is unconditional — no code path re-derives an already-named session, mirroring the AAR sweep's dedup-ledger discipline. |
| `CCDASH_GEMINI_API_KEY` not in the compose env-allowlist | Medium | High (standing hazard, per `5cb8e00`) | Add to `x-backend-shared-env` in the same change that flips `CCDASH_SESSION_NAME_DERIVE_ENABLED` on for a container deployment, or the flag silently no-ops in `worker`/`worker-watch`. |
| Lane C similarity-threshold miss (transfers an unrelated title) | Medium | Medium (if ever built) | Similarity-threshold gate mirroring `CCDASH_AAR_REVIEW_MIN_CONFIDENCE`; below threshold → no transfer, leave null. |

## Confidence rationale

**0.8.** High confidence on the mechanical facts (worker extension point, redaction module contents,
`session_embeddings`'s empty-vector state, the existing Gemini-call precedent, the inheritance
call site) — all grounded in direct file reads, not inference. Held below 0.9 because: (1) Lane A's
wall-clock assumption is untested on this hardware; (2) the node PG corpus's provider/subagent mix is
extrapolated from the local ratio, not measured; (3) LLM pricing figures are point-in-time estimates
explicitly flagged for pre-implementation verification; (4) the overlap between the 28.7% candidate
population and the untried rank-3 deterministic fallbacks (last-prompt, slash-command) was not
measured, so the true generative-lane target could be smaller than stated.
