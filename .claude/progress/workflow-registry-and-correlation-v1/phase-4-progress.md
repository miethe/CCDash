---
type: progress
schema_version: 2
doc_type: progress
prd: workflow-registry-and-correlation-v1
feature_slug: workflow-registry-and-correlation-v1
prd_ref: /docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
phase: 4
title: Router and API surface
status: completed
started: '2026-03-14'
completed: null
commit_refs:
- bf74591
- e26698c
- dee95b1
pr_refs: []
overall_progress: 85
completion_estimate: at-risk
total_tasks: 3
completed_tasks: 2
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 1
owners:
- python-backend-engineer
contributors:
- codex
tasks:
- id: API-4.1
  description: Add workflow registry list and detail endpoints to the analytics router
    with stable query parameters.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 3h
  priority: high
- id: API-4.2
  description: Preserve workflow-analytics disabled-state behavior and return a documented
    not-found response for missing registry details.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - API-4.1
  estimated_effort: 1h
  priority: high
- id: API-4.3
  description: Add analytics router tests covering list, detail, and disabled-state
    behavior for the workflow registry API.
  status: in_progress
  assigned_to:
  - python-backend-engineer
  dependencies:
  - API-4.1
  - API-4.2
  estimated_effort: 2h
  priority: high
parallelization:
  batch_1:
  - API-4.1
  batch_2:
  - API-4.2
  batch_3:
  - API-4.3
  critical_path:
  - API-4.1
  - API-4.2
  - API-4.3
  estimated_total_time: 6h
blockers:
- id: VAL-001
  title: Existing analytics router import cycle blocks unittest execution
  severity: medium
  blocking:
  - API-4.3
  resolution: Resolve the circular import between backend/runtime/bootstrap.py and backend/routers/analytics.py, then rerun backend.tests.test_analytics_router.AnalyticsRouterTests.
  created: '2026-03-14'
success_criteria:
- The analytics API exposes workflow registry list and detail endpoints without pushing
  correlation logic into the frontend.
- Query parameters for search and correlation-state filtering are stable and validated
  at the router boundary.
- Workflow analytics feature flags still gate the new endpoints consistently with
  existing analytics routes.
- Router tests cover happy-path, disabled-state, and missing-detail behavior.
files_modified:
- .claude/progress/workflow-registry-and-correlation-v1/phase-4-progress.md
- backend/routers/analytics.py
- backend/tests/test_analytics_router.py
progress: 85
updated: '2026-03-14'
---

# workflow-registry-and-correlation-v1 - Phase 4

## Objective

Expose the workflow registry service through stable analytics endpoints so the planned catalog/detail UI can load page-ready data without reimplementing workflow correlation rules.

## Implementation Notes

### Architectural Decisions

- Reuse `backend/services/workflow_registry.py` as the only source of registry aggregation logic.
- Keep the API under `backend/routers/analytics.py` to align with existing workflow-effectiveness and failure-pattern surfaces.
- Gate the endpoints with the existing workflow analytics feature-flag helper for consistent disabled behavior.

### Patterns and Best Practices

- Match existing FastAPI `Query(...)` alias patterns used across the analytics router.
- Return Pydantic response models from `backend/models.py` rather than untyped dictionaries.
- Cover direct route calls with unit tests that patch the active project, DB connection, and service entry points.

### Known Gotchas

- The implementation plan and PRD are currently untracked in git, so commits should stay scoped to code and progress artifacts unless explicitly requested otherwise.
- Registry detail responses should fail fast with `404` for unknown IDs instead of returning partial placeholders.

## Completion Notes

- Added `/api/analytics/workflow-registry` for catalog loading with validated `correlationState`, pagination, and search passthrough.
- Added `/api/analytics/workflow-registry/detail` with `registryId` query lookup so registry IDs containing `/` remain addressable.
- Added router coverage for list, detail, not-found, disabled-state, and query-contract behavior in `backend/tests/test_analytics_router.py`.
- Verified `backend/tests/test_workflow_registry.py` passes under `unittest` and verified the modified router/test modules compile.
- Phase remains in progress until the pre-existing analytics router import cycle is resolved and the router test module can run end-to-end.
