---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Current-State Architecture Report (Enterprise Edition)"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Current-State Architecture Report (Enterprise Edition)

> Audience: AI implementation agents and senior engineers planning Phase 0–6 enterprise work.
> This document is a **what-exists-now baseline** only. No recommendations, no proposals — those live in docs 02, 03, and 05.
> Every fact is anchored to file:line evidence from the 12-domain forensic investigation (2026-05-30).

---

## 1. Executive Snapshot

CCDash is a local-first → enterprise AI-session forensics dashboard. The stack is a React 19 + Vite SPA (HashRouter, port 3000) backed by a Python FastAPI server (port 8000) with an SQLite-default / PostgreSQL-enterprise dual data path. Background ingestion runs in a separate worker process profile; live events flow from worker to API via Postgres NOTIFY → SSE.

### System shape

```
Browser (HashRouter SPA)
  ↕ /api proxy (Vite dev) or nginx (container)
FastAPI API container  (CCDASH_RUNTIME_PROFILE=api)
  ↕ asyncpg.Pool / aiosqlite singleton
SQLite (dev: data/ccdash_cache.db) or PostgreSQL (enterprise)
  ↑ populated by
Worker containers  (CCDASH_RUNTIME_PROFILE=worker | worker-watch)
  ↑ reads from
Local filesystem  (JSONL session logs, .md plan documents)
```

### Two facts that define the enterprise problem

1. **The production SQLite DB is 10 GB.** Anatomy: `session_logs` 2.1 GB + `telemetry_events` 1.6 GB + `session_messages` 1.2 GB + `analytics_entries` 466 MB (1.8 M rows, unbounded) + `session_usage_attributions` 385 MB + `sessions` 199 MB (9,246 rows). There is no retention policy anywhere in the codebase. The page cache is the SQLite default of 8 MB (2,000 pages). No `PRAGMA cache_size`, `synchronous`, or `mmap_size` are set (`backend/db/connection.py:52–54`).

2. **The containerized enterprise build ingests zero data by default.** Three compounding defaults produce silent empty-DB deployments: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults `false` in the compose anchor (`deploy/runtime/compose.yaml:27`); `CCDASH_WORKER_STARTUP_SYNC_ENABLED` defaults `false` for the standard worker (`compose.yaml:133`); the `live-watch` profile (the only one that enables both) is not part of the default `docker compose --profile enterprise --profile postgres up` command. A standard enterprise deploy reaches a healthy API with an empty Postgres database.

---

## 2. Frontend

### 2.1 Framework, routing, and build

- **React 19** + **TypeScript** + **Vite** (port 3000). `HashRouter` — no SSR, no prefetching.
- Path alias `@/` → repo root. All shared types in root `types.ts` (~4,000 lines), constants in `constants.ts`.
- Lazy route code-splitting for all pages via `React.lazy` in `App.tsx:29–47`. ✓
- `GEMINI_API_KEY` baked into JS bundle via `vite.config.ts:84–87` `define` — present in static assets in container builds. PARTIAL.

### 2.2 State management: provider tree and DataContext facade

```
QueryClientProvider  (App.tsx:90 — queryClientRef.useRef stabilized)
  ThemeProvider
    HashRouter
      DataProvider  (contexts/DataContext.tsx:82 — composition facade)
        DataClientProvider
          AuthSessionProvider
            AppDataProviderGate
              AppSessionProvider   ← project list + activeProject (/projects/active)
              AppRuntimeProvider   ← health query (30 s refetchInterval)
```

`AppEntityDataContext.tsx` has been fully deleted (T4-005, confirmed by `contexts/__tests__/dataArchitecture.test.ts:54`). No server-state arrays in Context remain. The `useData()` facade at `DataContext.tsx:120–267` bridges legacy consumers via `queryClient.getQueryData()` — a **snapshot read, not a reactive subscription** (`DataContext.tsx:132–167`). Thirteen-plus components still consume `useData()` for `sessions`, `documents`, `features`, `tasks`, `alerts`, `notifications`, and `projects`; these arrays are stale snapshots until an unrelated render triggers the enclosing component to re-render. `OpsPanel.tsx:272`, `PlanCatalog.tsx:294`, `PlanningHomePage.tsx:928`, `SessionInspector.tsx:3957`, and others are affected. `activeProject` is sourced from `AppSessionContext` and is reactive (benign). `queryClient.clear()` on project switch is present at `DataContext.tsx:197`. ✓

**Completed vs Partial.** TQ migration phases 0–7 are complete (176 guardrail tests green). Gap: `useData()` reactive subscription not fixed; `AnalyticsDashboard.tsx` and three `Dashboard.tsx` analytics-series calls remain outside TQ; `setInterval` sprawl in 8+ components bypasses TQ dedup/visibility-awareness.

### 2.3 TanStack Query layer

**TQ v5 (`^5.100.14`)** fully wired. Global defaults in `lib/queryClient.ts:29–41`: `staleTime: 30_000`, `gcTime: 300_000`, `retry: 3`, `refetchOnWindowFocus: false`.

Query key registry at `services/queryKeys.ts` — all keys prefixed with `projectId`. Domain hook inventory:

| Hook | File | staleTime | refetchInterval |
|------|------|-----------|-----------------|
| `useSessionsQuery` | `sessions.ts:55` | 30 s | — |
| `useDocumentsQuery` | `documents.ts:72` | 60 s | — |
| `useFeaturesQuery` | `features.ts:81` | 30 s | **5 s when SSE off** |
| `useTasksQuery` | `tasks.ts` | 30 s | — |
| `useAlertsQuery` | `alerts.ts:45` | 30 s | 30 s |
| `useHealthQuery` | `health.ts:52` | 25 s | 30 s |
| `useDashboardBundleQuery` | `dashboard.ts:87` | 10 s | — |
| `usePlanningViewQuery` | `planning.ts:226` | 30 s | — |
| `usePlanningFeatureContextQuery` | `planning.ts:104` | 30 s | — |
| `usePlanningSessionBoardQuery` | `planning.ts:137` | 30 s | — |
| `usePlanningSummaryQuery` | `planning.ts:72` | **0** | — |
| `useFeatureSurface (list tier)` | `useFeatureSurface.ts:348` | **0** | — |
| `useFeatureSurface (rollup tier)` | `useFeatureSurface.ts:397` | 30 s | — |
| `useAnalyticsOverviewQuery` | `analytics.ts:55` | 30 s | — |
| `useMultiProjectCommandCenterQuery` | `planning.ts:338` | 30 s | — (gated) |
| `useMultiProjectSessionBoardQuery` | `planning.ts:386` | 30 s | — (gated) |

`useFeaturesQuery` `refetchInterval: 5_000` is conditional on `isFeatureLiveUpdatesEnabled()` (`services/queries/features.ts:85`); `VITE_CCDASH_LIVE_FEATURES_ENABLED` defaults `false` in `.env.example:135`. Enterprise deployments without SSE enablement fire 12 feature-list requests per minute. `useFeatureSurface` list tier `staleTime: 0` triggers a background refetch on every Dashboard and ProjectBoard mount.

Fat-read bundle endpoints implemented: `useDashboardBundleQuery` → `GET /api/v1/dashboard` (T5-005); `usePlanningViewQuery` → `GET /api/agent/planning/view` (T5-007); `useAnalyticsOverviewQuery` → `GET /api/analytics/overview-bundle` (T5-007 best-effort). ✓

SSE live-invalidation infrastructure fully built: `LiveConnectionManager` with exponential backoff, visibility-aware pause, cursor tracking (`services/live/connectionManager.ts`). `useLiveInvalidation` wired to planning summary (`PlanningHomePage.tsx:969–978`). ✓ Gap: not wired to session board or command center.

### 2.4 Lazy routing and virtualization

All page routes lazy-loaded via `React.lazy` (`App.tsx:29–47`). ✓

Virtualization coverage:

| Surface | Virtualizer | Threshold |
|---------|-------------|-----------|
| `TranscriptView` message list | `useVirtualizer` | all rows |
| `ProjectBoard` feature list | `useVirtualizer` | all items |
| `PlanCatalog` doc list | `useVirtualizer` (×2) | all items |
| `MultiProjectCommandCenter` work items | `useVirtualizer` | 250 items |
| `MultiProjectSessionBoard` column cards | `useVirtualizer` | 250 cards/col |
| `SessionInspector` past-threads panel | `useVirtualizer` | all items |
| `PlanningAgentSessionBoard` columns | **none** | CSS scroll only |
| `CommandCenterListView`, `BoardView` | **none** | — |
| `AnalyticsDashboard` artifact lists | **none** | — |

### 2.5 Memory guard

`isMemoryGuardEnabled()` defaults `true` (`VITE_CCDASH_MEMORY_GUARD_ENABLED`, `lib/featureFlags.ts:22`). Ring-buffer cap: `mergeSessionDetail` in `dataContextShared.ts:55–65` keeps last `MAX_SESSION_LOG_ROWS = 5000` log rows per session. Document cap: `useDocumentsQuery` `select` transform clamps to `MAX_DOCUMENTS_IN_MEMORY = 2000` (`services/queries/documents.ts:76–77`, `constants.ts:391`). Session page size: 50 items, infinite scroll (`services/queries/sessions.ts:17,41`). ✓

**Completed vs Partial.** Memory guard is complete for sessions and documents. Gap: no per-session eviction once loaded into TQ cache (`gcTime: 300_000`); document page size 500/page (up to 2,000 in memory) is large for enterprise; `MAX_SESSION_LOG_ROWS = 5000` is conservative but still substantial at scale.

---

## 3. Backend

### 3.1 Layered architecture

```
backend/routers/        → HTTP route handlers (FastAPI)
  api.py               → sessions, documents, tasks
  agent.py             → agent-queries transport (planning, forensics, system metrics)
  analytics.py         → analytics endpoints
  features.py          → feature CRUD + surface
  projects.py          → project management
  cache.py             → cache inspect/invalidate/sync
  codebase.py          → codebase explorer
  session_mappings.py  → session-mapping diagnostics
  live.py              → SSE /api/live/stream
  client_v1.py         → standalone CLI transport
backend/services/       → business logic (codebase_explorer, feature_execution)
backend/db/repositories/ → data access (SQL queries only, no business logic)
backend/application/services/agent_queries/ → transport-neutral intelligence layer
```

All routers call services or repositories; no raw SQL in routers. `backend/application/services/agent_queries/` is the shared intelligence layer consumed identically by `backend/routers/agent.py`, `backend/cli/main.py`, and `backend/mcp/server.py`. ✓

### 3.2 Transport-neutral agent_queries layer

The 15 service classes under `backend/application/services/agent_queries/` are instantiated once at `agent.py:93–112` (module-level singletons). Each service method may be decorated with `@memoized_query` (see §7). Key services:

| Service | Key methods | Cache key |
|---------|-------------|-----------|
| `ProjectStatusQueryService` | `get_status` | `project_status` |
| `PlanningQueryService` | `get_project_planning_summary`, `get_project_planning_graph`, `get_feature_planning_context`, `get_phase_operations`, `get_planning_view_bundle` | `planning_project_summary`, `planning_project_graph`, `planning_feature_context`, `planning_phase_ops` (none on view bundle) |
| `PlanningCommandCenterQueryService` | `get_command_center`, `get_command_center_item` | **none** |
| `PlanningSessionQueryService` | `get_session_board` | **none** |
| `DashboardQueryService` | `get_bundle` | `dashboard_bundle` |
| `SystemMetricsQueryService` | `get_system_active_count` | `system_active_count` |
| `LiveMetricsQueryService` | `get_active_count` | `live_active_count` |
| `MultiProjectPlanningCommandCenterQueryService` | `get_multi_project_command_center` | `mpcc_command_center` |
| `MultiProjectActiveSessionBoardQueryService` | `get_multi_project_session_board` | `mpss_session_board` |
| `AnalyticsBundleQueryService` | `get_analytics_overview_bundle` | `analytics_overview_bundle` |
| `FeatureForensicsQueryService` | `get_forensics` | `feature_forensics` |
| `FeatureEvidenceSummaryService` | `get_summary` | `feature-evidence-summary` |

### 3.3 Key routers and heavy endpoints

**GET /api/sessions** (`api.py:553`): Paginated session list. For every session in the page (limit 50), calls `session_transcript_service.list_session_logs(s, core_ports)` with an internal limit of 5,000 rows (`sessions.py:92`). 50 pages × 5,000 rows = 250,000 log-row DB queries per list page — used only to extract `command_slug`, `latest_summary`, `subagent_type`, and `badge_data`. These are unmaterialized fields.

**GET /api/agent/planning/view** (`agent.py:696`): Fat-read bundle calling `get_planning_view_bundle` (`planning.py:2158`). Calls three sub-services **sequentially** (lines 2199, 2220, 2242); each independently calls `features.list_all → SELECT * LIMIT 5000` and `documents.list_all → SELECT * LIMIT 5000`. A `?include=graph,session_board` request triggers 6× full table scans.

**GET /api/agent/planning/command-center** (`agent.py:468`): No `@memoized_query`; no cache. Each request loads all features + all docs, iterates every feature through `_build_item`, and calls `subprocess.run(["git", ...])` per item (`worktree_git_state.py`) with a 5-second in-process per-path TTL and 0.8 s subprocess timeout.

**GET /api/agent/planning/command-center/{feature_id}** (`agent.py:514`): Calls `get_command_center_item` (`planning_command_center.py:559–578`), which internally calls `get_command_center(page_size=500)` and scans the results. There is no fast-path DB lookup by `feature_id`.

**GET /api/agent/planning/session-board** (`agent.py:621`): No `@memoized_query`. Fetches `list_paginated(offset=0, limit=500)` (`planning_sessions.py:609`) — all sessions, no cursor — then loads all features and entity_links for every feature.

### 3.4 Runtime profiles and bootstrap

Five explicit profiles declared in `backend/runtime/profiles.py:28–89`:

| Profile | watch | sync | jobs | auth | Primary use |
|---------|-------|------|------|------|-------------|
| `local` | yes | yes | yes | no | Dev workstation |
| `api` | no | no | **no** | yes | Enterprise HTTP server |
| `worker` | no | yes | yes | no | Analytics, telemetry, cache warming |
| `worker-watch` | yes | yes | yes | no | Live filesystem ingest |
| `test` | no | no | no | no | Test suite |

`RuntimeContainer.startup()` (`container.py:72–168`) executes the lifespan sequence: validate storage pairing → DB connect → run migrations → build core ports → start live event broker/listener → instantiate SyncEngine → start `RuntimeJobAdapter`. The startup sync runs as a non-blocking `asyncio.Task` (`adapters/jobs/local.py:9–10`); the worker is not ready until it completes.

Bootstrap entry points: `backend/main.py` → `bootstrap_local`; `backend/worker.py` → `build_worker_runtime()` (also triggers a module-level orphan container at `bootstrap_worker.py:86`).

**Completed vs Partial.** Runtime profiles fully implemented and enforced. Gap: `CCDASH_WORKER_WATCH_PROJECT_ID` is a compose-layer alias (`compose.yaml:166`) not a Python config field — k8s/bare-container operators must set `CCDASH_WORKER_PROJECT_ID` directly; `CCDASH_WORKER_STARTUP_SYNC_ENABLED` compose variable is never read by `config.py:961` (Python reads only `CCDASH_STARTUP_SYNC_ENABLED`).

---

## 4. Database

### 4.1 Dual migration paths

Two independent migration files with separate schema version counters:
- `backend/db/sqlite_migrations.py` — `SCHEMA_VERSION = 27` (line 16)
- `backend/db/postgres_migrations.py` — `SCHEMA_VERSION = 28` (line 11)

Both run idempotent `CREATE TABLE IF NOT EXISTS` DDL. `factory.py:47–51` dispatches to SQLite or Postgres repositories based on `CCDASH_DB_BACKEND`. `asyncpg.Pool` is used for Postgres (`connection.py:45`); the pool is typed as `asyncpg.Connection` in all Postgres repository constructors (`postgres/sessions.py:15`) — functionally correct for single-query calls but non-atomic for multi-statement sequences.

### 4.2 Repository pattern

Each entity type has a SQLite repository (`backend/db/repositories/`) and a Postgres repository (`backend/db/repositories/postgres/`). The factory selects at startup. There is no ORM — all SQL is hand-written. `ON DELETE CASCADE` is set on child tables (`session_logs`, `session_messages`, `session_file_updates`, etc.).

### 4.3 Schema highlights

`sessions` table: ~60 columns, includes `id TEXT PRIMARY KEY` (globally unique — no composite PK with `project_id`), `project_id`, token counts, cost fields, `session_forensics_json` BLOB (~19 KB avg, 175 MB total). `source_file` column exists but has **no index** (`repositories/sessions.py:161–167`).

`features` table: `id, project_id, title, status, category, priority, data_json, created_at, updated_at`. The full Feature payload (tags, owners, phases, linkedDocs, prRefs, dependencyState) lives in `data_json` BLOB (`sqlite_migrations.py:431`) — no columnar indexing for any of those fields.

`entity_links` table: `source_type, source_id, target_type, target_id, link_type, marker` — **no `project_id` column** (`sqlite_migrations.py:37–56`). Cross-project link isolation is impossible without a join.

`feature_phases`, `documents`, `tasks` — all have `project_id`. `session_logs`, `session_tool_usage`, `session_file_updates` — **no `project_id` column**.

### 4.4 The 10 GB anatomy

| Table | Row count | Storage |
|-------|-----------|---------|
| `session_logs` | 546,043 | **2,084 MB** — `tool_args` avg 717 B + `tool_output` avg 2,764 B, verbatim TEXT |
| `telemetry_events` | 918,374 | **1,648 MB** — `payload_json` avg 1.6 KB, max 2.3 MB, no TTL |
| `session_messages` | 385,508 | **1,232 MB** — parallel transcript storage; duplicates `session_logs.content` |
| `analytics_entries` | 1,798,056 | **466 MB** — 100% `period='point'`, zero pruning, ~10,000 rows/hour during active sync |
| `session_usage_attributions` | (large) | 385 MB |
| `sessions` | 9,246 | 199 MB |
| `analytics_entity_links` | 3,580,439 | 166 MB |
| **Total index overhead** | — | ~1.9 GB |

`analytics_entries` grows at approximately 3,313 rows per sync snapshot (10 project-level + ~3 metrics × ~367 features). At multiple syncs per hour, this is roughly 250 rows/minute during active sessions. No `DELETE` or prune method exists anywhere in `backend/db/repositories/analytics.py`.

`session_messages` is described as a "canonical transcript seam" (`sqlite_migrations.py:192`) but stores the same content as `session_logs.content` row-for-row — approximately 1.2 GB of duplicate storage. Approximately 1.75 GB of `session_logs` rows have never been purged after canonical `session_messages` rows were written.

### 4.5 Indexes present and notable absences

Key indexes confirmed present:

| Index | Table | Columns |
|-------|-------|---------|
| `idx_sessions_project` | sessions | `(project_id, started_at DESC)` |
| `idx_sessions_updated_at` | sessions | `(project_id, updated_at)` |
| `idx_features_status_updated` | features | `(project_id, status, updated_at)` |
| `idx_features_project_status` | features | `(project_id, status)` |
| `idx_phases_feature_status` | feature_phases | `(feature_id, status)` |
| `idx_analytics_lookup` | analytics_entries | `(project_id, metric_type, captured_at)` |
| `idx_links_upsert` | entity_links | UNIQUE `(source_type, source_id, target_type, target_id, link_type)` |
| `idx_telemetry_source_key` | telemetry_events | UNIQUE `(project_id, source_key)` |
| `idx_logs_session` | session_logs | `(session_id, log_index)` |

Notable absences:

| Missing index | Impact |
|---------------|--------|
| `idx_sessions_project_status_updated` on `sessions(project_id, status, updated_at)` | Defined in `sqlite_migrations.py:161–162` `_TABLES` DDL but never added as `_ensure_index` backfill — absent from live DB; `count_active` / `list_active` fall back to partial `idx_sessions_updated_at` |
| `idx_sessions_source_file` on `sessions(source_file)` | `list_by_source` (`sessions.py:161–167`) full table scan on every file-watch event |
| Partial index `analytics_entries WHERE period='point'` | 1.8 M rows dominated by `period='point'`; index does not filter on the dominant predicate |

Postgres-specific: `idx_links_upsert` (the UNIQUE constraint enabling `ON CONFLICT`) is added as a late migration step (`postgres_migrations.py:1491–1498`) rather than in initial DDL. On a fresh Postgres install, `ON CONFLICT` inserts silently succeed as duplicates before `_ensure_entity_link_uniqueness` runs.

**Completed vs Partial.** Dual migration paths functional; 184 indexes across all tables; WAL mode, `foreign_keys=ON`, `busy_timeout` all set (`connection.py:52–54`). Gap: `PRAGMA cache_size` not set (8 MB default for 10 GB DB); `PRAGMA synchronous` not set to NORMAL; `idx_sessions_project_status_updated` absent from live DB; analytics retention absent; `session_logs` / `session_messages` duplication not resolved; Postgres `upsert_logs` / `upsert_file_updates` not wrapped in transactions (`postgres/sessions.py:88+`).

---

## 5. Workers and Runtime

### 5.1 Five-profile runtime

Profiles and capabilities are fully declared and enforced at `backend/runtime/profiles.py:28–89`. The `api` profile has `jobs=False` — no background jobs run in the API container. Workers own all background work.

### 5.2 InProcessJobScheduler

The only scheduler implementation (`backend/adapters/jobs/local.py:8–10`):

```python
class InProcessJobScheduler:
    def schedule(self, job: Awaitable[Any], *, name: str | None = None) -> asyncio.Task[Any]:
        return asyncio.create_task(job, name=name)
```

No queue, retry, priority, backpressure, supervision, or dead-letter handling. All five job slots share the asyncio event loop. A crashed task records `"idle"` not `"dead"` in the probe status snapshot (`adapters/jobs/runtime.py:385–420`).

### 5.3 Five startup/periodic jobs

| Job | Profiles | Interval | Scope |
|-----|----------|----------|-------|
| `startupSync` | worker, worker-watch, local | once at startup | active/bound project only |
| `analyticsSnapshots` | all with jobs | 900 s default | active/bound project only |
| `telemetryExports` | `worker` only | 900 s default | global outbound queue |
| `artifactRollupExports` | `worker` only | 3,600 s default | global artifact cache |
| `cacheWarming` | all with jobs | 300 s default | active/bound project only; 2 of 14 endpoints |

`TelemetryExporterJob` and `ArtifactRollupExportJob` are gated to `profile.name == "worker"` (`container.py:144–156`). A `worker-watch`-only deployment never flushes telemetry.

Analytics snapshots and cache warming use `bound_project or workspace_registry.get_active_project()` (`adapters/jobs/runtime.py:793–838`). In enterprise multi-project mode, `get_active_project()` returns the single global active project; N-1 projects receive no warming.

### 5.4 Worker probe

Dedicated probe HTTP server on `CCDASH_WORKER_PROBE_PORT` (default 9465; worker-watch uses 9466). Endpoints: `/livez`, `/readyz`, `/detailz`. Probe fields include `lastStartedAt`, `lastFinishedAt`, `lastOutcome`, `lastError`, `checkpointFreshnessSeconds`, `backlogCount` (`bootstrap_worker.py:31–67`). Worker readiness requires `worker_binding` to resolve. Worker-watch readiness additionally requires `watcher_runtime` and `startup_sync`.

### 5.5 Telemetry exporter and artifact rollup

`TelemetryExporterJob` (`backend/services/integrations/telemetry_exporter.py`) batches `ExecutionOutcomePayload` rows from `outbound_telemetry_queue` and POSTs to the SAM endpoint. `ArtifactRollupExportJob` (`artifact_rollup_export_job.py`) pushes `ArtifactOutcomePayload`. Both registered from `backend/runtime/container.py` and emit through `backend/observability/otel.py`. Full SkillMeat artifact intelligence pipeline (snapshot/ranking/recommendation/rollup) is wired and complete.

### 5.6 Postgres NOTIFY live bus

In enterprise mode: worker publishes session-sync events via `PostgresNotifyLiveEventBus`; API container subscribes via `postgres_listener.py` and republishes to the in-memory SSE broker. The listener has no reconnect or backoff logic — a dropped Postgres connection permanently stops live fan-out until container restart (`adapters/live_updates/postgres_listener.py`, deferred FU-2).

**Completed vs Partial.** Five-profile runtime complete; probe server complete; Postgres NOTIFY/LISTEN live bus complete. Gap: `InProcessJobScheduler` no supervision; no durable task queue; `telemetry`/`artifact` jobs absent from `worker-watch` profile; analytics/warming only cover the active/bound project; worker startup sync disabled by default in compose enterprise worker.

---

## 6. Session Ingestion and Filesystem

### 6.1 Parsers

`backend/parsers/sessions.py` — parses JSONL files into `AgentSession` objects. `backend/parsers/documents.py` — frontmatter + markdown body for plan docs. `backend/parsers/features.py`, `progress.py` — feature/progress YAML+Markdown hybrids.

### 6.2 SyncEngine

`backend/db/sync_engine.py` — approximately 6,000 lines. The main entry point is `sync_project(project_id, sessions_dir, docs_dir, progress_dir, ...)`. Phases:

1. `_sync_sessions`: `rglob("*.jsonl")` full scan of `sessions_dir`, stat + DB lookup per file (`sync_engine.py:4107–4119`). No manifest-based skip (documents have `_light_mode_scan_skip` at lines 4239–4278; sessions do not).
2. `_sync_documents`, `_sync_progress`, `_sync_feature_phases`: use `_rglob_cache` memo (reset per `sync_project` call) to share OS traversal within a run.
3. `_rebuild_entity_links`: `link_repo.upsert()` issues `await self.db.commit()` per link (`entity_graph.py:40`) — 25,000 individual commits during a full rebuild.
4. `_capture_analytics`: per-feature N+1 — `task_repo.list_by_feature` + `link_repo.get_links_for` + per-linked-session `session_repo.get_by_id` (`sync_engine.py:5874–5960`), approximately 12,000–15,000 DB queries per snapshot for 367 features.
5. Backfill pipelines (`_maybe_backfill_telemetry_events`, `_maybe_backfill_commit_correlations`, etc.): sequential single-row DB round-trips, not batched.

SyncEngine instantiation is gated by `_sync_engine_enabled()` (`container.py:237–242`): returns `False` for enterprise profile when `filesystem_source_of_truth = False`.

### 6.3 FileWatcher singleton

`file_watcher = FileWatcher()` at module scope (`file_watcher.py:307`). One process = one watcher = one set of paths = one project. Live file-change events dispatch to `sync_changed_files()`. The watcher uses `watchfiles.awatch` (`file_watcher.py:183`), which defaults to `inotify` on Linux. Docker Desktop bind mounts on macOS do not deliver inotify events; `WATCHFILES_FORCE_POLLING` defaults `false` in compose.

Watcher health probe reports `running`, `configured_no_paths`, `stopped`, or `error`. When watch paths resolve to non-existent container directories (`FilesystemProjectPathProvider.resolve` calls `Path(raw_value).expanduser().resolve(strict=False)` at `project_paths/providers/filesystem.py:25–28`), `_resolve_watch_paths` silently filters them (`file_watcher.py:260`), and the watcher settles in `configured_no_paths` state — not a readiness failure.

**Watcher-triggered delete bug**: `sync_changed_files` path calls `session_repo.delete_by_source(str(path))` (raw string, `sync_engine.py:3944`), but the full-sync path correctly uses `delete_by_source(sync_file_path)` (canonical key, `sync_engine.py:4171`). Watcher-triggered deletes leave orphaned DB rows.

Watcher rebind (`rebind_watcher`, `adapters/jobs/runtime.py:198–338`) — atomic stop/drain/start for in-process project switching. No concurrency mutex; simultaneous `POST /api/projects/active/` calls can race.

### 6.4 Source-identity aliasing

`SourceRootAlias` + `source_identity_policy_from_env()` (`backend/services/source_identity.py:271–308`) build path-remapping aliases from `CCDASH_WORKSPACE_HOST_ROOT`/`CCDASH_WORKSPACE_CONTAINER_ROOT`, `CCDASH_CLAUDE_HOME`/`CCDASH_CLAUDE_CONTAINER_HOME`, and up to 6 additional mount pairs. Canonical key scheme: `ccdash-source:v1/{project}/{kind}/{root}/{rel}` (`source_identity.py:120–138`).

When no alias matches an observed path, the fallback produces `opaque/<sha256[:32]>` keys (`source_identity.py:175–185`). The alias policy is populated only from env vars — not derived automatically from `ResolvedProjectPaths`.

### 6.5 Light-mode startup skip

`CCDASH_STARTUP_SYNC_LIGHT_MODE` (default `false`, `config.py:966`) enables a manifest-based scan skip for document and progress `.md` files (`sync_engine.py:4239–4278`). Sessions have **no equivalent skip** — always full `rglob` + N DB lookups. Three different default values exist across `config.py` (False), `runtime.py:731` (getattr fallback True), and `sync_engine.py:4261` (getattr fallback False) — a three-way default disagreement.

### 6.6 Live ingest (Postgres NOTIFY → SSE)

Worker publishes session-sync events to Postgres NOTIFY channel after each successful sync. API container listens via `postgres_listener.py` and republishes to `InMemoryLiveEventBroker`. Frontend subscribes via `GET /api/live/stream` SSE endpoint (`backend/routers/live.py`). `useLiveInvalidation` hook in frontend processes events and calls `queryClient.invalidateQueries()`.

**Completed vs Partial.** Parsers, SyncEngine, light-mode document skip, canonical source key scheme, Postgres NOTIFY live ingest, watcher health probe — all complete. Gap: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults `false`; no readiness failure on zero watch paths; watcher-triggered delete uses raw path; no session scan manifest skip; `STARTUP_SYNC_LIGHT_MODE` three-way default mismatch; Postgres listener no reconnect/backoff; source-identity alias not auto-derived.

---

## 7. Caching

### 7.1 Backend in-process cache

Single `TTLCache(maxsize=512, ttl=_effective_ttl)` module-level singleton (`cache.py:50`). `_effective_ttl` is fixed at import time from `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 600 s, `config.py:983`). Thread-safety: single-threaded asyncio loop only. All 512 entries share one TTL — no per-bucket TTL differentiation.

`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (default 10 s) and `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` (default 30 s) are documented in `config.py:987–1023` and echoed in service comments, but **neither is read by `cache.py`** — the global 600 s TTL applies to all keys. Operators setting these env vars see no effect on actual cache behavior.

### 7.2 `@memoized_query` decorator

Defined at `cache.py:328–492`. On every call (cache hit or miss), the decorator first calls `get_data_version_fingerprint()` which issues **6 sequential DB queries** (`cache.py:84–142`):

| # | Table | Query | Project scope |
|---|-------|-------|---------------|
| 1 | `sessions` | `MAX(updated_at)` | project-scoped |
| 2 | `features` | `MAX(updated_at)` | project-scoped |
| 3 | `feature_phases` | `COUNT + GROUP_CONCAT(all phase markers)` | project-scoped via JOIN |
| 4 | `documents` | `MAX(updated_at)` | project-scoped |
| 5 | `entity_links` | `COUNT + GROUP_CONCAT(all markers)` | **global — no project_id filter** |
| 6 | `planning_worktree_contexts` | `MAX(updated_at)` | project-scoped |

Query 5 (`cache.py:258–289`) performs a full-table `GROUP_CONCAT` with `ORDER BY` across all rows in `entity_links` with no `WHERE` clause — an O(N_total_links) scan across all projects on every fingerprint call. The fingerprint result is **not itself cached** — 6 DB queries fire on every request before any cache key is checked.

Cache key format: `{endpoint_name}:{project_id}:{param_hash}:{fingerprint}` (`cache.py:294–317`). No cross-project leakage. `system_active_count` uses scope `"global"`.

14 service methods carry `@memoized_query`. Notable uncached high-traffic paths: `PlanningCommandCenterQueryService.get_command_center` (V1), `PlanningSessionQueryService.get_session_board`, all session CRUD endpoints, legacy `GET /api/features`.

### 7.3 Background warming

`_start_cache_warming_task()` (`adapters/jobs/runtime.py:840–982`) runs at `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` (default 300 s) and warms exactly **2 of 14** cached endpoints: `project_status` and `workflow_diagnostics`. Only runs in `jobs=True` profiles. The `api` profile has `jobs=False` — the API container that serves traffic receives **zero background warming**. The worker warms its own in-process cache, which is invisible to the API container.

### 7.4 Frontend TanStack Query staleTime tiers

Documented in `docs/guides/feature-surface-architecture.md`:
- **Server memoized_query** (`~600 s`) — backend cache tier
- **Client TQ hot** (0–30 s `staleTime`) — live surfaces: planning summary (`staleTime: 0`), feature surface list (`staleTime: 0`), dashboard bundle (`staleTime: 10 s`)
- **Client TQ warm** (30–60 s `staleTime`) — most domain queries
- **Client TQ cold** (300 s `staleTime`) — project list

`bypass_cache=True` query param supported on all cached agent endpoints (`agent.py:137,235,270,287,318,356,393`). ✓

Cache status endpoint: `GET /api/cache/status` (`backend/routers/cache.py:219–273`). ✓

Single `clear_cache()` call site in production code: `PlanningQueryService.resolve_open_question` (`planning.py:1567`) — clears all 512 entries (not project-scoped). No `clear_cache()` after `sync_project()` completes.

**Completed vs Partial.** `@memoized_query` decorator with fingerprint, project-scoped keys, bypass param, cache-status endpoint, OTEL hit/miss counters — all complete. Frontend TQ per-hook staleTime configuration and two-tier architecture documentation complete. Gap: in-process cache not shared across enterprise api+worker containers; per-metric TTLs phantom; no sync-triggered invalidation; fingerprint is global (entity_links has no project_id); fingerprint not itself cached; warming covers 2/14 endpoints; warming absent from api profile; cache maxsize 512 insufficient for multi-project × multi-endpoint load.

---

## 8. Multi-Project Behavior

### 8.1 Project registry (projects.json)

`ProjectManager` persists all registrations to `config.PROJECT_ROOT / "projects.json"` (`project_manager.py:287`). The file stores `activeProjectId` + `projects[]` array with full path configs. Currently 5 projects registered (including the active `3df0ff70 / SkillMeat`). `_save()` is synchronous `write_text` with no file lock or atomic rename — torn file risk on concurrent writes.

In a containerized deployment, `projects.json` is mounted `read_only: true` (`compose.yaml:48`). `ProjectManager._save()` writes on startup if migration is detected (`project_manager.py:100`), which raises `PermissionError` with a read-only mount.

`CCDASH_PROJECTS_FILE` env var appears in `container_project_onboarding.py` output but is **never read by `config.py` or `ProjectManager`** — it is a dead variable.

### 8.2 Request-scoped project resolver

`resolve_project()` (`backend/application/services/common.py:93–120`) resolution order:
1. Explicit `requested_project_id` param
2. `X-CCDash-Project-Id` header or JWT `claim_scope.project_id`
3. Hosted principal without project → 404
4. Global fallback: `workspace_registry.get_active_project()`

Step 4 routes all headerless requests to the global active project — a process-wide side-channel. `POST /api/projects/active/{id}` is blocked for hosted requests (`routers/projects.py:138–147`), so in enterprise mode the only scoping mechanism is the request header.

Frontend: `setApiProjectScope(project.id)` stores selected project in `localStorage` under `ccdash:selected-project-id:v2` and attaches `X-CCDash-Project-Id` header (`services/apiClient.ts:178–231`). `switchProject()` calls `POST /api/projects/active/{id}` then `setApiProjectScope` then `queryClient.clear()`. ✓ for single-tab; multi-tab multi-project: last writer wins on `localStorage`.

### 8.3 DB project_id columns

Present on: `sessions`, `documents`, `tasks`, `features`, `analytics_entries`, `telemetry_events`, `session_usage_events`, `commit_correlations`, `session_relationships`. ✓

Missing on: `session_logs`, `session_tool_usage`, `session_file_updates` — these rely entirely on `session_id` FK uniqueness. `sessions.id TEXT PRIMARY KEY` is globally unique (not a composite `(project_id, session_id)`) — cross-project session ID collision silently overwrites the prior session's `project_id`.

`entity_links` has no `project_id` column at all (`sqlite_migrations.py:37–56`).

### 8.4 Active-project endpoint and watcher rebind

`POST /api/projects/active/{id}` (`routers/projects.py`) triggers atomic watcher rebind: stop old watcher → drain pending → start on new project's paths. Implemented in `adapters/jobs/runtime.py:198–338` (commit b1c83e4). No concurrency mutex on `rebind_watcher` — concurrent calls can race.

### 8.5 CLI project group

`packages/ccdash_cli/src/ccdash_cli/commands/project.py` — `ccdash project add/list/use` commands communicating to server over HTTP via `backend/routers/client_v1.py`. Backend CLI override: `--project` flag at `backend/cli/main.py:37`. ✓

### 8.6 Multi-project command center fan-out

`MultiProjectPlanningCommandCenterQueryService` (`multi_project_planning_command_center.py`) fans out over all registered projects with `asyncio.Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY=10)`. Uses `_NullGitProbe` for off-page items (MPCC-206 pattern). `@memoized_query("mpcc_command_center")`. ✓

Frontend: gated behind `MULTI_PROJECT_COMMAND_CENTER_ENABLED` — a Vite build-time constant resolved from `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED` at build (`constants.ts:399–421`), defaulting `false`. Changing it in a container requires a rebuild.

**Completed vs Partial.** DB project_id columns on most top-level tables; `resolve_project()`; MPCC fan-out; CLI project group; active-project endpoint with watcher rebind — all complete. Gap: `projects.json` not DB-backed; watcher singleton (one project at a time); session PK not composite; `session_logs` no `project_id`; `entity_links` no `project_id`; multi-project command center build-time gated; analytics/cache warming single-project; rebind no mutex; TQ cache not invalidated on project switch (gap — `queryClient.clear()` is called but `invalidateQueries` per-project is not).

---

## 9. Enterprise/Container Behavior

### 9.1 Dockerfile

`deploy/runtime/Dockerfile` — multi-stage image, non-root `ccdash` user, entrypoint dispatches on `CCDASH_RUNTIME_PROFILE` for `local`, `api`, `worker`. **`worker-watch` is absent from `entrypoint.sh:10–24`** — `compose.yaml` works around this via a `command:` override (`compose.yaml:162`); removing the override causes crash.

### 9.2 compose.yaml topology

Primary file: `deploy/runtime/compose.yaml`. Service graph (enterprise + postgres + live-watch profiles):

```
postgres       (profile: postgres)  healthcheck: pg_isready
  → api        (profile: enterprise) depends_on: postgres:service_healthy (required: false)
    → worker   (profile: enterprise) depends_on: api:service_healthy
worker-watch   (profile: live-watch) depends_on: api + postgres (required: false)
frontend       (profile: local|enterprise) NO depends_on:api  ← 502s at startup
```

`frontend` has no `depends_on: api` — serves 502 Bad Gateway responses until API becomes healthy.

### 9.3 x-backend-service anchor and volumes

`x-backend-service` anchor (`compose.yaml:44–84`) binds to every backend service:

| Mount | Host default | Container target | read_only |
|-------|-------------|------------------|-----------|
| `projects.json` | `../../projects.json` | `/app/projects.json` | **true** |
| workspace root | `../../..` | `${CCDASH_WORKSPACE_CONTAINER_ROOT:-/workspace}` | true |
| claude home | `~/.claude` | `/home/ccdash/.claude` | true |
| codex home | `~/.codex` | `/home/ccdash/.codex` | true |
| optional mounts 1–6 | `./empty-mounts/optional-N` | `/mnt/ccdash/optional-N` | true |

`projects.json` stores raw host-absolute paths (e.g. `root.filesystemPath: /Users/miethe/dev/homelab/development/skillmeat`). `FilesystemProjectPathProvider.resolve()` calls `Path(raw_value).expanduser()` verbatim (`project_paths/providers/filesystem.py:25–28`) — host paths do not resolve inside the container. Source-identity aliasing (`source_identity.py:271–308`) operates on session key canonicalization during sync but does **not** rewrite paths used for initial directory open. This is the primary root cause of zero filesystem ingestion in containers.

### 9.4 Enterprise ingestion defaults (the silent empty-DB problem)

Three independent defaults, each sufficient to cause silent empty-DB deployments:

| Default | Location | Effect |
|---------|----------|--------|
| `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: false` | `compose.yaml:27` (x-backend anchor) | `_sync_engine_enabled()` returns `False` (`container.py:237–242`); no SyncEngine instantiated; no ingest |
| `CCDASH_WORKER_STARTUP_SYNC_ENABLED: false` | `compose.yaml:133` (worker service) | No initial filesystem scan even if ingestion were enabled |
| `live-watch` profile not in default startup | `compose.yaml:159–193` requires `--profile live-watch` | `worker-watch` — the only service with both flags `true` — not started by default |

`docker compose --profile enterprise --profile postgres up` produces a fully healthy service with an empty database.

### 9.5 Postgres wiring

Connection string injected: `CCDASH_DATABASE_URL: "postgresql://ccdash:ccdash@postgres:5432/ccdash"` (`compose.yaml:89`). Pool created via `asyncpg.create_pool` (`connection.py:45`). Both `api` and `worker` run `run_migrations()` on startup (`container.py:106–108`). No `pg_advisory_lock` — DDL race on fresh Postgres with simultaneous api+worker startup (functionally safe under Postgres `CREATE TABLE IF NOT EXISTS` semantics, but `schema_version` insert is not atomic).

Postgres health gate: `api` depends on `postgres:service_healthy` (required: false); `worker` depends on `api:service_healthy`. ✓

### 9.6 Frontend nginx

`frontend` service runs nginx with proxy rules for `/api/`, `/api/v1/`, and SSE `/api/live/stream`. Image < 50 MB. Planning fonts loaded from Google Fonts CDN (`PlanningRouteLayout.tsx:31–48`) — fails silently in restricted-egress containers.

### 9.7 compose.hosted.yml

Legacy topology (`deploy/runtime/compose.hosted.yml`) is diverged: separate `api/Dockerfile` and `worker/Dockerfile` with no user hardening (`USER` directive absent, runs as root); worker has no `CCDASH_WORKER_PROJECT_ID` (startup crash); no filesystem bind mounts for workspace/claude/codex paths (live ingest impossible). Not aligned with the current compose strategy.

### 9.8 External-Postgres override

`deploy/runtime/compose.external-postgres.yaml` uses `!reset` to drop the `depends_on:postgres` edge — correct Podman-compat override for operators supplying their own database. ✓

### 9.9 CORS

`bootstrap.py:57–66` always allows `http://localhost:3000` and `http://127.0.0.1:3000` regardless of `CCDASH_FRONTEND_ORIGIN` — a security concern in production. Default compose: `CCDASH_FRONTEND_ORIGIN: "${CCDASH_FRONTEND_ORIGIN:-http://localhost:${CCDASH_FRONTEND_PORT:-3000}}"` (`compose.yaml:19`).

**Completed vs Partial.** Multi-stage Dockerfile, compose enterprise/postgres/live-watch profiles, x-backend anchor with workspace/claude/codex bind mounts, Postgres health gate, idempotent migrations, external-Postgres override, worker probe — all complete. Gap: `entrypoint.sh` missing `worker-watch` case; `frontend` missing `depends_on:api`; `projects.json` read_only + write-on-startup conflict; `CCDASH_PROJECTS_FILE` dead variable; host paths in `projects.json` not container-path-translated; `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults false; no e2e container smoke test; `compose.hosted.yml` diverged and broken; no `pg_advisory_lock` on migrations.

---

## Appendix A: Completed-Work Inventory (Top 20)

| Feature / PRD | Status | Key Artifacts |
|---------------|--------|---------------|
| containerized-deployment-v1 | COMPLETE | `deploy/runtime/Dockerfile`, `compose.yaml`, `compose.hosted.yml` |
| deployment-runtime-modularization-v1 | COMPLETE | `backend/runtime/profiles.py`, `bootstrap_worker.py` |
| data-platform-modularization-v1 | COMPLETE | `backend/config.py`, `backend/data_domains.py`, `backend/runtime/storage_contract.py` |
| sse-live-update-platform-v1 | COMPLETE | `backend/adapters/live_updates/in_memory_broker.py`, `backend/routers/live.py` |
| enterprise-live-session-ingest-v1 | COMPLETE (PRD status stale at 'draft') | `backend/runtime/profiles.py:65`, `container.py:111–118`, `compose.yaml:159` |
| live-ingest-source-path-canonicalization-hardening-v1 | COMPLETE | `source_identity.py`, canonical key scheme |
| session-transcript-append-deltas-v1 | COMPLETE | canonical transcript repo, SSE delta application |
| db-caching-layer-v1 | COMPLETE | `backend/db/` message-level storage, Postgres-ready session tables |
| ccdash-query-caching-and-cli-ergonomics-v1 | COMPLETE | `cache.py:328`, TTLCache, `--no-cache` flag, `POST /api/cache/invalidate` |
| runtime-performance-hardening-v1 | COMPLETE | transcript ring-buffer, react-virtual, link rebuild dedup/throttle |
| ccdash-frontend-data-layer-refactor (TQ migration) | COMPLETE (phases 0–7) | `services/queries/`, `queryKeys.ts`, 176 guardrail tests |
| feature-surface-data-loading-redesign-v1 | COMPLETE | `useFeatureSurface`, feature card rollup endpoints, lazy modal sections |
| ccdash-hexagonal-foundation-v1 | COMPLETE | repo/service/router split, all 6 phases |
| ccdash-planning-control-plane-v1 | COMPLETE | `PlanningHomePage`, `/api/agent/planning/*`, agent session board |
| planning-command-center-v1 | COMPLETE (PRD status stale at 'draft') | `PlanningCommandCenter.tsx`, list/card/board views |
| multi-project-planning-command-center-v1 | COMPLETE (feature-flagged OFF) | `MultiProjectCommandCenter.tsx`, `multi_project_planning_command_center.py` |
| planning-forensics-boundary-extraction-v1 | COMPLETE | all 6 phases |
| shared-auth-rbac-sso-v1 | COMPLETE | RBAC bearer token, `CCDASH_API_BEARER_TOKEN`, `authGuardrail` |
| ccdash-planning-reskin-v2 | COMPLETE | planning-tokens.css, OKLCH design tokens, modal-first nav |
| SkillMeat artifact intelligence exchange v1 | COMPLETE | snapshot/ranking/recommendation/rollup surfaces, SAM telemetry exporter |

---

## Appendix B: Issue Severity Summary (130 total)

| Severity | Count | Primary areas |
|----------|-------|---------------|
| CRITICAL | 20 | container (5), database (4), caching (2), ingestion (2), workers (2), multi-project (2), backend (2), data-contracts (2) |
| HIGH | 56 | database (11), container (10), backend (9), workers (7), frontend (5), caching (5), ingestion (4), multi-project (4), perf (3) |
| MEDIUM | 45 | database (8), container (8), caching (5), frontend (5), perf (5), workers (4), ingestion (3), integration (2), multi-project (2), ux (2), backend (2) |
| LOW | 9 | ux (2), perf (2), caching (1), workers (1), frontend (1), multi-project (1), integration (1) |

The 20 CRITICAL issues decompose into three root causes: (1) containerized enterprise build ingests zero data by default; (2) in-process cache per-container perpetually cold/inconsistent; (3) `projects.json` as sole project store broken in multi-replica containers. All three are wiring/defaults/hardening defects, not architectural rewrites.
