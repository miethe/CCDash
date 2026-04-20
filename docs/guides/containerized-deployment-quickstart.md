# CCDash Containerized Deployment Quickstart

Use this guide for the canonical container path. It covers the three compose profiles shipped in `deploy/runtime/compose.yaml`:

- `local` for a single backend container with SQLite
- `enterprise` for split API + worker containers
- `postgres` for the bundled Postgres service that layers onto `enterprise`

## Prerequisites

- Docker Compose v2 or `podman-compose`
- A checkout of this repository
- Optional: Podman rootless mode if you want to run the stack without root privileges

## 1) Prepare Environment

Copy the example environment file:

```bash
cp deploy/runtime/.env.example deploy/runtime/.env
```

Adjust the copied file as needed, then choose one of the profile sets below.

## 2) Start the Local Profile

The local profile is the fastest on-ramp. It runs one backend container and one frontend container, with SQLite stored in a named volume.

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local up --build
```

What to expect:

- the UI on `http://localhost:3000`
- the API on `http://localhost:8000`
- `CCDASH_DB_BACKEND=sqlite`
- `CCDASH_STORAGE_PROFILE=local`

## 3) Start the Enterprise Profile

Use `enterprise` when you want split API and worker containers and are providing your own Postgres database.

Set a real `CCDASH_DATABASE_URL` in `deploy/runtime/.env`, then start the profile:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise up --build
```

What to expect:

- `api`, `worker`, and `frontend` containers
- `CCDASH_RUNTIME_PROFILE=api` on the API container
- `CCDASH_RUNTIME_PROFILE=worker` on the worker container
- `CCDASH_STORAGE_PROFILE=enterprise`

## 4) Start the Bundled Postgres Profile

Use the bundled Postgres service when you want the full operator stack from a single compose file.

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres up --build
```

What to expect:

- `postgres`, `api`, `worker`, and `frontend` containers
- the API and worker wait for Postgres health checks
- `CCDASH_DATABASE_URL` defaults to the bundled Postgres service unless you override it

## 5) Rootless Podman Notes

The stack is designed to work with rootless Podman as long as you align container ownership with your host UID and GID.

- leave `CCDASH_UID` and `CCDASH_GID` at `1000` unless your host uses different values
- prefer the named volumes shipped in `compose.yaml` for `ccdash-local-data` and `ccdash-postgres-data`
- if you bind-mount host paths for data or logs, add the `:Z` label so SELinux can relabel the mount for the container
- use the same `docker compose` style commands with `podman-compose` if that is your preferred runtime

## 6) Verify the Stack

Render the compose contract first:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local config
```

Then confirm the containers are healthy with:

```bash
docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile local ps
```

For enterprise or bundled Postgres runs, replace `--profile local` with the matching profile set above and confirm the API, worker, frontend, and optional Postgres services are all present.

## Image Tags

Planned publication tags follow this convention:

- `ghcr.io/ccdash/backend:<version>`
- `ghcr.io/ccdash/frontend:<version>`

The convention is documentation only for now; registry publication automation is still out of scope.
