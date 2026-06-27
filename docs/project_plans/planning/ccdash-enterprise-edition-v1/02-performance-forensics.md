---
schema_version: 2
doc_type: report
report_category: audits
title: "CCDash Performance Forensics Report"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Performance Forensics Report

> Companion to the orchestrator synthesis brief (`.claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md`).
> This is a **diagnosis**, not a remediation plan — every claim is anchored to a measured number or a `file:line`
> from the 12-domain forensic investigation. Fixes are named for traceability and tied to the Phase 0–6 roadmap, but
> the implementation specifications live in the per-phase plan documents.
>
> **Scope discipline:** root-cause #2 of the brief — "why it is slow." This report covers the data-volume, N+1,
> cache-correctness, frontend-fetch, and ingestion-cost defects. The container-liveness defects (root cause #1) are
> referenced only where they intersect a performance path (e.g. the disabled-by-default sync that leaves the DB empty
> *and* the blocking startup sync that runs when it is enabled).

---

## 1. Method & Evidence Basis

The investigation measured a real, in-use 10 GB SQLite cache (`data/ccdash_cache.db`) for the `skillmeat` project
(9,246 sessions, 367 features, ~533 sync cycles over ~103–151 days). Evidence falls into five measurement classes:

| Measurement class | Tooling | What it produced |
|---|---|---|
| **Row counts** | `SELECT COUNT(*)` per table | 15 table cardinalities (perf-evidence.md §1, database.md §1) |
| **Byte sizes** | `dbstat` virtual table + `SUM(length(col))` | per-column payload MB; index storage MB (database.md §1) |
| **Growth rate** | rows-per-sync × sync count; observed rows/hour | `analytics_entries` +3,313 rows/sync, ~250 rows/min, 10,246 rows in one active hour (database.md §2c) |
| **Query-count estimates** | static code trace of loop bodies × cardinality | `_capture_analytics` ~11,744–15K queries/snapshot; session list 50×5000 row fetch (perf-evidence.md §8, backend-api.md §6.3) |
| **Polling intervals & payload fan-out** | static read of `refetchInterval`, `setInterval`, mount trees | 5 s feature poll, 5 concurrent cold loads on `/planning`, hard-coded 500-session board (perf-evidence.md §7, planning-frontend.md §2) |

**Hard-evidence anchors** (perf-evidence.md §"Evidence Checklist", lines 318–331): DB file = 9.5 GB measured;
`PRAGMA cache_size` = 2000 pages = 8 MB confirmed; `analytics_entries` = 1,765,449 rows for one project, all
`period='point'`; `telemetry_events.payload_json` SUM = 1,398 MB; `session_logs` text SUM = 1,746 MB; zero
`DELETE FROM analytics_entries` anywhere in the codebase (grep-confirmed).

**Confidence:** HIGH for all volume, N+1, and cache-non-shared findings (multiple domains corroborate; numbers are
measured, not inferred). The synthesis brief rates this cluster HIGH (§9). Query-count *estimates* are clearly marked
as static traces multiplied by observed cardinality — they are order-of-magnitude, not profiler-captured.

---

## 2. The 10 GB Database Anatomy

The on-disk file is 9.86 GB raw (2,477,334 pages × 4,096 bytes) with **157 free pages** — effectively zero slack
(perf-evidence.md §1). ~3.8 GB is identifiable text in five columns; the remainder is B-tree overhead across **184
indexes**, row headers, and cross-table transcript duplication (perf-evidence.md §1). There is **no retention policy
on any table** (database.md §9; issue-ledger CRITICAL `analytics_entries unbounded`).

### 2.1 Table-by-table ledger

| Table | Rows | Payload (MB) | Growth driver | Retention | Dominant offender? |
|---|---|---|---|---|---|
| `session_logs` | 546,043 | **2,084** | full `content`+`tool_args`+`tool_output` TEXT per JSONL entry | none | **YES** — largest single store; ~1.75 GB is duplicate of `session_messages` |
| `telemetry_events` | 918,374 | **1,648** | one `payload_json` row (avg 1.6 KB, max 2.3 MB) per JSONL log entry | none | **YES** — unbounded JSON blobs, ~6K events/day/project |
| `session_messages` | 385,508 | **1,232** | canonical transcript `content` — duplicates `session_logs` | none | **YES** — second full copy of transcript data |
| `analytics_entries` | 1,798,056 | **466** | full snapshot appended every sync (~3,313 rows/sync), all `period='point'` | none | **YES** — unbounded; +250 rows/min during active sync |
| `session_usage_attributions` | 2,461,210 | ~385 (242 MB is the UNIQUE index) | ~5.84 attributions/event × 424K events | none | secondary |
| `sessions` | 9,246 | **199** | 52+ wide columns; `session_forensics_json` avg 19 KB/row = 175 MB | n/a | computed-blob bloat |
| `analytics_entity_links` | 3,580,439 | **166** | ~2 links per analytics entry; unpruned alongside parent | none | secondary (grows with `analytics_entries`) |
| `session_usage_events` | 424,570 | — | per usage event | none | — |
| `entity_links` | 26,681 | — | feature/session/doc cross-refs | n/a | small but drives the cache fingerprint scan (§4) |
| `tasks` | 10,486 | — | — | n/a | — |
| `features` | 367 | — | `data_json` BLOB blocks SQL filtering (issue-ledger HIGH) | n/a | small-count, high-per-row cost |

Sources: database.md §1 (`dbstat`), perf-evidence.md §1 (`SELECT COUNT`).

### 2.2 The four dominant offenders, ranked

1. **`session_logs` + `session_messages` dual transcript storage = 3.3 GB combined**, of which **~1.75 GB of
   `session_logs` is never purged** after the canonical `session_messages` rows exist (perf-evidence.md §10;
   database.md §2a). `SessionTranscriptService.list_session_logs` reads canonical first and only falls back to
   `session_logs` when canonical is empty (`backend/application/services/sessions.py:107–116`) — so the legacy copy is
   pure dead weight for any session that has been re-ingested. Issue-ledger: HIGH `session_logs + session_messages dual
   transcript storage`, MEDIUM `~1.75 GB of session_logs never purged`.

2. **`telemetry_events.payload_json` = 1.6 GB unbounded** (database.md §2b; `backend/db/sqlite_migrations.py:500–542`).
   918K rows, written once per JSONL log entry, deleted never. Issue-ledger: HIGH `telemetry_events.payload_json
   unbounded JSON blob storage`.

3. **`analytics_entries` = 466 MB / 1.8M rows, zero retention** (database.md §2c; perf-evidence.md §2). Every
   `sync_project()` with `capture_analytics=True` (the default, `backend/db/sync_engine.py:2938`) appends a full
   snapshot via pure `INSERT` (no `ON CONFLICT`, `sync_engine.py:5802`). Each row also writes ~2
   `analytics_entity_links` rows → the 3.6M-row join table. A 90-day retention window or an `ON CONFLICT(project_id,
   metric_type, date(captured_at))` UPSERT would cut this ~50× (1.8M → ~30–90K rows; database.md §8 Priority 1).
   Issue-ledger: CRITICAL ×2 (`analytics_entries unbounded growth`, `_capture_analytics N+1`).

4. **`sessions.session_forensics_json` = 175 MB of computed aggregate stored in-row** across 9,246 sessions
   (database.md §2d; `backend/db/sqlite_migrations.py:152–153`). This is a recomputable aggregation persisted into the
   wide `sessions` row rather than computed on read or cached with a TTL.

**Page-cache mismatch makes all of this worse:** `PRAGMA cache_size=2000` = **8 MB page cache for a 9.5 GB DB**
(`backend/db/connection.py:52–54`; confirmed via `PRAGMA cache_size`). Every analytical query (planning summaries,
forensics, fingerprint scans) pages in from disk. The 60 MB WAL indicates a checkpoint is overdue
(`wal_autocheckpoint` untuned). Issue-ledger: HIGH `SQLite PRAGMA cache_size not configured`.

---

## 3. Backend Bottlenecks — The N+1 Catalog (with query counts)

### 3.1 `_capture_analytics` — ~11,744–15K DB queries per snapshot (CRITICAL)

**File:** `backend/db/sync_engine.py:5876–5972` (perf-evidence.md §8; database.md §4a).

Per analytics snapshot, for **each of 367 features**:

| Op | Call | Count |
|---|---|---|
| task list | `task_repo.list_by_feature()` (`sync_engine.py:5883`) | 1 / feature = 367 |
| link list | `link_repo.get_links_for("feature", id, "related")` (`sync_engine.py:5930`) | 1 / feature = 367 |
| session detail | `session_repo.get_by_id(session_id)` (`sync_engine.py:5955`) | N / feature |
| tool usage | `session_repo.get_tool_usage(session_id)` (`sync_engine.py:5964`) | N / feature |
| file updates | `session_repo.get_file_updates(session_id)` (`sync_engine.py:5971`) | N / feature |

At ~10 linked sessions/feature: `367 × (1 + 1 + 10×3) = ~11,744` queries. At ~30–40 linked sessions (the
`entity_links`-derived average, database.md §4a): **~12,000–15,000 queries** per snapshot, running synchronously in
the sync loop. **Fix direction:** replace per-feature/per-session fetches with batched CTE/JOIN aggregation
(perf-evidence.md QuickWin table). Issue-ledger: CRITICAL `_capture_analytics: N+1 — 12–15K DB queries per snapshot`.

### 3.2 Session-list N+1 log fetch — 50 × 5000-row queries per page (CRITICAL)

**File:** `backend/routers/api.py:628` in `list_sessions()` (perf-evidence.md §3; backend-api.md §2.1, §6.3).

For **every** session in the page, the handler calls `session_transcript_service.list_session_logs(s, core_ports)`,
whose internal default limit is **5000 logs** (`backend/application/services/sessions.py:92`). With `SESSIONS_PAGE_SIZE
= 50` (`services/queries/sessions.ts:17`): **50 DB queries fetching up to 250,000 log rows per page load** — purely to
derive badges (`derive_session_badges`, `api.py:630`) and extract command events / latest summary (`api.py:636–647`).
Subagent sessions trigger a **second** `list_session_logs` on the parent (`api.py:660`), with only an in-memory
`parent_logs_cache` softening repeats. Badge data (models/agents/skills used) never changes after a session ends — it
must be materialized into `sessions` columns. Issue-ledger: CRITICAL `N+1 full log-fetch on session list view`; HIGH
(perf-evidence) `N+1 session log queries on every session list page load`.

### 3.3 Planning view bundle — 6× `list_all` full scans, sequential sub-calls (CRITICAL)

**File:** `PlanningQueryService.get_planning_view_bundle` (`backend/application/services/agent_queries/planning.py:2158`);
sub-calls at `planning.py:2199, 2220, 2242` (backend-api.md §1.1, §6.2).

`GET /api/agent/planning/view?include=graph,session_board` invokes three sub-services **sequentially** (no
`asyncio.gather`): `get_project_planning_summary`, `get_project_planning_graph`, `get_session_board`. Each independently
calls `features.list_all` (→ `SELECT * ... LIMIT 5000`, `features.py:260`) **and** `documents.list_all` (→
`list_paginated(0, 5000)`, `documents.py:394`). Net: **6× `list_all` scans** (2 per sub-service × 3) with **no shared
data-load pass** per cache miss. Each scan is `SELECT *`, dragging the `data_json` BLOB even when summary views need
only `id, name, status, category, updated_at`. **Fix direction:** single shared `_load_all_features` +
`_load_all_doc_rows` pass, then `asyncio.gather` the three sub-builds (backend-api.md Fix 2). Issue-ledger: CRITICAL
`Planning view bundle performs 6x list_all scans`; MEDIUM `View bundle sub-services called sequentially`.

### 3.4 `entity_graph.upsert()` — 25K individual commits per link rebuild (HIGH)

**File:** `backend/db/repositories/entity_graph.py:40` — `await self.db.commit()` after **every single link insert**
(database.md §4b). `_rebuild_entity_links` (called from `sync_engine.py:4614+`) loops `upsert()` across the **26,681**
`entity_links` rows → **~25,000 individual commits / WAL flushes** during a full rebuild. **Fix direction:** batch the
inserts and commit once per transaction. Issue-ledger: HIGH `entity_graph.upsert() — commit per link causes 25K
individual commits`.

### 3.5 Row-by-row INSERTs without `executemany` (HIGH)

Three write paths loop `await self.db.execute()` per row inside one transaction (perf-evidence.md §4):

| Write path | File:line | Volume |
|---|---|---|
| telemetry events | `backend/db/sync_engine.py:1457–1486` (Postgres path `:1529`) | 100 execs for a 100-tool-call session |
| usage events + attributions | `backend/db/repositories/usage_attribution.py:26, 53` | 424K events × ~5.84 attributions |
| session logs (`INSERT OR IGNORE`) | `backend/db/repositories/sessions.py:730–753` | 546K rows; largest session 1,984 rows |

`aiosqlite.executemany()` collapses Python round-trips into a single C-level loop (perf-evidence.md §4 fix; QuickWin
"10–50× faster per-session sync writes"). Issue-ledger: HIGH `Row-by-row INSERT without executemany`.

### 3.6 `SELECT *` across all planning services (HIGH)

Every planning query (`summary`, `graph`, `feature_context`, `phase_ops`, `command_center`) uses `features.list_all`
(`SELECT * ... LIMIT 5000`, `features.py:260–265`) and `documents.list_all` (`list_paginated(0, 5000)`,
`documents.py:394–398`) with **no column projection** (backend-api.md §6.1, §6.9). The `data_json` feature payload BLOB
is fetched even for summary views that need five columns. A `list_summary(project_id)` projection variant is the fix
(backend-api.md Fix 6). Issue-ledger: HIGH `All planning services use SELECT * list_all`.

### 3.7 Single-feature requests load the entire project (HIGH)

`get_feature_planning_context` (`planning.py:1306`) loads **ALL** project features (`_load_all_features`,
`planning.py:1334`) and **ALL** documents (`_load_all_doc_rows`, `planning.py:1343`) for a single-feature modal request,
then chains `load_execution_documents` (`planning.py:1368`) and a nested `FeatureEvidenceSummaryService.get_summary`
(`planning.py:1417`). `get_phase_operations` (`planning.py:1574`) does the same for a single phase (backend-api.md §1.4,
§1.8). `get_command_center_item` (`planning_command_center.py:567`) calls `get_command_center(page_size=500)` and scans
500 items to return **one** feature — full scan + all git probes for the page (backend-api.md §1.6, §6.5). Issue-ledger:
HIGH `get_feature_planning_context loads all features+docs`, `get_command_center_item loads 500-item full page`.

### 3.8 git subprocess per command-center item (HIGH)

`PlanningCommandCenterQueryService._build_item` calls `git_probe.probe()` →
`subprocess.run(["git", "status", ...])` **per feature** (`backend/.../worktree_git_state.py`; backend-api.md §1.5,
§6.4) with a 0.8 s timeout and 5 s in-process TTL. On a 50-feature project with a cold cache (post-restart), that is up
to **50 synchronous subprocess spawns per request** blocking the event loop. The multi-project aggregate correctly uses
`_NullGitProbe` for off-page items; the V1 single-project center does not (backend-api.md Fix 9). Issue-ledger: HIGH
`git subprocess spawned per command-center item in V1`.

### 3.9 Highest-cost endpoint rank order (backend-api.md §8)

| Rank | Endpoint | Why | Severity |
|---|---|---|---|
| 1 | `GET /api/sessions` (list) | 50× `list_session_logs` up to 5000 rows each | CRITICAL |
| 2 | `GET /api/agent/planning/view?include=graph,session_board` | 6× `list_all`, sequential, no parallelism | CRITICAL |
| 3 | `GET /api/agent/planning/command-center` | uncached; git subprocess per item; all features+docs | HIGH |
| 4 | `GET /api/agent/planning/command-center/{feature_id}` | page_size=500 scan for one item | HIGH |
| 5 | cache fingerprint (per call) | `entity_links` global GROUP_CONCAT + `feature_phases` GROUP_CONCAT | HIGH |
| 6 | `GET /api/agent/planning/features/{feature_id}` | loads ALL features+docs for one feature | HIGH |
| 7 | `GET /api/sessions/{session_id}` (detail) | 8+ sequential DB round-trips + 5000-log transcript | MEDIUM |

---

## 4. Cache Cost & Correctness

The cache is a single in-process `cachetools.TTLCache(maxsize=512, ttl=600)` allocated at module import
(`backend/application/services/agent_queries/cache.py:50`; caching.md §"Architecture"). 14 service methods carry
`@memoized_query`. Five distinct defects make it slow *and* wrong at enterprise scale.

### 4.1 The fingerprint runs 6 DB queries before every cache lookup (CRITICAL)

`get_data_version_fingerprint()` (`cache.py:84–142`) fires **6 sequential SQL queries on every request to every cached
endpoint** — even on a cache **hit**, because the fingerprint is part of the cache key (caching.md §"Fingerprint";
backend-api.md §3.2):

| # | Table | Query | Scope |
|---|---|---|---|
| 1 | `sessions` | `MAX(updated_at)` | project |
| 2 | `features` | `MAX(updated_at)` | project |
| 3 | `feature_phases` | `COUNT + GROUP_CONCAT(all phase markers)` via JOIN | project, **O(N) string concat** |
| 4 | `documents` | `MAX(updated_at)` | project |
| 5 | `entity_links` | `COUNT + GROUP_CONCAT(marker) ORDER BY ...` | **GLOBAL — no project_id filter** |
| 6 | `planning_worktree_contexts` | `MAX(updated_at)` | project |

### 4.2 `entity_links` fingerprint is an unscoped global GROUP_CONCAT scan (CRITICAL)

**File:** `cache.py:258–289` (`_query_entity_links_marker`). The query has **no `WHERE project_id = ?`** because the
`entity_links` table **has no `project_id` column** (`backend/db/sqlite_migrations.py:37–56`; caching.md §"Critical
issue"). It `GROUP_CONCAT`s a sorted marker string across **all 26,681 rows spanning every project**, then SHA-256s it —
on **every** cached request. SQLite cannot parallelize; this serializes against the sync engine's writes (WAL eases but
does not eliminate contention). **Fix direction:** add `project_id` to `entity_links` and scope the fingerprint, OR
replace it with a sync-engine-maintained `entity_links_version` counter (caching.md Tier 4; backend-api.md Fix 5;
synthesis brief §6.5). Issue-ledger: CRITICAL `entity_links fingerprint is a full global table scan`; HIGH `Cache
fingerprint runs unscoped entity_links GROUP_CONCAT across all projects`.

### 4.3 The fingerprint itself is not cached (MEDIUM)

There is no secondary TTL on the fingerprint result (caching.md §"Fingerprint is NOT itself cached"; backend-api.md
§3.2). With 10 concurrent users, every cached-endpoint request pays the 6-query cost regardless of the 600 s entry TTL. A
5–10 s fingerprint cache amortizes this (caching.md Tier 3). Issue-ledger: MEDIUM `Fingerprint computation is not itself
cached — 6 DB queries per request`; HIGH `feature_phases fingerprint is O(N) string concat`.

### 4.4 In-process cache is not shared across api+worker containers (CRITICAL)

The `TTLCache` lives in one OS process (`cache.py:50`). In enterprise mode, `api` and `worker` are separate containers,
and **multiple `api` replicas each hold an independent cache** (caching.md §"Enterprise gaps"; documented in
`docs/guides/query-cache-tuning-guide.md:17`). Worse, background warming runs **only in `jobs`-capable profiles**
(`backend/runtime/profiles.py:41–52` — `api` profile is `jobs=False`; `backend/adapters/jobs/runtime.py:192` gates
warming on `profile.capabilities.jobs`). The **api container that serves traffic is never warmed** — it is perpetually
cold/inconsistent. **Fix direction:** shared Redis/Valkey cache (synthesis brief §6.1; Phase 2). Issue-ledger: CRITICAL
`In-process cache is not shared across enterprise api+worker containers`.

### 4.5 No post-sync invalidation (HIGH)

The **only** `clear_cache()` call site is `PlanningQueryService.resolve_open_question()` (`planning.py:1567`).
The sync endpoints `POST /api/cache/sync` and `POST /api/cache/sync-paths` (`backend/routers/cache.py:363–424`) do
**not** invalidate after `sync_project()` completes (caching.md §"Invalidation on Write"). After a full sync ingests new
sessions/features, `project_status`, `workflow_diagnostics`, and all planning surfaces serve stale data for up to the
600 s TTL. **Fix direction:** project-scoped invalidation (or Postgres `NOTIFY` / Redis pub-sub) on sync completion
(caching.md Tier 5; Phase 2). Issue-ledger: HIGH `No cache invalidation triggered after sync_project completes`.

### 4.6 Documented per-metric TTLs are never enforced (HIGH)

`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (10 s, `config.py:987–994`) and `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` (30 s,
`config.py:1015–1023`) are documented (and `agent.py:212` claims server-side caching at that TTL) but **never fed into
any TTL slot** — the single `TTLCache` bakes one global TTL at import (caching.md §"Documented-but-Broken"). An operator
setting these sees no effect; live count can stay cached for the full 600 s when no new session appears. Issue-ledger:
HIGH `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS and CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS are documented but never enforced`.

### 4.7 Warming covers 2 of 14 endpoints; maxsize=512 too small (MEDIUM)

Background warming (`runtime.py:840–982`) warms only `project_status` and `workflow_diagnostics` and only the
active/bound project (caching.md §"Warming"; synthesis brief §2c). The other 12 — including `planning_project_summary`,
`analytics_overview_bundle`, `dashboard_bundle`, `system_active_count` — are demand-only. `maxsize=512` is exceeded by
36+ projects × 14 endpoints × per-feature/per-phase param variants, forcing LRU eviction and degrading hit rate
(caching.md §"maxsize"). Issue-ledger: MEDIUM ×3 (`warming only 2 of 14+`, `maxsize=512 insufficient`, `warming only
warms bound/active project`).

---

## 5. Frontend Rendering & Fetching

### 5.1 V1 PlanningCommandCenter bypasses TanStack Query (CRITICAL)

**File:** `components/Planning/CommandCenter/PlanningCommandCenter.tsx:94, 133–161` (planning-frontend.md §1.2,
CRIT-02). It uses a **raw `useEffect` + manual fetch** to `GET /api/agent/planning/command-center?page_size=50` with a
`load` callback *and* a duplicate mount effect that can race — no TQ cache, no dedup, no stale-while-revalidate, no
background refresh. Every navigation to `/planning` re-fetches the command center cold against the 10 GB backend.
Issue-ledger: CRITICAL `V1 PlanningCommandCenter bypasses TanStack Query`. The backend side compounds it: this endpoint
has **no `@memoized_query`** (`planning_command_center.py:351`; backend-api.md §6.6). Issue-ledger: HIGH
`PlanningCommandCenterQueryService (V1) has no @memoized_query cache`.

### 5.2 Session board: no server pagination, no V1 virtualization (CRITICAL + HIGH)

`GET /api/agent/planning/session-board` fetches sessions with a **hard-coded `list_paginated(offset=0, limit=500)`**
(`backend/application/services/agent_queries/planning_sessions.py:609`) — no cursor, no page param — and silently
truncates older sessions on projects with thousands (backend-api.md §6.10; planning-frontend.md CRIT-01). The V1
`PlanningAgentSessionBoard` renders **all** rich cards into fixed-height CSS-scroll columns (`maxHeight: 520`,
`PlanningAgentSessionBoard.tsx:819`) with **no `useVirtualizer`** (planning-frontend.md HIGH-03). Each card carries 8+
DOM nodes plus token/correlation/relationship fan-out (planning-frontend.md §5). Issue-ledger: CRITICAL `Session board
has no server-side pagination`; HIGH `V1 session board has no virtualization`.

### 5.3 Five concurrent cold-load requests on `/planning` entry (HIGH)

`PlanningHomePage` always-mounts both `PlanningCommandCenterShell` (`PlanningHomePage.tsx:842`) and
`PlanningAgentSessionBoard` (`:919`), and `PlanningRouteLayout` fires `useSessionsQuery` + `useFeaturesQuery` on every
`/planning/*` route (`PlanningRouteLayout.tsx:146–147`). Cold-load total = **5 concurrent above-fold requests**: view
bundle, command-center, session-board, sessions, features (planning-frontend.md §2, HIGH-01, HIGH-03 of perf table).
None is viewport-deferred. Issue-ledger: HIGH `Planning home always-mounts session board and command center — 5
concurrent cold-load requests`.

### 5.4 `useData()` shim is non-reactive (HIGH)

**File:** `contexts/DataContext.tsx:132–167` (frontend-core.md §2.2). `useData()` reads each domain via
`queryClient.getQueryData(...)` — a **one-time snapshot**, not a reactive `useQuery()` subscription. When a TQ background
refetch completes, the **13+ components** still consuming the facade (`OpsPanel.tsx:272`, `PlanningHomePage.tsx:928`,
`ProjectBoard.tsx:1072`, `SessionInspector.tsx:3957`, etc.; frontend-core.md §2.3) do **not** re-render with fresh data
unless they re-render for an unrelated reason. `sessions`, `documents`, `features`, `tasks`, `alerts`, `notifications`
are all affected. **Fix direction:** replace snapshot reads with `useQuery()` or remove the facade (frontend-core.md
Rec 1). Issue-ledger: HIGH `useData() shim uses getQueryData() not useQuery()`.

### 5.5 Polling storm: 5 s feature poll, staleTime:0, setInterval sprawl (HIGH + MEDIUM)

- **`useFeaturesQuery` polls every 5 s when SSE is off** (`services/queries/features.ts:85`,
  `refetchInterval: isFeatureLiveUpdatesEnabled() ? false : 5_000`). `isFeatureLiveUpdatesEnabled()` reads
  `VITE_CCDASH_LIVE_FEATURES_ENABLED`, **default `false`** (`services/live/config.ts:21–23`) — the enterprise default.
  That is **12 req/min** to the **uncached** legacy `GET /api/features` (`features.py:837`, no `@memoized_query`), which
  runs `list_paginated` + `count` + a **per-feature `get_phases()` N+1 loop** (`features.py:868`) + execution-state
  derivation per poll (caching.md HIGH `Feature list default 5-second polling`; frontend-core.md §3.1). Issue-ledger:
  HIGH `useFeaturesQuery polls every 5 s` + `Legacy /api/features polled every 5s with N+1 queries`.
- **`useFeatureSurface` list tier `staleTime: 0`** (`services/useFeatureSurface.ts:348`) — data is stale immediately, so
  every mount of `ProjectBoard`/`Dashboard` triggers a background refetch + cascading rollup batch (frontend-core.md
  §3.1). Issue-ledger: HIGH `useFeatureSurface list tier staleTime: 0 refetches on every mount`. Same pattern, lower
  severity, on `usePlanningSummaryQuery` (`planning.ts:72`, LOW).
- **`setInterval` sprawl across 8+ components** bypassing TQ visibility/dedup: `Dashboard.tsx:117` (10 s live agents),
  `SystemMetricsChip.tsx:73` (30 s), `ProjectBoard.tsx:1422` (15 s feature-modal poll), `OpsPanel.tsx:885,900`
  (2.5–15 s adaptive + 10 s), `SessionInspector.tsx:4646,5652`, `PlanningAgentSessionBoard.tsx:880` (15 s
  `StaleIndicator` tick that starts from mount regardless of staleness) (frontend-core.md §3.2; planning-frontend.md
  MED-05). Issue-ledger: MEDIUM `Multiple manual setInterval polls bypass TQ`, `StaleIndicator setInterval starts
  immediately`.

### 5.6 Raw analytics fetches outside TQ re-fire on length changes (MEDIUM)

`Dashboard.tsx:251–253` makes 3 parallel `analyticsService.*` calls in a `useEffect` keyed on
`[sessions.length, tasks.length]` — a background TQ refetch that changes either length **re-fires all three** uncached
fetches (frontend-core.md §3.3). `AnalyticsDashboard.tsx:151–158` fires **7 parallel raw fetches on every mount** with
no TQ wrapper. Issue-ledger: MEDIUM `Dashboard analytics chart fetches outside TQ`, `AnalyticsDashboard fires 7 parallel
raw fetches`.

### 5.7 Monolith re-render risk (MEDIUM)

`SessionInspector.tsx` (6,101 lines) has virtualizers only in detail sub-panels (`:5749, :5758`) but **no `React.memo`
on inner panels** — any state change re-renders the entire tree (frontend-core.md §7, §8). `ProjectBoard.tsx`
(3,895 lines) re-renders the **entire feature modal every 15 s** via its `FEATURE_MODAL_POLL_INTERVAL_MS` poll
(`ProjectBoard.tsx:1422`) with un-memoized cards. Issue-ledger: MEDIUM `SessionInspector 6101-line monolith has no
React.memo`, `ProjectBoard 3895-line monolith re-renders entire feature modal every 15 s poll`.

### 5.8 Container-specific frontend defects (MEDIUM)

- **`GEMINI_API_KEY` baked into the JS bundle** via Vite `define` (`vite.config.ts:84–87`) — exposed in static enterprise
  builds (frontend-core.md §10.4). Issue-ledger: MEDIUM `GEMINI_API_KEY baked into JS bundle`.
- **Google Fonts CDN** injected on every planning route (`PlanningRouteLayout.tsx:31–48`) hangs/fails silently in
  restricted-egress containers; no offline fallback (planning-frontend.md MED-04). Issue-ledger: MEDIUM `Planning fonts
  loaded from Google Fonts CDN`.
- **`MULTI_PROJECT_COMMAND_CENTER_ENABLED` is a Vite build-time constant** (`constants.ts:418–421`) requiring a rebuild
  to enable in a container (planning-frontend.md MED-03). Issue-ledger: MEDIUM `build-time constant, requires rebuild`.
- **Hover prefetch bypasses TQ cache**: `prefetchFeaturePlanningContext` (`services/planning.ts:848`) calls
  `getFeaturePlanningContext` directly instead of `queryClient.prefetchQuery` — data is fetched and discarded; the modal
  still issues a fresh request on open (planning-frontend.md HIGH-02). Issue-ledger: HIGH `Hover prefetch bypasses TQ
  cache`.

---

## 6. Ingestion / Sync Cost

### 6.1 Full `rglob` + N DB lookups on every startup — no manifest skip for sessions (HIGH)

**File:** `backend/db/sync_engine.py:4107–4119` (`_sync_sessions`). Every startup sync runs `rglob("*.jsonl")` over the
entire sessions dir, and for **each** file does `path.stat().st_mtime` + `sync_repo.get_sync_state(sync_file_path)` —
**two I/O ops per file just to decide it is unchanged** (ingestion-fs.md Finding 5). The light-mode scan skip
(`_light_mode_scan_skip`, `sync_engine.py:4239–4278`) covers **only** documents/progress `.md` files, not JSONL
sessions. On a 5,000-file directory: 5,000 stats + 5,000 DB lookups before concluding nothing changed, against a 10 GB
WAL where those lookups are themselves slow. Issue-ledger: HIGH `No manifest-based skip for session JSONL scan`.

### 6.2 Sequential single-row backfill loops (MEDIUM)

`_backfill_telemetry_events_for_project` and `_backfill_commit_correlations_for_project`
(`sync_engine.py:2061–2097, 2252–2284`) iterate sessions **one-by-one** with per-session `get_logs` / `get_tool_usage` /
`get_file_updates` / `get_artifacts` SELECTs — up to **~37,000 individual SELECTs per full backfill** across 9,246
sessions (database.md §4c; ingestion-fs.md Finding 10). On Postgres these are O(N) sequential round-trips that never
exploit the `asyncpg.Pool` parallelism. Issue-ledger: MEDIUM `Backfill loops during startup sync are sequential
single-row DB round-trips`.

### 6.3 `sessions.source_file` full-scan on every watch event (HIGH)

**File:** `backend/db/repositories/sessions.py:161–167` (`list_by_source`, `WHERE source_file = ?`), called on every
file-watch event at `sync_engine.py:4121–4130`. There is **no index on `sessions.source_file`** — `EXPLAIN` shows `SCAN
sessions` (database.md §3b). At 9,246 rows this is ~1 ms; at 100K sessions it is ~100 ms **per watch event**. The
existing `ix_sessions_source_ref` covers a *different* column (`source_ref`). Issue-ledger: HIGH `sessions.source_file —
no index causes full table scan on every file-watch event`.

### 6.4 Startup sync is blocking and serializes on one SQLite connection (HIGH)

`_run_startup_sync_pipeline` (`runtime.py:731–784`) awaits `sync_project` on the main loop. When
`STARTUP_SYNC_LIGHT_MODE=False` (the `config.py:966` default), it passes `rebuild_links=True, capture_analytics=True,
backfill_session_intelligence=True` — i.e. the §3.1 12–15K-query analytics N+1 *and* the §3.4 25K-commit link rebuild
*and* the §6.2 37K-SELECT backfill all run during startup, holding the single `aiosqlite` connection
(`backend/db/connection.py` singleton) for the full duration (ingestion-fs.md Finding 10). A config/runtime fallback
mismatch (`config.py` default `False` vs `runtime.py:731` `getattr(..., True)`, ingestion-fs.md Finding 4) means
behavior depends on which path reads the flag. Issue-ledger: MEDIUM `STARTUP_SYNC_LIGHT_MODE getattr fallback default
mismatch`.

### 6.5 Adjacent correctness defects that also waste sync work

- **Watcher delete uses raw path, not canonical key** (`sync_engine.py:3944` `delete_by_source(str(path))` vs the correct
  `:4171` `delete_by_source(sync_file_path)`) — watcher-triggered deletes leave orphan rows that then bloat the DB and
  must be re-scanned (ingestion-fs.md Findings 2, 7). Issue-ledger: HIGH `Watcher-triggered session delete uses raw path
  string`.
- **Source-path aliases not populated from `ResolvedProjectPaths`** — unconfigured mounts produce `opaque/<hash>` keys
  that re-parse files and can duplicate sessions (ingestion-fs.md Finding 2). Issue-ledger: HIGH `Source-path alias
  policy not populated from ResolvedProjectPaths`. (This intersects the container-liveness root cause but directly
  causes duplicate-row growth.)

---

## 7. Bottleneck Table (CRITICAL + HIGH perf / db / caching / backend)

One row per distinct bottleneck. Severity per issue-ledger.md. Quick-win = S complexity AND no schema/architecture
migration required.

| Bottleneck | Evidence (file:line) | Sev | Affected UX path | Likely fix | Cplx | Quick-win? |
|---|---|---|---|---|---|---|
| `analytics_entries` unbounded (1.8M rows / 466 MB, no retention) | `sync_engine.py:5802`, `repositories/analytics.py` (no DELETE) | CRIT | DB size; all analytical reads slow | 90-day retention DELETE + `ON CONFLICT` upsert | M | partial (DELETE is S) |
| `_capture_analytics` N+1 (~11.7–15K queries/snapshot) | `sync_engine.py:5876–5972` | CRIT | sync duration; startup blocking | batch via CTE/JOIN; remove per-session fetch | L | no |
| Session-list N+1 log fetch (50×5000 rows/page) | `routers/api.py:628`; `services/sessions.py:92` | CRIT | `/sessions` list view latency | materialize badge cols on `sessions`; drop log fetch | M | no |
| Planning view bundle 6× `list_all`, sequential | `planning.py:2158, 2199, 2220, 2242` | CRIT | `/planning` cold load | shared load pass + `asyncio.gather` | M | no |
| `entity_links` fingerprint = global GROUP_CONCAT scan | `cache.py:258–289`; `sqlite_migrations.py:37–56` (no `project_id`) | CRIT | every cached endpoint | add `project_id` + scope, OR version counter | M | no |
| In-process cache not shared across containers | `cache.py:50`; `profiles.py:41–52`; `runtime.py:192` | CRIT | all cached reads in enterprise | shared Redis/Valkey | L | no |
| V1 command center bypasses TQ (FE) | `PlanningCommandCenter.tsx:94, 133–161` | CRIT | `/planning` re-fetch every nav | migrate to `useQuery` | M | no |
| Session board no server pagination (500 hard cap) | `planning_sessions.py:609`; `services/planning.ts:922` | CRIT | session board load + truncation | cursor pagination param | L | no |
| `SQLite cache_size=2000` (8 MB / 9.5 GB) | `db/connection.py:52–54` | HIGH | every uncached query | add `PRAGMA cache_size/mmap_size/synchronous=NORMAL` | S | **YES** |
| Row-by-row INSERT (no `executemany`) | `sync_engine.py:1457`; `usage_attribution.py:26,53`; `sessions.py:730` | HIGH | sync write throughput | `executemany` | S | **YES** |
| `entity_graph.upsert` commit-per-link (25K commits) | `entity_graph.py:40` | HIGH | link rebuild duration | batch + single commit | M | no |
| `idx_sessions_project_status_updated` missing from live DB | `sqlite_migrations.py:161–162` (DDL-only, not backfilled) | HIGH | `count_active` / `list_active` | add via `_ensure_index` backfill | S | **YES** |
| `sessions.source_file` no index (full scan/watch event) | `repositories/sessions.py:161–167`; `sync_engine.py:4121` | HIGH | watcher latency at scale | `CREATE INDEX idx_sessions_source_file` | S | **YES** |
| `session_logs`+`session_messages` dup (~1.75 GB dead) | `services/sessions.py:107–116`; `sqlite_migrations.py:192–225` | HIGH | DB size | purge orphaned `session_logs` after canonical | M | no |
| `telemetry_events.payload_json` 1.6 GB no TTL | `sqlite_migrations.py:500–542` | HIGH | DB size | retention/compression/offload | M | no |
| Postgres `upsert_logs`/`upsert_file_updates` non-atomic | `repositories/postgres/sessions.py:88+` | HIGH | data loss on partial fail | wrap in `postgres_transaction` | M | no |
| Cache fingerprint unscoped + uncached (6 q/req) | `cache.py:84–142, 195–289` | HIGH | every cached endpoint | cache fingerprint 5–10 s; scope it | S–M | partial |
| Per-metric TTLs unenforced | `cache.py:50`; `config.py:987–1023` | HIGH | live count staleness | separate TTL buckets / Redis key TTL | S | **YES** |
| No post-sync cache invalidation | `routers/cache.py:363–424`; only `planning.py:1567` clears | HIGH | stale dashboard ≤600 s post-sync | `clear_cache(project)` after sync | S | **YES** |
| `/api/features` legacy 5 s poll, uncached, N+1 phases | `services/queries/features.ts:85`; `features.py:837, 868` | HIGH | feature surface load | `@memoized_query` + raise interval/staleTime | M | partial |
| `useData()` non-reactive snapshot (13+ consumers) | `DataContext.tsx:132–167` | HIGH | stale UI across app | `useQuery()` or remove facade | M | no |
| `useFeatureSurface` list `staleTime:0` | `services/useFeatureSurface.ts:348` | HIGH | refetch every mount | set staleTime 10–30 s | S | **YES** |
| `staleTime:0` on planning summary | `services/queries/planning.ts:72` | LOW | refetch every Planning mount | set staleTime ≥5 s | S | **YES** |
| V1 session board no virtualization | `PlanningAgentSessionBoard.tsx:819` | HIGH | board first-render jank | `useVirtualizer` on columns | M | no |
| Hover prefetch bypasses TQ cache | `services/planning.ts:848` | HIGH | cold modal despite hover | use `queryClient.prefetchQuery` | S | **YES** |
| git subprocess per command-center item | `worktree_git_state.py`; `planning_command_center.py:607` | HIGH | command center cold load | `_NullGitProbe` for off-page items (port MPCC) | S | **YES** |
| `get_command_center_item` 500-item page scan | `planning_command_center.py:567` | HIGH | single feature open | DB lookup by `feature_id` | S | **YES** |
| `get_feature_planning_context` loads all features+docs | `planning.py:1306, 1334, 1343` | HIGH | feature modal latency | scoped load; cache feature index | M | no |
| `SELECT *` `list_all` all planning services | `features.py:260`; `documents.py:394` | HIGH | every planning read I/O | `list_summary` column projection | M | no |
| No manifest skip for JSONL session scan | `sync_engine.py:4107–4119` | HIGH | startup duration | inode/mtime manifest skip | M | no |
| Startup sync blocking on single SQLite conn | `runtime.py:731–784` | HIGH | API responsiveness at boot | default light-mode + deferred heavy passes | M | no |

---

## 8. Instrumentation Plan

There is **no OTEL instrumentation** for the analytics snapshot, the session-list badge derivation, or sync INSERT batch
sizes (perf-evidence.md §11; issue-ledger MEDIUM `No OTEL instrumentation for analytics snapshot...`). `otel.py` has
`record_ingestion()` (`backend/observability/otel.py:640`) but no histogram/counter for the worst paths. Add these exact
points (Phase 6; some land earlier with the fixes they measure):

| # | Instrument | Exact insertion point | OTEL metric to emit | Why |
|---|---|---|---|---|
| 1 | analytics-snapshot duration + rows written | entry of `_capture_analytics` at `backend/db/sync_engine.py:5787` (wrap span; counter at the `insert_entry` call `:5802`) | `ccdash_analytics_snapshot_duration_ms{project_id}` (Histogram), `ccdash_analytics_entries_written_total{project_id}` (Counter) | proves the §3.1 N+1 cost and validates the retention fix |
| 2 | session-list badge derivation latency | wrap the badge loop at `backend/routers/api.py:624` (`otel.start_span("sessions.list.badge_derivation", {"session_count": n})`) | `ccdash_session_list_badge_derivation_ms{page_size}` (Histogram) | quantifies the §3.2 N+1 before/after materialization |
| 3 | sync INSERT batch size | at `backend/db/sync_engine.py:1457` (telemetry loop), value = `len(events)` | `ccdash_sync_session_insert_batch_size` (Histogram) | confirms `executemany` collapses per-row round-trips (§3.5) |
| 4 | cache fingerprint cost | wrap `get_data_version_fingerprint` at `backend/application/services/agent_queries/cache.py:84`; separately time the `entity_links` marker at `cache.py:258` | `ccdash_cache_fingerprint_ms{endpoint}`, `ccdash_cache_fingerprint_entity_links_ms` (Histograms) | proves the §4.1–4.2 6-query / global-scan cost and the fingerprint-cache win |
| 5 | payload bytes per heavy endpoint | response-size middleware on `/api/sessions`, `/api/agent/planning/view`, `/api/agent/planning/session-board` | `ccdash_response_payload_bytes{endpoint}` (Histogram) | quantifies the §5.2/§5.3 fan-out and validates pagination/projection |
| 6 | SQLite page-cache stats | after PRAGMA setup at `backend/db/connection.py:54` (`PRAGMA stats` / cache-miss count) | `ccdash_sqlite_cache_miss_count` (Gauge) | proves the §2.2 8 MB → 128 MB cache_size win |
| 7 | startup-sync duration + sessions synced | `_run_startup_sync_pipeline` lifespan at `backend/adapters/jobs/runtime.py:731` | `ccdash_startup_sync_duration_ms`, `ccdash_startup_sync_sessions_synced` (Histogram/Counter) | quantifies §6.1/§6.4 blocking startup |
| 8 | feature-surface poll interval | `services/queries/features.ts:85` resolution → emit gauge on configured `refetchInterval` | `ccdash_feature_surface_poll_interval_ms` (Gauge) | makes the §5.5 5 s-vs-30 s default visible in ops |
| 9 | link-rebuild commit count | counter around `entity_graph.upsert` commits at `backend/db/repositories/entity_graph.py:40` | `ccdash_entity_link_commits_total` (Counter) | proves the §3.4 25K-commit win after batching |

`otel.py` skeleton additions (perf-evidence.md §2): declare `_analytics_snapshot_duration_hist` and
`_analytics_entries_written_counter` after `_ingestion_latency_hist` initialization. Existing live-ingest OTel follow-ups
FU-3/FU-5/FU-7 remain open (issue-ledger MEDIUM `Live ingest follow-ups`) and should fold into this plan.

---

## 9. Quick Wins vs Deep Refactors

### Quick wins (S complexity, no schema/architecture migration, high ROI)

Ranked by impact-per-effort. Each is a Phase 0/1 candidate.

1. **SQLite PRAGMAs** — add `cache_size=-131072` (128 MB), `mmap_size=4294967296` (4 GB), `synchronous=NORMAL`,
   `wal_autocheckpoint=1000`, `temp_store=MEMORY` at `connection.py:54`. ~5–10× query speed on the 9.5 GB DB
   (perf-evidence.md QuickWin; §2.2). **Single highest impact-per-line change.**
2. **`executemany` for telemetry / usage / log INSERTs** (`sync_engine.py:1457`, `usage_attribution.py:26,53`,
   `sessions.py:730`) — 10–50× faster per-session sync writes (§3.5).
3. **`analytics_entries` 90-day retention DELETE** in `_capture_analytics` — stops unbounded growth; 1.8M → ~30–90K rows
   (database.md Priority 1; §2.1).
4. **Backfill the two missing indexes** via `_ensure_index`: `idx_sessions_project_status_updated` and
   `idx_sessions_source_file` (database.md §3a/§3b; §6.3). Removes the watch-event full scan and the `count_active`
   residual filter.
5. **Post-sync cache invalidation** — call project-scoped `clear_cache()` after `sync_project()` in
   `routers/cache.py:363–424` (§4.5). Kills the ≤600 s stale window.
6. **Cache the fingerprint** for 5–10 s and **enforce per-metric TTL buckets** (`cache.py`; §4.3/§4.6). Removes 6
   queries/request on hot paths.
7. **Frontend staleTime/poll fixes** — `useFeatureSurface` list `staleTime: 0 → 10–30 s` (`useFeatureSurface.ts:348`);
   `useFeaturesQuery` `refetchInterval 5_000 → 30_000` when SSE off (`features.ts:85`); planning summary
   `staleTime ≥5 s` (`planning.ts:72`) (§5.5).
8. **`_NullGitProbe` for off-page command-center items** + **single-item DB lookup by `feature_id`**
   (`planning_command_center.py:567,607`) — port the MPCC pattern to V1 (§3.7/§3.8).
9. **Fix hover prefetch** to use `queryClient.prefetchQuery` (`services/planning.ts:848`) so the modal opens warm
   (§5.8).

### Deep refactors (M–XL, schema/architecture migration, sequenced into Phases 1–4)

Ranked by enterprise-correctness criticality.

1. **Shared cache (Redis/Valkey)** replacing the in-process `TTLCache` singleton — the single most important enterprise
   correctness fix; kills per-replica cold/inconsistent caches and unwarmed `api` containers (§4.4; synthesis brief §6.1;
   **Phase 2**).
2. **`_capture_analytics` batch rewrite** (CTE/JOIN) — eliminate the ~12–15K-query N+1 (§3.1; **Phase 1**).
3. **Materialize session badge columns** (`models_used_json`, `agents_used_json`, `skills_used_json`,
   `command_slug`, `latest_summary`, `subagent_type`) on `sessions`, populated at sync; drop the list-view log fetch
   (§3.2; backend-api.md Fix 1; **Phase 1**).
4. **Scope the `entity_links` fingerprint** — add `project_id` to `entity_links` (or a sync-maintained version counter)
   so the fingerprint stops scanning all projects (§4.2; **Phase 2**, depends on Phase 1 schema work).
5. **Summary/detail endpoint split + `list_summary` projection + `asyncio.gather` bundle** — kill the 6× `SELECT *`
   `list_all` and sequential sub-calls; lazy-load detail per tab (§3.3/§3.6; **Phase 2**).
6. **Transcript dedupe** — purge orphaned `session_logs` after canonical `session_messages` exist; reclaim ~1.75 GB
   (§2.2; **Phase 1**; transcript-storage decision is open per synthesis brief §8).
7. **`telemetry_events` retention/compression/offload** — reclaim ~1.4 GB (§2.1; **Phase 1**).
8. **Batch `entity_graph.upsert`** into a single transaction — remove the 25K commits (§3.4; **Phase 1**).
9. **Session-board server pagination (cursor)** + **V1 board virtualization** + **V1 command center → TQ** +
   **viewport-deferred mounting** — collapse the 5 concurrent cold loads and the O(N) board payload (§5.1/§5.2/§5.3;
   **Phase 4**).
10. **Make `useData()` reactive** (or remove it) and **migrate Dashboard/AnalyticsDashboard raw fetches to TQ** (§5.4,
    §5.6; **Phase 4**).
11. **Manifest-based session-scan skip** + **light-mode-default blocking-sync fix** + **concurrent/batched backfill**
    (§6.1/§6.2/§6.4; **Phase 1/3**).
12. **Postgres atomicity** — wrap `upsert_logs`/`upsert_file_updates`/`upsert_artifacts`/`upsert_tool_usage` in
    `postgres_transaction` (database.md §5c; **Phase 1**, correctness gate for the enterprise primary target).

---

## Appendix — Cross-reference index

Every numbered claim above maps to: `issue-ledger.md` (severity/complexity/area) and the cited domain finding
(`perf-evidence.md`, `database.md`, `caching.md`, `backend-api.md`, `frontend-core.md`, `planning-frontend.md`,
`ingestion-fs.md`). Phase boundaries (0–6) and target-architecture decisions are taken verbatim from
`synthesis-brief.md` §6–7; this report introduces no new phase scheme. Open human decisions affecting these fixes
(shared-cache tech, transcript storage, worker topology, SQLite-in-enterprise) are tracked in `synthesis-brief.md` §8.
