# Runtime Deployment Examples

This directory contains repo-shipped operator examples for the split CCDash hosted topology.

These examples mirror the runtime contract that the codebase ships today:

- frontend is a separate process
- API serves `backend.runtime.bootstrap_api:app`
- worker serves background jobs through `python -m backend.worker`

These files are examples, not a full deployment product. They do not provision TLS, a hardened public edge, image publishing, secrets distribution, or external supervision beyond the example units and compose file shown here.

## Canonical Topology

| Role | Canonical command | Responsibility |
| --- | --- | --- |
| frontend | `npm run start:frontend` | serves the built frontend bundle through the repo's current `vite preview` helper |
| api | `backend/.venv/bin/python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port 8000` | hosted HTTP API only |
| worker | `backend/.venv/bin/python -m backend.worker` | startup sync, refresh, telemetry export, scheduled jobs, and worker probe server |

Use `backend.main:app` and `npm run dev` only for local-convenience workflows. They are not the hosted API posture.

## Probe Surfaces

The examples assume the probe surfaces the runtime exposes today:

- API liveness: `GET /api/health/live`
- API readiness: `GET /api/health/ready`
- API detail: `GET /api/health/detail`
- Worker liveness: `GET http://127.0.0.1:9465/livez`
- Worker readiness: `GET http://127.0.0.1:9465/readyz`
- Worker detail: `GET http://127.0.0.1:9465/detailz`

The worker probe host and port default to `127.0.0.1:9465`. Override them with `CCDASH_WORKER_PROBE_HOST` and `CCDASH_WORKER_PROBE_PORT` when your supervisor layout needs a different binding.

## Hosted Smoke Contract

The repo now ships a repeatable smoke flow for the hosted compose example:

1. Edit [`compose.hosted.env.example`](/Users/miethe/dev/homelab/development/CCDash/deploy/runtime/compose.hosted.env.example) and replace `CCDASH_WORKER_PROJECT_ID` with a project id that the workspace registry can resolve.
2. Validate the rendered compose contract:

```bash
npm run docker:hosted:smoke:config
```

3. Start the split stack:

```bash
npm run docker:hosted:smoke:up
npm run docker:hosted:smoke:ps
```

4. Validate runtime startup, probes, and migration state:

```bash
npm run docker:hosted:smoke:probes
```

This asserts:

- frontend returns `200`
- `GET /api/health/ready` is ready
- `GET /api/health/detail` reports `profile=api`, `migrationStatus=applied`, and `jobsEnabled=false`
- `GET /readyz` succeeds on the worker probe port
- `GET /detailz` reports `runtimeProfile=worker` and a bound worker project id

5. Validate one representative background-job control path:

```bash
npm run docker:hosted:smoke:job
```

This enables the telemetry exporter in settings and calls `POST /api/telemetry/export/push-now`. In a fresh smoke stack the expected result is usually `success=true` with `batchSize=0`, which proves the worker-owned exporter path is configured and callable without claiming a real external sink.

6. Validate the shipped CLI and MCP adapters:

```bash
npm run docker:hosted:smoke:cli-contract
npm run docker:hosted:smoke:mcp-contract
```

These run the repo's lightweight command/tool harnesses inside the API container. They are adapter-contract checks, not a claim that the stack includes a standalone global `ccdash-cli` install.

7. Tear the stack down when you are done:

```bash
npm run docker:hosted:smoke:down
```

Convenience wrapper:

```bash
npm run docker:hosted:smoke:validate
```

## Environment Ownership

These examples split environment variables by runtime role. Shared values may live in more than one environment file, but runtime-specific values should only be injected where they are actually used.

| Variable | Role | Notes |
| --- | --- | --- |
| `CCDASH_STORAGE_PROFILE` | api, worker | keep `enterprise` for hosted smoke |
| `CCDASH_DB_BACKEND` | api, worker | keep `postgres` for hosted smoke |
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
| `docker:hosted:smoke:job` returns `configured=false` or `envLocked=true` | telemetry exporter env is incomplete or disabled | set `CCDASH_TELEMETRY_EXPORT_ENABLED=true`, `CCDASH_SAM_ENDPOINT`, and `CCDASH_SAM_API_KEY` |
| `docker:hosted:smoke:job` returns a retry or abandoned error with non-zero batch size | the smoke stack has real queued telemetry rows but the sink is not valid | point the exporter at a real sink or clear the queue before rerunning |
| CLI or MCP contract checks fail | the adapter surface drifted from the shipped tests | inspect the failing pytest output in the API container before changing operator docs |

## Shipped Examples

- `compose.hosted.yml`
- `systemd/ccdash-api.service`
- `systemd/ccdash-worker.service`
- `systemd/ccdash-frontend.service`
- `supervisor/ccdash.conf`

The frontend examples intentionally use `npm run start:frontend`, which currently maps to `vite preview --host 0.0.0.0 --port 3000`. Treat that as a repo-aligned process-manager example, not as a claim that the repo ships a hardened public edge server.

The supervisor example uses `/bin/sh -lc` to source env files because supervisord does not have a native `EnvironmentFile=` equivalent like systemd.
