# Runtime Deployment Examples

This directory contains operator examples for the split CCDash hosted topology.

It mirrors the current runtime contract already shipped in code:

- frontend is a separate process
- API serves `backend.runtime.bootstrap_api:app`
- worker serves background jobs through `python -m backend.worker`

These files are examples, not a full deployment product. They do not provision TLS, reverse proxying, secrets distribution, container images, or process supervision outside the shown units/programs.

## Canonical Topology

| Role | Canonical command | Responsibility |
| --- | --- | --- |
| frontend | `npm run start:frontend` | serves the built frontend bundle through the repo's current `vite preview` helper |
| api | `backend/.venv/bin/python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port 8000` | hosted HTTP API only |
| worker | `backend/.venv/bin/python -m backend.worker` | startup sync, refresh, telemetry export, scheduled jobs, and worker probe server |

Use `backend.main:app` and `npm run dev` only for local-convenience workflows. They are not the hosted API posture.

## Probe Surfaces

The examples assume the same probe surfaces the runtime exposes today:

- API liveness: `GET /api/health/live`
- API readiness: `GET /api/health/ready`
- API detail: `GET /api/health/detail`
- Worker liveness: `GET http://127.0.0.1:9465/livez`
- Worker readiness: `GET http://127.0.0.1:9465/readyz`
- Worker detail: `GET http://127.0.0.1:9465/detailz`

The worker probe host and port default to `127.0.0.1:9465`. Override them with `CCDASH_WORKER_PROBE_HOST` and `CCDASH_WORKER_PROBE_PORT` when your supervisor layout needs a different binding.

## Environment Ownership

These examples split environment variables by runtime role. Shared values may live in more than one environment file, but runtime-specific values should only be injected where they are actually used.

### Shared across API and worker

- `CCDASH_STORAGE_PROFILE=enterprise`
- `CCDASH_DB_BACKEND=postgres`
- `CCDASH_DATABASE_URL=postgresql://...`
- `CCDASH_STORAGE_SHARED_POSTGRES=true|false`
- `CCDASH_STORAGE_ISOLATION_MODE=dedicated|schema|tenant`
- `CCDASH_STORAGE_SCHEMA=ccdash`
- `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false`
- telemetry exporter tuning values when the worker needs them

### API only

- `CCDASH_API_BEARER_TOKEN`
- `CCDASH_BACKEND_HOST`
- `CCDASH_BACKEND_PORT`

### Worker only

- `CCDASH_WORKER_PROJECT_ID`
- `CCDASH_WORKER_PROBE_HOST`
- `CCDASH_WORKER_PROBE_PORT`

### Local only

- `CCDASH_DB_PATH`
- local filesystem/watcher inputs used by `backend.main:app` and `npm run dev`

## Shipped Examples

- `systemd/ccdash-api.service`
- `systemd/ccdash-worker.service`
- `systemd/ccdash-frontend.service`
- `supervisor/ccdash.conf`

The frontend examples intentionally use `npm run start:frontend`, which currently maps to `vite preview --host 0.0.0.0 --port 3000`. Treat that as a repo-aligned process-manager example, not as a claim that the repo ships a hardened public edge server.
The supervisor example uses `/bin/sh -lc` to source env files because supervisord does not have a native `EnvironmentFile=` equivalent like systemd.

## Example Rollout Order

1. Build frontend assets with `npm run build`.
2. Start the API process and wait for `GET /api/health/ready` to return success.
3. Start the worker process and confirm `GET /readyz` on the worker probe port returns success.
4. Start the frontend process behind the same reverse proxy or network boundary you use for the API.

## Validation Tips

- Confirm the API reports `profile=api`, `jobsEnabled=false`, and `runtimeJobBehavior=no_background_jobs`.
- Confirm the worker probe shows a configured binding and `runtimeProfile=worker`.
- Keep the frontend, API, and worker as separate restart units even when they share one machine.
