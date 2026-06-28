---
title: Auth Modes Guide
description: Workspace-scoped token authentication for remote CCDash deployments
audience: operators, developers
tags: [auth, workspace-tokens, security, migration, multi-project]
created: 2026-05-21
updated: 2026-05-21
category: Configuration
status: stable
related: ["docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md", "docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md"]
---

## Overview

CCDash v1 supports two authentication modes depending on the runtime profile:

| Auth Mode | Profile | Use Case | Status |
|-----------|---------|----------|--------|
| `single_bearer` | `local` | Single-user laptop; development | Legacy (backwards compatible) |
| `workspace_token` | `api` / `worker` | Multi-workspace remote deployments | Active (default for production) |

Check your active auth mode via the health endpoint:

```bash
curl http://localhost:8000/api/health | jq .auth_mode
# Output: "workspace_token" or "single_bearer"
```

## Single-Bearer Auth (local profile)

The `local` profile retains the original authentication model for backwards compatibility.

```bash
export CCDASH_PROFILE=local
export CCDASH_AUTH_TOKEN=your-secret-token
npm run dev:backend
```

In `local` profile:
- One static bearer token per instance
- No token database required
- Every authenticated request uses the same token
- No per-workspace scoping (single tenant only)
- Auth always in effect; cannot be disabled

**Limitations**: Cannot isolate workspaces or rotate tokens independently.

## Workspace-Scoped Auth (api/worker profiles)

The `api` and `worker` runtime profiles use workspace-scoped bearer tokens stored in a database table. Each token is bound to a single (workspace, project) pair and can be revoked independently.

### Auth Flow

```
1. Client sends: Authorization: Bearer <token-secret>
   ↓
2. WorkspaceTokenAuthBackend.verify()
   • SHA-256 fingerprint of secret (O(1) LRU lookup)
   • If cached: return cached AuthContext + recheck revocation
   • If miss: load token snapshot, argon2id verify against hashes
   ↓
3. AuthContext{workspace_id, project_id, token_id, scope} → request.state
   ↓
4. All repository queries filtered by workspace_id (explicit predicate)
   • Cross-workspace reads return 403 or empty
   • Cannot be bypassed via x-ccdash-project-id header
```

### Data Model

The backend creates two tables during schema migration (v29):

**workspaces table:**
```sql
CREATE TABLE workspaces (
    workspace_id    TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
```

**workspace_tokens table:**
```sql
CREATE TABLE workspace_tokens (
    token_id        TEXT PRIMARY KEY,           -- Stable ID for revocation
    workspace_id    TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    hashed_token    TEXT NOT NULL UNIQUE,       -- argon2id hash of secret
    scope           TEXT NOT NULL,              -- 'ingest_write' | 'read' | 'admin'
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    revoked_at      TEXT,
    description     TEXT
);

CREATE INDEX ix_workspace_tokens_workspace ON workspace_tokens (workspace_id)
    WHERE revoked_at IS NULL;
CREATE INDEX ix_workspace_tokens_hash ON workspace_tokens (hashed_token)
    WHERE revoked_at IS NULL;
```

## Migration: Single-Bearer to Workspace-Scoped

If you are upgrading from an older version with `local` profile, migrate to `api` profile with workspace tokens:

### Step 1: Verify Current State

Check the current auth mode:

```bash
curl http://localhost:8000/api/health | jq .auth_mode
# Expected: "single_bearer" (old) or "workspace_token" (already migrated)
```

Check your current bearer token environment:

```bash
echo $CCDASH_AUTH_TOKEN
# Keep this value — you'll use it in migration
```

Get your project ID from `projects.json`:

```bash
cat projects.json | jq '.projects[0].id'
# Example: "my-project"
```

### Step 2: Run Migration Script

With the server stopped, run the one-shot migration script:

```bash
export CCDASH_AUTH_TOKEN=<your-current-bearer-token>
cd backend
python -m backend.scripts.migrate_bearer_to_workspace_token \
    --project my-project
```

On success, you will see:

```
SUCCESS: token_id=<uuid>
  workspace_id = default-local
  project_id   = my-project
  scope        = admin

Next steps:
  export CCDASH_AUTH_TOKEN=<your-original-token>
  export CCDASH_PROFILE=api
  # restart the server
  # verify: GET /api/health → auth_mode == 'workspace_token'
```

**Idempotency**: Running the script twice on the same token is safe — the second run detects the token already exists and exits with code 0 (no-op).

### Step 3: Activate Workspace-Token Backend

Update your environment:

```bash
export CCDASH_PROFILE=api
# CCDASH_AUTH_TOKEN remains the same plaintext value
```

Restart the server:

```bash
npm run dev:backend
# or in production: systemctl restart ccdash-api
```

### Step 4: Verify Migration

Check the health endpoint:

```bash
curl http://localhost:8000/api/health | jq .auth_mode
# Expected output: "workspace_token"
```

If the output is `"workspace_token"`, migration is complete.

## Token Rotation

### Issue a New Token

To issue a new workspace-scoped token (e.g., for a daemon):

```bash
python -m backend.scripts.migrate_bearer_to_workspace_token \
    --project my-project \
    --workspace my-workspace \
    --token <new-secret> \
    --description "Daemon token for workspace-1"
```

This creates a new token row. Both the old and new tokens are active until you revoke the old one.

### Update the Daemon

Update the daemon's token in `daemon.toml`:

```toml
[remote]
endpoint = "https://api.ccdash.local"
token = "<new-secret>"
```

Ensure file permissions are strict:

```bash
chmod 0600 daemon.toml
```

### Revoke the Old Token

Find the old token's ID:

```bash
sqlite3 data/ccdash_cache.db \
    "SELECT token_id, description FROM workspace_tokens WHERE workspace_id='my-workspace' AND revoked_at IS NULL ORDER BY created_at DESC;"
```

Revoke it (via CLI or API):

```bash
sqlite3 data/ccdash_cache.db \
    "UPDATE workspace_tokens SET revoked_at = datetime('now') WHERE token_id='<old-uuid>';"
```

The old token is rejected on its very next use — revocation takes effect within one request cycle.

## Daemon Token Storage (daemon.toml)

The daemon stores its token in the local `daemon.toml` configuration file. Protect this file:

```bash
chmod 0600 daemon.toml
```

Example `daemon.toml`:

```toml
[remote]
endpoint = "https://api.ccdash.example.com"
token = "your-workspace-token-here"
project_id = "my-project"
workspace_id = "my-workspace"

[sync]
interval_seconds = 60
max_retries = 3
```

The token is never logged or echoed by the daemon — only its first 6 characters appear in logs for debugging.

## Error Codes

When using workspace-token auth, you may see these HTTP errors:

| Code | Error | Meaning | Resolution |
|------|-------|---------|-----------|
| 401 | `invalid_token` | Token not found in workspace_tokens table | Check token is correct; verify it is in the active (non-revoked) rows |
| 401 | `revoked_token` | Token was revoked; revoked_at IS NOT NULL | Issue a new token and update the daemon |
| 403 | `workspace_project_mismatch` | x-ccdash-project-id header doesn't match token's project_id | Remove or correct the header; routing is driven by the token, not the header |

Example error response:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "Bearer token not found or revoked"
  },
  "request_id": "req-12345"
}
```

## Performance Notes

Token verification uses an LRU cache to avoid repeated argon2id hashing:

- **LRU size**: 256 entries, 60-second TTL
- **Token snapshot refresh**: 60 seconds (in-memory list of active tokens)
- **Revocation re-check**: Every LRU cache hit performs a fast indexed lookup to detect revocation

For typical small-team deployments (tens of tokens):
- Cold (uncached) verify: ~100–300ms (argon2id cost)
- Warm (cached) verify: ~1ms (SHA-256 + DB revocation check)

Steady-state median latency is dominated by the warm-cache path.

## Per-Workspace Scoping

Every table that holds session, document, task, feature, or progress data includes a `workspace_id` column added in schema v29:

```sql
ALTER TABLE sessions        ADD workspace_id TEXT;
ALTER TABLE documents       ADD workspace_id TEXT;
ALTER TABLE tasks           ADD workspace_id TEXT;
ALTER TABLE features        ADD workspace_id TEXT;
ALTER TABLE entity_links    ADD workspace_id TEXT;
ALTER TABLE progress_files  ADD workspace_id TEXT;
ALTER TABLE ingest_cursors  ADD workspace_id TEXT;
```

Every repository query includes a `WHERE workspace_id = :workspace_id` predicate sourced from `AuthContext.workspace_id`. This ensures that tokens in workspace A cannot read or write data in workspace B.

The backend does not yet use PostgreSQL Row-Level Security (RLS) in v1; explicit predicate filtering is applied to all queries.

## Rollback

If you need to revert to single-bearer auth:

1. **Revert environment**:
   ```bash
   export CCDASH_PROFILE=local
   export CCDASH_AUTH_TOKEN=<original-token>
   ```

2. **Stop the server and run rollback script**:
   ```bash
   sqlite3 data/ccdash_cache.db < backend/scripts/rollback.sql
   ```

3. **Restart**:
   ```bash
   npm run dev:backend
   ```

4. **Verify**:
   ```bash
   curl http://localhost:8000/api/health | jq .auth_mode
   # Expected: "single_bearer"
   ```

**Important SQLite limitation**: SQLite versions before 3.35.0 do not support `ALTER TABLE ... DROP COLUMN`. On older SQLite, the rollback script will skip column drops. To fully clean up the workspace_id columns, you must manually rebuild the affected tables — see `backend/scripts/rollback.sql` header for instructions. PostgreSQL deployments support standard column drops and rollback cleanly.

## Related

- **ADR-008**: Architecture decision on workspace-scoped tokens — design rationale, hard gates, consequences. See `docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md`.
- **ADR-010**: Multi-project routing with request-scoped binding — how a single `api` process routes requests to the correct project based on `AuthContext.project_id`. See `docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md`.
- **Migration script**: `backend/scripts/migrate_bearer_to_workspace_token.py`
- **Auth backend**: `backend/adapters/auth/workspace_token.py`
- **Rollback script**: `backend/scripts/rollback.sql`
