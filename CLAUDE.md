# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- **Planning design tokens**: `planning-tokens.css` defines the OKLCH token system for planning surfaces. Planning primitives live in `components/Planning/primitives/`.
- **Planning modal-first navigation**: Route helpers in `lib/planning-routes.ts` enforce planning-page-local modals for features/artifacts. See feature guide at `.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md`.
- **Planning browser cache (SWR + LRU)**: Active-first, bounded, stale-while-revalidate cache in `services/planning.ts`. Invalidates on session/doc/link changes. See feature guide for cache patterns.
- **Planning summary payload**: Backend `statusCounts`, `ctxPerPhase`, `tokenTelemetry` fields on planning query responses. See implementation plan § Data Contracts.
- **Feature surface architecture (v2)**: Layered list → rollup → modal-section contracts with two-tier browser cache and unified invalidation bus. See `docs/guides/feature-surface-architecture.md` for hooks, cache policy, performance budgets, and migration patterns.
- **Planning session board**: `PlanningAgentSessionBoard` renders Kanban-style agent session cards grouped by state/feature/phase/agent/model. Backend queries at `backend/application/services/agent_queries/planning_sessions.py` + `planning.py` (next-run preview). Endpoints: `/api/agent/planning/session-board`, `/api/agent/planning/next-run-preview/{feature_id}`. Feature flags: `CCDASH_PLANNING_CONTROL_PLANE_ENABLED` (parent), `CCDASH_NEXT_RUN_PREVIEW_ENABLED` (preview, default true). Prompt context tray is copy/preview-only.
- **Runtime smoke gate**: For UI or frontend changes, start the dev server and perform a browser smoke check before marking a phase complete. If runtime is unavailable, Phase N cannot be marked `completed` without an explicit `runtime_smoke: skipped` field and reason; a clean unit-test pass is not a substitute.
- **Resilience-by-default**: Every new optional backend field requires an explicit FE fallback AC. Missing is a contract state, not a bug.
- **Memory guard flag**: `VITE_CCDASH_MEMORY_GUARD_ENABLED` (default true) gates frontend memory hardening (transcript ring-buffer cap, document pagination cap, in-flight request GC).
- **Incremental link rebuild**: `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (default false) enables scoped link-rebuild dispatch on partial syncs.
- **Light-mode startup sync**: `CCDASH_STARTUP_SYNC_LIGHT_MODE` (default false) enables manifest-based filesystem scan skip on unchanged paths.

---

## Operating Procedures

### Prime Directives

| Directive | Implementation |
|-----------|---------------|
| **Delegate everything** | Opus reasons & orchestrates; subagents implement |
| Token efficient | Symbol system, codebase-explorer, CLI-first status updates |
| Rapid iteration | PRD → plan → phase → code → verify |
| No over-architecture | YAGNI until proven |
| **Seam integrity** | Cross-owner seams are a named deliverable, not an emergent property |

### Opus Delegation Principle

**You are Opus. Tokens are expensive. You orchestrate; subagents execute.**

- ✗ **Never** write code directly (Read/Edit/Write for implementation)
- ✗ **Never** do token-heavy exploration yourself
- ✗ **Never** read full implementation files before delegating
- ✓ **Always** delegate implementation to specialized subagents
- ✓ **Always** use `codebase-explorer` (or Explore) for pattern discovery
- ✓ **Focus** on reasoning, analysis, planning, orchestration, and commits

**Delegation Pattern:**

```text
1. Analyze task → identify what needs to change
2. Delegate exploration → codebase-explorer finds files/patterns
3. Read progress YAML → get assigned_to and batch strategy
4. Delegate implementation → parallel Task() calls
5. Update progress → CLI scripts mark tasks complete
6. Commit → only direct action Opus takes
```

**File context for subagents**: Provide file paths, not file contents. Subagents read files themselves. Only read files directly when planning decisions require understanding current state.

**When you catch yourself about to edit a file**: STOP. Delegate instead.

### Documentation Policy

**Allowed:**

- `/docs/` → user/dev/architecture docs (with frontmatter where applicable)
- `.claude/progress/[prd-slug]/phase-N-progress.md` → ONE per phase (YAML+Markdown hybrid, schema_version: 2)
- `.claude/worknotes/[prd-slug]/` → context notes and investigation scratch per PRD
- `CHANGELOG.md` → user-facing changes; populated via `/release:bump` + `changelog-sync`

**Prohibited:**

- Debugging summaries as standalone files → use git commit messages
- Multiple progress files per phase
- Daily/weekly reports
- Session notes committed as docs

### Command–Skill Bindings

**Commands do not automatically load skills.** When executing `/dev:*`, `/fix:*`, `/plan:*`, or other workflow commands, you MUST explicitly invoke the required skill via the `Skill` tool before proceeding.

| Command                    | Required Skills                                       | Invoke First                                                            | Post-load Hook                                                                                                                          |
| -------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `/dev:execute-phase`       | dev-execution, artifact-tracking                      | `Skill("dev-execution")` then `Skill("artifact-tracking")`              | Before phase-exit, run `validate-phase-completion.py` and `ac-coverage-report.py`; block `status: completed` on any error               |
| `/dev:quick-feature`       | dev-execution                                         | `Skill("dev-execution")`                                                |                                                                                                                                         |
| `/dev:implement-story`     | dev-execution, artifact-tracking                      | `Skill("dev-execution")` then `Skill("artifact-tracking")`              |                                                                                                                                         |
| `/dev:complete-user-story` | dev-execution, artifact-tracking                      | `Skill("dev-execution")` then `Skill("artifact-tracking")`              |                                                                                                                                         |
| `/dev:create-feature`      | dev-execution                                         | `Skill("dev-execution")`                                                |                                                                                                                                         |
| `/plan:plan-feature`       | planning                                              | `Skill("planning")`                                                     | After plan generation, run `ac-coverage-report.py --dry`; block `status: approved` if any AC lacks `target_surfaces`                   |
| `/plan:*`                  | planning                                              | `Skill("planning")`                                                     |                                                                                                                                         |
| `/fix:debug`               | debugging (+ planning, artifact-tracking if critical) | `Skill("debugging")` then conditionally the others                      | If prompt contains post-incident phrases ("Codex had to patch", "gaps after merge", "we missed", "regression after phase X"), auto-invoke debugging skill's post-incident retrospective mode |
| `/release:pr`              | release, changelog-sync                               | `Skill("release")` then `Skill("changelog-sync")`                       |                                                                                                                                         |
| `/mc`                      | meatycapture-capture (self-contained)                 | no additional skills needed                                             |                                                                                                                                         |

**Enforcement**: First action after receiving a listed command is calling `Skill()` for each required skill. Do not proceed with any other actions until skills are loaded. Referenced file paths inside skill prompts are NOT auto-read — the skill load is what brings them in.

---

## Agent Delegation

**Mandatory**: All implementation work is delegated. Opus orchestrates only.

### Model Selection

| Model | Use When |
|-------|----------|
| **Opus 4.7** | Orchestration, deep reasoning, architectural decisions, cross-system debugging |
| **Sonnet 4.6** | Implementation, review, moderate reasoning (DEFAULT for subagents) |
| **Haiku 4.5** | Mechanical search, extraction, simple queries, doc writing |

Default: Sonnet 4.6 for subagents. Escalate to Opus only when the task genuinely requires deep reasoning.

### Multi-Model Integration (opt-in supplements)

External models are execution targets; Claude Opus remains the sole orchestrator.

| Capability | Model | Trigger |
|-----------|-------|---------|
| Plan review / second opinion | GPT-5.3-Codex via `codex` skill | Opt-in checkpoint before large changes |
| PR cross-validation / web research | Gemini 3.1 Pro/Flash via `gemini-cli` skill | Current web info; alternative perspective |
| Debug escalation | GPT-5.3-Codex | After 2+ failed Claude debug cycles |
| Scaffold / bounded subtasks | IBM Bob Shell via `bob-shell-delegate` | Drafting, scaffolding, exploration |
| Image generation | Nano Banana / Nano Banana Pro | Task requires image output |
| Video generation | Sora 2 via `sora` skill | Explicit request |

**Disagreement protocol**: When models conflict, tests decide — not model preference. CI is the neutral arbiter.

### Background Execution

| Parameter | Purpose |
|-----------|---------|
| `run_in_background: true` | Launch agent without blocking |
| `TaskOutput(task_id)` | Retrieve results (blocking) |
| `TaskOutput(task_id, block: false)` | Check status without waiting |

**Use background** for: 5+ independent tasks, productive work to do while waiting, long-running research.
**Do not use background** for: 2–3 small tasks, immediately-needed results, sequential-dependency tasks.

**Critical rule — file-writing agents**: Do NOT call `TaskOutput()` on background agents that wrote files. Verify their work on disk instead (read the file, grep for the change, run the test). Pulling their transcript defeats the parallelism gain.

### Context Budget Discipline

**Budget**: ~52K baseline leaves ~148K for work. Aim for ~25–30K per phase.

**Key rules:**
- Task prompts < 500 words (paths, not contents)
- Don't explore work you'll delegate — let the subagent do it
- Always scope `Glob` with a `path`
- No full-file reads before a delegation decision is made
- Verify background-agent output on disk, not via `TaskOutput()`

---

## Orchestration & Progress Tracking

**Reference**: Use the `artifact-tracking` skill for anything beyond a single-task status flip.

### File Locations

| Type | Location | Limit |
|------|----------|-------|
| Progress | `.claude/progress/[prd-slug]/phase-N-progress.md` | ONE per phase |
| Context / worknotes | `.claude/worknotes/[prd-slug]/` | ONE context.md per PRD |
| PRD | `docs/project_plans/PRDs/**/[prd-slug].md` | ONE per feature |
| Implementation plan | `docs/project_plans/implementation_plans/**/[prd-slug].md` | ONE per PRD |

Task IDs in progress YAML use the `T{phase}-{nnn}` convention (e.g., `T0-001`, `T7-012`). Match whatever the phase file declares.

### CLI-First Updates (0 agent tokens)

Four scripts under `.claude/skills/artifact-tracking/scripts/`:

```bash
# Single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-7-progress.md \
  -t T7-003 -s completed

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-7-progress.md \
  --updates "T7-001:completed,T7-002:completed,T7-003:in_progress"

# Arbitrary field (overall_progress, completion_estimate, etc.)
python .claude/skills/artifact-tracking/scripts/update-field.py \
  -f FILE --field overall_progress --value 85

# Plan / PRD status lifecycle (draft → approved → in-progress → completed)
python .claude/skills/artifact-tracking/scripts/manage-plan-status.py \
  --file docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md \
  --status in-progress
```

**Use agents only for**: creating new progress files, status updates that need context/notes, recording blockers, validation after phase completion.

### Orchestration Workflow

1. **Read phase YAML frontmatter** → get `parallelization.batch_N` and `tasks[].assigned_to` / `assigned_model`
2. **Execute batch in parallel** → single message with multiple `Task()` calls (one per independent task)
3. **Update via CLI** → `update-batch.py` after tasks complete (verify on disk first for background agents)
4. **Validate** → senior-code-reviewer / task-completion-validator before marking phase complete

### Token Efficiency

| Operation | Agent-driven | CLI-first | Savings |
|-----------|--------------|-----------|---------|
| Single status update | ~25KB | ~50 bytes | 99.8% |
| Batch update (5 tasks) | ~50KB | ~100 bytes | 99.8% |
| Query blockers | ~75KB | ~3KB | 96% |

---

## Progressive Disclosure Context

Load context in this order — stop as soon as you have what you need:

1. **Runtime truth** — the code and generated artifacts
   - `backend/application/services/agent_queries/` (intelligence layer)
   - `backend/routers/` + `types.ts` (API and type shapes)
   - `ai/` generated graphs if present
2. **Root `CLAUDE.md`** — this file (scope, invariants, conventions)
3. **Authoritative spec / PRD / phase plan** for the current work
   - PRD: `docs/project_plans/PRDs/**/[prd-slug].md`
   - Plan: `docs/project_plans/implementation_plans/**/[prd-slug].md`
   - Progress: `.claude/progress/[prd-slug]/phase-N-progress.md`
4. **Distilled project context** (only if the above is insufficient)
   - `.claude/context/distilled/project-purpose-and-feature-catalog.md`
   - `.claude/context/distilled/project-fundamentals-and-design-context.md`
   - `.claude/context/distilled/research-agent-context-pack.md`
   - `.claude/context/distilled/project-opportunity-map.md`
5. **Historical plans/reports** — for rationale only; verify behavior from runtime truth, not stale plans.

**Anti-pattern**: reading deep plans before runtime truth. Plans drift. The code is the contract.

---

## `.claude/` Directory Inventory

| Path | Purpose |
|------|---------|
| `.claude/agents/` | Subagent definitions (symlink to shared SkillMeat agent roster) |
| `.claude/commands/` | Custom slash commands (symlink to SkillMeat commands) |
| `.claude/skills/` | Skills (symlink to SkillMeat skills) — `artifact-tracking`, `planning`, `dev-execution`, `debugging`, `release`, `changelog-sync`, `ccdash`, etc. |
| `.claude/progress/` | Phase progress files (one per phase per PRD) |
| `.claude/worknotes/` | PRD-scoped context and investigation notes |
| `.claude/context/distilled/` | Project-context-distiller output (feature catalog, fundamentals, opportunity map, research pack) |
| `.claude/specs/` | Project-specific specs and cross-project examples |
| `.claude/hooks/` | Project-local hook scripts |
| `.claude/findings/` | Spike / research output |
| `.claude/plans/` | Legacy / ad-hoc planning docs |

## External Systems

| System | Purpose |
|--------|---------|
| `.mcp.json` (ccdash stdio) | The in-repo CCDash MCP server — feature forensics, project status, workflow failure patterns, AAR |
| Local filesystem | Agent session JSONL logs + markdown docs (the parser source of truth) |
| SQLite / PostgreSQL cache | Derived DB cache; frontend reads from API, not filesystem directly |
