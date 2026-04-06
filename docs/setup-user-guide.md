# CCDash Setup Guide

This guide covers local setup, development startup, and a production-style startup flow.

## Prerequisites

- Node.js 20+ and npm
- Python 3.10+ with `venv`

## 1) Install Frontend Dependencies

```bash
npm install
```

## 2) Configure Environment

Copy `.env.example` to `.env` and set values as needed:

- `GEMINI_API_KEY` for AI insight features
- `CCDASH_BACKEND_HOST` (default `127.0.0.1`)
- `CCDASH_BACKEND_PORT` (default `8000`)
- `CCDASH_API_PROXY_TARGET` (default `http://127.0.0.1:8000`)
- `CCDASH_PYTHON` (optional explicit Python path)
- `CCDASH_TEST_VISUALIZER_ENABLED` (default `false`; global gate for `/api/tests/*` and `/tests`)
- `CCDASH_INTEGRITY_SIGNALS_ENABLED` (default `false`; integrity signal features)
- `CCDASH_LIVE_TEST_UPDATES_ENABLED` (default `false`; backend gate for test live invalidation)
- `CCDASH_SEMANTIC_MAPPING_ENABLED` (default `false`; semantic mapping features)
- `VITE_CCDASH_LIVE_EXECUTION_ENABLED` (default `true`; execution live updates)
- `VITE_CCDASH_LIVE_SESSIONS_ENABLED` (default `true`; session live updates)
- `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` (default `false`; active-session transcript append delivery)
- `VITE_CCDASH_LIVE_FEATURES_ENABLED` (default `false`; feature board/modal live invalidation)
- `VITE_CCDASH_LIVE_TESTS_ENABLED` (default `false`; test visualizer live invalidation)
- `VITE_CCDASH_LIVE_OPS_ENABLED` (default `false`; Ops panel live invalidation)
- `CCDASH_STORAGE_PROFILE` (`local` or `enterprise`; storage profile selector)
- `CCDASH_DB_BACKEND` (`sqlite` or `postgres`; compatibility input)
- `CCDASH_DATABASE_URL` (required for Postgres-backed modes)
- `CCDASH_STORAGE_SHARED_POSTGRES` (`true` when CCDash shares Postgres infrastructure)
- `CCDASH_STORAGE_ISOLATION_MODE` (`dedicated`, `schema`, or `tenant`)
- `CCDASH_STORAGE_SCHEMA` (required for schema-based isolation)
- `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` (optional filesystem ingest in enterprise mode)
- `CCDASH_LINKING_LOGIC_VERSION` (default `1`; bump to force a full link rebuild after linking-logic changes)
- `CCDASH_STARTUP_SYNC_LIGHT_MODE` (default `true`; startup runs a light sync first)
- `CCDASH_STARTUP_SYNC_DELAY_SECONDS` (default `2`; delay before startup sync begins)
- `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` (default `true`; deferred heavier rebuild after startup)
- `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS` (default `45`)
- `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS` (default `false`)

Telemetry exporter configuration is documented in the dedicated guide:

- [`docs/guides/telemetry-exporter-guide.md`](./guides/telemetry-exporter-guide.md) covers the exporter settings, worker behavior, queue cap, purge behavior, and security rules.
- [`docs/guides/telemetry-exporter-troubleshooting.md`](./guides/telemetry-exporter-troubleshooting.md) covers common failure modes and recovery steps.

The exporter uses these telemetry-specific environment variables:

- `CCDASH_TELEMETRY_EXPORT_ENABLED` (default `false`; master enable for telemetry export)
- `CCDASH_SAM_ENDPOINT` (required when export is enabled; SAM ingestion URL)
- `CCDASH_SAM_API_KEY` (required when export is enabled; SAM authentication key)
- `CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS` (default `900`; scheduled export cadence)
- `CCDASH_TELEMETRY_EXPORT_BATCH_SIZE` (default `50`; rows pushed per run)
- `CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS` (default `30`; outbound request timeout)
- `CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE` (default `10000`; pending-row cap)
- `CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS` (default `30`; synced-row retention window)
- `CCDASH_TELEMETRY_ALLOW_INSECURE` (default `false`; allow non-HTTPS SAM endpoints for local testing only)

`CCDASH_STORAGE_PROFILE` is the operator-facing switch for local versus enterprise storage. `CCDASH_DB_BACKEND` remains a compatibility setting behind that contract. For the full profile matrix, see [`docs/guides/storage-profiles-guide.md`](./guides/storage-profiles-guide.md).

Canonical transcript intelligence is now fully rolled out under that storage contract. Use [`docs/guides/session-intelligence-rollout-guide.md`](./guides/session-intelligence-rollout-guide.md) for the enterprise backfill workflow, health checks, and SkillMeat draft approval flow.

## 3) Install Backend Dependencies

```bash
npm run setup
```

This creates `backend/.venv` (if missing) and installs `backend/requirements.txt`.

## 4) Start Development

```bash
npm run dev
```

What this does:

- Starts backend first and waits for `GET /api/health` to become healthy
- Starts Vite frontend only after backend is ready
- Shuts both down together on Ctrl+C
- Startup sync uses light mode by default:
  - first pass syncs sessions/docs/tasks/features
  - link rebuild and analytics snapshot are deferred
  - deferred heavy rebuild can be tuned via `CCDASH_STARTUP_DEFERRED_*` vars

### Storage Profiles

Local-first default:

```bash
CCDASH_STORAGE_PROFILE=local
CCDASH_DB_BACKEND=sqlite
```

Use this for the default desktop/local workflow. SQLite plus filesystem-derived ingestion stays the primary contract.

Local upgrade note:

- Existing SQLite installs should stay on `CCDASH_STORAGE_PROFILE=local`; Phase 5/6 does not require enterprise-table backfills in SQLite.
- Back up the SQLite file if you manage a custom path, then start the updated app and allow migrations to run normally.
- If you later move to hosted enterprise mode, bootstrap Postgres separately and re-ingest/rebuild instead of trying to promote the SQLite file in place.
- Expect `GET /api/health` to report a cache-oriented posture such as `sessionIntelligenceProfile=local_cache`, `sessionIntelligenceBackfillStrategy=local_rebuild_from_filesystem`, and `sessionEmbeddingWriteStatus=unsupported`.

Dedicated enterprise Postgres:

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://...
```

Use this for hosted CCDash deployments where Postgres is the canonical store. The API should stay stateless; the worker owns startup sync, refresh, and scheduled jobs.

For canonical transcript intelligence, this is the authoritative posture: enterprise Postgres owns transcript intelligence, full analytics, and checkpointed historical backfill.

Shared enterprise Postgres:

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://...
CCDASH_STORAGE_SHARED_POSTGRES=true
CCDASH_STORAGE_ISOLATION_MODE=schema
CCDASH_STORAGE_SCHEMA=ccdash
```

Use `schema` or `tenant` isolation only when CCDash shares infrastructure with another app. Shared Postgres is a deployment posture, not a license to couple tables across applications.

Shared-enterprise still uses the same canonical transcript-intelligence contract as dedicated enterprise, but `/api/health` should also show the explicit schema or tenant isolation boundary.

## Optional: Run Services Separately

Use two terminals:

```bash
npm run dev:backend
```

```bash
npm run dev:frontend
```

To run background work separately from the API:

```bash
npm run dev:worker
```

## Production-Style Startup

Build frontend assets:

```bash
npm run build
```

Start backend:

```bash
npm run start:backend
```

Start background worker:

```bash
npm run start:worker
```

Serve built frontend:

```bash
npm run start:frontend
```

For real deployments, run frontend, API, and worker under a process manager (systemd, Docker, or similar) and terminate TLS at a reverse proxy. `backend.main:app` should stay stateless for hosted API deployments; `backend.worker` owns startup sync and scheduled/background job execution.

Enterprise operator split:

- API serves HTTP and reads canonical state.
- Worker runs sync, refresh, and scheduled jobs.
- Filesystem ingest is optional in enterprise mode and should be treated as an adapter, not an assumption.
- Check `GET /api/health` to confirm `storageComposition`, `storageCanonicalStore`, `auditStore`, `migrationGovernanceStatus`, `syncProvisioned`, isolation mode/schema, and the runtime/job capability fields.

### Session-Intelligence Validation

Use `GET /api/health` as the runtime validation matrix for the completed rollout.

Minimum session-intelligence fields to confirm:

- `sessionIntelligenceProfile`
- `sessionIntelligenceAnalyticsLevel`
- `sessionIntelligenceBackfillStrategy`
- `sessionIntelligenceMemoryDraftFlow`
- `sessionIntelligenceIsolationBoundary`
- `sessionEmbeddingWriteStatus`
- `storageProfileValidationMatrix`
- `canonicalSessionStore`

Expected posture by row:

| Validation row | Expected posture |
| --- | --- |
| `local-sqlite` | Cache-oriented SQLite with canonical transcript projection, filesystem rebuilds, reviewable local drafts, and no authoritative embeddings |
| `enterprise-postgres` | Canonical Postgres transcript intelligence, full analytics, authoritative embeddings, and `checkpointed_enterprise_backfill` |
| `shared-enterprise-postgres` | Same canonical enterprise posture plus explicit `schema` or `tenant` isolation boundaries |

Memory-draft publishing remains approval-gated in every posture. CCDash can prepare reviewable SkillMeat memory drafts, but operators must still approve publication explicitly.

For the full field list, rollout command, checkpoint semantics, and failure modes, see [`docs/guides/session-intelligence-rollout-guide.md`](./guides/session-intelligence-rollout-guide.md).

## Troubleshooting

### Live updates do not activate

Check both layers of rollout:

1. backend env/project gates for the domain (`CCDASH_LIVE_TEST_UPDATES_ENABLED`, project testing flags, etc.)
2. matching frontend `VITE_CCDASH_LIVE_*` toggle for the surface you expect to stream

Feature, test, and ops live invalidation stay on their polling fallback paths when either gate is off. Session transcript append can be toggled independently of coarse session live updates; when it is off, Session Inspector keeps using the existing invalidation-plus-REST recovery path.

### `ECONNREFUSED` for `/api/*` in Vite

Backend is not reachable on the configured target.

Check backend health:

```bash
curl -sS http://127.0.0.1:8000/api/health
```

If unhealthy, run:

```bash
npm run setup
npm run dev:backend
```

### `500` for `/api/features`

This is a backend error. Start backend in its own terminal to inspect logs:

```bash
npm run dev:backend
```

Then load the UI again and inspect backend stack traces.

### Frontend opens but data stays empty

- Confirm `npm run dev` shows backend health before frontend startup.
- Confirm `CCDASH_API_PROXY_TARGET` points to the running backend.
- Confirm `GET /api/health` responds with `status: ok`.
- If session-intelligence rollout validation is the issue, compare `storageProfileValidationMatrix` and the resolved `sessionIntelligence*` fields against [`docs/guides/storage-profiles-guide.md`](./guides/storage-profiles-guide.md) and [`docs/guides/session-intelligence-rollout-guide.md`](./guides/session-intelligence-rollout-guide.md).

### `/tests` disabled, empty, or returning `503`

1. Confirm env gates are enabled (`CCDASH_TEST_VISUALIZER_ENABLED=true` at minimum).
2. In CCDash, open `Settings` -> `Projects` -> `Testing Configuration`.
3. Enable `Test Visualizer` for the project and configure at least one enabled platform.
4. Click `Validate Paths`, review `Source Status`, then click `Run Sync Now`.
5. Reload `/tests` and click `Refresh`.

For the complete project-scoped testing setup flow (platforms, patterns, setup script export), see [`docs/testing-user-guide.md`](./testing-user-guide.md).
