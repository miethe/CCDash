---
schema_version: 2
doc_type: progress
phase: 1
phase_title: Postgres in-place upgrade-path fix (W3)
feature_slug: ccdash-runtime-deploy-remediation
status: completed
created: 2026-06-12
updated: '2026-06-13'
overall_progress: 100
completion_estimate: "100%"
runtime_smoke: skipped  # docker daemon unavailable; seeded-pg smoke script authored + unit-test guard green (17 passed)
parallelization:
  strategy: batch-parallel
  batch_1:
  - T1-001
  batch_2:
  - T1-002
  - T1-004
  batch_3:
  - T1-003
  - T1-005
  - T1-006
  batch_4:
  - T1-007
---

# Phase 1 Progress — Postgres in-place upgrade-path fix (W3)

## Objective

Fix the `_TABLES` migration ordering defect: `CREATE INDEX` statements referencing
`sessions.project_id` execute before the v30 `ALTER TABLE` that adds that column, breaking
all Postgres in-place upgrades on pre-v35 databases. Add `pg-seed-v29.sql` fixture and
seeded-PG smoke script. karen milestone at exit (migration risk gate).

---

## Task Table

```yaml
tasks:
  - id: T1-001
    name: "Audit _TABLES indexes"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Identify every CREATE INDEX stmt in _TABLES (~lines 223-237) that references
      sessions.project_id. Document exhaustive list in task notes. Answers OQ-4
      and sets scope for T1-002.

  - id: T1-002
    name: "Migration reorder"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: extended
    description: >
      Move identified CREATE INDEX IF NOT EXISTS stmts out of _TABLES; add as
      await db.execute() calls inside if current_version < 30: block, placed AFTER
      _migrate_v30_detail_tables_project_id() returns. IF NOT EXISTS throughout.
      No DROP; no ALTER COLUMN TYPE. Verified by T1-005 + T1-006.

  - id: T1-003
    name: "Verify fresh-DB path"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Create fresh PG DB from scratch; confirm _TABLES + v30 block jointly produce
      complete v35 schema with no UndefinedColumnError. Fresh DB reaches
      SCHEMA_VERSION=35 cleanly.

  - id: T1-004
    name: "pg-seed-v29.sql fixture"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Create deploy/runtime/fixtures/pg-seed-v29.sql: minimal DDL snapshot with
      schema_version.version=29 and pre-v30 sessions table (no project_id column).
      Header comment: "TEST FIXTURE ONLY — not production DDL".

  - id: T1-005
    name: "Seeded-PG smoke script"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add docker:hosted:smoke:seeded-pg to package.json: boot PG with pg-seed-v29.sql
      init-script, start api, wait 30s, call /api/health/ready, assert
      migrationStatus=="applied", grep PG logs for UndefinedColumnError (must be absent),
      tear down. Re-run must exit 0 (idempotency).

  - id: T1-006
    name: "Upgrade path unit test"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add backend/tests/test_postgres_migrations_upgrade.py: mock current_version=29,
      run _run_migrations_inner, assert no exception and final version=35.
      Named-module only.

  - id: T1-007
    name: "Deployment quickstart rollback section"
    status: pending
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Add "Rollback plan" section to docs/guides/containerized-deployment-quickstart.md
      noting pre-migration pg_dump as recommended operator backup before in-place upgrades.
      Merge after T1-005 passes.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| AC-T1-002 | Identified indexes absent from `_TABLES`; present in `<30` block post-v30 ALTER; `IF NOT EXISTS` on all; advisory lock released on failure | `docker:hosted:smoke:seeded-pg` (T1-005), `test_postgres_migrations_upgrade.py` (T1-006) | pending |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → `Task(data-layer-expert, "T1-001: Audit all CREATE INDEX stmts in _TABLES referencing sessions.project_id in backend/db/postgres_migrations.py")`
- **batch_2** → `Task(data-layer-expert, "T1-002: Migration reorder — move project_id indexes into v30 block with IF NOT EXISTS")` + `Task(data-layer-expert, "T1-004: Create deploy/runtime/fixtures/pg-seed-v29.sql fixture")`
- **batch_3** → `Task(data-layer-expert, "T1-003: Fresh-DB path verification")` + `Task(data-layer-expert, "T1-005: docker:hosted:smoke:seeded-pg script in package.json")` + `Task(data-layer-expert, "T1-006: test_postgres_migrations_upgrade.py — mock v29 upgrade test")`
- **batch_4** → `Task(documentation-writer, "T1-007: Rollback plan section in docs/guides/containerized-deployment-quickstart.md")`

**Quality gates before phase close:**
- `npm run docker:hosted:smoke:seeded-pg` exits 0; re-run exits 0 (idempotency)
- `pytest backend/tests/test_postgres_migrations_upgrade.py` passes (named module)
- `UndefinedColumnError` absent from PG container logs
- karen milestone review completed

**Key files:** `backend/db/postgres_migrations.py`, `deploy/runtime/fixtures/pg-seed-v29.sql`, `package.json`, `docs/guides/containerized-deployment-quickstart.md`
