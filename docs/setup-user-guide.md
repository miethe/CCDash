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
For the full end-to-end hosted operator sequence, use [`docs/guides/enterprise-session-intelligence-runbook.md`](./guides/enterprise-session-intelligence-runbook.md).

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
- If you later move to hosted enterprise mode, treat that as a fresh hosted bootstrap plus re-ingest/rebuild. Do not try to promote the SQLite file in place.
- Expect `GET /api/health` to report a cache-oriented posture such as `sessionIntelligenceProfile=local_cache`, `sessionIntelligenceBackfillStrategy=local_rebuild_from_filesystem`, and `sessionEmbeddingWriteStatus=unsupported`.

Dedicated enterprise Postgres:

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://...
```

Use this for hosted CCDash deployments where Postgres is the canonical store. The API should stay stateless; the worker owns startup sync, startup refresh/backfill, telemetry export, and scheduled jobs.

For canonical transcript intelligence, this is the authoritative posture: enterprise Postgres owns transcript intelligence, full analytics, and checkpointed historical backfill.

Background job ownership in this hosted posture is explicit:

| Concern | local | api | worker | test |
| --- | --- | --- | --- | --- |
| Startup sync | owns | none | owns | none |
| File watch | owns | none | none | none |
| Analytics snapshots | owns | none | owns | none |
| Telemetry export | manual push-now only | manual push-now only | owns scheduled export | none |
| Integration refresh/backfill | startup refresh/backfill when configured | manual sync/refresh/backfill only | startup refresh/backfill when configured | none |
| Reconciliation / cache sync | owns | manual exception only when `sync_engine` exists | owns | none |

The API-local rows are manual operator controls, not background ownership. Keep these paths narrow and fail closed when the sync engine is not provisioned. Integration refresh/backfill runs at startup in local and worker runtimes when SkillMeat is configured; it is not a separate periodic job.

- `telemetry push-now`
- `integration refresh/backfill`
- `cache` sync/rebuild endpoints, guarded by `sync_engine` availability

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

Canonical runtime entrypoints:

| Runtime | Canonical entrypoint | Intended use |
| --- | --- | --- |
| `local` | `backend.main:app` and `npm run dev` | one-command contributor workflow with local-friendly sync/watch/jobs behavior |
| `api` | `backend.runtime.bootstrap_api:app` | hosted HTTP API only |
| `worker` | `python -m backend.worker` | hosted or local background sync, refresh, and scheduled jobs |
| `test` | `backend.runtime.bootstrap_test:app` | deterministic test harness with incidental background work disabled |

The matrix above is the operator-facing contract. Wrapper scripts are only equivalent when they select the same runtime explicitly. `npm run dev:backend` and `npm run start:backend` are repo wrappers for the hosted `api` runtime; `npm run dev` remains the local-convenience path.

Build frontend assets:

```bash
npm run build
```

Start API via the repo wrapper:

```bash
npm run start:backend
```

Start hosted API directly:

```bash
backend/.venv/bin/python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port 8000
```

Start background worker:

```bash
npm run start:worker
```

Serve built frontend:

```bash
npm run start:frontend
```

For real deployments, run frontend, API, and worker under a process manager (systemd, Docker, or similar) and terminate TLS at a reverse proxy. Hosted enterprise API deployments should serve `backend.runtime.bootstrap_api:app`; `backend.worker` owns startup sync and scheduled/background job execution. `backend.main:app` and `npm run dev` remain the local-convenience entrypoints; `npm run dev:backend` and `npm run start:backend` are convenience wrappers around the hosted `api` runtime.

Repo-shipped process-manager examples now live in [`deploy/runtime/README.md`](../deploy/runtime/README.md), including:

- [`deploy/runtime/systemd/ccdash-api.service`](../deploy/runtime/systemd/ccdash-api.service)
- [`deploy/runtime/systemd/ccdash-worker.service`](../deploy/runtime/systemd/ccdash-worker.service)
- [`deploy/runtime/systemd/ccdash-frontend.service`](../deploy/runtime/systemd/ccdash-frontend.service)
- [`deploy/runtime/supervisor/ccdash.conf`](../deploy/runtime/supervisor/ccdash.conf)

Those examples mirror the current split topology only. They do not add TLS termination or a hardened public frontend server beyond the repo's existing `npm run start:frontend` helper.

### Hosted Smoke Validation

Use the hosted compose example when you want one repeatable runtime check for split startup, probes, migrations, one background-job control path, and the shipped CLI/MCP adapters.

1. Edit [`deploy/runtime/compose.hosted.env.example`](../deploy/runtime/compose.hosted.env.example) and replace `CCDASH_WORKER_PROJECT_ID` with a project id the workspace registry can resolve.
2. Render and start the stack:

```bash
npm run docker:hosted:smoke:config
npm run docker:hosted:smoke:up
npm run docker:hosted:smoke:ps
```

3. Validate startup, probes, and migrations:

```bash
npm run docker:hosted:smoke:probes
```

Expected checks:

- frontend returns `200`
- API readiness succeeds
- API detail reports `profile=api`, `migrationStatus=applied`, and `jobsEnabled=false`
- worker readiness succeeds
- worker detail reports `runtimeProfile=worker` and a bound project id

4. Validate one representative background-job control path:

```bash
npm run docker:hosted:smoke:job
```

This flips the telemetry exporter setting on and calls `POST /api/telemetry/export/push-now`. In a fresh smoke stack the normal result is `success=true` with `batchSize=0`. That proves the worker-owned exporter path is present without claiming the repo ships a real telemetry sink.

5. Validate the shipped query adapters:

```bash
npm run docker:hosted:smoke:cli-contract
npm run docker:hosted:smoke:mcp-contract
```

These are adapter-contract checks run inside the API container. They prove the repo-local CLI and stdio MCP server still expose the current query surface. They are not a substitute for the separately packaged global `ccdash-cli`.

6. Tear the stack down:

```bash
npm run docker:hosted:smoke:down
```

Or run the full sequence with:

```bash
npm run docker:hosted:smoke:validate
```

Enterprise operator split:

- API serves HTTP and reads canonical state.
- Worker runs sync, refresh, and scheduled jobs.
- Filesystem ingest is optional in enterprise mode and should be treated as an adapter, not an assumption.
- Check `GET /api/health` to confirm `storageComposition`, `storageCanonicalStore`, `auditStore`, `migrationGovernanceStatus`, `syncProvisioned`, isolation mode/schema, and the runtime/job capability fields.
- Check the worker probe on `CCDASH_WORKER_PROBE_HOST:CCDASH_WORKER_PROBE_PORT` or the default `127.0.0.1:9465` using `/livez`, `/readyz`, and `/detailz`.
- If the worker does not resolve `CCDASH_WORKER_PROJECT_ID`, hosted validation is not complete even if the API is healthy.

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

For the end-to-end enterprise setup, backfill, and post-rollout usage sequence, see [`docs/guides/enterprise-session-intelligence-runbook.md`](./guides/enterprise-session-intelligence-runbook.md).
For the narrower rollout command, checkpoint semantics, and failure modes, see [`docs/guides/session-intelligence-rollout-guide.md`](./guides/session-intelligence-rollout-guide.md).

## Performance Tuning Quick Start

If CCDash feels heavy — slow startup, repeated syncs, sluggish responses after a restart, or the Chrome tab ballooning past a gigabyte — the following defaults are the highest-leverage knobs. See [`docs/project_plans/meta_plans/performance-and-reliability-v1.md`](./project_plans/meta_plans/performance-and-reliability-v1.md) for the full initiative tracker.

### Fast defaults for daily use

Copy these into `.env` to smooth out cold starts and keep cached queries warm:

```bash
# Keep the agent query cache warm across warmer runs (default 60/300 leaves cold windows).
CCDASH_QUERY_CACHE_TTL_SECONDS=600
CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=300

# Halve startup link work — the deferred rebuild is rarely needed day-to-day.
CCDASH_STARTUP_DEFERRED_REBUILD_LINKS=false

# Keep light-mode startup on so the readiness probe passes quickly.
CCDASH_STARTUP_SYNC_LIGHT_MODE=true
```

### Why the worker matters

The query-cache warmer only runs inside the worker runtime. Without `npm run dev:worker` (or `npm run start:worker` in production), every TTL expiry is served from a cold query. For the recommended layout:

```bash
# Terminal 1 — HTTP API
npm run dev:backend

# Terminal 2 — sync + cache warmer
npm run dev:worker

# Terminal 3 — frontend
npm run dev:frontend
```

Or run all three with `npm run dev` for the standard contributor workflow.

### When to bump a knob

| Symptom | Setting | Guidance |
|---------|---------|----------|
| Cold queries after idle | `CCDASH_QUERY_CACHE_TTL_SECONDS` | Increase to 600+; pair with warmer |
| Slow boot-to-ready | `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` | Set `false` unless you need an immediate full relink |
| `database is locked` under heavy sync | `CCDASH_SQLITE_BUSY_TIMEOUT_MS` | Default 30000; raise to 60000+ if still hitting |
| Frequent relink on unchanged data | `CCDASH_LINKING_LOGIC_VERSION` | Leave at 1 unless the link logic has been updated |
| Frontend tab memory growth | live transport toggles | Disable `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` on long-running tabs |

See also: [`docs/guides/query-cache-tuning-guide.md`](./guides/query-cache-tuning-guide.md) and [`docs/sync-observability-and-audit.md`](./sync-observability-and-audit.md).

## Full Configuration Reference

All backend variables are read in [`backend/config.py`](../backend/config.py); frontend flags are read at Vite bundle time. The `.env.example` file at the repo root contains inline defaults and recommendations for every variable below.

### Server / transport

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_BACKEND_HOST` | `127.0.0.1` | Host used by startup scripts |
| `CCDASH_BACKEND_PORT` | `8000` | Port used by startup scripts |
| `CCDASH_HOST` | `0.0.0.0` | FastAPI bind host |
| `CCDASH_PORT` | `8000` | FastAPI bind port |
| `CCDASH_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite proxy target for `/api` |
| `CCDASH_FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allowed origin |
| `CCDASH_PYTHON` | — | Explicit Python interpreter override |
| `CCDASH_API_BEARER_TOKEN` | — | Optional bearer token required on API requests |

### Database + storage

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_DB_BACKEND` | `sqlite` | `sqlite` or `postgres` |
| `CCDASH_DB_PATH` | `.ccdash.db` | SQLite file path |
| `CCDASH_DATABASE_URL` | — | PostgreSQL connection URL |
| `CCDASH_SQLITE_BUSY_TIMEOUT_MS` | `30000` | SQLite busy-timeout (ms); floor 1000 |
| `CCDASH_STORAGE_PROFILE` | `local` | `local` or `enterprise` |
| `CCDASH_STORAGE_SHARED_POSTGRES` | `false` | Enables shared-enterprise posture |
| `CCDASH_STORAGE_ISOLATION_MODE` | `dedicated` | `dedicated`, `schema`, or `tenant` |
| `CCDASH_STORAGE_SCHEMA` | `ccdash` | Schema name for shared-enterprise |
| `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` | `false` | Optional filesystem ingest in enterprise |

### Project selection + workspace paths

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_ACTIVE_PROJECT` | — | Project slug to activate at boot |
| `CCDASH_PROJECT_ROOT` | repo root | Override resolved project root |
| `CCDASH_DATA_DIR` | `examples/skillmeat` | Base data directory |
| `CCDASH_CLAUDE_PROJECTS_ROOT` | — | Claude projects discovery root |
| `CCDASH_CODEX_SESSIONS_ROOT` | — | Codex sessions discovery root |
| `CCDASH_SESSION_DISCOVERY_ROOT` | — | Generic session discovery root |
| `CCDASH_INTEGRATIONS_SETTINGS_FILE` | `.ccdash-integrations.json` | Integrations settings file |
| `CCDASH_REPO_WORKSPACE_CACHE_DIR` | `.ccdash-repo-cache` | Repo workspace cache |
| `CCDASH_TEST_RESULTS_DIR` | — | Override path for test result ingestion |
| `CCDASH_SESSION_MAPPINGS_FILE` | — | JSON file with session-mapping overrides |
| `CCDASH_SESSION_MAPPINGS_JSON` | — | Inline JSON session-mapping overrides |

### Feature gates (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_TEST_VISUALIZER_ENABLED` | `false` | Global gate for `/api/tests/*` and `/tests` |
| `CCDASH_INTEGRITY_SIGNALS_ENABLED` | `false` | Global gate for integrity signal features |
| `CCDASH_LIVE_TEST_UPDATES_ENABLED` | `false` | Backend gate for test live invalidation |
| `CCDASH_SEMANTIC_MAPPING_ENABLED` | `false` | Backend gate for semantic mapping |
| `CCDASH_SKILLMEAT_INTEGRATION_ENABLED` | `true` | Enables SkillMeat cache/sync endpoints |
| `CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED` | `true` | Historical stack recommendations |
| `CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED` | `true` | Workflow intelligence endpoints |
| `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED` | `true` | Attribution analytics and payloads |
| `CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED` | `true` | Session block insights |
| `CCDASH_LAUNCH_PREP_ENABLED` | `false` | Launch preparation surfaces |
| `CCDASH_PLANNING_CONTROL_PLANE_ENABLED` | `true` | Planning control plane surfaces |

### Frontend live rollout

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_CCDASH_LIVE_EXECUTION_ENABLED` | `true` | Stream-first execution updates |
| `VITE_CCDASH_LIVE_SESSIONS_ENABLED` | `true` | Stream-first session invalidation |
| `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` | `false` | Append-first transcript deltas |
| `VITE_CCDASH_LIVE_FEATURES_ENABLED` | `false` | Feature board/modal live invalidation |
| `VITE_CCDASH_LIVE_TESTS_ENABLED` | `false` | Test visualizer live invalidation |
| `VITE_CCDASH_LIVE_OPS_ENABLED` | `false` | Ops panel live invalidation |

### Startup + live tuning (performance-sensitive)

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_STARTUP_SYNC_LIGHT_MODE` | `true` | Light-mode first pass at startup |
| `CCDASH_STARTUP_SYNC_DELAY_SECONDS` | `2` | Delay before startup sync begins |
| `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` | `true` | Deferred heavier link rebuild |
| `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS` | `45` | Delay before deferred rebuild |
| `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS` | `false` | Capture analytics during deferred rebuild |
| `CCDASH_LINKING_LOGIC_VERSION` | `1` | Bump to force full relink |
| `CCDASH_ANALYTICS_SNAPSHOT_INTERVAL_SECONDS` | `900` | Analytics snapshot cadence |
| `CCDASH_LIVE_REPLAY_BUFFER_SIZE` | `200` | Replay buffer per live topic |
| `CCDASH_LIVE_HEARTBEAT_SECONDS` | `15` | SSE heartbeat cadence |
| `CCDASH_LIVE_MAX_PENDING_EVENTS` | `100` | Max pending events before coarse invalidation |

### Agent query cache

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_QUERY_CACHE_TTL_SECONDS` | `60` | Cache lifetime. `0` disables. |
| `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` | `300` | Worker warmer interval. `0` disables. |

### CLI + worker

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_TIMEOUT` | `30` | Standalone `ccdash` CLI HTTP timeout |
| `CCDASH_TARGET` | — | Active CLI target name |
| `CCDASH_WORKER_PROJECT_ID` | — | Bind worker to a resolvable project id before hosted startup |
| `CCDASH_WORKER_PROBE_HOST` | `127.0.0.1` | Worker readiness probe host |
| `CCDASH_WORKER_PROBE_PORT` | `9465` | Worker readiness probe port |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_OTEL_ENABLED` | `false` | Enable OpenTelemetry export |
| `CCDASH_OTEL_ENDPOINT` | `http://localhost:4318` | OTLP endpoint |
| `CCDASH_OTEL_SERVICE_NAME` | `ccdash-backend` | Service name reported to OTel |
| `CCDASH_PROM_PORT` | `9464` | Prometheus scrape port |

### Telemetry exporter

See [`docs/guides/telemetry-exporter-guide.md`](./guides/telemetry-exporter-guide.md) for full semantics.

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_TELEMETRY_EXPORT_ENABLED` | `false` | Master switch |
| `CCDASH_SAM_ENDPOINT` | — | SAM ingestion URL |
| `CCDASH_SAM_API_KEY` | — | SAM bearer token |
| `CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS` | `900` | Export cadence (min 60) |
| `CCDASH_TELEMETRY_EXPORT_BATCH_SIZE` | `50` | Rows per push (1-500) |
| `CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS` | `30` | Outbound request timeout |
| `CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE` | `10000` | Pending-row cap |
| `CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS` | `30` | Synced-row retention |
| `CCDASH_TELEMETRY_ALLOW_INSECURE` | `false` | Allow plaintext SAM endpoints |
| `CCDASH_SAM_ARTIFACT_TELEMETRY_ENABLED` | `false` | Optional artifact telemetry channel |
| `CCDASH_VERSION` | `0.1.0` | Version emitted in payloads |

### GitHub integration

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_GITHUB_TOKEN` | — | GitHub API token for repo-backed projects |
| `CCDASH_GITHUB_USERNAME` | — | GitHub username (optional convenience) |

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
