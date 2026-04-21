---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 11
title: Route-Local Modal Orchestration
status: in_progress
created: 2026-04-21
updated: '2026-04-21'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 25
completion_estimate: on-track
total_tasks: 4
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- frontend-developer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: P11-001
  description: Extract or wrap the ProjectBoard feature modal so /planning can host
    it without rendering the board page.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  note: Batch 1 delegated to frontend worker for route-local feature modal hosting.
- id: P11-002
  description: Replace planningFeatureModalHref primary usage with route-local modal
    state.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - P11-001
  estimated_effort: 2 pts
  priority: high
- id: P11-003
  description: Add planning modal route state, deep-link support, and back-button
    handling.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - P11-001
  estimated_effort: 2 pts
  priority: high
- id: P11-004
  description: Normalize artifact click behavior around DocumentModal.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - P11-001
  estimated_effort: 2 pts
  priority: medium
parallelization:
  batch_1:
  - P11-001
  batch_2:
  - P11-002
  - P11-003
  - P11-004
  critical_path:
  - P11-001
  - P11-002
  estimated_total_time: 2 days
blockers: []
success_criteria:
- id: SC-11.1
  description: Planning can open a feature modal from summary, graph, and feature
    columns while URL remains under /planning
  status: completed
- id: SC-11.2
  description: Primary feature clicks no longer navigate to /board; existing explicit
    'Open board' links still work
  status: pending
- id: SC-11.3
  description: /planning?feature=<id>&modal=feature or equivalent opens the modal;
    browser back closes it before leaving planning
  status: pending
- id: SC-11.4
  description: Artifact rows/chips open documents in place; nested /planning/artifacts/:type
    remains available for group drill-down
  status: pending
- id: SC-11.5
  description: All tests green
  status: pending
files_modified:
- components/ProjectBoard.tsx
- components/Planning/PlanningHomePage.tsx
- services/planningRoutes.ts
- components/Planning/__tests__/planningHomePage.test.tsx
- services/__tests__/planningRoutes.test.ts
progress: 25
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 11: Route-Local Modal Orchestration

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-11-progress.md \
  -t P11-001 -s completed
```

---

## Phase Overview

**Title**: Route-Local Modal Orchestration
**Entry Criteria**: Parent plan phases 8-10 merged. Modal extraction infrastructure available.
**Exit Criteria**: All tasks complete. Planning modal and side-panel surfaces open/close correctly. URL state preserved. Tests green.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-11`

Phase 11 is the foundational phase for this addendum. P11-001 (modal extraction) must complete first; P11-002, P11-003, and P11-004 can then run in parallel. Phases 14 and 15 both depend on the route-local state infrastructure established here — do not skip or short-circuit.

**Sequencing risk**: This phase touches `PlanningHomePage.tsx` and `PlanningRouteLayout.tsx`, the same files targeted by parent plan phases 8-10. Confirm those phases are merged before starting P11-001 to avoid divergent edits.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P11-001 | Extract/wrap ProjectBoard feature modal for /planning hosting | ui-engineer-enhanced | sonnet | 2 pts | — | pending |
| P11-002 | Replace planningFeatureModalHref with route-local modal state | ui-engineer-enhanced | sonnet | 2 pts | P11-001 | pending |
| P11-003 | Add modal route state, deep-link, back-button handling | frontend-developer | sonnet | 2 pts | P11-001 | pending |
| P11-004 | Normalize artifact click behavior around DocumentModal | frontend-developer | sonnet | 2 pts | P11-001 | pending |

### P11-001 Acceptance Criteria
Planning can open a feature modal from summary panel, graph panel, and feature columns while the URL remains under `/planning`. The modal is hosted in the planning route context, not the board route context. `ProjectBoard` itself is not re-rendered.

### P11-002 Acceptance Criteria
Primary feature clicks no longer navigate to `/board`. Existing explicit "Open board" secondary links/buttons continue to work. `planningFeatureModalHref` may remain for the secondary action only.

### P11-003 Acceptance Criteria
`/planning?feature=<id>&modal=feature` (or equivalent hash/search param scheme) opens the modal on direct load. Browser back closes the modal before navigating away from `/planning`. Deep links from external surfaces (CHANGELOG, worknotes) resolve correctly.

### P11-004 Acceptance Criteria
Artifact rows and chips throughout planning home, tracker, graph, and summary panels open `DocumentModal` in place. The nested route `/planning/artifacts/:type` remains navigable for group drill-down; rows inside it still open `DocumentModal` rather than navigating away.

---

## Quick Reference

### Batch 1 — Run first (unblocked)
```
Task("ui-engineer-enhanced", "P11-001: Extract or wrap the ProjectBoard feature modal (components/ProjectBoard.tsx) so /planning can host it without rendering the board page. Planning should be able to open a feature modal from summary, graph, and feature columns while URL remains under /planning. Files: components/ProjectBoard.tsx, components/Planning/PlanningHomePage.tsx, services/planningRoutes.ts")
```

### Batch 2 — After P11-001 completes; run in parallel
```
Task("ui-engineer-enhanced", "P11-002: Replace planningFeatureModalHref primary usage with route-local modal state. Primary feature clicks must no longer navigate to /board. Explicit 'Open board' secondary links still work. Files: services/planningRoutes.ts, components/Planning/PlanningHomePage.tsx, components/Planning/PlanningSummaryPanel.tsx")
Task("frontend-developer", "P11-003: Add planning modal route state, deep-link support, and back-button handling. /planning?feature=<id>&modal=feature opens the modal; browser back closes it before leaving /planning. Files: components/Planning/PlanningRouteLayout.tsx, App.tsx, services/planningRoutes.ts")
Task("frontend-developer", "P11-004: Normalize artifact click behavior around DocumentModal. Artifact rows/chips open documents in place across planning home, tracker, graph, and summary. Nested /planning/artifacts/:type remains for group drill-down. Files: components/Planning/PlanningHomePage.tsx, components/Planning/TrackerIntakePanel.tsx, components/DocumentModal.tsx")
```

---

## Quality Gates

- [ ] Feature modal opens from planning without board navigation
- [ ] `planningFeatureModalHref` primary path removed from non-secondary links
- [ ] Deep-link `/planning?feature=<id>&modal=feature` functional
- [ ] Browser back closes modal before leaving `/planning`
- [ ] Artifact clicks open `DocumentModal` in place
- [ ] No regressions in existing board feature modal behavior
- [ ] Tests green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
- 2026-04-21 Worker A: Completed P11-001 route-local feature modal hosting by exporting the existing board modal, hosting it from PlanningHomePage state, keeping planning feature clicks under `/planning`, and adding focused route/resolver tests.
