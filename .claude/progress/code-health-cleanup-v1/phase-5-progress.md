---
type: progress
prd: code-health-cleanup-v1
phase: 5
status: completed
progress: 100
tasks:
  - id: CH-501
    title: Promote feature list query fields to columns
    status: completed
    assigned_to:
      - orchestrator
    dependencies: []
    model: gpt-5
  - id: CH-502
    title: Backfill feature columns and add query indexes
    status: completed
    assigned_to:
      - orchestrator
    dependencies:
      - CH-501
    model: gpt-5
  - id: CH-503
    title: Add focused repository and list-query regression tests
    status: completed
    assigned_to:
      - orchestrator
    dependencies:
      - CH-501
      - CH-502
    model: gpt-5
parallelization:
  batch_1:
    - CH-501
    - CH-502
  batch_2:
    - CH-503
---

# Phase 5 Progress

Feature list filtering now reads from promoted columns instead of JSON-extract fallbacks.

## Completion Notes

- Added `tags_json`, `deferred_tasks`, `planned_at`, and `started_at` to the feature schema in SQLite and Postgres.
- Added migration backfill so legacy rows are populated from `data_json` on upgrade.
- Updated SQLite and Postgres feature repositories to populate and query the new columns.
- Added feature-list indexes for the promoted date and deferred-task predicates, plus a category lower-case index and a Postgres GIN index for tag containment.
- Added focused regression coverage for upsert column population, migration backfill, and query-builder behavior.
- Validation passed: `backend/.venv/bin/python -m pytest backend/tests/test_features_repository.py backend/tests/test_feature_list_query.py backend/tests/test_sqlite_migrations.py -q` -> 24 passed, 1 skipped.

## Remaining Blocker

- `latest_activity` and `session_count` still fall back to `updated_at` in the feature list sort mapping. Those values are derived from rollup/session data, so promoting them safely needs a separate rollup-backed column or join change.
