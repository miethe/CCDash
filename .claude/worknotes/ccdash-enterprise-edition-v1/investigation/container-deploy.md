# Container/Enterprise Deployment — Investigation Findings

**Domain**: container-deploy
**Investigator**: Claude Sonnet 4.6 (subagent)
**Date**: 2026-05-30
**Scope**: Dockerfile(s), compose variants, volumes, env vars, health checks, startup order, Postgres wiring, dev-vs-container parity, and the precise gap that prevents live session/filesystem ingestion in containers.

---

## 1. Topology Overview (as-built)

The repo ships **two** independent container topologies:

| File | Status | Notes |
|---|---|---|
| `deploy/runtime/Dockerfile` | COMPLETED | Single multi-stage image; entrypoint dispatches on `CCDASH_RUNTIME_PROFILE` |
| `deploy/runtime/compose.yaml` | COMPLETED | Primary compose with `local`, `enterprise`, `postgres`, `live-watch` profiles |
| `deploy/runtime/api/Dockerfile` | PARTIAL | Separate API image (no builder stage, installs directly into runtime layer) |
| `deploy/runtime/worker/Dockerfile` | PARTIAL | Same as api/Dockerfile pattern — no user hardening |
| `deploy/runtime/compose.hosted.yml` | PARTIAL | Older hosted topology, no volume mounts for filesystem ingestion |
| `deploy/runtime/compose.external-postgres.yaml` | COMPLETED | Podman-compat override to drop `depends_on:postgres` |

The **primary** compose is `deploy/runtime/compose.yaml`. The `compose.hosted.yml` is a legacy file that is not aligned with the current workspace-mount strategy.

---

## 2. Service Graph (compose.yaml enterprise profile)

```
postgres  (profile: postgres)
    ↓ service_healthy
api       (profile: enterprise)
    ↓ service_healthy
worker    (profile: enterprise)

worker-watch  (profile: live-watch)
    ↓ depends on api (service_healthy) + postgres (service_healthy, required: false)

frontend  (profile: local | enterprise)
    (no depends_on — starts independently)
```

**Critical gap**: The `frontend` service has **no `depends_on: api`** (`compose.yaml:195–217`). It starts immediately and may try to proxy API requests before the API is ready. The nginx proxy fails silently (502 Bad Gateway) until the API becomes healthy.

---

## 3. Volume / Path Wiring Analysis

### 3.1 Shared volume mounts (x-backend-service, compose.yaml:44–84)

Every backend service gets these bind mounts:

| Mount | Host default | Container target | read_only |
|---|---|---|---|
| projects.json | `../../projects.json` | `/app/projects.json` | true |
| workspace root | `../../..` (3 levels up from deploy/runtime/) | `${CCDASH_WORKSPACE_CONTAINER_ROOT:-/workspace}` | true |
| claude home | `~/.claude` | `/home/ccdash/.claude` | true |
| codex home | `~/.codex` | `/home/ccdash/.codex` | true |
| extra mounts 1–6 | `./empty-mounts/optional-N` (empty dirs) | `/mnt/ccdash/optional-N` | true |

### 3.2 The host-path-resolution gap (CRITICAL)

`projects.json` stores **raw host absolute paths** for all registered projects (confirmed from actual data):

```
[3df0ff70] SkillMeat
  root.filesystemPath: /Users/miethe/dev/homelab/development/skillmeat
  sessions.filesystemPath: ~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat

[3da60e0c] CCDash
  root.filesystemPath: /Users/miethe/dev/homelab/development/CCDash
  sessions.filesystemPath: ~/.codex/sessions/

[479ae45d] MeatyWiki
  sessions.filesystemPath: /Users/miethe/.claude/projects/-Users-miethe-dev-homelab-development-meatywiki
```

Inside the container:
- `/Users/miethe/dev/homelab/development/skillmeat` → **does not exist** (host macOS path, not mounted at that path)
- `~/.claude/projects/...` → expands to `/home/ccdash/.claude/projects/...` (the bind mount target) — this **does work IF** the `~/.claude` bind mount covers that subdirectory
- `/Users/miethe/.claude/projects/...` → **does not exist** (absolute host path, no mount covers it)

The workspace bind mount (`../../..` → `/workspace`) covers `CCDASH_WORKSPACE_HOST_ROOT=/Users/miethe/dev/homelab/development` → `/workspace`. But projects.json paths use `/Users/miethe/...` while the container mount target is `/workspace` — the backend code would need path aliasing to translate these.

**Source identity aliasing** exists (`backend/services/source_identity.py:271–308`): `source_identity_policy_from_env()` builds `SourceRootAlias` pairs from `CCDASH_WORKSPACE_HOST_ROOT`/`CCDASH_WORKSPACE_CONTAINER_ROOT`, `CCDASH_CLAUDE_HOME`/`CCDASH_CLAUDE_CONTAINER_HOME`, and up to 6 extra mounts. BUT this aliasing only operates during **session key canonicalization in the sync engine** — it does NOT rewrite the paths that `ProjectPathResolver.resolve_reference()` uses when opening directories for filesystem scanning. The `FilesystemProjectPathProvider.resolve()` (`backend/services/project_paths/providers/filesystem.py:17–37`) calls `Path(raw_value).expanduser()` on whatever is stored in `projects.json`, with no container alias translation.

**Result**: The sync engine is invoked against the container-translated path alias for session key identity, but the initial directory scan opens the raw host path — which does not exist inside the container. **This is the root cause of zero filesystem ingestion in containers.**

### 3.3 The projects.json read_only mount

`projects.json` is mounted `read_only: true` (`compose.yaml:48`). However, `ProjectManager._save()` (`project_manager.py:140–146`) calls `self.storage_path.write_text(...)` on startup if migration is detected (line 100) or when a project is modified. **With a read_only mount, any write attempt raises `PermissionError` and silently corrupts the startup flow.**

The `_load()` method checks for schema migration at `project_manager.py:114–127` and calls `_save()` on line 100 if `migrated=True`. On a fresh container with a pre-existing `projects.json` that triggers migration, this fails at import time.

### 3.4 CCDASH_PROJECTS_FILE not wired into config.py

`CCDASH_PROJECTS_FILE` appears in `container_project_onboarding.py` and the watcher env template, but is **never read in `backend/config.py`** and is not used by `ProjectManager.__init__()` at `project_manager.py:287`:

```python
project_manager = ProjectManager(config.PROJECT_ROOT / "projects.json")
```

`config.PROJECT_ROOT` is `Path(__file__).resolve().parent.parent` — which resolves to `/app` inside the container (the WORKDIR). The bind mount puts `projects.json` at `/app/projects.json`, which matches. However, there is no way to override the projects.json path via environment variable — the `CCDASH_PROJECTS_FILE` env documented in `container_project_onboarding.py` output is **a dead env var** with no effect.

---

## 4. Entrypoint and Profile Dispatch

`deploy/runtime/entrypoint.sh` only handles three profiles (`local`, `api`, `worker`) — **`worker-watch` is missing** (`entrypoint.sh:10–24`). Yet `compose.yaml:165` sets `CCDASH_RUNTIME_PROFILE: "worker-watch"` for the `worker-watch` service. The `worker-watch` service overrides `command` to `["python", "-m", "backend.worker"]` (`compose.yaml:162`), bypassing `entrypoint.sh`. This is functional but fragile — the entrypoint's case statement will print "Unsupported CCDASH_RUNTIME_PROFILE" and exit 1 if the command override is ever removed.

The `backend/runtime/bootstrap_worker.py:21–28` (`resolve_worker_runtime_profile()`) correctly accepts `worker-watch` as a valid profile name, so the worker binary itself is fine.

---

## 5. Postgres Wiring and Migration Bootstrap

### 5.1 Connection string
- `compose.yaml:89`: `CCDASH_DATABASE_URL: "postgresql://ccdash:ccdash@postgres:5432/ccdash"`
- This resolves correctly inside the Docker network because the `postgres` service is named `postgres`.
- `backend/db/connection.py:45`: `asyncpg.create_pool(config.DATABASE_URL)` — correct.

### 5.2 Migration execution
- `RuntimeContainer.startup()` (`container.py:106–108`) calls `await migrations.run_migrations(self.db)` after `await connection.get_connection()`.
- `postgres_migrations.run_migrations()` (`postgres_migrations.py:1497`) executes `CREATE TABLE IF NOT EXISTS` — fully idempotent.
- **Both the `api` AND `worker` containers run migrations on startup.** With the current topology there is no advisory lock (`pg_try_advisory_lock` is absent), so simultaneous startup of `api` + `worker` can race on schema initialization. In practice `CREATE TABLE IF NOT EXISTS` is safe under concurrent DDL in Postgres 17, but the `schema_version` insert (`_TABLES` includes no lock) is not atomic with the migration check at line 1501–1512.

### 5.3 API→Postgres dependency
- `compose.yaml:117–119`: `api` depends on `postgres` with `condition: service_healthy, required: false`.
- With `required: false`, if the `postgres` profile is not active, `api` starts without waiting. This is intentional for external-Postgres deployments.
- **With bundled Postgres** (`--profile enterprise --profile postgres`), the dependency correctly enforces health before `api` starts. ✓

### 5.4 `api` profile: no startup sync, no filesystem ingestion
- `RuntimeProfile("api").capabilities.sync = False` (`profiles.py:47–51`)
- `_sync_engine_enabled()` returns `False` for `api` profile (`container.py:237–242`)
- The `api` container **never runs startup sync** regardless of `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED`.
- In the default compose, `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` is `false` for both `api` and `worker` (`compose.yaml:27`). The `worker` service also has `CCDASH_STARTUP_SYNC_ENABLED: "${CCDASH_WORKER_STARTUP_SYNC_ENABLED:-false}"` — **worker startup sync is disabled by default**.

**Result**: With default enterprise profile (no `live-watch`), no filesystem ingestion happens at all. The DB starts empty and stays empty.

---

## 6. Live Filesystem Ingestion — `worker-watch` Service

The `worker-watch` service (`compose.yaml:159–193`) is the only container that enables live ingestion:
- `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: true` → sets `storage_profile.filesystem_source_of_truth = True`
- `CCDASH_STARTUP_SYNC_ENABLED: true` → enables startup scan
- `CCDASH_RUNTIME_PROFILE: worker-watch` → enables `watch` + `sync` capabilities

**But it requires the `live-watch` profile** (`profiles: ["live-watch"]`). The command to bring it up is:
```
docker compose --profile enterprise --profile postgres --profile live-watch up
```

This is not documented in the standard enterprise startup path. The `README.md` in `deploy/runtime/` may document it (not read), but the default `--profile enterprise --profile postgres` does **not** start the watcher.

---

## 7. `worker` vs `worker-watch` Role Confusion

The `worker` service (`compose.yaml:124–155`):
- Profile: `enterprise`
- Has `CCDASH_STARTUP_SYNC_ENABLED: false` (via `CCDASH_WORKER_STARTUP_SYNC_ENABLED`)
- Has `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: false` (inherits from shared env)
- **Purpose in compose**: cache warming, analytics snapshots, telemetry export only — no sync

The `worker-watch` service:
- Profile: `live-watch` (extra profile — not started by default)
- Enables filesystem ingestion + watcher

**Gap**: There is no default enterprise topology that performs initial data ingestion. Operators must know to add `--profile live-watch` for live data.

---

## 8. `discovery_profiles.json` — `${HOME}` expansion in containers

`backend/parsers/platforms/discovery_profiles.json:6–7`:
```json
"roots": [
  "${HOME}/.claude/projects",
  "${WORKSPACE_ROOT}/examples/skillmeat/claude-sessions"
]
```

Inside the container, `${HOME}` = `/home/ccdash`. The `~/.claude` bind mount points to `/home/ccdash/.claude`. So `${HOME}/.claude/projects` resolves correctly **if** the session data lives under `~/.claude/projects` on the host.

`${WORKSPACE_ROOT}` is substituted by `backend/scripts/session_data_discovery.py:47` — but only if `workspace_root` is passed. The discovery profile's `${WORKSPACE_ROOT}` fallback to the bundled example data works in local mode but is irrelevant for enterprise.

---

## 9. compose.hosted.yml — Legacy / Diverged

`compose.hosted.yml` defines its own `api`, `worker`, and `frontend` services referencing separate Dockerfiles (`deploy/runtime/api/Dockerfile`, `deploy/runtime/worker/Dockerfile`). These Dockerfiles:
- Have no `--chown` on COPY → runs as root
- Have no `USER` directive → runs as root
- No `PATH=/opt/venv/bin:$PATH` → relies on global pip install
- `worker` does not inherit the volume mounts from the shared `x-backend-service` anchor
- No `CCDASH_WORKER_PROJECT_ID` is set — worker startup would immediately crash with `RuntimeError: Runtime profile 'worker' requires a non-empty CCDASH_WORKER_PROJECT_ID`

**Status**: `compose.hosted.yml` is effectively broken for current worker requirements. It also defines volumes but **no filesystem bind mounts** for workspace/claude/codex paths, making any live ingestion impossible.

---

## 10. Health Check Sequencing

| Service | Health endpoint | start_period | Notes |
|---|---|---|---|
| postgres | `pg_isready` | 10s | ✓ Solid |
| api | `GET /api/health/ready` | 30s | Runs migrations during lifespan startup — must complete before ready. 30s may be tight on first cold start with large schema |
| worker | `GET /readyz` on port 9465 | 30s | Worker probe starts after `runtime.startup()` completes — includes project binding resolution which can fail |
| worker-watch | Same pattern, port 9466 | 30s | Same concerns as worker |
| frontend | `wget /` | 10s | No dependency on api; nginx serves static assets immediately |

**Race**: The `worker` depends on `api` being healthy. The `api` readiness probe checks `migration_status == "applied"`, which only passes after `run_migrations()` returns. In a fresh Postgres with 2176-line migration DDL, this can take several seconds. The 30s start_period is reasonable but tight in slow container environments (e.g., Docker Desktop on macOS with NFS mounts).

The **API healthcheck does not wait for migrations to fully complete** — the `/api/health/ready` endpoint checks `migration_status == "applied"` (`container.py:~500`), but the container was marked `depends_on: postgres: condition: service_healthy` — the api starts, runs migrations synchronously in `lifespan`, and only then serves traffic. The health check cannot be passed before the lifespan completes, so this is correctly sequenced. ✓

---

## 11. CORS / Auth configuration

- `compose.yaml:19`: `CCDASH_FRONTEND_ORIGIN: "${CCDASH_FRONTEND_ORIGIN:-http://localhost:${CCDASH_FRONTEND_PORT:-3000}}"` — defaults to `localhost:3000`
- In production behind a reverse proxy, `CCDASH_FRONTEND_ORIGIN` must be set to the external hostname or CORS will block requests.
- `bootstrap.py:57–66`: CORS always allows `http://localhost:3000` and `http://127.0.0.1:3000` in addition to `CCDASH_FRONTEND_ORIGIN` — this is a security concern in production (always permitting localhost).

---

## 12. Proposed Reliable Enterprise Topology

```
┌──────────────────────────────────────────────────────────┐
│  docker compose                                          │
│    --profile enterprise                                  │
│    --profile postgres                                    │
│    --profile live-watch   ← REQUIRED for live ingest     │
│    up                                                    │
└──────────────────────────────────────────────────────────┘

services:
  postgres       → named volume, health-gated
  api            → depends_on: postgres (service_healthy)
                   CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false (correct: api doesn't ingest)
  worker         → depends_on: api (service_healthy)
                   CCDASH_WORKER_PROJECT_ID=<project-id>  ← MUST be set
                   CCDASH_WORKER_STARTUP_SYNC_ENABLED=false  (analytics/telemetry only)
  worker-watch   → depends_on: api (service_healthy)
                   CCDASH_WORKER_PROJECT_ID=<same project-id>
                   CCDASH_WORKER_WATCH_PROJECT_ID=<same project-id>
                   CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true
                   CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true
                   volume: /host/project/root → /workspace/project (read_only)
                   volume: ~/.claude → /home/ccdash/.claude (read_only)
  frontend       → depends_on: api (service_healthy)   ← ADD THIS
                   proxies /api → api:8000
```

**Required pre-deployment steps:**
1. Run `backend/scripts/container_project_onboarding.py` to generate a `projects.json` with **container-visible paths** (e.g. `/workspace/skillmeat` not `/Users/miethe/...`)
2. Set `CCDASH_WORKSPACE_HOST_ROOT` and `CCDASH_WORKSPACE_CONTAINER_ROOT` so source identity aliasing canonicalizes session keys correctly
3. Set `CCDASH_WORKER_PROJECT_ID` to the project slug in `projects.json`
4. Set `CCDASH_API_BEARER_TOKEN` (required for `api` profile with `static_bearer` auth)

---

## 13. Summary of Root Cause for Live Data Failure

The containerized enterprise build previously failed to pull live session/filesystem data because of **four compounding gaps**:

1. **projects.json stores host-absolute paths** that do not resolve inside the container. `FilesystemProjectPathProvider.resolve()` calls `Path(raw_value).expanduser()` on the stored value without container-path aliasing. The sync engine never opens the correct directory. (`project_manager.py:287` → `services/project_paths/providers/filesystem.py:19–30`)

2. **`CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults to `false`** in compose (`compose.yaml:27`), which causes `StorageProfileConfig.filesystem_source_of_truth = False` (`config.py:246`), which causes `_sync_engine_enabled()` to return `False` (`container.py:242`). No sync engine, no ingestion — even if paths were correct.

3. **The default `enterprise` + `postgres` profile does not start `worker-watch`**. The only service that enables both filesystem ingestion and startup sync is `worker-watch`, which requires the additional `--profile live-watch` flag. Without it, the DB is populated only from API requests (which read from an empty DB).

4. **`CCDASH_WORKER_STARTUP_SYNC_ENABLED` defaults to `false` for `worker`** (`compose.yaml:133`), so even the `worker` container does not perform an initial filesystem scan.
