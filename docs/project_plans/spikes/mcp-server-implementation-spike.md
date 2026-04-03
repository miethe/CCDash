---
schema_version: "1.0"
doc_type: spike
title: "MCP Server Implementation - SPIKE Research"
description: "Technical research for exposing CCDash intelligence tools via Model Context Protocol (MCP) to coding agents"
status: completed
created: 2026-04-02
updated: 2026-04-02
completed_date: 2026-04-02
feature_slug: mcp-server
research_questions:
  - "MCP Python SDK maturity, key APIs for tools and resources"
  - "Transport modes: stdio vs SSE/Streamable HTTP for local-first dashboard"
  - "FastAPI integration: mount within existing app vs separate process"
  - "Tool design patterns for agent-query services"
  - "Resource vs tool distinction and design"
  - "Discovery and configuration for Claude Code"
  - "Testing strategy for MCP tools"
complexity: medium
estimated_research_time: "4h"
tags: [mcp, agent-tooling, fastapi, python-sdk, architecture]
related_documents:
  - backend/application/ports/core.py
  - backend/runtime/container.py
  - backend/runtime/bootstrap.py
  - backend/application/services/
---

# MCP Server Implementation - SPIKE Research

## Executive Summary

CCDash should expose its project intelligence capabilities via Model Context Protocol (MCP) so that coding agents (Claude Code, etc.) can query project status, session forensics, analytics, and feature progress without leaving their workflow. The recommended approach is a **dual-transport MCP server**: a stdio-launched process for Claude Code local use (primary), with Streamable HTTP mounted on the existing FastAPI app for network clients (secondary). The official `mcp` Python SDK (FastMCP) is mature enough for production use, and CCDash's existing hexagonal port system (`CorePorts`) provides clean integration points that avoid duplicating business logic.

**Recommendation**: Implement stdio transport first (Phase 1) using FastMCP decorators backed by CCDash application services, then add Streamable HTTP mounting on the FastAPI app (Phase 2). This gives immediate value for the primary use case (Claude Code subprocess) while preserving the option for networked agent access.

---

## 1. MCP Python SDK Assessment

### SDK Overview

| Property | Value |
|----------|-------|
| Package | `mcp` on PyPI |
| Repository | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) |
| Latest stable | 1.9.x (as of early 2026) |
| Python support | 3.10+ |
| Key dependency | Pydantic, httpx, anyio, starlette |
| License | MIT |
| Maturity | Production-ready; used by Anthropic, Prefect, and major MCP server ecosystem |

### Key APIs

The SDK provides **FastMCP**, a high-level server framework that handles protocol compliance, connection management, and message routing. The core decorators are:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CCDash", stateless_http=True)

@mcp.tool()
async def get_project_status(project_id: str) -> dict:
    """Get current project status including session counts, task velocity, and feature progress."""
    ...

@mcp.resource("ccdash://projects/{project_id}/overview")
async def project_overview(project_id: str) -> str:
    """Read-only project overview with key metrics."""
    ...

@mcp.prompt()
def diagnostic_prompt(project_id: str) -> str:
    """Generate a diagnostic prompt for analyzing project health."""
    ...
```

**Key SDK features:**
- Automatic JSON Schema generation from Python type hints
- Built-in parameter validation via Pydantic
- Async-first design (compatible with CCDash's async stack)
- Transport-agnostic tool definitions (same tools work over stdio and HTTP)
- Session management for stateful and stateless modes
- `Context` object for logging, progress reporting, and resource access within tools

### Maturity Assessment

The SDK is mature for the tool and resource primitives CCDash needs. Version 2.x is in development (targeting Q2 2026) with breaking changes to the low-level transport layer, but the FastMCP decorator API (`@mcp.tool()`, `@mcp.resource()`) is stable and will be preserved. **Recommendation**: pin to `mcp>=1.8,<2` until v2 stabilizes.

---

## 2. Transport Mode Analysis

### Transport Comparison

| Dimension | stdio | Streamable HTTP |
|-----------|-------|-----------------|
| **Launch model** | Claude Code spawns CCDash MCP as subprocess | MCP endpoint runs inside or alongside existing FastAPI |
| **Connection** | stdin/stdout JSON-RPC | HTTP POST/GET with optional SSE streaming |
| **Latency** | Lowest (in-process pipes) | HTTP overhead (~1-5ms local) |
| **Concurrency** | Single client per process | Multiple concurrent clients |
| **State** | Stateful (process lifetime) | Stateful or stateless per configuration |
| **Auth** | Implicit (process ownership) | Requires explicit auth if exposed |
| **Startup cost** | ~1-3s (Python + DB init) | Zero (already running with FastAPI) |
| **Claude Code support** | Native (primary integration path) | Supported via `type: "http"` in config |
| **Complexity** | Low | Medium (lifespan coordination, CORS) |

### Recommendation: Dual Transport, stdio Primary

**stdio is the right primary transport** for CCDash because:

1. **Claude Code's native model**: Claude Code launches MCP servers as subprocesses via stdio. This is the zero-friction path -- the user adds a config entry and it works.
2. **Local-first alignment**: CCDash is a local-first dashboard. stdio keeps everything on the same machine with no network exposure.
3. **No auth needed**: The subprocess inherits the user's filesystem permissions. No token management.
4. **Process isolation**: A crash in the MCP server does not affect the running FastAPI dashboard.

**Streamable HTTP as secondary transport** is valuable because:

1. **Reuses running server**: When the dashboard is already running, agents can connect without spawning a new process.
2. **Multi-agent support**: Multiple agents can query the same endpoint concurrently.
3. **Remote access**: Enables future scenarios where agents on other machines query CCDash.

### stdio Startup Optimization

The main concern with stdio transport is startup latency. The MCP subprocess must initialize the database connection and build `CorePorts` before it can serve tools. Mitigations:

- **Lazy DB initialization**: Connect to SQLite on first tool call, not at import time. SQLite opens in ~10ms.
- **Minimal imports**: The MCP server module should import only what it needs, avoiding the full FastAPI router tree.
- **Connection reuse**: Keep the process alive across Claude Code sessions (MCP protocol handles reconnection).

---

## 3. FastAPI Integration Architecture

### Option A: Mount MCP on Existing FastAPI App (Streamable HTTP)

```python
# backend/runtime/bootstrap.py (modified)
from backend.mcp.server import create_mcp_server

def build_runtime_app(profile: RuntimeProfile | RuntimeProfileName) -> FastAPI:
    ...
    app = FastAPI(title="CCDash API", lifespan=lifespan, ...)

    # Mount MCP server at /mcp
    mcp_server = create_mcp_server()
    mcp_app = mcp_server.streamable_http_app()
    app.mount("/mcp", mcp_app)

    _register_routers(app)
    return app
```

**Lifespan coordination** is the key challenge. The FastMCP server has its own session manager that must be initialized during the ASGI lifespan. The pattern:

```python
from contextlib import asynccontextmanager
import contextlib

@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.startup(app)
    # Enter MCP session manager lifespan
    async with contextlib.aclosing(mcp_server.session_manager):
        yield
    await container.shutdown(app)
```

**Pros:**
- Zero additional processes
- MCP tools access the same `CorePorts` instance as the REST API
- Single deployment artifact

**Cons:**
- Lifespan coupling can be fragile (see [python-sdk#1367](https://github.com/modelcontextprotocol/python-sdk/issues/1367))
- MCP endpoint shares FastAPI's error handling and middleware
- Tight coupling between MCP server lifecycle and dashboard lifecycle

### Option B: Separate stdio Process (Primary)

```python
# backend/mcp/server.py
from mcp.server.fastmcp import FastMCP
from backend.mcp.tools import register_tools
from backend.mcp.resources import register_resources

mcp = FastMCP("CCDash Intelligence", log_level="WARNING")

register_tools(mcp)
register_resources(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

The stdio server initializes its own `CorePorts` instance with a lightweight bootstrap:

```python
# backend/mcp/bootstrap.py
from backend.application.ports import CorePorts
from backend.db import connection
from backend.runtime_ports import build_core_ports
from backend.runtime.profiles import get_runtime_profile
from backend.runtime.storage_contract import get_storage_capability_contract

_ports: CorePorts | None = None

async def get_ports() -> CorePorts:
    global _ports
    if _ports is None:
        db = await connection.get_connection()
        profile = get_runtime_profile("local")
        _ports = build_core_ports(db, runtime_profile=profile, storage_profile=config.STORAGE_PROFILE)
    return _ports
```

**Pros:**
- Complete isolation from the dashboard process
- Can run without the dashboard running
- Clean, simple code path
- Native Claude Code integration

**Cons:**
- Separate DB connection (acceptable for SQLite WAL mode)
- Cannot share in-memory caches with the dashboard
- Slight startup latency

### Recommended: Option B (stdio) as primary, Option A (HTTP mount) as optional add-on

This aligns with CCDash's existing architecture where the `RuntimeContainer` pattern already supports multiple runtime profiles. The MCP server effectively becomes a new runtime profile.

---

## 4. Tool Design Patterns

### Tool Design Principles

Effective MCP tools for coding agents should follow these patterns:

1. **Descriptive docstrings**: The tool description is the primary way agents discover what a tool does. Write them as if explaining to a skilled developer.
2. **Structured parameters with defaults**: Use Pydantic models or typed parameters with sensible defaults. Agents should be able to call most tools with minimal arguments.
3. **Consistent response format**: Return structured dicts/JSON, not raw strings. Include metadata (counts, timestamps) that help agents decide next steps.
4. **Granular over monolithic**: Prefer many focused tools over few multi-purpose tools. Agents compose small tools better than they navigate complex parameter matrices.
5. **Error as data**: Return error information in the response body rather than raising exceptions. Agents handle structured errors better than stack traces.

### Proposed Tool Catalog

#### Project Intelligence Tools

```python
@mcp.tool()
async def get_project_status(
    project_id: str | None = None,
) -> dict:
    """Get the current project's high-level status.

    Returns session count, active features, task velocity,
    recent cost, and sync health. If project_id is omitted,
    uses the active project.
    """
    ports = await get_ports()
    ctx = build_mcp_context(project_id)
    overview = await AnalyticsOverviewService().get_overview(ctx, ports)
    return {"project_id": ctx.project.project_id, "overview": overview}


@mcp.tool()
async def list_sessions(
    project_id: str | None = None,
    limit: int = 20,
    model_filter: str | None = None,
    since: str | None = None,
) -> dict:
    """List recent agent sessions for the project.

    Returns session ID, model, duration, token usage, cost,
    and tool call count. Use 'since' as ISO date to filter.
    """
    ...


@mcp.tool()
async def get_session_detail(session_id: str) -> dict:
    """Get detailed information about a specific agent session.

    Returns full session metadata, tool usage breakdown,
    token metrics, cost, and linked features/tasks.
    """
    ...
```

#### Feature Forensics Tools

```python
@mcp.tool()
async def get_feature_status(
    feature_slug: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Get status and progress for a feature.

    If feature_slug is omitted, returns summary of all features.
    Includes completion percentage, linked sessions, and tasks.
    """
    ...


@mcp.tool()
async def get_feature_sessions(
    feature_slug: str,
    project_id: str | None = None,
) -> dict:
    """Get all sessions that contributed to a feature.

    Returns sessions sorted by recency with cost and token
    aggregates per session.
    """
    ...
```

#### Workflow Diagnostics Tools

```python
@mcp.tool()
async def get_task_board(
    project_id: str | None = None,
    status_filter: str | None = None,
) -> dict:
    """Get the current task board state.

    Returns tasks grouped by status (todo, in-progress, done, blocked).
    Optionally filter to a single status.
    """
    ...


@mcp.tool()
async def get_cost_breakdown(
    project_id: str | None = None,
    period: str = "7d",
) -> dict:
    """Get cost breakdown by model and session over a time period.

    Period format: '7d', '30d', '24h'. Returns per-model costs,
    total cost, and cost trend.
    """
    ...
```

#### Document Intelligence Tools

```python
@mcp.tool()
async def search_documents(
    query: str,
    doc_type: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Search project documents (PRDs, ADRs, guides, plans).

    Returns matching documents with title, type, status, and
    relevance snippet. Use doc_type to filter (prd, adr, guide, plan).
    """
    ...


@mcp.tool()
async def get_document(document_id: str) -> dict:
    """Get full content and metadata for a specific document."""
    ...
```

### Tool Response Format Convention

All tools should return responses following this structure:

```python
{
    "status": "ok",           # or "error", "partial"
    "data": { ... },          # the primary response payload
    "meta": {
        "project_id": "...",
        "count": 42,
        "generated_at": "2026-04-02T12:00:00Z",
    }
}
```

---

## 5. Resource Design

### When to Use Resources vs Tools

| Use Case | Primitive | Rationale |
|----------|-----------|-----------|
| Query session list with filters | **Tool** | Dynamic parameters, agent-initiated |
| Project configuration/metadata | **Resource** | Static context, read-only reference |
| Feature progress lookup | **Tool** | Agent needs to decide when to check |
| Database schema reference | **Resource** | Background context for the model |
| Run cost analysis | **Tool** | Computation with parameters |
| Project README/overview | **Resource** | Static document, context loading |

### Proposed Resources

```python
@mcp.resource("ccdash://projects")
async def list_projects() -> str:
    """List all configured projects with their IDs and paths."""
    ports = await get_ports()
    projects = ports.workspace_registry.list_projects()
    return json.dumps([{"id": p.id, "name": p.name, "path": p.path} for p in projects])


@mcp.resource("ccdash://projects/{project_id}/config")
async def project_config(project_id: str) -> str:
    """Project configuration including session paths, doc paths, and sync status."""
    ports = await get_ports()
    project = ports.workspace_registry.get_project(project_id)
    paths = ports.workspace_registry.resolve_project_paths(project)
    return json.dumps({
        "id": project.id,
        "name": project.name,
        "session_path": str(paths.sessions_dir),
        "documents_path": str(paths.documents_dir),
    })


@mcp.resource("ccdash://projects/{project_id}/models")
async def available_models(project_id: str) -> str:
    """List of AI models observed in project sessions with usage counts."""
    ...
```

### Resource Design Principles

- Resources are **read-only** and **idempotent** (like GET requests)
- Resources provide **context** that helps agents use tools more effectively
- Use URI templates (`{project_id}`) for parameterized resources
- Return plain text or JSON strings (not dicts -- the SDK serializes resources as text content)
- Resources are loaded by the **host application** (Claude Code), not invoked by the model directly

---

## 6. Discovery and Configuration

### Claude Code Configuration

Claude Code discovers MCP servers through configuration at three scope levels:

1. **Project scope** (`.mcp.json` at repo root) -- shared with the team via git
2. **User scope** (`~/.claude.json`) -- personal, global
3. **Local scope** (`~/.claude.json` under project path key) -- personal, per-project

### Recommended: Project-scoped `.mcp.json`

For CCDash, the MCP server configuration should ship with the repo so all developers get it automatically:

```json
{
  "mcpServers": {
    "ccdash": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "CCDASH_DB_BACKEND": "sqlite",
        "CCDASH_DATA_DIR": "./data"
      }
    }
  }
}
```

For Streamable HTTP (when the dashboard is running):

```json
{
  "mcpServers": {
    "ccdash-http": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Claude Desktop Configuration

For Claude Desktop (as opposed to Claude Code), configuration lives at `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "ccdash": {
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "cwd": "/path/to/CCDash"
    }
  }
}
```

### Discovery Flow

1. User adds `.mcp.json` to CCDash repo (or it ships with the repo)
2. Claude Code reads `.mcp.json` on project open
3. Claude Code spawns `python -m backend.mcp.server` as subprocess
4. MCP handshake: client sends `initialize`, server responds with capabilities (tools, resources list)
5. Agent can now call `list_tools` to discover available tools and their schemas
6. Agent calls tools as needed during conversation

---

## 7. Testing Strategy

### Unit Testing with In-Memory Transport

The MCP SDK provides an in-memory client that bypasses network transport, enabling fast, deterministic tests:

```python
import pytest
from mcp.server.fastmcp import FastMCP

from backend.mcp.server import mcp  # the FastMCP instance


@pytest.mark.asyncio
async def test_get_project_status():
    """Test the get_project_status tool returns expected shape."""
    async with mcp.test_client() as client:
        result = await client.call_tool("get_project_status", {})
        assert result is not None
        data = result[0].text  # TextContent
        parsed = json.loads(data)
        assert "status" in parsed
        assert "data" in parsed
```

The `mcp.test_client()` context manager creates an in-memory transport that connects the client directly to the server without stdio or HTTP, making tests fast and isolated.

### Integration Testing with Mocked Ports

Since CCDash tools delegate to `CorePorts`, tests can inject mock ports:

```python
@pytest.mark.asyncio
async def test_list_sessions_with_mock_storage():
    """Test list_sessions tool with mocked session repository."""
    mock_sessions = [
        {"id": "s1", "model": "claude-sonnet-4", "cost": 0.05},
        {"id": "s2", "model": "claude-opus-4", "cost": 0.25},
    ]

    with patch("backend.mcp.bootstrap.get_ports") as mock_get_ports:
        mock_ports = create_mock_ports(sessions=mock_sessions)
        mock_get_ports.return_value = mock_ports

        async with mcp.test_client() as client:
            result = await client.call_tool("list_sessions", {"limit": 10})
            parsed = json.loads(result[0].text)
            assert parsed["meta"]["count"] == 2
```

### End-to-End Testing

For E2E validation, the MCP ecosystem provides:

1. **MCP Inspector**: A web-based tool for interactively testing MCP servers (`npx @modelcontextprotocol/inspector`)
2. **Test harness**: The official [test harness repo](https://github.com/modelcontextprotocol/test-harness) for protocol compliance
3. **Manual testing**: Launch the stdio server and pipe JSON-RPC messages to validate behavior

### Test Matrix

| Test Type | Scope | Tools |
|-----------|-------|-------|
| Unit | Individual tool logic | pytest + `mcp.test_client()` |
| Integration | Tools with mocked CorePorts | pytest + unittest.mock |
| Protocol compliance | MCP handshake, capabilities | MCP Inspector |
| E2E | Full stack with real DB | pytest + test SQLite fixture |

---

## 8. Architecture: Proposed Module Structure

```
backend/
  mcp/
    __init__.py
    server.py          -> FastMCP instance, transport entry point
    bootstrap.py       -> Lightweight CorePorts initialization for stdio mode
    tools/
      __init__.py      -> register_tools() aggregator
      project.py       -> get_project_status, list_projects
      sessions.py      -> list_sessions, get_session_detail
      features.py      -> get_feature_status, get_feature_sessions
      analytics.py     -> get_cost_breakdown, get_analytics_overview
      documents.py     -> search_documents, get_document
      tasks.py         -> get_task_board, get_task_detail
    resources/
      __init__.py      -> register_resources() aggregator
      project.py       -> project config, model list resources
    context.py         -> MCP-specific RequestContext builder
  ...
```

### Integration Points

The MCP tools layer sits **above** the existing application services layer:

```
Claude Code / Agent
       |
  MCP Protocol (stdio or HTTP)
       |
  FastMCP Server (backend/mcp/server.py)
       |
  MCP Tool Handlers (backend/mcp/tools/)
       |
  Application Services (backend/application/services/)
       |
  CorePorts (backend/application/ports/core.py)
       |
  Repositories -> Database
```

This means MCP tools **reuse** the same business logic as the REST API. No duplication.

---

## 9. Implementation Roadmap

### Phase 1: Foundation + stdio Transport (3-5 days)

- Add `mcp` dependency to `requirements.txt`
- Create `backend/mcp/` module structure
- Implement `bootstrap.py` with lazy `CorePorts` init
- Implement 4-6 core tools (project status, list sessions, session detail, feature status, task board, cost breakdown)
- Implement 2-3 resources (project list, project config)
- Create `.mcp.json` for project-scoped Claude Code config
- Write unit tests with `mcp.test_client()`
- Test with Claude Code manually

### Phase 2: Streamable HTTP Mount (2-3 days)

- Add `streamable_http_app()` mount to `build_runtime_app()`
- Coordinate lifespan between `RuntimeContainer` and MCP session manager
- Add HTTP transport entry to `.mcp.json`
- Integration test HTTP endpoint
- Document both transport options

### Phase 3: Extended Tool Catalog (2-3 days)

- Document search tool
- Session transcript/message tools
- Analytics trend tools
- Feature forensics deep-dive tools
- Tool annotations (read-only hints, cost indicators)

### Phase 4: Polish and Docs (1-2 days)

- Error handling and edge cases
- Tool description refinement based on agent testing
- User documentation (setup guide)
- Developer documentation (adding new tools)

**Total estimated effort**: 8-13 days

---

## 10. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SDK v2 breaking changes | Medium | Medium | Pin to `mcp>=1.8,<2`; FastMCP decorator API is stable |
| stdio startup latency >3s | Medium | Low | Lazy DB init, minimal imports, keep process alive |
| SQLite concurrent access (stdio + dashboard) | Low | Medium | SQLite WAL mode handles concurrent readers well |
| Lifespan coordination bugs (HTTP mount) | Medium | Medium | Phase HTTP mount separately; test thoroughly |
| Tool descriptions inadequate for agents | High | Medium | Iterate based on real Claude Code testing; treat descriptions as UX |
| MCP protocol evolution | Low | Low | SDK abstracts protocol details; update SDK to track spec |
| Security: tools expose sensitive data | Medium | Low | stdio inherits user perms; HTTP mount behind localhost only |

---

## 11. Alternative Approaches Considered

### Alternative 1: fastapi-mcp (Auto-generate MCP from FastAPI routes)

The [`fastapi-mcp`](https://github.com/tadata-org/fastapi_mcp) library can automatically expose existing FastAPI endpoints as MCP tools.

**Pros**: Zero additional tool code; existing REST endpoints become MCP tools automatically.

**Cons**: Tool descriptions are derived from OpenAPI docs (often too terse for agents); no control over tool granularity; REST response shapes may not be optimal for agent consumption; couples MCP surface area to REST API changes; does not support stdio transport.

**Verdict**: Rejected. The REST API is designed for the frontend dashboard, not for agent consumption. Agent-optimized tool descriptions, response shapes, and granularity require intentional design.

### Alternative 2: Separate MCP server process with REST client

Run MCP as an independent process that calls the CCDash REST API over HTTP.

**Pros**: Complete decoupling; MCP server can be written in any language.

**Cons**: HTTP round-trip overhead; requires dashboard to be running; duplicates auth/context logic; adds network failure modes; harder to test.

**Verdict**: Rejected. Direct `CorePorts` access is simpler, faster, and more reliable.

### Alternative 3: MCP over WebSocket (custom transport)

Implement a custom WebSocket transport for real-time bidirectional communication.

**Pros**: Lower latency than HTTP polling; bidirectional streaming.

**Cons**: Not a standard MCP transport; no client support in Claude Code; significant custom protocol work.

**Verdict**: Rejected. Streamable HTTP already supports bidirectional communication via SSE. No need for custom transport.

---

## 12. ADR Recommendations

The following decisions are significant enough to warrant Architecture Decision Records:

1. **ADR: MCP Transport Strategy** -- Document the decision to use stdio as primary transport with Streamable HTTP as secondary, and the rationale for this ordering.

2. **ADR: MCP Tool Layer Architecture** -- Document the decision to create a dedicated `backend/mcp/` module that delegates to application services rather than auto-generating from REST endpoints or duplicating logic.

---

## 13. Open Questions

1. **Project context in stdio mode**: When Claude Code launches the MCP server, how does it know which CCDash project is active? Options: (a) pass project ID via env var, (b) use the active project from `projects.json`, (c) expose a `set_active_project` tool.

2. **Tool pagination**: For large result sets (hundreds of sessions), should tools paginate or return all results with a default limit? Agents handle pagination poorly; recommend generous default limits with explicit `limit` parameter.

3. **Embedding/semantic search**: Should the MCP server expose semantic search tools that use session embeddings? This depends on the session embedding infrastructure maturity.

4. **Rate limiting**: Should the HTTP transport have rate limiting? Probably not for local-first use, but worth considering if remote access is added.

---

## 14. Implementation Checklist

Ready for handoff to `implementation-planner`:

- [ ] Add `mcp>=1.8,<2` to `backend/requirements.txt`
- [ ] Create `backend/mcp/__init__.py`
- [ ] Create `backend/mcp/server.py` with FastMCP instance and `__main__` stdio entry point
- [ ] Create `backend/mcp/bootstrap.py` with lazy CorePorts initialization
- [ ] Create `backend/mcp/context.py` with MCP-specific RequestContext builder
- [ ] Create `backend/mcp/tools/project.py` with `get_project_status`, `list_projects`
- [ ] Create `backend/mcp/tools/sessions.py` with `list_sessions`, `get_session_detail`
- [ ] Create `backend/mcp/tools/features.py` with `get_feature_status`, `get_feature_sessions`
- [ ] Create `backend/mcp/tools/analytics.py` with `get_cost_breakdown`
- [ ] Create `backend/mcp/tools/documents.py` with `search_documents`, `get_document`
- [ ] Create `backend/mcp/tools/tasks.py` with `get_task_board`
- [ ] Create `backend/mcp/resources/project.py` with project config resources
- [ ] Create `.mcp.json` at repo root with stdio configuration
- [ ] Mount Streamable HTTP on FastAPI app at `/mcp` path
- [ ] Coordinate lifespan between RuntimeContainer and MCP session manager
- [ ] Write unit tests using `mcp.test_client()` in-memory transport
- [ ] Write integration tests with mocked CorePorts
- [ ] Test with Claude Code end-to-end
- [ ] Test with MCP Inspector for protocol compliance
- [ ] Document setup and tool catalog for users
- [ ] Document tool development guide for contributors

---

## References

- [MCP Python SDK - GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK - Documentation](https://py.sdk.modelcontextprotocol.io/)
- [FastMCP Documentation](https://gofastmcp.com/)
- [MCP Specification - Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP Specification - Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Specification - Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)
- [Claude Code MCP Configuration](https://code.claude.com/docs/en/mcp)
- [Connect Local MCP Servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
- [FastMCP Testing Guide](https://gofastmcp.com/servers/testing)
- [FastAPI-MCP Integration](https://github.com/tadata-org/fastapi_mcp)
- [MCP SDK Issue #1367 - Mounting on FastAPI](https://github.com/modelcontextprotocol/python-sdk/issues/1367)
- [Tool Annotations Blog Post](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
