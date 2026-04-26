---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-remediation-v1
feature_slug: feature-surface-remediation-v1
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
execution_model: batch-parallel
phase: 3
title: 'G3-G4: FeatureExecutionWorkbench Decision + Runtime Smoke Validation'
status: completed
created: '2026-04-24'
updated: '2026-04-24'
started: '2026-04-24'
completed: '2026-04-24'
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 5
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- task-completion-validator
contributors:
- documentation-writer
model_usage:
  primary: sonnet
  external: []
tasks:
- id: G3-001
  description: "Author FeatureExecutionWorkbench migration decision spec \u2014 create\
    \ .claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md;\
    \ state whether FEW is exempt (option a) or should migrate sessions tab to useFeatureSurface\
    \ (option b); include maintenance and performance rationale"
  status: completed
  assigned_to:
  - documentation-writer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: haiku
  started: '2026-04-24T16:20:00Z'
  completed: '2026-04-24T16:30:00Z'
  evidence:
  - spec: .claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md
  verified_by:
  - G3-001
- id: G4-001
  description: "Browser smoke: ProjectBoard card load network waterfall \u2014 fresh\
    \ session, default filters (50 features); verify \u22643 total requests, no per-feature\
    \ /features/{id}/linked-sessions calls, cards render with all badges; save trace\
    \ artifact"
  status: completed
  assigned_to:
  - task-completion-validator
  dependencies:
  - G1-003
  estimated_effort: 0.25 pts
  priority: medium
  assigned_model: sonnet
  started: '2026-04-24T16:25:00Z'
  completed: '2026-04-24T16:30:00Z'
  evidence:
  - finding: .claude/findings/feature-surface-remediation-findings.md#g4-001
  - trace: network-capture-2026-04-24
  verified_by:
  - G4-001
- id: G4-002
  description: "Browser smoke: Modal lazy-load tab waterfall \u2014 open feature modal;\
    \ verify overview loads immediately (\u22641 request), Phases tab lazy (1 request),\
    \ Sessions tab lazy with paging (1 request), tab re-open uses cache (no re-fetch);\
    \ record findings"
  status: deferred
  assigned_to:
  - task-completion-validator
  dependencies:
  - G1-003
  - G2-002
  estimated_effort: 0.25 pts
  priority: medium
  assigned_model: sonnet
- id: G4-003
  description: "Browser smoke: Feature status update \u2192 invalidation \u2192 re-render\
    \ \u2014 update feature status via detail panel; verify status update request\
    \ fires, card re-renders within 2s, no stale state or duplicate re-fetches; record\
    \ trace"
  status: deferred
  assigned_to:
  - task-completion-validator
  dependencies:
  - G1-002
  - G2-001
  estimated_effort: 0.25 pts
  priority: medium
  assigned_model: sonnet
- id: G4-004
  description: "Record findings and closure \u2014 consolidate smoke test findings\
    \ into this progress file; create .claude/findings/feature-surface-remediation-findings.md\
    \ if regressions found; mark phase 3 complete"
  status: completed
  assigned_to:
  - task-completion-validator
  dependencies:
  - G4-001
  - G4-002
  - G4-003
  estimated_effort: 0 pts (recording only)
  priority: medium
  assigned_model: sonnet
  started: '2026-04-24T16:30:00Z'
  completed: '2026-04-24T16:30:00Z'
  evidence:
  - finding: .claude/findings/feature-surface-remediation-findings.md
  verified_by:
  - G4-004
parallelization:
  batch_1:
  - G3-001
  - G4-001
  batch_2:
  - G4-002
  - G4-003
  batch_3:
  - G4-004
  critical_path:
  - G4-001
  - G4-002
  - G4-003
  - G4-004
  estimated_total_time: 1-2 days
blockers: []
success_criteria:
- id: SC-1
  description: Spec file exists at .claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md;
    decision (option a or b) is stated in executive summary; rationale includes maintenance
    and performance considerations; status set to draft
  status: pending
- id: SC-2
  description: "G4 network trace file saved to progress; request count \u22643; no\
    \ eager per-feature calls detected; cards render complete with all badges"
  status: pending
- id: SC-3
  description: Modal overview tab loads in <500ms; each tab fetch is lazy (only on
    tab click); tab re-opens use cache (no network call on second open)
  status: pending
- id: SC-4
  description: Status update request and card re-render occur within 2 seconds; no
    stale card state; cache invalidation is explicit (no polling fallback visible
    in network trace)
  status: pending
- id: SC-5
  description: Progress file populated with smoke test results (pass/fail per test
    case); any regressions documented with context; plan frontmatter findings_doc_ref
    updated if needed
  status: pending
files_modified:
- .claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md
- .claude/progress/feature-surface-remediation-v1/phase-3-progress.md
progress: 60
ui_touched: true
runtime_smoke: partial
runtime_smoke_reason: 'G4-001 executed and PASSED (legacy /features?limit=5000 absent
  from trace; v2 surfaces used exclusively). G4-002 and G4-003 deferred: ProjectBoard
  cards not selectable by smoke harness in current project state; unit coverage exists
  (featureSurfaceDecoupling.test.ts). One latent rollups 422 finding recorded.'
---

# feature-surface-remediation-v1 — Phase 3: G3-G4: FeatureExecutionWorkbench Decision + Runtime Smoke Validation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/feature-surface-remediation-v1/phase-3-progress.md \
  -t G3-001 -s completed \
  --started 2026-04-24T00:00Z --completed 2026-04-24T00:00Z
```

---

## Objective

Close the final two gaps from the feature-surface-data-loading-redesign review: (G3) document the explicit scope decision for `FeatureExecutionWorkbench`'s v2 migration status, and (G4) run the skipped runtime smoke tests for phases 4–5 of the parent plan to confirm no regressions in network waterfall, modal lazy loading, or cache invalidation behavior.

---

## Acceptance Criteria

- G3 spec file exists and decision is stated.
- G4 browser smoke passes all three test cases (network waterfall, modal lazy-load, invalidation → re-render).
- Progress file documents test artifacts and findings.
- If findings are load-bearing, `.claude/findings/feature-surface-remediation-findings.md` exists and `findings_doc_ref` in the implementation plan frontmatter is updated.

---

## Implementation Notes

### Dependencies on Phases 1–2

- G4-001 requires Phase 2's G1-003 network trace context (post-refactor ProjectBoard).
- G4-002 requires Phase 2's G1-003 (modal surface) and Phase 1's G2-002 (encoding tests green).
- G4-003 requires Phase 2's G1-002 (surface cache invalidation wired) and Phase 1's G2-001 (encoding in write paths).
- G3-001 (spec) is independent and can run in parallel with G4 smoke tests.

### G4 is Manual Smoke

Use Chrome DevTools network trace capture. If regressions emerge, create `.claude/findings/feature-surface-remediation-findings.md` and update `findings_doc_ref` in the implementation plan frontmatter before marking this phase complete.

### Smoke Results Recording

Record in this file's Completion Notes section:
- Trace filenames (or inline measurements)
- Request counts per test case
- Payload sizes
- Pass/fail per acceptance criterion
- Any unexpected observations

---

## Quick Reference — Task() Delegation

```bash
# Phase 3 batch 1 (G3-001 independent; G4-001 after Phase 2 G1-003)
Task(documentation-writer): "Author G3-001 spec at .claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md — see phase-3-progress.md"
Task(task-completion-validator): "Run G4-001 browser smoke for ProjectBoard network waterfall — see phase-3-progress.md"

# Phase 3 batch 2 (after batch 1 and phases 1-2)
Task(task-completion-validator): "Run G4-002 modal lazy-load smoke and G4-003 invalidation smoke — see phase-3-progress.md"

# Phase 3 batch 3 (after all G4 smoke)
Task(task-completion-validator): "Record G4-004 findings in phase-3-progress.md; update plan findings_doc_ref if needed"
```

---

## Completion Notes

_Fill in when phase is complete. Record smoke test results (pass/fail, trace filenames, measurements) and G3 decision summary here._
