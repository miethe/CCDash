# Runtime Deployment Examples

This directory contains repo-shipped operator examples for the canonical container deployment contract.

The compose file at `deploy/runtime/compose.yaml` is the primary deployment manifest. It defines these composable profiles:

- `local` for the single-container SQLite path
- `enterprise` for split API and worker containers
- `postgres` for the bundled `postgres:17-alpine` service layered on top of `enterprise`
- `live-watch` for an opt-in watcher worker layered on top of `enterprise`

These examples are operator-focused, not a full deployment product. They do not provision TLS, secrets distribution, registry publication automation, or external supervision beyond the example units and compose file shown here.

For hosted auth provider rollout, RBAC bootstrap expectations, lockout prevention, and rollback commands, see `docs/guides/shared-auth-rbac-sso-operator-guide.md`.

## Canonical Compose Contract

| Profile | Services | Typical command |
| --- | --- | --- |
| `local` | backend + frontend | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local up --build` |
| `enterprise` | api + worker + frontend | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise up --build` |
| `enterprise` + `postgres` | api + worker + frontend + postgres | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres up --build` |
| `enterprise` + `postgres` + `live-watch` | api + worker + worker-watch + frontend + postgres | `docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch up --build` |

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
- Watcher worker liveness: `GET http://127.0.0.1:9466/livez`
- Watcher worker readiness: `GET http://127.0.0.1:9466/readyz`
- Watcher worker detail: `GET http://127.0.0.1:9466/detailz`

The worker probe host and port default to `127.0.0.1:9465`. Override them with `CCDASH_WORKER_PROBE_HOST` and `CCDASH_WORKER_PROBE_PORT` when your supervisor layout needs a different binding.

The watcher worker uses the same probe endpoints on a separate default port, `9466`, through `CCDASH_WORKER_WATCH_PROBE_HOST` and `CCDASH_WORKER_WATCH_PROBE_PORT`. Keep the default worker and watcher worker on distinct ports when they co-run.

When `worker` and `worker-watch` co-run, only the watcher worker should own startup filesystem sync. Compose defaults `CCDASH_WORKER_STARTUP_SYNC_ENABLED=false` and `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true` so both processes do not replace the same transcript rows concurrently.

## Live Watcher Worker

The `worker-watch` service is an opt-in enterprise worker for live filesystem ingest. It is intended to co-run with the default `worker` service: the default worker keeps scheduled jobs on probe port `9465`, while `worker-watch` owns filesystem watching and startup filesystem sync on probe port `9466`.

Start the bundled Postgres enterprise stack with live watching:

```bash
docker compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch up --build
```

`worker-watch` binds one project per worker process in v1. Set `CCDASH_WORKER_WATCH_PROJECT_ID` to a project id that exists in the mounted project registry; it falls back to `CCDASH_WORKER_PROJECT_ID` when unset. To watch more than one project, run another watcher worker instance with a different project id and a different probe port.

Required read-only ingest mounts:

| Mount | Default env | Container target | Why it is required |
| --- | --- | --- | --- |
| Project registry | `CCDASH_PROJECTS_FILE=../../projects.json` | `/app/projects.json` | Resolves `CCDASH_WORKER_PROJECT_ID` to a workspace path. |
| Workspace root | `CCDASH_WORKSPACE_HOST_ROOT=../../..` | `CCDASH_WORKSPACE_CONTAINER_ROOT=/workspace` | Lets workers read project docs and session files referenced by the registry. |
| Claude home | `CCDASH_CLAUDE_HOME=~/.claude` | `CCDASH_CLAUDE_CONTAINER_HOME=/home/ccdash/.claude` | Provides Claude Code project/session metadata for watcher ingest. |
| Codex home | `CCDASH_CODEX_HOME=~/.codex` | `CCDASH_CODEX_CONTAINER_HOME=/home/ccdash/.codex` | Provides Codex session metadata for watcher ingest. |

### Env-Driven Optional Mounts

`compose.yaml` also exposes six optional read-only bind-mount slots:

| Slot | Host env | Container env |
| --- | --- | --- |
| 1 | `CCDASH_EXTRA_MOUNT_1_HOST` | `CCDASH_EXTRA_MOUNT_1_CONTAINER` |
| 2 | `CCDASH_EXTRA_MOUNT_2_HOST` | `CCDASH_EXTRA_MOUNT_2_CONTAINER` |
| 3 | `CCDASH_EXTRA_MOUNT_3_HOST` | `CCDASH_EXTRA_MOUNT_3_CONTAINER` |
| 4 | `CCDASH_EXTRA_MOUNT_4_HOST` | `CCDASH_EXTRA_MOUNT_4_CONTAINER` |
| 5 | `CCDASH_EXTRA_MOUNT_5_HOST` | `CCDASH_EXTRA_MOUNT_5_CONTAINER` |
| 6 | `CCDASH_EXTRA_MOUNT_6_HOST` | `CCDASH_EXTRA_MOUNT_6_CONTAINER` |

Unused slots default to checked-in empty directories under `deploy/runtime/empty-mounts/`, so operators can leave them unset and still run `compose config`.

Use optional slots when a project registry entry references a path outside the normal workspace, Claude home, or Codex home roots. If `projects.json` contains absolute host paths, set the container target to the same absolute path:

```env
CCDASH_EXTRA_MOUNT_1_HOST=/srv/customer-a/workspace
CCDASH_EXTRA_MOUNT_1_CONTAINER=/srv/customer-a/workspace
CCDASH_EXTRA_MOUNT_2_HOST=/var/lib/agent-sessions/customer-a
CCDASH_EXTRA_MOUNT_2_CONTAINER=/var/lib/agent-sessions/customer-a
```

This keeps path resolution simple: the path in `projects.json` is also the path the worker sees inside the container.

### Per-Watcher Env Files

For one watcher, keep the project id and mount variables in `deploy/runtime/.env`. For multiple watcher workers, keep one small env overlay per watcher and pass it after the shared env file so watcher-specific values win:

```bash
docker compose \
  --env-file deploy/runtime/.env \
  --env-file deploy/runtime/watchers/ccdash.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch up --build
```

The repo includes `deploy/runtime/watchers/ccdash.env.example` as a concrete example for this CCDash checkout.

For multi-project deployments, prefer mounting a stable superset root shared by all watcher containers, then vary only `CCDASH_WORKER_WATCH_PROJECT_ID` and `CCDASH_WORKER_WATCH_PROBE_PORT` per watcher. When projects live on unrelated host roots, use the optional mount slots in each watcher's env overlay. Do not use Compose `--scale worker-watch=N` for v1: each watcher needs a distinct project id and probe port, which requires distinct service/env configuration.

On macOS Docker Desktop, bind-mounted filesystem events can be unreliable. If `worker-watch` starts but does not see new JSONL changes, set `WATCHFILES_FORCE_POLLING=true` in `deploy/runtime/.env` and restart it. The shipped compose file passes this variable only to `worker-watch`; keep polling scoped there because it is a compatibility mode for Docker Desktop file sharing, not the default Linux path.

## Enterprise Live Ingest Smoke

Use this smoke when validating `TEST-004` for a real project. It assumes `deploy/runtime/.env` contains a resolvable `CCDASH_WORKER_PROJECT_ID`, the project registry and session roots are mounted read-only, and the bundled Postgres profile is in use.

Start the stack in the background:

```bash
COMPOSE="docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch"
$COMPOSE up --build -d
```

Expected probes:

```bash
curl -fsS http://localhost:8000/api/health/ready | python3 -m json.tool
curl -fsS http://localhost:9465/readyz | python3 -m json.tool
curl -fsS http://localhost:9466/readyz | python3 -m json.tool

curl -fsS http://localhost:9465/detailz | python3 -c 'import json,sys; p=json.load(sys.stdin); print(json.dumps({"runtimeProfile":p.get("runtimeProfile"), "ready":p.get("ready",{}).get("status"), "watcher":p.get("detail",{}).get("watcher"), "workerWatcherDisabled":p.get("detail",{}).get("worker",{}).get("watcherDisabled")}, indent=2))'

curl -fsS http://localhost:9466/detailz | python3 -c 'import json,sys; p=json.load(sys.stdin); d=p.get("detail",{}); w=d.get("watcher",{}); wp=d.get("worker",{}); print(json.dumps({"runtimeProfile":p.get("runtimeProfile"), "ready":p.get("ready",{}).get("status"), "watcherState":w.get("state"), "watchPathCount":w.get("watchPathCount"), "lastChangeSyncAt":w.get("lastChangeSyncAt"), "lastChangeCount":w.get("lastChangeCount"), "lastSyncStatus":w.get("lastSyncStatus"), "workerWatcherDisabled":wp.get("watcherDisabled"), "syncLagSeconds":wp.get("syncLagSeconds"), "backpressure":wp.get("backpressure")}, indent=2))'

curl -fsS http://localhost:8000/api/health/detail | python3 -c 'import json,sys; p=json.load(sys.stdin); f=p.get("detail",{}).get("liveFanout",{}); print(json.dumps({"mode":f.get("mode"), "running":f.get("running"), "connected":f.get("connected"), "errorCount":f.get("errorCount"), "listener":f.get("listener"), "recentErrors":f.get("recentErrors")}, indent=2))'
```

Expected values:

- API and both workers report readiness `pass`.
- Default `worker` detail reports watcher state `not_expected` and `workerWatcherDisabled=true`.
- `worker-watch` detail reports `runtimeProfile=worker-watch`, watcher state `running`, `watchPathCount > 0`, `workerWatcherDisabled=false`, and no backpressure backlog.
- API detail reports live fanout `mode=listen`, `running=true`, `connected=true`, and a stable `errorCount`. Recent listener errors or increasing `listener.publishErrors` mean Postgres fanout is degraded; persistence can still succeed, but browser SSE delivery may fall back to REST refresh.

Record DB counts before the append:

```bash
$COMPOSE exec -T postgres psql -U ccdash -d ccdash \
  -c "select count(*) as sessions_total from sessions; select count(*) as messages_total from session_messages;"
```

Append one valid JSONL message to a session file that belongs to `CCDASH_WORKER_PROJECT_ID`. Prefer an active Claude Code or Codex session file under the mounted session root. Do not append to a production transcript unless you are intentionally testing against disposable data.

```bash
SMOKE_SESSION_FILE=/absolute/host/path/to/watched/session.jsonl
python3 - "$SMOKE_SESSION_FILE" <<'PY'
import json
import sys
import uuid
from datetime import datetime, timezone

path = sys.argv[1]
entry = {
    "type": "user",
    "uuid": str(uuid.uuid4()),
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "message": {
        "role": "user",
        "content": "CCDash live ingest smoke append.",
    },
}
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
PY
```

Wait a few seconds, then confirm the watcher saw and synced the change:

```bash
curl -fsS http://localhost:9466/detailz | python3 -c 'import json,sys; w=json.load(sys.stdin).get("detail",{}).get("watcher",{}); print(json.dumps({"lastChangeSyncAt":w.get("lastChangeSyncAt"), "lastChangeCount":w.get("lastChangeCount"), "lastSyncStatus":w.get("lastSyncStatus"), "lastSyncError":w.get("lastSyncError")}, indent=2))'

$COMPOSE exec -T postgres psql -U ccdash -d ccdash \
  -c "select count(*) as sessions_total from sessions; select count(*) as messages_total from session_messages;"
```

Expected result: `lastSyncStatus=succeeded`, `lastChangeSyncAt` advances, and `messages_total` increases. If a brand-new session file was added instead of appending to an existing transcript, `sessions_total` should increase too.

Stop the smoke stack when finished:

```bash
$COMPOSE down
```

## Environment Ownership

These examples split environment variables by runtime role. Shared values may live in more than one environment file, but runtime-specific values should only be injected where they are actually used.

| Variable | Role | Notes |
| --- | --- | --- |
| `CCDASH_STORAGE_PROFILE` | backend, api, worker | `local` for the local profile; `enterprise` for the hosted profiles |
| `CCDASH_DB_BACKEND` | backend, api, worker | `sqlite` for the local profile; `postgres` for the hosted profiles |
| `CCDASH_DATABASE_URL` | api, worker | built from the Postgres values in the compose example |
| `CCDASH_PROJECT_ROOT` | api, worker | repo root inside the container; defaults to `/app` |
| `CCDASH_API_BEARER_TOKEN` | api | protects `/api/v1/*` only |
| `CCDASH_AUTH_PROVIDER` | api | auth provider selector: `static_bearer` by default for API runtime, or `local`, `clerk`, `oidc` |
| `CCDASH_LOCAL_NO_AUTH_ENABLED` | api, local | explicit local no-auth switch; local/test default to no-auth, hosted API requires explicit opt-in for `CCDASH_AUTH_PROVIDER=local` |
| `CCDASH_CLERK_PUBLISHABLE_KEY` / `CCDASH_CLERK_SECRET_KEY` / `CCDASH_CLERK_JWT_KEY` | api | Clerk hosted token validation; browser redirect is expected through the Clerk frontend SDK/id-token path |
| `CCDASH_OIDC_ISSUER` / `CCDASH_OIDC_AUDIENCE` / `CCDASH_OIDC_CLIENT_ID` / `CCDASH_OIDC_CLIENT_SECRET` / `CCDASH_OIDC_CALLBACK_URL` / `CCDASH_OIDC_JWKS_URL` | api | generic OIDC hosted token validation; OAuth authorization-code exchange is not implemented |
| `CCDASH_SESSION_COOKIE_NAME` / `CCDASH_SESSION_COOKIE_SECURE` / `CCDASH_SESSION_COOKIE_SAMESITE` / `CCDASH_SESSION_COOKIE_DOMAIN` | api | hosted auth session cookie controls |
| `CCDASH_TRUSTED_PROXY_ENABLED` | api | enables proxy-aware hosted auth/session behavior when deployed behind a trusted reverse proxy |
| `CCDASH_FRONTEND_ORIGIN` | api | browser origin expected by the hosted API |
| `CCDASH_WORKER_PROJECT_ID` | worker | required; worker startup fails if the id cannot be resolved |
| `CCDASH_WORKER_PROBE_HOST` | worker | probe listener bind host |
| `CCDASH_WORKER_PROBE_PORT` | worker | probe listener bind port |
| `CCDASH_WORKER_WATCH_PROBE_HOST` | worker-watch | watcher probe listener bind host; defaults to `0.0.0.0` in compose |
| `CCDASH_WORKER_WATCH_PROBE_PORT` | worker-watch | watcher probe listener bind port; defaults to `9466` to avoid `worker` port conflicts |
| `CCDASH_WORKER_WATCH_PROJECT_ID` | worker-watch | watcher project binding; falls back to `CCDASH_WORKER_PROJECT_ID` when unset |
| `CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED` | worker-watch | enables filesystem ingest for the watcher worker; defaults to `true` in compose |
| `CCDASH_WORKER_STARTUP_SYNC_ENABLED` | worker | disables startup filesystem sync for the standard worker when `worker-watch` owns ingest; defaults to `false` in compose |
| `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED` | worker-watch | enables startup filesystem sync for the watcher worker; defaults to `true` in compose |
| `CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED` | api, worker, worker-watch | controls inferred planning-status writes back to markdown; defaults to `false` for enterprise storage and `true` for local storage |
| `GIT_OPTIONAL_LOCKS` | api, worker, worker-watch | keep `0` when project repositories are mounted read-only so Git metadata reads do not try to refresh indexes |
| `WATCHFILES_FORCE_POLLING` | worker-watch | set to `true` on macOS Docker Desktop when bind-mount events do not reach the watcher |
| `CCDASH_EXTRA_MOUNT_N_HOST` / `CCDASH_EXTRA_MOUNT_N_CONTAINER` | api, worker, worker-watch | optional read-only bind slots for roots outside the shared workspace/home mounts |
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
| `worker-watch` exits during startup | `CCDASH_WORKER_PROJECT_ID` is unset, unresolved, or not present in mounted `projects.json` | choose a real project id and confirm `CCDASH_PROJECTS_FILE` points at the expected registry |
| `worker-watch` detail shows no paths or logs "nothing to monitor" | the workspace root, `.claude`, or `.codex` mount is missing, empty, or mounted at a path that does not match the project registry | check `CCDASH_WORKSPACE_*`, `CCDASH_CLAUDE_*`, and `CCDASH_CODEX_*`; preserve read-only mounts but make the host paths visible to Docker |
| `worker` and `worker-watch` cannot both publish probes | both workers are configured with the same probe port | keep `CCDASH_WORKER_PROBE_PORT=9465` and `CCDASH_WORKER_WATCH_PROBE_PORT=9466`, or assign another unique watcher port |
| `worker-watch` starts on macOS Docker Desktop but does not react to file changes | bind-mounted filesystem events are not delivered by Docker Desktop file sharing | restart the watcher with `WATCHFILES_FORCE_POLLING=true` passed into the container |

## Shipped Examples

- `compose.hosted.yml`
- `compose.yaml`
- `systemd/ccdash-api.service`
- `systemd/ccdash-worker.service`
- `systemd/ccdash-frontend.service`
- `supervisor/ccdash.conf`

The frontend examples intentionally use `npm run start:frontend`, which currently maps to `vite preview --host 0.0.0.0 --port 3000`. Treat that as a repo-aligned process-manager example, not as a claim that the repo ships a hardened public edge server.

The supervisor example uses `/bin/sh -lc` to source env files because supervisord does not have a native `EnvironmentFile=` equivalent like systemd.

## Rootless Podman Notes

The compose contract is validated against rootless Podman 4.6+ and podman-compose 1.5+. The following operator notes are required for parity with `docker compose`:

### Podman machine memory (macOS / Windows)

The default `podman machine` allocation is 2 GiB, which is not enough RAM for the frontend `vite build` step. The build will OOM (`Killed`, exit 137) at the `computing gzip size` stage. Bump the VM to at least 4 GiB before running `podman-compose ... up --build`:

```bash
podman machine stop
podman machine set --memory 4096
podman machine start
```

On a fresh install, also run `podman machine start` first — `podman machine list` will show `Last Up: Never` until that step is performed.

### `HEALTHCHECK` ignored on OCI image format

`podman build` warns: `HEALTHCHECK is not supported for OCI image format and will be ignored. Must use docker format`. The Dockerfile-level `HEALTHCHECK` is therefore inert under Podman, but the **compose-level** `healthcheck:` blocks defined in `compose.yaml` are honored by podman-compose, so end-to-end health gating still works. If you need the image-embedded healthcheck under Podman, build with `podman build --format=docker ...`.

### SELinux `:Z` bind-mount label

On SELinux-enforcing hosts (RHEL/Fedora/CentOS Stream), bind-mounted host paths must be relabeled or the container will see `Permission denied` even when UIDs match. Append `:Z` (private label, single-container) or `:z` (shared label, multi-container) to bind-mount sources:

```yaml
volumes:
  # Single-container access — relabel exclusively for this container
  - /opt/ccdash/projects.json:/app/projects.json:Z
  # Shared between containers — shared label
  - /opt/ccdash/data:/var/lib/ccdash:z
```

Named volumes (the default for `ccdash-local-data` and `ccdash-postgres` in `compose.yaml`) do not require `:Z`; Podman manages their SELinux labels automatically.

`:Z` is a no-op on non-SELinux hosts (Debian/Ubuntu, macOS Podman machine, WSL2) and is safe to leave in place across platforms. This was not live-tested on this Phase 5 host (Darwin / no SELinux available); the syntax is documented from the Podman upstream contract.

### External Postgres under `podman-compose` 1.5.0

`podman-compose` 1.5.0 does not honor `depends_on.<svc>.required: false` and aborts with `KeyError: 'postgres'` when the `enterprise` profile is brought up against an externally-managed Postgres (`CCDASH_DATABASE_URL` pointing off-stack). Layer `deploy/runtime/compose.external-postgres.yaml` to strip the optional postgres dependency:

```bash
podman-compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  -f deploy/runtime/compose.external-postgres.yaml \
  --profile enterprise up
```

Do NOT layer this override when running with the bundled `postgres` profile — it intentionally removes the dependency edge.

### `podman-compose` build-context size

`podman-compose` 1.5 streams the build context through an in-memory tar; large or polluted contexts (e.g. `data/`, `node_modules/`, `.git/`, local virtualenvs) cause `archive/tar: write too long`. The repo ships a `.dockerignore` that excludes these paths. If you fork the build context, keep the ignore list intact.

### Named volume UID mapping

Rootless Podman maps the in-container UID (e.g. `1000`) into the user namespace via `/etc/subuid`. Named volumes created by podman-compose are owned by that mapped UID and are writable from the container without further configuration. Verified path on Phase 5 smoke: `/var/lib/ccdash` mounted as named volume `ccdash-local-data` is owned by `ccdash:ccdash` (UID/GID 1000) inside the container, and the SQLite cache (`ccdash.db`, `.db-shm`, `.db-wal`) is writable.

## Image Tagging Convention

If you publish the container images to a registry, use the following tags:

- `ghcr.io/ccdash/backend:<version>`
- `ghcr.io/ccdash/frontend:<version>`

This is a documented convention only. Registry publication and automated tag promotion are still out of scope for this release.
