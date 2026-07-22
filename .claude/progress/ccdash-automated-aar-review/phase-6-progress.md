---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-automated-aar-review
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
execution_model: batch-parallel
phase: 6
title: "Gated Writeback Seam + Autonomous Worker + Guards"
status: pending
created: 2026-07-22
updated: 2026-07-22
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: on-track

total_tasks: 10
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners:
- backend-architect
- python-backend-engineer
contributors: []

model_usage:
  primary: sonnet
  external: []

tasks:
- id: T6-001
  description: "Design the 3 self-recursion guards (as executable logic, not just
    data): the provenance self-exclusion filter, the idempotent dedup ledger check,
    and the escalation-quota check — each a pure, deterministic gate evaluated
    before any handoff."
  status: pending
  assigned_to: [backend-architect]
  dependencies: ["Phase 5 sealed"]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: extended
- id: T6-002
  description: "Resolve OQ-4 (escalation-quota default): decide the escalation-quota
    default (count/time-window) and whether it is per-project or global; must be
    env-configured per PRD §8.1 guard 3."
  status: pending
  assigned_to: [backend-architect]
  dependencies: [T6-001]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: extended
- id: T6-003
  description: "Implement provenance self-exclusion filter: exclude any session
    tagged skill_name == \"aar-review\" (or a reserved workflow_id prefix) from the
    triage input set unconditionally — never content-sniffed."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-001]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T6-004
  description: "Implement idempotent dedup ledger: (aar_document_id, session_id) ->
    triaged_at on aar_reviews (columns already present from Phase 1); ensure re-runs
    of the sync/watcher cycle do not re-enqueue the same pair; retry_on_locked wraps
    every write (ADR-007)."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-001]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T6-005
  description: "Implement escalation-quota check: hard, env-configured escalation
    quota (T6-002's resolved default), checked before any handoff to op/ARC. CCDash
    never calls the swarm directly — it hands off a triage verdict + evidence bundle
    through the existing CLI/event contract."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-002]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T6-006
  description: "AARReviewSweepJob worker: incremental worker (changed/new AAR docs
    only, mirroring CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED) reusing the existing
    (project_id, trigger) coalescing guard; follow the
    telemetry_exporter.py/ArtifactRollupExportJob registration pattern in
    runtime/container.py; default-off via
    CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-003, T6-004, T6-005]
  estimated_effort: "2 pts"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P6.2]
- id: T6-007
  description: "Gated writeback seam: wire the writeback call site so it is reachable
    only when a run record has status approved (via op approve); no code path allows
    a pending/rejected run to trigger writeback."
  status: pending
  assigned_to: [backend-architect]
  dependencies: [T6-005]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: extended
  ac_refs: [AC-P6.1]
- id: T6-008
  description: "Integration test — rejected/pending run never writes: assert a
    rejected or pending run record never reaches the writeback call site, across
    every code path that could theoretically invoke it. Covers both rejected and
    pending states explicitly."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-007]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P6.1, AC-P6.3]
- id: T6-009
  description: "Synthetic self-referential test (guard 1): construct a synthetic test
    case — an AAR-review-originated session (tagged skill_name == \"aar-review\") is
    fed into the triage input set; assert it is excluded, unconditionally,
    independent of session content."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-003]
  estimated_effort: "0.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P6.3]
- id: T6-010
  description: "Simulated worker-restart idempotency test (guard 2): simulate a
    worker restart mid-sweep and assert the dedup ledger prevents re-enqueueing
    already-triaged (aar_document_id, session_id) pairs across a restart boundary."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T6-004]
  estimated_effort: "0.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P6.3]

parallelization:
  batch_1: [T6-001]
  batch_2: [T6-002, T6-003, T6-004]
  batch_3: [T6-005, T6-009, T6-010]
  batch_4: [T6-006, T6-007]
  batch_5: [T6-008]
  critical_path: [T6-001, T6-002, T6-005, T6-007, T6-008]
  estimated_total_time: "6-9 pts (5 sequential batches)"

blockers: []

success_criteria:
- id: SC-1
  description: "All 3 guards tested (T6-008, T6-009, T6-010) and green."
  status: pending
- id: SC-2
  description: "Worker is incremental, coalescing-guarded, and default-off."
  status: pending
- id: SC-3
  description: "Writeback seam requires an approved-run reference on every call
    path."
  status: pending
- id: SC-4
  description: "task-completion-validator review passes."
  status: pending
- id: SC-5
  description: "karen end-of-P4 milestone review passes."
  status: pending

files_modified:
- backend/adapters/jobs/aar_review_sweep.py
- backend/runtime/container.py
- backend/db/repositories/aar_reviews.py

notes: >
  Entry criteria: Phase 5 sealed (transport decision recorded; contract spec + smoke
  evidence complete). Highest-blast-radius phase, deliberately last on the critical
  path. Guard data inputs (provenance columns, dedup key) were made first-class in
  Phase 1 specifically so this phase does not need a schema migration to add them.
  This is the end-of-P4 (PRD roadmap tier) milestone — requires a karen review in
  addition to task-completion-validator before Phase 7 documentation closes the
  feature. Escalate Phase 6 guard-logic debugging to gpt-5.3-codex only after 2+
  failed local Claude debug cycles.
---

# ccdash-automated-aar-review - Phase 6: Gated Writeback Seam + Autonomous Worker + Guards

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-6-progress.md \
  -t T6-001 -s completed

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-6-progress.md \
  --updates "T6-001:completed,T6-002:completed"

# Arbitrary field update
python .claude/skills/artifact-tracking/scripts/update-field.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-6-progress.md \
  --field overall_progress --value 25
```

---

## Objective

Enforce the 3 self-recursion guards designed in Phase 1 (provenance self-exclusion, idempotent
dedup ledger, escalation quota), ship the incremental `AARReviewSweepJob` worker (default-off),
and wire the writeback seam so the sole trigger is `op approve` on an approved run record (Hard
Invariant #2, D3).

---

## Implementation Notes

### Architectural Decisions

- D3 (locked): CCDash emits only — never dispatches ARC/swarm, never mutates
  SkillMeat/skills/agents; writeback triggers exclusively via `op approve`.
- D4 (locked): the 3 self-recursion guards are designed as executable logic here; their data
  inputs (provenance columns + dedup key) were already made first-class in Phase 1.

### Patterns and Best Practices

- `AARReviewSweepJob` follows the `telemetry_exporter.py`/`ArtifactRollupExportJob` registration
  pattern in `runtime/container.py`.
- Guard failure behavior precedent: skip-without-failing, per `_push_batch`'s
  `skipped_artifact_ids` pattern.

### Known Gotchas

- Guard 1 (provenance self-exclusion) must never content-sniff — tag-based exclusion only.
- Escalation quota is CCDash's own brake at the handoff boundary; `op`'s own cost/tier gating
  remains the actual brake on runaway spend downstream.
- `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` must default false; when disabled, the read-only
  path (Phases 1-4) continues to function fully — this is a contract state, not a degraded mode.

### Development Setup

No special setup beyond the standard backend venv; worker registration should be verified against
`backend/runtime/container.py`'s existing job-adapter wiring.

---

## Completion Notes

_To be filled in when this phase is complete: what was built, key learnings, unexpected
challenges, recommendations for Phase 7._
