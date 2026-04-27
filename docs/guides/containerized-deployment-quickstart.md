# Containerized Deployment Quickstart

This is the preferred onboarding route for CCDash. It covers deploying with Docker Compose or Podman Compose using three composable profiles: `local` (single-container SQLite), `enterprise` (split API/worker), and `postgres` (bundled Postgres service).

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
POSTGRES_USER=ccdash
POSTGRES_PASSWORD=secure-password-here
POSTGRES_DB=ccdash
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
| `CCDASH_API_UPSTREAM` | frontend | Backend upstream for nginx reverse-proxy (default `http://backend:8000`) |
| `POSTGRES_USER` | postgres profile | Bundled Postgres username (default `ccdash`) |
| `POSTGRES_PASSWORD` | postgres profile | Bundled Postgres password (default `ccdash-dev-password`) |
| `POSTGRES_DB` | postgres profile | Bundled database name (default `ccdash`) |
| `CCDASH_API_BEARER_TOKEN` | All | Optional bearer token for `/api/v1/*` endpoints |

For the complete reference, see `deploy/runtime/.env.example` and `docs/guides/setup.md`.

## Health Check Endpoints

All services expose readiness and liveness probes:

| Service | Readiness endpoint | Port | Expected behavior |
|---------|-------------------|------|-------------------|
| API | `GET /api/health/ready` | 8000 | `200 OK` within 30s of startup |
| Worker | `GET /readyz` | 9465 | `200 OK` when project binding is resolved |
| Frontend | `GET /` | 3000 | `200 OK` (serves static assets) |
| Postgres | health check (pg_isready) | 5432 | Healthy within 30s (postgres profile only) |

Compose `depends_on: condition: service_healthy` ensures correct startup ordering.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Containers won't start, `exit 1` with no logs | Missing or invalid `.env` file | Copy `.env.example` and verify all required vars |
| API readiness fails (enterprise profile) | Postgres not healthy or `CCDASH_DATABASE_URL` invalid | Wait 60s for Postgres; check logs: `docker compose logs postgres api` |
| Worker exits: `CCDASH_WORKER_PROJECT_ID unresolved` | Required env var not set | Add a valid project ID to `.env` or override in compose |
| Frontend OOM on Podman machine (exit 137) | Insufficient RAM for Vite build | Bump Podman machine: `podman machine set --memory 4096` |
| SELinux `Permission denied` (RHEL/Fedora/CentOS) | Bind-mount needs relabeling | Add `:Z` suffix to bind-mount sources |
| Container build fails: `archive/tar: write too long` | Build context too large | Check `.dockerignore` excludes `data/`, `node_modules/`, `.git/`, `.venv/` |

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
