# CCDash MCP Server

This package exposes CCDash intelligence over MCP using a stdio FastMCP server.

## Scope

The MCP layer is an adapter only. Business logic lives in `backend/application/services/agent_queries/`.

Current tools:

- `ccdash_project_status`
- `ccdash_feature_forensics`
- `ccdash_workflow_failure_patterns`
- `ccdash_generate_aar`

## Runtime Pattern

MCP bootstrap mirrors the CLI runtime path:

- `RuntimeContainer(profile=get_runtime_profile("test"))`
- `build_core_ports(...)`
- `RequestMetadata`
- `container.build_request_context(...)`

Do not replace this with a `local`-profile startup path or a separate request-context builder.

## Launch

```bash
python -m backend.mcp.server
```

The repo-root `.mcp.json` uses the same launch command for workspace discovery.

## Response Contract

Each tool returns:

```json
{
  "status": "ok|partial|error",
  "data": {},
  "meta": {
    "generated_at": "...",
    "data_freshness": "...",
    "source_refs": []
  }
}
```

The tool layer should not reshape the business payload beyond this stable transport envelope.

## Adding A Tool

1. Add or reuse a transport-neutral query in `backend/application/services/agent_queries/`.
2. Add a thin registration function in `backend/mcp/tools/`.
3. Build request context through `backend/mcp/bootstrap.py`.
4. Return the shared MCP envelope.
5. Extend `backend/tests/test_mcp_server.py` with stdio coverage.

## Testing

Use the real stdio transport harness:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
```

The harness uses:

- `StdioServerParameters`
- `mcp.client.stdio.stdio_client`
- `ClientSession`

It validates `initialize`, `list_tools`, and `call_tool` against `python -m backend.mcp.server`.
