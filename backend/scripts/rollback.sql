-- rollback.sql — Revert ADR-008 workspace-scoped auth (v29 schema additions)
--
-- IMPORTANT — SQLite limitation:
--   SQLite prior to 3.35.0 does NOT support DROP COLUMN.
--   Even with 3.35+, dropping a column requires that the column is not:
--     • referenced by a foreign key constraint
--     • a PRIMARY KEY or part of a UNIQUE constraint
--     • used by an index (the index must be dropped first)
--   The ALTER TABLE … DROP COLUMN statements below are therefore ADVISORY for
--   SQLite deployments.  On older SQLite (< 3.35.0) you must rebuild the
--   affected tables by:
--     1. CREATE TABLE <name>_new AS SELECT <cols-without-workspace_id> FROM <name>;
--     2. DROP TABLE <name>;
--     3. ALTER TABLE <name>_new RENAME TO <name>;
--
-- For PostgreSQL deployments ALTER TABLE … DROP COLUMN is fully supported.
--
-- Execution order matters: drop dependent tables (workspace_tokens, which
-- references workspaces via workspace_id) before the parent table (workspaces).

-- Step 1: Drop dependent indexes on workspace_tokens (required before table drop).
DROP INDEX IF EXISTS ix_workspace_tokens_hash;
DROP INDEX IF EXISTS ix_workspace_tokens_workspace;

-- Step 2: Drop workspace_tokens table.
DROP TABLE IF EXISTS workspace_tokens;

-- Step 3: Drop workspaces table.
DROP TABLE IF EXISTS workspaces;

-- Step 4: Drop workspace_id columns from scoped tables.
--   ADVISORY on SQLite < 3.35.0 — see header note above.
ALTER TABLE sessions        DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE documents       DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE tasks           DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE features        DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE entity_links    DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE progress_files  DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE ingest_cursors  DROP COLUMN IF EXISTS workspace_id;

-- Step 5: Remove v29 schema_version record.
--   This allows the migration runner to re-apply v29 if needed.
DELETE FROM schema_version WHERE version = 29;
