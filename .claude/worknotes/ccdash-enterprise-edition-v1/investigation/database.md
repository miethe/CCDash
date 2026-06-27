# Database Investigation: CCDash Enterprise Edition

**Domain**: Database schema, migrations, indexes, repositories; SQLite-vs-Postgres readiness; query patterns and N+1.
**Date**: 2026-05-30
**Investigator**: Subagent (Sonnet 4.6)

---

## Executive Summary

The 10 GB SQLite cache (`data/ccdash_cache.db`) is dominated by three tables that store **full message/tool content as uncompressed TEXT**: `session_logs` (2.1 GB), `telemetry_events` (1.6 GB), and `session_messages` (1.2 GB). The `analytics_entries` table (~466 MB) grows unbounded — there is no pruning code anywhere. Indexes are mostly adequate but a critical composite index (`idx_sessions_project_status_updated`) is absent from the live DB because it was placed only in the `_TABLES` DDL block (which only runs on a version bump) and never backfilled via `_ensure_index`. The Postgres migration path is structurally complete but contains a data-correctness risk: `idx_links_upsert` (the UNIQUE constraint that `entity_links` ON CONFLICT depends on) is added as a late migration step rather than in the initial DDL. The analytics write path has an N+1 inside `_capture_analytics`: per-feature `task_repo.list_by_feature` + `link_repo.get_links_for` + per-session `session_repo.get_by_id` calls, each with an individual commit.

---

## 1. Table Inventory and Row / Byte Sizes

Measured from `dbstat` virtual table (total DB on disk: ~8.5 GB logical payload, ~10 GB on-disk with page overhead).

### High-Volume Tables (Data)

| Table | Row Count | Payload (MB) | Notes |
|-------|-----------|-------------|-------|
| `session_logs` | 546,043 | **2,084 MB** | `content`, `tool_args`, `tool_output` full TEXT |
| `telemetry_events` | 918,374 | **1,648 MB** | `payload_json` avg 1.6 KB, max 2.3 MB |
| `session_messages` | 385,508 | **1,232 MB** | `content` avg 272 bytes; duplicates session_logs data |
| `analytics_entries` | 1,798,056 | **466 MB** | All `period='point'`; no pruning; ~10K rows/hour during active sync |
| `session_usage_attributions` | (large) | **385 MB** | Including UNIQUE index: 242 MB |
| `sessions` | 9,246 | **199 MB** | Wide row: 52+ columns; JSON blobs |
| `analytics_entity_links` | 3,580,439 | **166 MB** | ~2 links per analytics entry; also unpruned |

### Index Overhead

Total index storage: ~1.9 GB, versus ~6.6 GB for tables. The `analytics_entries` indexes alone (`idx_analytics_lookup`, `idx_analytics_period`, `idx_analytics_entity`) consume **~470 MB combined** — matching the table itself.

---

## 2. Root Causes of the 10 GB Size

### 2a. `session_logs` — Full Tool Output Stored as TEXT (2.1 GB)

**File**: `backend/db/sqlite_migrations.py:178-183`

`session_logs.tool_output` and `session_logs.tool_args` store raw tool call outputs as TEXT. Average `tool_args` is 717 bytes; average `tool_output` is 2,764 bytes. Over 546K rows this totals ~640 MB for `tool_output` alone. No TTL, no truncation.

`session_messages.content` is a parallel storage of the same data (avg 272 bytes × 385K rows = 100 MB). This table was added as a "canonical transcript seam" but stores the same conversation content already in `session_logs.content`. **Two full copies of transcript data exist in the DB.**

**File**: `backend/db/sqlite_migrations.py:192-225` — `session_messages` DDL.

### 2b. `telemetry_events` — Per-Log-Entry Fact Table Storing Full JSON Payload (1.6 GB)

**File**: `backend/db/sqlite_migrations.py:500-542`

918K rows with avg `payload_json` of 1,597 bytes (max 2.3 MB). The `event_type` breakdown shows `log.tool` (254K), `artifact.linked` (187K), `log.message` (159K), `file.update` (114K), `log.system` (107K). These are written once per JSONL log entry during ingestion and never deleted. Over 151 days this is ~6,000 events/day for a single project.

### 2c. `analytics_entries` — Unbounded Point-in-Time Metrics (466 MB)

**File**: `backend/db/repositories/analytics.py` — no `DELETE` or prune method exists at all.

**File**: `backend/db/sync_engine.py:2691-2711` — `capture_analytics_snapshot` called on every full sync.

At ~2,400–2,600 rows per snapshot (10 project-level + ~3 metrics per feature × 367 features = ~1,101 feature-scoped entries + their entity links), running multiple times per hour, the table accumulates 1.8M rows over 103 days. Each row generates 2 `analytics_entity_links` rows, explaining the 3.6M rows in that join table.

Rate: **~250 rows/minute** during active sessions (observed 10,246 rows in one hour of active syncing).

### 2d. `sessions.session_forensics_json` / JSON Blob Columns (175 MB across 9K rows)

**File**: `backend/db/sqlite_migrations.py:152-153`

`session_forensics_json` averages 19 KB/row = 175 MB total across 9,246 sessions. `timeline_json` adds 3 MB; `impact_history_json` 6 MB. These are computed aggregations stored redundantly in the sessions row rather than being computed on read.

---

## 3. Index Analysis

### 3a. CONFIRMED MISSING: `idx_sessions_project_status_updated`

**Severity**: HIGH

**File**: `backend/db/sqlite_migrations.py:161-162` (DDL definition in `_TABLES` block)

This index is declared in the `_TABLES` DDL string:
```sql
CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated
    ON sessions(project_id, status, updated_at);
```

But `_TABLES` is only executed when `current_version < SCHEMA_VERSION` (`sqlite_migrations.py:1362-1367`). It was **never added as a `_ensure_index` backfill call** in the migrations function. The live DB (schema version 28) does not have this index.

**Confirmed absent** from `sqlite_master`:
```
idx_sessions_project_status_updated  -- NOT FOUND
```

**Impact**: The `count_active` query (`sessions.py:434-457`) and `list_active` (`sessions.py:459-536`) use:
```sql
WHERE project_id = ? AND status = ? AND updated_at >= ?
```
Without this index, SQLite falls back to `idx_sessions_updated_at (project_id, updated_at)` — which partially covers the query but cannot filter on `status` in the index, causing a residual `status` filter on all matching rows. With 9,246 sessions this is tolerable now but will degrade at scale.

### 3b. `sessions.source_file` — Missing Index (Full Table Scan on Every Sync)

**Severity**: HIGH

**File**: `backend/db/repositories/sessions.py:161-167` — `list_by_source(source_file)` does `WHERE source_file = ?`.

**File**: `backend/db/sync_engine.py:4121-4130` — called on every file-watch event: `rows = await self.session_repo.list_by_source(file_path)`.

There is no index on `sessions.source_file`. EXPLAIN confirms `SCAN sessions` (full table scan). With 9,246 rows currently this adds ~1ms per call; at 100K sessions it would be ~100ms per file-watch event.

The existing `ix_sessions_source_ref` index covers `(project_id, source_ref)` — `source_ref` is a different column added via a separate migration (not in the original DDL), and is unrelated to `source_file`.

### 3c. `analytics_entries` — HAVING Clause Anti-Pattern (Missing Index)

**Severity**: MEDIUM

**File**: `backend/db/repositories/analytics.py:103-121`

```sql
SELECT metric_type, value FROM analytics_entries
WHERE project_id = ? AND metric_type IN (...)
  AND period = 'point'
GROUP BY metric_type
HAVING captured_at = MAX(captured_at)
```

The `HAVING captured_at = MAX(captured_at)` clause runs as a post-aggregation filter. This forces SQLite to read all matching rows and group them before filtering. With 1.8M rows and `idx_analytics_lookup` on `(project_id, metric_type, captured_at)`, the index is used but the HAVING post-filter prevents an index-only early-exit. The correct pattern is a subquery or window function.

### 3d. `telemetry_events` — `LIKE 'log.%'` Pattern (Partial Index Miss)

**Severity**: MEDIUM

**File**: `backend/db/repositories/analytics.py:287-295`

```sql
WHERE project_id = ? AND event_type LIKE 'log.%'
```

`idx_telemetry_event_type` is on `(project_id, event_type, occurred_at)`. A `LIKE 'log.%'` prefix scan works with B-tree indexes in SQLite when the pattern doesn't start with `%`, but this indexes into a cardinality-explosion range (5 distinct `log.*` types × 918K rows). With `idx_telemetry_event_type` at 70 MB, this is a large index range scan.

### 3e. Complete Index Inventory

Indexes present and verified correct:

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_sessions_project` | sessions | `(project_id, started_at DESC)` | List paginated |
| `idx_sessions_root` | sessions | `(project_id, root_session_id, started_at DESC)` | Thread queries |
| `idx_sessions_family` | sessions | `(project_id, conversation_family_id, started_at DESC)` | Family queries |
| `idx_sessions_updated_at` | sessions | `(project_id, updated_at)` | Active count (partial coverage) |
| `idx_logs_session` | session_logs | `(session_id, log_index)` | Log fetch |
| `idx_logs_source_log_unique` | session_logs | `(session_id, source_log_id) WHERE != ''` | Dedup |
| `idx_session_messages_family` | session_messages | `(conversation_family_id, root_session_id, message_index)` | Thread reads |
| `idx_analytics_lookup` | analytics_entries | `(project_id, metric_type, captured_at)` | Trend queries |
| `idx_links_upsert` | entity_links | UNIQUE `(source_type, source_id, target_type, target_id, link_type)` | ON CONFLICT |
| `idx_telemetry_source_key` | telemetry_events | UNIQUE `(project_id, source_key)` | Dedup |
| `idx_features_status_updated` | features | `(project_id, status, updated_at)` | List query |

**Notable missing (besides `idx_sessions_project_status_updated`)**:
- `sessions(source_file)` — needed for sync file-watch path
- `analytics_entries` — no partial index for `period = 'point'` (most common query predicate)
- `session_logs(type)` — filtering by log type within a session has no index (only `tool_name` is indexed)

---

## 4. N+1 Query Patterns

### 4a. `_capture_analytics` — Triple N+1 per Feature (CRITICAL)

**Severity**: CRITICAL
**File**: `backend/db/sync_engine.py:5874-5960`

The analytics capture iterates over all 367 features and for each:
1. `await self.task_repo.list_by_feature(feature_id, None)` — 1 query per feature = 367 queries
2. `await self.link_repo.get_links_for("feature", feature_id, "related")` — 1 query per feature = 367 queries
3. For each linked session: `await self.session_repo.get_by_id(session_id)` — N queries per feature

This produces **367 × (2 + avg_linked_sessions)** DB round-trips per analytics snapshot. With ~25K entity_links for sessions, each feature has an average of ~30–40 linked sessions, yielding potentially **~12,000–15,000 individual DB queries per snapshot**.

Additionally, `entity_graph.py:15-41` — `link_repo.upsert()` calls `await self.db.commit()` on line 40 after every single link insert. During `_rebuild_entity_links` (called from `sync_engine.py:4614+`) which inserts thousands of links, this produces **N commits** (one per link), making WAL writes unbounded.

### 4b. `_rebuild_entity_links` — Per-Link Commit (HIGH)

**Severity**: HIGH
**File**: `backend/db/repositories/entity_graph.py:40`

```python
async def upsert(self, link_data: dict) -> int:
    # ...
    await self.db.commit()  # line 40 — one commit per link
    return cur.lastrowid or 0
```

`_rebuild_entity_links` in `sync_engine.py` calls `link_repo.upsert()` in a loop. With 25K `entity_links` rows, this is 25,000 individual commits during a full rebuild.

### 4c. Analytics Backfill — Per-Session `get_by_id` (HIGH)

**File**: `backend/db/sync_engine.py:2058-2095` (various `_backfill_*` methods)

Multiple backfill loops iterate sessions page by page (`list_paginated` in pages of 250) then fetch detail tables per session:
```python
for session in sessions:
    logs = await self.session_repo.get_logs(session_id)        # SELECT per session
    tools = await self.session_repo.get_tool_usage(session_id) # SELECT per session
    files = await self.session_repo.get_file_updates(session_id) # SELECT per session
    artifacts = await self.session_repo.get_artifacts(session_id) # SELECT per session
```

With 9,246 sessions this is up to **37,000 individual SELECT queries** per full backfill run.

---

## 5. SQLite-vs-Postgres Compatibility Issues

### 5a. `entity_links` UNIQUE Constraint — Late Migration Step (HIGH)

**Severity**: HIGH
**File**: `backend/db/postgres_migrations.py:1491-1498`

`idx_links_upsert` (the UNIQUE constraint enabling `ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE`) is created in a separate `_ensure_entity_link_uniqueness` migration step rather than in the initial `_TABLES` DDL block. On a fresh Postgres installation:

1. `_TABLES` executes — entity_links created **without** the UNIQUE constraint.
2. Repositories immediately start calling `upsert()` using `ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE`.
3. Without the UNIQUE constraint, `ON CONFLICT` silently inserts duplicates.

`_ensure_entity_link_uniqueness` runs as step 3 in `run_migrations` — but it uses `CREATE UNIQUE INDEX IF NOT EXISTS` which **will fail** if duplicate rows already exist. This is a data integrity trap on first-run Postgres deployments.

### 5b. String-Stored Timestamps in Postgres (MEDIUM)

**File**: `backend/db/postgres_migrations.py:82-148`

All timestamp columns on `sessions`, `session_logs`, `session_messages`, etc. are declared as `TEXT` in both SQLite and Postgres schemas (except `session_relationships.created_at` which correctly uses `TIMESTAMP WITH TIME ZONE`). On Postgres, text timestamps lose range-query optimization (no operator class for text `>=`/`<=` on ISO-8601 strings). The index `idx_sessions_project ON sessions(project_id, started_at DESC)` with `started_at TEXT` will use lexicographic sort — correct only if timestamps are consistently formatted as ISO-8601, which they appear to be, but is fragile.

### 5c. `asyncpg.Pool` Passed as `asyncpg.Connection` to Repositories (MEDIUM)

**File**: `backend/db/connection.py:45` — `_connection = await asyncpg.create_pool(config.DATABASE_URL)`.

**File**: `backend/db/factory.py:47-51` — repositories receive `db` which is actually an `asyncpg.Pool`.

**File**: `backend/db/repositories/postgres/sessions.py:15` — constructor types it as `asyncpg.Connection`.

`asyncpg.Pool` implements `execute`, `fetch`, `fetchrow`, `fetchval` directly (proxying through `acquire()`), so single-query calls work. However, `await self.db.execute(...)` in a Pool context acquires and releases a connection per call — meaning multi-statement "transactions" in `upsert_logs` that call `DELETE` then N `INSERT` without explicit `async with pool.acquire() as conn: async with conn.transaction():` are **not atomic on Postgres**. Partial failures (after DELETE, before all INSERTs complete) would produce data loss.

The `postgres_transaction` helper in `_transactions.py` correctly handles Pool vs Connection, but `upsert_logs`, `upsert_file_updates`, `upsert_artifacts`, `upsert_tool_usage` in the Postgres sessions repo do NOT use it — they issue `DELETE` + N INSERTs as separate non-transactional operations.

### 5d. SQLite `LIKE` on JSON Arrays for Platform Version Filter (MEDIUM)

**File**: `backend/db/repositories/sessions.py:222-226`

```python
where_clauses.append("(platform_version = ? OR platform_versions_json LIKE ?)")
params.append(f'%"{version}"%')
```

On Postgres this translates to text `LIKE` on a JSON-typed column. The Postgres repo (`postgres/sessions.py`) must use `platform_versions_json::jsonb @> $1::jsonb` or `jsonb_array_elements_text`. Verify that the Postgres implementation avoids the `LIKE` hack — the actual repo uses the same pattern.

### 5e. `PRAGMA`-Only WAL Mode (MEDIUM)

**File**: `backend/db/connection.py:52-54`

```python
await conn.execute("PRAGMA journal_mode=WAL")
await conn.execute("PRAGMA foreign_keys=ON")
await conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
```

`PRAGMA cache_size` is not set — defaulting to 2000 pages (~8 MB), far too small for a 10 GB database. Random I/O on uncached pages will be severe. Recommended: at least 32768 pages (128 MB).

`PRAGMA synchronous=NORMAL` is also not set — defaults to `FULL` which syncs on every WAL checkpoint, adding latency. For a cache DB (reconstructable from filesystem), `SYNCHRONOUS=NORMAL` or `OFF` is safe.

---

## 6. Migration Governance and Schema Drift

### 6a. `source_ref` Column Present in DB but Not in SQLite Migrations

**Confirmed**: `sessions` table has `source_ref` column (`ix_sessions_source_ref` index) but this column does not appear in `backend/db/sqlite_migrations.py` DDL. It was added via an `_ensure_column` call somewhere (possibly a now-removed migration step or an enterprise-only path) but its origin cannot be traced in the current migration code.

**File**: Live DB via `PRAGMA table_info(sessions)` — column 64 is `source_ref TEXT`.

This indicates schema drift between the migration code and the live DB.

### 6b. Schema Version Mismatch Between SQLite (27) and Postgres (28)

**File**: `backend/db/sqlite_migrations.py:16` — `SCHEMA_VERSION = 27`
**File**: `backend/db/postgres_migrations.py:11` — `SCHEMA_VERSION = 28`

The live DB reports version 28, which means the SQLite DB has been migrated by the Postgres migration runner at some point (or the SQLite version was bumped independently). This divergence will cause confusion in `run_migrations` — the SQLite path will always think the DB is already at version 27 and skip `_TABLES` execution.

---

## 7. Candidate Index List (Missing Indexes to Add)

These should all be added as `_ensure_index` calls in the migration runner so they are backfilled on existing databases:

```sql
-- 1. CRITICAL: Restore missing composite for count_active / list_active
CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated
    ON sessions(project_id, status, updated_at);

-- 2. HIGH: source_file for file-watch sync path (list_by_source + delete_by_source)
CREATE INDEX IF NOT EXISTS idx_sessions_source_file
    ON sessions(source_file);
CREATE INDEX IF NOT EXISTS idx_sessions_project_source_file
    ON sessions(project_id, source_file);

-- 3. MEDIUM: analytics_entries partial index for 'point' period (dominant query)
CREATE INDEX IF NOT EXISTS idx_analytics_entries_point
    ON analytics_entries(project_id, metric_type, captured_at DESC)
    WHERE period = 'point';

-- 4. MEDIUM: session_logs.type for log-type filtering within session
CREATE INDEX IF NOT EXISTS idx_logs_type
    ON session_logs(session_id, type);

-- 5. MEDIUM: telemetry_events partial index for lifecycle events (most common subquery)
CREATE INDEX IF NOT EXISTS idx_telemetry_lifecycle
    ON telemetry_events(project_id, occurred_at DESC)
    WHERE event_type = 'session.lifecycle';

-- 6. LOW: session_file_updates.root_session_id for thread-level churn queries
CREATE INDEX IF NOT EXISTS idx_file_updates_root_session
    ON session_file_updates(root_session_id);
```

---

## 8. Storage-Reduction Recommendations

### Priority 1: Analytics Retention Policy (IMMEDIATE — removes ~1 GB/year)

Add a rolling retention window to `analytics_entries` and `analytics_entity_links`. Recommendation: keep the last 90 days of `period='point'` entries and delete older rows. Add to `_capture_analytics`:

```sql
DELETE FROM analytics_entries 
WHERE project_id = $1 AND period = 'point'
  AND captured_at < NOW() - INTERVAL '90 days';
```

Alternatively, introduce a `period='daily'` aggregation and only retain daily rollups beyond 7 days. This would reduce the table from 1.8M rows to ~90,000 rows (50× reduction).

### Priority 2: Eliminate `session_messages` Duplication (removes ~1.2 GB)

`session_messages` is described as a "canonical transcript seam for future enterprise-grade session intelligence" (`sqlite_migrations.py:192`) but stores the same content as `session_logs` row-for-row (385K messages vs 546K logs). Until the intelligence layer actually uses `session_messages` exclusively, this table duplicates content storage. Options:

a. Drop `content` from `session_messages` and join to `session_logs` on read (saves ~100 MB).
b. Stop populating `session_logs` once `session_messages` is the canonical store (saves ~2 GB but requires confirming all consumers have migrated).
c. Store `content` only as a content-addressed external reference (S3/filesystem path) for sessions older than 30 days.

### Priority 3: `telemetry_events.payload_json` Compression or Offload (removes ~1.4 GB)

The `payload_json` column averages 1.6 KB and contains full tool call payloads. Options:

a. Apply zlib compression on write, decompress on read (SQLite has no native compression, but Python-side compression before storage). 10:1 compression ratio would reduce this to ~140 MB.
b. For events older than 30 days, archive `payload_json` to S3/filesystem and store only a reference.
c. On Postgres, use `BYTEA` with pg_compression or `jsonb` with toast compression (automatic).

### Priority 4: `session_logs.tool_output` Truncation (removes ~350 MB)

Tool outputs are stored verbatim — many are multi-MB file reads. Truncate `tool_output` to 8 KB on write (the existing `content` truncation at 5000 chars in `parsers/documents.py:958` should be applied here too). File read outputs beyond 8 KB carry no analytical value in the DB cache.

### Priority 5: `sessions.session_forensics_json` as Computed Column (removes ~175 MB)

This is a computed aggregate JSON blob stored in the sessions row. Recompute on read or cache separately with a TTL rather than persisting in the row.

---

## 9. Enterprise/Postgres Readiness Gaps

| Gap | Severity | Status |
|-----|----------|--------|
| `idx_sessions_project_status_updated` absent from live SQLite DB | HIGH | BROKEN |
| `idx_sessions_source_file` missing | HIGH | MISSING |
| `entity_links` UNIQUE constraint added post-initial DDL on Postgres | HIGH | UNSAFE |
| Postgres upsert_logs/upsert_file_updates not wrapped in transaction | HIGH | BROKEN |
| String timestamps (TEXT) on Postgres — no range index optimization | MEDIUM | PARTIAL |
| `asyncpg.Pool` typed as `asyncpg.Connection` in repos | MEDIUM | WORKS but fragile |
| `analytics_entries` has no retention/pruning — unbounded growth | CRITICAL | MISSING |
| `PRAGMA cache_size` not set — 8 MB page cache for 10 GB DB | HIGH | MISSING |
| `PRAGMA synchronous` not set to NORMAL/OFF for cache DB | MEDIUM | MISSING |
| Session data duplicated: `session_logs` + `session_messages` | HIGH | WASTE |
| Analytics N+1: 3 queries × 367 features × N sessions per snapshot | CRITICAL | BROKEN |
| Per-link commit in `entity_graph.upsert()` (25K commits per rebuild) | HIGH | PERF |

---

## 10. Key File:Line Evidence Summary

| Finding | File:Line |
|---------|-----------|
| `_TABLES` only runs on version bump | `backend/db/sqlite_migrations.py:1362-1367` |
| `idx_sessions_project_status_updated` in `_TABLES` only | `backend/db/sqlite_migrations.py:161-162` |
| `sessions.source_file` — no index | `backend/db/repositories/sessions.py:161-167` |
| `link_repo.upsert()` — commit per link | `backend/db/repositories/entity_graph.py:40` |
| Analytics N+1 — per-feature task list + link list | `backend/db/sync_engine.py:5876-5960` |
| Analytics N+1 — per-session `get_by_id` | `backend/db/sync_engine.py:5954-5958` |
| `analytics_entries` — no delete/prune | `backend/db/repositories/analytics.py` (entire file) |
| `entity_links` UNIQUE late migration | `backend/db/postgres_migrations.py:1491-1498` |
| Postgres repos receive `asyncpg.Pool` typed as `Connection` | `backend/db/factory.py:47-51`, `backend/db/connection.py:45` |
| Postgres `upsert_logs` no transaction | `backend/db/repositories/postgres/sessions.py:88+` |
| `PRAGMA cache_size` not set | `backend/db/connection.py:52-57` |
| SQLite schema version 27, Postgres 28 | `backend/db/sqlite_migrations.py:16`, `backend/db/postgres_migrations.py:11` |
| `session_messages` duplicates `session_logs` content | `backend/db/sqlite_migrations.py:192-225` |
| `telemetry_events.payload_json` avg 1.6 KB unbounded | `backend/db/sqlite_migrations.py:500-542` |
| `analytics_entries` 1.8M rows, 10K per hour | Live DB measurement via `dbstat` |
| `session_logs` 2.1 GB dominant storage | Live DB measurement via `dbstat` |
