---
schema_version: 2
doc_type: phase_plan
title: "P1 \u2014 Registry Correctness & Authority"
status: completed
created: 2026-06-03
updated: '2026-06-03'
phase: 1
phase_title: Registry Correctness & Authority
feature_slug: ccdash-db-design-remediation
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Phase 1 — Registry Correctness & Authority (~11 pts)

**Parent Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`

**Dependencies**: ADR-006 ratified (done 2026-06-03)
**Assigned Subagent(s)**: data-layer-expert (primary), python-backend-engineer (secondary)
**Model**: sonnet (implementation); Opus review of ADR-006 conformance at phase exit
**Reviewer Gates**: task-completion-validator at exit; karen milestone review (ADR-006 conformance)

## Entry Criteria

- ADR-006 ratified (DB-authoritative Option B). Status: satisfied 2026-06-03.
- No destructive DB operations have been performed (P4 not started).
- Live `projects` table has 5 rows (manual fix 2026-06-03); P1 must not drop or replace them.

## Background (file:line anchors)

| File | Lines | Subject |
|------|-------|---------|
| `backend/project_manager.py` | 447–460 | `_flush_snapshot_to_db` — swallow site (root cause of F-01) |
| `backend/project_manager.py` | 658, 663 | Dual-manager instantiation (F-02) |
| `backend/db/repositories/projects.py` | 42–49 | Sync connection, no `PRAGMA busy_timeout` |
| `backend/db/repositories/projects.py` | 72–96 | `ensure_table` DDL (addressed further in P3) |
| `backend/runtime/container.py` | 1203 | Registry lazy-bootstrap call site (sequencing) |
| `backend/runtime_ports.py` | 127–140 | Manager selection logic / JSON override |
| `backend/db/repositories/execution.py` | 33–69 | `_commit_with_retry` / `_is_locked` (reference pattern) |
| `backend/tests/test_db_project_registry.py` | 107–145 | Passes through F-01 (two-instance read) |
| `backend/config.py` | 57 | Dead `DB_PATH` default `.ccdash.db` (F-10) |

## Task Table

**Column conventions**: `Estimate` = story points. `Effort` = model reasoning budget (`adaptive` or `extended` for Claude). Never put points in `Effort`.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T1-001 | Fail-loud bootstrap | In `_flush_snapshot_to_db` (`project_manager.py:447–460`): on exception, do NOT set `_snapshot_loaded=True`; log ERROR with locked reason; return without success signal. On next `list_projects()` or `get_project()` call, the flush is retried. | Exception is not swallowed; `_snapshot_loaded` stays `False`; subsequent call retries the flush | 2 pts | data-layer-expert | sonnet | adaptive | None |
| T1-002 | Locked-retry on registry sync write | Apply the `execution.py:_commit_with_retry` pattern (local copy, pending P2 generalization) to `SqliteProjectRepository._flush_to_db`; add `PRAGMA busy_timeout = 30000` on the `_get_conn` path (`projects.py:42–49`) | Retry fires on a locked DB; `PRAGMA busy_timeout` present in connection setup; at most 3 retries with backoff | 2 pts | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-003 | Bootstrap sequencing | In `container.py` (around line 1203): move the registry bootstrap call to execute before the `SyncEngine` heavy-write window opens (or mark it lazy-on-first-request but ensure it cannot fire concurrently with the sync startup burst). | Cold-start timing: registry flush completes before sync engine begins its first `_replace_*` backfill commit; confirmed by log timestamp ordering in smoke test | 2 pts | python-backend-engineer | sonnet | extended | T1-001, T1-002 |
| T1-004 | Dual-manager collapse | Per ADR-006 Option B: (a) Remove the legacy `ProjectManager(...)` JSON-backed instantiation at `project_manager.py:658` from the runtime path or repurpose as a static `import_from_json(path)` helper; (b) Add `export_to_json(path)` to `DbProjectManager`; (c) Update `runtime_ports.py:127–140` so all production code resolves to the DB-backed manager. Grep all callers of the `manager=` override before retiring. | Single `DbProjectManager` instance at runtime; `import_from_json()` and `export_to_json()` callable; no production call site passes the JSON-backed manager as `manager=`; import/export round-trip preserves all fields | 3 pts | python-backend-engineer | sonnet | extended | T1-003 |
| T1-005 | Lock-injection test (F-01 reproducer) | In `backend/tests/test_db_project_registry.py`: add a test that holds a write-lock on the DB file via a second connection while `_flush_snapshot_to_db` executes; assert that an `Exception` is raised (or retry-then-success) — never a silent `True` return with no rows written. | Test `test_registry_flush_fail_loud` exists and fails without T1-001; passes with T1-001 applied | 2 pts | data-layer-expert | sonnet | adaptive | T1-001, T1-002 |
| T1-006 | Direct-count post-flush test | Add a test that: (1) calls `DbProjectManager._flush_snapshot_to_db`, (2) directly queries `SqliteProjectRepository.count()` (or `SELECT COUNT(*) FROM projects`), and (3) asserts the count matches the in-memory snapshot. No second `DbProjectManager` instance allowed (would re-bootstrap from JSON and mask the failure). | `test_registry_persistence_direct_count` exists; asserts `repo.count() == len(snapshot)`; fails if flush is a no-op | 2 pts | data-layer-expert | sonnet | adaptive | T1-001, T1-002 |
| T1-007 | Caller-grep audit | Grep all production call sites for `manager=` argument passing; document each in a code comment; remove or repurpose any that pass the JSON-backed manager in a non-test context. | No production code passes the JSON `ProjectManager` as `manager=`; test-only override paths are explicitly annotated | 1 pt | python-backend-engineer | sonnet | adaptive | T1-004 |
| T1-008 | Import/export round-trip test | Test that `import_from_json(projects.json)` populates the DB, and `export_to_json(out.json)` produces a file with identical project ids/names. Import must be additive (upsert-on-id, does not wipe existing rows). | Round-trip: 5 projects in → 5 out; existing DB rows not wiped by import | 1 pt | python-backend-engineer | sonnet | adaptive | T1-004 |
| T1-009 | Dead config.DB_PATH cleanup | Delete or consolidate the dead `config.DB_PATH` default at `config.py:57`. If deleting, ensure no reference to `config.DB_PATH` remains outside a comment. If consolidating, make `db/connection.py:25` derive from `config.DB_PATH`. | `config.DB_PATH = ".ccdash.db"` either removed or `connection.py` derives from it; no orphaned references; grep confirms | 1 pt | python-backend-engineer | sonnet | adaptive | None |
| T1-010 | P1 cold-start smoke (runtime-smoke) | Start a cold dev server (`npm run dev`), confirm `/api/projects` returns all 5 projects, confirm the `projects` DB table is non-empty via CLI (`backend/.venv/bin/ccdash project list`), confirm no startup regression in worker binding. | `GET /api/projects` → 5 projects; `SELECT COUNT(*) FROM projects` ≥ 5; worker starts and binds without error; no log-level ERROR related to registry on clean startup | 1 pt | python-backend-engineer | sonnet | adaptive | T1-001–T1-008 |

**Phase total: 11 pts**

## Acceptance Criteria Traceability

| AC | Task(s) | Notes |
|----|---------|-------|
| AC-001a: Rows survive cold restart | T1-006, T1-010 | Direct-count + smoke |
| AC-001b: Lock-injection proves fail-loud | T1-005 | F-01 reproducer |
| AC-002: Dual-manager collapse | T1-004, T1-007, T1-008 | Caller-grep + round-trip |

**R-P4 runtime-smoke task**: T1-010 — cold-start smoke referencing P1 target surfaces (`/api/projects`, projects DB table, worker binding). Required before phase exits.

## Phase 1 Quality Gates

- [ ] T1-005 `test_registry_flush_fail_loud` passes (lock-injection reproduces F-01, asserts fail-loud)
- [ ] T1-006 `test_registry_persistence_direct_count` passes (no two-instance workaround)
- [ ] T1-008 import/export round-trip test passes
- [ ] T1-010 cold-start smoke: `/api/projects` = 5 projects; `projects` table non-empty; worker binds
  - Scoped deviation (2026-06-03): "worker binds" applies only to enterprise/Postgres profiles — `worker` runtime is enterprise-only per `backend/runtime/storage_contract.py:153-170`; local SQLite runs jobs in-process via `InProcessJobScheduler`. Worker assertion recorded N/A by design for local dev smoke runs.
- [ ] T1-009 dead `config.DB_PATH` removed or consolidated (grep confirms)
- [ ] No startup regression: dev server starts without ERROR-level log related to registry on clean boot
- [ ] task-completion-validator sign-off
- [ ] karen milestone review: ADR-006 conformance (single DB-backed manager, import/export helpers, no silent flush)

## Exit Criteria

P1 is declared verified when all quality gates pass. P2 may proceed immediately after P1 verification. P3 and P4 may proceed in parallel after P1 exits (P4 additionally requires operator DB snapshot confirmation).
