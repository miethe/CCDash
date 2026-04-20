# Runtime Deployment Examples

This directory contains repo-shipped operator examples for the canonical container deployment contract.

The compose file at `deploy/runtime/compose.yaml` is the primary deployment manifest. It defines these composable profiles:

- `local` for the single-container SQLite path
- `enterprise` for split API and worker containers
- `postgres` for the bundled `postgres:17-alpine` service layered on top of `enterprise`

These examples are operator-focused, not a full deployment product. They do not provision TLS, secrets distribution, registry publication automation, or external supervision beyond the example units and compose file shown here.

## Canonical Compose Contract

| Profile | Services | Typical command |
| --- | --- | --- |
| `local` | backend + frontend | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local up --build` |
| `enterprise` | api + worker + frontend | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise up --build` |
| `enterprise` + `postgres` | api + worker + frontend + postgres | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres up --build` |

The backend image is built from `deploy/runtime/Dockerfile` and honors `BUILD_UID` / `BUILD_GID` for rootless runs. The frontend image is built from `deploy/runtime/frontend/Dockerfile` and consumes `VITE_CCDASH_API_BASE_URL`, `CCDASH_API_UPSTREAM`, and `CCDASH_FRONTEND_PORT`.

Use `backend.main:app` and `npm run dev` only for local-convenience workflows. They are not the canonical container contract.

## Probe Surfaces

The container examples assume the probe surfaces the runtime exposes today:

- API liveness: `GET /api/health/live`
- API readiness: `GET /api/health/ready`
- API detail: `GET /api/health/detail`
- Worker liveness: `GET http://127.0.0.1:9465/livez`
- Worker readiness: `GET http://127.0.0.1:9465/readyz`
- Worker detail: `GET http://127.0.0.1:9465/detailz`

The worker probe host and port default to `127.0.0.1:9465`. Override them with `CCDASH_WORKER_PROBE_HOST` and `CCDASH_WORKER_PROBE_PORT` when your supervisor layout needs a different binding.

## Environment Ownership

These examples split environment variables by runtime role. Shared values may live in more than one environment file, but runtime-specific values should only be injected where they are actually used.

| Variable | Role | Notes |
| --- | --- | --- |
| `CCDASH_STORAGE_PROFILE` | backend, api, worker | `local` for the local profile; `enterprise` for the hosted profiles |
| `CCDASH_DB_BACKEND` | backend, api, worker | `sqlite` for the local profile; `postgres` for the hosted profiles |
| `CCDASH_DATABASE_URL` | api, worker | built from the Postgres values in the compose example |
| `CCDASH_PROJECT_ROOT` | api, worker | repo root inside the container; defaults to `/app` |
| `CCDASH_API_BEARER_TOKEN` | api | protects `/api/v1/*` only |
| `CCDASH_FRONTEND_ORIGIN` | api | browser origin expected by the hosted API |
| `CCDASH_WORKER_PROJECT_ID` | worker | required; worker startup fails if the id cannot be resolved |
| `CCDASH_WORKER_PROBE_HOST` | worker | probe listener bind host |
| `CCDASH_WORKER_PROBE_PORT` | worker | probe listener bind port |
| `CCDASH_TELEMETRY_EXPORT_ENABLED` | worker | must be `true` for the smoke exporter path |
| `CCDASH_SAM_ENDPOINT` | worker | placeholder sink is acceptable for the zero-queue smoke path |
| `CCDASH_SAM_API_KEY` | worker | required whenever telemetry export is enabled |
| `CCDASH_TELEMETRY_ALLOW_INSECURE` | worker | keep `false` unless you intentionally target an HTTP sink |
| `CCDASH_API_UPSTREAM` | frontend | nginx upstream for `/api` |
| `CCDASH_FRONTEND_PORT` | frontend | container and host port for the frontend example |
| `VITE_CCDASH_API_BASE_URL` | frontend build arg | defaults to `/api` |

## Failure Modes

Common hosted-smoke failures and what they mean:

| Symptom | Likely cause | Operator action |
| --- | --- | --- |
| `worker` exits during startup | `CCDASH_WORKER_PROJECT_ID` is unset or unresolved | choose a real project id and rerun |
| API readiness fails | migrations or DB connectivity failed | inspect `docker compose logs api postgres` and correct the Postgres config before retrying |
| worker readiness fails | worker binding, startup sync, or probe binding failed | inspect `docker compose logs worker`; confirm `CCDASH_WORKER_PROBE_*` and project binding |
| telemetry exporter checks fail in an enterprise stack | telemetry exporter env is incomplete or disabled | set `CCDASH_TELEMETRY_EXPORT_ENABLED=true`, `CCDASH_SAM_ENDPOINT`, and `CCDASH_SAM_API_KEY` |
| telemetry exporter checks return a retry or abandoned error with non-zero batch size | the stack has real queued telemetry rows but the sink is not valid | point the exporter at a real sink or clear the queue before rerunning |
| CLI or MCP contract checks fail | the adapter surface drifted from the shipped tests | inspect the failing pytest output in the API container before changing operator docs |

## Shipped Examples

- `compose.hosted.yml`
- `compose.yaml`
- `systemd/ccdash-api.service`
- `systemd/ccdash-worker.service`
- `systemd/ccdash-frontend.service`
- `supervisor/ccdash.conf`

The frontend examples intentionally use `npm run start:frontend`, which currently maps to `vite preview --host 0.0.0.0 --port 3000`. Treat that as a repo-aligned process-manager example, not as a claim that the repo ships a hardened public edge server.

The supervisor example uses `/bin/sh -lc` to source env files because supervisord does not have a native `EnvironmentFile=` equivalent like systemd.

## Image Tagging Convention

If you publish the container images to a registry, use the following tags:

- `ghcr.io/ccdash/backend:<version>`
- `ghcr.io/ccdash/frontend:<version>`

This is a documented convention only. Registry publication and automated tag promotion are still out of scope for this release.
