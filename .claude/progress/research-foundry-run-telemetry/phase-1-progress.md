---
type: progress
schema_version: 2
doc_type: progress
prd: research-foundry-run-telemetry
feature_slug: research-foundry-run-telemetry
phase: 1
status: pending
created: 2026-07-21
updated: 2026-07-21
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
commit_refs: []
pr_refs: []

owners: ["data-layer-expert", "python-backend-engineer", "task-completion-validator"]
contributors: []

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 8
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

tasks:
  - id: "T1-001"
    name: "rf_events dual-DDL raw table"
    description: "New table in both backend/db/sqlite_migrations.py and backend/db/postgres_migrations.py, registered in get_sqlite_migration_tables()/get_postgres_migration_tables(), columns cover the full ccdash_event shape (event_id PK, run_id, rf raw ids, cost/quality metrics, optional fields nullable)."
    status: pending
    assigned_to: ["data-layer-expert"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "2 pts"
    dependencies: []

  - id: "T1-002"
    name: "Migration governance + parity/direct-count test (ADR-007 exit gate)"
    description: "Add rf_events to COLUMN_PARITY_DRIFT_ALLOWLIST entry set correctly; write the direct-count assertion test (insert N rows, assert SELECT COUNT(*) == N) per ADR-007."
    status: pending
    assigned_to: ["data-layer-expert"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1 pt"
    dependencies: ["T1-001"]
    ac_refs: ["AC-2"]

  - id: "T1-003"
    name: "POST /api/v1/ingest/rf-events endpoint"
    description: "New route in backend/routers/ingest.py (existing ingest_router), Pydantic models in backend/application/models/ingest.py, service in backend/application/services/ingest/rf_events_ingest.py; reuses WorkspaceTokenAuthBackend; accepts NDJSON or single JSON; runs the Layer 1 redaction scan (FR-14) before persistence."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "2 pts"
    dependencies: ["T1-001"]

  - id: "T1-004"
    name: "Idempotent cursor enqueue + dead-letter reuse"
    description: "New source_id='rf' row in ingest_cursors; wire the existing dead-letter queue for permanently-failed events; all writes wrapped in retry_on_locked."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1 pt"
    dependencies: ["T1-003"]

  - id: "T1-005"
    name: "Ingest idempotency regression test"
    description: "Test: POST the same event_id twice -> exactly one rf_events row; POST with missing optional fields (human_review, output.claim_ledger_created, etc.) -> row persists with those columns null, never a 422."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1 pt"
    dependencies: ["T1-002", "T1-004"]
    ac_refs: ["AC-1"]

  - id: "T1-006"
    name: "Feature flag CCDASH_RF_TELEMETRY_ENABLED"
    description: "Gate the ingest route behind the flag (default true, fail-open); disabling 404s the route with zero effect on any other surface."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T1-003"]

  - id: "T1-007"
    name: "Capability advert + ingest_sources[] health entry"
    description: "GET /api/v1/capabilities advertises research-runs:* (backend/routers/client_v1.py); /api/health/detail -> ingest_sources[] registers an rf entry with the existing freshness-threshold logic (backend/application/services/agent_queries/ingest_sources.py)."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T1-004"]
    ac_refs: ["AC-5"]

  - id: "T1-008"
    name: "Phase 1 completion review"
    description: "task-completion-validator verifies all Phase 1 ACs (AC-1, AC-2 partial, AC-5) are genuinely met, not superficially — re-run T1-005 and T1-002's tests independently."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T1-001", "T1-002", "T1-003", "T1-004", "T1-005", "T1-006", "T1-007"]
    ac_refs: ["AC-1", "AC-2", "AC-5"]

parallelization:
  batch_1: ["T1-001"]
  batch_2: ["T1-002", "T1-003"]
  batch_3: ["T1-004", "T1-006"]
  batch_4: ["T1-005", "T1-007"]
  batch_5: ["T1-008"]
  critical_path: ["T1-001", "T1-003", "T1-004", "T1-005", "T1-008"]

blockers: []
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
