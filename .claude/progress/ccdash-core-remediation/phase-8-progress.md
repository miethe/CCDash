---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-core-remediation
feature_slug: ccdash-core-remediation
phase: 8
status: completed
created: 2026-06-11
updated: '2026-06-11'
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs:
- a24111b
pr_refs: []
owners:
- python-backend-engineer
contributors:
- data-layer-expert
overall_progress: 100
tasks:
- id: T8-001
  name: Resolve OQ-4 + reconcile design (seam contract only)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
- id: T8-002
  name: Periodic all-projects reconcile
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T8-001
- id: T8-003
  name: Watcher liveness self-heal
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T8-001
- id: T8-004
  name: SYNC_ALL_PROJECTS + post-boot dirs
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T8-001
- id: T8-005
  name: Docs/plans parity + writeback regression tests
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T8-002
  - T8-003
  - T8-004
parallelization:
  batch_1:
  - T8-001
  batch_2:
  - T8-002
  - T8-003
  - T8-004
  batch_3:
  - T8-005
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
---

# Phase 8 — Cross-Project Freshness Hardening Progress

Executed via ICA bash delegation. Disjoint from P2 (runs in parallel after P5 commits).
Depends on Phase 7 coalescing guard (Wave 2, completed + validator-signed).
Single-threaded owner of `runtime.py` / `file_watcher.py` edits; touches `sync_engine.py`
+ `config.py` AFTER P5 commits (sequential, no parallel-edit hazard).

## Guards
- Reconcile enumerates projects from DB-authoritative registry (ADR-006), NOT projects.json.
- All reconcile dispatches go through the Phase 7 coalescing guard (no double-scan).
- Non-active project writeback stays OFF (permanent regression fixture, AC 8.5).
- New write paths use `retry_on_locked`; independent SQLite conns set `PRAGMA busy_timeout = 30000` (ADR-007).
- Backend-only phase: no FE, no runtime smoke (R-P3/R-P4 N/A).

## Implementation Evidence (single-pass, 2026-06-11)

### T8-001 — OQ-4 resolution + reconcile seam contract
- **Cadence**: interval-based polling reconcile. Config `CCDASH_RECONCILE_INTERVAL_SECONDS` (default 300; `<=0` disables). Documented inline in `backend/config.py`.
- **Registry-change-event**: noted as fast-follow; approximated cheaply today by `reload_projects()` (snapshot invalidation) at the start of each tick → post-boot rows surface within one interval.
- **Enumeration**: `workspace_registry.list_projects()` → `db_project_manager` (DB-authoritative, ADR-006; `projects.json` only as fallback/bootstrap). NEVER reads `projects.json` directly.
- **Guard routing**: each per-project pass dispatches `SyncEngine.sync_project(..., trigger="reconcile")`, which is wrapped by the Phase 7 `_sync_in_flight` coalescing guard (sync_engine.py:3112-3138 / release at 3404-3409). No new dispatch path; no double-scan.

### T8-002 — Periodic all-projects reconcile
- `backend/adapters/jobs/runtime.py`: new `RuntimeJobAdapter._start_reconcile_task()` (modeled on `_start_cache_warming_task`); `RuntimeJobState.reconcile_task` field; `"reconcile"` job observation; wired into `start()` under `capabilities.jobs`; torn down in `stop()`.
- Each tick: `reload_projects()` → `list_projects()` → per-project `sync_project(trigger="reconcile")` via the Phase 7 guard → self-heal. Per-project + per-resolve exceptions logged and skipped; sweep continues. Marks job success/failure with `projectsReconciled` / `watchersHealed` / `failedProjectIds`.

### T8-003 — Watcher liveness self-heal
- `backend/db/file_watcher.py`: `FileWatcherRegistry.dead_project_ids(expected_ids)` liveness predicate (detects registered-but-crashed via `is_running=False` AND expected-but-absent). Reconcile tick re-binds dead watchers via `registry.register(...)`; self-heal events logged (`watcher self-heal: re-bound ...`); re-bind failure logged + retried next tick (never silently dead). Gated by `CCDASH_WATCHER_HEAL_ENABLED` (default true).

### T8-004 — SYNC_ALL_PROJECTS + post-boot dirs
- `backend/config.py`: `CCDASH_SYNC_ALL_PROJECTS` default **flipped True→False** — boot hot-path all-projects sweep now defaults off; cross-project freshness provided by the reconcile job (decoupled). Flag still honored at the boot all-projects loop. (Only `config.py` + `test_sync_all_projects.py` reference the flag; that test sets it explicitly, so the default flip is regression-safe — verified 13/13 green.)
- Post-boot pickup: `DbProjectManager.reload()` (public wrapper for `_invalidate_snapshot`) + `ProjectManagerWorkspaceRegistry.reload_projects()` (getattr-guarded). Reconcile calls it each tick so projects/dirs added after boot are reconciled + watcher-registered with no restart.
- Non-active writeback stays OFF: `allow_writeback=(pid==active_project_id)` on every reconcile dispatch.

### T8-005 — Tests (`backend/tests/test_reconcile_freshness.py`)
- 8 tests, **all PASS** (`backend/.venv/bin/python -m pytest backend/tests/test_reconcile_freshness.py -v` → 8 passed):
  - (a) non-active project reconciled within one interval (`test_non_active_project_reconciled_within_interval`) — also asserts `trigger="reconcile"` (Phase 7 guard routing).
  - (b) crashed watcher self-heals within one interval (`test_crashed_watcher_self_heals_within_interval`) + predicate unit test (`test_dead_project_ids_detects_crashed_and_missing`).
  - (c) post-boot project picked up without restart (`test_post_boot_project_picked_up_without_restart`).
  - (d) **REGRESSION (permanent fixture)**: non-active writeback OFF / active ON (`test_non_active_writeback_stays_off_regression`).
  - Guard: malformed/empty project row skipped, sweep continues (`test_malformed_project_row_skipped_sweep_continues`).
  - Resilience: self-heal disabled skips re-bind; interval `<=0` disables the job.
- Regression: `backend/tests/test_sync_all_projects.py` → 13 passed (default-flip safe).

### Files changed
- `backend/config.py` (additive reconcile/heal vars; SYNC_ALL_PROJECTS default flip)
- `backend/adapters/jobs/runtime.py` (reconcile task + state + observation + start/stop wiring)
- `backend/db/file_watcher.py` (`dead_project_ids` predicate + `Iterable` import)
- `backend/project_manager.py` (`DbProjectManager.reload()`)
- `backend/adapters/workspaces/local.py` (`reload_projects()`)
- `backend/tests/test_reconcile_freshness.py` (new, 8 tests)

### Guards honored
- DB-authoritative enumeration only (ADR-006); malformed row → logged-skip-continue.
- All reconcile dispatches via `sync_project` → Phase 7 coalescing guard (no double-scan reintroduced).
- Non-active writeback OFF (permanent regression fixture).
- No new DB write paths added (reuses `sync_project` which already uses `retry_on_locked`); no new independent SQLite connections.
- Phase 5 sidecar-join code / `CCDASH_SIDECAR_CONTEXT_JOIN_ENABLED` untouched (additive edits only).
- `status: in_progress` retained pending task-completion-validator sign-off (Phase 8 Quality Gate).
