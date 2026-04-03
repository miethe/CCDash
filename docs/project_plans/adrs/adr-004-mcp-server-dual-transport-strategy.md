---
title: "ADR-004: MCP Server Dual Transport Strategy"
type: "adr"
status: "accepted"
created: "2026-04-02"
parent_prd: "docs/project_plans/PRDs/features/cli-enablement.md"
depends_on_spike: "docs/project_plans/spikes/mcp-server-implementation-spike.md"
tags: ["adr", "mcp", "claude-code", "architecture", "transport", "stdio", "http"]
---

# ADR-004: MCP Server Dual Transport Strategy

## Status

Accepted

## Context

CCDash needs to expose intelligence tools to coding agents (Claude Code, etc.) via the Model Context Protocol (MCP). The MCP Python SDK supports two primary transports:

1. **Stdio**: External process spawned as subprocess, communication via stdin/stdout
2. **Streamable HTTP**: MCP endpoint mounted on existing HTTP server

Each transport has trade-offs. Claude Code's MCP discovery pattern favors stdio for local, single-user development. Future multi-agent or remote scenarios benefit from HTTP.

## Decision

**Implement MCP server with stdio as primary transport, Streamable HTTP as secondary transport mounted on the existing FastAPI app.**

- **Primary**: `backend/mcp/` with `backend/mcp/stdio_server.py` entry point (`python -m backend.mcp.stdio`)
- **Secondary**: `backend/mcp/http_server.py` with FastAPI router mounted at `/mcp`
- **Shared logic**: Both transports instantiate the same `FastMCP` server instance; transport is just the delivery mechanism

## Decision Drivers

1. **Claude Code alignment**: stdio is the natural fit for Claude Code's MCP discovery pattern
2. **Local-first philosophy**: CCDash is fundamentally local-first; stdio subprocess pattern is native to that model
3. **No additional infrastructure**: stdio requires no auth, no server to keep running
4. **Forward compatibility**: HTTP transport provides path for remote agents without blocking MVP
5. **Proven patterns**: Both transports exist in MCP SDK; no custom transport code needed

## Alternatives Considered

1. **Stdio only**: Claude Code spawns CCDash MCP as subprocess. Pro: simplest, no auth, matches local-first philosophy. Con: blocks remote access, future multi-agent scenarios. Chosen as primary but deferred HTTP secondary.

2. **Streamable HTTP only**: MCP endpoint on existing FastAPI server. Pro: reuses running server, supports remote. Con: requires server running, auth complexity, blocks local-first pattern. Chosen as secondary for forward compatibility.

3. **Dual transport** (chosen): stdio primary for Claude Code, HTTP secondary for future. Pro: best of both, progressive complexity. Con: two code paths to maintain (mitigated: both share same FastMCP instance — transport is isolated).

4. **Custom transport**: Build gRPC or other transport. Pro: might optimize for specific use case. Con: outside MCP SDK, custom serialization, unproven with agents.

## Consequences

**Positive:**
- Claude Code launches `ccdash mcp --stdio` as subprocess, no server dependency
- If user runs backend normally, HTTP transport is automatically available
- Both transports share identical tool implementations; no behavioral divergence
- Can deprecate HTTP if stdio proves sufficient; or promote HTTP if remote use case emerges

**Negative:**
- Two initialization paths: `StdioServer.run()` vs FastAPI router mounting. Mitigated: both call same `build_fastmcp_server()` factory.
- Stdio requires subprocess handling in Claude Code. Standard pattern, not a burden.
- HTTP transport requires authentication if CCDash backend is exposed externally. Deferred: assume local use for MVP.

**Risks:**
- Tight coupling between core tools and MCP serialization. Mitigate: keep MCP schema separate from application DTOs; use adapter layer for serialization.

## Related

- `docs/project_plans/spikes/mcp-server-implementation-spike.md`
- `docs/project_plans/adrs/adr-002-mcp-server-separate-from-extension.md`
- `docs/project_plans/adrs/adr-003-transport-neutral-agent-query-layer.md`
