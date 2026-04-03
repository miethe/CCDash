---
schema_version: "1.0"
doc_type: implementation_plan
title: "CCDash CLI and MCP Enablement - Implementation Plan"
description: "Phased implementation plan for exposing CCDash project intelligence via transport-neutral query services, REST composite endpoints, Python CLI, and MCP server for coding agents."
status: draft
created: "2026-04-02"
updated: "2026-04-02"
feature_slug: "ccdash-cli-mcp-enablement"
feature_version: "v1"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: null
scope: "Agent query foundation, REST endpoints, CLI MVP, MCP server with 4 core tools"
effort_estimate: "23-28 story points"
effort_estimate_breakdown: "Phase 1: 8-10 pts | Phase 2: 4-5 pts | Phase 3: 6-7 pts | Phase 4: 5-6 pts"
priority: high
risk_level: medium
owner: "Backend Engineering"
contributors: ["Architecture Review Team"]
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
category: "product-planning"
tags: ["cli", "mcp", "agent-tooling", "typer", "fastmcp", "agent-queries", "python"]
related_documents:
  - docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
  - docs/project_plans/ccdash-cli-mcp-enablement-plan.md
  - docs/project_plans/spikes/mcp-server-implementation-spike.md
  - docs/project_plans/spikes/cli-framework-and-packaging-spike.md
---

# Implementation Plan: CCDash CLI and MCP Enablement

## Executive Summary

This implementation plan translates the PRD and planning documents into a phased, executable roadmap for shipping CCDash intelligence through three new access surfaces: a transport-neutral agent query layer, REST composite endpoints, a Python CLI, and an MCP server for coding agents.

**Scope**: Phases 1–4 (MVP)
**Total Effort**: 23–28 story points
**Timeline**: 5–7 weeks (4 weeks of focused development + 1–3 weeks for integration/hardening)
**Key Constraint**: Phase 1 is the critical path; Phases 2–4 depend on its stabilization

**Phased Approach**:
1. **Phase 1 (8–10 pts)**: Agent query foundation — transport-neutral services and DTOs
2. **Phase 2 (4–5 pts)**: REST composite endpoints — validate contracts
3. **Phase 3 (6–7 pts)**: CLI MVP — local query interface with human/JSON/Markdown output
4. **Phase 4 (5–6 pts)**: MCP MVP — agent-accessible tools via stdio transport

Phases 3 and 4 may proceed in parallel after Phase 1 is stable. Phase 2 is the contract validation gate and strongly recommended before Phase 3/4 ship.

---

## Implementation Strategy

### Architecture Principles

1. **Transport-Neutral**: All business logic lives in `agent_queries/` services; routers, CLI, and MCP are thin adapters.
2. **Single Source of Truth**: One query service → shared by REST, CLI, and MCP. No duplication.
3. **Graceful Degradation**: Services return `status: partial` when subsystems unavailable; never raise unhandled exceptions.
4. **Provenance First**: Every response includes data freshness, source entity IDs, and evidence references.
5. **Async-First**: All services use `async/await`. CLI bridges with Typer's native async support or `asyncio.run()`.

### Critical Path

```
Phase 1 (Agent Query Services) [CRITICAL]
  ↓ depends on
Phase 2 (REST Endpoints) [VALIDATION GATE]
  ├→ Phase 3 (CLI) [parallel after Phase 1]
  └→ Phase 4 (MCP) [parallel after Phase 1]
```

**Recommendation**: Proceed through Phase 2 before shipping Phase 3 and 4 to catch contract issues early.

### Files to Create/Modify Per Phase

See detailed phase plans:
- [Phase 1: Agent Query Foundation](./ccdash-cli-mcp-enablement-v1/phase-1-agent-queries.md)
- [Phase 2: REST Endpoints](./ccdash-cli-mcp-enablement-v1/phase-2-rest-endpoints.md)
- [Phase 3–4: CLI & MCP](./ccdash-cli-mcp-enablement-v1/phase-3-4-cli-mcp.md)

---

## High-Level Phase Breakdown

| Phase | Goal | Duration | Effort | Key Deliverables | Acceptance Gate |
|-------|------|----------|--------|------------------|-----------------|
| **1** | Agent query foundation | 5–7 d | 8–10 pts | `agent_queries/` services, DTOs, unit tests (>90% coverage) | All 4 services tested, `status` field works, partial degradation verified |
| **2** | REST composite endpoints | 2–3 d | 4–5 pts | `/api/agent/*` routes, OpenAPI docs | All 4 endpoints return valid DTOs, services never called twice per request |
| **3** | CLI MVP | 5–7 d | 6–7 pts | `ccdash` command, 4 core commands, formatters, CliRunner tests, entry point | All commands exit 0, JSON output valid, startup < 500 ms, `npm run setup` installs CLI |
| **4** | MCP MVP | 5–7 d | 5–6 pts | FastMCP server, 4 core tools, `.mcp.json`, test_client tests | All tools callable, responses valid, Claude Code discovers tools |

---

## Phase Dependencies & Sequencing

### Strict Dependencies

- **Phase 2 requires Phase 1** (REST calls agent_queries services)
- **Phase 3 requires Phase 1** (CLI calls agent_queries services)
- **Phase 4 requires Phase 1** (MCP calls agent_queries services)

### Recommended Sequencing

1. **Execute Phase 1 fully** (all 4 services + 90% test coverage)
2. **Execute Phase 2 fully** (serves as contract validation + docs example)
3. **Execute Phase 3 and 4 in parallel** (both call same Phase 1 services)
4. **Integration testing** (E2E with real DB; CLI + web server coexistence)

### Why Phase 2 Before 3/4

REST endpoints force the query services to be complete and well-specified before CLI and MCP build on them. Discovering contract issues at the REST layer prevents rework when agents start using MCP tools.

---

## Quality Gates Per Phase

### Phase 1 Quality Gate

- [ ] All 4 query services exist and have >90% line coverage
- [ ] All 4 DTOs include `status`, `data_freshness`, `generated_at`, `source_refs` fields
- [ ] Service returns `status: partial` (no exception) when subsystem unavailable
- [ ] Mock-based unit tests pass for all services
- [ ] Integration test against test SQLite DB passes
- [ ] Architecture review sign-off: no business logic duplication with existing services

### Phase 2 Quality Gate

- [ ] All 4 endpoints exist at `/api/agent/*` paths
- [ ] All endpoints appear in OpenAPI schema with examples
- [ ] No endpoint contains inline query logic (all delegate to Phase 1 services)
- [ ] Each endpoint is called exactly once by a router handler (no double-fetching)
- [ ] REST API tests pass; CliRunner and mcp.test_client() tests pass
- [ ] Example curl commands work

### Phase 3 Quality Gate

- [ ] `ccdash --version` and `ccdash --help` work
- [ ] `python -m backend.cli --help` works
- [ ] All 4 MVP commands exit 0 and produce valid output
- [ ] JSON output is valid (can be piped to `jq`)
- [ ] Startup latency < 500 ms
- [ ] `npm run setup` makes `ccdash` available
- [ ] CliRunner tests cover human/JSON/MD output modes

### Phase 4 Quality Gate

- [ ] `python -m backend.mcp.server` starts without error
- [ ] `.mcp.json` exists and points to server
- [ ] All 4 tools return valid response envelope
- [ ] mcp.test_client() tests pass
- [ ] Claude Code discovers tools (manual verification)
- [ ] No exception raised when subsystem unavailable

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Agent query services become a "grab bag" | Medium | Medium | Strict admission: only multi-domain queries. Single-domain logic stays in existing services. Architecture review sign-off. |
| CLI startup > 500 ms | Low | Medium | Lazy imports in command modules. Profile on first run. Fallback: async bootstrap deferred to command boundary. |
| MCP SDK v2 breaking changes | Low | Medium | Pin `mcp>=1.8,<2`. FastMCP decorator API confirmed stable. Monitor for v2 beta. |
| SQLite lock contention (CLI + web running) | Low | Low | WAL mode + 30s busy timeout already configured. CLI operations are short read transactions. |
| Tool descriptions inadequate for agents | Medium | High | Iterate based on real Claude Code testing. Treat docstrings as UX. Test with agents before shipping. |
| Query DTO shape diverges (CLI JSON vs REST JSON) | Low | Low | Both use Pydantic `.model_dump()` on same DTO classes. Divergence prevented by structure. |

---

## Testing Strategy

### Unit Testing (Phase 1)

- **Query services**: Pytest with mocked `CorePorts`, mocked repositories
- **Target**: >90% line coverage
- **Approach**: Test each service independently; mock subsystem failures to test graceful degradation

### Integration Testing (Phase 1 + 2)

- **Agent queries**: Real SQLite test DB with parsed fixture data
- **REST endpoints**: FastAPI TestClient
- **Approach**: Verify services return consistent data via both paths

### CLI Testing (Phase 3)

- **Framework**: Typer's CliRunner
- **Approach**: Test each command for human/JSON/Markdown output
- **Coverage**: All MVP commands, error cases, missing DB, stale sync

### MCP Testing (Phase 4)

- **Framework**: `mcp.test_client()` in-memory transport
- **Approach**: Test each tool with mocked CorePorts
- **Coverage**: All 4 tools, error cases, partial availability

### E2E Testing (All Phases)

- **Approach**: Full stack with real SQLite DB, CLI + web server coexistence
- **Validation**: Data consistency, no corruption under concurrent access

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent query services line coverage | >90% | pytest coverage report |
| REST endpoint response time (p95, local SQLite) | <100 ms | Load test with wrk/vegeta |
| CLI startup to first output | <500 ms | time ccdash status project |
| MCP tool response time (p95, local SQLite) | <2 s | mcp.test_client() wall clock |
| CLI JSON output parseable | 100% | for each MVP command: `ccdash ... --json \| jq .` |
| Zero business logic duplication | Verified | Architecture review checklist |
| All tests passing | 100% | CI gate (pytest, CliRunner, mcp.test_client) |

---

## Effort Estimates & Story Points

### Rationale for Story Points

Estimates follow Fibonacci scale with reference to CCDash's typical stories:
- **1 pt**: Trivial config change or single small function
- **2 pts**: Single service method or 1–2 formatters
- **3 pts**: Full command or tool with output rendering
- **5 pts**: Full service with integration tests
- **8 pts**: Multi-service feature with comprehensive testing

### Phase 1 Breakdown (8–10 pts total)

| Task | Effort | Notes |
|------|--------|-------|
| Create `agent_queries/` package structure | 1 pt | Boilerplate, `__init__.py`, module stubs |
| Implement `ProjectStatusQueryService` + DTO | 3 pts | Aggregates 5+ data sources; 90%+ coverage |
| Implement `FeatureForensicsQueryService` + DTO | 3 pts | Session timeline, iteration tracking, rework signals |
| Implement `WorkflowDiagnosticsQueryService` + DTO | 2 pts | Effectiveness scoring, failure patterns |
| Implement `ReportingQueryService` + DTO | 2 pts | AAR assembly, narrative generation |
| Shared filter/scope helpers | 1 pt | Time windows, project scope normalization |
| Unit tests (>90% coverage) | 2 pts | Mocked CorePorts, all services |
| Integration tests (test DB) | 1 pt | End-to-end with SQLite fixture |
| **Phase 1 Total** | **8–10 pts** | Estimate range: 8 (lean), 10 (comprehensive) |

### Phase 2 Breakdown (4–5 pts total)

| Task | Effort | Notes |
|------|--------|-------|
| Create `backend/routers/agent.py` router | 1 pt | Boilerplate, import Phase 1 services |
| Implement 4 REST endpoints | 2 pts | ~10 lines each; all delegate to Phase 1 |
| OpenAPI schema documentation | 1 pt | Add descriptions, example responses |
| Integration tests (FastAPI TestClient) | 1 pt | Test all 4 endpoints + error cases |
| **Phase 2 Total** | **4–5 pts** | |

### Phase 3 Breakdown (6–7 pts total)

| Task | Effort | Notes |
|------|--------|-------|
| Create `backend/cli/` package, Typer app structure | 1 pt | `main.py`, `__main__.py`, command stubs |
| Implement `CLIRuntimeContainer`, bootstrap logic | 1 pt | `runtime.py`, lazy CorePorts init, connection lifecycle |
| Implement 4 MVP commands (status, feature, workflow, report) | 3 pts | ~40 lines each; all delegate to Phase 1 |
| Implement 3 output formatters (human/JSON/Markdown) | 2 pts | TableFormatter, JsonFormatter, MarkdownFormatter |
| CliRunner tests (all commands, all output modes) | 1 pt | ~5 tests per command × 3 modes |
| Entry point in `pyproject.toml`, `npm run setup` integration | 1 pt | Config + shell script update |
| **Phase 3 Total** | **6–7 pts** | |

### Phase 4 Breakdown (5–6 pts total)

| Task | Effort | Notes |
|------|--------|-------|
| Add `mcp>=1.8,<2` dependency | 1 pt | Update requirements.txt |
| Create `backend/mcp/` package, FastMCP server | 1 pt | `server.py`, `bootstrap.py`, `__main__` entry point |
| Implement 4 core MCP tools | 3 pts | ~30 lines each; all delegate to Phase 1 |
| Create `.mcp.json` configuration | 1 pt | Stdio transport, env vars |
| mcp.test_client() unit tests | 1 pt | All 4 tools + error cases |
| **Phase 4 Total** | **5–6 pts** | |

---

## Detailed Phase Plans

Complete phase-by-phase task breakdowns with acceptance criteria are in:

- **[Phase 1: Agent Query Foundation](./ccdash-cli-mcp-enablement-v1/phase-1-agent-queries.md)** — Task IDs P1-T1 through P1-T8, dependencies, acceptance criteria
- **[Phase 2: REST Endpoints](./ccdash-cli-mcp-enablement-v1/phase-2-rest-endpoints.md)** — Task IDs P2-T1 through P2-T4
- **[Phase 3–4: CLI & MCP](./ccdash-cli-mcp-enablement-v1/phase-3-4-cli-mcp.md)** — Task IDs P3-T1 through P3-T6, P4-T1 through P4-T5

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│          Access Surfaces (Delivery Adapters)        │
├─────────────────────┬──────────────┬────────────────┤
│  REST               │   CLI        │    MCP         │
│  /api/agent/*       │   ccdash     │    stdio       │
│  (FastAPI Router)   │   (Typer)    │    (FastMCP)   │
└─────────────────────┴──────────────┴────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│   Agent Query Services (Transport-Neutral)          │
│   backend/application/services/agent_queries/       │
│  ┌─────────────────────────────────────────────┐   │
│  │ • ProjectStatusQueryService                 │   │
│  │ • FeatureForensicsQueryService              │   │
│  │ • WorkflowDiagnosticsQueryService           │   │
│  │ • ReportingQueryService                     │   │
│  │ • Shared filter/scope helpers               │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│   Application Services & CorePorts                  │
│   (Existing services: SessionFacetService,          │
│    AnalyticsOverviewService, DocumentQueryService) │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│   Repositories → Database (SQLite / PostgreSQL)     │
└─────────────────────────────────────────────────────┘
```

---

## File Structure Summary

New files created across all phases:

```
backend/
  application/
    services/
      agent_queries/
        __init__.py
        project_status.py         # Phase 1: ProjectStatusQueryService + DTO
        feature_forensics.py      # Phase 1: FeatureForensicsQueryService + DTO
        workflow_intelligence.py  # Phase 1: WorkflowDiagnosticsQueryService + DTO
        reporting.py              # Phase 1: ReportingQueryService + DTO
        _filters.py               # Phase 1: Shared filter helpers
  routers/
    agent.py                      # Phase 2: /api/agent/* endpoints
  cli/
    __init__.py                   # Phase 3
    __main__.py                   # Phase 3: python -m backend.cli entry
    main.py                       # Phase 3: Typer app, global options
    runtime.py                    # Phase 3: CLIRuntimeContainer bootstrap
    output.py                     # Phase 3: OutputMode, formatter selection
    commands/
      __init__.py                 # Phase 3
      status.py                   # Phase 3: ccdash status project
      feature.py                  # Phase 3: ccdash feature report <id>
      workflow.py                 # Phase 3: ccdash workflow failures
      report.py                   # Phase 3: ccdash report aar
    formatters/
      __init__.py                 # Phase 3
      base.py                     # Phase 3: OutputFormatter protocol
      table.py                    # Phase 3: TableFormatter
      json.py                     # Phase 3: JsonFormatter
      markdown.py                 # Phase 3: MarkdownFormatter
  mcp/
    __init__.py                   # Phase 4
    __main__.py                   # Phase 4: python -m backend.mcp.server entry
    server.py                     # Phase 4: FastMCP instance + lifespan
    bootstrap.py                  # Phase 4: Lazy CorePorts init
    context.py                    # Phase 4: MCP RequestContext builder
    tools/
      __init__.py                 # Phase 4: register_tools() aggregator
      project.py                  # Phase 4: ccdash_project_status
      features.py                 # Phase 4: ccdash_feature_forensics
      workflows.py                # Phase 4: ccdash_workflow_failure_patterns
      reports.py                  # Phase 4: ccdash_generate_aar
.mcp.json                         # Phase 4: Claude Code MCP config

Modified files:
  pyproject.toml                  # Phase 3: [project.scripts] entry point
  backend/requirements.txt         # Phase 4: Add mcp>=1.8,<2
  npm run setup script             # Phase 3: Add pip install -e .
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Existing CCDash repo with backend and frontend set up
- FastAPI application running (for Phase 2 onward)
- SQLite with WAL mode enabled (existing configuration)

### First Step: Phase 1

1. Create `backend/application/services/agent_queries/` directory
2. Implement `ProjectStatusQueryService` with Pydantic DTO
3. Write unit tests with >90% coverage
4. Get architecture review sign-off before proceeding to Phase 2

See [Phase 1 detailed plan](./ccdash-cli-mcp-enablement-v1/phase-1-agent-queries.md) for task-by-task guidance.

---

## Integration Checkpoints

### After Phase 1

- All 4 query services tested
- Graceful degradation verified (partial status)
- Ready to move to Phase 2 (REST) or skip to Phase 3/4 (CLI/MCP directly use Phase 1)

### After Phase 2

- REST endpoints validated
- Contract shape finalized
- No changes needed to Phase 1 DTOs (signals good design)

### After Phase 3

- CLI available as `ccdash` command
- All human/JSON/Markdown output modes working
- Ready for agent shell integration

### After Phase 4

- MCP tools discoverable in Claude Code
- Manual E2E test with Claude Code successful
- Ready for production release

---

## Deferred (Out of Scope)

These are explicit out-of-scope for this PRD; tracked separately:

- **Phase 5**: Streamable HTTP MCP transport, extended tool catalog, MCP resources
- **Phase 6**: Web UI convergence (routers calling agent_queries services)
- **Phase 5+**: Portfolio-level analysis, write/mutation operations, live update streaming

---

## Success Criteria

This implementation plan is complete and ready for development when:

- [ ] All phase-specific task breakdowns are reviewed and estimated
- [ ] Architecture review confirms query service contracts
- [ ] Team capacity and timeline are allocated
- [ ] Testing infrastructure (pytest, CliRunner, mcp.test_client) is validated

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [PRD: CCDash CLI and MCP Enablement](../../PRDs/features/ccdash-cli-mcp-enablement-v1.md) | Requirements source |
| [Planning: CCDash CLI and MCP Enablement](../../ccdash-cli-mcp-enablement-plan.md) | Architecture vision |
| [SPIKE: MCP Server Implementation](../../spikes/mcp-server-implementation-spike.md) | MCP technical research |
| [SPIKE: CLI Framework and Packaging](../../spikes/cli-framework-and-packaging-spike.md) | CLI technical research |
| [ADR-003: Transport-Neutral Agent Query Layer](../../adrs/adr-003-transport-neutral-agent-query-layer.md) | Architecture decision |
| [ADR-004: MCP Dual Transport Strategy](../../adrs/adr-004-mcp-server-dual-transport-strategy.md) | Architecture decision |

---

## Appendix: MeatyPrompts Architecture Alignment

This implementation follows MeatyPrompts layered architecture principles:

| Layer | Mapping | Example |
|-------|---------|---------|
| **Database** | SQLite/PostgreSQL with existing schema | sessions, features, analytics tables |
| **Repository** | Existing repositories (SessionRepository, FeatureRepository, etc.) | No new repos; agent_queries uses existing ones |
| **Service** | New agent_queries package + existing domain services | ProjectStatusQueryService, FeatureForensicsQueryService |
| **API** | REST routers + CLI commands + MCP tools | `/api/agent/*` endpoints + `ccdash` commands + MCP tools |
| **UI** | Web dashboard (unchanged); CLI formatters are output adapters | TableFormatter, JsonFormatter, MarkdownFormatter |
| **Testing** | Pytest (services), FastAPI TestClient (endpoints), CliRunner, mcp.test_client() | Comprehensive test coverage per phase |
| **Docs** | Inline docstrings, OpenAPI schema, tool descriptions | Quality tool/command help text |
| **Deployment** | CLI as pip entry point, MCP as stdio subprocess | Entry point in pyproject.toml, `.mcp.json` config |

---

## Document Metadata

- **Version**: 1.0
- **Last Updated**: 2026-04-02
- **Author**: Architecture Planning Team
- **Status**: Draft (ready for Phase 1 kickoff)
