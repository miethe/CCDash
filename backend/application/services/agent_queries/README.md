# Agent Queries

`backend/application/services/agent_queries/` is the transport-neutral query layer for agent-facing intelligence in CCDash.

## Purpose

Use this package when a caller needs a composite answer that spans multiple observed-product domains such as sessions, documents, tasks, analytics, sync freshness, or workflow intelligence.

Routers, CLI commands, and MCP tools should all call these services directly instead of reassembling the same aggregates in their own transport layer.

## Design Rules

- Resolve request scope first with the shared project helpers.
- Keep the service contract transport-neutral: no FastAPI responses, CLI formatting, or MCP transport logic.
- Reuse existing models and domain helpers where the shape already exists.
- Add new DTO fields only when the agent-facing aggregate cannot be represented by the current models cleanly.
- Use the shared `ok` / `partial` / `error` envelope semantics consistently.
- Derive `data_freshness` and `source_refs` through the shared helpers so all transports report provenance the same way.

## When To Add A New Query Service

Add a new query service only when the answer requires two or more existing repositories or application services and that composition is expected to be reused across transports.

If the need is a single-domain read path, extend the existing domain service instead.

## Testing Expectations

- Add focused unit tests alongside the service for happy path, partial degradation, and the primary error path.
- Add shared helper/regression coverage in `backend/tests/test_agent_queries_shared.py`.
- Keep at least one SQLite-backed integration path in `backend/tests/test_agent_queries_integration.py`.

## Current Services

- `ProjectStatusQueryService`
- `FeatureForensicsQueryService`
- `WorkflowDiagnosticsQueryService`
- `ReportingQueryService`
