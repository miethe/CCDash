---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 3
title: Planning Home, Graph, and Tracker/Intake Surfaces
status: pending
created: '2026-04-16'
updated: '2026-04-16'
started: '2026-04-16'
completed: ''
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: 4-5 days
total_tasks: 4
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- ai-agents
tasks:
- id: PCP-301
  description: Add the planning route, navigation entry point, loading/error/empty
    states, and page shell.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - PCP-204
  estimated_effort: 2 pts
  priority: high
- id: PCP-302
  description: Build summary cards and lists for intake, active plans, stale phases,
    mismatches, and tracker backlog.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - PCP-301
  estimated_effort: 3 pts
  priority: high
- id: PCP-303
  description: Build graph/list detail surfaces that explain lineage, blockers, and
    related entities.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - PCP-301
  - PCP-202
  estimated_effort: 3 pts
  priority: high
- id: PCP-304
  description: Add panels or tabs for ready-for-promotion specs, stale shaping work,
    deferred tracker items, and validation warnings.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - PCP-302
  - PCP-303
  estimated_effort: 2 pts
  priority: high
parallelization:
  batch_1:
  - PCP-301
  batch_2:
  - PCP-302
  - PCP-303
  batch_3:
  - PCP-304
  critical_path:
  - PCP-301
  - PCP-303
  - PCP-304
  estimated_total_time: 10 pts / 4-5 days
blockers: []
notes:
- Phase 2 exposed planning APIs (`/api/agent/planning/*`), live topics (project.planning,
  feature.planning), and the frontend `services/planning.ts` client; Phase 3 consumes
  these to deliver planning-first UI surfaces.
- Commits land per batch as requested ("commit in batches").
success_criteria:
- id: SC-3.1
  description: Planning home becomes the primary entry point for project-level planning
    operations.
  status: pending
- id: SC-3.2
  description: Users can navigate planning hierarchy without bouncing between unrelated
    screens.
  status: pending
- id: SC-3.3
  description: Tracker and intake visibility is available in-product and grounded
    in existing workflow semantics.
  status: pending
files_modified: []
progress: 25
---

# ccdash-planning-control-plane-v1 - Phase 3

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Objective

Deliver the planning-first home route, graph/detail drill-down, and tracker/intake visibility surfaces on top of the Phase 2 planning APIs and live topics. Reuse existing shell, navigation, and data-context patterns; do not fork a parallel app structure.

## Orchestration Quick Reference

```bash
# Batch 1
Task("frontend-developer", "Execute PCP-301: /planning route + shell + nav entry (components/Planning/, App.tsx, Layout.tsx)")

# Batch 2 (parallel after PCP-301)
Task("ui-engineer-enhanced", "Execute PCP-302: PlanningHomePage summary surface (intake, active, stale, mismatches, tracker)")
Task("ui-engineer-enhanced", "Execute PCP-303: PlanningGraphPanel + PlanningNodeDetail drill-down with lineage/blocker evidence")

# Batch 3 (after PCP-302 + PCP-303)
Task("frontend-developer", "Execute PCP-304: TrackerIntakePanel (promotion-ready specs, stale shaping, deferred trackers, validation warnings)")
```
