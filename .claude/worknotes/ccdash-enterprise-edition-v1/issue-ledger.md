# CCDash Enterprise Investigation — Global Issue Ledger

130 issues from 12-domain forensic investigation (2026-05-30). Severity = UX/scalability impact; Complexity = S(<0.5d)/M(1-2d)/L(3-5d)/XL(>1wk).

```
SEVERITY | CPLX | AREA | DOMAIN | TITLE
CRITICAL | L  | perf        | planning-frontend | Session board has no server-side pagination — full project payload on every load
CRITICAL | M  | caching     | planning-frontend | V1 PlanningCommandCenter bypasses TanStack Query — no cache, no dedup
CRITICAL | M  | backend     | backend-api       | N+1 full log-fetch on session list view
CRITICAL | M  | backend     | backend-api       | Planning view bundle performs 6x list_all scans with no data sharing
CRITICAL | M  | database    | database          | analytics_entries unbounded growth — 1.8M rows / 466 MB with no retention policy
CRITICAL | L  | backend     | database          | Analytics _capture_analytics: N+1 query pattern — 12–15K DB queries per snapshot
CRITICAL | L  | caching     | caching           | In-process cache is not shared across enterprise api+worker containers
CRITICAL | M  | database    | caching           | entity_links fingerprint is a full global table scan on every cached request
CRITICAL | S  | container   | ingestion-fs      | CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED defaults false in compose anchor; enterprise SyncEngine never instantiated
CRITICAL | S  | workers     | workers-runtime   | Enterprise worker startup sync disabled by default — no data ever ingested
CRITICAL | L  | multi-project | multi-project     | projects.json is a local file, not DB-backed — breaks multi-replica containers
CRITICAL | S  | container   | multi-project     | Enterprise profile silently disables ingestion — container has empty DB
CRITICAL | XL | workers     | multi-project     | Single worker per project — N projects require N worker processes with no orchestration
CRITICAL | M  | container   | container-deploy  | Host-path projects.json paths do not resolve inside containers — zero filesystem ingestion
CRITICAL | S  | container   | container-deploy  | CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED defaults false — sync engine disabled for all enterprise containers
CRITICAL | S  | container   | container-deploy  | live-watch profile not started by default — no filesystem ingestion in standard enterprise deployment
CRITICAL | M  | database    | perf-evidence     | analytics_entries grows unboundedly — no retention, no dedup
CRITICAL | S  | container   | perf-evidence     | Enterprise container worker startup sync disabled by default — no data ever ingested
CRITICAL | M  | backend     | data-contracts    | tokenUsageByModel missing from Feature model — PlanningTokenTelemetry always unavailable
CRITICAL | L  | container   | data-contracts    | projects.json as sole Project store — incompatible with container/enterprise deployments
HIGH     | M  | frontend    | frontend-core     | useData() shim uses getQueryData() not useQuery() — no reactive subscription for 7 domain arrays
HIGH     | S  | perf        | frontend-core     | useFeaturesQuery polls every 5 s when SSE disabled — enterprise default fires 12 req/min
HIGH     | S  | perf        | frontend-core     | useFeatureSurface list tier staleTime: 0 refetches on every mount
HIGH     | M  | perf        | planning-frontend | Planning home always-mounts session board and command center — 5 concurrent cold-load requests
HIGH     | S  | caching     | planning-frontend | Hover prefetch bypasses TQ cache — data fetched and discarded, modal still cold
HIGH     | M  | perf        | planning-frontend | V1 session board has no virtualization — rich cards render fully for all sessions
HIGH     | M  | multi-project | planning-frontend | Multi-project queries fire with hardcoded projectListReady:true before project list resolves
HIGH     | S  | caching     | backend-api       | PlanningCommandCenterQueryService (V1) has no @memoized_query cache
HIGH     | S  | backend     | backend-api       | get_command_center_item loads 500-item full page to retrieve one feature
HIGH     | M  | database    | backend-api       | Cache fingerprint runs unscoped entity_links GROUP_CONCAT across all projects
HIGH     | S  | database    | backend-api       | feature_phases fingerprint is an O(N) string concat per fingerprint call
HIGH     | M  | database    | backend-api       | All planning services use SELECT * list_all (no column projection)
HIGH     | S  | caching     | backend-api       | Session board (single-project) has no caching and fetches 500 sessions unconditionally
HIGH     | M  | backend     | backend-api       | PlanningQueryService.get_feature_planning_context loads all features+docs for a single feature request
HIGH     | S  | perf        | backend-api       | git subprocess spawned per command-center item in V1 (no NullGitProbe for off-page items)
HIGH     | S  | database    | database          | idx_sessions_project_status_updated missing from live DB — count_active uses suboptimal index
HIGH     | S  | database    | database          | sessions.source_file — no index causes full table scan on every file-watch event
HIGH     | L  | database    | database          | session_logs + session_messages dual transcript storage — 3.3 GB combined duplication
HIGH     | M  | database    | database          | entity_graph.upsert() — commit per link causes 25K individual commits during link rebuild
HIGH     | M  | database    | database          | Postgres entity_links UNIQUE constraint added post-DDL — ON CONFLICT silently inserts duplicates on fresh install
HIGH     | M  | backend     | database          | Postgres upsert_logs/upsert_file_updates non-atomic — DELETE then N INSERTs without transaction
HIGH     | S  | database    | database          | SQLite PRAGMA cache_size not configured — 8 MB page cache for 10 GB database
HIGH     | M  | database    | database          | telemetry_events.payload_json unbounded JSON blob storage — 1.6 GB with no TTL
HIGH     | S  | caching     | caching           | CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS and CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS are documented but never enforced
HIGH     | S  | caching     | caching           | No cache invalidation triggered after sync_project completes
HIGH     | M  | perf        | caching           | Legacy /api/features polled every 5s with N+1 queries and no server-side caching
HIGH     | S  | ingestion   | ingestion-fs      | Watcher-triggered session delete uses raw path string; does not match canonical source key stored during ingest
HIGH     | M  | container   | ingestion-fs      | File watcher silently watches zero paths when projects.json session paths resolve to non-existent container directories
HIGH     | S  | container   | ingestion-fs      | watchfiles inotify does not fire on Docker Desktop bind mounts; WATCHFILES_FORCE_POLLING defaults false
HIGH     | M  | ingestion   | ingestion-fs      | Source-path alias policy not populated from ResolvedProjectPaths; opaque hash keys produced when mount env vars absent
HIGH     | M  | perf        | ingestion-fs      | No manifest-based skip for session JSONL scan; full rglob + N DB lookups on every startup
HIGH     | S  | container   | workers-runtime   | CCDASH_WORKER_WATCH_PROJECT_ID not implemented in Python config — k8s/bare-container trap
HIGH     | M  | workers     | workers-runtime   | No task supervision — dead job task silently shows as 'idle'
HIGH     | L  | workers     | workers-runtime   | InProcessJobScheduler has no queue, retry, or concurrency controls — all jobs share the same event loop
HIGH     | XL | workers     | workers-runtime   | No durable task queue — full re-sync on every container restart for large projects
HIGH     | M  | ingestion   | multi-project     | FileWatcher is a process-level singleton — only one project watched at a time
HIGH     | L  | database    | multi-project     | Session primary key is globally unique — cross-project ID collision silently corrupts data
HIGH     | M  | backend     | multi-project     | Global active-project fallback bypasses per-request project isolation
HIGH     | M  | database    | multi-project     | session_logs, session_tool_usage, session_file_updates have no project_id column
HIGH     | M  | container   | container-deploy  | projects.json mounted read_only but ProjectManager._save() writes on startup migration
HIGH     | S  | container   | container-deploy  | CCDASH_PROJECTS_FILE env var is a dead variable — never read by config.py or ProjectManager
HIGH     | S  | container   | container-deploy  | frontend service has no depends_on:api — serves 502s at startup
HIGH     | S  | container   | container-deploy  | entrypoint.sh does not handle worker-watch profile — crash if command override is removed
HIGH     | S  | container   | container-deploy  | compose.hosted.yml is diverged and broken for current worker requirements
HIGH     | M  | frontend    | completed-work    | Dashboard KPI cards show 0 on slow/aborted load — legacy imperative path not migrated
HIGH     | S  | backend     | completed-work    | Bootstrap test FU-004 skips cover code that appears fixed — test coverage gap
HIGH     | M  | backend     | completed-work    | Postgres NOTIFY listener has no reconnect/backoff — live ingest breaks on DB hiccup
HIGH     | M  | backend     | perf-evidence     | N+1 session log queries on every session list page load
HIGH     | S  | ingestion   | perf-evidence     | Row-by-row INSERT without executemany across telemetry, attribution, and log writes
HIGH     | S  | database    | perf-evidence     | SQLite page cache critically undersized — 8 MB for 9.5 GB database
HIGH     | M  | backend     | perf-evidence     | _capture_analytics feature-level N+1 — ~11,744 DB queries per sync cycle
HIGH     | M  | backend     | data-contracts    | Open question resolutions stored in process memory only — lost on restart
HIGH     | L  | database    | data-contracts    | Feature data_json BLOB — no columnar indexing for tags/owners/phases/linkedDocs
HIGH     | XL | integration | data-contracts    | ARC/agentic-research-council integration — entirely missing
HIGH     | L  | integration | data-contracts    | MeatyWiki research integration — entirely missing
HIGH     | M  | perf        | data-contracts    | Planning graph computed in-memory per cache TTL — expensive for large project sets
MEDIUM   | M  | frontend    | frontend-core     | Dashboard analytics chart fetches outside TQ, re-fire on every sessions.length or tasks.length change
MEDIUM   | M  | frontend    | frontend-core     | AnalyticsDashboard fires 7 parallel raw fetches on every mount with no TQ caching
MEDIUM   | L  | perf        | frontend-core     | Multiple manual setInterval polls bypass TQ visibility-awareness and dedup
MEDIUM   | L  | perf        | frontend-core     | SessionInspector 6101-line monolith has no React.memo on inner panel components
MEDIUM   | M  | perf        | frontend-core     | ProjectBoard 3895-line monolith re-renders entire feature modal every 15 s poll
MEDIUM   | S  | perf        | frontend-core     | Documents fetched in 500-item pages with 2000-item memory cap — excessive for enterprise
MEDIUM   | M  | container   | frontend-core     | GEMINI_API_KEY baked into JS bundle via Vite define — security issue in container builds
MEDIUM   | S  | frontend    | frontend-core     | OpsPanel reads sessions and documents from useData() — gets stale snapshots not live subscriptions
MEDIUM   | M  | perf        | planning-frontend | Session board hover triggers O(N) Set re-construction causing all SessionCard memos to re-evaluate
MEDIUM   | M  | ux          | planning-frontend | V1 command center pageSize=50 hardcoded with no UI pagination — features >50 silently missing
MEDIUM   | S  | container   | planning-frontend | MULTI_PROJECT_COMMAND_CENTER_ENABLED is a Vite build-time constant, requires rebuild to enable in container
MEDIUM   | M  | container   | planning-frontend | Planning fonts loaded from Google Fonts CDN — fails silently in restricted-egress containers
MEDIUM   | S  | perf        | planning-frontend | StaleIndicator setInterval starts immediately from mount regardless of staleness
MEDIUM   | S  | backend     | backend-api       | View bundle sub-services called sequentially, not in parallel
MEDIUM   | S  | caching     | backend-api       | TTLCache maxsize=512 insufficient for multi-project multi-endpoint load
MEDIUM   | M  | backend     | backend-api       | Session detail endpoint has 8+ sequential DB round-trips
MEDIUM   | M  | container   | backend-api       | No background cache warm-up despite CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS config
MEDIUM   | S  | database    | database          | analytics_entries HAVING anti-pattern — prevents index-only early exit on get_latest_entries
MEDIUM   | M  | database    | database          | SQLite SCHEMA_VERSION=27 vs Postgres SCHEMA_VERSION=28 — migration divergence
MEDIUM   | S  | caching     | caching           | Background cache warming only covers 2 of 14+ memoized endpoints
MEDIUM   | S  | frontend    | caching           | featureSurface list staleTime=0 causes constant background DB refetches
MEDIUM   | S  | caching     | caching           | TTLCache maxsize=512 insufficient for multi-project enterprise
MEDIUM   | M  | database    | caching           | Fingerprint computation is not itself cached — 6 DB queries per request
MEDIUM   | S  | ingestion   | ingestion-fs      | STARTUP_SYNC_LIGHT_MODE getattr fallback default mismatch: config.py=False, runtime.py fallback=True
MEDIUM   | M  | integration | ingestion-fs      | Postgres NOTIFY listener has no reconnect/backoff; dropped connection silently kills live fan-out permanently
MEDIUM   | M  | perf        | ingestion-fs      | Backfill loops during startup sync are sequential single-row DB round-trips, not batched or concurrent
MEDIUM   | S  | workers     | workers-runtime   | Module-level container = build_worker_runtime() in bootstrap_worker.py creates orphaned container at import time
MEDIUM   | M  | workers     | workers-runtime   | Analytics snapshot and cache warming only iterate single active/bound project
MEDIUM   | S  | container   | workers-runtime   | CCDASH_WORKER_STARTUP_SYNC_ENABLED per-service env vars not read by Python config.py
MEDIUM   | S  | workers     | multi-project     | Concurrent rebind_watcher has no mutex — race condition in multi-operator scenarios
MEDIUM   | M  | caching     | multi-project     | Cache warming and analytics snapshots only warm the bound/active project
MEDIUM   | S  | multi-project | multi-project     | projects.json _save() is synchronous and unguarded — torn file on concurrent writes
MEDIUM   | M  | database    | container-deploy  | No pg_advisory_lock on migrations — api and worker race on fresh Postgres
MEDIUM   | S  | container   | container-deploy  | CORS always allows localhost:3000 regardless of production configuration
MEDIUM   | S  | container   | completed-work    | worker-watch not launchable via entrypoint.sh — inconsistent with other profiles
MEDIUM   | S  | backend     | completed-work    | Live ingest follow-ups FU-3/FU-5/FU-7 still open — publish exception isolation and OTel gaps
MEDIUM   | S  | multi-project | completed-work    | Multi-project command center feature-flagged OFF — enterprise operators cannot discover it
MEDIUM   | S  | frontend    | perf-evidence     | Features endpoint polls every 5s when SSE is disabled (default)
MEDIUM   | M  | database    | perf-evidence     | ~1.75 GB of session_logs rows never purged after canonical session_messages exist
MEDIUM   | L  | database    | perf-evidence     | session_messages content search uses LIKE full-table-scan — no FTS index
MEDIUM   | S  | backend     | perf-evidence     | No OTEL instrumentation for analytics snapshot, session list badge derivation, or sync INSERT batch sizes
MEDIUM   | M  | database    | perf-evidence     | Postgres migration has GIN indexes but analytics/telemetry retention policy absent
MEDIUM   | M  | multi-project | data-contracts    | No cross-project token/cost aggregate endpoint
MEDIUM   | M  | integration | data-contracts    | Pull request status not live — only stored ref strings
MEDIUM   | M  | backend     | data-contracts    | Available-next-work backlog — no ranked endpoint
LOW      | S  | perf        | frontend-core     | usePlanningSummaryQuery staleTime: 0 causes refetch on every Planning page mount
LOW      | XL | ux          | planning-frontend | Global Cmd-K search and New Spec creation are stubs — toast-only responses
LOW      | M  | ux          | planning-frontend | Sparkline data and token-saved % are heuristic fictions — misleads enterprise users
LOW      | S  | caching     | caching           | clear_cache() on open_question resolution evicts all projects, not just the affected one
LOW      | S  | multi-project | ingestion-fs      | One worker-watch container per project; no mechanism to detect or warn on multi-project projects.json without explicit binding
LOW      | S  | workers     | workers-runtime   | TelemetryExporterJob and ArtifactRollupExportJob not wired for worker-watch profile
LOW      | S  | frontend    | multi-project     | TanStack Query cache not invalidated on project switch — stale UI data window
LOW      | S  | multi-project | completed-work    | PRD status metadata drift on two completed efforts
LOW      | S  | integration | data-contracts    | ArtifactVersionOutcomePayload not emitted — SAM version-level telemetry incomplete

TOTAL: 130 | by severity: {'critical': 20, 'high': 56, 'medium': 45, 'low': 9} | by area: {'perf': 17, 'caching': 12, 'backend': 18, 'database': 24, 'container': 22, 'workers': 9, 'multi-project': 7, 'frontend': 8, 'ingestion': 5, 'integration': 5, 'ux': 3}
```
