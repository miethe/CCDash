---
title: "Feature Contract: Populate routing_rollup.success_rate (DI-4e)"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "Replace the always-null success_rate in the routing_rollup producer with the per-key tool-error-rate complement, plus a new skill-dimension coverage axis."
status: blocked
created: 2026-08-10
updated: 2026-08-10
feature_slug: di-4e-routing-success-rate
category: enhancements
estimated_points: 7
tier: 1
owner: null
priority: high
risk_level: medium
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
  - docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-feasibility-brief.md
  - docs/project_plans/exploration/routing-feedback-success-signal/spikes/tool-failures/di-4d-remeasurement.md
  - docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md
spike_ref: null
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/routing_rollup.py
  - backend/application/services/agent_queries/models.py
  - backend/tests/test_routing_rollup_metrics.py
  - backend/tests/test_routing_rollup_envelope_completeness.py
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
  - docs/guides/routing-feedback-loop.md
---

# Feature Contract: Populate `routing_rollup.success_rate` (DI-4e)

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 7,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 6,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [
    "Design surface, DI-4d remeasurement, and DI-4f feasibility brief already resolved every open research question; the only remaining unknown (whether the LIVE 30-day window is still skewed by stale pre-b51de27 session_tool_usage rows) is handled as an in-sprint go/no-go verification gate (D-b4/AC2), not a standalone SPIKE."
  ],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md",
  "execution_target": "execute-contract",
  "slug": "di-4e-routing-success-rate",
  "category": "enhancements",
  "review_intensity": "standard",
  "files_affected": [
    "backend/application/services/agent_queries/routing_rollup.py",
    "backend/application/services/agent_queries/models.py",
    "backend/tests/test_routing_rollup_metrics.py",
    "backend/tests/test_routing_rollup_envelope_completeness.py",
    "docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md",
    "docs/guides/routing-feedback-loop.md"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Populate routing_rollup.success_rate (DI-4e feature contract)",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint. Read docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md in full and execute it end to end -- it is the complete contract. Sequence: (1) FIRST run the D-b4 live verification query (adapt docs/project_plans/exploration/routing-feedback-success-signal/spikes/tool-failures/di-4d-remeasurement.md section 1's SQL to the current window) against the live DB and record pass/HALT before writing any code -- AC2 is a hard gate, HALT and report if the family split is still skewed. (2) Extend backend/application/services/agent_queries/routing_rollup.py's _fetch_raw_aggregate_rows with a join/aggregate against session_tool_usage (call_count, success_count), threading new fields through RawRollupRow -> MappedRollupRow -> ProviderRollupRow exactly as cost_sum/cost_covered_count were threaded. (3) Add a _success_rate_and_coverage helper (call-volume-weighted per D-b1, null-on-zero-attribution per D-b2) and wire into compute_metrics. (4) Add skill-dimension coverage counters (D-b3) to RoutingRollupResponseDTO in backend/application/services/agent_queries/models.py and thread through build_response. (5) Add the regression_rate=None code comment citing the DI-4b closure (AC4). (6) Confirm CCDASH_ROUTING_FEEDBACK_ENABLED/live_consumption_disabled are untouched (AC5). (7) Add/update tests in backend/tests/test_routing_rollup_metrics.py and backend/tests/test_routing_rollup_envelope_completeness.py per the contract's Acceptance Criteria and Additional engineering ACs, including the D-b1 call-volume-weighted synthetic case. (8) Update docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md and docs/guides/routing-feedback-loop.md per AC3 (skill-dimension coverage as an explicit contract state, citing the feasibility brief). Run backend/.venv/bin/python -m pytest backend/tests/ -k routing_rollup and lint. Produce the Completion Report required by section 13, including the D-b4 verification result and any deviation from D-b1..D-b5. Do NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 7,
                "files_affected": [
                  "backend/application/services/agent_queries/routing_rollup.py",
                  "backend/application/services/agent_queries/models.py",
                  "backend/tests/test_routing_rollup_metrics.py",
                  "backend/tests/test_routing_rollup_envelope_completeness.py",
                  "docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md",
                  "docs/guides/routing-feedback-loop.md"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If the D-b4 live-verification gate HALTs (window still skewed by stale pre-b51de27 Codex session_tool_usage rows), do not force the sprint -- promote to a short Tier 1 follow-up scoped around a Codex session_tool_usage backfill/resync precondition, then re-run this same contract once the window is clean."
}
```

## 1. Goal

Replace the hardcoded `success_rate=None` in
`RoutingRollupQueryService.compute_metrics` (`backend/application/services/agent_queries/routing_rollup.py`)
with a real per-`(project_id, source_skill_name, model)` success rate derived from the
per-key tool-error rate's complement, aggregated from `session_tool_usage` over the same
30-day rolling window the rollup already scans. Both prior gates are cleared: DI-4d
(Codex tool-error detection fixed — main `b51de27`) and DI-4f (skill-attribution NO-GO,
closed).

---

## 2. User / Actor

- **Primary user**: The delegation-router (MeatySkills/`ibm-main`), consuming
  `/api/v1/routing/rollup` — currently deferred behind `live_consumption_disabled` (DI-1,
  out of scope here).
- **Secondary users**: CCDash operators verifying envelope health via
  `ccdash_routing_rollup` (MCP) / `ccdash routing rollup` (CLI) / REST, and the
  MeatySkills/`ibm-main` team reading the consumer-facing handoff spec to decide whether a
  key is skill-aware or `(project × model)` wearing a three-part key's clothes.

---

## 3. Job To Be Done

When **a routing key's sessions carry genuine tool-usage attribution**, the producer wants
to **emit a `success_rate` reflecting that key's actual tool-error-rate complement** — with
an explicit `null` for keys with no tool-usage attribution — so the router merge's
success term becomes a live signal instead of a permanently-absent one, without ever
implying a skill-aware key where the key is really `(project × model)`.

---

## 4. Scope

### In Scope

- A per-`(project_id, source_skill_name, model)` tool-call/tool-error aggregation, joined
  from `session_tool_usage` at the same grain the rollup already groups on (mirrors the
  existing cost-aggregation join pattern in `_fetch_raw_aggregate_rows`; DI-4a precedent).
- `success_rate = 1 - (sum(tool_errors) / sum(tool_calls))` computed over the **covered**
  subset only (keys/sessions with `session_tool_usage` rows) — call-volume-weighted (sum of
  errors over sum of calls across the key's sessions), never a mean-of-per-session-rates
  (see D-b1).
- Explicit `null` for a key with zero tool-usage-attributed sessions — never a fabricated
  constant (D-b2, same null-over-fabrication posture as `cost_index`/DI-4a).
- **New skill-dimension coverage counters** distinguishing a genuinely skill-aware key
  (non-empty `source_skill_name`) from a `(project × model)` key wearing a three-part key's
  clothes (D-b3) — response-level, additive to `RoutingRollupResponseDTO`.
- A **live pre-implementation verification step** (D-b4): before writing the aggregation
  code, query the current 30-day window's Claude-vs-Codex family split to confirm it is
  measurably non-skewed post-`b51de27` (per DI-4d's re-measurement method,
  `di-4d-remeasurement.md` §1–2). If the live data is still skewed (stale
  pre-`b51de27` `session_tool_usage` rows dominating the window), HALT and record the
  finding — do not ship a producer signal known to be built on stale counts.
- Explicit decision on retry/recovery (D-b5): document that raw error-rate cannot
  distinguish "failed then recovered" from "failed and stayed broken" (95.2% of
  tool-failure sessions still reach `completed`), and that this contract does **not**
  attempt retry-aware modeling — a documented limitation, not a silent gap.
- A code comment on `regression_rate=None` citing the DI-4b closure (no `test_results`/
  `test_runs` signal exists) — no behavior change to `regression_rate`.
- Unit coverage: zero-attribution → `null`; partial coverage → computed-over-covered-subset
  + coverage fraction; full coverage → real, non-constant value; skill-dimension counters;
  determinism.
- Consumer-facing documentation update (`routing-feedback-router-merge-handoff.md` and/or
  `routing-feedback-loop.md`) naming the ~40–45% skill-dimension coverage as an explicit
  contract state (AC3), citing the feasibility brief.

### Out of Scope

- Any change to `CCDASH_ROUTING_FEEDBACK_ENABLED` or `live_consumption_disabled` — DI-1,
  router-owner's call, untouched.
- `regression_rate` computation — stays `null`; CLOSED per DI-4b (no `test_results`/
  `test_runs` signal), not deferred, not revisited here.
- Backfilling/re-parsing historical Codex `session_tool_usage` rows written by the
  pre-`b51de27` parser. Per `di-4d-remeasurement.md` §7, a backfill is "a prerequisite, not
  an optimisation" for *reading a correct historical Codex success_rate*, but this contract
  reads the live window as-is; if D-b4's verification shows the live window is still
  materially stale, that becomes a named blocker for this contract, not a backfill task
  this contract absorbs.
- Any new column, migration, or schema-version bump. `routing_rollup.success_rate REAL`
  already exists nullable in both DDLs (`sqlite_migrations.py:1580`,
  `postgres_migrations.py:1593`) — this is a read-time compute-layer change only, per the
  design surface's explicit HALT-as-Mode-D instruction if a new column is ever required.
- Any skill-attribution fix (Claude Code subagent→parent inheritance) — DI-4f closed that
  as a separate, decoupled, un-scoped Tier 1 follow-up on its own merits.
- Router-side merge-algorithm changes (DI-1).

---

## 5. UX / Behavior Requirements

Backend-only, no UI surface. Behavior is specified by the emitted envelope:

- A key where all sessions carry tool-usage attribution emits a real `success_rate` float
  in `[0.0, 1.0]`.
- A key with zero tool-usage-attributed sessions emits `success_rate: null`.
- A key with partial tool-usage coverage emits `success_rate` computed over the covered
  subset, plus a coverage signal (mirrors `cost_coverage_fraction`'s shape/naming
  convention — exact field name is this contract's implementation decision).
- The response envelope gains skill-dimension coverage counters so a consumer can
  determine, without reading CCDash source, what fraction of emitted keys are genuinely
  skill-aware vs `(project × model)`-only (AC3). Exact field names are an implementation
  decision but must be response-level (mirrors the existing `mapped_count`/
  `unclassified_count` FR-7 pattern), not per-row-only.
- `eligible_for_adjustment`, `sample_count`, `confidence`, `cost_index`,
  `cost_coverage_fraction`, `regression_rate` are unaffected.
- Additive-only per D5 versioning: any consumer already tolerating `null` `success_rate` is
  unaffected.

---

## 6. Data Requirements

- **Entities affected**: `RoutingRollupQueryService` compute pipeline
  (`fetch_raw_rows` → `apply_mapping` → `apply_provider` → `compute_metrics` →
  `build_response`). No new persisted entities.
- **New fields**: None in the persisted `routing_rollup` table (`success_rate` already
  exists, nullable). New skill-dimension coverage counters live on the
  compute-layer/response DTO only (`RoutingRollupResponseDTO`), same treatment as
  `mapped_count`/`unclassified_count` — computed, not persisted, unless the implementer can
  show a strong reason otherwise (justify in the Completion Report).
- **New read**: a join/subquery against `session_tool_usage` (`call_count`,
  `success_count`) aggregated per `(project_id, source_skill_name, model)` — same pattern
  as the existing `cost_sum`/`cost_covered_count`/effort aggregates already added to
  `_fetch_raw_aggregate_rows`, except `session_tool_usage` is a separate table requiring an
  actual join (unlike the cost/effort columns, which live directly on `sessions`).
- **Storage implications**: None. No schema/DDL change. If implementation genuinely
  requires a new column, HALT as Mode D per the task's design surface — do not proceed.

---

## 7. API / Integration Requirements

**Modified behavior on an existing endpoint (no new routes):**
- `GET /api/v1/routing/rollup?project_id={project_id}` — `RoutingRollupKeyDTO.success_rate`
  changes from always-`None` to a computed value or `null`; `RoutingRollupResponseDTO`
  gains additive skill-dimension coverage fields.
- MCP tool `ccdash_routing_rollup` and CLI `ccdash routing rollup` — same DTO, same change,
  no transport-level code changes expected.

**Internal service dependencies:**
- `backend/application/services/agent_queries/routing_rollup.py` — sole file implementing
  the aggregation + metric.
- `session_tool_usage` (`call_count`, `success_count`, already has `project_id` per prior
  migrations) — read-only join, no new repository method required if the existing
  aggregate SQL in `_fetch_raw_aggregate_rows` can be extended with a `LEFT JOIN` /
  correlated aggregate, mirroring how effort-tier aggregates were added there.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/application/services/agent_queries/routing_rollup.py`'s existing pipeline shape
  — extend `RawRollupRow` → `MappedRollupRow` → `ProviderRollupRow` with tool-call/error
  aggregate fields, exactly as `cost_sum`/`cost_covered_count`/`effort_*` were added; do not
  introduce a parallel query path or a second DB round-trip inside `compute_metrics`.
- The module's null-over-fabrication principle (`cost_index`'s D-a2 precedent, cited
  verbatim in the module's own docstrings) — applies identically to `success_rate`.
- No LLM/model call on this compute path — the existing CI grep-guard
  (`test_routing_rollup_no_llm_imports.py`) must stay green.

**Must not change** (protected areas):
- `regression_rate` semantics — stays `None`, with a citation comment only.
- `live_consumption_disabled` / `CCDASH_ROUTING_FEEDBACK_ENABLED` — DI-1, untouched.
- The pinned mapping (`routing_task_map_v1.json`) and its digest-lock CI guard.
- `cost_index`/`cost_coverage_fraction`/`eligible_for_adjustment`/`confidence` semantics.
- `(project_id, source_skill_name, model)` as the persisted/natural key — DI-4f measured
  and rejected every alternative (`task_class` 38.9%, `command_slug` 7.8%, coalesce chain
  41.1%); do not re-open that decision here.

---

## 9. Acceptance Criteria

(Verbatim from IntentTree node `node_01KZ4AKJZ27M2648AKGN00WCJ7`; do not paraphrase.)

- [ ] **AC1**: `success_rate` populated only for keys with genuine tool-usage attribution;
  `null` (never a fabricated constant) otherwise, with coverage counters emitted.
- [ ] **AC2**: Family split verified non-skewed post-DI-4d **before any row is emitted** —
  run the D-b4 live verification query against the current window and record the result
  (pass/HALT) in the Completion Report before proceeding to implementation.
- [ ] **AC3**: Skill-dimension coverage (~40–45% of `min_sample`-clearing keys) documented
  in the envelope (new response-level counters) **and** in the consumer-facing handoff spec
  — a consumer must be able to tell a skill-aware key from a `(project × model)` key
  without reading CCDash source.
- [ ] **AC4**: `regression_rate` remains `null` with a code comment citing the DI-4b
  closure.
- [ ] **AC5**: `live_consumption` remains disabled; no router-side change in this task.

**Additional engineering ACs:**
- [ ] Determinism: two invocations over a frozen fixture row-set produce field-identical
  `success_rate`/coverage output.
- [ ] Zero-tool-usage key asserts `success_rate is None` directly in a test.
- [ ] Partial-coverage key's `success_rate` is computed over the covered subset and its
  coverage signal differs from a fully-covered key's.
- [ ] Full-coverage key's `success_rate` changes when underlying call/error inputs change
  (provably derived, not a disguised constant).
- [ ] D-b1's call-volume-weighted aggregation is tested against a synthetic case where
  per-session-mean and call-volume-weighted would disagree (e.g., one 200-call session with
  1 error vs one 2-call session with 1 error) — assert the call-volume-weighted answer.
- [ ] Existing digest-parity / envelope-completeness tests updated only where they asserted
  the old fixed `None`, never weakened.

---

## 10. Validation Requirements

- [ ] Lint passes (ruff/flake8 per repo convention).
- [ ] Tests added/updated per Acceptance Criteria; relevant suite:
  `backend/.venv/bin/python -m pytest backend/tests/ -k "routing_rollup"`.
- [ ] Module continues to import cleanly.
- [ ] `docs/guides/routing-feedback-loop.md` updated if it documents the old
  always-`None`/placeholder `success_rate` behavior.
- [ ] `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` updated
  with the AC3 skill-dimension coverage documentation.
- [ ] No unrelated changes — this contract touches `routing_rollup.py`, its DTOs, its
  tests, and the two named docs only.

---

## 11. Risk Areas

- **D-b4's live-verification gate could HALT the whole contract.** If the current 30-day
  window is still dominated by pre-`b51de27` Codex sessions (parser fix landed, but
  `session_tool_usage` rows are only correct going forward per `di-4d-remeasurement.md`
  §0/§7), shipping `success_rate` now would silently re-introduce the categorical skew DI-4d
  just closed. This is the single highest-risk item — run the verification query first, and
  if skewed, stop and report rather than implementing around it.
- **Retry/recovery blindness (D-b5) understates reliability for recovered sessions.**
  Documented limitation, not fixed here — do not let scope creep into building retry
  linkage; the schema has none.
- **Skill-dimension coverage counters could be over-engineered.** The requirement (AC3) is
  that a consumer can tell the difference — a count/fraction pair is sufficient; do not
  build a per-consumer discounting algorithm.
- **Join cost**: `session_tool_usage` is a separate, potentially large table; ensure the
  aggregate is a single additional `GROUP BY`/join folded into the existing one-query
  pattern, not an N+1 per key.

---

## 12. Implementation Notes

**Suggested approach:**
1. Run D-b4's live verification query first (adapt the `di-4d-remeasurement.md` §1 SQL to
   the current window) and record the result before writing any code.
2. Extend `_fetch_raw_aggregate_rows`'s single aggregate query with a `LEFT JOIN` (or
   correlated subquery, matching whichever is cheaper for the two dialects) against
   `session_tool_usage`, summing `call_count`/`success_count` per key — mirroring how
   `cost_sum`/`cost_covered_count`/effort aggregates were added to the same query.
3. Carry the new `tool_call_sum`/`tool_error_sum` fields through `RawRollupRow` →
   `MappedRollupRow` → `ProviderRollupRow`, exactly as the cost fields were threaded.
4. Add a `_success_rate_and_coverage` helper mirroring `_cost_index_and_coverage`'s
   shape/docstring rigor; wire into `compute_metrics`.
5. Add skill-dimension coverage computation (new method, mirrors
   `compute_coverage_counters`'s FR-7 pattern) and thread its output into
   `build_response`/`RoutingRollupResponseDTO`.
6. Add the `regression_rate` citation comment.
7. Update the two named docs.

**Similar existing code**: `_cost_index_and_coverage`, `_task_class_cost_baselines`,
`compute_coverage_counters` — same file, same author intent, same docstring density
expected.

**Known gotchas**: `session_tool_usage` needs the join scoped by `project_id` (per prior
migration work adding `project_id` to that table) to avoid a cross-project fan-out; do not
join purely on `session_id` if `sessions.id` non-uniqueness is a risk in this table (per the
feasibility brief's Risks table — verify at implementation time whether this table shares
that risk).

---

## 13. Completion Report Required

Standard Completion Report per
`.claude/skills/dev-execution/validation/completion-criteria.md`, plus explicitly:
- **D-b4 verification result**: the live query, its output, and the pass/HALT
  determination — this is a hard requirement of AC2, not optional narrative.
- **D-b1/D-b2/D-b3/D-b5 decisions as actually implemented**, and any deviation from this
  contract's recommendations with rationale.

---

## Metadata & References

**Tier**: 1 (7 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no
phase orchestration. D-b4's verification step runs first, inside the same sprint, as a
go/no-go check before the implementation subtasks.

**Reviewer**: `task-completion-validator` (mandatory).

**Related Documents**: see `related_documents` in frontmatter.

---

## Design Decisions (Named, Not Silently Picked)

### D-b1 — Aggregation: call-volume-weighted, never per-session mean-of-means

**Decision**: `success_rate = 1 - (sum(tool_errors) / sum(tool_calls))` across all covered
sessions in the key — i.e., weighted by each session's own call volume — never an
unweighted average of each session's own error rate. A 200-call session with 1 error and a
2-call session with 1 error must not contribute equally to the key's rate.

**Status**: ratified — implementer must test this explicitly (see AC list).

### D-b2 — Zero-attribution keys emit `null`, never a fabricated constant

**Decision**: mirrors `cost_index`'s D-a2 verbatim. A key with no `session_tool_usage` rows
at all emits `success_rate: null`.

**Status**: ratified.

### D-b3 — Skill-dimension coverage: response-level counters, count/fraction only

**Decision**: add response-level counters (exact name is implementer's choice, e.g.
`skill_attributed_key_count`/`skill_unattributed_key_count`, scoped to the same
`min_sample_size`-clearing population the ~40–45% figure describes) so a consumer can
distinguish skill-aware keys from `(project × model)`-only keys without inspecting
`source_skill_name` per row. Do not build per-row router-discounting logic — count/fraction
only, consumer does its own discounting (same "evidence-only producer" posture as D-a3).

**Status**: recommended shape, implementer chooses the concrete field names; must be
tested and documented in the consumer-facing handoff spec (AC3).

### D-b4 — Live verification gate before any row is emitted

**Decision**: before implementing, re-run (adapted to the current window) the
`di-4d-remeasurement.md` §1 family-split query. If Claude and Codex/GPT families are not
measurably informative (i.e., if the live window is still dominated by stale
pre-`b51de27` `session_tool_usage` rows), HALT this contract and report — do not ship.

**Status**: ratified as a hard gate (AC2), not a recommendation.

### D-b5 — Retry/recovery is out of scope; document, do not model

**Decision**: raw error-rate is used as-is. The known limitation (95.2% of sessions with a
recorded tool failure still reach `completed`, per `di-4d-remeasurement.md` §7) is
documented in the module's docstring and the consumer-facing handoff spec, not fixed —
the schema has no retry linkage and building one is out of scope.

**Status**: ratified.
