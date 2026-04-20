# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

CCDash is a local-first dashboard for orchestrating, monitoring, and analyzing AI agent sessions within software projects. It bridges project management (Kanban, docs) with AI development forensics (session logs, tool usage, token metrics).

## Architecture

**Full-stack app with split frontend/backend:**

- **Frontend**: React 19 + TypeScript + Vite (port 3000). Uses HashRouter. All frontend source lives at the repo root (`App.tsx`, `types.ts`, `constants.ts`, `components/`, `services/`, `contexts/`). Path alias `@/` maps to repo root.
- **Backend**: Python FastAPI + explicit runtime profiles (`local`, `api`, `worker`, `test`). API runtime serves HTTP on port 8000; worker runtime lives at `backend/worker.py`. Located in `backend/`. Uses async SQLite (default) or PostgreSQL via `CCDASH_DB_BACKEND` env var. Python venv at `backend/.venv/`.
- **Agent Query Surfaces**: `backend/application/services/agent_queries/` is the shared transport-neutral intelligence layer used by REST, CLI, and MCP.
- **Standalone CLI**: `packages/ccdash_cli/` — globally installable CLI that talks to the server over HTTP via `backend/routers/client_v1.py`. Shared contracts in `packages/ccdash_contracts/`.
- **Proxy**: Vite proxies `/api` requests to the backend in dev mode.
- **Styling**: Tailwind CSS with a slate dark mode theme.

### Backend Structure (backend/)

```
main.py          → Local runtime entrypoint (`backend.runtime.bootstrap_local`)
config.py        → All env var config (DB, sync tuning, OTEL, server)
routers/         → API route handlers (api.py, agent.py, analytics.py, features.py, projects.py, cache.py, codebase.py, session_mappings.py)
services/        → Business logic (codebase_explorer.py, feature_execution.py)
runtime/         → Runtime profiles, FastAPI app bootstrap, container composition
adapters/jobs/   → In-process scheduler + runtime background job adapter
worker.py        → Background-only worker entrypoint (no HTTP server)
cli/             → Typer CLI over the shared agent query services
mcp/             → FastMCP stdio server exposing the same query services as tools
parsers/         → File parsers (sessions.py, documents.py, features.py, progress.py, status_writer.py)
application/services/agent_queries/ → Transport-neutral project/feature/workflow/report query services
db/
  connection.py  → Singleton async DB connection (SQLite or PostgreSQL)
  migrations.py  → Migration runner
  sync_engine.py → Filesystem→DB sync engine
  file_watcher.py→ Watches filesystem for changes
  repositories/  → Data access layer (sessions.py, documents.py, tasks.py, features.py, analytics.py, links.py, base.py)
routers/agent.py → REST transport for the shared agent intelligence queries
models.py        → Pydantic models
observability/   → OpenTelemetry + Prometheus instrumentation
tests/           → Backend unittest/pytest-compatible test suite
```

### Frontend Structure

```
App.tsx                     → Root component with routes
types.ts                    → All TypeScript interfaces (AgentSession, Feature, ProjectTask, PlanDocument, etc.)
constants.ts                → App constants
contexts/DataContext.tsx    → Compatibility facade over split shell providers
contexts/AppSessionContext.tsx → Project/session shell state
contexts/AppEntityDataContext.tsx → Sessions/documents/tasks/features state
contexts/AppRuntimeContext.tsx → Polling, loading/error state, runtime health
services/apiClient.ts       → Typed API client for app-shell fetch/mutation flows
services/runtimeProfile.ts  → Runtime-health normalization helpers
components/                 → Page-level components (Dashboard, ProjectBoard, SessionInspector, PlanCatalog, etc.)
services/                   → Domain API helpers (analytics.ts, execution.ts, geminiService.ts, etc.)
```

### Key Data Flow

1. Backend `parsers/` read local filesystem (session JSONL logs, markdown docs with frontmatter, progress files)
2. `sync_engine.py` syncs parsed data into the SQLite/PostgreSQL cache DB
3. `repositories/` provide data access; `routers/` expose REST API
4. Frontend shell providers use `services/apiClient.ts`, while `contexts/DataContext.tsx` exposes a compatibility `useData()` facade to components

## Commands

```bash
# First-time setup (creates backend/.venv, installs Python deps)
npm run setup

# Full dev stack (backend + frontend with hot reload)
npm run dev

# Frontend only (Vite dev server)
npm run dev:frontend

# Backend only (uvicorn with --reload)
npm run dev:backend

# Worker only (background sync/jobs, no HTTP)
npm run dev:worker

# Build frontend
npm run build

# Run backend tests
backend/.venv/bin/python -m unittest backend.tests.test_runtime_bootstrap backend.tests.test_request_context
# Or, if pytest is installed in the venv:
backend/.venv/bin/python -m pytest backend/tests/ -v

# Query surfaces (repo-local CLI)
backend/.venv/bin/ccdash --help
backend/.venv/bin/ccdash status project
backend/.venv/bin/ccdash feature report FEAT-123 --json
backend/.venv/bin/ccdash workflow failures --md
backend/.venv/bin/ccdash report aar --feature FEAT-123
backend/.venv/bin/python -m backend.cli --help

# Standalone CLI (install globally: pipx install ccdash-cli)
ccdash version
ccdash feature list --status active --json
ccdash session search "authentication" --limit 10
ccdash report aar --feature FEAT-123
ccdash target check local
# CLI flags: --timeout SECONDS (default 30), --no-cache (bypass cache), --q TEXT (keyword filter on feature list)
ccdash feature list --q "auth" --timeout 45

# Standalone CLI tests
python -m pytest packages/ccdash_cli/tests/ -v

# MCP server and MCP regression coverage
backend/.venv/bin/python -m backend.mcp.server
backend/.venv/bin/python -m unittest backend.tests.test_mcp_server -v

# Run a single backend test
backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v

# Run backend tests matching a pattern
backend/.venv/bin/python -m pytest backend/tests/ -k "test_model_identity" -v
```

## Key Conventions

- **DB backend**: Default SQLite at `data/ccdash_cache.db`. Set `CCDASH_DB_BACKEND=postgres` + `CCDASH_DATABASE_URL` for PostgreSQL.
- **Config via env vars**: All backend config is in `backend/config.py` reading from `CCDASH_*` env vars. Copy `.env.example` for local overrides.
- **CLI timeout**: `CCDASH_TIMEOUT` (default 30s; overridden by `--timeout` flag). See `docs/guides/cli-timeout-debugging.md`.
- **Query cache**: `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 60; 0 disables). `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` (default 300; background warming). See `docs/guides/query-cache-tuning-guide.md`.
- **Frontend types**: All shared interfaces are in root `types.ts`. Import from `@/types`.
- **Router→Service→Repository pattern**: Backend follows layered architecture. Routers call services/repositories, never raw SQL.
- **Transport-neutral agent queries**: Add new cross-domain intelligence reads in `backend/application/services/agent_queries/` first, then wire them into `backend/routers/agent.py`, `backend/cli/`, and `backend/mcp/` as needed.
- **Telemetry exporter**: Worker-side export logic lives in `backend/services/integrations/telemetry_exporter.py`, is registered from `backend/runtime/container.py`, and emits observability data through `backend/observability/otel.py`. Operator guidance lives in `docs/guides/telemetry-exporter-guide.md` and `docs/guides/telemetry-exporter-troubleshooting.md`.
- **Session data**: Agent session logs are JSONL files parsed by `backend/parsers/sessions.py`.
- **Document linking**: `backend/document_linking.py` handles cross-referencing between sessions, documents, features, and tasks.
- **Project switching**: Multi-project support via `projects.json` and `backend/project_manager.py`. Each project has its own session/doc/progress paths.
- **MCP transport**: `backend/mcp/server.py` is a stdio server. Running it manually will block waiting for an MCP client; use `.mcp.json` or `backend/tests/test_mcp_server.py` for normal validation.
- **Frontend tests**: Vitest covers utility and architecture guardrail tests under `components/**/__tests__`, `contexts/__tests__`, `lib/__tests__`, and `services/__tests__`.
