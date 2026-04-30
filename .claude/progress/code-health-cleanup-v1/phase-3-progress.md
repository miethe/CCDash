---
type: progress
prd: code-health-cleanup-v1
phase: 3
status: completed
progress: 100
tasks:
  - id: CH-301
    title: analytics.py raw queries to repository
    status: completed
    assigned_to:
      - backend-repository-worker
    dependencies: []
    model: gpt-5.4
  - id: CH-302
    title: features.py telemetry insert to repository
    status: completed
    assigned_to:
      - backend-repository-worker
    dependencies: []
    model: gpt-5.4
  - id: CH-303
    title: test_visualizer.py raw queries to repository
    status: completed
    assigned_to:
      - backend-repository-worker
    dependencies: []
    model: gpt-5.4
  - id: CH-304
    title: test_health.py service raw SQL to repository
    status: completed
    assigned_to:
      - backend-repository-worker
    dependencies: []
    model: gpt-5.4
  - id: CH-305
    title: Repository tests
    status: completed
    assigned_to:
      - backend-repository-worker
    dependencies:
      - CH-301
      - CH-302
      - CH-303
      - CH-304
    model: gpt-5.4
parallelization:
  batch_1:
    - CH-301
    - CH-302
    - CH-303
    - CH-304
  batch_2:
    - CH-305
---

# Phase 3 Progress

Move router/service raw SQL behind repository methods while preserving response shapes.

## Completion Notes

- Moved targeted analytics artifact telemetry, Prometheus aggregate, entity-link, and thread stats reads into SQLite/Postgres analytics repositories.
- Moved feature execution telemetry inserts behind `AnalyticsRepository.record_execution_event`.
- Moved test visualizer domain pruning, definition lookup, and `test_metrics` summary reads behind repositories.
- Moved test-health commit-correlation lookup behind test-run repositories.
- Added focused repository migration coverage plus router regression updates.
- Guardrail passed: `rg -n "db\\.execute|self\\.db\\.execute|await db\\.execute" backend/routers/analytics.py backend/routers/test_visualizer.py backend/routers/features.py backend/services/test_health.py || true` returned no matches.
- Validation passed: `backend/.venv/bin/python -m compileall ...`.
- Validation passed: `backend/.venv/bin/python -m unittest backend.tests.test_phase3_repository_migration backend.tests.test_test_visualizer_router backend.tests.test_analytics_router` ran 44 tests.
