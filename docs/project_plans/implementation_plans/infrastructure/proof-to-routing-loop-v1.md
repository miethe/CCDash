---
title: "Implementation Plan: Proof \u2192 Routing Feedback Loop \u2014 CCDash Producer\
  \ Surface (BP-6)"
schema_version: 2
doc_type: implementation_plan
it_schema: 1
status: completed
created: 2026-07-29
updated: '2026-07-31'
feature_slug: proof-to-routing-loop
feature_version: v1
tier: 2
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: null
scope: "CCDash producer-side rollup, persistence, worker sweep, and REST/MCP/CLI transports\
  \ for a deterministic, opt-in, no-LLM (source_skill_name \xD7 model)-grain routing-feedback\
  \ surface; router-side merge/consumption is out of scope."
effort_estimate: 16 points
architecture_summary: "Clones the shipped Automated AAR Review Loop end-to-end: vendored\
  \ contract constants \u2192 routing_rollup table (dual DDL) \u2192 RoutingRollupQueryService\
  \ (agent_queries/) \u2192 RoutingRollupSweepJob (worker) \u2192 REST/MCP/CLI transports\
  \ \u2192 guard/parity tests + docs."
category: infrastructure
priority: medium
risk_level: medium
changelog_required: true
intenttree_node: node_01KY69N7KW566PGJ51BMYRK5SN
deferred_items_spec_refs:
- docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
- docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md
- docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md
findings_doc_ref: null
related_documents:
- docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-feasibility-brief.md
- docs/project_plans/exploration/proof-to-routing-loop/spikes/tech-findings.md
- docs/project_plans/exploration/proof-to-routing-loop/spikes/value-findings.md
- docs/project_plans/exploration/proof-to-routing-loop/spikes/risk-findings.md
- docs/project_plans/design-specs/proof-to-routing-loop.md
- /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
- /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json
- docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
- docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
- docs/guides/aar-review-loop.md
- .claude/worknotes/proof-to-routing-loop/decisions-block.md
references:
  user_docs:
  - docs/guides/aar-review-loop.md
  context:
  - docs/guides/launch-time-capture-convention.md
  specs:
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json
  related_prds:
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
spike_ref: null
adr_refs: []
charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
changelog_ref: null
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: null
contributors: []
tags:
- implementation
- planning
- infrastructure
- routing-feedback
- cross-repo
- no-llm
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
planning_maturity: shipped
open_questions:
- q: 'OQ-1: Is skill_name (bucketed via the pinned v1 mapping) an acceptable v1 task_class
    source?'
  owner: implementation-planner
  status: resolved-by-D3
- q: 'OQ-2: Exact metric-payload schema.'
  owner: implementation-planner
  status: "resolved \u2014 see \xA76.3 field table below, Phase 3"
- q: 'OQ-3: Minimum-sample eligibility_hint semantics/default/override.'
  owner: implementation-planner
  status: "resolved \u2014 eligible_for_adjustment = sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE\
    \ (default 5), Phase 3"
- q: 'OQ-4: Protected-class / _unclassified emission policy.'
  owner: implementation-planner
  status: "resolved \u2014 coverage-only rows, eligible_for_adjustment hardcoded false,\
    \ gated by CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS (unclassified always\
    \ emitted regardless), Phase 3"
- q: 'OQ-5: Vendored-mapping path + refresh procedure.'
  owner: implementation-planner
  status: "resolved \u2014 backend/application/services/agent_queries/routing_task_map_v1.json;\
    \ refresh = re-vendor + bump mapping_version/mapping_digest constants together,\
    \ CI parity test fails otherwise, Phase 1/6"
- q: 'OQ-6: Rolling window length default and decay-input representation.'
  owner: implementation-planner
  status: deferred
decisions:
- decision: 'D1: Ship the CCDash producer surface only; router-side empirical merge
    + live consumption is a named cross-repo (MeatySkills/ibm-main) deferral'
  rationale: This repo squashes to CCDash main; the router owns merge math and is
    currently live_consumption_disabled.
  status: locked
- decision: "D2: Emit the achievable (task_class \xD7 model) tuple; drop profile/effort_tier/model_variant;\
    \ provider is derived from model"
  rationale: profile/effort_tier/model_variant are write-path-dead (0/14,399 populated).
    provider rides free via derive_model_identity().
  status: locked
- decision: "D3: Apply the pinned v1 skill_name\u2192task_class mapping and emit the\
    \ canonical task_class + full 11-field join envelope; never emit raw skill_name\
    \ as task_class; unmapped \u2192 _unclassified, coverage-only, never a routing\
    \ key"
  rationale: "17 skill names vs 12 policy keys, zero direct overlaps \u2014 exact\
    \ mapping is mandatory."
  status: locked
- decision: 'D4: Persist a worker-computed routing_rollup table as the PULL source,
    not read-time aggregation'
  rationale: Deterministic O(1)-ish PULL, keeps compute off the read path, clones
    the shipped aar_reviews pattern.
  status: locked
- decision: "D5: CCDash designs the empirical metric payload \u2014 the contract leaves\
    \ this unspecified"
  rationale: Contract pins only the join envelope + vocabulary; numeric proof fields
    are the producer's design surface.
  status: locked
- decision: "D6: New capability string routing:feedback + default-OFF flag CCDASH_ROUTING_FEEDBACK_ENABLED;\
    \ disabled \u2192 deterministic disabled envelope across REST/MCP/CLI"
  rationale: Mirrors the AAR-review capability gate + flag pattern.
  status: locked
- decision: 'D7: Reversibility = emit-only + flag-flip; CCDash never actuates routing'
  rationale: CCDash owns emission reversibility; the router owns adjustment reversibility.
  status: locked
- decision: 'D8: Router-side numeric merge is out of scope; captured as a DOC-006
    cross-repo handoff design spec'
  rationale: Owned by MeatySkills/ibm-main; not buildable from CCDash's working tree.
  status: locked
- decision: "D9: The metric payload is provisional/additive-versioned; socializing\
    \ it to the router owner is a strong recommendation before Phase 5 seals \u2014\
    \ NOT a hard gate; this feature's 'done' asserts producer-surface completeness,\
    \ not that the feedback loop is live end-to-end"
  rationale: "Contract leaves the numeric payload unspecified \u2014 a unilaterally-designed\
    \ shape risks an unconsumable rollup, but router-owner acknowledgment cannot block\
    \ CCDash's own completion on an external repo's availability/timeline."
  status: attempted
decision_gates:
- gate: "D9 \u2014 socialize D5 metric-payload shape with router owner before Phase\
    \ 5 (Transport Surfaces) seals; strong recommendation, NOT a hard blocking gate\
    \ on this feature's own completion"
  status: attempted
success_metrics:
- "Mapping digest parity: 100% \u2014 vendored mapping bytes SHA-256 == contract's\
  \ pinned mapping_digest, every CI run"
- "No-LLM compliance: 100% \u2014 zero banned model-client/dispatch symbols in the\
  \ transitive import graph"
- "Determinism: 100% \u2014 two sweeps over an unchanged window produce field-identical\
  \ rollup rows"
- "Disabled-state consistency: 100% \u2014 REST/MCP/CLI return byte-identical disabled\
  \ envelopes"
- 'Coverage visibility: every response reports mapped_count/unclassified_count/distinct_unmapped_skill_names'
contributors_note: null
scores: {}
acceptance_criteria:
- "AC-1 through AC-8 carried forward verbatim from the PRD \xA711 \u2014 see Phase\
  \ 6 for resolved verified_by task IDs"
execution_mode: unassigned
agent_title: "Proof \u2192 Routing Feedback Loop \u2014 CCDash producer surface (BP-6)"
agent_summary: "Emit a deterministic, opt-in, no-LLM (source_skill_name \xD7 model)-grain\
  \ routing-feedback rollup via routing_rollup + agent_queries + REST/MCP/CLI, cloning\
  \ the shipped AAR-review PULL pattern; router-side consumption is out of scope."
wave_plan:
  serialization_barriers: []
  phases:
  - id: P1
    depends_on: []
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/application/services/agent_queries/routing_task_map_v1.json
    - backend/application/services/agent_queries/routing_feedback_contract.py
    - backend/routers/client_v1.py
    - backend/config.py
  - id: P2
    depends_on:
    - P1
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
    - backend/db/migration_governance.py
    - backend/db/repositories/routing_rollup.py
    - backend/tests/test_routing_rollup_repo.py
  - id: P3
    depends_on:
    - P2
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/application/services/agent_queries/routing_rollup.py
    - backend/application/services/agent_queries/models.py
    - backend/tests/test_routing_rollup_determinism.py
    - backend/tests/test_routing_rollup_no_llm_imports.py
  - id: P4
    depends_on:
    - P3
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/adapters/jobs/routing_rollup_sweep_job.py
    - backend/adapters/jobs/runtime.py
    - backend/runtime/container.py
    - backend/tests/test_routing_rollup_sweep_job.py
  - id: P5
    depends_on:
    - P3
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/routers/_client_v1_routing_rollup.py
    - backend/routers/client_v1.py
    - backend/mcp/tools/routing.py
    - backend/mcp/tools/__init__.py
    - backend/cli/commands/routing.py
    - backend/cli/main.py
    - backend/tests/test_routing_rollup_transports.py
  - id: P6
    depends_on:
    - P4
    - P5
    isolation: shared
    owner_skills: []
    files_affected:
    - backend/tests/test_routing_rollup_no_llm_imports.py
    - backend/tests/test_routing_feedback_contract_parity.py
    - backend/tests/test_routing_rollup_envelope_completeness.py
    - backend/tests/test_routing_rollup_determinism.py
    - backend/tests/test_routing_rollup_sparse_protected.py
    - backend/tests/test_routing_rollup_disabled_state.py
    - docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md
    - docs/guides/routing-feedback-loop.md
    - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
    - docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md
    - docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md
    - CHANGELOG.md
  waves:
  - - P1
  - - P2
  - - P3
  - - P4
    - P5
  - - P6
---

# Implementation Plan: Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)

**Plan ID**: `IMPL-2026-07-29-PROOF-TO-ROUTING-LOOP`
**Date**: 2026-07-29
**Author**: implementation-planner (Sonnet 5), from an Opus-authored decisions block
**Human Brief**: N/A — not created (out of scope for this expansion; author separately if desired)
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`
- **Decisions block**: `.claude/worknotes/proof-to-routing-loop/decisions-block.md`
- **Sibling precedent**: `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md`, `docs/guides/aar-review-loop.md`, `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`

**Complexity**: Medium (Tier 2, held below the 16-pt Tier 3 boundary — see decisions block §4 Estimation Notes)
**Total Estimated Effort**: 16 points
**Target Timeline**: single sprint, 6 sequential/semi-parallel phases

## Executive Summary

CCDash already proves, per session, which `(skill, model)` route worked, failed, cost too much, or
regressed — but today that proof is pure observability. This plan ships the **producer** half of a
cross-repo feedback loop: a deterministic, opt-in, no-LLM rollup computed at
`(project_id, source_skill_name, model)` grain, with `task_class` derived only through the pinned
`aos.routing.feedback` v1.0.0 contract's exact mapping, persisted to a new `routing_rollup` table by a
worker sweep, and served read-only via REST/MCP/CLI for the MeatySkills delegation-router to PULL.
Every phase is a structural clone of the shipped Automated AAR Review Loop (`aar_reviews` table →
`AARReviewSweepJob` → `agent_queries/aar_review.py` → REST/MCP/CLI trio), with one genuinely
algorithmic phase (Phase 3, the aggregation + mapping + metric-design core). The feature is
additive-only, default-off, and reversible by a single flag flip; it never actuates routing.

This plan ships the **producer surface only**: the backward-pass loop does not close until the
router-side empirical merge lands in MeatySkills/`ibm-main` (currently `live_consumption_disabled`,
tracked as DI-1) — a named cross-repo deferral, never a blocking precondition for this plan's own
completion.

## Implementation Strategy

### Architecture Sequence

This feature has no frontend surface. The sequence mirrors the shipped AAR-review loop rather than
the full 8-layer UI-bearing template:

1. **Contract & Envelope Foundations** (Phase 1) — vendored mapping, pinned constants, capability
   string, default-off flag. No behavior change.
2. **Data Layer** (Phase 2) — `routing_rollup` table, dual DDL, repository (ADR-006/007 discipline).
   Additive-only — not a Mode-D migration of existing rows.
3. **Rollup Compute Service** (Phase 3) — pure-SQL aggregation, mapping application, coverage +
   metric-payload design. The only algorithmic phase.
4. **Worker Sweep Job** (Phase 4) — multi-project, incremental, idempotent persistence.
5. **Transport Surfaces** (Phase 5) — REST + MCP + CLI, one shared DTO, capability advertisement.
6. **Validation, Guards & Docs** (Phase 6) — no-LLM/parity/determinism/disabled-state test battery,
   consumer-contract doc, operator guide, deferred-items design specs.

### Parallel Work Opportunities

Phase 4 (worker/writer, touches `backend/adapters/jobs/*` + `backend/runtime/container.py`) and Phase 5
(transport/reader, touches `backend/routers/client_v1.py` + `backend/mcp/tools/*` + `backend/cli/*`)
operate on disjoint files once Phase 3 freezes the `routing_rollup` table shape and the
`RoutingRollupQueryService` read contract. They run in the same wave (wave_4) under file-ownership
batching.

### Critical Path

`P1 → P2 → P3 → (P4 ∥ P5) → P6`. P1–P3 are strictly serial: each phase freezes a contract
(envelope constants → table columns → query-service output shape) that the next phase consumes. No
task in this feature touches auth, payments, deletion, or an existing-row migration — the new table is
additive-only, so no phase requires `isolation: worktree`.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 1 | Contract & Envelope Foundations | 2 pts | backend-architect, python-backend-engineer | sonnet | Seam precision (digest pins) — kept on primary, not offloaded. |
| 2 | Data Layer | 3 pts | data-layer-expert | sonnet | Additive-only DDL (not Mode-D); dual SQLite+PG parity, ADR-006/007. |
| 3 | Rollup Compute Service | 4 pts | backend-architect, python-backend-engineer | sonnet (extended) | Algorithmic core — aggregation, mapping, coverage, metric design. Highest reasoning need. |
| 4 | Worker Sweep Job | 2 pts | python-backend-engineer | sonnet | Mechanical clone of `AARReviewSweepJob`; ICA-offload eligible (`claude-sonnet-5[1m]`). |
| 5 | Transport Surfaces | 3 pts | python-backend-engineer | sonnet | Mechanical clone of AAR REST/MCP/CLI trio; ICA-offload eligible. Parallel with Phase 4. |
| 6 | Validation, Guards & Docs | 2 pts | task-completion-validator (gate), karen (feature-end gate), documentation-writer, python-backend-engineer | haiku (docs) / sonnet (tests) | Guards+parity+determinism tests + docs + DOC-006 handoff specs. |
| **Total** | — | **16 pts** | — | — | — |

**Model column conventions**: all phases are Claude-only (no external model/UI surface in this
feature); Phase 6 mixes haiku (docs tasks) and sonnet (guard/parity/determinism test tasks) — see
Phase 6 task table for the per-task split.

> Estimation rationale (H1–H6 anchors, AAR-review comparable) lives in the decisions block
> (`.claude/worknotes/proof-to-routing-loop/decisions-block.md` §4). This plan retains only the
> per-phase point totals below. **Reconciliation note**: 16 pts is the *floor* of a 16–20-pt
> persisted-path (D4) expectation anchored to the AAR-review-clone discount (H5) — not the ceiling of
> the feasibility brief's original 10–16 range, which assumed a read-time-only aggregation path; see
> the decisions block §4 for the three named contingencies that could push the total toward 20.

### Clone Anchor Reference Map (H5 — grounding for every phase file)

This feature is a structural clone of the shipped Automated AAR Review Loop (merged `7d96c3e`). Every
phase file below points its tasks at the specific real files it mirrors:

| CCDash concern | AAR-review precedent (shipped) | This feature's new analog |
|---|---|---|
| Table DDL | `backend/db/sqlite_migrations.py`, `backend/db/postgres_migrations.py` (v42, `aar_reviews`) | same files, new `routing_rollup` table |
| Repository | `backend/db/repositories/aar_reviews.py` | `backend/db/repositories/routing_rollup.py` |
| Compute service | `backend/application/services/agent_queries/aar_review.py` | `backend/application/services/agent_queries/routing_rollup.py` |
| DTO | `AARReviewDTO` in `backend/application/services/agent_queries/models.py` | `RoutingRollupKeyDTO`/`RoutingRollupResponseDTO` in the same file |
| Worker sweep | `backend/adapters/jobs/aar_review_sweep_job.py` (`AARReviewSweepJob`) | `backend/adapters/jobs/routing_rollup_sweep_job.py` (`RoutingRollupSweepJob`) |
| Worker wiring | `backend/adapters/jobs/runtime.py`, `backend/runtime/container.py` | same files, new job registration |
| REST route module | `backend/routers/_client_v1_aar_review.py` + wiring in `backend/routers/client_v1.py` | `backend/routers/_client_v1_routing_rollup.py` + same wiring file |
| Capability string | `"aar-review"` in `_V1_CAPABILITIES` (`backend/routers/client_v1.py`) | `"routing:feedback"` in the same list |
| MCP tool | `ccdash_aar_review` in `backend/mcp/tools/reports.py`, wired via `backend/mcp/tools/__init__.py::register_tools` | new `backend/mcp/tools/routing.py::register_routing_tools`, wired the same way |
| CLI command | `report_app.command("aar-review")` in `backend/cli/commands/report.py`, registered in `backend/cli/main.py` | new `routing_app` Typer sub-app in `backend/cli/commands/routing.py`, registered the same way |
| Default-off flag | `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` (`backend/config.py`) | `CCDASH_ROUTING_FEEDBACK_ENABLED` |
| No-LLM guard | `backend/tests/test_aar_review_no_llm_imports.py` | `backend/tests/test_routing_rollup_no_llm_imports.py` |
| Write-path discipline | `backend/db/repositories/base.py::retry_on_locked` (ADR-007) | same helper, new repository |

## Deferred Items & In-Flight Findings Policy

### Deferred Items

**Rule**: Every deferred item MUST have a corresponding design-spec authoring task in Phase 6
(DOC-006). The resulting design-spec path is appended to `deferred_items_spec_refs` in this plan's
frontmatter once authored.

#### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| DI-1 | dependency-blocked | Router-side empirical merge + live consumption (bounded-adjustment cap, effective-score floor, minimum-sample re-gate, decay blend, `RoutingRecord` provenance) is owned by MeatySkills/`ibm-main` and currently `live_consumption_disabled`; not buildable from CCDash's working tree (D1, D8). | Router owner flips `live_consumption_disabled` → enabled and negotiates the merge algorithm against CCDash's emitted envelope. | `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` |
| DI-2 | research-needed | Model/provider cross-repo namespacing: CCDash emits `model` verbatim and derives `provider` via `derive_model_identity()`; no canonical cross-repo model-string format is negotiated with the router owner. | A cross-repo model-naming negotiation is opened between CCDash and the router owner. | `docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md` |
| DI-3 | research-needed | Window/decay numeric defaults beyond CCDash's own config knobs: the 30-day window / N≥5 sample-size candidates are spike-anchored placeholders (value-findings), not locked requirements (PRD OQ-6/§13). | Router-side consumption goes live and empirically validates (or invalidates) the candidate defaults. | `docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md` |

*All three items get ONE combined DOC-006 task in Phase 6 (three output docs, one task ID) per the
Documentation Finalization convention.*

### In-Flight Findings

**Lazy-creation rule** applies: `.claude/findings/proof-to-routing-loop-findings.md` is created only on
the first real finding during execution. `findings_doc_ref` stays `null` until then.

### Quality Gate

Phase 6 cannot be sealed until all three deferred items have a design-spec path recorded (DOC-006), and
`deferred_items_spec_refs` is populated with all three paths above.

**Reference**: `.claude/skills/planning/references/deferred-items-and-findings.md`

## Phase Breakdown

Full task tables, detailed task specs, quality gates, key files, and testing strategy live in the
per-phase files below (this plan is split per the >800-line optimization pattern). Every task ID
follows the `T{phase}-{nnn}` convention (docs tasks use the template's `DOC-00N` convention within
Phase 6). Every `dev:backend` execution reference uses `--runtime local`.

| Phase | File | Points |
|-------|------|--------|
| 1 — Contract & Envelope Foundations | [phase-1-contract-envelope-foundations.md](./proof-to-routing-loop-v1/phase-1-contract-envelope-foundations.md) | 2 |
| 2 — Data Layer | [phase-2-data-layer.md](./proof-to-routing-loop-v1/phase-2-data-layer.md) | 3 |
| 3 — Rollup Compute Service | [phase-3-rollup-compute-service.md](./proof-to-routing-loop-v1/phase-3-rollup-compute-service.md) | 4 |
| 4 — Worker Sweep Job | [phase-4-worker-sweep-job.md](./proof-to-routing-loop-v1/phase-4-worker-sweep-job.md) | 2 |
| 5 — Transport Surfaces | [phase-5-transport-surfaces.md](./proof-to-routing-loop-v1/phase-5-transport-surfaces.md) | 3 |
| 6 — Validation, Guards & Docs | [phase-6-validation-guards-docs.md](./proof-to-routing-loop-v1/phase-6-validation-guards-docs.md) | 2 |
| **Total** | — | **16** |

### Acceptance Criteria Index (carried forward from PRD §11, `verified_by` resolved in Phase 6)

| AC | Title | verified_by |
|----|-------|-------------|
| AC-1 | Envelope completeness | T3-003, T6-003 |
| AC-2 | Mapping fidelity | T1-005, T6-002 |
| AC-3 | Determinism + no-LLM | T3-001, T3-005, T6-001, T6-004 |
| AC-4 | Default-off disabled behavior | T5-004, T6-006 |
| AC-5 | Sparse-key / eligibility visibility | T3-004, T6-005 |
| AC-6 | `_unclassified` / protected-class coverage-only handling | T3-002, T6-005 |
| AC-7 | Reversibility | T4-003, T6-006 |
| AC-8 | Version-mismatch resilience | T1-002, T1-005, T6-006 |

Full AC text (target_surfaces, propagation_contract, resilience) is unchanged from PRD §11 — this plan
resolves only the `verified_by` task IDs above; do not re-derive the AC text in phase files, cite the
PRD. Phase-3 `verified_by` backfill rationale: T3-001 (read-rule / aggregation skeleton) →
determinism test (T6-004); T3-003 (mapped_count/unclassified_count coverage counters) →
envelope-completeness test (T6-003), which asserts these counters at the top level; T3-004
(sample_count/eligible_for_adjustment) → sparse-key fixture test (T6-005); T3-002 (protected-class /
`_unclassified` policy) → protected-class fixture test (T6-005, already listed under AC-6).

**Consumer-absent resilience (B3)**: AC-4's `verified_by` (T6-006) includes a capability-string-
unconditional test — `GET /api/v1/capabilities` MUST include `"routing:feedback"` regardless of
`CCDASH_ROUTING_FEEDBACK_ENABLED`. This is the concrete "consumer-absent" resilience-axis coverage for
this feature (per the decisions block's AC-discipline note on R-P2/R-P4 substitution).

**Write-path-discipline gate (orthogonal to AC-1..AC-8)**: Phase 2's T2-004 (parity allowlist +
direct-count `retry_on_locked`/ADR-006/007 test) is verified independently of the 8 contract ACs
above — it is a write-path-discipline gate, not one of AC-1..AC-8.

## Risk Mitigation

### Technical Risks (from decisions block §3)

| Risk | Impact | Likelihood | Mitigation Strategy |
| ----- | :----: | :--------: | ---------- |
| Silent non-join / cross-repo vocabulary drift (seam risk, R-P3) | High | Low (post-contract) | Emit canonical `task_class` via the exact pinned mapping only; carry all envelope digests verbatim; Phase 6 CI parity test (T6-002) on the vendored mapping bytes; router's `validateFeedbackJoin()` is the fail-closed backstop; `integration_owner` declared on Phase 6. |
| Per-key sparsity for a single-operator workload | Medium | Medium | Coarsened, density-validated tuple (52% N≥5 per value-findings); emit `sample_count` + `eligible_for_adjustment` so the router applies its own threshold; thin keys simply don't route — safe, not wrong. |
| Constraint-4 violation (LLM on the compute/read path) | Medium | Low | Pure-SQL aggregation; worker/service import nothing from `backend.adapters.agents`/`services.agents`; CI-enforced AST-walk guard (T3-005, extended T6-001); determinism test over a fixture DB. |
| Metric-payload shape unconsumable by the router (unspecified by the contract) | Medium | Medium | D5 payload is additive-versioned; D9 (attempted 2026-07-31 — informal GitHub issue on `github.com/miethe/MeatySkills`, response pending) — socialized the shape to the router owner before Phase 5 sealed; keep evidence-only so a mismatch is inert, never harmful. |
| Blast radius on CCDash (new table/worker/endpoints regress existing reads) | Low | Low | Additive-only DDL; default-off flag; zero mutation of `sessions`/`aar_reviews`; instant env-var revert; disabled state returns a deterministic empty envelope. |

### Schedule Risks

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| D9 socialization slips past Phase 5 | Low (materialized, resolved) | — | Resolved 2026-07-31: attempt documented in Phase 5's completion note + `.claude/worknotes/proof-to-routing-loop/decisions-block.md` (informal GitHub issue, response pending). |
| Phase 3 (the only algorithmic phase) runs long | Medium | Low | `karen` review at the Phase 3 milestone (per decisions block §4 estimation notes) in addition to `task-completion-validator` per phase. |

## Resource Requirements

**Skill Requirements**: FastAPI, SQLAlchemy/aiosqlite, PostgreSQL dual-DDL discipline, Typer CLI,
FastMCP tool registration, pytest/AST-walk CI guards. No frontend, no external models, no UI-package
extraction candidates (no `*.tsx` files anywhere in this plan).

## Success Metrics

See frontmatter `success_metrics` (mirrors PRD §4 Success Metrics table verbatim — mapping digest
parity, no-LLM compliance, determinism, disabled-state consistency, coverage visibility).

## Post-Implementation

- No monitoring dashboard changes required (rollup is emit-only; existing OTEL span/log conventions
  from the AAR-review worker are cloned per-phase, not net-new observability surfaces).
- D9 socialization is a strong recommendation, not a hard gate: this feature's "done" state asserts
  producer-surface completeness only. The metric payload (D5) is provisional and additive-versioned —
  it is not guaranteed consumable by the router as-is, and router-owner acknowledgment is not a
  precondition for CCDash marking this feature complete.
- The backward-pass loop does not close end-to-end until the router-side empirical merge lands in
  MeatySkills/`ibm-main` (DI-1, currently `live_consumption_disabled`) — a named cross-repo deferral,
  never a blocker on CCDash's own completion.
- DI-1/DI-2/DI-3 stay tracked via their Phase 6 design specs until their promotion triggers fire.

---

**Progress Tracking:**

See `.claude/progress/proof-to-routing-loop/` (created when execution begins).

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-07-29
