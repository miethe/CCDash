---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Enterprise Edition v1 — Phase 3 completion status + follow-ups & Phase 4 next-pass handoff"
status: completed
created: 2026-06-01
updated: 2026-06-01
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
  - .claude/worknotes/ccdash-enterprise-edition-v1/phase-2-status-and-next-pass.md
  - .claude/progress/ccdash-enterprise-edition-v1/phase-3-progress.md
  - .claude/progress/ccdash-enterprise-edition-v1/phase-4-progress.md
---

# Phase 3 Completion + Follow-ups & Phase 4 Next-Pass Handoff

## Where things stand (2026-06-01)

| Phase | Status | Commit |
|-------|--------|--------|
| Phase 0/1 | ✅ completed | `62fbf56` |
| Phase 2 — Cache & Query Correctness | ✅ completed | `46abba0` |
| **Phase 3 — DB Registry & Multi-Project Worker** | ◑ **substantially delivered (partial)** | `dde811a` (code), `afb4548` (progress) |
| Phase 4 — Frontend Performance Finish | ⛔ not started (scaffolded; DAG ready in Phase 2 handoff) | — |

Work was done in worktree `.claude/worktrees/ee-phases-2-4` on branch
`feat/ccdash-ee-phases-2-4` (off `feat/ccdash-enterprise-edition-v1`). **Not yet merged** to
the feat branch — see "Merge & post-merge validation" below.

## Phase 3 — what shipped (live + unit-tested)

Executed as a gated 3-wave owner-batched fan-out (migrations → repos/services/worker → session-PK).
**204 passed, 4 skipped** across the Phase 3 + regression suites (explicit-file pytest;
`test_runtime_bootstrap` intentionally NOT run in a worktree — it hangs). `task-completion-validator`:
APPROVE-WITH-NOTES (both notes addressed).

- **P3-001** DB-backed `projects` table is the authoritative registry; `projects.json` →
  bootstrap/fallback only. `DbProjectManager` (`backend/project_manager.py`) preserves the **sync**
  `WorkspaceRegistry` protocol (zero caller changes) using a dedicated sync DB accessor + in-memory
  snapshot; swapped in via `build_workspace_registry` (`backend/runtime_ports.py`). Sync repos at
  `backend/db/repositories/projects.py` + `postgres/projects.py`.
- **P3-002** OQ resolutions persisted in `oq_resolutions` (repo: `backend/db/repositories/oq_resolutions.py`);
  `planning.py resolve_open_question` reads/writes DB; project-scoped eviction wired via a callback in
  `cache.py` (`aclear_project_cache` + `oq_overlay_evict_project`).
- **P3-004** `project_id` added+backfilled on `session_logs`/`session_tool_usage`/`session_file_updates`;
  repo `upsert_*` write it (threaded from `session_ingest_service.py`).
- **P3-005** per-project `FileWatcherRegistry` (`backend/db/file_watcher.py`). **Key seam:** rebind/start
  MUTATE the legacy `file_watcher` singleton **in place** so `from backend.db.file_watcher import file_watcher`
  consumers (`runtime.py:519`, `routers/cache.py:262`) stay current; the registry is the multi-project mirror
  (the `watcherRegistry` probe field). (An earlier attempt to repoint the module attribute failed because
  `from … import` bindings don't follow attribute reassignment — fixed.)
- **P3-007** multi-project warming + analytics iterate `workspace_registry.list_projects()`.
- **P3-008** enterprise/hosted headerless requests fail-fast (`common.py`); local/dev keep the active fallback.
- **P3-009** `TelemetryExporterJob` + `ArtifactRollupExportJob` run under `worker-watch` (`_export_profiles`).
- **P3-010** `asyncio.Lock` around `rebind_watcher` + registry mutations.
- **P3-012** no module-level `RuntimeContainer` build in `bootstrap_worker.py`.
- **P3-013** supervision states `idle/running/dead/crashed` + server-side `stale_since` on the job probe.
- **P3-014** Postgres NOTIFY listener reconnect with exponential backoff + jitter (+ reconnect test).
- **P3-016** multi-project registry without a worker binding emits an operator warning; dead config vars
  `CCDASH_WORKER_WATCH_PROJECT_ID` / `CCDASH_WORKER_STARTUP_SYNC_ENABLED` wired into the worker startup binding.
- **P3-006 (component only)** durable `job_queue` table + `SqliteJobQueueRepository`
  (`backend/db/repositories/job_queue.py`) + `DurableJobScheduler`/`make_durable_scheduler`
  (`backend/adapters/jobs/durable_queue.py`) with retry/backoff/checkpoint, supervision, and depth metrics —
  shipped and unit-tested, **but not wired as the live scheduler** (see follow-up).
- `SCHEMA_VERSION` 29 → **30** in both `sqlite_migrations.py` and `postgres_migrations.py`
  (projects, oq_resolutions, job_queue, detail-table project_id). New config flag
  `CCDASH_JOB_QUEUE_BACKEND` (default `memory`).
- **P3-011** confirmed subsumed by P3-001 (merged).

## Deferred — two tracked follow-ups (DO THESE NEXT, before declaring Phase 3 done)

### P3-003-FU — session composite PK `(project_id, id)` (the forward-only migration)
**Why deferred:** `backend/db/connection.py:53` runs `PRAGMA foreign_keys=ON`, and **~10 child tables**
declare `… REFERENCES sessions(id) ON DELETE CASCADE` (session_logs, session_tool_usage,
session_file_updates, session_artifacts, session_stack_observations, session_relationships ×2, …).
Once `sessions` PK becomes `(project_id, id)`, `id` alone is no longer unique, so with FK enforcement ON
the **first insert into any child table raises "foreign key mismatch"** → session ingestion breaks. Tests
passed only because they run on empty / FK-off DBs.

**Current state (gated, consistent, safe):** the SQLite recreate migration `_migrate_v30_sessions_composite_pk`
is fully written and **correct** (uses the create-`sessions_new`/copy/drop-`sessions`/rename ordering — the
buggy `RENAME sessions→_sessions_backup` that rewrote child FK refs was fixed), but its CALL is **commented
out** in both migration files inside the `current_version < 30` block. Both `sessions` repos use
`ON CONFLICT(id)`. `sessions` PK remains single-column `id`. Composite-PK tests
(`test_sessions_composite_pk_upsert.py`, one in `test_phase3_repository_migration.py`) are skipped.

**To finish:** make the child→sessions FKs composite `(project_id, session_id) → sessions(project_id, id)`
across ALL child tables (each needs `project_id` — only 3 have it today from P3-004; the rest need it too),
then un-gate `_migrate_v30_sessions_composite_pk`, flip both repos to `ON CONFLICT(project_id, id)`, and
un-skip the tests. This is its own L/XL migration. **Snapshot the DB first; it is forward-only/destructive
on SQLite.** Validate `PRAGMA foreign_key_check` is empty post-migration.

### P3-006-FU — make the durable queue the live dispatch path
The component is built+tested but `ports.job_scheduler` is still `InProcessJobScheduler()` (composed in
`build_core_ports`, `runtime_ports.py:61`), and `DurableJobScheduler.schedule()` only delegates in-process
(the DB enqueue/claim API is unused; the Postgres repo is a stub: `durable_queue.py:215`). So crash-resume
is NOT yet real. **To finish:** (1) implement the asyncpg `PostgresJobQueueRepository`; (2) wire
`make_durable_scheduler(db)` into `build_core_ports` when `JOB_QUEUE_BACKEND != memory`; (3) route
sync/warming jobs through `repo.enqueue` + add a drain/consumer loop so jobs actually persist and resume.
**Validate the ports-composition change in the MAIN repo** (run `test_runtime_bootstrap` there — it hangs in
a worktree). `deploy/runtime/compose.yaml` currently defaults `JOB_QUEUE_BACKEND=memory` with a P3-006-FU
comment; flip enterprise services to `postgres` once wired.

## Merge & post-merge validation (do this next pass)
1. Merge `feat/ccdash-ee-phases-2-4` → `feat/ccdash-enterprise-edition-v1` (squash, mirroring the Phase 2 merge).
2. **In the MAIN repo (not a worktree)** run `python -m unittest backend.tests.test_runtime_bootstrap` to
   validate the container/bootstrap changes (P3-008/009/012 + worker binding) — it could not run in the worktree.
3. Optional: a real 2-replica Postgres `docker compose up` smoke (P0-013 gate) to exercise the DB registry +
   cache sharing + NOTIFY reconnect end-to-end (deferred since Phase 2).

## Environment / workflow (unchanged from Phase 2 handoff)
- Worktree needs `npm install` (already done in `ee-phases-2-4`); no venv in the worktree — use the main-repo
  venv `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python` with `PYTHONPATH=<worktree>`.
- **Test invocation:** always explicit files, never bare `pytest backend/tests` (collection hang). Example:
  `PYTHONPATH=$(pwd) <venv>/python -m pytest backend/tests/test_X.py -p no:cacheprovider --no-header -q`.
- **NEVER run `test_runtime_bootstrap` in a worktree** (imports `backend.main`; hangs — caused a prior 20h stall).
- Delegation: Opus orchestrates; Sonnet subagents implement; owner-batch so no two agents edit the same file.
- Pyright strictness noise (features.py DTOs, planning.py, runtime.py Optional `self.sync`, test fakes) is
  pre-existing; backend has no Pyright CI gate; all tests pass.

## Phase 4 — Frontend Performance Finish (NEXT — L, 22 tasks; P4-017 deferred)
The validated file-owner batch DAG is in
`.claude/worknotes/ccdash-enterprise-edition-v1/phase-2-status-and-next-pass.md` (§"Phase 4"). Highlights:
- Wave 1 (foundational): P4-003 reactive `useData()` (unblocks P4-006/011/012/021), P4-001 cursor pagination
  on the session-board endpoint, P4-010 backend Gemini proxy `POST /api/ai/insight`.
- Wave 2 (one owner per file): command-center/session-board virtualization, setInterval→TQ refetch sweep,
  dashboards→TQ, poll tuning, self-host fonts, project-switch invalidation, React.memo, viewport-deferred mount.
- **FE runtime-smoke gate is MANDATORY**: `npm run dev` + browser smoke before marking Phase 4 complete; no
  `completed` without `runtime_smoke`.

## READY-TO-PASTE PROMPT FOR THE NEXT PASS

> Resume CCDash Enterprise Edition v1 on branch `feat/ccdash-ee-phases-2-4` (worktree
> `.claude/worktrees/ee-phases-2-4`). Phase 3 is committed (`dde811a`) but PARTIAL. Read
> `.claude/worknotes/ccdash-enterprise-edition-v1/phase-3-status-and-next-pass.md` first. Either (A) finish
> the two Phase-3 follow-ups — **P3-003-FU** (composite session PK + composite child FKs across all child
> tables; un-gate `_migrate_v30_sessions_composite_pk`; repos → `ON CONFLICT(project_id, id)`; snapshot DB,
> forward-only) and **P3-006-FU** (asyncpg job-queue repo + wire `make_durable_scheduler` into
> `build_core_ports` + enqueue/drain loop; validate `test_runtime_bootstrap` in the MAIN repo) — then merge to
> `feat/ccdash-enterprise-edition-v1`; OR (B) merge Phase 3 as-is and execute **Phase 4 — Frontend Performance
> Finish** per the validated DAG in the Phase 2 handoff (`phase-4-progress.md` + backlog `07-...md`). Delegate
> to Sonnet subagents owner-batched (no two agents edit the same file); Opus orchestrates only. Explicit-file
> pytest only; NEVER run `test_runtime_bootstrap` in a worktree. FE work requires an `npm run dev` browser
> smoke before `completed`. Run `task-completion-validator` before each commit.
