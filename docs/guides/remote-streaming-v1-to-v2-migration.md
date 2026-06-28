---
title: "Remote Streaming v1→v2 Migration Guide"
description: "Migrate from local single-user CCDash to remote multi-workspace remote-ingest deployment"
audience: operators, platform engineers, DevOps
category: Operations
tags: [migration, remote-ingest, workspace-auth, schema-upgrade, multi-project]
created: 2026-06-28
updated: 2026-06-28
status: stable
related: ["docs/guides/auth-modes.md", "docs/guides/remote-ingest-operator-guide.md", "docs/guides/external-api-lan-deployment.md", "docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md", "docs/project_plans/adrs/adr-009-ingest-source-routing-schema-and-cursors.md"]
---

# Remote Streaming v1→v2 Migration Guide

This guide covers migrating from a **local single-user CCDash deployment** (v1) to a **remote
multi-workspace remote-ingest deployment** (v2). The migration is forward-only but non-destructive;
all existing session and document data is preserved and automatically migrated.

---

## What Changes

### Schema Migration (v35 → v37)

The schema migration is **automatic and additive** on startup. No manual steps required.

| Aspect | v1 (Single-User) | v2 (Multi-Workspace) |
|--------|------------------|---------------------|
| **Schema version** | v35 | v37 |
| **Auth mode** | `single_bearer` (optional) | `workspace_token` (default) |
| **Workspace support** | No; filesystem-only | Yes; `workspaces` table |
| **Ingest transport** | Filesystem polling | NDJSON batches + daemon |
| **New tables** | — | `workspaces`, `workspace_tokens`, `ingest_cursors` |
| **New columns** | — | `workspace_id` (sessions, docs, tasks, features, entity_links) |

**Default workspace**: All existing sessions and documents are assigned to `workspace_id = "default-local"`
on migration. This ensures **zero breaking changes** to read APIs.

### New Columns (Nullable, Backwards Compatible)

```sql
ALTER TABLE sessions ADD COLUMN workspace_id TEXT DEFAULT 'default-local';
ALTER TABLE documents ADD COLUMN workspace_id TEXT DEFAULT 'default-local';
ALTER TABLE tasks ADD COLUMN workspace_id TEXT DEFAULT 'default-local';
ALTER TABLE features ADD COLUMN workspace_id TEXT DEFAULT 'default-local';
ALTER TABLE entity_links ADD COLUMN workspace_id TEXT DEFAULT 'default-local';

CREATE TABLE workspaces (
  workspace_id TEXT PRIMARY KEY,
  display_name TEXT,
  created_at TEXT
);

CREATE TABLE workspace_tokens (
  token_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,
  created_at TEXT,
  last_used_at TEXT,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE TABLE ingest_cursors (
  source_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  cursor TEXT,
  last_updated_at TEXT,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);
```

---

## Migration Path: Step-by-Step

### Phase 1: Prepare (Zero Downtime)

1. **Review current state**:
   ```bash
   # Check current version and auth mode
   curl http://localhost:8000/api/health | jq '.'
   # Expected: "version": "0.50.x", "auth_mode": "single_bearer"
   ```

2. **Back up database** (SQLite or Postgres):
   ```bash
   # SQLite
   cp data/ccdash_cache.db ~/ccdash_backup_preupgrade.db
   
   # Postgres
   pg_dump --host localhost --username postgres ccdash_prod \
     > ~/ccdash_backup_preupgrade.sql
   ```

3. **Review `.env` and config**:
   ```bash
   cat .env  # or .env.local
   # Current: CCDASH_DB_BACKEND=sqlite (or postgres)
   # No CCDASH_API_BEARER_TOKEN set
   ```

### Phase 2: Enable Bearer Auth (v2 Auth Mode)

Bearer auth is additive; existing single-user mode continues to work.

1. **Generate a workspace token**:
   ```bash
   # Use the bootstrap token generator (built into startup)
   # Or generate one manually
   TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   echo $TOKEN  # e.g., Drmhx_aTvK7xL2m3PqRsTuVwXyZaBcDeFg
   ```

2. **Set the token in environment**:
   ```bash
   export CCDASH_API_BEARER_TOKEN="$TOKEN"
   # Or in .env:
   # CCDASH_API_BEARER_TOKEN=Drmhx_aTvK7xL2m3PqRsTuVwXyZaBcDeFg
   ```

3. **Restart backend**:
   ```bash
   npm run dev:backend
   # Or if running: Ctrl+C, then npm run dev:backend
   ```

4. **Verify auth mode changed**:
   ```bash
   curl http://localhost:8000/api/health | jq '.auth_mode'
   # Expected: "workspace_token"
   ```

### Phase 3: Verify Schema Migration

On restart, CCDash automatically runs all pending migrations (v35 → v37).

1. **Check migration completed** (check logs during startup):
   ```bash
   # Logs should show:
   # "Running migration: v36_add_ingest_source_routing"
   # "Running migration: v37_add_workspace_tables"
   ```

2. **Verify new columns exist**:
   ```bash
   # SQLite
   sqlite3 data/ccdash_cache.db ".schema sessions" | grep workspace_id
   
   # Postgres
   psql -h localhost -U postgres ccdash_prod \
     -c "\d sessions" | grep workspace_id
   ```

3. **Verify default workspace created**:
   ```bash
   # Query via API
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/health/detail | jq '.workspace_id'
   # Expected: "default-local"
   ```

### Phase 4: Point a Daemon at the Server

1. **Install the daemon** (bundled with `ccdash-cli`):
   ```bash
   # If using global ccdash-cli (pipx)
   ccdash-cli daemon --help
   
   # Or repo-local
   backend/.venv/bin/ccdash daemon --help
   ```

2. **Start the daemon**:
   ```bash
   ccdash-cli daemon start \
     --server http://localhost:8000 \
     --token $CCDASH_API_BEARER_TOKEN
   ```

3. **Verify daemon is healthy**:
   ```bash
   ccdash-cli daemon status
   # Expected: "Status: running (pid XXXX)", "Last poll: ... (healthy)"
   ```

### Phase 5: Verify Multi-Workspace API Contracts

1. **Health endpoint**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/health | jq '.'
   # Expected: "auth_mode": "workspace_token"
   ```

2. **Health detail (ingest source state)**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/health/detail | jq '.ingest_sources'
   # Expected: [{ "source_id": "...", "workspace_id": "default-local", "state": "idle|connected" }]
   ```

3. **List sessions in default workspace**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     'http://localhost:8000/api/v1/sessions?workspace_id=default-local' | jq '.data | length'
   # Expected: count of existing sessions
   ```

### Phase 6: Test Remote Ingest

1. **Craft a test batch** (NDJSON):
   ```bash
   cat > /tmp/test-batch.ndjson << 'EOF'
   {"event_id": "test-001", "session_id": "sess_abc123", "messages": [{"role": "user", "content": "hello"}]}
   {"event_id": "test-002", "session_id": "sess_def456", "messages": [{"role": "assistant", "content": "hi"}]}
   EOF
   ```

2. **POST to ingest endpoint**:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/x-ndjson" \
     -H "x-ccdash-project-id: main" \
     --data-binary @/tmp/test-batch.ndjson \
     http://localhost:8000/api/v1/ingest/sessions
   
   # Expected response (202):
   # { "accepted": 2, "rejected": [], "dead_lettered": [], "cursor_advanced_to": "..." }
   ```

3. **Verify sessions created**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     'http://localhost:8000/api/v1/sessions?workspace_id=default-local' | \
     jq '.data | map(select(.session_id | startswith("sess_"))) | length'
   # Expected: 2 (or count including new ones)
   ```

---

## Rollback Playbook

The migration is **forward-only**, meaning you cannot downgrade the schema. However, auth is additive;
you can disable remote ingest and fall back to filesystem-only operation at any time.

### If Remote Ingest Fails

1. **Stop the daemon**:
   ```bash
   kill $(pgrep -f 'ccdash-cli daemon')
   ```

2. **Disable ingest**:
   ```bash
   export CCDASH_INGEST_ENABLED=0
   npm run dev:backend
   ```

3. **Fall back to filesystem monitoring**:
   - Worker resumes reading `.claude/` directly
   - All read APIs continue to work (workspace_id defaults to "default-local")
   - No data loss

4. **Preserve dead-letter files** (if any):
   ```bash
   cp -r ~/.local/state/ccdash/deadletter ~/deadletter_backup
   ```

5. **When issues are fixed, re-enable**:
   ```bash
   export CCDASH_INGEST_ENABLED=1
   ccdash-cli daemon replay --dir ~/deadletter_backup
   ```

### If You Need to Revert Auth

1. **Remove bearer token**:
   ```bash
   unset CCDASH_API_BEARER_TOKEN
   # Or in .env: comment out the line
   ```

2. **Restart backend**:
   ```bash
   npm run dev:backend
   ```

3. **Auth mode reverts to `single_bearer`** (or `test` in dev):
   ```bash
   curl http://localhost:8000/api/health | jq '.auth_mode'
   # Expected: "single_bearer"
   ```

4. **All data remains** (workspace_id columns are now nullable; queries still work)

### Cannot Downgrade Schema

Schema v37 is permanent. If you must revert to v35:

1. Restore from backup:
   ```bash
   # SQLite
   rm data/ccdash_cache.db
   cp ~/ccdash_backup_preupgrade.db data/ccdash_cache.db
   
   # Postgres
   psql -h localhost -U postgres -c "DROP DATABASE ccdash_prod"
   psql -h localhost -U postgres < ~/ccdash_backup_preupgrade.sql
   ```

2. Switch back to old binary (not recommended in production)

---

## Postgres In-Place Upgrade

For Postgres deployments, v29 → v35 in-place upgrade is validated by the `npm run docker:hosted:smoke:seeded-pg`
gate. Schema migrations then proceed normally (v35 → v37) on `ccdash` backend startup.

**No additional steps required.** The seeded-pg smoke covers composite FK bugs that SQLite mocks miss.

---

## Timeline & Success Criteria

| Phase | Duration | Success Indicator |
|-------|----------|-------------------|
| Prepare | 5 min | Backup verified, config reviewed |
| Enable auth | 5 min | `curl /api/health` shows `workspace_token` |
| Schema verify | 2 min | New columns visible in DB |
| Daemon | 5 min | `ccdash-cli daemon status` shows `running` |
| Test ingest | 10 min | Test NDJSON batch accepted (202), session queryable |
| **Total** | **30 min** | All checks pass |

---

## FAQ

**Q: Will my existing sessions disappear?**

A: No. All existing sessions are migrated to `workspace_id = "default-local"` automatically.
They remain queryable via `/api/v1/sessions?workspace_id=default-local`.

**Q: Do I have to use remote ingest?**

A: No. Remote ingest is optional. You can keep using filesystem-only mode by not starting the daemon.
Set `CCDASH_INGEST_ENABLED=0` if you prefer.

**Q: What if I have multiple workspaces?**

A: Create additional workspace tokens via the API:

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/v1/workspaces \
  -d '{"workspace_id": "team-a", "display_name": "Team A"}'
```

Then generate a token for that workspace and start a separate daemon instance.

**Q: Can I migrate data between workspaces?**

A: Not yet. This is a future capability. For now, data ingested under one workspace
remains scoped to that workspace.

**Q: What if the daemon crashes?**

A: Batches accumulate in the dead-letter queue. Restart the daemon, then run
`ccdash-cli daemon replay` to catch up.

**Q: How do I monitor the migration?**

A: Check daemon status regularly:

```bash
watch -n 5 'ccdash-cli daemon status | tail -10'
```

And check server health:

```bash
watch -n 5 'curl -s http://localhost:8000/api/health/detail | jq .ingest_sources'
```

