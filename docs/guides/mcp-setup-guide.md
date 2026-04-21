# MCP Setup Guide

This guide explains how to use CCDash through the shipped MCP stdio server.

## What Ships

CCDash exposes four transport-neutral intelligence tools through MCP:

- `ccdash_project_status`
- `ccdash_feature_forensics`
- `ccdash_workflow_failure_patterns`
- `ccdash_generate_aar`

The workspace config lives at [`.mcp.json`](../../.mcp.json) and launches the server with `python -m backend.mcp.server`.

## Prerequisites

- Python 3.10+
- `npm run setup` completed successfully
- A populated local CCDash data store or a project configuration that CCDash can resolve

## Basic Setup

1. Run `npm run setup`.
2. Confirm the MCP server imports and starts:
   ```bash
   backend/.venv/bin/python -m backend.mcp.server
   ```
   This starts a stdio server and waits for a client connection. Stop it with `Ctrl+C`.
3. Keep the repo-root `.mcp.json` checked in so Claude Code can discover the server automatically when the workspace opens.

## Claude Code Usage

When Claude Code opens this repo, it should discover the `ccdash` MCP server from `.mcp.json`. The server exposes these tools:

- `ccdash_project_status`
  Project-level health, counts, recent sessions, and workflow activity.
- `ccdash_feature_forensics`
  Feature-specific history, linked evidence, rework signals, and representative sessions.
- `ccdash_workflow_failure_patterns`
  Workflow diagnostics and recurring failure patterns.
- `ccdash_generate_aar`
  After-action review generation from existing CCDash evidence.

## Manual Validation

Validate the shipped MCP transport with the repo test harness:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
```

Validate the CLI surface separately if needed:

```bash
backend/.venv/bin/ccdash --help
backend/.venv/bin/ccdash status project
```

## Notes

- The MCP server is a thin adapter over `backend/application/services/agent_queries/`.
- It does not require the FastAPI server to be in the request path.
- The server uses the lightweight `RuntimeContainer(profile=test)` bootstrap path rather than the full `local` runtime profile.
