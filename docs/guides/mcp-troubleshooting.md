# MCP Troubleshooting

This guide covers the most common issues when running CCDash through the shipped stdio MCP server.

## Server Does Not Start

Symptoms:

- Claude Code does not discover the `ccdash` server
- `python -m backend.mcp.server` exits immediately
- import or dependency errors appear on startup

Checks:

1. Re-run `npm run setup`.
2. Verify the MCP dependency is installed:
   ```bash
   backend/.venv/bin/python -m pip show mcp
   ```
3. Verify the server imports and starts:
   ```bash
   backend/.venv/bin/python -m backend.mcp.server
   ```

## Tools Are Not Discovered

Symptoms:

- The server starts, but no `ccdash_*` tools appear

Checks:

1. Confirm `.mcp.json` exists at the repo root.
2. Confirm `.mcp.json` points to:
   - `command: "python"`
   - `args: ["-m", "backend.mcp.server"]`
3. Confirm the workspace environment resolves the repo venv first on `PATH`, or launch through the repo venv explicitly during manual testing.
4. Run the stdio harness:
   ```bash
   backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
   ```

## Tool Returns `status: error`

Symptoms:

- Tool call succeeds transport-wise, but the payload contains `"status": "error"`

What it usually means:

- CCDash could not resolve the active project scope
- the requested feature does not exist
- the underlying data source is not present in the local CCDash cache

Checks:

1. Verify your active project configuration in CCDash.
2. Try the equivalent CLI command:
   ```bash
   backend/.venv/bin/ccdash status project
   backend/.venv/bin/ccdash feature report <feature_id>
   ```
3. Confirm the feature or project exists in the local dataset.

## Tool Is Slow Or Times Out

Checks:

1. Verify the local SQLite database exists and is healthy.
2. Retry the equivalent CLI command to confirm whether the issue is transport-specific or data-specific.
3. Re-run:
   ```bash
   backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
   ```
4. If the harness passes but the client still times out, the issue is likely in client discovery/configuration rather than the CCDash server itself.

## Manual Debug Flow

Use this order:

1. `backend/.venv/bin/python -m backend.mcp.server`
2. `backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q`
3. `backend/.venv/bin/ccdash --help`
4. `backend/.venv/bin/ccdash status project`

If steps 1-2 pass, the CCDash MCP server itself is usually healthy.
