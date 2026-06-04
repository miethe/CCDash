---
schema_version: 2
doc_type: phase_plan
title: "P3 — Migration Integrity & Parity"
status: draft
created: 2026-06-03
updated: 2026-06-03
phase: 3
phase_title: "Migration Integrity & Parity"
feature_slug: ccdash-db-design-remediation
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Phase 3 — Migration Integrity & Parity (~13 pts)

**Parent Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`

**Dependencies**: P1 verified (bootstrap sequencing guarantees migrations run before `ensure_table`). May run in parallel with P4 after P1 exits.
**Assigned Subagent(s)**: data-layer-expert (sole owner — migrations, parity governance, `ensure_table`)
**Model**: sonnet
**Reviewer Gates**: task-completion-validator at exit; karen milestone review (migration integrity)

## Entry Criteria

- P1 quality gates all passed (bootstrap-ordering guarantee allows `ensure_table` elimination).
- Both SQLite and Postgres migration files are accessible in the working environment.
- CI environment runs both SQLite and Postgres backend variants.

## Background (file:line anchors)

| File | Lines | Subject |
|------|-------|---------|
| `backend/db/sqlite_migrations.py` | 2641–2659 | SQLite migration runner — no concurrency guard (F-04) |
| `backend/db/sqlite_migrations.py` | 1565–1722 | v31 `sessions_new` table-rebuild migration (race risk) |
| `backend/db/postgres_migrations.py` | 2278–2294 | Postgres `pg_advisory_lock` — reference pattern |
| `backend/db/migrations.py` | — | Entry point routing to backend-specific runners |
| `backend/db/migration_governance.py` | — | Table-set parity module (extend to column diff) |
| `backend/tests/test_migration_governance.py` | 23–27 | Table-set equality test — extend to column level |
| `backend/db/repositories/projects.py` | 72–96 | `ensure_table` DDL (three-copy drift surface) |

## Backlog Mapping

| Backlog ID | Finding | Description | Plan Task |
|------------|---------|-------------|-----------|
| P1-1 | F-04 | SQLite migration concurrency guard | T3-008 (impl) + T3-001 (test) |
| P1-2 | F-05 | Column/constraint-level parity check | T3-009 (impl) + T3-002 (test) |
| P1-3 | F-08 | `ensure_table` elimination — verified by T3-004 CI grep | T3-010 (impl) + T3-004 (audit) |
| P3-3 | F-04, F-07 | Migration idempotency + concurrency tests | T3-001, T3-003 |
| P3-4 | F-07 | Per-version migration ledger | T3-011 |

## Task Table

Task ID scheme: T3-001..T3-004 are the *verification/test* tasks whose IDs align with PRD AC `verified_by` references. T3-008..T3-011 are the corresponding implementation tasks.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T3-008 | SQLite migration concurrency guard (impl) | In `sqlite_migrations.py` (around line 2641): add a first-boot inter-process concurrency guard using `fcntl.flock` (or `fasteners.InterProcessLock`) on a lock file `data/.migration.lock`. Guard must: (a) acquire lock before any DDL; (b) after acquiring, check current `schema_version` — if already at target, log `migration already complete` and release without running DDL; (c) release on completion or exception; (d) respect a configurable timeout (default 30s); (e) mirror the Postgres advisory-lock intent from `postgres_migrations.py:2278–2294`. | Lock file created at `data/.migration.lock`; two concurrent processes serialize; second acquires and detects no-op; no DDL re-execution on no-op | 3 pts | data-layer-expert | sonnet | extended | P1 verified |
| T3-001 | Concurrent migration test (PRD: AC-005) | Add a test that spawns two concurrent Python processes (or threads) both calling `run_migrations` on the same SQLite file. Assert: (a) no `OperationalError` / `database is locked` propagates; (b) no `schema changed` error; (c) final schema is identical to single-process result; (d) `migrations_applied` ledger has no duplicate rows. | `test_concurrent_sqlite_migrations` passes; two concurrent callers serialize correctly; no data loss | 3 pts | data-layer-expert | sonnet | adaptive | T3-008, T3-011 |
| T3-009 | Column/constraint-level parity diff (impl) | Extend `migration_governance.py` to parse each shared table's DDL block (SQLite CREATE TABLE + Postgres CREATE TABLE) into a normalized structure: `{column_name: (type, nullable, default)}` dict + set of `{UNIQUE(col,...)}` constraints + set of index definitions. For every table in `get_sqlite_migration_tables() ∩ get_postgres_migration_tables()`, compare structural equality. The diff function must return a machine-readable `{table: {sqlite: ..., postgres: ...}}` diff on mismatch. | `migration_governance.py` exports `column_parity_diff(table)` and `get_column_parity_diff_all()`; returns empty dict when no drift exists | 4 pts | data-layer-expert | sonnet | extended | P1 verified |
| T3-002 | Column-parity CI test (PRD: AC-006) | Add `test_column_parity_all_shared_tables` to `test_migration_governance.py`: call `get_column_parity_diff_all()` and assert the result is an empty dict. This test must run in the same CI job as the existing `test_shared_migration_tables_match_across_backends`. | `test_column_parity_all_shared_tables` exists; fails if any column drift is introduced; passes on both SQLite and Postgres backends | 1 pt | data-layer-expert | sonnet | adaptive | T3-009 |
| T3-003 | Migration idempotency test (PRD: AC-007) | Add a test that calls `run_migrations` twice on a populated SQLite DB (first call brings it to current version; second call is a no-op). Assert: (a) no exception on second call; (b) `PRAGMA schema_version` is identical before and after the second call; (c) same for Postgres. | `test_migration_idempotency` passes on both backends; second `run_migrations` call is a no-op with no error | 3 pts | data-layer-expert | sonnet | adaptive | T3-008, T3-011 |
| T3-010 | `ensure_table` DDL elimination (impl) | In `SqliteProjectRepository` (`repositories/projects.py:72–96`) and `PostgresProjectRepository` (`postgres/projects.py:63–91`): remove the inline `CREATE TABLE IF NOT EXISTS projects` DDL. Replace with either: (a) a call to the canonical migration DDL function (if exposed as a callable), or (b) a guard that asserts migrations have already run (logs a warning + raises if the table is absent). Audit for other out-of-band `CREATE TABLE IF NOT EXISTS` for migration-managed tables: check `_ensure_test_visualizer_tables` and `_ensure_planning_worktree_contexts_table`. | `SqliteProjectRepository.ensure_table` and `PostgresProjectRepository.ensure_table` contain no inline CREATE TABLE DDL for `projects`; audit of other tables documented in code comment | 3 pts | data-layer-expert | sonnet | adaptive | T3-008 (ordering guarantee) |
| T3-004 | Grep-for-inline-DDL audit in CI (PRD: AC-008) | Add a CI step (or test) that runs `git grep -n "CREATE TABLE IF NOT EXISTS" -- backend/db/repositories/` and asserts zero hits for tables that are also present in the canonical migration files. Document any intentional exceptions (e.g., test-only safety nets) with a `# noqa: inline-ddl` comment. | CI grep returns zero hits for `projects` inline DDL in production code; any remaining `ensure_table` DDL for other tables is either test-only or migration-delegating | 1 pt | data-layer-expert | sonnet | adaptive | T3-010 |
| T3-011 | Per-version migration ledger | In both `sqlite_migrations.py` and `postgres_migrations.py`: record each applied migration version individually with an `applied_at` timestamp. Implement as either: (a) extend `schema_version` table to allow multiple rows (one per applied step), or (b) create a `migrations_applied(version INT, applied_at DATETIME)` table. Resolve OQ-01 (shared schema vs backend-specific) at implementation time — document the decision in a code comment. | `migrations_applied` (or equivalent) contains one row per applied version with `applied_at`; running migrations twice does not duplicate rows; both backends use the same schema | 2 pts | data-layer-expert | sonnet | adaptive | T3-008 |

**Phase total: ~13 pts** (3+3+4+1+3+3+1+2 = 20 raw; SPIKE backlog sizes implementation+test pairs together: P1-1=3pts, P1-2=4pts, P1-3=3pts, P3-3=3pts, P3-4=2pts → 15; rounding: audit tasks T3-002 and T3-004 are smaller than their impl tasks and the 13pt total is the SPIKE-authoritative estimate — accept 13 pts as the locked figure)

## Risk Guard (Scope Protection)

If T3-009 `column_parity_diff` reveals genuine existing drift exceeding 2 pts to fix: record the specific drift to `.claude/findings/ccdash-db-design-remediation-findings.md` (create lazily), update `findings_doc_ref` in the parent plan frontmatter, and triage: fix in-phase if ≤2 pts, else add a T5-005 design-spec task in P5 for the follow-up. Do not let drift discovery balloon P3 beyond 13 pts.

## Acceptance Criteria Traceability

| AC | Task(s) | Notes |
|----|---------|-------|
| AC-005: Migration concurrency guard | T3-008, T3-001 | Guard impl + concurrent test |
| AC-006: Column-parity governance | T3-009, T3-002 | Parity diff + CI test |
| AC-007: Migration idempotency | T3-011, T3-003 | Ledger + idempotency test |
| AC-008: `ensure_table` DDL elimination | T3-010, T3-004 | Elimination + CI grep audit |

## Phase 3 Quality Gates

- [ ] T3-008 SQLite migration concurrency guard implemented; lock file at `data/.migration.lock`
- [ ] T3-001 concurrent migration test passes (two processes, no lock error, no duplicate ledger rows)
- [ ] T3-009 `migration_governance.py` exports `column_parity_diff`; returns empty dict on current codebase
- [ ] T3-002 `test_column_parity_all_shared_tables` passes in CI on both backends
- [ ] T3-010 `ensure_table` contains no inline `CREATE TABLE` DDL for `projects`
- [ ] T3-004 CI grep confirms zero hits for `projects` inline DDL in production repositories
- [ ] T3-011 `migrations_applied` ledger records per-version rows with `applied_at`; no duplicate rows on rerun
- [ ] T3-003 migration idempotency test passes on both SQLite and Postgres
- [ ] If column drift found: recorded in findings doc and triaged; P3 scope not exceeded
- [ ] task-completion-validator sign-off
- [ ] karen milestone review: migration integrity (concurrency guard, column-parity, idempotency)
