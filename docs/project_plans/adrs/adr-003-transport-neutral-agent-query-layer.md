---
title: "ADR-003: Transport-Neutral Agent Query Layer"
type: "adr"
status: "accepted"
created: "2026-04-02"
parent_prd: "docs/project_plans/PRDs/features/cli-enablement.md"
depends_on_spike: "docs/project_plans/spikes/cli-framework-and-packaging-spike.md"
tags: ["adr", "architecture", "agent-queries", "cli", "mcp", "transport"]
---

# ADR-003: Transport-Neutral Agent Query Layer

## Status

Accepted

## Context

CCDash needs to expose its data through multiple transports simultaneously:
- REST API (web frontend)
- CLI (`ccdash` command-line tool)
- MCP server (for Claude Code and other AI agents)

Currently, routers contain presentation logic and response shaping that would need duplication across transports. The existing application services (SessionFacetService, DocumentQueryService, etc.) handle individual domain queries but don't compose cross-domain intelligence summaries needed by agents (e.g., project status = sessions + features + analytics + sync freshness).

## Decision

**Introduce a dedicated `backend/application/services/agent_queries/` service layer** that provides composite, transport-agnostic query services for agent-consumable intelligence.

Individual query services:
- `ProjectStatusQueryService`: Aggregates sessions, features, analytics, and sync freshness
- `FeatureForensicsQueryService`: Cross-domain feature execution history with session links
- `WorkflowDiagnosticsQueryService`: Agent execution patterns and tool invocation analytics
- `SessionIntelligenceQueryService`: Session state with cost analysis and cross-references

Each service returns domain DTOs (not HTTP-specific response objects), enabling translation to REST/CLI/MCP formats by respective transports.

## Decision Drivers

1. **Transport agnosticism**: Same query logic serves REST, CLI, and MCP without duplication
2. **Separation of concerns**: Existing application services correctly scoped to single domains
3. **Composability**: Cross-domain summaries require orchestration separate from single-domain repositories
4. **Testability**: Query services tested independently of HTTP or CLI presentation
5. **Forward compatibility**: Foundation for future transports (gRPC, GraphQL, etc.)

## Alternatives Considered

1. **Extend existing application services**: Add composite methods to current services. Pro: less new code. Con: bloats single-domain services, mixes orchestration with domain logic.

2. **Transport-neutral agent query layer** (chosen): Dedicated services for composite queries. Pro: clean separation, reusable DTOs, composable queries. Con: additional indirection.

3. **Build directly in CLI/MCP handlers**: Let each transport compose its own responses. Pro: simple initially. Con: code duplication, divergence, unmaintainable at scale.

4. **Unified facade per query** (deferred): `CCDashAgentAccessService` as single facade over all queries. Chosen to defer — start with individual query services, add facade only if usage patterns warrant it.

## Consequences

**Positive:**
- Transport-agnostic DTOs enable REST, CLI, and MCP to independently shape responses for their constraints
- Composite queries composable (ProjectStatus can include selected FeatureForensics)
- Single-domain services remain focused; orchestration logic isolated
- Easy to test: mock repositories, unit test query logic in isolation

**Negative:**
- Additional indirection layer for simple single-domain queries (mitigated: CLI/MCP can call existing application services directly for simple cases)
- Requires coordination across services if cross-domain invariants change

**Risks:**
- Query services become the "grab bag" for new composite logic. Mitigate: strict admission criteria — if a query doesn't compose multiple domains, it belongs in the existing service.

## Related

- `docs/project_plans/spikes/cli-framework-and-packaging-spike.md`
- `docs/project_plans/adrs/adr-002-mcp-server-separate-from-extension.md`
