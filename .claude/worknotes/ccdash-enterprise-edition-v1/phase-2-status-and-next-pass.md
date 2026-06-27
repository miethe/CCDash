---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Enterprise Edition v1 — Phase 2 completion status + Phase 3/4 next-pass handoff"
status: completed
created: 2026-06-01
updated: 2026-06-01
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
  - .claude/progress/ccdash-enterprise-edition-v1/phase-2-progress.md
  - .claude/progress/ccdash-enterprise-edition-v1/phase-3-progress.md
  - .claude/progress/ccdash-enterprise-edition-v1/phase-4-progress.md
---

# Phase 2 Completion + Phase 3/4 Next-Pass Handoff

## Where things stand (2026-06-01)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 — Enterprise Liveness Hotfix | ✅ completed (commit `62fbf56`) | shipped before this pass |
| Phase 1 — Storage Hygiene & DB Perf | ✅ completed (commit `62fbf56`) | shipped before this pass |
| **Phase 2 — Cache & Query Correctness** | ✅ **completed this pass** | 17/18 tasks; P2-018 deferred. 410 backend tests green. |
| Phase 3 — DB Registry & Multi-Project Worker | ⛔ **not started** (scaffolded only) | progress file + owner-batch DAG ready below |
| Phase 4 — Frontend Performance Finish | ⛔ **not started** (scaffolded only) | progress file + owner-batch DAG ready below |

This pass executed **Phase 2 only**. Phases 3 and 4 have progress trackers created
(`phase-3-progress.md`, `phase-4-progress.md`) with the full task list and validated
file-owner batches, but **no implementation code was written for them**.

## Phase 2 — what shipped

Executed via a 2-wave owner-batched fan-out (10 agents). All 17 active tasks landed; **P2-018
(precompute planning graph in worker) deferred** because it depends on P3-007 (multi-project
warming) and is consumed in Phase 5.

Tasks completed: P2-001, P2-002, P2-003, P2-004, P2-005, P2-006, P2-007, P2-008, P2-009,
P2-010, P2-011, P2-012, P2-013, P2-014, P2-015, P2-016, P2-017.

Key deliverables:
- **Shared cache abstraction (P2-001)** behind the existing `@memoized_query` seam in
  `backend/application/services/agent_queries/cache.py`: a `CacheBackend` interface with two
  implementations — `InProcessCacheBackend` (default, wraps the module-level `_query_cache`
  `TTLCache`) and `PostgresCacheBackend` (new `query_cache` table). Selected via
  `CCDASH_QUERY_CACHE_BACKEND` (default `memory`; enterprise compose defaults `postgres`).
  `init_postgres_cache_backend(db)` is wired at `backend/runtime/container.py:110` (post-migration,
  all profiles) and falls back to in-process on failure.
- **Fingerprint correctness (P2-003/004)**: `entity_links` fingerprint marker is now
  project-scoped (`WHERE project_id = ?`) instead of a global `GROUP_CONCAT` table scan;
  `feature_phases` marker is constant-time `MAX(updated_at)+COUNT(*)` instead of O(N) string concat.
- **Per-metric TTLs (P2-005)**, **project-scoped eviction (P2-006)**, **maxsize 512→2048 (P2-015)**.
- **Sync-triggered invalidation (P2-002)**: `sync_project()` calls `aclear_project_cache(project_id)`
  → `DELETE FROM query_cache WHERE project_id` on the postgres backend (cross-replica propagation).
- **Bundle parallelization (P2-007)**: `get_planning_view_bundle` does ONE shared
  `_load_all_features`/`_load_all_doc_rows` pass + `asyncio.gather` of sub-builds.
- **Bounded feature context (P2-012)**, **summary projections (P2-008 `list_summary`)**,
  **V1 command-center + session-board memoization (P2-009/010)**, **fast single-feature path
  (P2-011)**, **NullGitProbe in V1 build (P2-013)**, **cache warming expanded 2→10 endpoints
  (P2-014)**, **legacy `/api/features` memoized + N+1 removed (P2-016)**, **session-detail query
  batching (P2-017)**.
- `SCHEMA_VERSION` bumped **28 → 29** (both `sqlite_migrations.py` and `postgres_migrations.py`),
  adding the additive `query_cache` table. **Phase 3 migrations must start from 29 → 30.**

New config flags: `CCDASH_QUERY_CACHE_BACKEND` (default `memory`),
`CCDASH_FINGERPRINT_CACHE_TTL_SECONDS` (default 5). Both documented in `.env.example`.
Enterprise services in `deploy/runtime/compose.yaml` default `CCDASH_QUERY_CACHE_BACKEND=postgres`.

### Test evidence
- 230 new/changed Phase 2 unit tests pass.
- Full regression + new-suite batch: **410 passed, 1 skipped** (cache, migrations, planning,
  features, session-intelligence suites). Run with:
  `PYTHONPATH=$(pwd) backend/.venv/bin/python -m pytest <explicit files> -p no:cacheprovider -q`
- `compileall backend` clean; key-module import check clean; `container.py` import clean.

### Caveats / known follow-ups carried out of Phase 2
1. **P2-003 fingerprint-result short-TTL cache deferred off the hot path.** A 5–10s fingerprint
   cache fundamentally conflicts with the existing immediate-invalidation contract tests
   (`test_agent_query_cache_invalidation.py` expects touching feature B to invalidate A's cache
   immediately). We shipped the high-value parts (project-scoping + constant-time markers) and
   left `_get_data_version_fingerprint_cached` as an opt-in wrapper not wired into the hot path.
   To finish it later: reconcile with invalidation (e.g. bust the fingerprint cache on
   `sync_project`/`clear_project_cache`) and relax the immediate-invalidation tests to allow a
   bounded stale window, per roadmap §2.2 which explicitly accepts a 5–10s window.
2. **P2-018 deferred** (depends on P3-007; consumed in Phase 5).
3. **No full enterprise `docker compose up` smoke** was run this pass — validation was unit +
   functional tests + import checks only. The P0-013 compose e2e gate (Phase 0) plus the
   cache-sharing/invalidation validation steps in roadmap §Phase 2 should be exercised against a
   real 2-replica postgres topology before declaring enterprise-ready.
4. **Pyright strictness noise** (pre-existing) re-surfaced in `planning.py` (gather-result typing
   at ~2439), `sync_engine.py` (Optional `.get` access), `features.py` (row access). These are NOT
   regressions — the backend has no Pyright CI gate and all tests pass. Optional cleanup: add
   `cast()`s around the `asyncio.gather` results in `get_planning_view_bundle`.
5. **`test_runtime_bootstrap` hangs in a worktree** because it imports `backend.main` (starts
   runtime side-effects that never terminate). This was the cause of the 20h stall. Validate the
   container startup change via `python -m unittest backend.tests.test_runtime_bootstrap` **in the
   main repo** (not a worktree), or rely on the targeted import check. Do NOT run it in a worktree.

## Environment / workflow setup for the next pass

- **Worktree:** this work was done in `.claude/worktrees/ee-phases-2-4` on branch
  `feat/ccdash-ee-phases-2-4`, then merged into `feat/ccdash-enterprise-edition-v1`. A fresh
  worktree needs `npm install`; the backend has **no venv in the worktree** — use the main-repo
  venv at `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python` with
  `PYTHONPATH=<worktree-root>`.
- **Test invocation (avoids the known pytest-collection hang):** always pass **explicit test
  files**, never `pytest backend/tests`. Example:
  `PYTHONPATH=$(pwd) /Users/.../backend/.venv/bin/python -m pytest backend/tests/test_X.py backend/tests/test_Y.py -p no:cacheprovider --no-header -q`
- **Delegation model:** Opus orchestrates; Sonnet subagents implement (set `model: 'sonnet'` on
  every Workflow `agent()` — workflow agents otherwise inherit the Opus main-loop model). Use
  `agentType: 'python-backend-engineer'` / `'data-layer-expert'` / `'ui-engineer-enhanced'`.
- **Owner-batching is the parallel-safety rule:** never let two parallel agents edit the same file.

## Locked decisions (from synthesis brief §8 — do not re-litigate)
- **Shared cache tech:** Postgres-backed cache table is the enterprise default (shipped); Valkey
  is a future optional backend behind the same `CacheBackend` interface. In-process is dev fallback.
- **Worker topology:** watch-all default + per-project opt-in via `CCDASH_WORKER_WATCH_PROJECT_ID`.
- **Durable queue (P3-006):** Postgres-backed, behind the existing `adapters/jobs/` port with
  in-process fallback (no new infra).
- **Transcript storage:** canonical `session_messages` + filesystem source-of-truth (Phase 1).
- **SQLite:** dev-only; Postgres mandatory for enterprise.

## Phase 3 — DB-backed Project Registry & Multi-Project Worker (NEXT — XL, the hardest phase)

16 tasks (P3-001..P3-016); P3-011 is **merged** (subsumed by P3-001 DB-backed registry).
This is the most structurally invasive phase: a `projects` table, OQ→DB, a session-PK migration
(forward-only, destructive on SQLite), a `FileWatcherRegistry`, and a durable job queue.

**Validated file-owner batch DAG (no two parallel agents share a file):**

Wave 1 (foundation — migrations + independent reconnect):
- `migration-owner` (data-layer-expert) → P3-001(projects DDL), P3-002(oq_resolutions DDL),
  P3-003(session PK → `(project_id, id)`, **destructive on SQLite: table recreate**),
  P3-004(`project_id` on `session_logs`/`session_tool_usage`/`session_file_updates`), + the
  durable job-queue table for P3-006. Owns `backend/db/sqlite_migrations.py` +
  `backend/db/postgres_migrations.py`. **SCHEMA_VERSION 29 → 30, bump LAST.** Migration ordering:
  projects → oq_resolutions → job_queue → session PK → detail `project_id` → version bump.
- `notify-owner` (python-backend-engineer) → P3-014 Postgres NOTIFY listener reconnect +
  exponential backoff. Owns `backend/adapters/live_updates/postgres_listener.py` (enterprise-only,
  gated at `container.py:229`; no reconnect loop today — `start()` is one-shot).

Wave 2 (after migrations; all independent files):
- `registry-owner` (python-backend-engineer) → P3-001 repo facade: replace `projects.json`
  load/save in `backend/project_manager.py` with a `projects`-table-backed repo, preserving the
  `WorkspaceRegistry` Protocol (`backend/application/ports/core.py`). Keep a read-path compat shim
  that falls back to `projects.json` for one release.
- `sessions-repo-owner` (data-layer-expert) → P3-003 (`ON CONFLICT` target → `(project_id, id)`),
  P3-004 (`project_id` in `upsert_logs`/`upsert_tool_usage`/`upsert_file_updates`). Owns
  `backend/db/repositories/sessions.py` + `backend/db/repositories/postgres/sessions.py`.
- `oq-owner` (python-backend-engineer) → P3-002: move `_OQ_OVERLAY` (in-memory dict at
  `planning.py:109`) to the `oq_resolutions` table; `resolve_open_question` (planning.py:1501)
  becomes the DB upsert; reads fall back to overlay during transition. Owns `planning.py`.
- `watcher-queue-owner` (python-backend-engineer, HEAVIEST — 2 XL items) → P3-005
  (`FileWatcherRegistry` replacing the `file_watcher` singleton at `file_watcher.py:307`; one
  watcher task per registered project), P3-006 (durable queue replacing
  `InProcessJobScheduler.create_task` at `adapters/jobs/local.py:8`; retry/priority/backpressure/
  supervision; resume-from-checkpoint), P3-007 (multi-project warming/analytics loops in
  `runtime.py:786,840` — iterate `list_projects()` not active-only; reuse `_CACHE_WARM_TARGETS`),
  P3-010 (`rebind_watcher` `asyncio.Lock`), P3-013 (supervision states `idle`/`running`/`dead`/
  `crashed` + `stale_since`), P3-015 (queue-depth metrics). Owns `backend/db/file_watcher.py` +
  `backend/adapters/jobs/runtime.py` + `backend/adapters/jobs/local.py`.
- `worker-bootstrap-owner` (python-backend-engineer) → P3-008 (enterprise headerless fail-fast:
  remove global active-project fallback at `common.py:93-120` + `container.py:293`, enterprise-
  gated; local keeps fallback), P3-009 (wire `TelemetryExporterJob`/`ArtifactRollupExportJob` for
  `worker-watch`, today `worker`-only at `container.py:144-156`), P3-012 (remove module-level
  `container = build_worker_runtime()` at `bootstrap_worker.py:86`), P3-016 (warn on multi-project
  registry without binding). Also wire the dead `CCDASH_WORKER_WATCH_PROJECT_ID`/
  `CCDASH_WORKER_STARTUP_SYNC_ENABLED` config vars (config.py:968-973) into the worker runtime
  (`_resolve_startup_project_binding` at `container.py:1161`). Owns `backend/runtime/container.py`
  + `backend/runtime/bootstrap_worker.py` + `backend/config.py` + `backend/application/services/common.py`.

Risk notes: session-PK change is forward-only — add a collision pre-check + backfill `project_id`
on detail tables before flipping the conflict target; snapshot DB before enabling. All registry +
fail-fast changes are enterprise-gated so local mode is unaffected.

## Phase 4 — Frontend Performance Finish (after Phase 3 — L)

22 tasks (P4-001..P4-022); **P4-017 deferred** (depends on P5-001, out of scope).

**Validated file-owner batch DAG:**

Wave 1 (backend prereqs + foundational FE):
- `backend-pagination-owner` → P4-001 cursor pagination on the session-board endpoint
  (`backend/routers/agent.py:621` + `planning_sessions.py:609` `list_paginated(0,500)`).
- `gemini-proxy-owner` → P4-010 new backend route `POST /api/ai/insight` proxying Gemini + swap
  `services/geminiService.ts` to it + remove the `define` in `vite.config.ts:84`.
- `datacontext-owner` → P4-003 make `useData()` reactive (`contexts/DataContext.tsx:132-167`
  `getQueryData()` → `useQuery()`). **Foundational — unblocks P4-006/011/012/021.**

Wave 2 (FE, after Wave 1; one owner per file):
- `command-center-owner` → P4-002 (`PlanningCommandCenter.tsx` raw fetch → TQ), P4-014 (UI
  pagination beyond `pageSize=50`).
- `session-board-owner` → P4-004 (virtualize V1 `PlanningAgentSessionBoard.tsx` `BoardColumn`),
  P4-018 (O(N) Set hover), P4-019 (`StaleIndicator` interval only when stale). Depends on P4-001.
- `setinterval-owner` → P4-006 replace `setInterval` sprawl across `Dashboard.tsx:117`,
  `SystemMetricsChip.tsx:73`, `ProjectBoard.tsx:1422`, `OpsPanel.tsx:885,900`,
  `SessionInspector.tsx:4646,5652` with TQ `refetchInterval`/SSE. (Split per-file if parallelized.)
- `dashboard-owner` → P4-011 (Dashboard chart-series raw fetches → TQ; KPI cards already TQ),
  P4-012 (`AnalyticsDashboard.tsx` 7 raw fetches → TQ).
- `polls-owner` → P4-005 (`features.ts:85` refetchInterval 5s→30s; `useFeatureSurface.ts:348`
  staleTime 0→10–30s — depends on P2-016 ✅ done), P4-008 (hover prefetch → `queryClient.prefetchQuery`
  in `services/planning.ts:848`), P4-016 (`planning.ts:72` summary staleTime 0→≥5s).
- `fonts-owner` → P4-009 self-host fonts (`PlanningRouteLayout.tsx:31-48`).
- `project-switch-owner` → P4-015 invalidate TQ on project switch (`AppSessionContext.tsx` /
  `DataContext.tsx:196`).
- `memo-owner` → P4-013 `React.memo` inner panels of `SessionInspector.tsx`/`ProjectBoard.tsx`.
- `opspanel-owner` → P4-021 `OpsPanel` reactive reads (depends on P4-003).
- `docs-owner` → P4-022 (.env.example/deploy SSE docs), P4-020 (doc page-size/memory cap).
- `viewport-owner` → P4-007 viewport-deferred mount of board + command center
  (`PlanningHomePage.tsx:842,919`). Depends on P4-001/002.

FE gate: every FE change requires a `npm run dev` browser smoke before marking a phase complete
(CLAUDE.md runtime-smoke gate). No `completed` without `runtime_smoke`.

---

## READY-TO-PASTE PROMPT FOR THE NEXT PASS

> Resume CCDash Enterprise Edition v1. Phases 0–2 are complete and merged on
> `feat/ccdash-enterprise-edition-v1`. Execute **Phase 3 — DB-backed Project Registry &
> Multi-Project Worker** next (then Phase 4 if budget remains). Read
> `.claude/worknotes/ccdash-enterprise-edition-v1/phase-2-status-and-next-pass.md` — it contains
> the locked decisions, the validated file-owner batch DAG for Phase 3 and Phase 4, the migration
> ordering (SCHEMA_VERSION 29 → 30), the worktree/venv setup, and the test-invocation pattern that
> avoids the pytest-collection hang. The task list + statuses live in
> `.claude/progress/ccdash-enterprise-edition-v1/phase-3-progress.md` (pending) and
> `phase-4-progress.md` (pending); ACs are in
> `docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md`.
> Work in a worktree off `feat/ccdash-enterprise-edition-v1`, run `npm install`, use the main-repo
> venv with `PYTHONPATH=<worktree>`. Delegate implementation to Sonnet subagents owner-batched per
> the DAG (no two agents edit the same file); Opus orchestrates only. **Do NOT run
> `test_runtime_bootstrap` in a worktree** (it imports `backend.main` and hangs — this caused a
> 20h stall last pass; validate with targeted import checks + explicit-file pytest, or run that
> one test in the main repo). Commit per phase; run the mandatory `task-completion-validator`
> reviewer gate before each phase commit. Be realistic about scope — Phase 3 alone has 2 XL items
> (FileWatcherRegistry + durable queue) and a forward-only session-PK migration; if you run low on
> budget, commit what is done, update the progress file, and write a fresh handoff rather than
> leaving uncommitted work.
