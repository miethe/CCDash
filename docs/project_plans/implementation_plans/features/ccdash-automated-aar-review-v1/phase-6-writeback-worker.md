---
schema_version: 2
doc_type: phase_plan
title: "Phase 6: Gated Writeback Seam + Autonomous Worker + Guards"
status: draft
created: 2026-07-22
phase: 6
phase_title: "Gated Writeback Seam + Autonomous Worker + Guards"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- Phase 5 sealed (transport decision recorded; contract spec + smoke evidence complete).
exit_criteria:
- All 3 self-recursion guards tested; a rejected/pending run NEVER writes (integration test).
- AARReviewSweepJob worker is incremental, coalescing-guarded, and off the sync/watcher hot path by
  default (CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED default-off).
- Writeback seam is driven exclusively by op approve.
---

# Phase 6: Gated Writeback Seam + Autonomous Worker + Guards

**Duration**: ~1-1.5 sprints
**Dependencies**: Phase 5 sealed
**Assigned Subagent(s)**: `backend-architect` (primary — guards + escalation-quota + writeback-seam design), `python-backend-engineer` (secondary — worker job implementation)
**Points**: 6-9 (decisions block §4 anchor: H3 escalation-quota + dedup ledger, plus a
`telemetry_exporter`-patterned worker ~4 pts; no RF analogue — this is the highest-blast-radius phase,
deliberately last on the critical path)

## Overview

Enforce the 3 self-recursion guards designed (as data model, not enforcement) back in Phase 1: (1)
provenance self-exclusion via `skill_name`/`workflow_id`, never content-sniffing; (2) an idempotent
`(aar_document_id, session_id)` dedup ledger; (3) a hard, env-configured escalation quota checked
before any handoff to `op`/ARC. Ship `AARReviewSweepJob`, an incremental, coalescing-guarded worker
(default-off, `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`), following the
`telemetry_exporter.py`/`ArtifactRollupExportJob` pattern. Wire the writeback seam so the **sole**
trigger is `op approve` on an approved run record (Hard Invariant #2, D3).

**Boundary rationale** (decisions block §1): no escalation path exists pre-Phase 6, so guards have
nothing to guard until now — but their data inputs (provenance columns, dedup key) were made
first-class in Phase 1 specifically so this phase does not need a schema migration to add them.

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T6-001 | Design the 3 self-recursion guards | Design (as executable logic, not just data) the provenance self-exclusion filter, the idempotent dedup ledger check, and the escalation-quota check — each as a pure, deterministic gate evaluated before any handoff. | Design doc/comment specifies exact evaluation order and failure behavior (skip-without-failing, precedent: `_push_batch`'s `skipped_artifact_ids`) for each guard. | 1.5 pt | backend-architect | sonnet | extended | Phase 5 sealed |
| T6-002 | Resolve OQ-4 (escalation-quota default) | Decide the escalation-quota default (count/time-window) and whether it is per-project or global; must be env-configured per PRD §8.1 guard 3. | Decision recorded with rationale; env var name + default value documented for Phase 7's DOC-006 tuning spec. | 1 pt | backend-architect | sonnet | extended | T6-001 |
| T6-003 | Implement provenance self-exclusion filter | Implement the filter excluding any session tagged `skill_name == "aar-review"` (or a reserved `workflow_id` prefix) from the triage input set unconditionally — never content-sniffed. | Filter excludes tagged sessions deterministically; verified by a synthetic self-referential test case (T6-009). | 1 pt | python-backend-engineer | sonnet | adaptive | T6-001 |
| T6-004 | Implement idempotent dedup ledger | Implement the `(aar_document_id, session_id) -> triaged_at` dedup ledger on `aar_reviews` (columns already present from Phase 1); ensure re-runs of the sync/watcher cycle do not re-enqueue the same pair. Follow ADR-007 (`retry_on_locked`) for every write. | Ledger writes are idempotent under a simulated worker restart (T6-010); `retry_on_locked` wraps every write. | 1.5 pt | python-backend-engineer | sonnet | adaptive | T6-001 |
| T6-005 | Implement escalation-quota check | Implement the hard, env-configured escalation quota (T6-002's resolved default), checked before any handoff to `op`/ARC. CCDash never calls the swarm directly — it hands off a triage verdict + evidence bundle through the existing CLI/event contract; `op`'s own cost/tier gating remains the actual brake on runaway spend. | Quota check observably caps handoffs in a test simulating volume above the configured threshold. | 1.5 pt | python-backend-engineer | sonnet | adaptive | T6-002 |
| T6-006 | `AARReviewSweepJob` worker | Implement an incremental worker (changed/new AAR docs only, mirroring `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`) reusing the existing `(project_id, trigger)` coalescing guard — no second scheduler; follow the `telemetry_exporter.py`/`ArtifactRollupExportJob` registration pattern in `runtime/container.py`; default-off via `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`. | Worker registered in `runtime/container.py`; default-off; incremental scope confirmed by a test asserting only changed/new docs are re-triaged. | 2 pts | python-backend-engineer | sonnet | adaptive | T6-003, T6-004, T6-005 |
| T6-007 | Gated writeback seam | Wire the writeback call site so it is reachable **only** when a run record has status `approved` (via `op approve`); no code path allows a `pending`/`rejected` run to trigger writeback. | Writeback function signature requires an approved-run token/reference; no call site bypasses this check. | 1.5 pt | backend-architect | sonnet | extended | T6-005 |
| T6-008 | Integration test — rejected/pending run never writes | Add an integration test asserting a rejected or pending run record never reaches the writeback call site, across every code path that could theoretically invoke it. | Test is green and covers both `rejected` and `pending` states explicitly. | 1 pt | python-backend-engineer | sonnet | adaptive | T6-007 |
| T6-009 | Synthetic self-referential test (guard 1) | Construct a synthetic test case: an AAR-review-originated session (tagged `skill_name == "aar-review"`) is fed into the triage input set; assert it is excluded. | Test is green; proves guard 1 unconditionally, independent of session content. | 0.5 pt | python-backend-engineer | sonnet | adaptive | T6-003 |
| T6-010 | Simulated worker-restart idempotency test (guard 2) | Simulate a worker restart mid-sweep and assert the dedup ledger prevents re-enqueueing already-triaged `(aar_document_id, session_id)` pairs. | Test is green; proves idempotency across a restart boundary. | 0.5 pt | python-backend-engineer | sonnet | adaptive | T6-004 |

## Structured Acceptance Criteria

#### AC P6.1: Writeback triggers exclusively via `op approve` (Hard Invariant #2, D3)
- target_surfaces:
    - backend/adapters/jobs/aar_review_sweep.py
    - backend/runtime/container.py
- propagation_contract: The writeback function requires an approved-run reference as an argument;
  the worker (`AARReviewSweepJob`) never calls writeback directly — it only ever emits triage
  verdicts + evidence bundles through the existing CLI/event contract.
- resilience: N/A (invariant AC).
- visual_evidence_required: false
- verified_by: [T6-007, T6-008]

#### AC P6.2: Autonomous worker stays off the sync/watcher hot path by default
- target_surfaces:
    - backend/adapters/jobs/aar_review_sweep.py
    - backend/runtime/container.py
- propagation_contract: `AARReviewSweepJob` is registered behind
  `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` (default false); when disabled, zero additional load
  is added to the sync/watcher cycle.
- resilience: When the flag is unset/false, the read-only path (Phases 1-4) continues to function
  fully — this is a contract state, not a degraded mode.
- visual_evidence_required: false
- verified_by: [T6-006]

#### AC P6.3: All 3 self-recursion guards enforced in production (§8.1)
- target_surfaces:
    - backend/adapters/jobs/aar_review_sweep.py
    - backend/db/repositories/aar_reviews.py
- propagation_contract: Guard 1 (provenance self-exclusion) and guard 2 (dedup ledger) are evaluated
  inside the worker's per-document loop before any evidence is computed; guard 3 (escalation quota)
  is evaluated immediately before any handoff.
- resilience: N/A (invariant AC).
- visual_evidence_required: false
- verified_by: [T6-009, T6-010, T6-008]

## Reviewer Gates

- `task-completion-validator` — mandatory, standard per-phase gate.
- **`karen` milestone review — end of P4 (PRD roadmap tier).** This phase closes the PRD's highest-
  blast-radius tier (HITL-gated writeback + autonomous worker); `karen` must review before Phase 7
  documentation closes the feature.

## Phase 6 Quality Gates

- [ ] All 3 guards tested (T6-008, T6-009, T6-010) and green.
- [ ] Worker is incremental, coalescing-guarded, and default-off.
- [ ] Writeback seam requires an approved-run reference on every call path.
- [ ] `task-completion-validator` review passes.
- [ ] **`karen` end-of-P4 milestone review passes.**

## Phase 6 Success Criteria

All exit criteria in this file's frontmatter are met, AND the `karen` end-of-P4 milestone review has
passed, before Phase 7 begins.
