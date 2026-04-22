# Runtime, Storage, and Performance Quickstart

Updated: 2026-04-19

This is the shortest operator guide for the current CCDash runtime split,
storage profiles, and performance posture. Use it when you want the newest
runtime/storage behavior without re-reading the full setup and rollout docs.

## 1. Pick the right posture

### Local daily workflow

Use this when developing locally or running CCDash as a desktop-style tool.

```bash
CCDASH_STORAGE_PROFILE=local
CCDASH_DB_BACKEND=sqlite
```

Recommended startup:

```bash
npm run dev
```

That keeps the local-first flow: SQLite, filesystem-derived sync, and the
standard contributor startup path.

### Hosted or serious multi-process workflow

Use this when Postgres should be the canonical store and the API should stay
stateless.

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>
```

If CCDash shares a Postgres instance with something else:

```bash
CCDASH_STORAGE_SHARED_POSTGRES=true
CCDASH_STORAGE_ISOLATION_MODE=schema
CCDASH_STORAGE_SCHEMA=ccdash
```

Use `tenant` isolation only if your deployment already enforces tenancy at that
boundary.

## 2. Run the right processes

### Best local performance layout

```bash
# terminal 1
npm run dev:backend

# terminal 2
npm run dev:worker

# terminal 3
npm run dev:frontend
```

Why this matters:

- the worker owns cache warming, sync, refresh, and scheduled/background work
- the API stays responsive instead of doing mixed-mode background ownership
- cached query TTLs are much more effective when the worker is actually running

### Hosted runtime contract

- API: `backend.runtime.bootstrap_api:app`
- Worker: `python -m backend.worker`
- Local convenience only: `backend.main:app` and `npm run dev`

Do not use the local runtime profile as a substitute for enterprise validation.

## 3. Verify that the runtime is healthy

For the API, check:

- `GET /api/health`

Important fields:

- `profile`
- `storageProfile`
- `storageComposition`
- `storageBackend`
- `migrationStatus`
- `migrationGovernanceStatus`
- `jobsEnabled`
- `syncProvisioned`
- `canonicalSessionStore`

For the worker, check:

- `http://127.0.0.1:9465/livez`
- `http://127.0.0.1:9465/readyz`
- `http://127.0.0.1:9465/detailz`

Important worker posture:

- `runtimeProfile=worker`
- readiness succeeds only after worker binding is valid
- `CCDASH_WORKER_PROJECT_ID` must resolve for hosted readiness

## 4. Apply the current performance posture

These are still the highest-leverage settings today:

```bash
CCDASH_QUERY_CACHE_TTL_SECONDS=600
CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=300
CCDASH_STARTUP_DEFERRED_REBUILD_LINKS=false
CCDASH_STARTUP_SYNC_LIGHT_MODE=true
```

Use them because:

- TTL `600` avoids cold windows between warmer runs
- disabling deferred rebuild reduces duplicate startup work
- light-mode startup improves boot-to-ready time

If long-running tabs grow too much in memory, also disable transcript append:

```bash
VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED=false
```

## 5. Postgres-specific usage

Use Postgres when you want the current hosted enterprise posture:

- canonical enterprise storage
- shared/dedicated storage validation through storage profiles
- worker-owned background processing
- canonical session intelligence and backfill workflows

Do not promote a local SQLite file in place. Treat enterprise Postgres as a
fresh bootstrap plus re-ingest/rebuild.

If you are rolling out enterprise transcript intelligence after Postgres setup,
use the runbook:

- [enterprise-session-intelligence-runbook.md](enterprise-session-intelligence-runbook.md)

## 6. Best references

- Full setup and env reference: [setup.md](setup.md)
- Storage profile contract: [storage-profiles-guide.md](storage-profiles-guide.md)
- Data-platform rollout and handoff: [data-platform-rollout-and-handoff.md](data-platform-rollout-and-handoff.md)
- Query-cache tuning: [query-cache-tuning-guide.md](query-cache-tuning-guide.md)
- Performance tracker: [performance-and-reliability-v1.md](../project_plans/meta_plans/performance-and-reliability-v1.md)
