---
schema_version: 2
doc_type: phase_plan
title: "P2 \u2014 DB-Write Reliability & Observability Standard"
status: completed
created: 2026-06-03
updated: '2026-06-03'
phase: 2
phase_title: DB-Write Reliability & Observability Standard
feature_slug: ccdash-db-design-remediation
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Phase 2 — DB-Write Reliability & Observability Standard (~8 pts)

**Parent Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`

**Dependencies**: P1 verified (cold-start smoke passed, registry correctness confirmed)
**Assigned Subagent(s)**: python-backend-engineer (primary), data-layer-expert (secondary)
**Model**: sonnet
**Reviewer Gates**: task-completion-validator at exit; runtime-smoke on `/api/health/detail`

## Entry Criteria

- P1 quality gates all passed.
- P1 cold-start smoke confirmed (T1-010).
- `backend/db/repositories/execution.py:33–69` (`_commit_with_retry` / `_is_locked`) is the reference pattern to generalize.

## Background (file:line anchors)

| File | Lines | Subject |
|------|-------|---------|
| `backend/db/repositories/execution.py` | 33–69 | `_commit_with_retry`, `_is_locked` — generalization source |
| `backend/db/repositories/base.py` | — | Target location for shared helper |
| `backend/db/repositories/sessions.py` | — | Sync helpers that need the shared helper applied |
| `backend/runtime/bootstrap.py` | 124–191 | `_build_health_payload` — health endpoint construction |
| `backend/routers/api.py` | — | Health endpoint |
| `backend/observability/otel.py` | — | Prometheus/OTEL metrics module |
| `backend/config.py` | 1074–1102 | Retention config |
| `packages/ccdash_cli/` | — | `ccdash target check local` — consumer of health fields |

## Backlog Mapping

| Backlog ID | Finding | Description | Plan Task |
|------------|---------|-------------|-----------|
| P1-4 | F-06, ADR-007 | Shared locked-retry helper in `base.py`; apply to sync writers; audit `busy_timeout` | T2-001, T2-002 |
| P3-1 | F-09, ADR-007 | `/api/health/detail` new fields | T2-003 |
| P3-1 CLI smoke | F-09 | CLI `ccdash target check local` smoke for health fields | T2-004 |
| P3-1 resilience | F-09, ADR-007 | Consumer handles missing health fields | T2-005 |
| P3-2 | F-09, ADR-007 | `ccdash_db_write_failures_total` counter + injection test | T2-006 |

## Task Table

Task IDs align with PRD AC `verified_by` references. T2-003 = health-field integration test; T2-004 = CLI smoke; T2-005 = missing-field resilience test; T2-006 = counter-injection test.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T2-001 | Shared locked-retry helper | In `repositories/base.py`: extract a `retry_on_locked(fn, max_retries=3, backoff=0.5)` helper from `execution.py:_commit_with_retry` (`33–69`). The helper must: (a) call `fn()`, (b) on `OperationalError` with "database is locked", wait `backoff * attempt` seconds and retry up to `max_retries`, (c) on final failure, re-raise (never swallow), (d) increment `ccdash_db_write_failures_total{repo,reason}` at each retry site. | `retry_on_locked` in `repositories/base.py`; re-raises on exhaustion | 3 pts | python-backend-engineer | sonnet | adaptive | P1 verified |
| T2-002 | Apply helper to sync writers + busy_timeout audit | Apply `retry_on_locked` to: (a) `SqliteProjectRepository._flush_to_db` (replace the P1 local copy with the shared helper), (b) all identified sync helpers in `repositories/sessions.py`. Audit every independent `sqlite3.connect()` call in non-test, non-migration code for `PRAGMA busy_timeout`; add where missing. | Registry sync path uses shared helper; `sessions.py` sync helpers use shared helper or re-raise; every runtime `sqlite3.connect()` issues `PRAGMA busy_timeout = 30000`; grep confirms | 2 pts | data-layer-expert | sonnet | adaptive | T2-001 |
| T2-003 | Health fields integration test | In `_build_health_payload` (`bootstrap.py:124–191`): add `registry` (with `project_count: int|null`, `last_flush_status: "ok"|"failed"|"locked"|"unknown"`), `db` (with `size_bytes: int|null`, `freelist_bytes: int|null`, `backend: "sqlite"|"postgres"`), `retention` (with `last_run: ISO8601|null`, `enabled: bool`) to the health response. Add an integration test that starts the server and asserts all three top-level keys are present with the correct types. On any sub-call exception, field is `null` (never unhandled). | Response schema contains `registry`, `db`, `retention` keys; integration test asserts all fields non-null after warm start; `project_count` matches DB row count; `size_bytes` > 0 | 3 pts | python-backend-engineer | sonnet | extended | T2-001 |
| T2-004 | CLI `ccdash target check local` smoke (R-P4 runtime smoke) | After T2-003 health fields are wired: run `ccdash target check local` and confirm it exits 0 without a parse error on the new fields. Also: start a warm dev server, query `GET /api/health/detail`, assert `registry.project_count` ≥ 0, `db.size_bytes` > 0, `retention.enabled` is present. | `ccdash target check local` exits 0; no unhandled exception parsing the new fields; `/api/health/detail` returns all three new top-level keys; no ERROR in server logs during health check | 0.5 pts | python-backend-engineer | sonnet | adaptive | T2-003 |
| T2-005 | Missing-field resilience test | Add a test that mocks the `/api/health/detail` response with each of the three new top-level keys (`registry`, `db`, `retention`) individually omitted; assert the CLI `ccdash target check local` and any frontend health-display path each degrade gracefully (return `"unknown"`, not an exception or crash). | Test exercises missing `registry`, missing `db`, missing `retention`; CLI gracefully shows `unknown`; frontend (if applicable) does not throw | 1 pt | python-backend-engineer | sonnet | adaptive | T2-003 |
| T2-006 | Counter injection test | Define `ccdash_db_write_failures_total` (Counter, labels: `repo`, `reason`) in `observability/otel.py`. Add a test that: (a) injects a `database is locked` `OperationalError` into a write via `retry_on_locked`, (b) asserts the counter `ccdash_db_write_failures_total > 0` after the failure, (c) asserts the exception is re-raised (not swallowed). | Counter defined and exported; increments on injected failure; exception propagates; `repo` + `reason` labels populated | 1 pt | data-layer-expert | sonnet | adaptive | T2-001 |

**Phase total: ~8 pts** (3+2+3+0.5+1+1 = 10.5 pts; rounded to 8 pts per SPIKE backlog sizing: T2-001/T2-002 together are the P1-4 backlog item at 3 pts; T2-003/T2-004/T2-005 together are P3-1 at 3 pts; T2-006 is P3-2 at 2 pts = 8 pts total)

## Acceptance Criteria Traceability

| AC | Task(s) | Notes |
|----|---------|-------|
| AC-003a: New health fields present and correct | T2-003, T2-004 | Integration test + CLI smoke |
| AC-003b: Consumer handles missing health fields | T2-005 | Resilience test |
| AC-004: Prometheus counter increments on failure | T2-001, T2-006 | Counter definition + injection test |

**R-P4 runtime-smoke task (Plan Generator Rule R-P4)**: T2-004 is the runtime smoke task for this phase, referencing target surfaces `backend/runtime/bootstrap.py` (`_build_health_payload`) and `backend/routers/api.py` (health endpoint) and `packages/ccdash_cli/` (consumer). This task must pass before Phase 2 exits.

## Phase 2 Quality Gates

- [ ] T2-001 `retry_on_locked` in `repositories/base.py`; re-raises on exhaustion (never swallows)
- [ ] T2-002 all runtime `sqlite3.connect()` calls issue `PRAGMA busy_timeout = 30000` (grep confirms)
- [ ] T2-003 `/api/health/detail` returns `registry.project_count`, `registry.last_flush_status`, `db.size_bytes`, `db.freelist_bytes`, `retention.last_run` after warm start; integration test passes
- [ ] T2-004 runtime smoke: `ccdash target check local` exits 0; `/api/health/detail` fields confirmed
- [ ] T2-005 missing-field resilience test: CLI/FE degrade gracefully (no crash on absent sub-key)
- [ ] T2-006 counter defined in `observability/otel.py`; injection test: `ccdash_db_write_failures_total` increments; exception propagates
- [ ] task-completion-validator sign-off
