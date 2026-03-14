---

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.10+

### Installation

1. **Install frontend dependencies**:
   ```bash
   npm install
   ```

2. **Install backend dependencies and create virtual environment**:
   ```bash
   npm run setup
   ```

3. **Start the full development stack** (backend + frontend with hot reload):
   ```bash
   npm run dev
   ```

   Frontend runs on `http://localhost:3000`; backend API on `http://localhost:8000`. Vite proxies `/api` requests automatically.

### Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Full dev stack (backend + frontend with hot reload) |
| `npm run dev:frontend` | Frontend only (Vite dev server, port 3000) |
| `npm run dev:backend` | Backend only (uvicorn with reload, port 8000) |
| `npm run dev:worker` | Background worker only (sync + scheduled jobs, no HTTP) |
| `npm run discover:sessions` | Run session signal discovery (default profile: `claude_code`) |
| `npm run build` | Build frontend assets for production |
| `npm run start:backend` | Production-style backend startup |
| `npm run start:worker` | Production-style background worker startup |
| `npm run start:frontend` | Serve built frontend (`vite preview`) |

### Environment Variables

#### Integrations

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Enables AI insight features (Google Gemini) |

#### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_BACKEND_HOST` | `127.0.0.1` | Backend bind host |
| `CCDASH_BACKEND_PORT` | `8000` | Backend bind port |
| `CCDASH_API_PROXY_TARGET` | — | Vite proxy target for `/api` requests |

#### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_DB_BACKEND` | `sqlite` | Database backend (`sqlite` or `postgres`) |
| `CCDASH_DATABASE_URL` | — | PostgreSQL connection URL (required when using `postgres`) |

#### Feature Gates

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_TEST_VISUALIZER_ENABLED` | — | Global gate for `/api/tests/*` and `/tests` data |
| `CCDASH_INTEGRITY_SIGNALS_ENABLED` | — | Global gate for integrity signal features |
| `CCDASH_LIVE_TEST_UPDATES_ENABLED` | — | Global gate for live test updates |
| `CCDASH_SEMANTIC_MAPPING_ENABLED` | — | Global gate for semantic mapping |
| `CCDASH_SKILLMEAT_INTEGRATION_ENABLED` | `true` | Global gate for SkillMeat sync/cache endpoints |
| `CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED` | `true` | Global gate for historical stack recommendations |
| `CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED` | `true` | Global gate for workflow intelligence endpoints |
| `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED` | `true` | Global gate for attribution analytics and payloads |

#### Startup Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `CCDASH_STARTUP_SYNC_LIGHT_MODE` | `true` | Run startup sync in lightweight mode first |
| `CCDASH_STARTUP_SYNC_DELAY_SECONDS` | `2` | Delay before startup sync starts |
| `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` | `true` | Run deferred link rebuild after light startup sync |
| `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS` | `45` | Delay before deferred link rebuild |
| `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS` | `false` | Capture analytics during deferred rebuild |
| `CCDASH_LINKING_LOGIC_VERSION` | `1` | Link-rebuild version gate; bump to force full relink |

### Runtime Profiles

- **`npm run dev` / `npm run start:backend`** — `local` runtime profile: HTTP server + in-process sync/watch/scheduled jobs for desktop convenience.
- **`npm run dev:worker` / `npm run start:worker`** — Worker-only profile: sync, refresh, and scheduled jobs without serving HTTP.
- **`backend.main:app`** — Hosted-style API entrypoint with background work disabled; suitable for containerized deployments.

Copy `.env.example` to `.env` for local overrides. All variables are prefixed `CCDASH_*`.

For full setup, troubleshooting, and deployment guidance, see [`docs/setup-user-guide.md`](docs/setup-user-guide.md).
