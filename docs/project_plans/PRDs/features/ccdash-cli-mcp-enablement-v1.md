---
schema_version: "1.0"
doc_type: prd
title: "CCDash CLI and MCP Enablement"
description: "Expose CCDash project intelligence through a Python CLI, an MCP server for coding agents, and new composite REST endpoints — all backed by a shared transport-neutral agent query layer."
status: draft
created: "2026-04-02"
updated: "2026-04-02"
feature_slug: "ccdash-cli-mcp-enablement"
feature_version: "v1"
prd_ref: null
plan_ref: null
owner: fullstack-engineering
contributors: ["Architecture Review Team"]
priority: high
risk_level: medium
category: "product-planning"
tags: ["cli", "mcp", "agent-tooling", "typer", "fastmcp", "agent-queries", "claude-code"]
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
related_documents:
  - docs/project_plans/ccdash-cli-mcp-enablement-plan.md
  - docs/project_plans/spikes/mcp-server-implementation-spike.md
  - docs/project_plans/spikes/cli-framework-and-packaging-spike.md
  - docs/project_plans/adrs/adr-002-mcp-server-separate-from-extension.md
  - docs/project_plans/adrs/adr-003-transport-neutral-agent-query-layer.md
  - docs/project_plans/adrs/adr-004-mcp-server-dual-transport-strategy.md
  - docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md
---

# PRD: CCDash CLI and MCP Enablement v1

## 1. Feature brief & metadata

**Feature name:** CCDash CLI and MCP Enablement

**Filepath:** `docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md`

**Date:** 2026-04-02

**Author:** Architecture Review Team

**Related plan:** `docs/project_plans/ccdash-cli-mcp-enablement-plan.md`

**Key ADRs:**
- [ADR-003: Transport-Neutral Agent Query Layer](../adrs/adr-003-transport-neutral-agent-query-layer.md)
- [ADR-004: MCP Server Dual Transport Strategy](../adrs/adr-004-mcp-server-dual-transport-strategy.md)

---

## 2. Executive summary

**Priority:** HIGH

CCDash is today a browser-only dashboard. Coding agents (Claude Code), terminal operators, and CI pipelines have no direct access to its project intelligence — they must open a browser or orchestrate multiple thin REST calls to assemble an answer. This feature closes that gap by shipping three new access surfaces backed by a single shared service layer:

1. **Agent query foundation** — a transport-neutral `backend/application/services/agent_queries/` layer with composite Pydantic DTOs covering project status, feature forensics, workflow diagnostics, and after-action reports.
2. **REST composite endpoints** — four new `/api/agent/*` routes that validate the service contracts before CLI/MCP ship.
3. **Python CLI** — a `ccdash` command (Typer-based, direct in-process) enabling shell, script, and agent-shell workflows without requiring the web server to be running.
4. **MCP server** — a FastMCP stdio server exposing four high-value tools so Claude Code and other agents can query CCDash project intelligence without leaving the editor.

MVP covers Phases 1-4. Phases 5-6 (extended tool catalog, web UI convergence) follow separately.

---

## 3. Context & background

### Current state

CCDash provides a rich FastAPI backend (`backend/routers/`) with routes covering sessions, features, analytics, projects, execution, codebase, documents, cache, and telemetry. The backend is migrating toward hexagonal architecture via `CorePorts` (`backend/application/ports/core.py`) and request-scoped application services.

Despite this foundation, all intelligence is surfaced exclusively through the browser dashboard. There is no CLI, no MCP server, and no composite "agent-ready" query surface.

### Structural gap

The main gap is not raw data availability but **packaging and abstraction**. Many routers still contain inline response-shaping logic. There is no service that answers cross-domain questions such as "summarize this project's current state" or "generate an AAR-ready feature narrative." Agents that want rich answers today must orchestrate multiple thin HTTP calls and assemble results themselves.

### Strategic fit

CCDash's long-term goal is to become the operating intelligence layer for AI-native software delivery. CLI and MCP access are a necessary step: they make CCDash's forensic data available at the point of agent decision-making, not just as a post-hoc browser artifact.

---

## 4. Problem statement

Coding agents (Claude Code), terminal operators, and CI pipelines cannot directly consume CCDash intelligence. Agents must orchestrate multiple HTTP calls to assemble a project-status answer. Operators must open the browser for quick status checks. Scripts that need structured data have no stable composite endpoint to call. This forces unnecessary context-switching and makes CCDash inaccessible in the workflows where its data is most valuable.

---

## 5. User personas

| Persona | Description | Primary access surface |
|---------|-------------|----------------------|
| **Agent developer** (primary) | Developer using Claude Code or similar AI coding agents who wants the agent to have contextual project awareness without leaving the editor | MCP tools |
| **Project operator** | Technical lead who wants quick terminal status checks, report generation, and shell-script integration | CLI |
| **Automation pipeline** | CI/CD or scheduled scripts that need structured JSON CCDash data for dashboards, alerts, or automated reporting | CLI `--json` / REST `/api/agent/*` |

---

## 6. Goals & success metrics

| Goal | Metric | Target |
|------|--------|--------|
| Agent retrieves project status via MCP in real time | Tool response latency (p95) | < 2 s |
| CLI output is pipeline-friendly | `ccdash status project --json \| jq .projectId` executes successfully | 100% of MVP commands |
| MCP tools enable agent chaining | Responses include stable IDs (`session_id`, `feature_id`, `workflow_id`) | 100% of core tools |
| Zero business logic duplication | REST, CLI, and MCP all call the same query services | Verified by architecture review |
| Query services are well-tested | Line coverage on `agent_queries/` services | > 90% |
| CLI startup is fast | Time-to-first-output for any MVP command | < 500 ms |
| Responses degrade gracefully | Stale or unavailable subsystems return structured error with `status: partial` | All query services |

---

## 7. User stories

### Epic 1: Agent query foundation

| ID | Story | Phase |
|----|-------|-------|
| US-1 | As an agent developer, I want CCDash to expose composite project intelligence through transport-neutral services, so that CLI, MCP, and REST can all serve the same rich data | 1 |
| US-2 | As a project operator, I want a "project status" summary that combines feature counts, recent session activity, cost trends, and sync freshness in one response | 1 |

### Epic 2: REST composite endpoints

| ID | Story | Phase |
|----|-------|-------|
| US-REST-1 | As an agent developer, I want `/api/agent/project-status` to return a validated composite project summary that I can call directly | 2 |
| US-REST-2 | As an automation pipeline, I want `/api/agent/feature-forensics/{feature_id}` to return complete feature history and metrics in one call | 2 |
| US-REST-3 | As an automation pipeline, I want `/api/agent/workflow-diagnostics` to return workflow effectiveness data suitable for automated alerts | 2 |
| US-REST-4 | As a project operator, I want `/api/agent/reports/aar` to generate a structured after-action report via a single POST | 2 |

### Epic 3: CLI access

| ID | Story | Phase |
|----|-------|-------|
| US-3 | As a project operator, I want to run `ccdash status project` to see current project state without opening the browser | 3 |
| US-4 | As an automation pipeline, I want `ccdash feature report <id> --json` to get structured feature data for CI integration | 3 |
| US-5 | As a project operator, I want `ccdash report aar --feature <id> --md` to generate an after-action review in markdown | 3 |
| US-6 | As an agent developer, I want `ccdash workflow failures --json` to identify problematic workflows programmatically | 3 |

### Epic 4: MCP access

| ID | Story | Phase |
|----|-------|-------|
| US-7 | As an agent developer, I want Claude Code to access `ccdash_project_status` MCP tool to understand what I'm working on | 4 |
| US-8 | As an agent developer, I want `ccdash_feature_forensics` MCP tool to get deep feature analysis during planning | 4 |
| US-9 | As an agent developer, I want `ccdash_workflow_failure_patterns` to avoid repeating ineffective approaches | 4 |
| US-10 | As an agent developer, I want `ccdash_generate_aar` to produce retrospectives from within Claude Code | 4 |

---

## 8. Functional requirements

### 8.1 Agent query foundation (Phase 1)

| ID | Requirement |
|----|-------------|
| AQ-1 | A new `backend/application/services/agent_queries/` package shall contain four service modules: `project_status.py`, `feature_forensics.py`, `workflow_intelligence.py`, `reporting.py` |
| AQ-2 | Each query service shall accept a `CorePorts` instance and a request context; it shall not depend on HTTP request objects |
| AQ-3 | Each query service shall return a typed Pydantic DTO, not a raw dict or HTTP response model |
| AQ-4 | DTOs shall include provenance fields: relevant IDs (`session_id`, `feature_id`, `workflow_id`, `document_id`), source timestamps, and a `data_freshness` indicator |
| AQ-5 | DTOs shall include a `status` field with values `ok`, `partial`, or `error` to support graceful degradation when subsystems are unavailable |
| AQ-6 | `ProjectStatusQueryService` shall aggregate: active project identity, feature counts by status, session activity (last 7 d), top workflows, cost/token totals (last 7 d), blocked or risky features, cache/sync freshness, and notable anomalies |
| AQ-7 | `FeatureForensicsQueryService` shall aggregate: feature metadata, linked docs and task progress, linked sessions with timeline, total iterations, total tokens and cost, workflow mix, rework signals, failure patterns, and a summary narrative |
| AQ-8 | `WorkflowDiagnosticsQueryService` shall aggregate: effectiveness score, session count, success/failure ratio, cost efficiency, common failure patterns, representative sessions and features |
| AQ-9 | `ReportingQueryService` shall produce a structured AAR pack: scope statement, timeline, key metrics, turning points, workflow observations, bottlenecks, successful patterns, lessons learned, and evidence links |
| AQ-10 | Shared filter/scope helpers shall normalize project scope, time windows, and entity ID resolution for reuse across all services |

### 8.2 REST composite endpoints (Phase 2)

| ID | Requirement |
|----|-------------|
| REST-1 | A new `backend/routers/agent.py` router shall be registered at the `/api/agent` prefix |
| REST-2 | `GET /api/agent/project-status` shall return a `ProjectStatusDTO` serialized as JSON; optional `?project_id=` query param |
| REST-3 | `GET /api/agent/feature-forensics/{feature_id}` shall return a `FeatureForensicsDTO` |
| REST-4 | `GET /api/agent/workflow-diagnostics` shall return a `WorkflowDiagnosticsDTO`; optional `?feature_id=` filter |
| REST-5 | `POST /api/agent/reports/aar` shall accept `{"feature_id": "...", "project_id": "..."}` and return an `AARReportDTO` |
| REST-6 | All agent endpoints shall call the `agent_queries` services directly; no inline response assembly |
| REST-7 | All agent endpoints shall be included in the OpenAPI schema with complete descriptions and example responses |

### 8.3 CLI (Phase 3)

| ID | Requirement |
|----|-------------|
| CLI-1 | The CLI shall be implemented using Typer with the root application registered as `ccdash` |
| CLI-2 | The CLI shall bootstrap its own `CorePorts` instance via a `CLIRuntimeContainer` without requiring the FastAPI web server to be running |
| CLI-3 | All commands shall support three output modes: human-readable (default), `--json`, and `--md` (where applicable); output mode shall be selectable via a global `--output` option or per-command `--json`/`--md` flags |
| CLI-4 | Query logic shall be fully separated from output rendering via an `OutputFormatter` protocol; command handlers shall never contain `print()` or format strings |
| CLI-5 | `ccdash status project` shall call `ProjectStatusQueryService` and render a project summary |
| CLI-6 | `ccdash feature report <feature-id>` shall call `FeatureForensicsQueryService` and render a feature forensics report |
| CLI-7 | `ccdash workflow failures` shall call `WorkflowDiagnosticsQueryService` filtered to failure patterns |
| CLI-8 | `ccdash report aar --feature <feature-id>` shall call `ReportingQueryService` and render a markdown AAR |
| CLI-9 | JSON output shall use Pydantic `.model_dump()` producing key names consistent with the REST API JSON keys |
| CLI-10 | The CLI shall be invocable via `python -m backend.cli` (zero-setup) and via the `ccdash` entry point after `pip install -e .` |
| CLI-11 | The `npm run setup` script shall be extended to run `pip install -e .` so the `ccdash` command is available after first-time setup |
| CLI-12 | CLI startup time (first-output) shall be < 500 ms for SQLite-backed deployments |
| CLI-13 | A global `--project <project-id>` option shall override the active project for the duration of a command |

### 8.4 MCP server (Phase 4)

| ID | Requirement |
|----|-------------|
| MCP-1 | The MCP server shall be implemented using FastMCP (`mcp>=1.8,<2`) with `backend/mcp/server.py` as the module entry point |
| MCP-2 | Stdio transport shall be the primary deployment target; the server shall be launchable via `python -m backend.mcp.server` |
| MCP-3 | The MCP server shall initialize its own `CorePorts` instance via a lazy bootstrap in `backend/mcp/bootstrap.py`; DB connection shall be deferred until first tool call |
| MCP-4 | Four core tools shall be implemented for Phase 4 MVP: `ccdash_project_status`, `ccdash_feature_forensics`, `ccdash_workflow_failure_patterns`, `ccdash_generate_aar` |
| MCP-5 | Each tool shall include a descriptive docstring suitable for agent discovery (explains inputs, outputs, and use case) |
| MCP-6 | Each tool response shall follow the standard envelope: `{"status": "ok|partial|error", "data": {...}, "meta": {"project_id": "...", "generated_at": "...", "data_freshness": "..."}}` |
| MCP-7 | All tools shall be read-only; no mutation operations shall be exposed in Phase 4 |
| MCP-8 | A `.mcp.json` file shall be added to the repository root with stdio configuration for Claude Code discovery |
| MCP-9 | Tool implementations shall call the `agent_queries` services via `CorePorts`; no tool shall contain inline query logic |
| MCP-10 | The MCP server shall operate correctly when the FastAPI web server is not running |
| MCP-11 | Tool responses shall include stable IDs in the `data` payload to enable agent chaining across tool calls |

---

## 9. Non-functional requirements

| Category | Requirement | Target |
|----------|-------------|--------|
| **Performance** | CLI startup to first output (SQLite) | < 500 ms |
| **Performance** | MCP tool response time (p95, local SQLite) | < 2 s |
| **Reliability** | Query service response when a subsystem is unavailable | Returns `status: partial` with available data; never raises an unhandled exception |
| **Freshness** | Every query service response | Includes `data_freshness` timestamp from the most recently synced data record |
| **Provenance** | Every query service response | Includes relevant entity IDs (session, feature, workflow, document) as source references |
| **Testability** | Agent query services | > 90% line coverage via pytest unit tests with mocked `CorePorts` |
| **Testability** | CLI commands | All MVP commands covered by `typer.testing.CliRunner` tests for human, JSON, and MD output modes |
| **Testability** | MCP tools | All Phase 4 tools covered by `mcp.test_client()` in-memory transport tests |
| **Compatibility** | SQLite concurrent access (web server + CLI) | Handled via existing WAL mode + `CCDASH_SQLITE_BUSY_TIMEOUT_MS` busy timeout |
| **Compatibility** | MCP SDK version | Pin to `mcp>=1.8,<2` until v2 FastMCP API stabilizes |
| **Observability** | CLI errors | Exit code non-zero on failure; error message to stderr; `--json` mode returns `{"status": "error", "message": "..."}` to stdout |
| **Security** | MCP stdio | Inherits user filesystem permissions; no additional auth required for local use |

---

## 10. Scope

### In scope (Phase 1-4, this PRD)

- `backend/application/services/agent_queries/` package with four query services and transport-neutral Pydantic DTOs
- Shared filter/scope normalization helpers
- `backend/routers/agent.py` with four composite REST endpoints at `/api/agent/*`
- `backend/cli/` package: Typer app, CLI runtime container, `OutputFormatter` protocol, four MVP commands, formatters, packaging
- `backend/mcp/` package: FastMCP server, stdio bootstrap, four core tools, `.mcp.json` configuration
- Unit tests for query services (> 90% coverage), CLI commands (CliRunner), and MCP tools (test_client)
- `pip install -e .` entry point and `npm run setup` integration

### Out of scope (deferred to Phase 5+)

| Item | Rationale |
|------|-----------|
| MCP Streamable HTTP transport | Deferred to Phase 5; stdio proves sufficient for Claude Code MVP |
| Portfolio-level analysis | Requires cross-project aggregation not yet supported by `CorePorts` |
| Write/mutation operations via CLI or MCP | Query-first design; mutations require richer concurrency and undo semantics |
| Live update streaming via MCP | Depends on SSE live-update platform maturity |
| MCP resources (`@mcp.resource()`) | Deferred to Phase 5; tools prove sufficient for initial agent workflows |
| Web UI convergence on query services | Deferred to Phase 6; requires careful router refactoring |
| Extended CLI command surface (`session`, `analytics`, `cache` commands) | Phase 5 follow-on after MVP validates patterns |

---

## 11. Architecture

### Layer model

```
Claude Code / Agent / Shell / CI
          |
  ┌───────┼───────────────────────┐
  │  MCP   │  CLI  │  REST /api/agent/*  │
  │ stdio  │ Typer │  FastAPI router     │
  └───────┼───────────────────────┘
          |
  backend/application/services/agent_queries/
  (ProjectStatusQueryService, FeatureForensicsQueryService,
   WorkflowDiagnosticsQueryService, ReportingQueryService)
          |
  backend/application/services/  (existing domain services)
          |
  CorePorts → Repositories → Database (SQLite / PostgreSQL)
```

**Key invariant:** CLI and MCP never call router functions. Routers are HTTP adapters only. All three delivery surfaces call the same `agent_queries` services.

### Proposed file structure

```
backend/
  application/
    services/
      agent_queries/
        __init__.py
        project_status.py        # ProjectStatusQueryService + ProjectStatusDTO
        feature_forensics.py     # FeatureForensicsQueryService + FeatureForensicsDTO
        workflow_intelligence.py # WorkflowDiagnosticsQueryService + WorkflowDiagnosticsDTO
        reporting.py             # ReportingQueryService + AARReportDTO
        _filters.py              # Shared scope/filter normalization helpers
  routers/
    agent.py                     # /api/agent/* composite endpoints (Phase 2)
  cli/
    __init__.py
    __main__.py                  # python -m backend.cli entry point
    main.py                      # Root Typer app, global options, sub-app registration
    runtime.py                   # CLIRuntimeContainer: bootstrap_cli(), teardown_cli()
    output.py                    # OutputMode enum, formatter selection
    commands/
      status.py                  # ccdash status project
      feature.py                 # ccdash feature report <id>
      workflow.py                # ccdash workflow failures
      report.py                  # ccdash report aar
    formatters/
      base.py                    # OutputFormatter protocol, JsonFormatter, TableFormatter, MarkdownFormatter
      features.py                # Feature report domain renderers
      projects.py                # Project status domain renderers
  mcp/
    __init__.py
    server.py                    # FastMCP instance + __main__ stdio entry point
    bootstrap.py                 # Lazy CorePorts initialization for stdio mode
    context.py                   # MCP-specific RequestContext builder
    tools/
      __init__.py                # register_tools() aggregator
      project.py                 # ccdash_project_status
      features.py                # ccdash_feature_forensics
      workflows.py               # ccdash_workflow_failure_patterns
      reports.py                 # ccdash_generate_aar
.mcp.json                        # Claude Code project-scoped MCP configuration
```

### Key design decisions

| Decision | Choice | ADR |
|----------|--------|-----|
| Query service layer | Dedicated `agent_queries/` package; not embedded in existing domain services or routers | ADR-003 |
| CLI framework | Typer (type-hint-driven, native async, CliRunner testing) | ADR-003 / CLI SPIKE |
| CLI service access | Direct in-process `CorePorts` bootstrap; no HTTP round-trip required | CLI SPIKE |
| MCP primary transport | stdio (Claude Code subprocess model; no auth, no server dependency) | ADR-004 |
| MCP secondary transport | Streamable HTTP mounted on FastAPI at `/mcp` (Phase 5) | ADR-004 |
| MCP SDK | FastMCP (`mcp>=1.8,<2`); pin below v2 until API stabilizes | MCP SPIKE |

### DTO design contract

All query service DTOs shall follow this pattern:

```python
class ProjectStatusDTO(BaseModel):
    status: Literal["ok", "partial", "error"]
    project_id: str
    project_name: str
    # ... domain fields ...
    data_freshness: datetime          # timestamp of most recently synced record
    generated_at: datetime            # when this DTO was assembled
    source_refs: list[str]            # entity IDs included as evidence
```

### MCP tool response envelope

```json
{
  "status": "ok",
  "data": { "...": "..." },
  "meta": {
    "project_id": "my-project",
    "generated_at": "2026-04-02T12:00:00Z",
    "data_freshness": "2026-04-02T11:55:00Z"
  }
}
```

### `.mcp.json` configuration (Claude Code)

```json
{
  "mcpServers": {
    "ccdash": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "CCDASH_DB_BACKEND": "sqlite",
        "CCDASH_DATA_DIR": "./data"
      }
    }
  }
}
```

---

## 12. Dependencies & assumptions

### Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| `typer>=0.12` | New Python dep | Async command support added in 0.10+; 0.12 is stable |
| `mcp>=1.8,<2` | New Python dep | Pin below v2 until FastMCP decorator API confirmed stable |
| `CorePorts` / `build_core_ports()` | Existing internal | CLI and MCP bootstrap use the same composition function as the web runtime |
| SQLite WAL mode | Existing config | Required for CLI + web server concurrent access; already configured |
| Existing application services | Existing internal | `agent_queries` services orchestrate across `SessionFacetService`, `AnalyticsOverviewService`, `DocumentQueryService`, `FeatureExecutionApplicationService` |
| Phase 1 `agent_queries` | Sequencing | Phases 2, 3, and 4 all depend on Phase 1 services being stable |

### Assumptions

- The `CorePorts` composition API (`build_core_ports()`) remains stable through Phase 4.
- SQLite WAL mode with the existing 30 s busy timeout handles concurrent CLI + web server read access without contention.
- The active project is resolvable from `projects.json` in the repo root; the CLI and MCP server use this as the default scope unless a `--project` flag or env var override is provided.
- MCP SDK v2 breaking changes will not affect the `@mcp.tool()` and `@mcp.resource()` decorator API (FastMCP's stable surface); pin `mcp>=1.8,<2` as a precaution.
- Phase 5 (Streamable HTTP MCP transport, extended tool catalog, resources) and Phase 6 (web UI convergence) are out of scope for this PRD and will be tracked separately.

---

## 13. Risks & mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `agent_queries` services become a logic "grab bag" over time | Medium | Medium | Strict admission criteria: if a query does not compose multiple domains, it belongs in the existing single-domain service |
| CLI startup > 500 ms due to heavy imports | Medium | Medium | Lazy imports in command modules; profile on first implementation; target 500 ms strictly |
| MCP SDK v2 breaks FastMCP decorator API | Medium | Low | Pin `mcp>=1.8,<2`; FastMCP decorator API confirmed stable per spike research |
| SQLite lock contention (CLI + web server concurrently) | Medium | Low | WAL mode + existing 30 s busy timeout; CLI operations are short read transactions |
| Tool descriptions are inadequate for agent discovery | High | Medium | Treat tool docstrings as UX; iterate based on real Claude Code testing before shipping |
| Typer async support regresses | Low | Low | Trivial fallback: `asyncio.run()` wrapper is 3 lines; mitigates any Typer async regression |
| Query DTO shape diverges between CLI JSON and REST JSON | Medium | Medium | Both use Pydantic `.model_dump()` on the same DTO classes; divergence is structurally prevented |
| Phase 2 REST endpoints reveal service contract issues before CLI/MCP ship | Low — this is good | — | Phase 2 is explicitly the validation gate for service contracts; fix issues before Phase 3 |

---

## 14. Phasing

| Phase | Goal | Deliverables | Sequencing constraint |
|-------|------|--------------|-----------------------|
| **1** | Agent query foundation | `agent_queries/` services, transport-neutral DTOs, shared filter helpers, unit tests | Unblocked |
| **2** | REST composite endpoints | `backend/routers/agent.py`, four `/api/agent/*` routes, OpenAPI docs | Requires Phase 1 |
| **3** | CLI MVP | `backend/cli/` package, four MVP commands, formatters, packaging, CliRunner tests | Requires Phase 1; Phase 2 recommended |
| **4** | MCP MVP | `backend/mcp/` package, four core tools, `.mcp.json`, MCP test_client tests | Requires Phase 1; Phase 2 recommended |
| **5** | Extended tools & resources | Streamable HTTP transport, MCP resources, extended CLI command surface, portfolio analysis | Out of scope (this PRD) |
| **6** | Web UI convergence | Router refactoring to consume query services; unified reporting across all surfaces | Out of scope (this PRD) |

Phases 3 and 4 may proceed in parallel once Phase 1 is stable. Phase 2 serves as a contract-validation gate and is strongly recommended before Phase 3/4 ship.

---

## 15. Acceptance criteria

### Phase 1 — Agent query foundation

| ID | Criterion |
|----|-----------|
| AC-1.1 | `ProjectStatusQueryService.get_status(context, ports)` returns a `ProjectStatusDTO` with `status`, `project_id`, `feature_counts`, `recent_session_summary`, `cost_last_7d`, `sync_freshness`, and `data_freshness` fields |
| AC-1.2 | `FeatureForensicsQueryService.get_forensics(context, ports, feature_id)` returns a `FeatureForensicsDTO` with session links, iteration count, token totals, workflow mix, and failure pattern indicators |
| AC-1.3 | `WorkflowDiagnosticsQueryService.get_diagnostics(context, ports)` returns a `WorkflowDiagnosticsDTO` with per-workflow effectiveness scores, session counts, and failure patterns |
| AC-1.4 | `ReportingQueryService.generate_aar(context, ports, feature_id)` returns an `AARReportDTO` with scope, timeline, metrics, turning points, and evidence links |
| AC-1.5 | All four services return `status: "partial"` (not raise an exception) when a dependent subsystem returns no data or an error |
| AC-1.6 | All four services have > 90% line coverage measured by pytest with mocked `CorePorts` |
| AC-1.7 | All DTOs include `data_freshness`, `generated_at`, and `source_refs` fields |

### Phase 2 — REST composite endpoints

| ID | Criterion |
|----|-----------|
| AC-2.1 | `GET /api/agent/project-status` returns HTTP 200 with a valid `ProjectStatusDTO` JSON body; returns HTTP 200 with `status: "partial"` if sync data is stale |
| AC-2.2 | `GET /api/agent/feature-forensics/{feature_id}` returns HTTP 200 for a known feature ID; returns HTTP 404 for an unknown ID |
| AC-2.3 | `GET /api/agent/workflow-diagnostics` returns HTTP 200 with at least one workflow entry when sessions exist |
| AC-2.4 | `POST /api/agent/reports/aar` with a valid `feature_id` returns HTTP 200 with an `AARReportDTO` |
| AC-2.5 | All four endpoints appear in the OpenAPI schema at `/docs` with descriptions and example responses |
| AC-2.6 | No agent endpoint contains inline query logic; all delegate to `agent_queries` services |

### Phase 3 — CLI

| ID | Criterion |
|----|-----------|
| AC-3.1 | `ccdash status project` exits 0 and renders a project summary to stdout |
| AC-3.2 | `ccdash status project --json` exits 0 and outputs valid JSON with a `project_id` key |
| AC-3.3 | `ccdash feature report <id> --json` exits 0 and outputs valid JSON with `feature_id`, `session_count`, and `total_cost` keys |
| AC-3.4 | `ccdash workflow failures --json` exits 0 and outputs valid JSON array of workflow entries with `workflow_id` and `failure_rate` keys |
| AC-3.5 | `ccdash report aar --feature <id> --md` exits 0 and outputs a markdown document beginning with `#` |
| AC-3.6 | All MVP commands exit non-zero and write an error message to stderr when called against an empty or unreachable database |
| AC-3.7 | `python -m backend.cli --help` executes without error |
| AC-3.8 | `ccdash --help` executes without error after `pip install -e .` |
| AC-3.9 | Time from `ccdash status project --json` invocation to first byte of output is < 500 ms on a SQLite-backed development machine |
| AC-3.10 | All commands are covered by `typer.testing.CliRunner` tests for human, JSON, and MD output modes |

### Phase 4 — MCP server

| ID | Criterion |
|----|-----------|
| AC-4.1 | `python -m backend.mcp.server` starts without error when SQLite database exists |
| AC-4.2 | `ccdash_project_status` tool returns a valid response envelope with `status`, `data`, and `meta` keys when called via `mcp.test_client()` |
| AC-4.3 | `ccdash_feature_forensics` tool accepts `feature_id` parameter and returns feature data including `session_count` and `total_cost` |
| AC-4.4 | `ccdash_workflow_failure_patterns` tool returns an array of workflow failure entries with `workflow_id` and `failure_count` |
| AC-4.5 | `ccdash_generate_aar` tool accepts `feature_id` and returns an AAR report with a `narrative` field |
| AC-4.6 | All tools return `status: "partial"` (not raise an exception) when data is unavailable |
| AC-4.7 | `.mcp.json` exists at the repository root and points to `python -m backend.mcp.server` with stdio transport |
| AC-4.8 | Claude Code discovers and lists CCDash tools after opening the repository (manual verification) |
| AC-4.9 | All four tools are covered by `mcp.test_client()` unit tests and mocked `CorePorts` integration tests |
| AC-4.10 | The MCP server operates correctly when the FastAPI web server (`npm run dev:backend`) is not running |

---

## 16. Open questions

| ID | Question | Impact | Owner |
|----|----------|--------|-------|
| OQ-1 | Should the CLI have a dedicated `"cli"` `RuntimeProfileName` value, or reuse the existing `"local"` profile with sync/jobs disabled? A named profile is self-documenting but requires a one-line `Literal` type change and any exhaustive match updates. | Low | Backend engineering |
| OQ-2 | In MCP stdio mode, how is the active project determined? Options: (a) read `projects.json` active field, (b) `CCDASH_ACTIVE_PROJECT` env var, (c) expose a `ccdash_set_active_project` tool. | Medium (affects all tools) | Architecture |
| OQ-3 | Should MCP tool pagination use explicit `limit`/`offset` parameters, or should tools return all results up to a generous default limit (e.g., 50)? Agents handle pagination poorly; default limits are preferred. | Low | MCP tool design |
| OQ-4 | Should `ccdash` be a top-level Python package or remain under `backend/cli/`? Top-level enables standalone distribution in future; `backend/cli/` is simpler today. | Low (defer) | Backend engineering |
| OQ-5 | Should a `CCDashAgentAccessService` facade wrap all four query services for convenience? ADR-003 defers this; revisit after Phase 4 if tool call patterns suggest it. | Low | Architecture |

---

## 17. Related documents

| Document | Relationship |
|----------|-------------|
| [CCDash CLI and MCP Enablement Plan](../../ccdash-cli-mcp-enablement-plan.md) | Architecture vision and phasing source |
| [MCP Server Implementation SPIKE](../../spikes/mcp-server-implementation-spike.md) | MCP SDK assessment, transport analysis, tool design patterns |
| [CLI Framework and Packaging SPIKE](../../spikes/cli-framework-and-packaging-spike.md) | Typer vs Click/argparse analysis, async bridging, packaging, testing |
| [ADR-002: MCP Server as Separate Package](../adrs/adr-002-mcp-server-separate-from-extension.md) | Decision to keep MCP server independent of VSCode extension |
| [ADR-003: Transport-Neutral Agent Query Layer](../adrs/adr-003-transport-neutral-agent-query-layer.md) | Decision to create `agent_queries/` service layer |
| [ADR-004: MCP Server Dual Transport Strategy](../adrs/adr-004-mcp-server-dual-transport-strategy.md) | Decision for stdio primary, Streamable HTTP secondary |
| [PRD: VSCode CCDash Extension v1](./vscode-ccdash-extension-v1.md) | Complementary IDE surface; Phase 3 of that PRD integrates MCP tools from this PRD |
