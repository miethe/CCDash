---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 8
title: Planning UI Integration — Modals, Drill-Downs & Validation
status: pending
created: '2026-04-17'
updated: '2026-04-17'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: 4-5 days
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- task-completion-validator
tasks:
- id: PCP-703
  description: Make each artifact-composition badge clickable; open a dedicated screen
    listing artifacts of that type (Design Specs, PRDs, Progress Files, etc.) with
    title, status, updated date, and key metadata. Reuse DocumentsList or similar
    from /plans/documents. Rows open DocumentModal on click.
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PCP-702
  - PCP-303
  estimated_effort: 3 pts
  priority: high
- id: PCP-704
  description: Refactor planning surfaces (feature cards, lists, graph nodes representing
    features) to delegate to the ProjectBoard feature modal on click instead of planning-only
    detail panels. Add Expand button in modal navigating to /planning/feature/:id/detail
    for advanced views.
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PCP-702
  - PCP-401
  estimated_effort: 3 pts
  priority: high
- id: PCP-705
  description: Refactor all planning artifact clicks (design spec, PRD, progress file,
    context file, report) to open DocumentModal from /plans instead of planning-only
    viewers. Ensure modal renders content, metadata, and navigation the same way as
    /plans.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - PCP-706
  - PCP-303
  estimated_effort: 2 pts
  priority: high
- id: PCP-707
  description: Ensure all planning surface modals and detail-page transitions follow
    the same pattern. Test modal-to-page transitions, deep linking, and browser back/forward.
    Update route definitions and link generation for consistent paths.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - PCP-703
  - PCP-704
  - PCP-705
  estimated_effort: 2 pts
  priority: high
- id: PCP-708
  description: Add/update UI tests covering active plans/planned features columns,
    artifact drill-down screens, feature modal integration, document modal flows, and
    badge consolidation. Run Phase 6 and earlier validation tests to confirm no regressions.
  status: pending
  assigned_to:
  - frontend-developer
  - task-completion-validator
  dependencies:
  - PCP-707
  estimated_effort: 2 pts
  priority: high
parallelization:
  batch_1:
  - PCP-703
  - PCP-704
  - PCP-705
  batch_2:
  - PCP-707
  batch_3:
  - PCP-708
  critical_path:
  - PCP-704
  - PCP-707
  - PCP-708
  estimated_total_time: 10-12 pts / 4-5 days
blockers: []
notes:
- Phase 8 depends on Phase 7 completion; PCP-702, PCP-706, and PCP-709 must be done
  before Phase 8 work begins.
- PCP-703, PCP-704, and PCP-705 can proceed in parallel once Phase 7 is complete.
- PCP-707 consolidates navigation state after modal refactors are in place; should
  not start until PCP-703, PCP-704, and PCP-705 are done.
- PCP-708 validates all Phase 7-8 work and confirms Phase 6 behavior unchanged. Full
  test suite including Phase 3-6 must pass.
- Phase 8 is the final UI consolidation phase. After completion, no planning-only
  viewers, modals, or navigation patterns remain.
---

# Phase 8 Progress: Planning UI Integration — Modals, Drill-Downs & Validation

## Overview

Phase 8 is the final consolidation phase for the Planning Control Plane V1. It integrates artifact composition drill-down screens, unifies feature and document modal delegation across all planning surfaces, ensures navigation consistency (modal ↔ page transitions, deep linking, back/forward), and adds comprehensive frontend test coverage for all new and refactored flows. Phase 6 validation gates must remain satisfied throughout.

## Objective

Complete the consolidation of planning UI surfaces to use `/board` feature modals and `/plans` document modals exclusively. Make artifact composition indicators drill-down clickable using shared document-list components. Establish consistent navigation patterns across planning home, graph, phase operations, and launch prep surfaces. Validate all Phase 7-8 consolidation work and confirm Phase 3-6 behavior is unchanged.

## Task Breakdown

| Task ID | Description | Assigned To | Est. | Dependencies | Status |
|---------|-------------|-------------|------|--------------|--------|
| PCP-703 | Artifact composition drill-down screens (clickable badges) | frontend-developer, ui-engineer-enhanced | 3 pts | PCP-702, PCP-303 | pending |
| PCP-704 | Feature modal unification — delegate feature clicks to ProjectBoard modal | frontend-developer, ui-engineer-enhanced | 3 pts | PCP-702, PCP-401 | pending |
| PCP-705 | Document modal integration — delegate artifact clicks to DocumentModal | frontend-developer | 2 pts | PCP-706, PCP-303 | pending |
| PCP-707 | Navigation and state consistency — modal/page transitions and deep links | frontend-developer | 2 pts | PCP-703, PCP-704, PCP-705 | pending |
| PCP-708 | Frontend tests for all consolidation flows; Phase 6 regression check | frontend-developer, task-completion-validator | 2 pts | PCP-707 | pending |

## Batch Dependency Structure

```
Batch 1 (parallel):    PCP-703, PCP-704, PCP-705
Batch 2 (sequential):  PCP-707 (depends on Batch 1)
Batch 3 (final):       PCP-708 (depends on PCP-707)
```

## Quality Gates

1. All Phase 6 validation tests pass without modification after each batch.
2. Artifact composition drill-down screens render and filter correctly; clicking rows opens DocumentModal.
3. Clicking any feature on a planning surface opens the same feature modal as `/board`.
4. Clicking any planning artifact (design spec, PRD, progress file, context, report) opens DocumentModal as in `/plans`.
5. All modal ↔ page transitions follow consistent pattern: planning home ➜ feature modal ➜ full page ➜ back.
6. Deep links to features and artifacts resolve correctly; browser back returns to prior planning view.
7. All Phase 3-6 validation tests pass after Phase 8 completion; no regressions.

## Success Criteria

1. Artifact composition indicators are clickable; drill-down screens reuse document-list rendering from `/plans`.
2. All feature clicks open the feature modal (consistent with `/board`); artifact clicks open DocumentModal (consistent with `/plans`).
3. All planning navigation follows the same modal-to-page pattern as `/board` and `/plans`.
4. Phase 6 validation gates remain satisfied; no behavior regressions.
5. Deep links to features and artifacts work; browser back/forward navigation is consistent.
6. Comprehensive test coverage confirms all Phase 7-8 flows work and Phase 3-6 behavior is unchanged.
7. No planning-only viewers, modals, or navigation patterns remain in codebase.

## Quick Reference

### PCP-703 — Artifact Composition Drill-Down Screens
```
Task("Make each artifact-composition badge on planning surfaces clickable.
Opening a badge opens a filterable list screen (Design Specs, PRDs, Progress
Files, etc.) reusing DocumentsList or equivalent from /plans/documents. Rows
open DocumentModal on click. Drill-down screens accessible from planning home
and phase operations.
Assigned: frontend-developer, ui-engineer-enhanced.
Dependencies: PCP-702, PCP-303.")
```

### PCP-704 — Feature Modal Unification
```
Task("Refactor planning feature cards, feature lists, and graph nodes representing
features so they delegate to the ProjectBoard feature modal on click. Remove
planning-only detail panels for features. Add an Expand button inside the modal
navigating to /planning/feature/:id/detail for advanced views.
Assigned: frontend-developer, ui-engineer-enhanced.
Dependencies: PCP-702, PCP-401.")
```

### PCP-705 — Document Modal Integration
```
Task("Refactor all planning artifact clicks (design spec, PRD, progress file,
context file, report) across planning surfaces to open DocumentModal from /plans
instead of planning-only viewers. Modal must render content and metadata the same
way as /plans.
Assigned: frontend-developer.
Dependencies: PCP-706, PCP-303.")
```

### PCP-707 — Navigation and State Consistency
```
Task("Verify and fix modal/page transition patterns across all planning surfaces.
Ensure: planning home -> feature modal -> full page -> back works consistently;
deep links to features and artifacts resolve; browser back returns to prior
planning view. Update route definitions and link generation for consistent paths.
Assigned: frontend-developer.
Dependencies: PCP-703, PCP-704, PCP-705.")
```

### PCP-708 — Frontend Tests for Consolidation Flows
```
Task("Add or update UI tests covering: active plans/planned features columns,
artifact drill-down screens, feature modal integration, document modal flows,
and badge consolidation. Run Phase 6 and earlier validation tests and confirm
no regressions. Include mutation testing to verify coverage quality.
Assigned: frontend-developer, task-completion-validator.
Dependency: PCP-707.")
```
