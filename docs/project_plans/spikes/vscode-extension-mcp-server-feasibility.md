---
title: "SPIKE: CCDash MCP Server Integration Feasibility"
type: "spike"
status: "draft"
created: "2026-04-02"
time_box: "3 days"
parent_prd: "docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md"
tags: ["spike", "mcp", "claude-code", "vscode", "extension"]
---

# SPIKE: CCDash MCP Server Integration Feasibility

## Problem Statement

CCDash exposes session data, analytics, and project state through a FastAPI REST API. Claude Code supports MCP (Model Context Protocol) servers as tool providers. This spike investigates whether an MCP server can reliably bridge the two, enabling Claude Code to query CCDash data natively during coding sessions.

## Research Questions

### RQ1: Can a standalone MCP server reliably wrap the CCDash REST API?

- Can an MCP server proxy HTTP calls to `localhost:8000` and return structured tool results?
- What latency overhead does the MCP layer introduce over direct API calls?
- How does the MCP SDK handle typed tool definitions and response schemas?

### RQ2: Transport selection -- stdio vs HTTP/SSE

- stdio: simpler lifecycle, no port conflicts, natural for CLI-spawned processes
- HTTP/SSE: supports multiple concurrent clients, survives editor restarts
- Which transport does Claude Code currently prefer or require?
- What are the implications for debugging and logging?

### RQ3: Process lifecycle management

- Who spawns the MCP server -- the VSCode extension, Claude Code config, or the user manually?
- Can the extension activate the MCP server on startup and tear it down on deactivation?
- What happens if the MCP server process crashes mid-session?
- Can `claude_desktop_config.json` or `.mcp.json` project config handle auto-start?

### RQ4: Backend unavailability handling

- What does the MCP server return when CCDash backend is unreachable?
- Should it return a structured error tool result or throw?
- Can it implement health-check polling and surface availability status as a tool?
- How does Claude Code behave when a tool call returns an error vs times out?

### RQ5: Packaging strategy -- separate package vs bundled

- Separate `@ccdash/mcp-server` npm package: reusable outside VSCode, independently versioned
- Bundled in VSCode extension: simpler distribution, single install
- Can a hybrid approach work (shared core, extension wraps for lifecycle)?
- What do existing MCP server projects (e.g., `@anthropic/mcp-server-*`) use as a model?

### RQ6: Minimal viable tool set for proof of concept

Proposed MVP tools:
- `ccdash_get_sessions` -- list sessions with optional filters (project, date range)
- `ccdash_get_session_detail` -- return full session metadata, tool calls, token usage
- What input schemas and response shapes make these most useful to Claude Code?
- Should tool descriptions include example invocations for better discoverability?

## Scope

### In Scope

- MCP SDK evaluation (TypeScript `@modelcontextprotocol/sdk`)
- Transport comparison for CCDash use case
- Proof-of-concept: single tool returning live session data
- Error handling patterns for backend unavailability
- Packaging recommendation

### Out of Scope

- Full tool catalog design (beyond the 2 MVP tools)
- MCP resource or prompt primitives
- Authentication/authorization (CCDash is local-first, no auth needed for localhost)
- Performance optimization or caching within the MCP layer

## Approach

1. Scaffold a minimal MCP server using `@modelcontextprotocol/sdk`
2. Implement `ccdash_get_sessions` tool proxying to `GET /api/sessions`
3. Test with Claude Code via stdio transport and `.mcp.json` project config
4. Simulate backend unavailability, document error behavior
5. Evaluate HTTP/SSE transport as alternative, compare DX
6. Document packaging trade-offs and make recommendation

## Expected Outputs

- Working proof-of-concept: single MCP tool returning live session data from CCDash
- Architecture decision: separate package vs bundled (with rationale)
- Transport recommendation: stdio vs HTTP/SSE (with trade-off matrix)
- Error handling strategy document for backend unavailability
- Spike findings written to this document (updated in place)

## Success Criteria

- Claude Code can invoke `ccdash_get_sessions` via MCP and receive real session data from a running CCDash instance
- Error case documented: MCP server returns a meaningful message when CCDash is offline
- Transport recommendation justified with at least 3 comparison dimensions
- Packaging recommendation made with clear rationale

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| MCP SDK breaking changes | High | Low | Pin SDK version, monitor changelog |
| Claude Code transport limitations | High | Medium | Test both transports early (day 1) |
| Latency overhead makes tools impractical | Medium | Low | Benchmark in PoC, set acceptable threshold |
| CCDash API shape changes break MCP tools | Medium | Medium | Version MCP tool schemas, add integration test |

## Time Box

3 days. If transport selection is not resolved by day 2, default to stdio and document HTTP/SSE as follow-up.
