---
type: progress
schema_version: 2
doc_type: progress
prd: research-foundry-run-telemetry
feature_slug: research-foundry-run-telemetry
phase: 1
status: completed
created: '2026-07-21'
updated: '2026-07-21'
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
commit_refs:
- 575ccba
- 3628b12
- 2abe6ee
- a27e656
- f2e7166
- c12ca09
pr_refs: []
owners:
- data-layer-expert
- python-backend-engineer
- task-completion-validator
contributors: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 8
completed_tasks: 8
in_progress_tasks: 0
blocked_tasks: 0
tasks:
- id: T1-001
  name: rf_events dual-DDL raw table
  description: New table in both backend/db/sqlite_migrations.py and backend/db/postgres_migrations.py,
    registered in get_sqlite_migration_tables()/get_postgres_migration_tables(), columns
    cover the full ccdash_event shape (event_id PK, run_id, rf raw ids, cost/quality
    metrics, optional fields nullable).
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  effort: adaptive
  estimate: 2 pts
  dependencies: []
  started: 2026-07-21T18:20Z
  completed: 2026-07-21T18:39Z
  evidence:
  - commit: 575ccba
  - test: backend/tests/test_rf_events_migration_governance.py
  verified_by:
  - T1-008
- id: T1-002
  name: Migration governance + parity/direct-count test (ADR-007 exit gate)
  description: Add rf_events to COLUMN_PARITY_DRIFT_ALLOWLIST entry set correctly;
    write the direct-count assertion test (insert N rows, assert SELECT COUNT(*) ==
    N) per ADR-007.
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  effort: adaptive
  estimate: 1 pt
  dependencies:
  - T1-001
  ac_refs:
  - AC-2
  started: 2026-07-21T18:40Z
  completed: 2026-07-21T18:46Z
  evidence:
  - commit: 3628b12
  - test: backend/tests/test_rf_events_migration_governance.py
  verified_by:
  - T1-008
- id: T1-003
  name: POST /api/v1/ingest/rf-events endpoint
  description: New route in backend/routers/ingest.py (existing ingest_router), Pydantic
    models in backend/application/models/ingest.py, service in backend/application/services/ingest/rf_events_ingest.py;
    reuses WorkspaceTokenAuthBackend; accepts NDJSON or single JSON; runs the Layer
    1 redaction scan (FR-14) before persistence.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 2 pts
  dependencies:
  - T1-001
  started: 2026-07-21T18:25Z
  completed: 2026-07-21T18:39Z
  evidence:
  - commit: 575ccba
  - test: backend/tests/test_rf_events_ingest_endpoint.py
  verified_by:
  - T1-008
- id: T1-004
  name: Idempotent cursor enqueue + dead-letter reuse
  description: New source_id='rf' row in ingest_cursors; wire the existing dead-letter
    queue for permanently-failed events; all writes wrapped in retry_on_locked.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 1 pt
  dependencies:
  - T1-003
  started: 2026-07-21T18:47Z
  completed: 2026-07-21T18:55Z
  evidence:
  - commit: 2abe6ee
  - test: backend/tests/test_rf_events_ingest_idempotency.py
  verified_by:
  - T1-008
- id: T1-005
  name: Ingest idempotency regression test
  description: 'Test: POST the same event_id twice -> exactly one rf_events row; POST
    with missing optional fields (human_review, output.claim_ledger_created, etc.)
    -> row persists with those columns null, never a 422.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 1 pt
  dependencies:
  - T1-002
  - T1-004
  ac_refs:
  - AC-1
  started: 2026-07-21T00:00Z
  completed: 2026-07-21T01:00Z
  evidence:
  - test: backend/tests/test_rf_events_ingest_idempotency.py
  - review: T1-008 re-ran test_rf_events_ingest_idempotency.py independently
  verified_by:
  - T1-008
- id: T1-006
  name: Feature flag CCDASH_RF_TELEMETRY_ENABLED
  description: Gate the ingest route behind the flag (default true, fail-open); disabling
    404s the route with zero effect on any other surface.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T1-003
  started: 2026-07-21T00:00Z
  completed: 2026-07-21T00:30Z
  evidence:
  - test: backend/tests/test_rf_events_feature_flag.py
  - review: T1-008 re-ran test_rf_events_feature_flag.py independently
  verified_by:
  - T1-008
- id: T1-007
  name: Capability advert + ingest_sources[] health entry
  description: GET /api/v1/capabilities advertises research-runs:* (backend/routers/client_v1.py);
    /api/health/detail -> ingest_sources[] registers an rf entry with the existing
    freshness-threshold logic (backend/application/services/agent_queries/ingest_sources.py).
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T1-004
  ac_refs:
  - AC-5
  started: 2026-07-21T00:00Z
  completed: 2026-07-21T01:00Z
  evidence:
  - test: backend/tests/test_rf_ingest_sources_health.py
  - test: backend/tests/test_external_api_contract.py::TestCapabilityContract::test_capabilities_includes_research_runs
  - review: T1-008 re-ran test_rf_ingest_sources_health.py and test_external_api_contract.py
      independently
  verified_by:
  - T1-008
- id: T1-008
  name: Phase 1 completion review
  description: "task-completion-validator verifies all Phase 1 ACs (AC-1, AC-2 partial,\
    \ AC-5) are genuinely met, not superficially \u2014 re-run T1-005 and T1-002's\
    \ tests independently."
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  - T1-005
  - T1-006
  - T1-007
  ac_refs:
  - AC-1
  - AC-2
  - AC-5
  started: 2026-07-21T19:00Z
  completed: 2026-07-21T19:20Z
  evidence:
  - test: backend/tests/test_rf_events_ingest_endpoint.py
  - test: backend/tests/test_rf_events_migration_governance.py
  - test: backend/tests/test_rf_events_feature_flag.py
  - test: backend/tests/test_rf_events_ingest_idempotency.py
  - test: backend/tests/test_rf_ingest_sources_health.py
  - test: backend/tests/test_external_api_contract.py
  - note: 77 passed, 1 skipped (live-PG only) across the full rf_events + ingest_sources
      + capability-contract suite; independently reproduced the pre-existing unrelated
      test_migration_governance.py::test_column_parity_all_shared_tables workspace_id-drift
      failure and confirmed rf_events is not implicated
  - note: "self-attestation \u2014 T1-008 is the phase completion review itself"
  verified_by:
  - T1-008
parallelization:
  batch_1:
  - T1-001
  batch_2:
  - T1-002
  - T1-003
  batch_3:
  - T1-004
  - T1-006
  batch_4:
  - T1-005
  - T1-007
  batch_5:
  - T1-008
  critical_path:
  - T1-001
  - T1-003
  - T1-004
  - T1-005
  - T1-008
blockers: []
progress: 100
---

# research-foundry-run-telemetry - Phase 1: Ingest transport + rf_events persistence

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-1-progress.md \
  -t T1-001 -s completed \
  --started 2026-07-21T00:00Z --completed 2026-07-21T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-1-progress.md \
  --updates "T1-001:completed,T1-002:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-1-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-1-progress.md
```
