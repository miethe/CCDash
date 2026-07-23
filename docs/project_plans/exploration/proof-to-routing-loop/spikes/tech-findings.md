---
leg: tech
confidence: 0.75
feasibility: feasible-with-constraints
---

# Tech Feasibility Spike — Proof → Routing Feedback Loop

## 1. Feasibility verdict

**Feasible-with-constraints**: CCDash can clone the shipped AAR-review mechanics
(worker-primed deterministic rollup, `agent_queries/` service, REST/MCP/CLI PULL surface,
capability gate, default-off flag) end-to-end with confirmed-captured `model`/`profile`/
`effort_tier` columns — but the tuple's most load-bearing field, `task_class`, has exactly
one deterministic candidate (`skill_name`) and this repo contains **no evidence** that
candidate's vocabulary joins the delegation-router's own `task_class` taxonomy (that
taxonomy lives in a repo this leg cannot see). This matches the charter's own
**conditional** verdict shape, not an unqualified go.

## 2. `task_class` derivation — the crux

Options assessed, evidence-based:

| Candidate | Source | Coverage | Stability | Verdict |
|---|---|---|---|---|
| `sessions.skill_name` | `_primary_skill_name()`, `backend/parsers/platforms/claude_code/parser.py:1237-1249`; column `backend/db/sqlite_migrations.py:~226` (Phase 5 detection columns) | **Sparse** — only populated when a session invoked a skill via `skillLoads`; `None` (explicit null contract, not `""`) otherwise | Stable string once present (a real skill identifier, e.g. a SkillMeat skill name) | **Best available candidate**, but only covers the subset of sessions that route through named skills |
| `sessions.command_slug` | Populated at sync time (`backend/db/repositories/sessions.py:94,144`); materialized badge column (T1-010) | Broader coverage than `skill_name` (any slash-command session) but is a UI-display slug, not a task-taxonomy label | Deterministic per session, but vocabulary is CCDash's own command-slug convention | Weaker candidate — even less likely to be a *task* label a router would recognize |
| Feature "tier" | `tier: str = "core"` fields on feature models (`backend/models.py:3275,3313`) | This is a **feature-priority** tier (core/nice-to-have), not a task-*type* taxonomy | N/A — wrong semantic axis | **Rejected** — conflates feature triage priority with task classification |
| `workflow_id` | column exists (`sessions.workflow_id`, Phase 5) | Identifies a workflow *instance*, not a task *class* | High cardinality (near-unique per run) | **Rejected** — wrong grain (instance, not class) |

**Best candidate: `skill_name`** (with `command_slug` as a fallback bucket for
non-skill sessions, e.g. `_unclassified` or a slug-derived class). It is the only field
that is (a) already captured with no new capture path, (b) a genuine *task-type* label
rather than a priority tier or run-instance id, and (c) stable/deterministic once present.

**Can it join an external taxonomy? Honest answer: unconfirmed, and this repo cannot
confirm it.** `skill_name` values are whatever SkillMeat/skill names CCDash happens to
observe in a session's `skillLoads` — an artifact of *this* repo's skill catalog, not a
shared vocabulary negotiated with the delegation-router. The design spec's own Open
Question 1 states this is unresolved; the sibling `risk` leg (already written,
`spikes/risk-findings.md` §2-3) independently reaches the same conclusion and flags it
as the single highest-severity risk: a **silent non-join** (the rollup ships real
`sample_count`s that never intersect the router's own task_class keys, with no error to
signal the mismatch). I concur: CCDash-side derivation is mechanically solvable; the
*join* is a cross-repo vocabulary-negotiation problem this leg cannot close, matching the
charter's `conditional` branch verbatim ("task_class is derivable CCDash-side but the
exact join... requires a cross-repo contract negotiation before build").

A secondary consequence: because `skill_name` is null for any session that didn't invoke
a named skill, a large fraction of real sessions would fall into an `_unclassified` /
empty `task_class` bucket — a coverage gap independent of the taxonomy-join question (see
sibling `value` leg for the density implication).

## 3. Tuple field capture — confirmed/refuted per field

| Field | Status | Evidence |
|---|---|---|
| `model` | **Confirmed** — always-present column | `sessions.model TEXT DEFAULT ''`, `backend/db/sqlite_migrations.py:159` |
| `provider` | **Confirmed, but derived — not a raw captured column** | No `model_provider`/`modelProvider` column exists anywhere in `sessions` DDL (grepped `backend/db/sqlite_migrations.py`, `backend/db/postgres_migrations.py` — zero matches). `modelProvider` is computed at read/serialization time by `derive_model_identity()` (`backend/model_identity.py:29-79`) parsing the first token of the `model` string (`"claude-…" → "Claude"`, `"gpt-…"/"openai-…" → "OpenAI"`, else title-cased). **The spec's claim that provider is "captured" is technically imprecise** — it is deterministically *derivable* from an always-captured field, which is functionally equivalent for a rollup's GROUP BY key, but the row is not written with a provider value at ingest time. |
| `profile` | **Confirmed, but conditionally populated** | Column `sessions.profile TEXT` added via `_ensure_column(db, "sessions", "profile", "TEXT")` (`backend/db/sqlite_migrations.py:3053`, dup at `:3956`); populated in the parser from the **launch-time capture sidecar** (`backend/parsers/platforms/claude_code/parser.py:829-887`, esp. `:844,885`). The sidecar (`<session-id>.capture.json`) is written **only if** a `SessionStart` hook + wrapper script exporting `CCDASH_LAUNCH_PROFILE`/`CCDASH_LAUNCHER`/`CCDASH_LAUNCH_EFFORT`/`CCDASH_LAUNCH_MODEL` is installed (`docs/guides/launch-time-capture-convention.md`). **Fail-open**: missing hook/sidecar ⇒ `null`, never a defaulted value, and this is Phase-11-forward only (no retrospective backfill for pre-Phase-11 sessions). So the column and code path are real, but real-world population is opt-in and possibly sparse depending on operator setup — this must be verified live by the sibling `value` leg. |
| `effort_tier` (a.k.a. `effortTier`/effort) | **Confirmed, same conditional-capture caveat as `profile`** | Same column family/mechanism: `_ensure_column(db, "sessions", "effort_tier", "TEXT")` (`:3054,:3957`); parser wiring `backend/parsers/platforms/claude_code/parser.py:4540` (`effortTier=capture_sidecar.get("effortTier")`) |
| `model_variant` (launch-time model id, e.g. `claude-opus-4-8[1m]`) | **Confirmed, same conditional-capture caveat** | `_ensure_column(db, "sessions", "model_variant", "TEXT")` (`:3055,:3958`); parser wiring `:4542`. Distinct from the always-present `model` column — this is specifically the *launch-time* requested variant, only known via the sidecar. |
| `launcher` | **Confirmed, same mechanism** (not part of the spec's tuple but shares the capture path) | `_ensure_column(db, "sessions", "launcher", "TEXT")` (`:3052,:3955`) |

**Net finding on (b):** the charter explicitly said "do NOT trust the spec's claim; confirm
it." Confirmed with one material correction: `provider` is a derived value, not a raw
captured column, and `profile`/`effort_tier`/`model_variant` are real columns fed by an
**opt-in, fail-open sidecar mechanism**, not an unconditional per-session capture as the
spec's prose implies ("CCDash already ingests... `modelProvider`, `profile`,
`effortTier`... plus..."). The columns and plumbing exist and are shipped
(Phase 11, `T11-003`/`T11-004`); whether they are *populated* for the operator's actual
session corpus is a live-data question for the `value` leg, not a code-existence question.

## 4. Integration points — concrete files/layers

Mirroring the `aar_reviews`/`system_metrics.py` precedent exactly:

- **Storage decision (spec OQ2)**: two viable patterns already shipped in this repo —
  - *Read-time aggregation* (no new table): `backend/application/services/agent_queries/system_metrics.py` — GROUP BY queries run live over `sessions` per request, `memoized_query`-cached (`_system_token_rollup_params`, `.cache.py`). Cheapest to build; freshness = cache TTL.
  - *Persisted rollup table* (new table): `aar_reviews` DDL (`backend/db/sqlite_migrations.py:1445-1466`, dup CREATE at `:4260-4277`) + `backend/db/repositories/aar_reviews.py` repo + `backend/scripts/aar_reviews_backfill.py` one-time backfill + `backend/adapters/jobs/aar_review_sweep_job.py` periodic sweep. Heavier to build (migration + repo + backfill + sweep + dedup-ledger guards), buys point-in-time snapshot stability and decay/window bookkeeping the spec's §5 guardrails want.
  - **Recommendation for a build**: start with the read-time pattern (`system_metrics.py` shape) for v1 — the aggregation here (GROUP BY task_class/model/provider/profile with count/avg/threshold) is simpler than AAR's document-to-session correlation and does not obviously need persisted state; revisit persistence only if decay/window semantics (§5) prove awkward to compute live.
- **Query service**: new module `backend/application/services/agent_queries/routing_rollup.py` (sibling of `system_metrics.py` and `aar_review.py`), registered in `backend/application/services/agent_queries/__init__.py` alongside `AARReviewQueryService`/`SystemMetricsQueryService`.
- **Worker priming** (only needed if the persisted-table path is chosen): `backend/runtime/container.py:200-206` (job constructed iff `profile == "worker"` and its enable-flag is true, exact pattern used for `aar_review_sweep_job`); `backend/adapters/jobs/runtime.py:2646-2706` (`_start_aar_review_sweep_task` — periodic `asyncio.Task` loop, interval clamp, `otel` span, error handling) is the template for a `_start_routing_rollup_sweep_task`.
- **REST surface**: new handler module `backend/routers/_client_v1_routing_rollup.py` (sibling of `backend/routers/_client_v1_aar_review.py`), wired into `backend/routers/client_v1.py` next to `get_aar_review_v1` (`client_v1.py:59`); new route `GET /api/v1/routing/rollup` per the spec's sketch.
- **MCP surface**: new tool in `backend/mcp/tools/reports.py` (sibling of `ccdash_aar_review` tool, `:28-39`).
- **CLI surface**: new command in `backend/cli/commands/report.py` (sibling of `aar_review` command, `:66-108`).
- **Capability gate**: append a new string (e.g. `"routing-rollup"`) to `_V1_CAPABILITIES` in `backend/routers/client_v1.py:145-149` — exact same one-line-list pattern the `"aar-review"` entry already uses (`:149`), served by the existing `/api/v1/capabilities` handler (`:163-178`).
- **Config flag**: `backend/config.py` — add `CCDASH_ROUTING_ROLLUP_ENABLED = _env_bool("CCDASH_ROUTING_ROLLUP_ENABLED", False)` directly beside the precedent `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED = _env_bool(..., False)` (`config.py:112`); companion tunables (`CCDASH_ROUTING_ROLLUP_MIN_SAMPLE_SIZE`, window/decay knobs) follow the `CCDASH_AAR_REVIEW_MIN_CONFIDENCE`/`CCDASH_RANKING_MIN_SAMPLE_SIZE` (`config.py:90`) numeric-threshold pattern.
- **No-LLM CI guard**: port the existing AST-walk test (referenced in `risk-findings.md` §2 as `test_aar_review_no_llm_imports.py`) to the new module — trivial, precedent exists.

## 5. Story-point estimate vs. `aar_reviews` anchor

The shipped AAR-review feature (commit `7d96c3e`) spans 7 phases with per-phase point
ranges recorded in `docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1/phase-*.md`:
P1 verdict-persistence 5-7, P2 evidence-enrichment 5-7, P3 skillmeat-5th-flag 3-5,
P4 read-surfaces 4-6, P5 consumer-contract 5-8, P6 writeback-worker 6-9,
P7 documentation 2-3 — **total ≈ 30-45 points** for the full feature.

This rollup does **not** need P2 (evidence-enrichment traversal: doc→feature→plan→task
graph walk) or P3 (SkillMeat semantic 5th-flag lookup) — those are AAR-document-specific
correlation logic with no analogue here (aggregation is a flat GROUP BY over already-typed
session rows, not a multi-hop entity-link traversal). It also does not need P6's
escalation-quota / self-referential-session guards (no self-recursion risk: the rollup
reads sessions, it does not write AAR documents that could be re-ingested as sessions).

**Estimate: 10-16 points** for a v1 build (read-time aggregation path):
- `task_class` derivation module + tests (novel logic, sparse-coverage handling): 2-3
- Rollup query service (GROUP BY + threshold/window arithmetic, `system_metrics.py`-shaped): 3-4
- REST endpoint + capability-gate line + config flag(s): 1-2
- MCP + CLI surfaces (thin wrappers, precedent-heavy): 1-2
- Consumer-contract doc + operator guide (mirrors `aar-review-loop.md` + the v1 consumer-contract doc): 2-3
- No-LLM CI guard port: 1

Add **+6-9 points** if the persisted-table path is chosen instead (migration DDL, repo
class, backfill script, sweep-worker registration in `container.py`/`runtime.py`,
dedup bookkeeping) — pushing the total toward AAR's P1+P6 weight (11-16 pts for just
those two phases).

**Delta justification**: lower than AAR's full 30-45 because the two heaviest AAR
phases (multi-hop evidence correlation, semantic 5th-flag) have no analogue; but the
estimate does **not** capture the cross-repo taxonomy-join risk from §2 — that risk is a
*blocking precondition*, not a story-point cost CCDash-side work can absorb.

## 6. Open architectural questions

- **OQ-1** (= spec's own OQ1): Is `skill_name` (possibly `_unclassified`-bucketed) an
  acceptable v1 `task_class`, or must CCDash wait for a negotiated shared taxonomy before
  shipping any `task_class` field at all? This is the crux the charter's `conditional`
  branch names.
- **OQ-2**: Read-time aggregation (`system_metrics.py` pattern) vs. persisted table
  (`aar_reviews` pattern) for the rollup — this leg recommends read-time for v1 (§4) but
  the sibling `value` leg's density findings may change that calculus (a very sparse,
  rarely-changing dataset might favor a cheap persisted snapshot over repeated live
  GROUP BYs).
- **OQ-3**: Should the rollup response make the `_unclassified`/null-`skill_name` bucket
  visible (transparency about coverage gaps) or suppress it (avoid a router key it can
  never match)? AAR's precedent (never synthesize a default, always null-contract) argues
  for visibility.
- **OQ-4**: Should `provider` be persisted (materialized at ingest time via
  `derive_model_identity`) rather than re-derived at every rollup query? Low cost either
  way; only matters if the read-time-aggregation path is chosen and provider grouping
  becomes a hot query.

## 7. Confidence score

**0.75** — high confidence in every CCDash-side mechanical claim (all cited against
concrete DDL/parser/router line numbers, no speculation); the score is capped below 0.8
solely because the pivotal sub-question — whether `skill_name` (or any CCDash-derivable
string) actually joins the delegation-router's task_class taxonomy — is structurally
unanswerable from this repo, independently corroborated by the sibling `risk` leg.
