# CCDash CLI and MCP Enablement Plan

## Goal

Enable CCDash insights to be consumed directly by coding agents through a maintainable, modular access architecture that supports:
- human-facing web UX
- scriptable CLI workflows
- agent-facing MCP tools

The design should let agents and operators retrieve project status, feature history, workflow effectiveness, usage attribution, execution context, and forensic evidence without coupling those access patterns to the existing React UI.

---

## Executive Summary

CCDash already has strong foundations for this initiative:

- the backend exposes a large set of HTTP endpoints across sessions, features, analytics, projects, execution, cache, telemetry, integrations, and codebase exploration
- the backend is moving toward a hexagonal architecture via [`CorePorts`](backend/application/ports/core.py) and request-scoped application services
- key agent-relevant domains already exist in the API and models, especially sessions, documents, features, analytics, execution, and usage attribution
- runtime composition is centralized in [`RuntimeContainer`](backend/runtime/container.py), which is a good place to attach new delivery surfaces

The main gap is not raw data availability, but packaging and abstraction. Today, many routes still perform response shaping inside routers, and some routers still depend directly on legacy globals like [`project_manager`](backend/routers/codebase.py) or raw DB access. A CLI or MCP layer built directly atop current routers would work, but would be harder to maintain.

The recommended approach is to introduce a dedicated **agent-access application layer** that sits above repositories and below delivery channels. Then expose that layer through:
- REST API adapters
- a local CLI
- an MCP server

This keeps transport concerns separate from query semantics and lets CCDash evolve into a multi-surface intelligence platform rather than a UI-first dashboard with add-on command wrappers.

---

## Current Architecture Findings

### Strong existing foundations

1. **Hexagonal port system already exists**
   - [`CorePorts`](backend/application/ports/core.py) centralizes access to storage, workspace registry, authorization, jobs, and integrations.
   - [`resolve_application_request()`](backend/application/services/common.py) and related helpers already standardize request-scoped app access.

2. **Rich agent-relevant domains already exist**
   - Sessions and transcripts via [`backend/routers/api.py`](backend/routers/api.py)
   - Analytics and usage attribution via [`backend/routers/analytics.py`](backend/routers/analytics.py)
   - Features and feature execution via [`backend/routers/features.py`](backend/routers/features.py)
   - Execution workflows via [`backend/routers/execution.py`](backend/routers/execution.py)
   - Codebase exploration via [`backend/routers/codebase.py`](backend/routers/codebase.py)
   - Projects and path resolution via [`backend/routers/projects.py`](backend/routers/projects.py)
   - Live updates via [`backend/routers/live.py`](backend/routers/live.py)

3. **Shared typed models already exist**
   - [`AgentSession`](backend/models.py:154)
   - [`PlanDocument`](backend/models.py)
   - [`Project`](backend/models.py)
   - [`SessionUsageAggregateResponse`](backend/models.py:409)
   - [`SessionUsageDrilldownResponse`](backend/models.py:444)
   - [`SessionUsageCalibrationSummary`](backend/models.py:453)
   - execution and telemetry DTOs in [`backend/models.py`](backend/models.py)

4. **Runtime composition is centralized**
   - [`RuntimeContainer`](backend/runtime/container.py:43) is the natural composition point for adding CLI/MCP runtime access to the same underlying services and policies.

### Current structural weaknesses relevant to CLI/MCP

1. **Routers still contain too much presentation logic**
   - Many route handlers shape DTOs and derive summaries inline, especially in [`backend/routers/api.py`](backend/routers/api.py) and [`backend/routers/analytics.py`](backend/routers/analytics.py).
   - This is fine for HTTP delivery, but the same logic would need duplication or awkward reuse in CLI/MCP.

2. **Not all routers consistently use app services**
   - Good example: [`ExecutionApplicationService`](backend/application/services/execution.py) is used from [`backend/routers/execution.py`](backend/routers/execution.py).
   - Less ideal examples: [`backend/routers/codebase.py`](backend/routers/codebase.py) and parts of [`backend/routers/features.py`](backend/routers/features.py) still mix direct DB access, service creation, and request handling.

3. **No single “agent query” abstraction exists**
   - There is no service that answers higher-level questions such as:
     - “summarize this project’s current state”
     - “generate an AAR-ready feature narrative”
     - “identify problematic workflows across a feature family”
     - “compare iteration cost across related sessions”
   - These would currently require clients to orchestrate several endpoints.

4. **HTTP endpoints are broad, but agent ergonomics are not yet optimized**
   - MCP and CLI benefit from fewer, richer, intent-oriented operations rather than many thin CRUD-style endpoints.

---

## Existing Backend Surfaces Most Relevant to Agent Workflows

### Projects and scope
Useful for selecting the correct project/workspace context.

- [`list_projects()`](backend/routers/projects.py:14)
- [`get_active_project()`](backend/routers/projects.py:79)
- [`get_active_project_paths()`](backend/routers/projects.py:88)
- [`set_active_project()`](backend/routers/projects.py:100)

### Sessions and transcripts
Useful for forensic review, timeline construction, and feature/session correlation.

- [`list_sessions()`](backend/routers/api.py:496)
- [`get_session()`](backend/routers/api.py:735)
- [`get_session_model_facets()`](backend/routers/api.py:703)
- [`get_session_platform_facets()`](backend/routers/api.py:719)
- [`get_session_linked_features()`](backend/routers/api.py:1037)

Relevant shared services:
- [`SessionFacetService`](backend/application/services/sessions.py:17)
- [`SessionTranscriptService`](backend/application/services/sessions.py:86)

### Documents and planning artifacts
Useful for PRD retrieval, implementation-plan review, progress correlation, and historical documentation context.

- [`list_documents()`](backend/routers/api.py:1529)
- [`get_documents_catalog()`](backend/routers/api.py:1568)
- [`get_document_links()`](backend/routers/api.py:1604)
- [`get_document()`](backend/routers/api.py:1620)

Relevant shared service:
- [`DocumentQueryService`](backend/application/services/documents.py)

### Features and execution context
Useful for feature-centric analysis and AAR workflows.

- [`list_features()`](backend/routers/features.py:682)
- [`get_feature()`](backend/routers/features.py:1037)
- [`get_feature_execution_context()`](backend/routers/features.py:919)
- [`get_feature_linked_sessions()`](backend/routers/features.py:1174)

### Analytics and workflow intelligence
Useful for project health, workflow effectiveness, and metrics-rich reporting.

- [`get_overview()`](backend/routers/analytics.py:1550)
- [`get_series()`](backend/routers/analytics.py:1566)
- [`get_breakdown()`](backend/routers/analytics.py:1741)
- [`get_correlation()`](backend/routers/analytics.py:1855)
- [`get_session_cost_calibration()`](backend/routers/analytics.py:1931)
- [`get_usage_attribution()`](backend/routers/analytics.py:2028)
- [`get_usage_attribution_drilldown_view()`](backend/routers/analytics.py:2056)
- [`get_usage_attribution_calibration_view()`](backend/routers/analytics.py:2084)
- [`workflow_effectiveness()`](backend/routers/analytics.py:2161)
- [`workflow_registry()`](backend/routers/analytics.py:2207)
- [`workflow_registry_detail()`](backend/routers/analytics.py:2244)
- [`failure_patterns()`](backend/routers/analytics.py:2269)

Relevant shared service:
- [`AnalyticsOverviewService`](backend/application/services/analytics.py:59)

### Execution and operational surfaces
Useful for agent-controlled or agent-informed execution workflows.

- [`check_execution_policy()`](backend/routers/execution.py:90)
- [`create_execution_run()`](backend/routers/execution.py:101)
- [`list_execution_runs()`](backend/routers/execution.py:112)
- [`get_execution_run()`](backend/routers/execution.py:131)
- [`list_execution_run_events()`](backend/routers/execution.py:142)

### Codebase context
Useful when an agent wants file-centric forensics or correlation.

- [`get_codebase_tree()`](backend/routers/codebase.py:22)
- [`get_codebase_files()`](backend/routers/codebase.py:44)
- [`get_codebase_file_content()`](backend/routers/codebase.py:76)
- [`get_codebase_file_detail()`](backend/routers/codebase.py:92)

### Sync and freshness controls
Useful for ensuring an agent is operating on current data.

- [`get_cache_status()`](backend/routers/cache.py:198)
- [`list_cache_operations()`](backend/routers/cache.py:225)
- [`trigger_sync()`](backend/routers/cache.py:243)
- [`trigger_rebuild_links()`](backend/routers/cache.py:308)
- [`trigger_sync_paths()`](backend/routers/cache.py:361)

### Telemetry and live stream
Useful later for automation or near-real-time agent consumption.

- [`get_telemetry_export_status()`](backend/routers/telemetry.py:30)
- [`push_telemetry_now()`](backend/routers/telemetry.py:53)
- [`stream_live_updates()`](backend/routers/live.py:45)

---

## Recommended North-Star Architecture

## Layer model

### 1. Domain and repository layer
Keep current repositories and parser-driven data ingestion as system-of-record mechanics.

Examples already available through [`CorePorts`](backend/application/ports/core.py:182):
- sessions
- session messages
- documents
- tasks
- features
- analytics
- session usage
- execution
- agentic intelligence

### 2. Application query layer
Add a new service family dedicated to agent-consumable intelligence queries.

Recommended package:
- `backend/application/services/agent_queries/`

Recommended service modules:
- `project_status.py`
- `feature_forensics.py`
- `workflow_intelligence.py`
- `reporting.py`
- `session_forensics.py`
- `portfolio_analysis.py`

This layer should:
- orchestrate across repositories/services
- assemble higher-order summaries
- normalize filters and scope handling
- produce stable transport-agnostic DTOs

This is the layer both CLI and MCP should call.

### 3. Delivery adapters
Three delivery channels should sit on top of the same application layer:

- **Web/API adapter**: FastAPI routers
- **CLI adapter**: local command-line binary/module
- **MCP adapter**: tool-based server for agent interaction

### 4. Optional composition facade
For especially common workflows, add a top-level facade such as:

- `CCDashAgentAccessService`

This service can bundle the most important composite use cases:
- project summary
- feature review
- feature AAR pack
- workflow diagnostics
- session diagnostics
- readiness snapshot

---

## Proposed Modular Structure

Recommended backend additions:

```text
backend/
  application/
    services/
      agent_queries/
        __init__.py
        project_status.py
        feature_forensics.py
        workflow_intelligence.py
        reporting.py
        session_forensics.py
        portfolio_analysis.py
      agent_access.py
  cli/
    __init__.py
    main.py
    commands/
      projects.py
      status.py
      features.py
      sessions.py
      analytics.py
      reports.py
      workflows.py
      cache.py
  mcp/
    __init__.py
    server.py
    tools/
      projects.py
      status.py
      features.py
      sessions.py
      workflows.py
      reports.py
      analytics.py
    resources/
      project_snapshot.py
      feature_report.py
      workflow_registry.py
```

### Why this structure works

- keeps CLI and MCP out of router code
- encourages transport-neutral DTOs and query contracts
- makes testing easier because application services can be unit tested once and reused
- lets the web app later consume richer query endpoints instead of rebuilding summaries in UI code

---

## CLI Design Recommendation

## Primary principle

The CLI should be **query-first**, not CRUD-first.

That means commands should answer useful questions directly instead of merely mirroring REST endpoints.

## Recommended CLI shape

Command namespace:

```text
ccdash project list
ccdash project use <project-id>
ccdash project show

ccdash status project
ccdash status feature <feature-id>
ccdash status workflow --feature <feature-id>

ccdash feature list
ccdash feature show <feature-id>
ccdash feature sessions <feature-id>
ccdash feature report <feature-id>
ccdash feature compare <feature-id> [--with <feature-id>]

ccdash session show <session-id>
ccdash session timeline <session-id>
ccdash session transcript <session-id>
ccdash session diagnostics <session-id>

ccdash workflow leaderboard
ccdash workflow show <workflow-id>
ccdash workflow failures
ccdash workflow investigate --feature <feature-id>

ccdash analytics overview
ccdash analytics attribution --entity-type workflow
ccdash analytics calibration
ccdash analytics trends --metric session_cost

ccdash report aar --feature <feature-id>
ccdash report blog-pack --feature <feature-id>
ccdash report project-summary
ccdash report problematic-features

ccdash cache status
ccdash cache sync
```

## Output modes

Every CLI command should support at least:
- human-readable table/text output
- `--json` for structured automation
- `--md` for markdown-ready report output where relevant

This is critical for agent workflows. An agent will often prefer JSON, while a human may want readable text or markdown.

## CLI implementation guidance

Prefer a Python CLI since the backend is Python and the business logic already lives there.

Recommended stack:
- [`argparse`](https://docs.python.org/3/library/argparse.html) or `typer`
- keep command handlers thin
- command handlers call application services, not routers
- formatting layer separate from query layer

Suggested internal layers:
- `commands/*` parse arguments
- `client/context.py` resolves active project and runtime access
- `formatters/*` handle table/json/markdown rendering
- application services produce plain DTOs

---

## MCP Design Recommendation

## Role of MCP in CCDash

MCP should expose CCDash as an **agent intelligence provider**.

Instead of thinking “how do we wrap the whole API as tools?”, think:
- what are the highest-value questions an autonomous agent would ask while planning, debugging, reviewing, or writing retrospectives?

## Best-fit MCP tool categories

### Project and portfolio awareness
- `ccdash_project_list`
- `ccdash_project_status`
- `ccdash_project_paths`
- `ccdash_portfolio_hotspots`

### Feature intelligence
- `ccdash_feature_list`
- `ccdash_feature_status`
- `ccdash_feature_sessions`
- `ccdash_feature_forensics`
- `ccdash_feature_report`

### Session intelligence
- `ccdash_session_summary`
- `ccdash_session_transcript`
- `ccdash_session_diagnostics`
- `ccdash_session_linked_features`

### Workflow intelligence
- `ccdash_workflow_leaderboard`
- `ccdash_workflow_detail`
- `ccdash_workflow_failure_patterns`
- `ccdash_workflow_investigate_feature`

### Reporting and retrospectives
- `ccdash_generate_aar`
- `ccdash_generate_blog_pack`
- `ccdash_generate_project_summary`
- `ccdash_generate_problem_analysis`

### Operational/freshness tools
- `ccdash_cache_status`
- `ccdash_sync_project`
- `ccdash_recent_sync_operations`

## MCP resource candidates

Good MCP resources are stable, referenceable views rather than imperative tools.

Examples:
- `ccdash://project/active/status`
- `ccdash://project/{project_id}/summary`
- `ccdash://feature/{feature_id}/report`
- `ccdash://feature/{feature_id}/sessions`
- `ccdash://workflow/leaderboard`
- `ccdash://analytics/overview`
- `ccdash://analytics/usage-attribution?entityType=workflow`

## MCP response design

Each tool/resource should return:
- concise summary fields
- relevant metrics
- source references
- optional evidence arrays
- stable IDs so agents can chain calls

For example, a feature-forensics response should include:
- feature identity
- status and plan coverage
- linked sessions
- total tokens/cost
- iteration count
- failure or rework indicators
- related documents
- most representative sessions
- findings summary
- evidence references

---

## Proposed High-Value Query Contracts

These are the missing abstractions that should exist before CLI/MCP becomes first-class.

### Project Status Query
Purpose: answer “what is happening in this project right now?”

Suggested output:
- active project identity
- feature counts by status
- recent session activity
- top workflows
- cost/tokens last 7d
- blocked or risky features
- cache freshness / sync status
- notable anomalies

### Feature Forensics Query
Purpose: answer “what happened during development of this feature?”

Suggested output:
- feature metadata
- linked docs and task progress
- linked sessions and timeline
- total iterations
- total tokens and cost
- workflow mix
- rework signals
- failure patterns
- representative artifacts
- summary narrative

### Workflow Diagnostics Query
Purpose: answer “which workflows are effective or problematic?”

Suggested output:
- workflow effectiveness score
- session count
- success/failure mix
- cost efficiency
- common failure patterns
- representative sessions/features
- recommended follow-up areas

### AAR Report Query
Purpose: produce a structured after-action review pack.

Suggested output:
- scope statement
- timeline of work
- key metrics
- turning points
- workflow/tool observations
- bottlenecks
- successful patterns
- lessons learned
- supporting evidence links

### Problem Feature Query
Purpose: detect highly iterative, problematic features.

Suggested heuristics:
- high session count
- high retry/rework behavior
- elevated failure-pattern overlap
- high cost with low completion progress
- repeated workflow switches
- prolonged duration and deferred tasks

---

## Delivery Strategy: REST, CLI, and MCP

## REST should remain the foundation
REST remains the stable interop surface, but should be augmented with richer composite endpoints.

Recommended new route family:

```text
/api/agent/
  /project-status
  /feature-forensics/{feature_id}
  /workflow-diagnostics
  /reports/aar
  /reports/blog-pack
  /problematic-features
```

These routes should call the same agent-query services used by CLI/MCP.

## CLI should be local and operator-friendly
Primary use cases:
- shell scripts
- local review flows
- agent shell usage inside Claude Code / similar environments
- markdown/json export

## MCP should be intent-oriented and low-friction
Primary use cases:
- planning assistance
- retrieval during coding
- retrospective/report generation
- automated forensic analysis

---

## Maintainability Guardrails

### 1. Never let CLI or MCP call router functions
Routers are HTTP adapters, not business logic.

Use:
- application services
- shared DTO mappers
- repository-backed query services

### 2. Create transport-neutral DTOs for agent workflows
Do not reuse web-only response shapes blindly.

Add dedicated models for:
- project summary
- feature forensic report
- workflow diagnostics
- AAR/report bundles

### 3. Keep formatting separate from data retrieval
The CLI should never mix query logic and table rendering in one place.

### 4. Prefer composite use cases over endpoint mirroring
Do not create fifty low-level CLI commands that simply wrap existing REST calls one-to-one.

### 5. Standardize filtering and scope resolution
Project scope, feature scope, time windows, and include/exclude flags should be normalized in shared helper utilities.

### 6. Bake source references into responses
Agents need provenance. Responses should include:
- session IDs
- feature IDs
- document IDs/paths
- workflow IDs
- timestamps
- evidence snippets where appropriate

### 7. Support deterministic machine output
All agent-facing commands/tools should offer stable JSON schemas.

### 8. Design for partial availability
If sync is stale or a subsystem is disabled, responses should degrade gracefully with:
- status flags
- freshness timestamps
- missing-data notes

---

## Recommended Implementation Phases

## Phase 1 — Agent query foundation
Goal: create transport-neutral composite services.

Deliverables:
- `backend/application/services/agent_queries/`
- new Pydantic models for project status, feature forensics, workflow diagnostics, and AAR packs
- shared filtering/scope helpers
- unit tests for query services

Suggested first queries:
- project status
- feature forensics
- workflow diagnostics

## Phase 2 — Internal REST composite endpoints
Goal: expose the new query layer over HTTP.

Deliverables:
- `/api/agent/project-status`
- `/api/agent/feature-forensics/{feature_id}`
- `/api/agent/workflow-diagnostics`
- `/api/agent/reports/aar`

This validates the service contracts before introducing more transports.

## Phase 3 — CLI MVP
Goal: make CCDash usable in shell and agent workflows.

Deliverables:
- `ccdash project list`
- `ccdash status project`
- `ccdash feature show`
- `ccdash feature report`
- `ccdash workflow leaderboard`
- `ccdash report aar`
- `--json` support on all MVP commands

Recommended packaging:
- Python entrypoint under `backend/cli/main.py`
- package entrypoint later exposed as `ccdash`

## Phase 4 — MCP MVP
Goal: expose high-value agent workflows through tools/resources.

Deliverables:
- MCP server bootstrap
- tools for project status, feature report, workflow failures, and AAR generation
- optional resources for stable snapshots

Prioritize read-only tools first.

## Phase 5 — Operational and advanced flows
Goal: support richer automation.

Deliverables:
- cache freshness and sync tools
- execution-aware investigative tools
- live update subscriptions or polling-friendly freshness resources
- portfolio-level heuristics for problematic features

## Phase 6 — Web convergence
Goal: have the web UI reuse the same composite services where beneficial.

Deliverables:
- replace some router-local response assembly with shared query services
- unify reporting outputs across UI, CLI, and MCP

---

## Recommended MVP Scope

If you want the smallest high-value first release, build this set:

### Agent query services
- project status
- feature forensics
- workflow diagnostics
- AAR pack

### REST endpoints
- `/api/agent/project-status`
- `/api/agent/feature-forensics/{feature_id}`
- `/api/agent/workflow-diagnostics`
- `/api/agent/reports/aar`

### CLI commands
- `ccdash status project --json`
- `ccdash feature report <feature-id> --json`
- `ccdash workflow failures --json`
- `ccdash report aar --feature <feature-id> --md`

### MCP tools
- `ccdash_project_status`
- `ccdash_feature_forensics`
- `ccdash_workflow_failure_patterns`
- `ccdash_generate_aar`

This is enough to prove value in:
- planning
- retrospectives
- workflow analysis
- feature investigation

---

## Risks and Mitigations

### Risk: CLI/MCP become thin wrappers over unstable HTTP responses
Mitigation:
- create shared application-layer contracts first
- use routers only as adapters

### Risk: too many low-level tools overwhelm agents
Mitigation:
- start with high-value intent-oriented tools
- keep the first MCP surface small and composable

### Risk: duplicated filtering/formatting logic across surfaces
Mitigation:
- centralize query normalization and DTO assembly
- separate formatters from query services

### Risk: stale data leads to misleading agent conclusions
Mitigation:
- expose freshness metadata
- support optional sync/status commands
- annotate reports with data recency

### Risk: codebase remains split between new and legacy router patterns
Mitigation:
- adopt a policy: all new multi-surface capabilities must enter through application services
- gradually migrate legacy router logic as adjacent work happens

---

## Concrete Recommendations

1. Build a new agent-query service layer before building the CLI.
2. Expose that layer through composite REST endpoints first.
3. Implement the CLI in Python so it shares backend logic directly.
4. Add MCP only after the first 3–4 composite queries are stable.
5. Keep the MCP surface narrow and high-value.
6. Treat provenance and freshness as first-class fields in every agent-facing response.
7. Use the new query services to slowly reduce complex response shaping inside routers like [`backend/routers/api.py`](backend/routers/api.py) and [`backend/routers/analytics.py`](backend/routers/analytics.py).

---

## Suggested Next Build Step

The next best implementation step is:

**Create the transport-neutral query contracts and service skeletons for project status, feature forensics, workflow diagnostics, and AAR reporting.**

That establishes the seam needed for:
- future REST composite endpoints
- a maintainable Python CLI
- an MCP server with stable tool contracts

Once that exists, the rest becomes delivery work rather than architecture guesswork.