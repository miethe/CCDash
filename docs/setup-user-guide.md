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
- `CCDASH_LINKING_LOGIC_VERSION` (default `1`; bump to force a full link rebuild after linking-logic changes)
- `CCDASH_STARTUP_SYNC_LIGHT_MODE` (default `true`; startup runs a light sync first)
- `CCDASH_STARTUP_SYNC_DELAY_SECONDS` (default `2`; delay before startup sync begins)
- `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` (default `true`; deferred heavier rebuild after startup)
- `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS` (default `45`)
- `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS` (default `false`)

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

### `/tests` disabled, empty, or returning `503`

1. Confirm env gates are enabled (`CCDASH_TEST_VISUALIZER_ENABLED=true` at minimum).
2. In CCDash, open `Settings` -> `Projects` -> `Testing Configuration`.
3. Enable `Test Visualizer` for the project and configure at least one enabled platform.
4. Click `Validate Paths`, review `Source Status`, then click `Run Sync Now`.
5. Reload `/tests` and click `Refresh`.

For the complete project-scoped testing setup flow (platforms, patterns, setup script export), see [`docs/testing-user-guide.md`](./testing-user-guide.md).
