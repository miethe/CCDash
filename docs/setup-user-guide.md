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

## Optional: Run Services Separately

Use two terminals:

```bash
npm run dev:backend
```

```bash
npm run dev:frontend
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

Serve built frontend:

```bash
npm run start:frontend
```

For real deployments, run backend/frontend under a process manager (systemd, Docker, or similar) and terminate TLS at a reverse proxy.

## Troubleshooting

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
