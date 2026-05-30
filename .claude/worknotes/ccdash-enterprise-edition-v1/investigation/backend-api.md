# Backend REST API + Agent Query Intelligence Layer — Investigation Findings

**Date**: 2026-05-30  
**Domain**: backend-api  
**Target**: Enterprise/container + PostgreSQL readiness, performance at scale  
**Key context**: SQLite cache `data/ccdash_cache.db` is 10 GB with a 1.7 MB WAL; `skillmeat` project is reported as much too slow.

---

## 1. Endpoint Inventory for the Planning Page

### 1.1 Planning Page Primary Bundle
- **`GET /api/agent/planning/view`** — fat-read bundle (`agent.py:696`); always returns project planning summary; optional `?include=graph` and/or `?include=session_board`.  
  - Implementation: `PlanningQueryService.get_planning_view_bundle` (`planning.py:2158`).  
  - Calls `get_project_planning_summary` (always) + optionally `get_project_planning_graph` + `get_session_board` sequentially (not parallel: `planning.py:2199`, `2220`, `2242`).  
  - Each sub-read loads **all features** (`features.list_all → LIMIT 5000`, `planning.py:660`) and **all documents** (`documents.list_all → LIMIT 5000`, `planning.py:670`) independently. Three sub-calls each re-query these tables.

### 1.2 Planning Summary
- **`GET /api/agent/planning/summary`** — `agent.py:406`.  
  - `PlanningQueryService.get_project_planning_summary` (`planning.py:883`). `@memoized_query("planning_project_summary")`.  
  - Loads all features + all docs, applies `_project_with_planning` (calls `feature_dependency_state` + `apply_planning_projection`) for **every feature** in a Python loop (`planning.py:929–935`). Per-feature calls `_load_doc_rows_for_feature` (O(N×F) scan, `planning.py:967`).  
  - Also builds orphan-candidate FeatureSummaryItems from doc_rows in a second O(D) pass (`planning.py:1021–1083`).

### 1.3 Planning Graph
- **`GET /api/agent/planning/graph`** — `agent.py:436`.  
  - `PlanningQueryService.get_project_planning_graph` (`planning.py:1180`). `@memoized_query("planning_project_graph")`.  
  - Loads all features + all docs, calls `build_planning_graph` for **every feature** in a loop (`planning.py:1247`); each graph build reconstructs LinkedDocument objects from scratch.

### 1.4 Planning Feature Context (feature modal)
- **`GET /api/agent/planning/features/{feature_id}`** — `agent.py:543`.  
  - `PlanningQueryService.get_feature_planning_context` (`planning.py:1306`). `@memoized_query("planning_feature_context")`.  
  - Even for a single-feature request, loads **ALL** project features (`_load_all_features`) and **ALL** documents (`_load_all_doc_rows`) (`planning.py:1334`, `1343`). Feature index needed for cross-feature dependency resolution.  
  - Then calls `load_execution_documents` (additional DB call, `planning.py:1368`).  
  - Then calls `FeatureEvidenceSummaryService.get_summary` (another `@memoized_query` call, `planning.py:1417`).

### 1.5 Planning Command Center
- **`GET /api/agent/planning/command-center`** — `agent.py:468`.  
  - `PlanningCommandCenterQueryService.get_command_center` (`planning_command_center.py:351`). **NO `@memoized_query` wrapper** (confirmed: no decorator present in file).  
  - Calls `_load_project_data` (all features + all docs), then `_build_items_for_scope` which iterates every feature and per item calls `_build_item` (`planning_command_center.py:552`).  
  - `_build_item` calls `self.git_probe.probe(worktree.path)` for **every feature** (`planning_command_center.py:607`). `WorktreeGitStateProbe.probe` spawns a `subprocess.run(["git", ...])` process per item with 0.8 s timeout and 5 s in-process TTL cache (`worktree_git_state.py`). On a project with 50 features that is up to 50 synchronous subprocess spawns per request.

### 1.6 Single-Item Lookup (feature modal from command center)
- **`GET /api/agent/planning/command-center/{feature_id}`** — `agent.py:514`.  
  - Calls `PlanningCommandCenterQueryService.get_command_center_item` (`planning_command_center.py:559`).  
  - **Internally calls `self.get_command_center(... page_size=500)` and then scans results** (`planning_command_center.py:567–578`). This forces a full project scan + 500-item page to retrieve one item. No fast-path by feature_id.

### 1.7 Planning Session Board
- **`GET /api/agent/planning/session-board`** — `agent.py:621`.  
  - `PlanningSessionQueryService.get_session_board` (`planning_sessions.py:560`). **No `@memoized_query`**.  
  - Fetches all sessions with `list_paginated(offset=0, limit=500)` (`planning_sessions.py:609`).  
  - Loads all features + all entity_links for all features via `load_correlation_data` (`planning_sessions.py:627`, `planning_sessions.py:331–353`).  
  - Calls `build_correlation_map` which processes sessions in order through `_correlate_session_impl` (`planning_sessions.py:384–400`). On a 10 GB DB, 500 sessions × full feature list × entity links = heavy.

### 1.8 Phase Operations Detail
- **`GET /api/agent/planning/features/{feature_id}/phases/{phase_number}`** — `agent.py:572`.  
  - `PlanningQueryService.get_phase_operations` (`planning.py:1574`). `@memoized_query("planning_phase_ops")`.  
  - Also loads all features + all docs even for a single-phase query.

---

## 2. Session Endpoints

### 2.1 Session List (critical N+1)
- **`GET /api/sessions`** — `api.py:553`.  
  - Fetches paginated session rows (`api.py:616–618`).  
  - For **every session row** in the page, calls `session_transcript_service.list_session_logs(s, core_ports)` (`api.py:628`). Default limit inside `list_session_logs` is **5000 logs** (`sessions.py:92`).  
  - On a page of 50 sessions that is **50 × 5000-row DB queries** against `session_messages` or `session_logs`. With a 10 GB DB this is catastrophic for list view.  
  - Additionally, for subagent sessions, calls `list_session_logs` again for the **parent session** (`api.py:660`) — another N-per-page I/O with an in-memory `parent_logs_cache` to soften repeat hits only.  
  - All of this is used just to extract: `command_events`, `latest_summary`, `subagent_type`, and `badge_data`. These should be stored in the sessions table (materialized columns).

### 2.2 Session Detail (compounded fan-out)
- **`GET /api/sessions/{session_id}`** — `api.py:828`.  
  - Full transcript fetch (up to 5000 logs, `api.py:844`).  
  - `repo.get_tool_usage`, `get_file_updates`, `get_artifacts`, `list_relationships` — 4 sequential awaits (`api.py:850–858`).  
  - Per fork relationship: awaits `repo.get_by_id(child_id)` inside a loop (`api.py:869`).  
  - Calls `get_session_usage_attribution_details` (separate DB query, `api.py:983`).  
  - Calls `session_intelligence_read_service.get_session_detail` (another query, `api.py:997`).  
  - Total: 8+ sequential DB round-trips for a single session.

---

## 3. Agent Query Cache Layer (`cache.py`)

### 3.1 Coverage and TTL
- Covered: `project_status`, `feature_forensics`, `feature-evidence-summary`, `workflow_diagnostics`, `aar_report`, `live_active_count`, `system_active_count`, `planning_project_summary`, `planning_project_graph`, `planning_feature_context`, `planning_phase_ops`, `analytics_overview_bundle`, `dashboard_bundle`, `mpcc_command_center`, `mpss_session_board` (`cache.py` + grep results).
- **NOT covered** (no `@memoized_query`): `PlanningCommandCenterQueryService.get_command_center` (V1 single-project command center, `planning_command_center.py:351`), `PlanningSessionQueryService.get_session_board` (`planning_sessions.py:560`), all session CRUD endpoints.
- Default TTL: `CCDASH_QUERY_CACHE_TTL_SECONDS = 600` (`config.py:983`). Comment says "default 60" in the docstring but env default is 600 s — 10 minutes. Very long for a live dashboard with active writes.

### 3.2 Fingerprint Query Cost
- On every cache-miss (and on every cache-hit, to compute the cache key), `get_data_version_fingerprint` fires **6 SQL queries** (`cache.py:116`):
  1. `MAX(updated_at) FROM sessions WHERE project_id = ?`
  2. `MAX(updated_at) FROM features WHERE project_id = ?`
  3. `GROUP_CONCAT/STRING_AGG` across all `feature_phases` joined to features — **full table scan per project** (`cache.py:197–254`).
  4. `MAX(updated_at) FROM documents WHERE project_id = ?`
  5. **`entity_links` marker: `GROUP_CONCAT(marker, '|') FROM entity_links ORDER BY ...` — no project_id scope** (`cache.py:258–289`). Cross-project full-table aggregate on every fingerprint call. On a 10 GB DB this is an unbounded query.
  6. `MAX(updated_at) FROM planning_worktree_contexts WHERE project_id = ?`
- The `feature_phases` fingerprint also uses `GROUP_CONCAT` of all concatenated phase fields — this is an O(all_phases_in_project) string construction per fingerprint call.

### 3.3 Cache Maxsize
- `TTLCache(maxsize=512)` (`cache.py:50`). With 12+ distinct endpoints × multiple projects × multiple param combinations, the 512-entry limit can evict heavily under multi-project load. No LRU-aware sizing.

---

## 4. Multi-Project Endpoints

### 4.1 Multi-Project Command Center
- **`GET /api/agent/planning/multi-project/command-center`** — `agent.py:835`.  
  - `MultiProjectPlanningCommandCenterQueryService.get_multi_project_command_center` (`multi_project_planning_command_center.py:355`). `@memoized_query("mpcc_command_center")`.  
  - Fans out over all registered projects with `asyncio.Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY=10)` (`multi_project_planning_command_center.py:79`).  
  - Per project: `_load_project_data` (all features + all docs) + `_build_items_for_scope` with `_NullGitProbe` to defer git I/O.  
  - After pagination: calls `_build_item` with real `WorktreeGitStateProbe` for each page-visible item — git subprocess per item.  
  - On 36 projects × (features + docs) loads, this is a large fan-out even with the semaphore.

### 4.2 Multi-Project Session Board
- **`GET /api/agent/planning/multi-project/session-board`** — `agent.py:913`.  
  - `MultiProjectActiveSessionBoardQueryService.get_multi_project_session_board` (`multi_project_planning_sessions.py:502`). `@memoized_query("mpss_session_board")`.  
  - Fans out with semaphore; per-project: 500-session fetch + feature list + entity_links.

### 4.3 System Active Count
- **`GET /api/agent/system/active-count`** — `agent.py:193`.  
  - `SystemMetricsQueryService.get_system_active_count` (`system_metrics.py:172`). `@memoized_query("system_active_count")`.  
  - Separate TTL cache (30 s, `config.py:1020`). Semaphore(10).  
  - Two queries per project (count_active + MAX(updated_at)). Concurrency guard is appropriate.  
  - `Cache-Control: max-age=30` header set at router level (`agent.py:228`). Reasonable.

---

## 5. Analytics Router

### 5.1 Analytics Bundle
- **`GET /api/analytics/overview-bundle`** — `analytics.py:~200` area.  
  - `AnalyticsBundleQueryService.get_analytics_overview_bundle` (`analytics_bundle.py:67`). `@memoized_query("analytics_overview_bundle")`.  
  - Delegates to `AnalyticsOverviewService.get_overview`. Bounded and cached.

### 5.2 Transcript Search
- **`GET /api/analytics/sessions/search`** — `analytics.py` around line 1700.  
  - `limit=5000` max (`api.py:1698`). On a 10 GB DB, full-text search over 5000 sessions with keyword matching in session_messages is unbounded.

---

## 6. Key Patterns and Cross-Cutting Issues

### 6.1 "Load All" Anti-Pattern Across Planning Services
Every planning query (`summary`, `graph`, `feature_context`, `phase_ops`, `command_center`) calls:
- `features.list_all(project_id)` → `SELECT * FROM features WHERE project_id = ? LIMIT 5000` (`features.py:260–265`)
- `documents.list_all(project_id)` → internally calls `list_paginated(0, 5000, {})` (`documents.py:394–398`)

For a project with hundreds of features and thousands of documents this is a full scan on every cache miss. There are no selective projections (SELECT specific columns) — `SELECT *` brings all JSONB/text columns including potentially large `data_json` fields.

### 6.2 Double Load in View Bundle
`get_planning_view_bundle` calls three separate service methods sequentially (`planning.py:2199, 2220, 2242`). Each of those calls `_load_all_features` + `_load_all_doc_rows` independently. There is no shared data-load pass. For a `?include=graph,session_board` request, the DB sees 6× list_all calls (2 per sub-service × 3 sub-services) per cache miss.

### 6.3 N+1 Log Fetch in Session List
`GET /api/sessions` fetches 5000 log rows per session on the list view (`api.py:628`). With `limit=50` sessions per page, that is 250,000 log rows fetched just to extract command types and summaries. These fields should be materialized/denormalized into the sessions table.

### 6.4 git subprocess per Command-Center Item
`PlanningCommandCenterQueryService._build_item` calls `git_probe.probe()` which runs `subprocess.run(["git", "status", ...])` per item (`worktree_git_state.py`). The probe has a 5-second in-process cache per path, but with 50+ features and cold cache (e.g., after container restart), this can block the event loop for multiple seconds during the probe phase. The MPCC aggregate layer correctly uses `_NullGitProbe` for off-page items but the single-project V1 command center does not.

### 6.5 Command-Center Item Lookup Is Full-Page Scan
`get_command_center_item` (`planning_command_center.py:567`) calls `get_command_center(page_size=500)` to get a single item. This loads all features, all docs, runs full planning projection, all git probes for the page. There is no DB-level lookup by feature_id.

### 6.6 Uncached Planning Command Center (V1)
`PlanningCommandCenterQueryService.get_command_center` has no `@memoized_query` decorator. Every request to the command center re-runs the full expensive build including all DB loads, planning projections, and git probes. The multi-project version (`mpcc_command_center`) IS cached but the single-project V1 is not.

### 6.7 Cross-Project entity_links Fingerprint
The cache fingerprint function reads `entity_links` without a project_id scope (`cache.py:140: "scope": None`). This means every cache-key computation across any project triggers a full table aggregate on `entity_links` — all rows, all projects. At 10 GB DB scale this query alone could take seconds.

### 6.8 feature_phases Fingerprint Is an Unbounded String Concat
`_query_feature_phases_marker` builds `GROUP_CONCAT(marker, '|')` over all phase rows for the project (`cache.py:198`). The concatenated string is then SHA-256'd. For projects with 100s of phases this is O(N_phases) string construction on every fingerprint call. With 512 cache slots and many endpoints, this fires frequently.

### 6.9 No Summary vs Detail Split for Features
The `features.list_all` query returns `SELECT *` including `data_json` (feature payload JSON). Planning services that only need `id`, `name`, `status`, `category`, `updated_at` for summary views still fetch the full row. A `list_summary` projection (minimal columns) would reduce I/O significantly on a 10 GB DB.

### 6.10 Session Board Hard-Coded 500 Session Limit
`planning_sessions.py:609–611` fetches `limit=500` sessions unconditionally. On a project with thousands of sessions (like skillmeat) this returns only the 500 most recent and silently truncates older sessions from the board. The truncation is undocumented and the board shows incomplete data.

---

## 7. Container / Enterprise Readiness Issues

### 7.1 SQLite Is the Default; aiosqlite Behavior Under Load
The cache uses a single `aiosqlite.Connection` singleton (`db/connection.py`). Concurrent service calls (planning summary + graph + session board from view bundle) all serialize through this one connection. This is the primary bottleneck in container mode.

### 7.2 Planning Query Service Singletons Created at Module Import
`agent.py:93–112` instantiates all query service singletons at module load. On a fresh container start, the TTLCache is empty and the first request to the planning page triggers the full expensive cold path for all sub-services simultaneously. No warm-up or background refresh is applied at startup.

### 7.3 Background Cache Refresh (`CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=300`)
Config exists at `config.py:986` but there is no evidence of a background task actually warming the planning query caches. The refresh interval config is not wired to any background job in the reviewed code paths.

---

## 8. Summary of Highest-Cost Endpoints (Rank Order)

| Rank | Endpoint | Why Expensive | Severity |
|------|----------|---------------|----------|
| 1 | `GET /api/sessions` (list) | N+1: 50× list_session_logs up to 5000 rows each per page | CRITICAL |
| 2 | `GET /api/agent/planning/view?include=graph,session_board` | 6× list_all (features+docs), 3× planning projection loops, no parallelism | CRITICAL |
| 3 | `GET /api/agent/planning/command-center` | Uncached; git subprocess per item; all features + docs | HIGH |
| 4 | `GET /api/agent/planning/command-center/{feature_id}` | Full page_size=500 scan to retrieve one item | HIGH |
| 5 | Cache fingerprint per call | entity_links full-table GROUP_CONCAT unscoped; feature_phases per-project GROUP_CONCAT | HIGH |
| 6 | `GET /api/agent/planning/features/{feature_id}` | Loads ALL features+docs for single-feature query | HIGH |
| 7 | `GET /api/agent/planning/multi-project/command-center` | 36-project fan-out; cached but cold path is expensive | MEDIUM |
| 8 | `GET /api/sessions/{session_id}` (detail) | 8+ sequential DB calls + 5000-log transcript | MEDIUM |

---

## 9. Concrete Fix Recommendations

### Fix 1 (CRITICAL, S-M): Materialize session summary fields
Add `command_slug`, `latest_summary`, `subagent_type` as indexed columns to the `sessions` table, populated during sync. Remove log-fetch from `GET /api/sessions` list handler.

### Fix 2 (CRITICAL, M): Parallelize view bundle sub-calls and share data load
In `get_planning_view_bundle`, do a single `_load_all_features` + `_load_all_doc_rows` pass, then fan out `summary`, `graph`, `session_board` with `asyncio.gather`.

### Fix 3 (HIGH, S): Add `@memoized_query` to `PlanningCommandCenterQueryService.get_command_center`
The V1 single-project command center is the only major planning surface without caching.

### Fix 4 (HIGH, S): Fast-path single-item lookup by feature_id
`get_command_center_item` should do a scoped DB query by feature_id rather than loading all 500 items and scanning.

### Fix 5 (HIGH, M): Scope `entity_links` fingerprint to project
Add `project_id` join or a project-scoped `updated_at` approach so the fingerprint does not aggregate all rows across all projects.

### Fix 6 (HIGH, S): Replace `features.list_all` SELECT * with projection
Add `list_summary(project_id)` variant that selects only `id, name, status, category, updated_at, data_json, phases_json` (drop large infrequently-read columns).

### Fix 7 (MEDIUM, M): Paginate or limit planning summary feature list
For summary view, only load non-terminal features by default; add a `status NOT IN ('done','deferred','completed')` WHERE clause in the list query.

### Fix 8 (MEDIUM, S): Cache the session board
Add `@memoized_query` to `PlanningSessionQueryService.get_session_board`. TTL can match planning summary (600 s default).

### Fix 9 (MEDIUM, S): Defer git probes in single-project command center
Use `_NullGitProbe` for the full build phase; re-probe only page-visible items (port the MPCC-206 pattern to V1).

### Fix 10 (LOW, S): Increase cache maxsize
Raise `TTLCache(maxsize=512)` to 2048–4096 to handle multi-project × multi-endpoint × multi-param combinations without eviction.
