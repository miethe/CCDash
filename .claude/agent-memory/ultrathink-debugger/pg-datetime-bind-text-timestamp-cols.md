---
name: pg-datetime-bind-text-timestamp-cols
description: CCDash timestamp columns are TEXT/ISO-8601 in BOTH backends; asyncpg refuses to bind a Python datetime to a $1 text column, while SQLite's sibling computes cutoffs in-SQL — a recurring PG-only DataError class the SQLite path masks
metadata:
  type: feedback
---

CCDash stores timestamps as **TEXT (ISO-8601)** columns in both SQLite and Postgres DDL (e.g. `analytics_entries.captured_at`, `telemetry_events.occurred_at` are `TEXT NOT NULL` in `postgres_migrations.py` AND `sqlite_migrations.py`; conflict indexes like `left(captured_at, 10)` prove the column is text, not timestamptz). Writers store `datetime.now(timezone.utc).isoformat()`.

The PG-only failure class: a repo method that computes a cutoff/bound as a **Python `datetime`** and binds it positionally (`WHERE captured_at < $1`, param = a `datetime`) raises asyncpg `DataError: invalid input for query argument $1: datetime.datetime(...) (expected str, got datetime)`. asyncpg will NOT coerce datetime→text for a text column.

**Why SQLite masks it:** the SQLite siblings do NOT bind a Python datetime — they compute the cutoff **inside SQL** via `datetime('now', ? || ' days')` against the text column (text-to-text compare), OR rely on sqlite3's default datetime adapter that serializes to an ISO string. Either way no strict type check fires. So a SQLite-green test suite can pass while the PG writeback/enrichment path throws.

**Two variants of the same bug class** (both PG-only, both masked by SQLite):
- *Client-side* — asyncpg `DataError: ... expected str, got datetime`: an `execute`/`fetch` binds a Python `datetime` directly to a `$N` for a TEXT column.
- *Server-side* — `UndefinedFunctionError: operator does not exist: text < timestamp with time zone`: the SQL itself compares a TEXT timestamp column to a **timestamptz expression** (`occurred_at < NOW() - ($n || ' days')::interval`). No Python datetime is bound — `NOW()`/`CURRENT_TIMESTAMP` arithmetic yields timestamptz and PG won't implicitly cast the TEXT column.

**How to apply:** Grep the writeback/enrichment path for BOTH patterns: (1) `timedelta` / bare `datetime.now(` not immediately `.isoformat()`'d, and (2) `NOW()` / `CURRENT_TIMESTAMP` / `::interval` compared against a column. Fix uniformly by computing an ISO-string cutoff in Python (`(datetime.now(timezone.utc) - timedelta(days=n)).isoformat()`) and binding it for a **text-to-text** compare — mirrors the SQLite sibling (which uses `datetime('now', ? || ' days')`, also text) and tolerates empty/odd values. Do NOT cast the column `::timestamptz` for prune-style deletes: rows with `''` would raise `invalid input syntax for type timestamp`. (Casting both sides `::timestamptz` is fine where the column is guaranteed parseable — see `telemetry_queue.py`.) Concrete instances (2026-06-27, all in the `_capture_analytics` sync-enrichment step right after the link-rebuild dispatch log): client-side `backend/db/repositories/postgres/analytics.py` `prune_entries_older_than_days` + `prune_telemetry_older_than_days` (bound `cutoff` datetime to `$1`); server-side `backend/db/sync_engine.py:_prune_telemetry_events` PG branch (`occurred_at < NOW() - interval`). The scheduled retention job (`backend/adapters/jobs/runtime.py`) delegates to the fixed repo methods — no separate fix needed. Related: [[sqlite-composite-fk-child-writers]], [[db-connection-module-level-path]].
