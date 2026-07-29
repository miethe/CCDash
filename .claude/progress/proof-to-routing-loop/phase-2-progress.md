---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 2
title: "Data Layer"
status: pending
created: "2026-07-29"
updated: "2026-07-29"
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["data-layer-expert"]
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T2-001"
    description: "Design routing_rollup schema — grain key (project_id, source_skill_name, model)"
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: []
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"

  - id: "T2-002"
    description: "Dual DDL — CREATE TABLE in sqlite_migrations.py and postgres_migrations.py (v43)"
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["T2-001"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"

  - id: "T2-003"
    description: "Repository — backend/db/repositories/routing_rollup.py with upsert + reads"
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["T2-002"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"

  - id: "T2-004"
    description: "Parity allowlist + direct-count test — ADR-007 write-path validation"
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["T2-003"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T2-001"]
  batch_2: ["T2-002"]
  batch_3: ["T2-003"]
  batch_4: ["T2-004"]
  critical_path: ["T2-001", "T2-002", "T2-003", "T2-004"]
  estimated_total_time: "3h"

blockers: []

success_criteria: []

files_modified:
  - "backend/db/sqlite_migrations.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/migration_governance.py"
  - "backend/db/repositories/routing_rollup.py"
  - "backend/tests/test_routing_rollup_repo.py"

---

# Phase 2: Data Layer

**Total Tasks**: 4  
**Estimated Effort**: 3 points  
**Key Files**: Migration files (v43), `routing_rollup.py` repository, tests

## Objective

Create the `routing_rollup` table and repository. This is an additive-only schema change with a natural grain key of `(project_id, source_skill_name, model)`. Every column is persisted except derived fields (task_class, provider).

## Implementation Notes

### Architectural Decisions

- **Additive-only DDL**: No ALTER on existing tables, no backfill — this feature creates a brand new table from scratch
- **Natural key discipline**: `(project_id, source_skill_name, model)` is the PRIMARY KEY; `window_start`/`window_end` are ordinary columns updated in place on upsert
- **Dual-DDL parity by construction**: Uses identical literal types (TEXT, INTEGER, REAL) in both SQLite and PostgreSQL to avoid drift allowlist entries
- **ADR-006/007 discipline**: Every write path wrapped in `retry_on_locked`; direct-count assertion test validates idempotency

### Patterns and Best Practices

- Clones `aar_reviews` table structure exactly, including the shared ordered-columns contract pattern
- Uses same `_ensure_column` migration pattern for schema version bumping
- Bootstrap path (in `_TABLES`) + upgrade path (version-gated block) both present for fresh and upgraded databases

### Known Gotchas

- **Version-gate ordering**: New block must follow the v42 block, before any `_ensure_index` calls
- **`_TABLES` regex sensitivity**: `_CREATE_TABLE_RE` requires trailing `;` and specific shape — off-by-one breaks silently
- **Independent SQLite connections**: New test must issue `PRAGMA busy_timeout = 30000` immediately after connecting

### Development Setup

- Knowledge of SQLite/PostgreSQL DDL syntax and type normalization
- Familiarity with `column_parity_diff()` and `migration_governance.py` patterns
- Understanding of `retry_on_locked` pattern from ADR-007

## Completion Notes

*Fill in when phase is complete*

- Table creation verified on both backends
- Parity test green (zero unexpected allowlist entries)
- Direct-count assertion validates write-path idempotency
