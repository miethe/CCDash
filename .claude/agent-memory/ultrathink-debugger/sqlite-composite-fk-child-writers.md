---
name: sqlite-composite-fk-child-writers
description: After v31, every session child writer must pass project_id matching the parent session, or the composite FK fails under foreign_keys=ON; NULL project_id silently creates orphans
metadata:
  type: feedback
---

The v31 migration gave `sessions` a composite PK `(project_id, id)` and every child table a composite FK `(project_id, session_id) -> sessions(project_id, id) ON DELETE CASCADE`. `backend/db/connection.py` always sets `PRAGMA foreign_keys=ON`. Consequences for any session child writer (`session_messages`, `session_logs`, `session_tool_usage`, `session_file_updates`, intelligence-fact tables):

- A child INSERT with a **non-NULL** `project_id` that does not match a `sessions(project_id, id)` row raises `FOREIGN KEY constraint failed`.
- A child INSERT with `project_id=NULL` is **silently accepted** (SQLite does not enforce a composite FK when any FK column is NULL) — this creates *orphan* rows, not an error. This is exactly how `replace_session_messages` produced 304 NULL-project orphans before the fix.
- `replace_session_messages` (SQLite + Postgres) had no `project_id` param at all → always wrote NULL. Fixed to accept and persist `project_id`, scope the DELETE to `(project_id OR NULL OR '')`, and dedupe by `message_index` (last wins) to mirror Postgres `ON CONFLICT (session_id, message_index) DO UPDATE`.

**Why:** the `idx_session_messages_session_message(session_id, message_index)` UNIQUE index is NOT composite with project_id, so a single DELETE-then-INSERT payload containing duplicate `messageIndex` raises `UNIQUE constraint failed` mid-transaction. The projection (`project_session_messages`) uses `enumerate`, so duplicates only arise across multiple session payloads / re-projection; dedupe in the repo makes the replace idempotent.

**How to apply:** When adding or debugging a session child writer, (1) thread `project_id` through and pass the SAME id the parent session was upserted under; (2) never rely on the FK to catch a NULL project_id — it won't; (3) test under `PRAGMA foreign_keys=ON` against a DB built by `backend.db.sqlite_migrations.run_migrations` (raw aiosqlite connections default foreign_keys OFF, so tests can pass while runtime fails). See [[db-connection-module-level-path]].
