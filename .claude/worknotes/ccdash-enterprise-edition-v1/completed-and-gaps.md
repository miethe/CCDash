# CCDash Enterprise Investigation — Completed-Work & Gaps Ledger

Per-domain ledger of what is already shipped (+) vs missing (-). Source: 12-domain investigation 2026-05-30.

```

### frontend-core
COMPLETED:
  + TanStack Query v5 (^5.100.14) fully wired — QueryClientProvider at root, queryClientRef.useRef-stabilized (App.tsx:87): done
  + AppEntityDataContext.tsx deleted (T4-005) — confirmed by architecture test contexts/__tests__/dataArchitecture.test.ts:54: done
  + Domain query hooks migrated: sessions, documents, tasks, features, alerts, notifications, projects, health, planning summary/featureContext/sessionBoard, dashboard bundle, analytics overview, feature surface (T1-T5): done
  + Fat-read bundles: useDashboardBundleQuery GET /api/v1/dashboard (T5-005), usePlanningViewQuery GET /api/agent/planning/view (T5-007), useAnalyticsOverviewQuery GET /api/analytics/overview-bundle (T5-007 best-effort): done
  + refetchOnWindowFocus: false globally in lib/queryClient.ts:35: done
  + queryClient.clear() on project switch (DataContext.tsx:197): done
  + Lazy route code-splitting for all pages via React.lazy in App.tsx:29-47: done
  + Virtualization on SessionInspector transcript (TranscriptView.tsx:2448), ProjectBoard feature list (ProjectBoard.tsx:3483), PlanCatalog doc lists (PlanCatalog.tsx:590,596), MultiProjectCommandCenter (MultiProjectCommandCenter.tsx:97), MultiProjectSessionBoard columns (MultiProjectSessionBoard.tsx:337): done
  + SSE live invalidation infrastructure: LiveConnectionManager with backoff, visibility-aware pause, cursor tracking (services/live/connectionManager.ts): done
  + Memory guard: mergeSessionDetail ring-buffer cap (dataContextShared.ts:55-65), document cap via select transform (services/queries/documents.ts:76-77): done
  + Session page size 50 with infinite scroll (services/queries/sessions.ts:17,41): done
  + Feature surface two-tier TQ architecture with rollup-tier staleTime:30_000 (services/useFeatureSurface.ts:381-398): done
  + PlanningAgentSessionBoard.tsx SessionCard and BoardColumn wrapped in React.memo (lines 362, 723): done
  + MultiProjectSessionBoard sub-components memo-wrapped (WorkerRow:92, AggregateSessionCardView:128, CardList:328, BoardGroupColumn:419): done
GAPS:
  - useData() shim reactive subscription: 7 domain arrays read via getQueryData() (snapshot) not useQuery() (reactive) — 13+ components silently see stale data after TQ background-refetches
  - useFeaturesQuery refetchInterval: 5_000 when SSE disabled — enterprise default, creates 12 req/min on large projects; should be 30_000 minimum
  - useFeatureSurface list tier staleTime: 0 — refetches on every Dashboard and ProjectBoard mount; needs minimum 10-30 s staleTime
  - Dashboard analytics series fetches (3 calls) outside TQ with sessions.length/tasks.length effect dependency — not migrated in T5-007
  - AnalyticsDashboard.tsx: 7 parallel raw fetches on every mount including getArtifacts({limit:200}) — entire component outside TQ
  - Manual setInterval polls: Dashboard live-agents (10 s), SystemMetricsChip (30 s), ProjectBoard feature modal (15 s), OpsPanel operations (2.5-15 s adaptive), OpsPanel telemetry (10 s), SessionInspector (2 locations), FeatureExecutionWorkbench, TestVisualizer
  - React.memo missing on inner panels of SessionInspector (6101 lines) and ProjectBoard (3895 lines) — full re-render on any state change
  - GEMINI_API_KEY baked into Vite bundle via define — security issue in enterprise container builds
  - Documents: page size 500, max 2000 in memory — excessive for large enterprise projects; no lazy/on-demand loading for PlanCatalog
  - Session transcript cap MAX_SESSION_LOG_ROWS=5000 per session in React state — may be excessive for memory-constrained containers
  - No SSR or query prefetching — all data loaded after first render; remote backends in containers create visible loading waterfalls on every page navigation
  - ProjectBoard feature modal setInterval (15 s) should be replaced with TQ refetchInterval on the feature detail query
  - SSE for features, tests, ops defaulted off in .env.example — enterprise operators must manually enable; no documentation in deploy/ guides

### planning-frontend
COMPLETED:
  + Modal-first navigation routing: planningRouteFeatureModalHref enforces /planning?feature=<id>&modal=feature&tab=<tab> (services/planningRoutes.ts:41) — done
  + TanStack Query migration for planning summary, feature context, session board queries (services/queries/planning.ts:61-175) — done
  + usePlanningViewQuery fat-read bundle (T5-007): single above-fold GET /api/agent/planning/view on cold load (services/queries/planning.ts:226) — done
  + Live invalidation subscription via useLiveInvalidation wired to planning summary (PlanningHomePage.tsx:969-978) — done
  + Status bucket + signal URL filter state with usePlanningFilter (services/planningRoutes.ts:155) — done
  + PlanningAgentSessionBoard: per-grouping TQ query, URL-driven grouping mode, stale indicator, detail panel, Prepare Next Run (PlanningAgentSessionBoard.tsx) — done
  + PlanningAgentSessionDetailPanel: full session forensics UI including lineage, evidence, token context, activity timeline, quick actions (PlanningAgentSessionDetailPanel.tsx) — done
  + MultiProjectCommandCenter shell + query hooks (gated behind flag) with TQ-backed aggregate queries (MultiProjectCommandCenter.tsx, services/queries/planning.ts:286-390) — partial
  + MultiProjectSessionBoard with per-column virtualization (threshold 250) using @tanstack/react-virtual (MultiProjectSessionBoard.tsx:41,337) — partial
  + MultiProjectCommandCenter work-item list virtualization (threshold 250) (MultiProjectCommandCenter.tsx:68,97) — partial
  + CommandCenterListView: dense 6-column list with expand/collapse and EditableCommandField (CommandCenterListView.tsx, CommandCenterFeatureRow.tsx) — done
  + CommandCenterBoardView: 5-bucket kanban (needs-plan/ready/active/blocked/done) with overflow-x scroll (CommandCenterBoardView.tsx) — done
  + CommandCenterCardView: card grid view mode (CommandCenterCardView.tsx) — done
  + PhasePlanTable: phase-by-phase table with status, story points, agent, files (PhasePlanTable.tsx) — done
  + Feature hover-prefetch wired (mouseEnter/onFocus) — partial (bypasses TQ cache)
  + Planning density toggle (comfortable/compact) with localStorage persistence (PlanningRouteLayout.tsx) — done
  + FeatureDetailShell: 7-tab modal (overview, phases, docs, relations, sessions, history, test-status) with aria and keyboard navigation (FeatureDetailShell.tsx) — done
  + Attention columns: stale, blocked, mismatched/reversed features in PlanningSummaryPanel (PlanningSummaryPanel.tsx) — done
  + PlanningTopBar: live-agent pill derived from useData sessions, Cmd-K handler registered (stub) (PlanningTopBar.tsx) — partial
  + CCDASH_PLANNING_CONTROL_PLANE_ENABLED gate + DisabledShell rendering (PlanningHomePage.tsx:1018) — done
GAPS:
  - Server-side pagination for session-board endpoint (currently returns all sessions with no cursor/page)
  - TanStack Query migration for V1 PlanningCommandCenter (currently raw useEffect + local state)
  - Viewport-deferred mounting for session board and command center on planning home (currently always-mounted)
  - Correct hover-prefetch using queryClient.prefetchQuery to populate TQ cache
  - Virtualization for V1 PlanningAgentSessionBoard BoardColumn (currently CSS-scroll only)
  - Runtime-configurable MULTI_PROJECT_COMMAND_CENTER_ENABLED via capabilities endpoint
  - useProjectListReady gate for multi-project queries (currently hardcoded projectListReady:true)
  - Self-hosted fonts to eliminate Google Fonts CDN dependency in container deployments
  - Cmd-K cross-feature/cross-project command palette (currently stub)
  - New Spec / artifact creation workflow (currently stub)
  - Real historical per-day aggregate data for sparklines (currently synthesized)
  - Real token-saved telemetry (ctxPerPhase, tokensSavedPct from backend — T2-001 TODO)
  - PlanningSummaryPanel attention column click-through beyond ROW_LIMIT=8
  - V1 command center pagination UI (currently pageSize=50, no page > 1 access)
  - Live invalidation (SSE) wired to session board and command center (currently only planning summary)

### backend-api
COMPLETED:
  + Transport-neutral agent_queries layer extracted from REST/CLI/MCP: done
  + @memoized_query decorator with TTL + fingerprint caching: done for project_status, feature_forensics, planning_project_summary, planning_project_graph, planning_feature_context, planning_phase_ops, aar_report, analytics_overview_bundle, dashboard_bundle, mpcc_command_center, mpss_session_board, system_active_count, live_active_count
  + Bundle endpoint GET /api/agent/planning/view with optional include= sub-payloads: done
  + Planning command center pagination (page/page_size params): done
  + MPCC-206 NullGitProbe for off-page items in multi-project command center: done (partial — only multi-project, not V1 single-project)
  + asyncio.Semaphore concurrency guard on multi-project and system-metrics fan-out: done
  + Feature-scoped entity_links batch load (get_links_for_many): done
  + Session list pagination (PaginatedResponse with offset/limit): done
  + Session logs endpoint with cursor-based pagination (GET /api/sessions/{id}/logs): done
  + Feature context @memoized_query caching: done
  + Cache-Control header on system/active-count: done
GAPS:
  - Session list N+1 log-fetch: command_slug, latest_summary, subagent_type, badge_data must be materialized in sessions table
  - View bundle parallel sub-call execution (asyncio.gather) with shared data load pass
  - @memoized_query on single-project PlanningCommandCenterQueryService.get_command_center
  - Fast-path get_command_center_item by feature_id (no full 500-item page scan)
  - entity_links fingerprint project-scoping (currently cross-project full-table aggregate)
  - feature_phases fingerprint O(N) GROUP_CONCAT replaced with MAX(updated_at) + COUNT(*)
  - SELECT * list_all replaced with column-projected list_summary variants for planning summary paths
  - @memoized_query on PlanningSessionQueryService.get_session_board
  - NullGitProbe in V1 single-project command center build phase
  - Background cache warm-up job wired to CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS
  - TTLCache maxsize raised from 512 to support multi-project × multi-endpoint load
  - Session detail multi-query fan-out batched into fewer round-trips
  - Entity_links table: missing project_id column prevents efficient project-scoped queries

### database
COMPLETED:
  + Dual SQLite + Postgres migration paths implemented (sqlite_migrations.py + postgres_migrations.py): done
  + Factory pattern (factory.py) dispatching to SQLite vs Postgres repositories for all entity types: done
  + asyncpg.Pool-based connection for Postgres with Pool.acquire/transaction helper: done (partial — _transactions.py exists but not used consistently)
  + Core indexes for sessions, features, documents, entity_links, telemetry: done
  + Feature-surface composite indexes (idx_features_status_updated, idx_features_project_status, idx_phases_feature_status): done
  + idx_sessions_project_status_updated defined in migration DDL: done (but not applied to existing DB)
  + WAL mode enabled on SQLite: done
  + ON DELETE CASCADE on child tables (session_logs, session_messages, session_file_updates, etc.): done
  + Telemetry queue (outbound_telemetry_queue) with status indexes: done
  + StorageProfileConfig and RuntimeEnvironmentContract for enterprise operator configuration: done
  + Postgres-specific repositories for all major entities: done
  + UNIQUE index on entity_links added via migration step: done (partial — not in initial DDL)
GAPS:
  - No analytics_entries or analytics_entity_links retention/TTL/pruning — table grows unbounded at ~10K rows/hour
  - idx_sessions_project_status_updated never backfilled as _ensure_index for existing databases
  - sessions.source_file has no index — file-watch sync path does full table scans
  - session_logs + session_messages contain duplicate transcript content (~1.2 GB wasted)
  - SQLite PRAGMA cache_size not configured — default 8 MB cache for 10 GB DB
  - Postgres upsert_logs/upsert_file_updates/upsert_tool_usage not wrapped in transactions
  - analytics _capture_analytics N+1: 12-15K DB queries per snapshot for 367 features
  - entity_graph.upsert() commits per-link — no batch upsert path for link rebuilds
  - telemetry_events.payload_json has no TTL — 1.6 GB unbounded JSON blob storage
  - entity_links UNIQUE constraint not in initial Postgres DDL — ON CONFLICT race on fresh install
  - Schema version mismatch between SQLite (27) and Postgres (28) migration files
  - PRAGMA synchronous not set to NORMAL/OFF for cache-rebuilable SQLite DB
  - get_latest_entries HAVING anti-pattern prevents early index exit on 1.8M row table
  - Candidate partial indexes for analytics_entries period='point' and telemetry_events by event_type not yet added

### caching
COMPLETED:
  + In-process TTLCache singleton with project-scoped cache keys (done): backend/application/services/agent_queries/cache.py:50,294-317
  + memoized_query decorator with fingerprint-based invalidation on 14 service methods (done): cache.py:328-492
  + bypass_cache=True query param on all cached agent endpoints (done): backend/routers/agent.py:137,235,270,287,318,356,393
  + Background cache warming for project_status + workflow_diagnostics in jobs-capable profiles (done): backend/adapters/jobs/runtime.py:840-982
  + OTEL hit/miss counters for cache observability (done): backend/observability/otel.py:327-332,934-944
  + TanStack Query QueryClient with project-scoped query keys (done): lib/queryClient.ts, services/queryKeys.ts
  + Per-hook staleTime configuration across frontend queries (done): services/queries/*.ts
  + TTL=0 bypass and fingerprint-None graceful degradation (done): cache.py:411,469-474
  + Cache status endpoint for operator observability (done): backend/routers/cache.py:219-273
  + Frontend queryClient.clear() on project switch (partial): documented in lib/queryClient.ts but enforcement path not verified
  + Operator documentation for TTL tuning (done): docs/guides/query-cache-tuning-guide.md
  + Two-tier frontend caching architecture documented (done): docs/guides/feature-surface-architecture.md
GAPS:
  - Shared distributed cache (Redis/Valkey) for enterprise multi-container deployments — the single most important missing piece for enterprise production readiness
  - Per-metric TTL enforcement — CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS and CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS have no effect on actual cache behavior
  - Sync-triggered cache invalidation — no hook from sync_project() to clear project cache entries after data ingestion
  - Project-scoped cache eviction API — clear_cache() evicts all entries; no project-targeted eviction
  - Fingerprint caching — 6 DB queries per request before cache key lookup, including a full global entity_links scan
  - entity_links fingerprint project-scoping — entity_links has no project_id column; fingerprint scans all rows across all projects
  - Cache warming for the remaining 12 memoized endpoints not covered by the warmer
  - Cache warming in api profile — api containers have jobs=False and receive no warming
  - Multi-replica cache consistency — no pub/sub or LISTEN/NOTIFY to propagate invalidations across api replicas
  - Legacy /api/features caching — list_features has no @memoized_query; frontend polls it every 5s by default

### ingestion-fs
COMPLETED:
  + worker-watch runtime profile with capabilities.watch=True — backend/runtime/profiles.py:65-72 (done)
  + SyncEngine._sync_engine_enabled() enterprise filesystem ingestion guard — container.py:237-242 (done, but default is misconfigured)
  + SourceRootAlias + source_identity_policy_from_env() for container path remapping — backend/services/source_identity.py (done)
  + WATCHFILES_FORCE_POLLING env var plumbed through compose and documented — compose.yaml:175, README.md:178 (done, default is wrong)
  + Postgres NOTIFY fanout: worker publishes, API listens, SSE republishes — enterprise-live-session-ingest-v1 phase-3 (done)
  + Watcher health probe fields: running state, watch paths, last sync at, last error — runtime.py:422-463 (done)
  + Incremental _light_mode_scan_skip for document/progress .md scans — sync_engine.py:4239-4278 (done, sessions not covered)
  + Deferred link rebuild with configurable stagger delay — runtime.py:774-784 (done)
  + Per-run _rglob_cache memo for document/progress/feature phases — sync_engine.py:1277-1290 (done)
  + Canonical source key scheme ccdash-source:v1/{project}/{kind}/{root}/{rel} — source_identity.py:120-138 (done)
  + worker-watch compose service with live-watch profile and separate probe port — compose.yaml (done)
  + Operator documentation for mount setup, polling mode, watcher no-paths troubleshooting — deploy/runtime/README.md (done)
GAPS:
  - CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED compose anchor defaults to false; enterprise deployments without the live-watch profile silently have no sync engine
  - Watcher-triggered delete uses str(path) not canonical source key — orphaned DB rows on file deletion (sync_engine.py:3944)
  - No readiness probe failure when worker-watch has zero valid watch paths (configured_no_paths silently passes readyz)
  - WATCHFILES_FORCE_POLLING defaults false in compose; Docker Desktop deployments get silent watcher with no events
  - SourceIdentityPolicy not populated from ResolvedProjectPaths; depends entirely on operator setting 6 env vars correctly
  - No manifest-based scan skip for session JSONL files; full rglob + N DB lookups on every startup (document scan has this, sessions do not)
  - STARTUP_SYNC_LIGHT_MODE has three different default values across config.py, runtime.py, and sync_engine.py
  - Postgres NOTIFY listener has no reconnect/backoff; dropped connection permanently kills live fan-out until API restart
  - Backfill pipelines (telemetry events, commit correlations, usage attribution) are sequential N+1 loops, not batched
  - No end-to-end container smoke test that actually runs docker compose up and verifies sessions appear in the API
  - Session scanner does not verify that the resolved sessions_dir is inside a configured mount alias; operator can misconfigure without detection
  - projects.json stores host-absolute tilde paths; no validation that these resolve correctly inside the container at registration time

### workers-runtime
COMPLETED:
  + Five-profile runtime separation (local/api/worker/worker-watch/test) declared and enforced in backend/runtime/profiles.py:28–89 — done
  + api profile has watch=False, sync=False, jobs=False — correctly excludes all background work — done
  + worker/worker-watch profiles have dedicated startup/periodic jobs (startup sync, analytics, cache warming, telemetry, artifact rollup) — done
  + RuntimeJobAdapter orchestrates all five job slots with per-job observation state (lastStartedAt, lastDurationMs, lastError, etc.) — done
  + Startup sync runs as non-blocking asyncio.Task (does not block request serving) — done
  + Worker probe HTTP server on CCDASH_WORKER_PROBE_PORT (default 9465) with /livez, /readyz, /detailz endpoints — done
  + Worker readiness check requires worker_binding (project must resolve before ready) — done
  + worker-watch readiness checks include watcher_runtime and startup_sync — done
  + Postgres live event bus (NOTIFY) on worker side, listener on api side — enterprise live fanout architecture done
  + Worker project binding requires CCDASH_WORKER_PROJECT_ID and raises hard RuntimeError if unresolved — done
  + OTEL + Prometheus metrics for worker job freshness and backpressure — done
  + Watcher rebind (rebind_watcher) for in-process project switching — done
  + FileWatcher is a module-level global singleton (file_watcher = FileWatcher() at bottom of file_watcher.py:307) — done but single-project scoped
  + CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED gates SyncEngine in enterprise mode — done
  + compose.yaml provides enterprise, worker, worker-watch, live-watch profiles with correct CCDASH_RUNTIME_PROFILE per service — done
GAPS:
  - CRITICAL: enterprise worker has STARTUP_SYNC_ENABLED=false by default in compose.yaml:133 — enterprise data never ingested without live-watch profile or explicit override
  - CCDASH_WORKER_WATCH_PROJECT_ID resolved only at compose layer, not in Python config.py — k8s/bare-container operators will encounter silent misconfiguration
  - InProcessJobScheduler is bare asyncio.create_task() with no retry policy, queue, priority, backpressure, or supervision at the scheduler level
  - No task supervision — a dead job task appears as 'idle' in the probe contract rather than 'dead' or 'crashed'
  - Workers are single-project-scoped; multi-project coverage requires N separate containers with no shared scheduler or cross-project analytics
  - Analytics snapshot and cache warming only cover the active/bound project — no multi-project iteration loop
  - TelemetryExporterJob and ArtifactRollupExportJob only wired for profile.name=='worker'; worker-watch never flushes telemetry
  - No durable task queue (Redis/Postgres-backed) — container crash mid-sync loses all in-flight work and forces full re-sync on restart
  - Module-level container = build_worker_runtime() in bootstrap_worker.py:86 creates an orphaned RuntimeContainer at import time
  - CCDASH_WORKER_STARTUP_SYNC_ENABLED and CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED exist in compose/scripts but are not read by Python config.py directly
  - No 'stale since' threshold alarm in probe contract — operators must manually compute staleness from checkpointFreshnessSeconds
  - No job queue depth metrics for analytics snapshots and cache warming (only telemetry export has queue depth)

### multi-project
COMPLETED:
  + DB schema: project_id column on sessions, documents, tasks, features, analytics_entries, telemetry_events, session_usage_events, commit_correlations, session_relationships (done)
  + Request-scoped project resolver: resolve_project() with X-CCDash-Project-Id header support (done)
  + POST /api/projects/active/{id} endpoint with atomic watcher rebind (done — commit b1c83e4, watcher-rebind-v1)
  + CLI project group: ccdash project add/list/use commands in packages/ccdash_cli (done)
  + Backend CLI --project override flag (done — backend/cli/main.py:37)
  + Multi-project MPCC fan-out query service with asyncio.gather + semaphore (done — multi_project_planning_command_center.py)
  + Display metadata (color palette, group) for projects (done — project_manager.py:26-83)
  + Hosted/enterprise project-ID extraction from JWT claims and X-CCDash-Project-Id header (done — container.py:415-425)
  + Project path resolver with filesystem + github_repo source kinds (done — services/project_paths/resolver.py)
  + Enterprise storage profile validation with Postgres requirement (done — config.py:213-228)
GAPS:
  - DB-backed project registry: projects.json must be replaced with a `projects` table for multi-replica container deployments
  - Multi-project worker mode: CCDASH_WORKER_PROJECT_ID binds one worker to one project; no 'watch all' orchestration exists
  - Per-project FileWatcher instances: singleton watcher must become a dict-keyed registry for concurrent multi-project watching
  - Startup warning when enterprise profile + ingestion disabled + DB empty: operator will not know why data is missing
  - Session primary key isolation: sessions.id PK must include project_id to prevent cross-project collision corruption
  - session_logs project_id column: detail tables have no project_id, rely on session_id FK uniqueness which is not guaranteed
  - Active-project global fallback removal in enterprise mode: headerless requests must fail-fast instead of routing to global active project
  - Multi-project cache warming: cache-warming loop must iterate all registered projects, not just the bound/active one
  - TanStack Query cache invalidation on project switch: queryClient.invalidateQueries() must be called after setApiProjectScope()
  - Concurrent rebind_watcher mutex: asyncio.Lock needed for multi-operator scenarios

### container-deploy
COMPLETED:
  + Single-image multi-stage Dockerfile (deploy/runtime/Dockerfile) with non-root user, entrypoint dispatch on CCDASH_RUNTIME_PROFILE — status: done
  + compose.yaml with enterprise/postgres/local/live-watch profiles and x-backend-service anchor with workspace/claude/codex bind mounts — status: done
  + Source identity aliasing (backend/services/source_identity.py:271–308) for CCDASH_WORKSPACE_HOST_ROOT/CONTAINER_ROOT and CCDASH_CLAUDE_HOME/CONTAINER_HOME pairs — status: done
  + Postgres health-gate: api depends_on postgres:service_healthy, worker depends_on api:service_healthy — status: done
  + Idempotent Postgres migration (postgres_migrations.py:1497–2176, CREATE TABLE IF NOT EXISTS, schema_version 28) — status: done
  + compose.external-postgres.yaml podman-compat override using !reset to drop postgres dependency edge — status: done
  + worker-watch service definition in compose.yaml with CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true and STARTUP_SYNC_ENABLED=true — status: partial (requires explicit --profile live-watch, not in default enterprise docs)
  + container_project_onboarding.py helper script for generating container-path projects.json entries — status: done
  + Worker probe app on port 9465/9466 with /livez /readyz /detailz endpoints — status: done
  + Frontend nginx image with proxy for /api/, /api/v1/, and SSE /api/live/stream — status: done
GAPS:
  - No container-path translation in FilesystemProjectPathProvider.resolve() — stored host paths in projects.json are opened verbatim inside the container
  - CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED defaults to false in compose.yaml, disabling sync engine for all enterprise containers
  - live-watch profile not included in default enterprise startup command; no data ever reaches the DB without --profile live-watch
  - CCDASH_WORKER_STARTUP_SYNC_ENABLED defaults to false for the worker service in compose.yaml — no initial filesystem scan
  - projects.json mounted read_only:true but ProjectManager._save() writes to it on startup migration — PermissionError on modified schemas
  - CCDASH_PROJECTS_FILE env var is documented in container_project_onboarding.py but never read in backend/config.py or ProjectManager
  - frontend service has no depends_on:api — starts before API is ready, serving 502s
  - entrypoint.sh case statement does not handle worker-watch profile — crash if command override is removed
  - compose.hosted.yml is diverged: no filesystem volume mounts, no CCDASH_WORKER_PROJECT_ID, worker runs as root, referenced api/worker Dockerfiles have no user hardening
  - No advisory lock on Postgres migrations — api and worker both run run_migrations() on startup with potential DDL race on fresh DB
  - CORS always allows localhost:3000/127.0.0.1:3000 regardless of CCDASH_FRONTEND_ORIGIN — insecure in production deployments
  - No documented step to run container_project_onboarding.py before first enterprise deployment; operator must know to do this manually

### completed-work
COMPLETED:
  + containerized-deployment-v1: COMPLETED — multi-stage Dockerfile, compose profiles (local/enterprise/live-watch), podman-compose !reset workaround, frontend image <50MB; deploy/runtime/Dockerfile, deploy/runtime/compose.yaml, deploy/runtime/compose.hosted.yml
  + deployment-runtime-modularization-v1: COMPLETED — explicit RuntimeProfileName (local|api|worker|worker-watch|test), RuntimeCapabilities contract, separate bootstrap modules, worker probe FastAPI app; backend/runtime/profiles.py, bootstrap_worker.py
  + data-platform-modularization-v1: COMPLETED — storage profile capability contract (local/enterprise/shared-enterprise), data_domains.py canonical vs derived classification, runtime/storage combination validation; backend/config.py, backend/data_domains.py, backend/runtime/storage_contract.py
  + sse-live-update-platform-v1: COMPLETED — InMemoryLiveEventBroker, GET /api/live/stream SSE endpoint, useLiveInvalidation frontend hook; backend/adapters/live_updates/in_memory_broker.py, backend/routers/live.py
  + enterprise-live-session-ingest-v1: COMPLETED (PRD status stale at 'draft') — worker-watch profile, PostgresNotifyLiveEventBus + listener (NOTIFY/LISTEN), CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED, compose live-watch profile; backend/runtime/profiles.py:65, backend/runtime/container.py:111-118, deploy/runtime/compose.yaml:159
  + live-ingest-source-path-canonicalization-hardening-v1: COMPLETED — canonical path normalization, duplicate migration/backfill, runtime guardrails, performance validation gate
  + session-transcript-append-deltas-v1: COMPLETED — canonical transcript repository, append-delta ingestion, frontend delta application via SSE
  + db-caching-layer-v1: COMPLETED (phases 3-4; phases 1-2 predate progress tracking) — canonical transcript repository, message-level storage, Postgres-ready session tables
  + ccdash-query-caching-and-cli-ergonomics-v1: COMPLETED — @memoized_query TTLCache(maxsize=512) decorator, CCDASH_QUERY_CACHE_TTL_SECONDS=600s default, POST /api/cache/invalidate, --no-cache CLI flag; backend/application/services/agent_queries/cache.py:328
  + runtime-performance-hardening-v1: COMPLETED — transcript ring-buffer cap (5000 rows), MAX_DOCUMENTS_IN_MEMORY=2000, react-virtual virtualization, link rebuild dedup/throttle, OTel instrumentation pass; contexts/dataContextShared.ts:61
  + ccdash-frontend-data-layer-refactor (TanStack Query migration): COMPLETED (phases 0-7, 176 guardrail tests green) — QueryClient, services/queries/ domain hooks, queryKeys.ts registry, hand-rolled LRU caches removed, backend fat-read bundle endpoints, legacy getFeatures() reduced to 100-row limit; services/queries/, services/queryKeys.ts, services/apiClient.ts:421-423
  + feature-surface-data-loading-redesign-v1: COMPLETED — feature card list/rollup/modal v1 endpoints, useFeatureSurface hook, ProjectBoard off session-summary loop, lazy modal section loading, SQLite+Postgres parity; documented partial gap: global provider refresh still runs
  + ccdash-hexagonal-foundation-v1: COMPLETED — foundational hexagonal architecture, repository/service/router split; all 6 phases
  + ccdash-planning-control-plane-v1: COMPLETED — all 8 phases, PlanningHomePage/GraphPanel/AgentSessionBoard/LaunchSheet/SummaryPanel, /api/agent/planning/* endpoints
  + planning-command-center-v1: COMPLETED (PRD status stale at 'draft') — GET /api/agent/planning/command-center, PlanningCommandCenter.tsx with list/card/board views, WorktreeGitStatePanel, embedded in PlanningHomePage; confirmed via AAR + implementation plan both status:completed; commits d903b55-645e1b7
  + multi-project-planning-command-center-v1: COMPLETED — MultiProjectCommandCenter.tsx, aggregate DTOs, multi_project_planning_command_center.py, TQ hooks; ALL phases completed; FEATURE-FLAGGED OFF by default (VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false); constants.ts:399-421
  + planning-forensics-boundary-extraction-v1: COMPLETED — all 6 phases
  + shared-auth-rbac-sso-v1: COMPLETED (phases 2-7) — RBAC bearer token auth, CCDASH_API_BEARER_TOKEN, authGuardrail in health endpoint; commits 68c6cdb, 3799316, d42ef27
  + ccdash-planning-reskin-v2 + interaction-performance-addendum: COMPLETED — all phases in both progress dirs
GAPS:
  - Dashboard KPI TanStack Query migration: Dashboard.tsx still uses legacy getOverview() imperative path (20.5s cold, 9.7s warm); KPI cards show literal 0 while in-flight; no loading skeleton or error state; T0-001/T0-002/T0-003 all pending in quick-features/dashboard-kpi-tq-migration.md
  - Postgres NOTIFY listener reconnect/backoff: postgres_listener.py has no reconnect or exponential backoff; transient DB disconnect permanently breaks live ingest until container restart; deferred FU-2 with no plan yet
  - Wire-boundary SSE smoke test: no real-browser or integration test for SessionInspector receiving live events through the Postgres NOTIFY→SSE path; deferred FU-4
  - Bootstrap test FU-004 skip decorators: 5 test classes/methods permanently skipped at backend/tests/test_runtime_bootstrap.py:616,680,716,1057,1333; the underlying production drift they claim (missing authGuardrail/probeDetailWarningCodes in _build_health_payload) appears to have been fixed (fields present at bootstrap.py:176,224) but the skips were never re-evaluated; entire RuntimeBootstrapLifecycleTests class skipped due to macOS subprocess leak
  - Publish exception isolation (FU-3): no confirmed try/except around LiveEventBus.publish() call sites in backend/db/sync_engine.py; a publish failure could potentially abort a sync write
  - OTel instruments for live fanout latency (FU-5): ccdash_live_fanout_publish_latency_ms, ccdash_live_fanout_delivered_total, ccdash_live_watcher_sync_latency_ms not confirmed present
  - _COMPACT_PAYLOAD_KEYS extension contract documentation (FU-7): undocumented; downstream consumers may add fields without understanding cross-process payload constraints
  - Multi-project command center is feature-flagged OFF by default: operators must set VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true; no documentation path for enterprise operators to discover this flag
  - worker-watch entrypoint gap: deploy/runtime/entrypoint.sh handles only local|api|worker; CCDASH_RUNTIME_PROFILE=worker-watch falls through to error case; compose.yaml works around via command: override but this is inconsistent with hosted.yml path
  - App-shell global feature refresh partial retirement: services/apiClient.ts:421-423 getFeatures() still exists at 100-row default; legacy path not fully retired from app shell polling
  - PRD status metadata drift: planning-command-center-v1.md status still 'draft', enterprise-live-session-ingest-v1.md status still 'draft' despite both being fully implemented; causes confusion for effort triage

### perf-evidence
COMPLETED:
  + WAL mode enabled for SQLite (connection.py:52) — done
  + foreign_keys=ON pragma set at runtime (connection.py:53) — done
  + busy_timeout configured (connection.py:54) — done
  + 184 indexes created across all tables including composite indexes on sessions, session_logs, session_messages (sqlite_migrations.py) — done
  + TanStack Query replacing hand-rolled setInterval polling for most endpoints (alerts, notifications, health, sessions, features, planning) — done (partial: some components still use setInterval)
  + @memoized_query TTL cache (600s default) for agent query services — done
  + Cache hit/miss OTEL counters (otel.py:931-944) — done
  + Feature surface latency histogram (otel.py:364) — done
  + Watcher sync latency histogram (otel.py:430) — done
  + asyncio.Semaphore bounding on multi-project fan-out (system_metrics.py:199, multi_project_planning_sessions.py:572) — done
  + InfiniteQuery pagination for sessions list (services/queries/sessions.ts) — done
  + MEMORY_GUARD flag gating document pagination cap (lib/featureFlags.ts:22) — done (partial: only covers documents, not sessions/logs)
  + ON DELETE CASCADE from session_usage_events to session_usage_attributions (sqlite_migrations.py) — done
  + GIN indexes on Postgres JSON columns (postgres_migrations.py:706-1231) — done
  + OTEL spans on sync phases (sync_engine.py) — partial (session parse and project-level spans exist; analytics capture span lacks duration histogram)
  + Partial-sync light mode flag (CCDASH_STARTUP_SYNC_LIGHT_MODE) — done (flag exists, wired to compose.yaml, but default is false)
  + Multi-project command center service with bounded concurrency — done
GAPS:
  - No analytics_entries retention/purge policy — table grows 3,313 rows per sync indefinitely
  - Enterprise worker startup sync defaults to disabled in compose.yaml — fresh deployments have empty database
  - Session badge metadata (models_used, agents_used, skills_used) not materialized on sessions table — causes N+1 log fetches on every list page
  - No executemany() usage for batch inserts — row-by-row INSERT in telemetry, attribution, session_log writes
  - SQLite cache_size at 8 MB default — never tuned for 9.5 GB production database
  - No FTS5 index on session_messages.content — search is O(n) full-table-scan
  - session_logs rows not pruned after canonical session_messages rows are written — ~1.75 GB dead storage
  - No OTEL histogram for _capture_analytics duration or for session list badge derivation latency
  - features refetchInterval at 5s when SSE disabled — excessive polling on large projects
  - Postgres analytics_entries/telemetry_events lacks time-series partitioning for enterprise scale
  - No DB-level VACUUM or ANALYZE scheduled job — 157 free pages but no statistics refresh
  - PRAGMA synchronous, mmap_size, wal_autocheckpoint, temp_store not configured for production SQLite workload

### data-contracts
COMPLETED:
  + statusCounts (shaping/planned/active/blocked/review/completed/deferred/stale_or_mismatched) in ProjectPlanningSummaryDTO — done (planning.py:788-803)
  + ctxPerPhase ratio (context docs / total phases) in ProjectPlanningSummaryDTO — done (planning.py:806-823)
  + Multi-project planning command center fan-out with NullGitProbe + page-first enrichment (MPCC-202/203/206) — done (multi_project_planning_command_center.py)
  + Project summary rollup with active-session counts and freshness/staleness per project — done (models.py:3451, multi_project_planning_command_center.py:212)
  + Planning agent session board (Kanban by state/feature/phase/agent/model) — done (planning_sessions.py + models.py PlanningAgentSessionBoardDTO)
  + Feature planning context with graph/phases/open-questions/spikes — done (planning.py:1306)
  + Phase operations with batch readiness and task assignments — done (planning.py:1574)
  + SkillMeat artifact snapshot fetch and cache — done (artifact_snapshot_cache table + skillmeat_client.py)
  + SkillMeat artifact ranking and recommendation generation — done (artifact_ranking table + artifact_ranking_service.py)
  + SkillMeat session stack observations and workflow effectiveness — done (session_stack_observations + effectiveness_rollups tables)
  + SkillMeat memory drafts pipeline (extract → review → publish) — done (session_memory_drafts table + skillmeat_memory_drafts.py)
  + SAM outbound telemetry (ExecutionOutcomePayload + ArtifactOutcomePayload) — done (telemetry_exporter.py + artifact_rollup_export_job.py)
  + PlanningCommandCenterItemDTO with command resolution, tier, story_points, phase summary, artifacts, blockers, worktree, git_state, PR — done (planning_command_center.py)
  + Feature dependency state and family sequencing (ExecutionGateState / FeatureFamilySummary) — done (models.py:1967-2049, feature_execution.py)
  + Live active session count per project with 10s TTL — done (live_metrics.py)
  + Session intelligence (sentiment/churn/scope_drift) heuristics and DB tables — done
  + Execution runs + approval pipeline + run events — done (execution_runs table + models.py:2742-2842)
  + Planning worktree contexts (branch/path/status per feature/phase) — done (planning_worktree_contexts table)
  + Test run integration (pytest/jest/playwright/coverage tables) — done (test_runs + test_definitions + test_results tables)
  + Multi-project session board response envelope (MultiProjectSessionBoardResponse) — done (models.py:3607)
GAPS:
  - tokenUsageByModel not on Feature model → PlanningTokenTelemetry.source always 'unavailable' in project summary — planning KPI telemetry broken
  - Projects stored only in projects.json (no DB table) — incompatible with containerized/multi-instance enterprise deployments
  - Open question resolutions in process memory only (_OQ_OVERLAY) — lost on restart, incompatible with multi-instance
  - ARC/agentic-research-council reviews: zero implementation — no model, client, DB table, or endpoint
  - MeatyWiki research integration: zero implementation — registered as project only, no API surface
  - No cross-project token/cost aggregate in ProjectWorkItemCounts — enterprise dashboard KPIs incomplete
  - No 'available next work' ranked backlog endpoint — shaping/planned items have no priority-ordered execution queue
  - Feature BLOB (data_json) pattern prevents SQL-level filtering on tags/owners/phases/linkedDocs — performance bottleneck at skillmeat scale
  - Planning graph recomputed in-memory per cache TTL — no precomputed graph cache in DB
  - Pull request status not live — only stored ref strings, no GitHub API live status query
  - ArtifactVersionOutcomePayload not emitted — SAM version-level telemetry path incomplete
```
