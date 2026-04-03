---
title: "ADR-002: CCDash MCP Server as Separate Package from VSCode Extension"
type: "adr"
status: "proposed"
created: "2026-04-02"
parent_prd: "docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md"
depends_on_spike: "docs/project_plans/spikes/vscode-extension-mcp-server-feasibility.md"
tags: ["adr", "mcp", "claude-code", "architecture", "vscode"]
---

# ADR-002: CCDash MCP Server as Separate Package from VSCode Extension

## Status

Proposed (pending MCP feasibility spike validation)

## Context

Claude Code connects to Model Context Protocol (MCP) servers as external processes via stdio or HTTP transport. The VSCode extension runs in VSCode's Extension Host (a sandboxed Node.js process). These are fundamentally different deployment environments:

- VSCode extension → human developer viewing UI panels
- MCP server → Claude Code AI agent requesting structured tool data

The original design proposed embedding the MCP server as a module inside the extension (`src/bob/mcp-server.ts`). However, MCP servers must be launchable as standalone processes, not nested inside another application's module.

## Decision

**Package the CCDash MCP server as a separate, standalone package** — not embedded in the VSCode extension.

### Proposed Structure

```
packages/vscode-ccdash/          # VSCode extension
packages/ccdash-mcp-server/      # Standalone MCP server for Claude Code
packages/ccdash-api-client/      # Shared backend API client
```

## Decision Drivers

1. **Process boundary**: MCP servers are spawned as external processes; they cannot live inside another process's module namespace
2. **Independent lifecycle**: MCP server can run without VSCode (e.g., terminal-only Claude Code usage)
3. **Independent testing**: MCP server tested separately from VSCode extension test harness
4. **Independent versioning**: Each package evolves at its own release cadence
5. **Architectural clarity**: Single responsibility — one package = one deployment unit

## Alternatives Considered

1. **Embedded in extension**: Extension spawns MCP server as child process. Adds complexity, couples lifecycles, makes MCP server unusable without VSCode.

2. **Python MCP server**: Written in Python alongside CCDash backend. MCP SDK ecosystem stronger in TypeScript; keeps extension ecosystem cohesive.

3. **Backend-native MCP**: CCDash backend itself exposes MCP tools. Interesting but couples MCP protocol to backend runtime; adds maintenance burden.

## Consequences

- Requires monorepo or multi-package structure
- Shared `ccdash-api-client` library prevents duplication across packages
- Extension can optionally launch/manage MCP server as convenience feature
- Users running Claude Code without VSCode can still use MCP server independently
- Two separate npm packages to maintain and version
