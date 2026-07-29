---
title: "Phase 3: Rollup Compute Service"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-29
updated: 2026-07-29
feature_slug: "proof-to-routing-loop"
feature_version: "v1"
phase: 3
phase_title: "Rollup Compute Service"
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria:
  - "Phase 2 complete — routing_rollup table + repository exist"
exit_criteria:
  - "Determinism + mapping-fidelity + no-LLM-import tests green"
related_documents:
  - docs/guides/aar-review-loop.md
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: []
owner: null
contributors: []
priority: medium
risk_level: high
category: "product-planning"
tags: [phase-plan, implementation, infrastructure, routing-feedback, no-llm, algorithmic]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/routing_rollup.py
  - backend/application/services/agent_queries/models.py
  - backend/tests/test_routing_rollup_determinism.py
  - backend/tests/test_routing_rollup_no_llm_imports.py
---

# Phase 3: Rollup Compute Service

**Parent Plan**: [Implementation Plan: Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~2 days
**Effort**: 4 story points
**Dependencies**: Phase 2 complete — `routing_rollup` table + repository exist
**Team Members**: backend-architect, python-backend-engineer

---

## Phase Overview

This phase implements `RoutingRollupQueryService` — the aggregation, mapping, and metric-computation
core of the Proof → Routing Feedback Loop. It is **the only genuinely algorithmic phase in the entire
feature** (H3 anchor per the decisions block, `.claude/worknotes/proof-to-routing-loop/decisions-block.md`
§4): every other phase (1, 2, 4, 5, 6) is a mechanical, near-1:1 clone of the shipped Automated AAR
Review Loop (`aar_reviews` table → `AARReviewSweepJob` → `agent_queries/aar_review.py` →
REST/MCP/CLI). Phase 3 is where the new logic actually lives — aggregation grain, mapping application,
protected-class policy, and the D5 metric-payload design.

**Hard invariant (AOS Constraint 4): zero LLM/model-client imports anywhere in this module's
transitive closure.** `routing_rollup.py` and every module it (transitively, statically) imports under
`backend/` must never import a model/LLM client library (`anthropic`, `openai`, `litellm`, `langchain`,
`google.generativeai`) and must never reference a Task/Agent-dispatch helper symbol. This is pure SQL
aggregation + threshold/arithmetic only — the same hard invariant the shipped AAR-review loop enforces
(`backend/tests/test_aar_review_no_llm_imports.py`), CI-enforced here for the first time on this new
module by T3-005.

### Goals

- Aggregate sessions at `(project_id, source_skill_name, model)` grain over a rolling window with a
  single pure-SQL `GROUP BY` query — zero N+1, zero ORM lazy-loading.
- Apply the pinned v1 `skill_name → task_class` mapping (Phase 1's `routing_feedback_contract.py` +
  vendored `routing_task_map_v1.json`) to derive `task_class` as a **write-time-derived column** —
  never the raw `skill_name` string (D3/FR-6, PRD §6.3).
- Implement the `_unclassified` / protected-class (`orchestration`, `mode_d`) coverage-only policy:
  `eligible_for_adjustment` hardcoded `False`, never overridable, `_unclassified` always emitted
  regardless of config, protected classes gated by `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`.
- Derive `provider` exclusively via the existing `backend/model_identity.py::derive_model_identity()`
  — never an independently-keyed derivation.
- Compute the full D5 metric payload (`sample_count`, `success_rate`, `cost_index`, `regression_rate`,
  `confidence`, `eligible_for_adjustment`, `window_start`/`window_end`, `freshness_ts`) per key, per
  PRD §6.3's literal JSON example — cited there, not reinvented here.
- Add `RoutingRollupKeyDTO` / `RoutingRollupResponseDTO` to `backend/application/services/agent_queries/models.py`
  (the same file `AARReviewDTO` lives in), as plain `BaseModel` subclasses mirroring `AARReviewDTO`'s
  pattern exactly (`models.py:341-370`) — **not** an `AgentQueryEnvelope` subclass.
- Prove determinism (two invocations over an unchanged fixture window produce field-identical rows)
  and the no-LLM invariant via automated CI guards, not manual review.

### Architecture Focus

This phase implements a transport-neutral compute service following this repo's `agent_queries/`
convention:

- **Layer**: Application service (`backend/application/services/agent_queries/`) — consumed by the
  Phase 4 worker sweep and the Phase 5 REST/MCP/CLI transports; imports nothing from `routers/`,
  `cli/`, or `mcp/`.
- **Patterns**: Clone the query-shape conventions of two existing worker-primed rollup precedents in
  the same directory — `backend/application/services/agent_queries/aar_review.py` (module-docstring
  no-LLM invariant statement, direct `aiosqlite` queries, no ORM) and
  `backend/application/services/agent_queries/system_metrics.py` (pure `GROUP BY` aggregation
  functions, e.g. `_fetch_model_family_tokens`'s `GROUP BY model`).
- **Standards**: ADR-006/007 write-path discipline does not apply here (this phase is read/compute
  only — Phase 4 owns the write path); AOS Constraint 4 (no-LLM) is the binding standard, enforced by
  T3-005.

---

## Task Breakdown

### Epic: Rollup Compute Service

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---|---|---|---|---|---|---|---|---|
| T3-001 | `RoutingRollupQueryService` skeleton | New `backend/application/services/agent_queries/routing_rollup.py`, transport-neutral per this repo's `agent_queries/` convention. Pure-SQL `GROUP BY` aggregation of sessions at `(project_id, source_skill_name, model)` grain over a rolling window (`CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS`, default 30). No ORM lazy-loading, zero N+1. | Correct grouping on a fixture DB; zero N+1 queries | 1 pt | backend-architect | sonnet | extended | Phase 2 complete |
| T3-002 | Apply pinned mapping + protected-class policy | Load `routing_feedback_contract.py`'s `MAPPING_JSON_PATH`; derive `task_class` per row via lookup. Resolves-to-`_unclassified` (no entry found OR an entry EXISTS but explicitly resolves to `_unclassified`, e.g. `codex`/`claude-api`/`ica-delegate`) AND resolves-to-protected (`orchestration`, `mode_d`) both emit coverage-only: `task_class="_unclassified"` (ALWAYS emitted per FR-7) or the protected class name (gated by `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`), both with `eligible_for_adjustment` hardcoded `False`, never overridable. Raw `skill_name` never copied into `task_class` (D3/FR-6). | `_unclassified` always present when unmapped OR executor-identity names exist; protected rows never `eligible_for_adjustment=true` | 1 pt | backend-architect | sonnet | extended | T3-001 |
| T3-003 | Provider + coverage counters | Call EXISTING `backend/model_identity.py::derive_model_identity()` for `provider` — never independently keyed. Compute `mapped_count`/`unclassified_count` keyed by resolved `task_class` (never by mapping-entry presence), deduplicated `distinct_unmapped_skill_names` (FR-7). | Counters match a hand-computed fixture (`mapped_count + unclassified_count == total_rows`); provider never diverges from `derive_model_identity()` | 0.5 pts | python-backend-engineer | sonnet | adaptive | T3-002 |
| T3-004 | D5 metric payload | Per key compute: `sample_count` (int), `success_rate` (float 0-1), `cost_index` (float, 1.0=baseline), `regression_rate` (float 0-1), `confidence` (float 0-1, saturating with sample_count), `eligible_for_adjustment` (bool = `sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`, resolves OQ-3), `window_start`/`window_end` (ISO-8601, resolves OQ-2), `freshness_ts` (ISO-8601). Never suppress sub-threshold keys (AC-5). Add `RoutingRollupKeyDTO` + `RoutingRollupResponseDTO` to `models.py` mirroring `AARReviewDTO`. | Every key carries all D5 fields; sub-threshold keys still present | 1 pt | backend-architect | sonnet | extended | T3-003 |
| T3-005 | Determinism + no-LLM guard | New `backend/tests/test_routing_rollup_determinism.py`: two invocations over an unchanged fixture window produce field-identical rows. New `backend/tests/test_routing_rollup_no_llm_imports.py`: AST-walk the transitive import graph of `routing_rollup.py`, cloning `backend/tests/test_aar_review_no_llm_imports.py`'s guard shape, asserting zero imports from `backend.adapters.agents`/`services.agents` or any model-client SDK. Note: Phase 6 (T6-001) later EXTENDS this same guard file to also cover Phase 4's sweep-job module — do not mark it "final" here. | Both tests pass; guard fails loudly on any accidental model import | 0.5 pts | python-backend-engineer | sonnet | adaptive | T3-004 |

**Model Selection Guidance**: All tasks in this phase run on `sonnet` — three at `extended` effort
(T3-001, T3-002, T3-004 — the aggregation/mapping/metric-design core, this feature's highest reasoning
need) and two at `adaptive` (T3-003, T3-005 — mechanical extraction/test-authoring work). No external
models or `haiku` tasks in this phase.

---

## Detailed Task Specifications

### Task T3-001: `RoutingRollupQueryService` skeleton

**Estimate**: 1 point
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: extended
**Dependencies**: Phase 2 complete
**started**: null
**completed**: null
**verified_by**: [T6-004]
**evidence**: []

**Description**:
Create `backend/application/services/agent_queries/routing_rollup.py` as a new transport-neutral
module. Implement the single aggregation entry point (a `RoutingRollupQueryService` class or
module-level async function — match whichever shape `aar_review.py`/`system_metrics.py` use for
their primary compute entry point) that issues one pure-SQL `GROUP BY project_id, source_skill_name,
model` query against the sessions table for a rolling window bounded by
`config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` (default 30, landed by Phase 1). This task freezes the
raw aggregated-row shape (`project_id`, `source_skill_name`, `model`, session counts/success signal
inputs) that T3-002 through T3-004 build on — do not add mapping, provider, or metric logic here.

**Acceptance Criteria**:
- [ ] Query returns exactly one row per distinct `(project_id, source_skill_name, model)` combination present in a hand-built fixture window — verified by a fixture-DB unit test.
- [ ] Zero N+1: a single SQL statement is issued for the whole aggregation call (assert via a query-counting DB wrapper or connection-level instrumentation), regardless of the number of distinct keys in the fixture.
- [ ] No ORM lazy-loading anywhere in the code path — direct `aiosqlite`/DB-connection-singleton query, matching `aar_review.py`'s `import aiosqlite` pattern, not an ORM session object.
- [ ] Window boundary is read from `config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS`, not hardcoded.

**Implementation Notes**:
- Clone the module-docstring convention from `aar_review.py` (states the file should be greppable for
  any LLM/agent-invocation import and find none) and the `GROUP BY` query-shape convention from
  `system_metrics.py::_fetch_model_family_tokens` (`GROUP BY model`).
- Reuse `backend/application/services/agent_queries/_filters.py::resolve_project_scope` /
  `resolve_time_window` if their existing signatures fit the per-project / rolling-window resolution
  need — do not hand-roll a parallel window-resolution helper if the existing one applies.
- This task's output is consumed directly by Phase 4's `RoutingRollupSweepJob` (not yet built) — the
  raw-row shape frozen here is the read contract Phase 4 depends on.
- **Grain clarification (companion fix)**: the persisted `routing_rollup` table's PRIMARY KEY is
  `(project_id, source_skill_name, model)` — `window_start` is NOT part of the key. Because of this,
  each worker sweep's aggregation (computed by this service, fresh from `sessions` each sweep, never
  read from the persisted table — per this Phase Overview's own read-rule note) OVERWRITES the single
  row per key via upsert when Phase 4 persists it. The table never accumulates one row per historical
  window, and any downstream read of `routing_rollup` always returns exactly one current row per key,
  never a multi-row "latest window" selection. This task's own aggregation query is unaffected by this
  note — it is scoped to `sessions`, not `routing_rollup` — but the raw-row shape it freezes here is
  exactly what Phase 4 upserts under this grain.

**Files Involved**:
- `backend/application/services/agent_queries/routing_rollup.py` - new module; aggregation query + skeleton entry point
- `backend/application/services/agent_queries/_filters.py` - read-only reference for window/project-scope helpers

---

### Task T3-002: Apply pinned mapping + protected-class policy

**Estimate**: 1 point
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: extended
**Dependencies**: T3-001
**started**: null
**completed**: null
**verified_by**: [T6-005]
**evidence**: []

**Description**:
For every aggregated row from T3-001, derive `task_class` by looking up `source_skill_name` against
the pinned mapping loaded from Phase 1's `routing_feedback_contract.py::MAPPING_JSON_PATH`
(vendored `routing_task_map_v1.json`). Coverage is determined by the **resolved `task_class` value
itself, not by whether a mapping entry was found** — three resolved outcomes, each with distinct
policy:

1. **Resolves to a normal `task_class`** — row proceeds to T3-003/T3-004 as an ordinary routing key.
2. **Resolves to `task_class = "_unclassified"`** — this covers BOTH (a) no mapping entry found for
   `source_skill_name`, AND (b) a mapping entry EXISTS and explicitly maps to `_unclassified` (the
   mapping table carries entries for executor-identity skill names — e.g. `codex`, `claude-api`,
   `ica-delegate` — because an executor identity is not a classifiable task, and their resolved
   `task_class` is itself `_unclassified`). Both cases are policy-identical: `eligible_for_adjustment`
   hardcoded `False`, row **always emitted** regardless of any config flag (FR-7 mandates this
   visibility unconditionally). Do not treat "no mapping entry ≡ `_unclassified`" as the defining
   test — the defining test is always the resolved `task_class` value, never mapping-entry presence.
3. **Resolves to a protected class (`orchestration` or `mode_d`)** — `task_class` set to the protected
   class name, `eligible_for_adjustment` hardcoded `False`, row emission gated by
   `config.CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` (default `true` per PRD §6.3).

`task_class` is a **derived, denormalized column computed at write time via the pinned mapping** —
the raw `skill_name` string is never copied into it (D3/FR-6). Do not conflate policy #2 and #3: the
`_unclassified` gate and the protected-class gate are independent — `_unclassified` bypasses the
config flag entirely.

**Acceptance Criteria**:
- [ ] A fixture containing ≥1 skill name with NO mapping entry, AND ≥1 skill name whose mapping entry EXISTS but explicitly resolves to `_unclassified` (e.g. `codex`, `claude-api`, `ica-delegate`), both always yield `task_class="_unclassified"` rows, independent of `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`'s value (test both `true` and `false`).
- [ ] A fixture containing a skill name mapped to `orchestration` or `mode_d` is present in the result when the flag is `true` and absent when `false`; the same fixture's `_unclassified` rows (if any) are unaffected by the flag in either case.
- [ ] Every protected/`_unclassified` row has `eligible_for_adjustment=False` hardcoded — asserted independent of T3-004's sample-size threshold logic (i.e. still `False` even when `sample_count` is large).
- [ ] No fixture ever observes `task_class` set to the literal raw `source_skill_name` value unless the mapping coincidentally maps a name to an identical string (document this as a non-issue in the test, not treat it as a false negative).

**Implementation Notes**:
- Read `MAPPING_JSON_PATH` and the mapping loader from Phase 1's `routing_feedback_contract.py` —
  this task is a pure consumer of that contract, it does not re-parse or re-vendor the mapping file.
- `_unclassified` and protected-class rows still carry the full pinned join envelope (Phase 1
  constants: `contract_id`, `contract_version`, `taxonomy_id`, etc.) — only `task_class` and
  `eligible_for_adjustment` differ; do not special-case the envelope fields for these rows.

**Files Involved**:
- `backend/application/services/agent_queries/routing_rollup.py` - mapping lookup + emission-gating logic
- `backend/application/services/agent_queries/routing_feedback_contract.py` - read-only; `MAPPING_JSON_PATH` + mapping loader (Phase 1 output)
- `backend/application/services/agent_queries/routing_task_map_v1.json` - read-only; vendored mapping data (Phase 1 output)

---

### Task T3-003: Provider + coverage counters

**Estimate**: 0.5 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T3-002
**started**: null
**completed**: null
**verified_by**: [T6-003]
**evidence**: []

**Description**:
For every row, derive `provider` by calling the existing `backend/model_identity.py::derive_model_identity(raw_model)`
and taking its `"modelProvider"` key — never independently parsed or keyed in `routing_rollup.py`.
Compute the three response-level coverage counters mandated by FR-7, each keyed off the row's
**resolved `task_class` value — never off whether a mapping entry was found** (mapping-entry presence
and `task_class == "_unclassified"` are NOT equivalent; see T3-002's Description for the
executor-identity case, e.g. `codex`/`claude-api`/`ica-delegate`, where an entry EXISTS but resolves
to `_unclassified`): `unclassified_count` (total session-level count of rows whose derived
`task_class == "_unclassified"` — covering BOTH unmapped `source_skill_name`s AND mapped names whose
entry explicitly resolves to `_unclassified`), `mapped_count` (total session-level count of rows whose
derived `task_class != "_unclassified"` — includes protected-class rows), and
`distinct_unmapped_skill_names` (deduplicated, sorted list of the raw `source_skill_name` values whose
resolved `task_class` is `_unclassified`). These are computed once per response — session-level
totals across the whole window, not per-key values (see PRD §6.3's example: `mapped_count: 767`,
`unclassified_count: 13632` — magnitudes far larger than any single key's `sample_count`, confirming
these are aggregate window totals, not per-key figures). `mapped_count + unclassified_count` MUST
equal the total session-level row count exactly — a row is counted in exactly one of the two buckets,
never both and never neither.

**Acceptance Criteria**:
- [ ] `mapped_count` (rows with `task_class != "_unclassified"`) and `unclassified_count` (rows with `task_class == "_unclassified"`) each independently match a hand-computed value against a fixture (session-level totals, not per-key sums).
- [ ] `mapped_count + unclassified_count == total_rows` holds exactly against a fixture that includes `codex`, `claude-api`, and `ica-delegate` as skill names WITH mapping entries that resolve to `task_class == "_unclassified"` (executor-identity names, not "no entry found") — proves the counters never double-count a row that has both a mapping entry AND an `_unclassified` resolution.
- [ ] `distinct_unmapped_skill_names` is deduplicated and returned in a deterministic (e.g. alphabetically sorted) order — required for T3-005's determinism guarantee downstream.
- [ ] `provider` on every key is byte-identical to `derive_model_identity(model)["modelProvider"]` for that model — a unit test asserts this equality directly, never a hardcoded or re-derived value.

**Implementation Notes**:
- This is a mechanical extraction task (existing helper reuse + counter arithmetic) — no new
  algorithmic surface, hence `adaptive` effort versus the `extended` tasks around it.
- Do not add a new provider-derivation code path "for efficiency" — always call through
  `derive_model_identity()`, even if it means one extra function call per row.

**Files Involved**:
- `backend/application/services/agent_queries/routing_rollup.py` - counters + provider derivation
- `backend/model_identity.py` - read-only; `derive_model_identity()`

---

### Task T3-004: D5 metric payload

**Estimate**: 1 point
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: extended
**Dependencies**: T3-003
**started**: null
**completed**: null
**verified_by**: [T6-005]
**evidence**: []

**Description**:
Compute the CCDash-designed D5 metric payload for every key, per the PRD §6.3 JSON example (cite that
example verbatim — do not reinvent field names or types here): `sample_count` (int), `success_rate`
(float 0–1), `cost_index` (float, `1.0` = baseline), `regression_rate` (float 0–1), `confidence`
(float 0–1, a saturating function of `sample_count` — monotonically increasing, asymptotic, never
exceeding 1.0), `eligible_for_adjustment` (bool = `sample_count >= config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`,
default 5 — resolves OQ-3), `window_start` / `window_end` (ISO-8601 strings bounding the rolling
window — resolves OQ-2), and `freshness_ts` (ISO-8601 timestamp of computation). **Never suppress a
sub-threshold key** — every distinct `(source_skill_name, model)` key present in the aggregation
appears in `keys[]`; only `eligible_for_adjustment` flips to `False` for thin keys (AC-5).

Add `RoutingRollupKeyDTO` and `RoutingRollupResponseDTO` to `backend/application/services/agent_queries/models.py`
— the same file `AARReviewDTO` already lives in (`models.py:341-370`) — as plain `BaseModel`
subclasses mirroring `AARReviewDTO`'s exact pattern: explicit field types, `Field(default_factory=...)`
for list defaults, a class docstring stating the DTO's provenance (PRD §6.3). **Not** an
`AgentQueryEnvelope` subclass, matching `AARReviewDTO`'s own documented rationale for opting out of
that base class.

**Acceptance Criteria**:
- [ ] Every key in a multi-key fixture carries the full pinned join envelope (`producer`, `contract_id`, `contract_version`, `taxonomy_id`, `taxonomy_version`, `taxonomy_digest`, `mapping_id`, `mapping_version`, `mapping_digest`, `source_skill_name`, `task_class`) plus every D5 metric field (`model`, `provider`, `sample_count`, `success_rate`, `cost_index`, `regression_rate`, `confidence`, `eligible_for_adjustment`, `window_start`, `window_end`, `freshness_ts`) — verified field-by-field against the PRD §6.3 JSON example.
- [ ] A fixture key with `sample_count=1` (below the default `MIN_SAMPLE_SIZE=5`) still appears in `keys[]` with `eligible_for_adjustment=False` — assert the response's key count equals the fixture's full distinct-key count, never a filtered subset.
- [ ] `RoutingRollupKeyDTO` / `RoutingRollupResponseDTO` are plain `BaseModel` (not `AgentQueryEnvelope` subclasses) — asserted via an `isinstance`/MRO check in the determinism test module (T3-005).

**Implementation Notes**:
- `confidence`'s saturating formula and `cost_index`'s baseline definition are this task's own design
  surface (D5 explicitly leaves the numeric payload unspecified by the cross-repo contract) — pick a
  simple, documented, monotonic formula (e.g. `confidence = min(1.0, sample_count / (sample_count + k))`
  for some fixed `k`) and comment the rationale inline; do not gold-plate this into a tunable model.
- D9 (socializing this metric-payload shape with the router owner) is a plan-level decision gate
  tracked before Phase 5 ships — this task does not need to wait on that socialization to complete its
  own acceptance criteria.

**Files Involved**:
- `backend/application/services/agent_queries/routing_rollup.py` - D5 metric computation
- `backend/application/services/agent_queries/models.py` - `RoutingRollupKeyDTO`, `RoutingRollupResponseDTO`

---

### Task T3-005: Determinism + no-LLM guard

**Estimate**: 0.5 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T3-004
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Two new test files close out this phase's exit criteria.

`backend/tests/test_routing_rollup_determinism.py` builds a fixture DB with a fixed set of session
rows, invokes the compute service twice with no change to the underlying window, and asserts every
field of every returned key row is value-identical across both invocations — assert on a
deterministically **sorted** list (e.g. by `(source_skill_name, model)`), since order-independent set
comparison alone is insufficient to prove determinism.

`backend/tests/test_routing_rollup_no_llm_imports.py` clones
`backend/tests/test_aar_review_no_llm_imports.py`'s AST-walk BFS pattern verbatim (same
`_BANNED_IMPORT_PATTERNS` / `_BANNED_SYMBOL_PATTERNS` lists, same `_module_name_to_path` /
`_walk_dependency_graph` structure), with `_ENTRY_MODULE = "backend.application.services.agent_queries.routing_rollup"`,
asserting zero imports from `backend.adapters.agents` / `services.agents` or any model-client SDK
anywhere in the transitive closure. **Note**: Phase 6 (T6-001) later EXTENDS this same guard file with
a second entry-point walk (mirroring the AAR guard's own `_P6_ENTRY_MODULES` extension) to also cover
Phase 4's `routing_rollup_sweep_job.py` module — write this file so that extension is additive (a
second entry-point tuple + subtest, same `TestCase` class), not a rewrite. Do not mark this guard
"final" in comments or docstrings.

**Acceptance Criteria**:
- [ ] `test_routing_rollup_determinism.py` passes: two invocations over an unchanged fixture window produce field-identical rows in a stable sort order.
- [ ] `test_routing_rollup_no_llm_imports.py` passes with the walk visiting more than 5 modules (non-trivial coverage, mirroring the AAR guard's own sanity assertion at `test_aar_review_no_llm_imports.py:210`).
- [ ] The guard fails loudly (non-empty `offending` list surfaced in the assertion failure message) when a banned import/symbol is deliberately introduced on a scratch branch — verify this manually once during phase review (not a permanent CI fixture).

**Implementation Notes**:
- This task closes both of this phase's `exit_criteria` — do not mark the phase complete until both
  files are green.
- Keep the guard's banned-pattern lists byte-identical to the AAR precedent's lists unless a new
  banned SDK/symbol is discovered — divergence between the two guard files is itself a maintenance
  risk.

**Files Involved**:
- `backend/tests/test_routing_rollup_determinism.py` - new
- `backend/tests/test_routing_rollup_no_llm_imports.py` - new; clones `backend/tests/test_aar_review_no_llm_imports.py`'s structure

---

## Quality Gates

This phase is complete when:

- [ ] **Functional**: `RoutingRollupQueryService` aggregates sessions at `(project_id, source_skill_name, model)` grain over the configured rolling window and returns a well-formed `RoutingRollupResponseDTO` per the PRD §6.3 shape.
- [ ] **Testing**: `test_routing_rollup_determinism.py` and `test_routing_rollup_no_llm_imports.py` both green; all T3-001 through T3-005 acceptance criteria pass.
- [ ] **Performance**: single aggregate SQL statement per invocation (zero N+1), verified by T3-001's query-count fixture test.
- [ ] **Security**: N/A — no new PII surface; `skill_name`/`model` are already exposed via existing session/feature surfaces (PRD §6.2).
- [ ] **Documentation**: `routing_rollup.py`'s module docstring explicitly states the zero-LLM-import invariant, mirroring `aar_review.py`'s docstring convention.
- [ ] **Code Quality**: pure SQL + arithmetic only, no ORM lazy-loading anywhere in the code path (H3 discipline).
- [ ] **Architecture**: transport-neutral per the `agent_queries/` convention — zero `routers/`/`cli/`/`mcp/` imports in `routing_rollup.py`.
- [ ] **Seam verification** (if `integration_owner` set): N/A — `integration_owner: null` this phase; Phase 6 owns the cross-phase seam.
- [ ] **Runtime smoke** (if `ui_touched: true`): N/A — `ui_touched: false`, no frontend surface in this feature.

---

## Integration Points

### External Systems

- **None.** This phase's compute service makes no outbound calls of any kind — no LLM/model-client
  APIs, no other network services. Pure SQL aggregation + in-process arithmetic only (AOS Constraint 4).

### Internal Systems

- **Phase 1 contract module** (`routing_feedback_contract.py` + vendored `routing_task_map_v1.json`):
  T3-002's sole mapping source — read-only dependency; the mapping is frozen before this phase starts.
- **Phase 2 `routing_rollup` table + repository**: this phase's entry criterion; the DTOs frozen here
  (T3-004) define the row shape Phase 4's worker will persist into that table.
- **`backend/model_identity.py::derive_model_identity()`**: T3-003's sole provider source.
- **Phase 4 `RoutingRollupSweepJob`** (not yet built): will import and call this phase's
  `RoutingRollupQueryService` to compute rows for persistence — this phase freezes the read contract
  Phase 4 depends on.
- **Phase 6 no-LLM guard extension**: T6-001 later extends `test_routing_rollup_no_llm_imports.py`
  with a second entry-point walk covering `backend/adapters/jobs/routing_rollup_sweep_job.py`.

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/application/services/agent_queries/routing_rollup.py` | new (~150-250) | `RoutingRollupQueryService`: aggregation, mapping, coverage counters, D5 metric payload | backend-architect |
| `backend/application/services/agent_queries/models.py` | +~60-80 (appended near `AARReviewDTO`) | `RoutingRollupKeyDTO`, `RoutingRollupResponseDTO` | backend-architect |
| `backend/tests/test_routing_rollup_determinism.py` | new (~80-120) | Determinism fixture test | python-backend-engineer |
| `backend/tests/test_routing_rollup_no_llm_imports.py` | new (~120-180, cloned from AAR precedent) | AST-walk no-LLM/no-agent-dispatch import-graph guard | python-backend-engineer |

---

## Testing Strategy

### Unit Tests

- Mapping lookup edge cases: resolves-to-normal (mapped), resolves-to-`_unclassified` (covers BOTH no-entry-found AND an existing entry that explicitly resolves to `_unclassified`, e.g. `codex`/`claude-api`/`ica-delegate`), resolves-to-protected (`orchestration`, `mode_d`) — each policy branch independently.
- Provider derivation delegation: `provider` always equals `derive_model_identity(model)["modelProvider"]`, never independently derived.
- Coverage counter arithmetic: `mapped_count` / `unclassified_count` / `distinct_unmapped_skill_names` against a hand-computed fixture total.
- D5 metric field computation: `confidence` saturation curve monotonicity, `eligible_for_adjustment` threshold boundary (`sample_count == CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE - 1` vs `== MIN_SAMPLE_SIZE`).

### Integration Tests

- Fixture DB (in-memory or temp-file `aiosqlite`) seeded with representative session rows spanning
  multiple projects, `skill_name`s, and models; assert the full `RoutingRollupResponseDTO` shape
  matches the PRD §6.3 example field-for-field.
- Query-count instrumentation asserting the aggregation call issues exactly one SQL statement,
  independent of the number of distinct fixture keys.
- Two-invocation determinism check over an unchanged fixture window (T3-005).

### E2E Tests (if applicable)

- N/A — no frontend surface; transport wiring (REST/MCP/CLI) does not exist until Phase 5.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Silent mis-join from a mapping-lookup bug or typo | High | Mapping is applied via exact dict lookup against the pinned Phase-1 JSON, never fuzzy-matched; T3-002's unit tests pin known mapped/unmapped/protected fixture rows; Phase 6's T6-002 CI parity test digest-verifies the vendored mapping file itself did not drift. |
| Accidental N+1 query pattern | Medium | Single `GROUP BY` aggregate query (T3-001); fixture test asserts query count == 1 regardless of fixture size. |
| Accidental LLM/model-client import creeping into the transitive closure | Medium | T3-005's AST-walk guard fails CI on any banned import/symbol; module docstring states the zero-import invariant explicitly, matching the AAR precedent's own guard shape. |
| Protected-class or `_unclassified` row leaking into an "eligible" routing signal | Medium | `eligible_for_adjustment` hardcoded `False` for these rows at the DTO-population level, never config-overridable; T3-002/T3-004 unit tests assert this independent of the `sample_count` threshold logic. |
| D5 metric-payload formula (`cost_index`/`confidence`) diverges from router-owner expectations | Medium | D5 is CCDash's own design surface per the PRD (the cross-repo contract leaves it unspecified); D9 socialization is tracked as a plan-level decision gate before Phase 5 ships, not a blocker for this phase's own acceptance criteria. |

---

## Success Metrics

- **Completion**: all five tasks (T3-001 through T3-005) checked off.
- **Quality**: both new test files (`test_routing_rollup_determinism.py`, `test_routing_rollup_no_llm_imports.py`) green.
- **Determinism**: 100% — two sweeps over an unchanged fixture window produce field-identical rows (mirrors the plan-level `success_metrics`).
- **Mapping fidelity**: every fixture row's `task_class` traces to the exact pinned mapping entry, or falls through to the documented `_unclassified`/protected-class policy — zero raw `skill_name` leakage into `task_class`.
- **Coverage visibility**: `mapped_count` / `unclassified_count` / `distinct_unmapped_skill_names` present and correct on every fixture response, satisfying AC-5 and AC-6.

---

## Notes

### Implementation Approach

Build strictly bottom-up in task order: T3-001 freezes the raw aggregated-row shape, T3-002 layers
mapping/policy on top of it, T3-003 layers provider derivation + coverage counters, T3-004 layers the
D5 numeric payload and adds the DTOs, and T3-005 locks the whole module down with the determinism and
no-LLM guards. Do not parallelize T3-002 through T3-004 — each strictly extends the in-memory row
shape the prior task produced.

### Gotchas

- **Row-grain discipline**: never collapse `(source_skill_name, model)` rows sharing a `task_class`
  into one key — that merge is the router's job, explicitly out of scope here (PRD §6.3, FR-5). A
  `task_class`-grouped view may be offered as a read-only operator convenience, but it is never the
  authoritative `keys[]` row.
- **Two independent gates, do not conflate**: `_unclassified` bypasses
  `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` entirely (always emitted per FR-7); only the
  `orchestration`/`mode_d` protected classes are gated by that flag.
- **`provider` sourcing**: always via `derive_model_identity(model)["modelProvider"]` — never
  parse/derive it independently in this module, even as a "quick" fallback for an edge-case model
  string.
- **This is the H3 anchor phase**: the only genuinely algorithmic phase in the whole feature. Budget
  the plan-level `karen` milestone review at this phase's completion in addition to the mandatory
  `task-completion-validator` pass — do not treat it as a routine mechanical-clone phase like 1, 2, 4,
  5, or 6.

### Learnings

*Populate during execution.*

### Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
