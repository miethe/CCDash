---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 14
title: Tracker and Intake Side Panel
status: completed
created: 2026-04-21
updated: '2026-04-21'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 4
completed_tasks: 4
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
- id: P14-001
  description: Add PlanningQuickViewPanel for tracker/intake rows.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - P11-001
  - P11-003
  estimated_effort: 2 pts
  priority: high
- id: P14-002
  description: Resolve node row click target as feature-first when featureSlug exists,
    doc-first otherwise.
  status: completed
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - P14-001
  estimated_effort: 1.5 pts
  priority: high
- id: P14-003
  description: Add promotion paths from quick view to full modal or nested planning
    page.
  status: completed
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - P14-001
  estimated_effort: 1 pt
  priority: medium
- id: P14-004
  description: Preserve tab/filter state across quick-view open/close.
  status: completed
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - P14-001
  estimated_effort: 1 pt
  priority: medium
parallelization:
  batch_1:
  - P14-001
  batch_2:
  - P14-002
  - P14-003
  - P14-004
  critical_path:
  - P14-001
  - P14-002
  estimated_total_time: 2 days
blockers: []
success_criteria:
- id: SC-14.1
  description: Row click opens a right-side panel in /planning; focus is trapped and
    restorable
  status: pending
- id: SC-14.2
  description: Feature rows show feature quick view; standalone docs show document
    quick view/modal
  status: pending
- id: SC-14.3
  description: Quick view can open full feature modal, full document modal, or expanded
    nested planning page
  status: pending
- id: SC-14.4
  description: Closing a panel returns to the same tracker tab and scroll position
  status: pending
- id: SC-14.5
  description: All tests green
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 14: Tracker and Intake Side Panel

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-14-progress.md \
  -t P14-001 -s completed
```

---

## Phase Overview

**Title**: Tracker and Intake Side Panel
**Entry Criteria**: Phase 11 modal orchestration complete. Route-local state infrastructure in place.
**Exit Criteria**: All tasks complete. Quick-view panel opens/closes correctly. State preserved across open/close. Tests green.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-14`

P14-001 (the panel itself) is the gate for this phase. Once the `PlanningQuickViewPanel` component exists, P14-002, P14-003, and P14-004 can run in parallel. All four tasks use `frontend-developer` or `ui-engineer-enhanced` — no backend work required.

**Key constraint**: Reuse existing feature/document components where possible. Do not create a second feature detail renderer unless the shared modal is genuinely too heavy for quick view. The plan explicitly calls this out as a risk.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P14-001 | Add PlanningQuickViewPanel component | ui-engineer-enhanced | sonnet | 2 pts | P11-001, P11-003 | pending |
| P14-002 | Resolve row click target feature-first / doc-first | frontend-developer | sonnet | 1.5 pts | P14-001 | pending |
| P14-003 | Add promotion paths from quick view | frontend-developer | sonnet | 1 pt | P14-001 | pending |
| P14-004 | Preserve tab/filter state across open/close | frontend-developer | sonnet | 1 pt | P14-001 | pending |

### P14-001 Acceptance Criteria
`PlanningQuickViewPanel` opens as a right-side panel within `/planning` when a tracker/intake row is clicked. Focus is trapped inside the panel when open and restored to the triggering row on close. The panel renders inside the planning route — it does not navigate away. Reuses existing feature summary components wherever feasible. Files: `components/Planning/TrackerIntakePanel.tsx`, new `components/Planning/PlanningQuickViewPanel.tsx`.

### P14-002 Acceptance Criteria
When a tracker/intake row has a `featureSlug` (or equivalent feature identity), clicking it resolves to the feature quick view. When a row is document-only (no feature context), clicking it resolves to the document quick view or `DocumentModal` directly, based on available metadata. The resolution logic is centralized — not scattered across row components.

### P14-003 Acceptance Criteria
`PlanningQuickViewPanel` exposes promotion actions: (1) "Open feature" — expands to the full route-local feature modal; (2) "Open document" — expands to the full `DocumentModal`; (3) "Go to planning page" — navigates to the nested `/planning/feature/:id` or `/planning/artifacts/:type` route. No tracker tab or filter state is lost when promoting.

### P14-004 Acceptance Criteria
Closing `PlanningQuickViewPanel` (via keyboard, backdrop click, or explicit close button) returns focus and scroll position to the same tracker tab the operator was on before opening. Active tab index and scroll offset are preserved in local state or route state — not relying on browser scroll restoration alone.

---

## Quick Reference

### Batch 1 — Gate task; must complete first
```
Task("ui-engineer-enhanced", "P14-001: Create PlanningQuickViewPanel component at components/Planning/PlanningQuickViewPanel.tsx. Opens as a right-side panel within /planning when tracker/intake rows are clicked. Focus trap required (open → trapped, close → restored to trigger row). Reuse existing feature summary and document components. Depends on Phase 11 route-local state infrastructure (P11-001, P11-003).")
```

### Batch 2 — After P14-001; run in parallel
```
Task("frontend-developer", "P14-002: Add centralized row click resolution to TrackerIntakePanel. When row has featureSlug → feature quick view in PlanningQuickViewPanel. When doc-only → document quick view or DocumentModal. Logic must be centralized, not duplicated per-row. Files: components/Planning/TrackerIntakePanel.tsx, components/Planning/PlanningQuickViewPanel.tsx")
Task("frontend-developer", "P14-003: Add promotion paths in PlanningQuickViewPanel: (1) Open full route-local feature modal, (2) Open full DocumentModal, (3) Navigate to nested /planning/feature/:id or /planning/artifacts/:type. No tab/filter state lost on promotion. Files: components/Planning/PlanningQuickViewPanel.tsx, services/planningRoutes.ts")
Task("frontend-developer", "P14-004: Preserve tracker tab index and scroll position across PlanningQuickViewPanel open/close. Closing returns operator to the same tab and scroll offset. Store in local state or route state. Files: components/Planning/TrackerIntakePanel.tsx, components/Planning/PlanningQuickViewPanel.tsx")
```

---

## Quality Gates

- [ ] `PlanningQuickViewPanel` opens from tracker/intake rows without navigation
- [ ] Focus trap functional (open → trapped, close → restored)
- [ ] Feature-row vs doc-row resolution correct and centralized
- [ ] Three promotion paths functional (feature modal, doc modal, nested page)
- [ ] Tab and scroll position preserved across open/close
- [ ] No duplicate feature detail renderer created (reuse confirmed)
- [ ] Tests green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
