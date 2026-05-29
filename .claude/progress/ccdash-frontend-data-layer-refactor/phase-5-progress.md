---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 5
title: Backend Fat-Read Bundles + Waterfall Collapse
status: not_started
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs: []
pr_refs: []
owners:
- python-backend-engineer
- ui-engineer-enhanced
contributors: []
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 10
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T5-001
  description: Create backend/application/services/agent_queries/dashboard.py with get_dashboard_bundle (sessions page 20 + task_counts by status); DashboardBundleDTO in models.py; @memoized_query 10s TTL; OTEL span
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-008
- id: T5-002
  description: Wire GET /api/v1/dashboard in backend/routers/client_v1.py returning ClientV1Envelope[DashboardBundleDTO]; same auth guard as other /api/v1/ routes; pytest integration test
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-001
- id: T5-003
  description: Add get_planning_view_bundle(project_id, include) in backend/application/services/agent_queries/planning.py composing existing summary/graph/session_board helpers; wire GET /api/agent/planning/view?include= in backend/routers/agent.py; pytest with/without include param
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-008
- id: T5-004
  description: Add get_analytics_overview_bundle in backend/application/services/agent_queries/ (new or extend analytics); wire GET /api/analytics/overview-bundle in backend/routers/analytics.py; above-fold data only; pytest; OTEL span
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-008
- id: T5-005
  description: Author services/queries/dashboard.ts with useDashboardBundleQuery (staleTime 10_000, enabled on dashboard route); resilience for missing taskCounts ({}) and sessions ([])
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-002
  - T4-010
- id: T5-006
  description: Update Dashboard.tsx to consume useDashboardBundleQuery; one GET /api/v1/dashboard cold load; fetch-spy test asserts no separate /api/sessions or /api/tasks calls; missing field resilience
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-005
- id: T5-007
  description: Add usePlanningViewQuery in services/queries/planning.ts; wire to GET /api/agent/planning/view?include=; one above-fold call; graph/session-board on demand via enabled+include= refinement
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-003
  - T4-010
- id: T5-008
  description: Seam task — verify bundle endpoint integration in dev server; Dashboard single /api/v1/dashboard call; Planning single planning/view call; resilience to missing taskCounts; R-P3 cross-owner seam (python-backend-engineer × ui-engineer-enhanced)
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-007
- id: T5-009
  description: Runtime smoke Dashboard + Planning + Analytics; verify single above-fold call per view; all bundle payloads render correctly
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-008
- id: T5-010
  description: task-completion-validator gate (P5)
  status: pending
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T5-009
parallelization:
  batch_1:
  - T5-001
  - T5-003
  - T5-004
  batch_2:
  - T5-002
  batch_3:
  - T5-005
  - T5-007
  batch_4:
  - T5-006
  batch_5:
  - T5-008
  batch_6:
  - T5-009
  batch_7:
  - T5-010
  critical_path:
  - T5-001
  - T5-002
  - T5-005
  - T5-006
  - T5-008
  - T5-009
  - T5-010
blockers: []
success_criteria:
- id: SC-5.1
  description: backend/application/services/agent_queries/dashboard.py created with DashboardBundleDTO; pytest passing
  status: pending
- id: SC-5.2
  description: GET /api/v1/dashboard registered; GET /api/agent/planning/view?include= registered; GET /api/analytics/overview-bundle registered
  status: pending
- id: SC-5.3
  description: services/queries/dashboard.ts — useDashboardBundleQuery with resilience for missing fields
  status: pending
- id: SC-5.4
  description: Dashboard cold load 1 network request (fetch-spy confirmed)
  status: pending
- id: SC-5.5
  description: Planning cold load 1 network request
  status: pending
- id: SC-5.6
  description: Resilience ACs — missing taskCounts/sessions handled gracefully
  status: pending
- id: SC-5.7
  description: task-completion-validator sign-off
  status: pending
files_modified:
- backend/application/services/agent_queries/dashboard.py
- backend/routers/client_v1.py
- backend/application/services/agent_queries/planning.py
- backend/routers/agent.py
- backend/routers/analytics.py
- backend/models.py
- services/queries/dashboard.ts
- services/queries/planning.ts
- components/Dashboard.tsx
- components/Planning/PlanningHomePage.tsx
---

# CCDash Frontend Data Layer Refactor - Phase 5: Backend Fat-Read Bundles

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-5-progress.md \
  -t T5-001 -s completed
```

---

## Objective

Three bundle endpoints reduce above-fold request count to ≤1 per view. P5a backend starts after P0 (parallel to P2/P3/P4). P5b FE wiring starts after P4 + P5a endpoint ships. Backend logic lands in `agent_queries/` first (transport-neutral pattern), then wired into routers. OQ-5 resolution: compose existing cached `agent_queries` reads — no new methods needed.
