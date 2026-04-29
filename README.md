# CCDash — Agentic Project Dashboard & Analytics Platform

**CCDash** bridges traditional project management with AI development forensics — giving you a local-first dashboard to orchestrate, monitor, and analyze AI agent work across software projects.

Where Kanban meets session logs. Where token costs meet delivery velocity.

<!-- badges placeholder -->

Docs: [Documentation home](docs/README.md)

### Why CCDash

- **Agent-First Traceability**: Every task, commit, and document change is traceable back to specific Agent Sessions.
- **Deep Forensics**: Introspect into agent thought processes, tool usage, subagent topology, and cost breakdowns.
- **Workflow Intelligence**: Discover which workflows succeed, which waste tokens, and which carry risk.
- **Local Context**: Tightly coupled with your local filesystem, Git history, and Markdown frontmatter.
- **Multi-Platform**: Native support for Claude Code and Codex with extensible parser routing.

→ [Get Started](#getting-started)

---

## Screenshots

Visual previews of CCDash across its core surfaces. Screenshots are captured against a running local instance — see the [Getting Started](#getting-started) section to run CCDash with your own project data.

### Surfaces Overview

| Surface | Route | What You'll See |
|---------|-------|----------------|
| Landing | `/` | Product overview, docs entrypoint, and public release positioning |
| Dashboard | `/dashboard` | KPI cards, cost/velocity chart, model usage breakdown, and AI-generated project health summary |
| Planning Control Plane | `/planning` | Planning summary, triage inbox, graph view, and feature drill-down surfaces |
| Feature Board | `/board` | Kanban columns grouped by stage with drill-down modals showing phases, tasks, and linked docs |
| Execution Workbench | `/execution` | Recommended stack card, pre-run review modal, safety pipeline, and streaming run output |
| Testing | `/tests` | Test ingestion, health, integrity, and feature/test correlation surfaces |
| Documents | `/plans` | Documentation catalog with document modal, local editing, and GitHub write-back support |
| Docs | `/docs` | Curated public docs site rendered from repo Markdown |
| Session Inspector | `/sessions` | 3-pane transcript with tool call expansion, forensics payload, and session analytics |
| Codebase Explorer | `/codebase` | File tree, activity correlation, and feature/session references |
| Session Mappings | `/session-mappings` | Mapping integrity and semantic correlation controls |
| Operations | `/ops` | Sync, cache, telemetry, and runtime maintenance controls |
| Analytics | `/analytics` | Workflow intelligence, session intelligence, and alert/notification surfaces |
| Workflow Registry | `/workflows` | Searchable catalog with effectiveness scores, composition summary, and issue cards |
| Settings | `/settings` | Project paths, integrations, alert rules, pricing, and runtime configuration |

> Screenshots are being captured. Run `npm run dev` to explore these surfaces live.

---

## Features

73 capabilities across 13 categories.

### Global Navigation & Layout

- **Collapsible Sidebar**: Fluid-transition sidebar with icon-only mode to maximize workspace
- Notification Badges: System alerts for cost overruns, quality drops, and threshold breaches
- Theme Modes: Persisted dark, light, and system preferences with first-paint resolution and browser-chrome alignment

### Dashboard & Analytics

- **KPI Cards**: Real-time metrics for workload, model IO, cache, cost, velocity, and tool reliability
- **Usage Attribution**: Rank attributed workload by skill, agent, command, artifact, and workflow
- **AI Insights**: Google Gemini-powered executive summaries on project health
- Cost vs Velocity Charts: Track spending against task velocity over time with interactive area charts
- Model Usage Charts: Model usage breakdown revealing allocation and cost drivers across sessions
- Workflow Intelligence: Ranks workflows, agents, and skills by success, efficiency, quality, and risk
- Session Block Insights: Break long sessions into time blocks with burn-rate and cost projections
- Master Timeline: Full-width session lifecycle correlation view against token consumption
- Token Semantics: Separate model IO, cache input, and observed workload for accurate attribution

### Session Inspector & Forensics

- **3-Pane Transcript**: Fluid layout with log list, detail view, and metadata sidebar
- Append-First Transcript Live Updates: Safe active-session deltas merge in place, with coarse invalidation and targeted REST recovery as fallback
- Shared Content Viewer: Long-form prompts, markdown-like detail payloads, and raw file-backed session rows open in the standardized viewer shell
- **Deep Forensics**: Queue pressure, resource footprint, subagent topology, and hook signals
- Session Analytics: Token timeline, model allocation, session block insights, and master timeline
- Artifact Cards: Skills, commands, agents, hooks, tasks, and test-run artifacts with source correlation
- App Impact: Delivery outcomes, file footprint, validation movement, and workflow risk signals
- Test Status: Track modified test files and run telemetry including framework, status, and timing
- File Activity: Per-file action chips, touch counts, net diff, and session history in one table
- Agent Cards: Card view of participating agents with click-to-filter transcript navigation

### Feature Board

- **Feature-Centric Board**: Kanban and list views grouping work by feature stage with drill-down modals
- **Document-First Discovery**: Cross-references PRDs, implementation plans, and progress files automatically
- Dependency-Aware Execution: Feature modals surface blocked-by chips, execution-gate summaries, family position, and family-sequence order
- Kanban & List Views: Toggle between visual Kanban board and sortable list for different workflows
- Drill-Down Modal: Overview, phases accordion, documents tab, and session summaries per feature
- Phase & Task Tracking: Accordion phase view with real-time task checklist and deferred caveat indicators
- Search & Filtering: Search by name, filter by category, status, and deferred state with sort controls
- Session Correlation: Feature-linked session chips surface workload and cache share context
- Deferred Task Tracking: Features with terminal-complete deferred steps land in Done with caveat badge

### Planning Control Plane

- **Planning Home**: Hero stats, metrics strip, artifact chips, and the planning corpus overview
- **Planning Graph**: Lane-based graph with DocChips, totals cells, and dependency-aware execution context
- Triage Inbox: Blocked, mismatch, stale, and ready-to-promote tabs for fast cleanup
- Live Agent Roster: Running and idle agents with state dots and live task context
- Feature Drawer: Lineage strip, SPIKE tiles, inline OQ resolution, dependency DAG, and execution actions

### Project Management

- **Dynamic Project Switching**: Instantly switch between multiple local projects from the sidebar
- Project Context Config: Typed path-source configuration for sessions, plans, and progress tracking
- Project Creation: Add projects with metadata and path roots persisted for future sessions

### Plan Catalog

- **Card Grid View**: Visual overview of PRDs, RFCs, and architecture docs in scannable card format
- Folder Explorer: 3-pane IDE-style file explorer for navigating documentation hierarchies
- Document Modal: Tabbed modal with Summary, Delivery, Relationships, Content, and Timeline views
- Dependency-Aware Document Views: Plan cards and the document modal surface family lineage, sequence order, blocked-by links, and board navigation
- Shared Viewer Rendering: Documents, plans, reports, and task sources share one formatted content shell with frontmatter-aware markdown rendering
- Inline Document Editing: Edit plan documents in-modal with local save and GitHub write-back support

### Codebase Explorer

- **Project File Tree**: Full project tree with gitignore-aware filtering and safety excludes
- File Correlations: Per-file session involvement, feature links, document references, and activity
- Cross-Surface Navigation: Deep-link from files into sessions, features, and plan documents for full context

### Settings

- **Alert Rules Engine**: Persisted threshold-based alerts with activate/deactivate toggle controls
- Projects Tab: Per-project path editors, typed source selection, and testing configuration
- Integrations Tab: SkillMeat and GitHub sub-tabs for token validation and workspace controls
- Telemetry Exporter: Worker-side outbound queue, SAM push controls, queue-depth visibility, and disabled-state monitoring
- AI Pricing Catalog: Global platform pricing with provider sync, exact-model rows, and manual overrides

### Execution Workbench

- **Execution Workbench**: Feature-scoped execution with safety pipeline, env profiles, and run history
- **Recommended Stack**: Confidence-scored workflow suggestions based on historical outcomes and SkillMeat definitions
- Dependency-Aware Review: The workbench shows execution gates, family position, blocked-by evidence, and navigation back to board, plans, sessions, and analytics
- Run Launch UX: Pre-run review modal with editable command, working directory, and env profile selection
- Safety Pipeline: Allow, approval-required, and deny command policies for auditable run lifecycles
- Run History & Output: Streamed terminal output with run history, active run metadata, cancel, and retry
- Embedded Workflow Intelligence: Feature-scoped leaderboard with failure patterns and direct registry handoff
- Execution API: Persistent run events and approval workflow through dedicated backend endpoints

### Workflow Registry

- **Workflow Catalog**: Searchable catalog with correlation-state filters and keyboard navigation
- **Workflow Detail**: Composition summary, effectiveness scores, issue cards, and representative sessions
- Workflow Identity: Correlation state (strong/hybrid/weak), family refs, and SkillMeat resolution metadata
- Cross-Surface Navigation: Registry actions open SkillMeat workflows, bundles, and representative sessions

### Agentic SDLC Intelligence

- **SkillMeat Sync**: Read-only cache for artifact, workflow, context-module, and bundle definitions
- Observed Stack Extraction: Backfills historical sessions into stack observations against cached SkillMeat definitions
- Canonical Transcript Intelligence: Local SQLite stays cache-oriented while enterprise Postgres acts as the canonical transcript-intelligence store
- Approval-Gated Memory Drafts: CCDash can draft SkillMeat memory candidates from session intelligence, while publication remains operator-approved
- Operator Tooling: CLI script to sync definitions, backfill observations, and recompute workflow rollups

### Platform Support

- **Claude Code**: Native JSONL parsing with sidecar enrichment for todos, tasks, teams, and tool results
- Codex: JSONL payload parsing with tool/result correlation and signal extraction
- Platform Registry: Centralized parser routing for adding platforms without changing API/UI contracts


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
| `npm run build:docs` | Build the static GitHub Pages artifact with `/CCDash/` base path |
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

### CLI, API, and MCP

The same operator queries are available through REST, CLI, and MCP:

| Capability | REST | CLI | MCP |
|-----------|------|-----|-----|
| Project status | `GET /api/agent/project-status` | `ccdash status project` | `ccdash_project_status` |
| Feature forensics | `GET /api/agent/feature-forensics/{feature_id}` | `ccdash report feature <feature_id>` | `ccdash_feature_forensics` |
| Workflow diagnostics | `GET /api/agent/workflow-diagnostics` | `ccdash workflow failures` | `ccdash_workflow_failure_patterns` |
| After-action report | `POST /api/agent/reports/aar` | `ccdash report aar --feature <feature_id>` | `ccdash_generate_aar` |

See [`docs/guides/standalone-cli-guide.md`](docs/guides/standalone-cli-guide.md), [`docs/guides/cli-user-guide.md`](docs/guides/cli-user-guide.md), and [`docs/guides/mcp-setup-guide.md`](docs/guides/mcp-setup-guide.md).

### Deployment Modes

| Mode | Command | Guide |
|------|---------|-------|
| Local container | `npm run docker:local:up` | [`docs/guides/containerized-deployment-quickstart.md`](docs/guides/containerized-deployment-quickstart.md) |
| Enterprise split API/worker/frontend | `npm run docker:enterprise:up` | [`deploy/runtime/README.md`](deploy/runtime/README.md) |
| Enterprise with bundled Postgres | `npm run docker:postgres:up` | [`docs/guides/storage-profiles-guide.md`](docs/guides/storage-profiles-guide.md) |

For full setup, troubleshooting, and deployment guidance, see [`docs/guides/setup.md`](docs/guides/setup.md), [`docs/guides/runtime-storage-and-performance-quickstart.md`](docs/guides/runtime-storage-and-performance-quickstart.md), and [`docs/README.md`](docs/README.md).

---

## Architecture

CCDash is a full-stack local-first application with a split frontend/backend design.

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite (port 3000) |
| Styling | Tailwind CSS (Slate dark mode) |
| Charts | Recharts (Area, Bar, Pie, Line, Composed) |
| Routing | React Router DOM v7 (HashRouter) |
| Backend | Python FastAPI (port 8000) |
| Database | Async SQLite (default) or PostgreSQL |
| AI | Google Gemini SDK (`@google/genai`) |

### Data Flow

```
Session JSONL files + Markdown docs
          ↓
    backend/parsers/        ← Parse filesystem artifacts
          ↓
  db/sync_engine.py         ← Sync parsed data into cache DB
          ↓
  db/repositories/          ← Data access layer
          ↓
    routers/ (REST API)     ← Expose via /api/* endpoints
          ↓
  services/apiClient.ts     ← Frontend typed API client
          ↓
    React contexts + UI     ← Shell providers feed components
```

### Key Directories

```
.                           ← Frontend root (App.tsx, types.ts, constants.ts)
├── components/             ← Page-level UI components
├── contexts/               ← Shell state providers (session, entity, runtime)
├── services/               ← Domain API helpers and typed client
└── backend/
    ├── parsers/            ← Session JSONL + document + progress parsers
    ├── routers/            ← REST API route handlers
    ├── services/           ← Business logic (codebase explorer, execution)
    ├── db/                 ← Connection, migrations, sync engine, repositories
    ├── runtime/            ← Runtime profiles + FastAPI app bootstrap
    └── observability/      ← OpenTelemetry + Prometheus instrumentation
```

### Multi-Project Support

Projects are defined in `projects.json`. Each project has typed path-source configuration for session logs, plan documentation, and progress tracking — supporting local filesystem roots, project-relative roots, and GitHub-backed repo paths.

See [`CLAUDE.md`](CLAUDE.md) for full architecture conventions and development guidelines.

---

## Data Models

### Feature
The primary unit of delivery. Aggregates linked documents (PRDs, implementation plans, reports), implementation phases with granular tasks, and related feature variants. Includes rollup metadata for priority, risk, complexity, and execution readiness.

### AgentSession
The atomic unit of work. Contains the conversation/tool execution stream, impact history, updated files, linked artifacts (skills, commands, agents, hooks, test runs), and structured forensic payloads including queue pressure, resource footprint, and subagent topology.

### ProjectTask
A specific unit of implementation with status mapping (pending, in-progress, review, completed, deferred) and estimated effort cost.

### PlanDocument
Markdown documentation with typed identity/classification metadata, canonical delivery fields, and normalized linking for features, related docs, commits, and PRs.

---

## Documentation

| Guide | Audience |
|-------|---------|
| [`docs/README.md`](docs/README.md) | Documentation home and launch point |
| [`docs/guides/setup.md`](docs/guides/setup.md) | Setup, troubleshooting, and local development |
| [`docs/guides/containerized-deployment-quickstart.md`](docs/guides/containerized-deployment-quickstart.md) | Containerized local and hosted deployment quickstart |
| [`docs/guides/standalone-cli-guide.md`](docs/guides/standalone-cli-guide.md) | Standalone CLI install, targets, auth, commands, and troubleshooting |
| [`docs/guides/mcp-setup-guide.md`](docs/guides/mcp-setup-guide.md) | MCP server setup and validation |
| [`docs/guides/execution-workbench.md`](docs/guides/execution-workbench.md) | End-user execution workflow |
| [`docs/guides/planning-control-plane-guide.md`](docs/guides/planning-control-plane-guide.md) | Planning graph, triage, artifact, and feature workflow |
| [`docs/guides/agentic-sdlc-intelligence.md`](docs/guides/agentic-sdlc-intelligence.md) | Workflow intelligence and recommended-stack usage |
| [`docs/guides/session-usage-attribution.md`](docs/guides/session-usage-attribution.md) | Attribution semantics and interpretation |
| [`docs/guides/telemetry-exporter-guide.md`](docs/guides/telemetry-exporter-guide.md) | Telemetry exporter setup and operations |
| [`docs/schemas/document_frontmatter/README.md`](docs/schemas/document_frontmatter/README.md) | Document frontmatter contracts |

---

**v0.2.0** — Released Apr 29, 2026 | Licensed under Business Source License 1.1 | Change license: Apache 2.0 on 2028-04-27

---

## Contributing

### Development Setup

Follow the [Getting Started](#getting-started) section to set up your local environment. The full stack runs with `npm run dev`.

### Running Tests

**Frontend** (Vitest):
```bash
npm run test
```

**Backend** (pytest):
```bash
# Full test suite
backend/.venv/bin/python -m pytest backend/tests/ -v

# Single test file
backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v

# Tests matching a pattern
backend/.venv/bin/python -m pytest backend/tests/ -k "test_model_identity" -v
```

### Contribution Workflow

1. Fork the repository and create a feature branch: `git checkout -b feature/my-feature`
2. Follow existing patterns — check [`CLAUDE.md`](CLAUDE.md) for architecture conventions and layering rules
3. Run both frontend and backend tests before opening a PR
4. Add tests for new backend logic; add Vitest tests for new frontend utilities
5. Document new features in the appropriate `docs/` guide
6. Open a pull request with a clear description of what changed and why

### Code Standards

- **Backend**: Routers call services/repositories only — no raw SQL in routers. Follow the layered architecture documented in `CLAUDE.md`.
- **Frontend**: All shared TypeScript interfaces live in `types.ts`. Import from `@/types`.
- **Observability**: New backend endpoints should include appropriate OpenTelemetry spans where relevant.

See [`CLAUDE.md`](CLAUDE.md) for the full development reference.
