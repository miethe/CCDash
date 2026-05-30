# CCDash Performance & Enterprise Readiness Investigation
## perf-evidence.md — Domain: perf-evidence
### Date: 2026-05-30

---

## Executive Summary

The 10 GB SQLite database and reported app slowness on large projects (e.g. "skillmeat", 9246 sessions) have five compounding root causes:

1. **Analytics rows accumulate without TTL or purge** — 1.77M rows for a single project across ~533 syncs, N+1 DB queries per sync per feature.
2. **Session list endpoint has an N+1 query per page** — `list_session_logs()` is called once per session in every `GET /api/sessions` response, for badge derivation only.
3. **Row-by-row INSERTs without `executemany`** — telemetry events, usage events, usage attributions, and session logs are each written in Python `for`-loops.
4. **SQLite is severely under-configured** — 8 MB page cache (`PRAGMA cache_size=2000`) for a 9.5 GB database; no `cache_size`, `mmap_size`, or `wal_autocheckpoint` tuning.
5. **Enterprise container bootstrap is broken by default** — the `api` runtime has `sync=False` in its capabilities; the `worker` runtime defaults to `CCDASH_STARTUP_SYNC_ENABLED=false` in `compose.yaml`; so a vanilla enterprise deployment has no filesystem ingestion at all.

---

## 1. Database Size Analysis (Measured)

### Raw numbers

| Metric | Value |
|--------|-------|
| DB file | 9.5 GB |
| WAL file | 60 MB |
| Page count | 2,477,334 × 4,096 bytes = 9.86 GB raw |
| Free pages | 157 (essentially zero free space) |
| SQLite `cache_size` | 2,000 pages = **8 MB** |

### Row counts (measured via `SELECT COUNT(*)`)

| Table | Rows | Est. text payload |
|-------|------|-------------------|
| `session_usage_attributions` | **2,461,210** | ~211 MB text |
| `analytics_entries` | **1,798,056** | ~329 MB text |
| `telemetry_events` | **918,374** | ~1,398 MB text (`payload_json`) |
| `session_logs` | **546,043** | ~1,746 MB text (`content + tool_args + tool_output`) |
| `session_usage_events` | **424,570** | — |
| `session_messages` | **385,508** | ~100 MB text |
| `sessions` | **9,246** | — |
| `entity_links` | **26,681** | — |
| `tasks` | **10,486** | — |
| `features` | **367** | — |

**Total identifiable text data: ~3.8 GB in five columns alone.** The remaining ~5.7 GB is B-tree index overhead for 184 indexes, row headers, and cross-duplication between `session_logs` and `session_messages`.

### Per-project concentration

`analytics_entries`: 1,765,449 rows for project `3df0ff70...` (the active skillmeat project) — all rows have `period='point'` and no retention/purge mechanism exists.

`telemetry_events`: 794,579 rows for the same project; `payload_json` averages ~1.5 KB per row.

---

## 2. Root Cause: analytics_entries Unbounded Growth

**File: `backend/db/sync_engine.py:5787–5990`**  
**Function: `_capture_analytics()`**

Every call to `sync_project()` with `capture_analytics=True` (the default, `backend/db/sync_engine.py:2938`) appends a **full snapshot** of project metrics with no upsert / dedup logic.

```
analytics_repo.insert_entry(...)  # line 5802 — pure INSERT, no ON CONFLICT
```

Estimated metrics per sync call for this project:
- ~10 project-level metrics (session_count, cost, tokens, duration, task_velocity, task_completion_pct, feature_progress, tool_call_count, tool_success_rate, file_churn)
- ~9 × 367 features = ~3,303 feature-level metrics

Total: ~**3,313 rows per sync**. Across ~533 syncs = 1,765,729 rows. No `DELETE FROM analytics_entries WHERE project_id = ? AND captured_at < NOW() - INTERVAL '?'` equivalent exists anywhere in the codebase (`grep` of all `*.py` files confirms zero purge logic for this table).

**Instrumentation gap:** `backend/observability/otel.py` has `record_ingestion()` (line 640) but no histogram or counter for `_capture_analytics` duration or row count. Add:
```python
# backend/observability/otel.py — after _ingestion_latency_hist initialization
_analytics_snapshot_duration_hist: Histogram  # ccdash_analytics_snapshot_duration_ms{project_id}
_analytics_entries_written_counter: Counter   # ccdash_analytics_entries_written_total{project_id}
```
Emit in `backend/db/sync_engine.py:5787` at entry of `_capture_analytics()`.

---

## 3. Root Cause: N+1 Session Log Queries on List Endpoint

**File: `backend/routers/api.py:628`**  
**Endpoint: `GET /api/sessions` → `list_sessions()`**

For every session in the page, the handler calls:
```python
session_logs = await session_transcript_service.list_session_logs(s, core_ports)
# line 628 — fetches up to 5000 rows per session
```

This is used solely to derive badges (`derive_session_badges()`, line 630) and extract command events / latest summary (lines 636–647) for the list view. With `SESSIONS_PAGE_SIZE = 50` (frontend, `services/queries/sessions.ts:17`) and average 59 logs/session:
- **1 page load = 50 DB queries + ~3,000 row fetches just for badge data**
- Badge data (models/agents/skills used) never changes after a session ends — it should be materialized in the `sessions` table or a summary column.

Additionally, subagent sessions trigger a second `list_session_logs()` call on the parent session (`api.py:660`), potentially doubling the cost.

**Instrumentation point:** Add a per-request timing span around the badge derivation loop at `backend/routers/api.py:624`:
```python
with otel.start_span("sessions.list.badge_derivation", {"session_count": len(sessions_data)}):
    # existing loop
```
Metric to emit: `ccdash_session_list_badge_ms` histogram with `page_size` label.

---

## 4. Root Cause: Row-by-Row INSERT Without `executemany`

### Telemetry Events
**File: `backend/db/sync_engine.py:1457–1486`**

```python
for event in events:          # line 1457
    await self.db.execute(    # line 1458
        insert_query, (...)
    )
await self.db.commit()        # line 1486
```

For a session with 100 tool calls, this is 100 separate `await self.db.execute()` round-trips inside a single transaction. The pattern repeats at `sync_engine.py:1529` (Postgres path).

### Session Usage Attributions
**File: `backend/db/repositories/usage_attribution.py:26–71`**

```python
for event in events:          # line 26
    await self.db.execute(...)
for attribution in attributions:  # line 53
    await self.db.execute(...)
await self.db.commit()        # line 72
```

With ~5.84 attributions per event and 424K events, this is a massive write amplification during sync. `aiosqlite` supports `executemany()`, which batches all the Python round-trips into a single C-level loop.

### Session Logs
**File: `backend/db/repositories/sessions.py:730–753`**

`INSERT OR IGNORE` in a Python loop. 546K rows, largest session has 1,984 log rows.

### Fix pattern for all three:
```python
# Replace loop pattern with executemany:
await self.db.executemany(insert_query, [tuple(e.values()) for e in events])
```

**Instrumentation:** Add `ccdash_sync_session_insert_batch_size` histogram at `sync_engine.py:1457` (value = `len(events)`).

---

## 5. Root Cause: SQLite Under-Configured

**File: `backend/db/connection.py:52–54`**

Current PRAGMAs set:
```python
await conn.execute("PRAGMA journal_mode=WAL")      # good
await conn.execute("PRAGMA foreign_keys=ON")        # good
await conn.execute(f"PRAGMA busy_timeout={...}")    # good
```

Missing high-impact PRAGMAs for a 9.5 GB database:
```python
await conn.execute("PRAGMA cache_size = -131072")     # 128 MB page cache (vs. current 8 MB)
await conn.execute("PRAGMA mmap_size = 4294967296")   # 4 GB mmap (let OS manage hot pages)
await conn.execute("PRAGMA synchronous = NORMAL")     # safe with WAL, 2× write throughput
await conn.execute("PRAGMA wal_autocheckpoint = 1000") # checkpoint before WAL grows too large
await conn.execute("PRAGMA temp_store = MEMORY")      # sorts/aggregates in RAM
```

Without `cache_size` tuning, every analytical query (planning summaries, forensics, system metrics) incurs disk I/O to page in the 9.5 GB file. The WAL at 60 MB means a checkpoint is overdue.

**Instrumentation:** Emit `PRAGMA page_cache_miss_count` at startup via:
```python
# backend/db/connection.py — after pragma setup
async with conn.execute("PRAGMA stats") as cur:
    row = await cur.fetchone()
    logger.info("SQLite page cache: %s", row)
```

---

## 6. Root Cause: Enterprise Container Data Ingestion Disabled by Default

### Chain of defaults

1. `backend/runtime/profiles.py:43–55`: `api` runtime profile has `capabilities.sync = False`.
2. `backend/runtime/container.py:237–242`: `_sync_engine_enabled()` returns `False` for enterprise api runtime.
3. `deploy/runtime/compose.yaml:worker-service`: `CCDASH_STARTUP_SYNC_ENABLED: "${CCDASH_WORKER_STARTUP_SYNC_ENABLED:-false}"` — defaults to `false`.
4. `backend/config.py:246`: `filesystem_source_of_truth = False` when enterprise profile + `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false` (default).

Result: In a default `docker compose --profile enterprise up`, the `api` service is read-only and the `worker` service never triggers a startup sync. A fresh Postgres database starts empty; the frontend sees zero sessions, features, and documents.

The fix requires either:
- `CCDASH_STARTUP_SYNC_ENABLED=true` in the worker compose service, **or**
- `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true` on the api service (enables sync engine on api)

Neither is documented as a required step in `docs/guides/containerized-deployment-quickstart.md`. The guide describes `python3 backend/scripts/container_project_onboarding.py` for path wiring but does not set these critical flags.

**The compose.yaml worker default is the direct root cause of the "live session data never appeared" failure.**

**Instrumentation gap:** The api health endpoint (`/api/health/ready`) reports `startup_sync` status, but the compose healthcheck does not validate it (`container.py:673`).

---

## 7. Polling Overhead (Frontend)

### Measured polling intervals

| Hook / Component | Interval | Endpoint hit |
|---|---|---|
| `useAlertsQuery` (`services/queries/alerts.ts:46`) | 30s | `/api/alerts` |
| `useNotificationsQuery` (`services/queries/notifications.ts:46`) | 30s | `/api/notifications` |
| `useHealthQuery` (`services/queries/health.ts:53`) | 30s | `/api/health/ready` |
| `useFeaturesQuery` (`services/queries/features.ts:85`) | **5s** (when SSE disabled) | `/api/features?view=cards` |
| `Dashboard.tsx:117` (`LIVE_AGENTS_POLL_MS = 10_000`) | 10s | `/api/agent/live/active-count` |
| `SystemMetricsChip.tsx:73` (`SYSTEM_METRICS_POLL_MS = 30_000`) | 30s | `/api/agent/system/active-count` |
| `PlanningAgentSessionBoard.tsx:880` | 15s tick (re-render only, no fetch) | — |

The 5-second `features` refetch (`services/queries/features.ts:85`) fires when `isFeatureLiveUpdatesEnabled()` returns `false` (the default when SSE is not explicitly enabled). On a project with 367 features, each `/api/features?view=cards` call returns a paginated response but is still a DB query. If multiple browser tabs are open, this multiplies.

**Instrumentation:** Add `ccdash_feature_surface_poll_interval_ms` gauge in `otel.py` emitted when `refetchInterval` is configured.

---

## 8. Heavy Endpoint Fan-Out Analysis

### `GET /api/agent/planning/session-board`

**File: `backend/application/services/agent_queries/planning_sessions.py:609`**

```python
sessions = await ports.storage.sessions().list_paginated(
    offset=0, limit=500, ...   # line 609–616 — hard-coded 500 sessions
)
```

Loads 500 sessions in a single call. If the project has fewer than 500 active sessions, this is bounded; but a full-project board load for a project with 9,246 sessions will still materialize 500 rows and then build Kanban cards per session.

### `GET /api/agent/system/active-count` (multi-project)

**File: `backend/application/services/agent_queries/system_metrics.py:199`**

Fan-out to all projects (5 in this repo) via `asyncio.gather` bounded by `Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY=10)`. With SQLite's single-writer-at-a-time model, this concurrency cap is effectively irrelevant — all reads still serialize on the same connection. The `@memoized_query` cache (TTL 10s for live count) mitigates repeated hits.

### `_capture_analytics()` Feature-Level N+1

**File: `backend/db/sync_engine.py:5876–5972`**

For each of 367 features:
- 1 × `task_repo.list_by_feature()` — line 5883
- 1 × `link_repo.get_links_for()` — line 5930
- N × `session_repo.get_by_id()` — line 5955 (per linked session)
- N × `session_repo.get_tool_usage()` — line 5964
- N × `session_repo.get_file_updates()` — line 5971

Assuming 10 sessions per feature: **367 × (1 + 1 + 10×3) = ~11,744 individual DB queries per sync cycle** just for the analytics capture phase. This runs synchronously in the sync loop.

---

## 9. Content Search Without FTS Index

**File: `backend/db/repositories/session_messages.py:98`**

```python
term_clauses = ["LOWER(sm.content) LIKE ?" for _ in search_terms]
```

`LOWER(sm.content) LIKE ?` on 385,508 rows (100 MB of content text) is a full table scan. SQLite does not use the `(session_id, message_index)` index for this query pattern. A `CREATE VIRTUAL TABLE session_messages_fts USING fts5(content, session_id)` with triggers would reduce search from O(n) to O(log n).

---

## 10. Duplicate Data: `session_logs` vs `session_messages`

Both tables store the same transcript data (`session_logs`: 546K rows, 1.75 GB; `session_messages`: 385K rows, 100 MB). The `session_messages` table is the canonical store; `session_logs` is the legacy fallback. The `SessionTranscriptService.list_session_logs()` (`backend/application/services/sessions.py:99–117`) checks canonical rows first and falls back to `session_logs` only when empty. However, `session_logs` rows are never purged after canonical rows are written, resulting in ~1.7 GB of redundant storage.

**File: `backend/application/services/sessions.py:107–116`**

```python
if not canonical_rows:           # only uses session_logs as fallback
    raw_logs = await ...get_logs(...)
```

---

## 11. Missing Instrumentation Summary

| What to instrument | Where | Metric name |
|---|---|---|
| `_capture_analytics` duration + row count | `sync_engine.py:5787` | `ccdash_analytics_snapshot_ms`, `ccdash_analytics_rows_written` |
| Session list badge derivation latency | `api.py:624` | `ccdash_session_list_badge_derivation_ms` |
| Sync session INSERT batch size | `sync_engine.py:1457` | `ccdash_sync_session_insert_batch_size` |
| SQLite page cache stats | `connection.py:54` | `ccdash_sqlite_cache_miss_count` |
| Analytics entries table row count | `sync_engine.py` post-analytics | `ccdash_analytics_entries_total{project_id}` |
| Startup sync completion + duration | `container.py` lifespan | `ccdash_startup_sync_duration_ms`, `ccdash_startup_sync_sessions_synced` |

---

## Quick-Win vs Deep-Refactor Prioritization

| Fix | Complexity | Impact |
|-----|-----------|--------|
| Set `CCDASH_STARTUP_SYNC_ENABLED=true` default in compose worker | **S** | Unblocks enterprise data ingestion |
| Add `PRAGMA cache_size=-131072; mmap_size=4294967296; synchronous=NORMAL` to `connection.py` | **S** | ~5-10× query speed on 9.5 GB DB |
| Switch telemetry/usage INSERT loops to `executemany` | **S** | 10–50× faster per-session sync writes |
| Add analytics_entries retention (DELETE WHERE captured_at < now - 90d) | **S** | Stops unbounded DB growth |
| Cache badge metadata in `sessions` table columns (`models_used_json`, `agents_used_json`, `skills_used_json`) | **M** | Eliminates N+1 on session list endpoint |
| Add TTL/dedup to analytics snapshot (UPSERT with `ON CONFLICT(project_id, metric_type, date(captured_at))`) | **M** | Reduces analytics_entries from 1.77M → ~30K rows |
| Switch `_capture_analytics` per-feature queries to batch (CTEs / single JOINs) | **M** | Eliminates ~11K queries per sync cycle |
| Add FTS5 virtual table for `session_messages.content` | **L** | Makes search O(log n) vs O(n) |
| Purge orphaned `session_logs` rows where canonical `session_messages` exist | **M** | Reclaim ~1.7 GB storage |

---

## Evidence Checklist

- [x] DB size: `du -sh data/ccdash_cache.db` = 9.5 GB (measured)
- [x] Row counts: `SELECT COUNT(*) FROM ...` for 15 tables (measured)
- [x] analytics_entries: 1,765,449 rows for single project, all `period='point'` (measured)
- [x] telemetry_events `payload_json`: SUM(length) = 1,398 MB (measured)
- [x] session_logs text payload: SUM(length) = 1,746 MB (measured)
- [x] `cache_size = 2000` = 8 MB (confirmed via `PRAGMA cache_size`)
- [x] Enterprise worker `CCDASH_STARTUP_SYNC_ENABLED` defaults to `false` (compose.yaml confirmed)
- [x] `api` runtime `capabilities.sync = False` (profiles.py confirmed)
- [x] N+1 in `list_sessions`: `list_session_logs()` at `api.py:628` (code confirmed)
- [x] Row-by-row INSERT at `sync_engine.py:1457`, `usage_attribution.py:26,53` (code confirmed)
- [x] No analytics retention: zero `DELETE FROM analytics_entries` in codebase (grep confirmed)
- [x] Feature-level N+1 in `_capture_analytics`: 367 features × ~32 queries (code confirmed)
- [x] `features` poll at 5s (`services/queries/features.ts:85`) when SSE disabled (code confirmed)
