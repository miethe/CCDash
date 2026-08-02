---
title: "Feature Contract: Routing Feedback Cost Index (DI-4a)"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "Derive a real per-key cost_index in the routing-feedback envelope, replacing the fixed 1.0 baseline."
status: completed
created: 2026-08-01
updated: 2026-08-02
feature_slug: routing-feedback-cost-index
category: infrastructure
estimated_points: 5
tier: 1
owner: null
priority: high
risk_level: low
changelog_required: true
node_type: work_package
acceptance_criteria: []
definition_of_done: null
execution_mode: unassigned
agent_title: null
agent_summary: null
agent_context: null
open_questions: []
decisions: []
scores: {}
related_documents:
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
spike_ref: null
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: null
commit_refs: ["5d5da18"]
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/routing_rollup.py
  - backend/application/services/agent_queries/models.py
  - backend/routers/_client_v1_routing_rollup.py
  - backend/tests/test_routing_rollup_metrics.py
  - backend/tests/test_client_v1_routing_rollup.py
  - docs/guides/routing-feedback-loop.md
---

# Feature Contract: Routing Feedback Cost Index (DI-4a)

## 1. Goal

Replace the fixed `_COST_INDEX_BASELINE = 1.0` in
`backend/application/services/agent_queries/routing_rollup.py` with a real per-`(source_skill_name
× model)` cost index derived from session cost, so the routing-feedback envelope carries at least
one live, non-constant outcome signal instead of an inert placeholder.

---

## 2. User / Actor

- **Primary user**: The delegation-router (MeatySkills/`ibm-main`), consuming CCDash's
  `/api/v1/routing/rollup` envelope to compute routing-adjustment decisions (DI-1, currently
  deferred behind `live_consumption_disabled`).
- **Secondary users**: CCDash operators verifying routing-feedback envelope health via
  `ccdash_routing_rollup` (MCP) / `ccdash routing rollup` (CLI) / REST.

---

## 3. Job To Be Done

When **a router key's sessions carry real per-session cost data**, the routing-feedback producer
wants to **emit a `cost_index` that reflects that key's actual relative cost**, so it can **make
the router merge's `penalty_for_cost` term (routing-feedback-router-merge-handoff.md §2.2) a live
signal instead of a permanently-zero one** (per §0 of that spec: at the fixed `1.0` baseline,
`penalty_for_cost = max(1.0 - 1.0, 0.0) = 0.0` for every row, unconditionally).

---

## 4. Scope

### In Scope

- A per-`(source_skill_name × model)` cost aggregation, computed from `sessions.total_cost` /
  `display_cost_usd`, at the same grain the rollup already groups on (no new join, no new table).
- A baseline computation for cost normalization (see D-a1) and the resulting `cost_index =
  key_mean_cost / baseline`, or `null` where the baseline itself cannot be established.
- Explicit `null` emission for a key whose sessions carry no cost attribution at all (see D-a2).
- Coverage-fraction handling for a key that is only partially covered (see D-a3).
- Outlier-awareness for the interaction between a single expensive session and a low-sample key
  (see D-a4), documented as a decision even if the shipped answer is "rely on the existing
  `min_sample_size` gate, no separate outlier logic."
- Unit coverage for the new cost-index computation, and updates to the existing digest-parity /
  envelope-completeness tests so they assert the new non-constant behavior instead of the old
  fixed `1.0`.

### Out of Scope

- `success_rate` / `regression_rate` (DI-4b) — tracked separately as a SPIKE (see the sibling
  exploration charter, `docs/project_plans/exploration/routing-feedback-success-signal/`). This
  contract touches `cost_index` only.
- Any router-side merge-algorithm change (DI-1) — owned by MeatySkills/`ibm-main`, deferred.
- Flipping `CCDASH_ROUTING_FEEDBACK_ENABLED` or `live_consumption_disabled` — both remain exactly
  as configured today; this contract only changes what value ships inside the envelope when the
  producer runs.
- Any new DDL, migration, or schema-version bump. The `routing_rollup.cost_index` column already
  exists and is nullable (Phase 2 DDL, `backend/db/sqlite_migrations.py` /
  `backend/db/postgres_migrations.py`, both declare `cost_index REAL` with no `NOT NULL`).
- Backfilling or re-deriving cost for the 28% of sessions with no cost attribution — that is a
  separate, unscoped data-quality problem, not this contract's concern.

---

## 5. UX / Behavior Requirements

This is a backend-only, data-shape change with no direct UI surface. Behavior is specified purely
by the emitted envelope field:

- A key where all covered sessions carry cost data emits a real `cost_index` float.
- A key with zero cost-attributed sessions emits `cost_index: null` — never a fabricated `1.0` or
  any other placeholder.
- A key with partial cost coverage still emits a `cost_index` computed over the covered subset,
  plus a coverage-fraction indicator so the router can discount low-coverage keys appropriately
  (see D-a3 — the exact field name/shape is this contract's design decision, not pre-specified).
- The change is silent from the perspective of any consumer that does not yet read `cost_index` —
  no other envelope field changes shape or semantics.
- `eligible_for_adjustment`, `sample_count`, `confidence`, and the coverage-only/protected-class
  handling in `compute_metrics` are unaffected; this contract only changes the `cost_index=
  _COST_INDEX_BASELINE` line and its supporting computation.

---

## 6. Data Requirements

- **Entities affected**: `routing_rollup` DTO assembly path
  (`RoutingRollupQueryService.compute_metrics` in
  `backend/application/services/agent_queries/routing_rollup.py`). No new entities.
- **New fields**: None required in the persisted `routing_rollup` table (`cost_index` already
  exists, nullable). If D-a3's coverage-fraction signal needs a home, prefer an existing envelope
  field or a computed-not-persisted value over a new column; justify in the Completion Report if a
  new field is unavoidable.
- **State changes**: None — this is a read-time computation change, not a write-path change.
- **Storage implications**: None. Explicitly no new table, no new column, no schema-version bump
  (per the ground truth in the handoff spec §5.4: "the `routing_rollup.cost_index` column already
  exists and is nullable").

---

## 7. API / Integration Requirements

**Modified behavior on an existing endpoint (no new routes):**
- `GET /api/v1/routing/rollup?project_id={project_id}` — `RoutingRollupKeyDTO.cost_index` changes
  from an always-`1.0` constant to a computed value or `null`.
- MCP tool `ccdash_routing_rollup` and CLI `ccdash routing rollup` — same DTO, same change, no
  transport-level changes needed since both already pass the DTO through verbatim.

**External service calls**: None.

**Internal service dependencies:**
- `backend/application/services/agent_queries/routing_rollup.py` — the sole file whose
  `compute_metrics` (and any helper it calls) implements this change.
- Session cost fields already read elsewhere in the codebase (`sessions.total_cost` /
  `display_cost_usd`) are the only new data this service needs to read; no new repository method
  should be required if the rollup's existing `ProviderRollupRow` construction can be extended to
  carry per-row cost aggregates from the same session query that already produces `session_count`.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/application/services/agent_queries/routing_rollup.py` — the existing pipeline shape
  (`fetch_raw_rows` → `ProviderRollupRow` → mapping/coverage → `compute_metrics` → DTO). Add the
  cost aggregation into this pipeline; do not introduce a parallel query path.
- The module's existing null-over-fabrication principle, already codified in the `success_rate`/
  `regression_rate` code comments: *"fabricating one from a non-signal would be actively
  misleading to a consuming router."* This contract's `cost_index` must honor the same principle
  for zero-coverage keys (D-a2).
- No LLM/model call on this compute path — `routing_rollup.py` is a deterministic, CI-grep-guarded
  module (see Acceptance Criteria).

**Must not change** (protected areas):
- `RoutingRollupResponseDTO`'s top-level envelope fields (contract/taxonomy/mapping identity,
  coverage counters) — additive-only per D5 versioning (handoff spec §5.4: "additive per D5").
- `eligible_for_adjustment`, `sample_count`, `confidence`, `success_rate`, `regression_rate`
  semantics — untouched by this contract.
- The pinned mapping (`routing_task_map_v1.json`) and its digest-lock CI guard (AC-2 in the
  handoff spec) — this contract does not touch skill→task_class mapping.
- `_COST_INDEX_BASELINE` as a *name* may be removed/repurposed, but the module's existing
  min-sample gating (`CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`, default 5,
  `eligible_for_adjustment = sample_count >= min_sample_size`) must not be altered by this
  contract — cost-index coverage is a separate concern from adjustment eligibility (see D-a4).

**New dependencies:**
- No new dependencies expected.

---

## 9. Acceptance Criteria

- [ ] **Determinism**: two invocations of `compute_metrics` (or its cost-index helper) over a
  frozen fixture DB/row-set produce field-identical `cost_index` values — no wall-clock,
  randomness, or non-deterministic ordering in the computation.
- [ ] **No LLM on the compute path**: the existing CI grep-guard that keeps `routing_rollup.py`
  free of model calls stays green with this change applied.
- [ ] **Zero-coverage key emits `null`**: a key whose sessions carry no cost attribution asserts
  `cost_index is None` directly in a test — never `1.0`, never `0.0`, never any other placeholder.
- [ ] **Partial-coverage key emits a computed index over the covered subset**, and the coverage
  fraction (or equivalent discount signal per D-a3) is asserted in a test to differ from a
  fully-covered key with the same nominal cost.
- [ ] **Full-coverage key emits a real, non-constant `cost_index`** that changes when the
  underlying per-session cost inputs change (i.e., the value is provably derived, not a disguised
  constant).
- [ ] **Baseline choice (D-a1) is implemented and testable**: a test constructs two keys in
  different `task_class` buckets with different absolute costs but the same relative
  standing within their own bucket, and asserts the per-task-class baseline (or whichever
  baseline is chosen — see D-a1) produces the expected relative `cost_index`, not a
  cross-task_class-skewed one.
- [ ] **Outlier handling (D-a4) is a documented, tested decision** — whatever the answer, a test
  demonstrates the chosen behavior for a low-sample key with one dominant high-cost session.
- [ ] **Existing digest-parity test stays green** (updated only where it asserted the old fixed
  `1.0`, never weakened).
- [ ] **Existing envelope-completeness test stays green**, updated to tolerate `cost_index` being
  either a float or `null` rather than asserting the old constant.
- [ ] **Envelope stays additive/forward-compatible**: a consumer that already tolerates `null`
  `cost_index` values is unaffected by this change; no other DTO field's shape or semantics
  changes.

---

## 10. Validation Requirements

- [ ] **Typecheck**: N/A for this module (Python, not typed via `tsc`) — mypy/pyright equivalent
  passes if the project runs one over `backend/`.
- [ ] **Lint** passes (flake8/ruff, per repo convention).
- [ ] **Tests** added or updated for meaningful behavior (see Acceptance Criteria above).
- [ ] **Relevant tests pass**: `backend/.venv/bin/python -m pytest backend/tests/ -k
  "routing_rollup"` (or whatever the actual routing-rollup test module name is — verify at
  implementation time; do not assume a name not yet confirmed in this contract).
- [ ] **Build/import** passes — the module continues to import cleanly with no syntax or dependency
  errors.
- [ ] **Docs updated**: note the `cost_index` behavior change in
  `docs/guides/routing-feedback-loop.md` if that guide already documents the `1.0` placeholder
  (verify at implementation time whether such a guide exists and references the constant).
- [ ] **No unrelated changes** introduced — this contract touches `routing_rollup.py`, its cost
  helper(s), and its tests only. No changes to the merge algorithm, the mapping file, or DI-4b.

**Cost-term interaction to preserve** (do not re-derive, cite): the ratified merge algorithm's cost
term (handoff spec §2.2, corrected 2026-08-01) is `penalty_for_cost = max(cost_index - 1.0, 0.0)`.
A `cost_index` **below** 1.0 is inert by design — cheapness earns no bonus, only above-baseline
cost can downweight a route. This contract's baseline/normalization choice (D-a1) must produce
`cost_index` values on that same `1.0`-centered scale (a key at its baseline reads `~1.0`; a key
twice as expensive as baseline reads `~2.0`), or the merge's clamp semantics silently break for
every router that eventually consumes this field.

---

## 11. Risk Areas

- **Baseline choice changes what "expensive" means (D-a1)**: picking the wrong grain (e.g., a
  single global mean across all task classes) makes an inherently expensive orchestration key look
  permanently "over baseline" relative to a cheap mechanical key, even when both are performing
  exactly as expected for their class. This is the single highest-risk decision in this contract —
  get the recommendation reviewed before implementing.
- **Coverage-fraction semantics (D-a3) could be over-engineered**: the requirement is that the
  router can discount a low-coverage key, not that CCDash pre-computes the router's discount logic.
  Keep the emitted signal simple (a fraction or count) and leave the discounting math to the
  consumer, consistent with CCDash's "evidence-only producer" scope (handoff spec §"Deferral
  Rationale": "CCDash's Scope (Shipped): Evidence-only producer surface").
- **Outlier handling (D-a4) risks scope creep into statistical modeling**: this contract is not
  the place to build a robust-statistics library. The lowest-risk answer is likely "rely on the
  existing `min_sample_size` gate to exclude low-sample keys from `eligible_for_adjustment`, and do
  no additional outlier suppression in `cost_index` itself" — but that must be stated as a
  deliberate decision, not an oversight.
- **Test-suite entanglement**: the digest-parity and envelope-completeness tests may currently hard
  -assert the literal `1.0` in multiple places. Search broadly before editing so no assertion is
  missed and silently left green against the wrong expectation.

---

## 12. Implementation Notes

**Suggested approach** (agent may improve):
- Start by reading `RoutingRollupQueryService.compute_metrics` and its upstream `ProviderRollupRow`
  construction in `backend/application/services/agent_queries/routing_rollup.py` in full, to
  confirm exactly where per-session cost data would need to enter the pipeline (likely alongside
  the existing `session_count` aggregation, since both are per-`(source_skill_name × model)`
  aggregates over the same session set).
- Implement the D-a1 baseline (recommended: per-`task_class` mean cost-per-session) as a
  same-pass aggregate over the rows already being processed — no second DB round-trip should be
  necessary since the rollup already has the full row set in memory when `compute_metrics` runs.
- Resolve D-a2 (`null` on zero coverage) and D-a3 (partial-coverage discount signal) together,
  since both stem from the same "not every session has cost data" reality.
- Resolve D-a4 last, once the baseline and null/partial logic are settled and tested — it is a
  refinement on top of a working index, not a prerequisite for one.

**Similar existing code**:
- Reference: the existing `_confidence_for_sample_count` helper and its
  `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`-gated `eligible_for_adjustment` computation in the same
  file — both are examples of the module's existing pattern for turning a raw per-key count into a
  bounded, documented derived signal. Follow the same level of docstring rigor for the new
  cost-index helper.
- Reason: consistency of documentation density and null-handling philosophy across the module.

**Known gotchas**:
- `sessions.total_cost` / `display_cost_usd` — the handoff spec's audit (§0) cites both names as
  the cost-population evidence (72% populated); confirm at implementation time which column(s) the
  rollup's existing session query already selects, and whether both need to be considered or one
  supersedes the other in this codebase's current schema.
- Do not touch `_COST_INDEX_BASELINE`'s call sites in a way that reintroduces a fixed constant
  under a new name — the entire point of this contract is that the value becomes real per-key data.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason.
- **Tests run**: What tests were added/updated and results.
- **Validation results**: Table of all validation commands and their results (pass/fail/not
  applicable).
- **Deviations from contract**: Any material changes to the contract during implementation and
  why — especially if D-a1/D-a2/D-a3/D-a4 were resolved differently than this contract's
  recommendation.
- **Risks / Limitations**: Any remaining risks or known limitations.
- **Follow-up recommendations**: Suggested next steps or follow-on work (e.g., whether DI-4b now
  has a cleaner path given this contract's baseline-computation code).

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report
template.

---

## Metadata & References

**Tier**: 1 (5 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase
orchestration.

**Reviewer**: `task-completion-validator` (mandatory).

**Related Documents**:
- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` — §0 (signal-source
  audit, ground truth for this contract) and §5.4 (DI-4 scoping, this contract is DI-4a).
- `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` — parent PRD.
- `backend/application/services/agent_queries/routing_rollup.py` — the file this contract modifies.

---

## Design Decisions (Named, Not Silently Picked)

### D-a1 — Baseline choice for cost normalization

**Options**: (a) global mean cost-per-session across all keys, (b) per-`task_class` mean, (c)
cheapest-key-as-baseline.

**Recommendation**: **(b) per-`task_class` mean.** Comparing a mechanical key's cost against an
orchestration key's cost — or vice versa — is meaningless: the two task classes have
structurally different expected cost profiles (an orchestrating model doing multi-step reasoning
is *supposed* to cost more than a mechanical extraction call), so a global mean would flag every
orchestration key as "expensive" regardless of whether it is well-routed within its own class.
Per-task_class mean keeps the comparison apples-to-apples: a key is only flagged as
above-baseline-expensive relative to peers doing the *same kind* of work.

**Status**: recommended, not yet ratified — implementer should confirm and document if a different
choice is made.

### D-a2 — Zero-coverage keys emit `null`, never a fabricated `1.0`

**Decision**: a key with zero cost-attributed sessions emits `cost_index: null`. This is not
optional or up for re-litigation — it mirrors why v1 emitted `null` for `success_rate`/
`regression_rate` in the first place. Per the module's own existing rationale (quoted verbatim from
`routing_rollup.py`): fabricating a value from a non-signal **"would be actively misleading to a
consuming router."** A fabricated `1.0` (or any other placeholder) for a zero-coverage key is
exactly the failure mode v1 already refused to commit for the other two fields; DI-4a must not
reintroduce it for `cost_index`.

**Status**: ratified — this is a hard constraint, not a recommendation.

### D-a3 — Partial coverage: emit the index over the covered subset, surface the coverage fraction

**Decision**: for a key where only some sessions carry cost data, compute `cost_index` over the
covered subset only (not diluted by treating uncovered sessions as zero-cost), and additionally
surface a coverage-fraction (or covered/total count pair) so the router can discount a low-coverage
key's `cost_index` appropriately. The exact field name/shape for the coverage signal is an
implementation detail left to the executing agent, but it must exist and be tested — a router
consuming a `cost_index` computed from 2 of 50 sessions needs a way to know that, or it will treat
a noisy estimate with the same confidence as a fully-covered one.

**Status**: recommended shape, implementer chooses the concrete field.

### D-a4 — Outlier handling: should one expensive session dominate a low-sample key's index?

**Question**: a key with few sessions where one session is anomalously expensive could produce a
`cost_index` that overstates the key's typical cost. This interacts with the existing
`min_sample_size` gate (`CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`, default 5): should
`eligible_for_adjustment`'s existing sample-count threshold be considered sufficient protection
against this (i.e., a key with too few sessions to be adjustment-eligible also shouldn't need
special-cased outlier suppression in its cost math, since the router won't act on it anyway), or
does `cost_index` need its own robustness logic independent of adjustment eligibility?

**Recommendation**: rely on the existing `min_sample_size` gate; do not add separate outlier
suppression (e.g., trimmed means, winsorization) to the cost-index computation itself. Adding
statistical robustness machinery here would be scope creep relative to a 5-point contract and
duplicates a gate that already exists for exactly this "too little data to trust" concern. If the
executing agent disagrees, this must be recorded as a deviation in the Completion Report with
rationale, not implemented silently.

**Status**: recommended, not yet ratified.
