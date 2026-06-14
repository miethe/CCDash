# Containerized Deployment Quickstart

This is the preferred onboarding route for CCDash. It covers deploying with Docker Compose or Podman Compose using four composable profiles: `local` (single-container SQLite), `enterprise` (split API/worker), `postgres` (bundled Postgres service), and `live-watch` (watcher worker for enterprise live ingest).

For full runtime reference, probe endpoints, and environment variables, see `deploy/runtime/README.md`.

## Prerequisites

- Docker Compose v2 or `podman-compose` >= 1.2
- A checkout of this repository
- For rootless Podman on macOS/Windows: Podman machine with minimum 4 GiB RAM (frontend builds require it)

## Quick Start: Local Profile

The local profile runs a unified backend container with SQLite. Ideal for evaluation, development, and small deployments.

1. Copy the environment template:

```bash
cp deploy/runtime/.env.example deploy/runtime/.env
```

2. Start the stack:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local up --build
```

3. Access the UI at `http://localhost:3000` and API at `http://localhost:8000`.

4. Verify health:

```bash
curl http://localhost:8000/api/health/ready
curl http://localhost:3000/
```

What you get:
- Backend container with `CCDASH_STORAGE_PROFILE=local` and `CCDASH_DB_BACKEND=sqlite`
- Frontend nginx container on port 3000
- SQLite database persisted in named volume `ccdash-local-data`

## STEP 1 (Required Pre-Deploy): Prepare Projects For Containers

Every enterprise and live-watch deployment resolves projects from the mounted `projects.json` registry. The paths in that registry must be visible from inside the containers, not only on the host. A healthy API, worker, and Postgres stack can still show no sessions, plans, or features when the active project id points at a host-only path or a project different from the watcher binding.

**This step is required before starting any enterprise, postgres, or live-watch compose stack for the first time on a new host or a new project.** Running `container_project_onboarding.py` is the canonical way to create or update the registry entry and watcher env overlay atomically and reproducibly.

### Running the onboarding helper

`backend/scripts/container_project_onboarding.py` is a standalone CLI that prepares `projects.json` and optionally writes a per-watcher env overlay file. It does **not** start containers; container startup is controlled by `docker compose` separately.

```bash
python3 backend/scripts/container_project_onboarding.py \
  --projects-file projects.json \
  --project-id my-project \
  --name "My Project" \
  --root-container /workspace/my-project \
  --sessions-container /home/ccdash/.codex/sessions \
  --watcher-env deploy/runtime/watchers/my-project.env \
  --workspace-host-root /absolute/host/workspace \
  --workspace-container-root /workspace \
  --codex-home "$HOME/.codex" \
  --codex-container-home /home/ccdash/.codex
```

The helper upserts the project into the registry (creates the file if missing, merges into existing), sets it as `activeProjectId` by default, and writes a watcher env overlay ready for `--env-file` compose use. Run it again with the same `--project-id` to update an existing entry without removing other projects.

### Full flag reference

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--projects-file PATH` | No | `projects.json` | Path to the `projects.json` registry to create or update. |
| `--project-id ID` | No | slug of `--name` | Stable project id. Use a short, lowercase, hyphenated identifier; changing this after data is ingested requires a re-sync. |
| `--name TEXT` | **Yes** | — | Project display name shown in the UI. |
| `--description TEXT` | No | `""` | Optional project description. |
| `--repo-url URL` | No | `""` | Optional repository URL for display purposes. |
| `--root-container PATH` | **Yes** | — | Project root path as seen **inside** containers (e.g. `/workspace/my-project`). Must be a container-visible absolute path. |
| `--plan-docs PATH` | No | `docs/project_plans/` | Plan docs path relative to the project root for PRDs, implementation plans, and design specs. |
| `--sessions-container PATH` | No | `""` | Session JSONL directory as seen **inside** containers. Should be a project-scoped subdirectory rather than all of `~/.codex/sessions`. |
| `--progress PATH` | No | `progress` | Progress path relative to the project root for phase trackers and task files. |
| `--agent-platform LABEL` | No | `Claude Code` | Agent platform label. Repeatable to add multiple platforms: `--agent-platform "Claude Code" --agent-platform "Codex"`. |
| `--no-active` | No | off | Do not set this project as `activeProjectId`. Useful when adding a non-primary project to a multi-project registry. |
| `--watcher-env PATH` | No | — | If set, writes a watcher env overlay file at this path. Omit to print the overlay to stdout instead. Typical path: `deploy/runtime/watchers/<project-id>.env`. |
| `--watcher-probe-port PORT` | No | `9466` | Probe port value written into the watcher env overlay (`CCDASH_WORKER_WATCH_PROBE_PORT`). Increment by 1 for each additional watcher worker. |
| `--projects-file-for-env PATH` | No | `../../projects.json` | Value of `CCDASH_PROJECTS_FILE` written into the watcher env overlay. Use a host-visible path that compose can resolve at runtime. |
| `--workspace-host-root PATH` | No | — | `CCDASH_WORKSPACE_HOST_ROOT` in the watcher overlay. Host-side root that is bind-mounted at `--workspace-container-root`. |
| `--workspace-container-root PATH` | No | — | `CCDASH_WORKSPACE_CONTAINER_ROOT` in the watcher overlay. Container-side root (e.g. `/workspace`). |
| `--claude-home PATH` | No | — | `CCDASH_CLAUDE_HOME` in the watcher overlay. Host path to `.claude` directory. |
| `--claude-container-home PATH` | No | — | `CCDASH_CLAUDE_CONTAINER_HOME` in the watcher overlay. Container path where `.claude` is mounted. |
| `--codex-home PATH` | No | — | `CCDASH_CODEX_HOME` in the watcher overlay. Host path to `.codex` directory. |
| `--codex-container-home PATH` | No | — | `CCDASH_CODEX_CONTAINER_HOME` in the watcher overlay. Container path where `.codex` is mounted. |

### Example: single-project enterprise deployment with live watch

```bash
# 1. Prepare the registry and watcher env overlay.
python3 backend/scripts/container_project_onboarding.py \
  --projects-file projects.json \
  --project-id myrepo \
  --name "My Repo" \
  --root-container /workspace/myrepo \
  --sessions-container /home/ccdash/.codex/sessions/myrepo \
  --watcher-env deploy/runtime/watchers/myrepo.env \
  --watcher-probe-port 9466 \
  --projects-file-for-env /opt/ccdash/projects.json \
  --workspace-host-root /opt/ccdash/workspace \
  --workspace-container-root /workspace \
  --claude-home "$HOME/.claude" \
  --claude-container-home /home/ccdash/.claude \
  --codex-home "$HOME/.codex" \
  --codex-container-home /home/ccdash/.codex

# 2. Start the stack (now that the registry and overlay are ready).
docker compose \
  --env-file deploy/runtime/.env \
  --env-file deploy/runtime/watchers/myrepo.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch \
  up --build
```

### Example: adding a second project without changing the active project

```bash
python3 backend/scripts/container_project_onboarding.py \
  --projects-file projects.json \
  --project-id secondary-repo \
  --name "Secondary Repo" \
  --root-container /workspace/secondary-repo \
  --sessions-container /home/ccdash/.codex/sessions/secondary-repo \
  --no-active \
  --watcher-env deploy/runtime/watchers/secondary-repo.env \
  --watcher-probe-port 9467
```

Note: `worker-watch` binds one project id per worker process in v1. To ingest a second project live, run a second `worker-watch` container with a unique `CCDASH_WORKER_WATCH_PROJECT_ID` and probe port.

If you prepare `projects.json` manually, the minimum project entry is:

```json
{
  "activeProjectId": "my-project",
  "projects": [
    {
      "id": "my-project",
      "name": "My Project",
      "path": "/workspace/my-project",
      "description": "",
      "repoUrl": "",
      "agentPlatforms": ["Claude Code"],
      "planDocsPath": "docs/project_plans/",
      "sessionsPath": "/home/ccdash/.codex/sessions",
      "progressPath": "progress"
    }
  ]
}
```

For container deployments, prefer a stable project id. The standard worker uses `CCDASH_WORKER_PROJECT_ID`; `worker-watch` uses `CCDASH_WORKER_WATCH_PROJECT_ID`. In v1, a watcher worker binds one project id for the life of that container, so UI project switching does not rebind live ingest.

Path setup rules:

- `path` / `pathConfig.root`: container-visible project root, commonly below `CCDASH_WORKSPACE_CONTAINER_ROOT`.
- `planDocsPath`: relative directory for PRDs, implementation plans, and design specs.
- `progressPath`: relative directory for progress trackers and task files.
- `sessionsPath`: container-visible JSONL session root. A project-specific session directory is cheaper than all of `~/.codex/sessions` or all of `~/.claude/projects`.
- `activeProjectId`: project the UI/API use by default in local-mode requests.

## Enterprise Profile (External Postgres)

Use `enterprise` when you want split API and worker containers with an external Postgres database.

1. Update `deploy/runtime/.env` with your Postgres credentials:

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://user:password@postgres-host:5432/ccdash
```

2. Start the stack:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise up --build
```

3. Verify both API and worker are healthy:

```bash
# API readiness (port 8000)
curl http://localhost:8000/api/health/ready

# Worker readiness (port 9465)
curl http://localhost:9465/readyz
```

What you get:
- Separate `api` and `worker` containers
- API runs with `CCDASH_RUNTIME_PROFILE=api`
- Worker runs with `CCDASH_RUNTIME_PROFILE=worker`
- Frontend nginx on port 3000
- External Postgres database (configured via `CCDASH_DATABASE_URL`)

## Postgres Profile (Bundled Database)

Combine `enterprise` and `postgres` profiles for a fully self-contained stack with bundled `postgres:17-alpine`.

1. Update `deploy/runtime/.env`:

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres

# Optional: customize Postgres credentials (defaults: user=ccdash, db=ccdash)
CCDASH_POSTGRES_USER=ccdash
CCDASH_POSTGRES_PASSWORD=secure-password-here
CCDASH_POSTGRES_DB=ccdash
```

2. Start with both profiles:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres up --build
```

3. Wait 30–60 seconds for Postgres to become healthy:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres ps
```

What you get:
- Postgres service on port 5432 (named volume `ccdash-postgres`)
- API and worker containers (depend_on Postgres health check)
- Frontend nginx on port 3000
- Fully managed inside `compose.yaml` — no external Postgres needed

## Live Watcher Worker Profile

Add `live-watch` when you need enterprise live session ingest from mounted Claude Code or Codex session directories. The watcher co-runs with the default enterprise worker; it does not replace it. The default worker keeps probe port `9465`, and `worker-watch` uses `9466` by default.

The watcher supports two operating modes controlled by `CCDASH_WORKER_WATCH_PROJECT_ID`:

### Registry-Driven Fan-Out Mode (Recommended for Multi-Project)

When `CCDASH_WORKER_WATCH_PROJECT_ID` is empty, `worker-watch` performs registry-driven fan-out: it queries the DB registry at startup and during periodic reconciliation (default every 60s) to discover all `is_active=true` projects and spawns one WatcherBinding per project. This mode is ideal for deployments with multiple active projects.

```bash
# Leave CCDASH_WORKER_WATCH_PROJECT_ID empty for registry-driven mode
CCDASH_WORKER_PROJECT_ID=your-default-project-id
CCDASH_WORKER_PROBE_PORT=9465
# Omit CCDASH_WORKER_WATCH_PROJECT_ID or set to empty string
CCDASH_WORKER_WATCH_PROJECT_ID=
CCDASH_WORKER_WATCH_PROBE_PORT=9466
CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true
CCDASH_WORKER_STARTUP_SYNC_ENABLED=false
CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true
CCDASH_WATCHER_SYNC_CONCURRENCY=20
CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS=60
CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED=false
GIT_OPTIONAL_LOCKS=0
```

### Single-Project Scope Mode (v1 Backward Compatibility)

When `CCDASH_WORKER_WATCH_PROJECT_ID` is set to a specific project id, `worker-watch` binds to only that project. One project per worker process; use multiple `worker-watch` containers with unique project ids and probe ports for multi-project ingest.

```bash
CCDASH_WORKER_PROJECT_ID=your-default-project-id
CCDASH_WORKER_PROBE_PORT=9465
CCDASH_WORKER_WATCH_PROJECT_ID=your-specific-project-id  # Scopes to one project
CCDASH_WORKER_WATCH_PROBE_PORT=9466
CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true
CCDASH_WORKER_STARTUP_SYNC_ENABLED=false
CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true
CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED=false
GIT_OPTIONAL_LOCKS=0
```

Confirm the required read-only ingest mounts point at host paths Docker can see:

```bash
CCDASH_PROJECTS_FILE=../../projects.json
CCDASH_WORKSPACE_HOST_ROOT=../../..
CCDASH_WORKSPACE_CONTAINER_ROOT=/workspace
CCDASH_CLAUDE_HOME=~/.claude
CCDASH_CLAUDE_CONTAINER_HOME=/home/ccdash/.claude
CCDASH_CODEX_HOME=~/.codex
CCDASH_CODEX_CONTAINER_HOME=/home/ccdash/.codex
```

Start the stack:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch up --build
```

Verify both worker roles:

```bash
curl http://localhost:9465/readyz
curl http://localhost:9466/readyz
```

On macOS Docker Desktop, bind-mounted filesystem events may not arrive. If the watcher starts but does not detect new session JSONL changes, pass `WATCHFILES_FORCE_POLLING=true` into the `worker-watch` container and restart it.

### Watcher Concurrency and Reconciliation Tuning

- `CCDASH_WATCHER_SYNC_CONCURRENCY` (default 20): Max parallel file sync operations per project. Increase on high-throughput deployments; decrease for memory-constrained environments.
- `CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS` (default 60): How often the watcher re-reads the registry to detect added/removed/activated projects. Only relevant in registry-driven fan-out mode (empty `CCDASH_WORKER_WATCH_PROJECT_ID`).

## Data Visibility Checks

After health probes pass, verify the project data path before treating the deployment as usable:

```bash
curl -fsS http://localhost:8000/api/projects/active | python3 -m json.tool
curl -fsS 'http://localhost:8000/api/v1/features?view=cards&limit=5' | python3 -m json.tool
curl -fsS http://localhost:9466/detailz | python3 -m json.tool
```

Expected results:

- `/api/projects/active` returns the project id you intended to serve.
- Feature, document, and session surfaces return data after startup sync or a manual sync has completed.
- `worker-watch` detail shows `runtimeProfile=worker-watch`, a running watcher state, a non-zero `watchPathCount` for projects with configured paths, and `lastSyncStatus=succeeded` after a live change.

If health passes but data is empty, inspect `activeProjectId`, `CCDASH_WORKER_PROJECT_ID`, `CCDASH_WORKER_WATCH_PROJECT_ID`, and whether every registry path resolves inside the container.

## Rootless Podman Configuration

The stack is validated for rootless Podman >= 4.6 and `podman-compose` >= 1.5. Use the same `docker compose` commands with `podman-compose`:

```bash
podman-compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local up --build
```

### Podman Machine Memory (macOS / Windows)

Default allocation (2 GiB) is insufficient for frontend Vite builds. You will see OOM exit 137 at the `computing gzip size` stage. Bump to 4 GiB:

```bash
podman machine stop
podman machine set --memory 4096
podman machine start
```

On fresh installs, run `podman machine start` first.

### HEALTHCHECK OCI Format Note

`podman build` may warn that `HEALTHCHECK is not supported for OCI image format`. The compose-level `healthcheck:` blocks are honored by `podman-compose`, so end-to-end health gating works. The image-level `HEALTHCHECK` is inert, but this is a no-op in practice since compose health checks are used.

### SELinux Bind-Mount Labels (`:Z` / `:z`)

On SELinux-enforcing hosts (RHEL/Fedora/CentOS Stream), bind-mounted host paths require relabeling. Append `:Z` (single-container exclusive) or `:z` (shared multi-container) to bind-mount sources:

```yaml
volumes:
  # Single-container exclusive access
  - /opt/ccdash/projects.json:/app/projects.json:Z
  # Shared between containers
  - /opt/ccdash/data:/var/lib/ccdash:z
```

Named volumes (the defaults in `compose.yaml`) manage SELinux labels automatically; no suffix needed.

The `:Z`/`:z` suffix is a no-op on non-SELinux hosts (Debian/Ubuntu, macOS Podman machine, WSL2) and is safe to leave in compose files for cross-platform use.

### Build Context Size

`podman-compose` streams build context through in-memory tar. Large contexts (e.g., `data/`, `node_modules/`, `.git/`) cause `archive/tar: write too long`. The repo ships `.dockerignore` excluding these. Keep it intact.

### Named Volume UID Mapping

Rootless Podman maps in-container UIDs via `/etc/subuid`. Named volumes created by `podman-compose` are owned by that UID and are writable without additional configuration. The default `ccdash-local-data` and `ccdash-postgres` volumes are automatically UID-compatible.

## Environment Variables

Common variables for container profiles:

| Variable | Profile | Notes |
|----------|---------|-------|
| `CCDASH_STORAGE_PROFILE` | All | `local` (SQLite) or `enterprise` (Postgres) |
| `CCDASH_DB_BACKEND` | All | `sqlite` or `postgres` |
| `CCDASH_DATABASE_URL` | enterprise/postgres | Postgres connection URL (required for enterprise) |
| `CCDASH_FRONTEND_PORT` | All | Frontend port (default 3000) |
| `CCDASH_API_UPSTREAM` | frontend | Backend upstream for nginx reverse-proxy (default `http://api:8000`) |
| `CCDASH_WORKER_PROJECT_ID` | enterprise (worker) | Project ID the worker binds to on startup; required for worker container readiness. Default in compose.yaml is `smoke-stack`. |
| `CCDASH_WORKER_WATCH_PROJECT_ID` | live-watch | **Optional** scope filter for the watcher worker. Empty → registry-driven fan-out (derive targets from DB, one WatcherBinding per is_active project). Non-empty → scope to that specific project id (v1 single-project mode). When unset, defaults to empty for registry-driven behavior. |
| `CCDASH_WORKER_WATCH_PROBE_PORT` | live-watch | Watcher worker probe port. Default is `9466` so it can co-run with the default worker. |
| `CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED` | live-watch | Enables filesystem ingest for `worker-watch`; default is `true`. |
| `CCDASH_WATCHER_SYNC_CONCURRENCY` | live-watch | Max parallel file sync operations per project. Default is `20`. Increase on high-throughput deployments; decrease for memory-constrained environments. |
| `CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS` | live-watch | Registry reconciliation interval (seconds). Default is `60`. Only relevant in registry-driven fan-out mode (empty `CCDASH_WORKER_WATCH_PROJECT_ID`). How often the watcher re-reads the DB registry to detect added/removed/activated projects. |
| `CCDASH_WORKER_STARTUP_SYNC_ENABLED` | enterprise (worker) | Keeps the standard worker from racing watcher-owned filesystem startup sync when live-watch is running; default is `false` in compose. |
| `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED` | live-watch | Lets the watcher worker own startup filesystem sync; default is `true` in compose. |
| `CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED` | enterprise/local | Controls inferred planning-status writes back to markdown. Defaults to `false` for enterprise storage and `true` for local storage. |
| `GIT_OPTIONAL_LOCKS` | enterprise/local | Keep `0` when project repositories are mounted read-only so Git metadata reads do not try to refresh indexes. |
| `WATCHFILES_FORCE_POLLING` | live-watch | Set to `true` on macOS Docker Desktop when bind-mount events are not delivered. |
| `CCDASH_POSTGRES_USER` | postgres profile | Bundled Postgres username (default `ccdash`) |
| `CCDASH_POSTGRES_PASSWORD` | postgres profile | Bundled Postgres password (default `ccdash`) |
| `CCDASH_POSTGRES_DB` | postgres profile | Bundled database name (default `ccdash`) |
| `CCDASH_API_BEARER_TOKEN` | All | Optional bearer token for `/api/v1/*` endpoints |

For the complete reference, see `deploy/runtime/.env.example` and `docs/guides/setup.md`.

## Live Updates and SSE Configuration

CCDash supports two modes for real-time feature, test, and operations panel updates:

1. **Server-Sent Events (SSE)**: Real-time push-based invalidation (when enabled)
2. **Polling fallback**: 30-second TanStack Query polling (when SSE is disabled)

### SSE (Default for Local, Recommended for Enterprise)

Enable when your load balancer supports streaming:

```bash
VITE_CCDASH_LIVE_FEATURES_ENABLED=true    # Feature board/modal updates
VITE_CCDASH_LIVE_TESTS_ENABLED=true       # Test visualizer updates
VITE_CCDASH_LIVE_OPS_ENABLED=true         # Operations panel updates
CCDASH_LIVE_TEST_UPDATES_ENABLED=true     # Backend gate for test SSE
```

**Requirements**:
- Load balancer proxy buffering disabled (Nginx: `proxy_buffering off`)
- Client connections remain open for event streaming
- Heartbeat keep-alive prevents timeout-happy proxies from closing idle connections

**Transport tuning**:
```bash
CCDASH_LIVE_REPLAY_BUFFER_SIZE=200          # Events per topic for reconnecting clients
CCDASH_LIVE_HEARTBEAT_SECONDS=15            # Keep-alive ping cadence (increase for slow networks)
CCDASH_LIVE_MAX_PENDING_EVENTS=100          # Raise on high-concurrency deployments
CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS=10      # Per-topic cache TTL
CCDASH_LIVE_AGENTS_WINDOW_SECONDS=600       # Active session aggregation window (10 min)
```

### Polling Fallback (When SSE Unavailable)

When `VITE_CCDASH_LIVE_FEATURES_ENABLED=false`, `VITE_CCDASH_LIVE_TESTS_ENABLED=false`, or `VITE_CCDASH_LIVE_OPS_ENABLED=false`, the frontend automatically falls back to TanStack Query polling with a 30-second cadence to reduce server load.

```bash
# Disable SSE, use polling fallback
VITE_CCDASH_LIVE_FEATURES_ENABLED=false
VITE_CCDASH_LIVE_TESTS_ENABLED=false
VITE_CCDASH_LIVE_OPS_ENABLED=false
# Backend still allows test updates if needed
CCDASH_LIVE_TEST_UPDATES_ENABLED=true
```

**Use polling fallback when**:
- Load balancer does not support streaming
- Network infrastructure is unstable or drops idle connections
- Local development where simplicity is preferred over real-time delivery
- Enterprise deployment with restricted egress where SSE is not a blocker

### Enterprise Deployment Recommendation

For enterprise Postgres deployments with Nginx:

```bash
# Enable SSE for real-time updates
VITE_CCDASH_LIVE_FEATURES_ENABLED=true
VITE_CCDASH_LIVE_TESTS_ENABLED=true
VITE_CCDASH_LIVE_OPS_ENABLED=true
CCDASH_LIVE_TEST_UPDATES_ENABLED=true

# Nginx upstream config (in your reverse-proxy)
proxy_buffering off;
proxy_request_buffering off;
proxy_http_version 1.1;
Connection "";
```

## Health Check Endpoints

All services expose readiness and liveness probes:

| Service | Readiness endpoint | Port | Expected behavior |
|---------|-------------------|------|-------------------|
| API | `GET /api/health/ready` | 8000 | `200 OK` within 30s of startup |
| Worker | `GET /readyz` | 9465 | `200 OK` when project binding is resolved |
| Worker-watch | `GET /readyz` | 9466 | `200 OK` when project binding and watcher startup are healthy |
| Frontend | `GET /` | 3000 | `200 OK` (serves static assets) |
| Postgres | health check (pg_isready) | 5432 | Healthy within 30s (postgres profile only) |

Compose `depends_on: condition: service_healthy` ensures correct startup ordering.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Containers won't start, `exit 1` with no logs | Missing or invalid `.env` file | Copy `.env.example` and verify all required vars |
| API readiness fails (enterprise profile) | Postgres not healthy or `CCDASH_DATABASE_URL` invalid | Wait 60s for Postgres; check logs: `docker compose logs postgres api` |
| Worker exits: `CCDASH_WORKER_PROJECT_ID unresolved` | Required env var not set | Add a valid project ID to `.env` or override in compose |
| Worker-watch logs "nothing to monitor" or shows no watch paths | Required `projects.json`, workspace root, `.claude`, or `.codex` mount is missing or points outside Docker's shared paths | Check `CCDASH_PROJECTS_FILE`, `CCDASH_WORKSPACE_*`, `CCDASH_CLAUDE_*`, and `CCDASH_CODEX_*` |
| Worker and worker-watch probe ports conflict | Both services are configured for the same host port | Keep `CCDASH_WORKER_PROBE_PORT=9465` and `CCDASH_WORKER_WATCH_PROBE_PORT=9466`, or assign another unique watcher port |
| Worker-watch does not detect changes on macOS Docker Desktop | Bind-mounted filesystem events are not delivered | Restart `worker-watch` with `WATCHFILES_FORCE_POLLING=true` passed into the container |
| Frontend OOM on Podman machine (exit 137) | Insufficient RAM for Vite build | Bump Podman machine: `podman machine set --memory 4096` |
| SELinux `Permission denied` (RHEL/Fedora/CentOS) | Bind-mount needs relabeling | Add `:Z` suffix to bind-mount sources |
| Container build fails: `archive/tar: write too long` | Build context too large | Check `.dockerignore` excludes `data/`, `node_modules/`, `.git/`, `.venv/` |

## Rollback Plan for Postgres In-Place Upgrades

CCDash's Postgres migration runner is forward-only: it adds columns and indexes but never drops or recreates existing schema objects. When upgrading a production database to a new `SCHEMA_VERSION`, take a snapshot first so you can restore the prior state if an unexpected migration failure occurs.

**Recommended pre-upgrade steps:**

1. Stop the CCDash API and worker containers so no writes occur during the backup.
2. Run `pg_dump` against the live database:

```bash
pg_dump -h localhost -U ccdash -d ccdash \
  -F c -f ccdash-backup-$(date +%Y%m%d%H%M%S).dump
```

3. Store the dump outside the Postgres data volume (the volume is lost if you use `docker compose down --volumes`).
4. Start the updated stack. CCDash applies versioned migrations atomically under an advisory lock. If startup fails:

```bash
# Restore from dump into a fresh database
pg_restore -h localhost -U ccdash -d ccdash --clean ccdash-backup-*.dump
```

**Seeded-v29 smoke:** to verify the upgrade path against a pre-v30 schema before touching production data:

```bash
npm run docker:hosted:smoke:seeded-pg
```

This boots a PG container from `deploy/runtime/fixtures/pg-seed-v29.sql` (schema_version=29, sessions table without `project_id`), upgrades it to SCHEMA_VERSION=35, and asserts `migrationStatus=="applied"` with no `UndefinedColumnError` in logs.

## Image Tagging Convention

If publishing container images to a registry, use:

```
ghcr.io/ccdash/backend:<version>
ghcr.io/ccdash/frontend:<version>
```

This is a documented convention. Registry publication and tag automation remain out of scope for this release.

## Next Steps

- **Full setup reference**: `docs/guides/setup.md`
- **Runtime probe endpoints and variables**: `deploy/runtime/README.md`
- **Process manager examples**: `deploy/runtime/systemd/` and `deploy/runtime/supervisor/`
- **Telemetry export**: `docs/guides/telemetry-exporter-guide.md`
- **Storage profiles and session intelligence**: `docs/guides/storage-profiles-guide.md`
