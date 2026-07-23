---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-automated-aar-review
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
execution_model: batch-parallel
phase: 5
title: Cross-Repo Consumer Contract + Event Transport Decision
status: completed
created: '2026-07-22'
updated: '2026-07-22'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: complete
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- documentation-writer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T5-001
  description: 'Resolve D5 (transport decision): evaluate whether the existing PULL
    path (REST/MCP/CLI, already polled at op''s classify->plan->dispatch gate) is
    sufficient, or whether the log-only aar_review_candidate event must be promoted
    to a durable/queued PUSH. Base the decision on T5-004''s smoke evidence.'
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - Phase 4 sealed
  estimated_effort: 1.5 pt
  assigned_model: sonnet
  model_effort: extended
  started: '2026-07-22T16:00:00Z'
  completed: '2026-07-22T23:00:00Z'
  evidence:
  - adr: proposed-adr.md#phase-5-d5-addendum
  verified_by:
  - task-completion-validator
- id: T5-002
  description: 'ADR addendum recording D5: author an ADR addendum recording the transport
    decision (T5-001) and its rationale; append to the accepted ADR or a dated addendum
    file.'
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T5-001
  estimated_effort: 0.5 pt
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-22T16:00:00Z'
  completed: '2026-07-22T23:00:00Z'
  evidence:
  - adr: proposed-adr.md#phase-5-d5-addendum
  verified_by:
  - task-completion-validator
- id: T5-003
  description: "Author cross-repo consumer contract specification citing PRD \xA7\
    7.3's aar_review_candidate event schema verbatim, naming the routing decision\
    \ inputs (correlation.confidence, triage_verdict), and stating explicitly that\
    \ human_triage_required verdicts must never auto-route to op council. Hand-off\
    \ artifact for the op/agentic_meta_dev repo team."
  status: completed
  assigned_to:
  - documentation-writer
  dependencies:
  - T5-001
  estimated_effort: 2 pts
  assigned_model: haiku
  model_effort: adaptive
  ac_refs:
  - AC-P5.1
  started: '2026-07-22T16:00:00Z'
  completed: '2026-07-22T23:00:00Z'
  evidence:
  - doc: docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
  verified_by:
  - task-completion-validator
- id: T5-004
  description: Build a best-effort cross-repo smoke harness (in this repo, or a thin
    script invoking a real op instance if available) demonstrating op consuming a
    real aar_review_candidate/verdict and producing a routed decision with zero CCDash-side
    code change required.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T5-001
  estimated_effort: 2 pts
  assigned_model: sonnet
  model_effort: extended
  started: '2026-07-22T16:00:00Z'
  completed: '2026-07-22T23:00:00Z'
  evidence:
  - harness: backend/scripts/aar_review_consumer_smoke.py-exit0
  verified_by:
  - task-completion-validator
- id: T5-005
  description: 'Assert human_triage_required never auto-routes: add an assertion (in
    the smoke harness or a targeted contract test) proving a human_triage_required
    verdict is never passed to op council/ARC by the documented routing contract.'
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T5-003
  - T5-004
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs:
  - AC-P5.2
  started: '2026-07-22T16:00:00Z'
  completed: '2026-07-22T23:00:00Z'
  evidence:
  - assertion: AC-P5.2-human_triage_never_auto_routes-green
  verified_by:
  - task-completion-validator
parallelization:
  batch_1:
  - T5-001
  batch_2:
  - T5-002
  - T5-003
  - T5-004
  batch_3:
  - T5-005
  critical_path:
  - T5-001
  - T5-003
  - T5-005
  estimated_total_time: 5-8 pts (3 sequential batches)
blockers: []
success_criteria:
- id: SC-1
  description: D5 transport decision recorded with rationale tied to real smoke evidence
    (T5-001, T5-002).
  status: met
- id: SC-2
  description: "Contract spec cites \xA77.3 verbatim; routing inputs named exactly."
  status: met
- id: SC-3
  description: Cross-repo smoke evidence captured (best-effort acceptable, documented
    as such).
  status: met
- id: SC-4
  description: human_triage_required non-auto-route assertion green.
  status: met
- id: SC-5
  description: task-completion-validator review passes.
  status: met
files_modified:
- docs/project_plans/adrs/
notes: "Entry criteria: Phase 4 sealed and its karen end-of-P2 milestone review passed.\
  \ This repo's obligation is the contract + transport decision + smoke harness only\
  \ \u2014 heavy op-side implementation lives out-of-repo in agentic_meta_dev/op;\
  \ exit criteria intentionally do NOT require a working op-side implementation. op-side\
  \ routing must be proven before autonomous writeback runs unattended in Phase 6\
  \ (highest blast radius last, per decisions block \xA71).\n"
progress: 100
---

# ccdash-automated-aar-review - Phase 5: Cross-Repo Consumer Contract + Event Transport Decision

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-5-progress.md \
  -t T5-001 -s completed

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-5-progress.md \
  --updates "T5-001:completed,T5-002:completed"

# Arbitrary field update
python .claude/skills/artifact-tracking/scripts/update-field.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-5-progress.md \
  --field overall_progress --value 25
```

---

## Objective

Specify the `op`-side consumer contract end-to-end and resolve decision D5 (PULL vs PUSH
transport) from real cross-repo smoke evidence, recording the outcome as an ADR addendum.

---

## Implementation Notes

### Architectural Decisions

- D5 (pending until this phase resolves it): defaults to PULL-as-v1 unless smoke proves it
  insufficient (decisions block §pending default).
- Contract doc is the canonical hand-off artifact; the `agentic_meta_dev`/`op` repo implementation
  must reference it rather than re-deriving the schema independently (PRD §14 Documentation
  Acceptance).

### Patterns and Best Practices

- This repo's deliverable is the contract + decision + smoke harness, not a working `op`
  implementation.

### Known Gotchas

- Do not decide D5 before T5-004's smoke evidence exists.
- A partial/simulated smoke (e.g., mocking op's dispatch gate) is acceptable if a live cross-repo
  run is unavailable, and must be documented as such.

### Development Setup

No special local setup; T5-004 may require access to a real `op` instance (best-effort — see
Known Gotchas).

---

## Completion Notes

_To be filled in when this phase is complete: what was built, key learnings, unexpected
challenges, recommendations for Phase 6._
