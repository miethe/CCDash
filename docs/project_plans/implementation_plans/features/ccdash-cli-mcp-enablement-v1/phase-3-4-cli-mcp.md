---
schema_version: "1.0"
doc_type: phase_plan
title: "Phase 3–4: CLI Completion and MCP Execution Plan"
description: "Record Phase 3 completion and define the executable Phase 4 MCP plan against the current CCDash repo."
status: in-progress
created: "2026-04-02"
updated: "2026-04-12"
phase: "3-4"
phase_title: "CLI MVP complete; MCP MVP pending"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md"
entry_criteria:
  - Phase 1 (agent query services) complete and tested
  - Phase 2 (REST composite endpoints) complete and tested
  - Phase 3 (CLI MVP) complete and validated in-repo
  - Python 3.10+ and Typer/FastMCP SDK research complete (see SPIKE docs)
exit_criteria:
  - Phase 4: MCP server starts via `python -m backend.mcp.server` and exposes all 4 MVP tools over stdio
  - Phase 4: tool calls reuse existing Phase 1 query services with zero business-logic duplication
  - Phase 4: `.mcp.json` points Claude Code at the stdio server and manual discovery succeeds
  - Phase 4: automated coverage uses the SDK-supported `stdio_client` + `ClientSession` harness
priority: high
effort_estimate: 11-13
effort_estimate_unit: story_points
effort_estimate_breakdown: "Phase 3: completed (6–7 pts) | Phase 4: remaining (5–6 pts)"
duration_estimate: 5-7
duration_estimate_unit: days
can_parallelize: true
parallelization_note: "Phase 3 is complete. In Phase 4, test harness work and Claude Code config/docs can run in parallel after the MCP bootstrap and tools exist."
---

# Phase 3–4: CLI Completion and MCP Execution Plan

## Phase Overview

**Goal**: Expose the completed Phase 1 query services through two thin delivery adapters:
- **Phase 3 (CLI)**: complete in the current repo and retained here as the baseline adapter pattern
- **Phase 4 (MCP)**: the remaining execution scope; add a FastMCP stdio server for Claude Code and other MCP clients

**Current Status**:
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4: not started

**Key Invariant**: CLI and MCP remain transport adapters only. All business logic continues to live in `backend/application/services/agent_queries/`.

---

## Validation Notes (2026-04-12)

- Phase 3 is already implemented and complete in the current worktree; see `.claude/progress/ccdash-cli-mcp-enablement-v1/phase-3-progress.md`. Treat it as landed baseline, not open scope.
- The repo already contains `backend/cli`, a repo-root `pyproject.toml`, and `scripts/setup.mjs`; Typer/Rich packaging work is done and must not be replanned as pending Phase 4 work.
- `backend/cli/runtime.py` establishes the lightweight bootstrap pattern to reuse for MCP: `RuntimeContainer(profile=get_runtime_profile("test"))`, `RequestMetadata`, and `container.build_request_context(...)`.
- The repo does **not** contain `backend/mcp/` or a committed `.mcp.json`; Phase 4 remains unstarted and is the next execution target.
- `backend/requirements.txt` already includes `typer` and `rich` but does not yet include `mcp`.
- Phase 4 must not use `RequestContext.from_environment()` or a `local` runtime profile. Reuse the existing lightweight container bootstrap pattern used by the CLI.
- Phase 4 validation must not rely on speculative `mcp.test_client` guidance. Use the SDK-supported stdio harness: spawn the server with `stdio_client`, create a `ClientSession`, initialize it, then call `list_tools`/`call_tool`.

---

## Phase 3 Completion Snapshot

Phase 3 is closed. Treat it as implementation baseline, not future work.

### Delivered Surface

- `backend/cli/` Typer application and command modules exist
- lightweight CLI runtime bootstrap exists in `backend/cli/runtime.py`
- repo-root `pyproject.toml` publishes the `ccdash` console script
- `scripts/setup.mjs` installs the editable package
- focused CLI test coverage exists in `backend/tests/test_cli_commands.py`

### Verified Evidence

- `backend/.venv/bin/python -m backend.cli --help` passed during Phase 3 validation
- `backend/.venv/bin/ccdash --help` passed after editable install
- `backend/.venv/bin/python -m pytest backend/tests/test_cli_commands.py -q` passed (`8 passed`)

### Phase 3 Acceptance Criteria

- [x] `python -m backend.cli --help` works
- [x] `ccdash --help` works after editable install
- [x] All 4 MVP commands exist and delegate to Phase 1 query services
- [x] Human/JSON/Markdown output modes are covered
- [x] CLI packaging/setup integration exists in-repo
- [x] Phase 3 introduced no new business-logic duplication

---

## Phase 4: MCP Implementation

### Overview

Phase 4 adds a stdio-launched MCP server that exposes the same CCDash intelligence already available through REST and CLI. The server must bootstrap CCDash runtime state without spinning up HTTP, background jobs, or sync/watcher behavior.

**Core Tools**:
- `ccdash_project_status`
- `ccdash_feature_forensics`
- `ccdash_workflow_failure_patterns`
- `ccdash_generate_aar`

**Non-Negotiable Bootstrap Pattern**:

```python
from backend.application.context import RequestMetadata
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile

MCP_PROFILE = get_runtime_profile("test")

container = RuntimeContainer(profile=MCP_PROFILE)
...
context = await container.build_request_context(
    RequestMetadata(
        headers=headers,
        method="MCP",
        path=f"mcp://ccdash/{tool_name}",
    )
)
```

That is the repo-aligned pattern. Do not substitute `local` profile startup or `RequestContext.from_environment()`.

---

## Phase 4 Task Breakdown

### P4-T1: Add MCP Dependency and Bootstrap Package Skeleton

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: Phase 1-3 complete

**Description**:
Add the MCP SDK dependency and create the initial package structure with the same lightweight runtime bootstrap shape already used by the CLI.

**Detailed Tasks**:

1. Update `backend/requirements.txt` with a pinned v1-line MCP SDK dependency:
   ```text
   mcp>=1.8,<2
   ```
2. Create the package skeleton:
   ```text
   backend/mcp/
     __init__.py
     __main__.py
     server.py
     bootstrap.py
     tools/
       __init__.py
       project.py
       features.py
       workflows.py
       reports.py
   ```
3. Implement `backend/mcp/bootstrap.py` by mirroring the existing CLI bootstrap pattern:
   - use `RuntimeContainer(profile=get_runtime_profile("test"))`
   - create ports through `build_core_ports(...)`
   - cache the container for the server lifetime
   - expose helpers for request-context construction and shutdown
4. Build request context with `RequestMetadata` headers via `container.build_request_context(...)`; do not use `RequestContext.from_environment()` or a local runtime profile.

**Implementation Sketch**:

```python
from backend.application.context import RequestContext, RequestMetadata
from backend.application.ports import CorePorts
from backend.db import connection
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.runtime_ports import build_core_ports

MCP_PROFILE = get_runtime_profile("test")
_container: RuntimeContainer | None = None

async def bootstrap_mcp() -> RuntimeContainer:
    ...

async def get_app_request(
    *,
    tool_name: str,
    project_id: str | None = None,
) -> tuple[RequestContext, CorePorts]:
    headers: dict[str, str] = {}
    if project_id:
        headers["x-ccdash-project-id"] = project_id
    context = await container.build_request_context(
        RequestMetadata(
            headers=headers,
            method="MCP",
            path=f"mcp://ccdash/{tool_name}",
        )
    )
    return context, container.require_ports()
```

**Acceptance Criteria**:
- [ ] `backend/requirements.txt` includes `mcp>=1.8,<2`
- [ ] `backend/mcp/` imports without errors
- [ ] MCP bootstrap uses the existing test runtime profile via `RuntimeContainer(profile=get_runtime_profile("test"))`
- [ ] MCP bootstrap uses `RequestMetadata` plus `container.build_request_context(...)`
- [ ] No use of `RequestContext.from_environment()` or `get_runtime_profile("local")`

---

### P4-T2: Implement FastMCP Server and Four Thin Tool Adapters

**Effort**: 2 story points  
**Duration**: 1.5–2 days  
**Assignee**: Backend Engineer  
**Depends on**: P4-T1

**Description**:
Create the FastMCP server entry point and register the four MVP tools as thin wrappers over existing Phase 1 query services.

**Detailed Tasks**:

1. Create `backend/mcp/server.py` with a single FastMCP instance.
2. Expose stdio startup through `backend/mcp/__main__.py` so `python -m backend.mcp.server` remains the launch command used by the plan/PRD.
3. Implement each tool in `backend/mcp/tools/`:
   - bootstrap request context through `backend/mcp/bootstrap.py`
   - instantiate the corresponding Phase 1 query service
   - return a stable response envelope
4. Keep tool docstrings/descriptions agent-facing and concrete.
5. Centralize repeated response-envelope and error-path shaping if duplication appears.

**Required Response Envelope**:

```python
{
    "status": result.status,
    "data": result.model_dump(mode="json"),
    "meta": {
        "project_id": ...,
        "generated_at": ...,
        "data_freshness": ...,
        "source_refs": ...,
    },
}
```

**Acceptance Criteria**:
- [ ] `python -m backend.mcp.server` launches the stdio server without import/runtime errors
- [ ] All 4 tools are registered on one FastMCP instance
- [ ] Each tool delegates to exactly one Phase 1 query service path
- [ ] Tool descriptions are suitable for Claude Code discovery
- [ ] Response envelopes are consistent across tools

---

### P4-T3: Add SDK-Supported Stdio Client Harness Tests

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P4-T2

**Description**:
Validate the real stdio transport using the supported MCP client/session flow instead of an in-memory helper.

**Detailed Tasks**:

1. Add `backend/tests/test_mcp_server.py` (or a small `backend/tests/mcp/` suite) that:
   - launches the module with `StdioServerParameters`
   - opens a stdio client connection with `stdio_client`
   - initializes a `ClientSession`
   - asserts `list_tools()` includes the four MVP tools
   - calls each tool and validates the response envelope
2. Cover three path types:
   - happy path
   - partial availability (`status: partial`)
   - user-facing error path (`status: error` or equivalent envelope)
3. Prefer patching the shared bootstrap/service seams rather than bypassing transport entirely.

**Harness Pattern**:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(
    command=python_executable,
    args=["-m", "backend.mcp.server"],
    cwd=repo_root,
)

async with stdio_client(server) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("ccdash_project_status", {})
```

**Acceptance Criteria**:
- [ ] Automated tests use `stdio_client` + `ClientSession`
- [ ] `initialize`, `list_tools`, and `call_tool` are all exercised
- [ ] Each MVP tool has coverage for success and at least one non-success path
- [ ] Tests validate the same transport that Claude Code will use

---

### P4-T4: Add `.mcp.json` Workspace Configuration

**Effort**: 1 story point  
**Duration**: 0.5 day  
**Assignee**: Backend Engineer  
**Depends on**: P4-T2

**Description**:
Commit the workspace MCP configuration that points Claude Code at the stdio server.

**Detailed Tasks**:

1. Create a repo-root `.mcp.json`:
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
           "CCDASH_DATA_DIR": "./data",
           "CCDASH_SQLITE_BUSY_TIMEOUT_MS": "30000"
         }
       }
     }
   }
   ```
2. Keep the launch command aligned with the PRD and plan.
3. Verify the config works with the actual server startup path used in tests/manual validation.

**Acceptance Criteria**:
- [ ] `.mcp.json` exists at repo root
- [ ] Config points to `python -m backend.mcp.server`
- [ ] Workspace env is sufficient for local CCDash startup
- [ ] Config stays aligned with the automated stdio harness

---

### P4-T5: Manual Claude Code Validation and Phase Closeout

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer + Reviewer  
**Depends on**: P4-T3, P4-T4

**Description**:
Run the end-to-end Claude Code verification path and close Phase 4 only after both automated and manual discovery work.

**Detailed Tasks**:

1. Open the workspace with `.mcp.json` present.
2. Confirm Claude Code discovers the `ccdash` MCP server and the four tools.
3. Invoke each tool manually at least once.
4. Record any discrepancies between automated stdio tests and manual agent UX.
5. Update progress artifacts with final validation evidence before marking complete.

**Acceptance Criteria**:
- [ ] Claude Code discovers the server from `.mcp.json`
- [ ] All 4 tools are callable manually
- [ ] Manual results are consistent with automated stdio harness tests
- [ ] Phase 4 progress artifact contains final evidence and closeout notes

---

## Phase 4 Execution Sequence

### Required Order

1. **P4-T1**: add the MCP dependency and bootstrap skeleton on the existing test-profile runtime path
2. **P4-T2**: wire the FastMCP server and four thin tool adapters
3. **P4-T3** and **P4-T4**: add stdio transport coverage and workspace config in parallel after the server boots
4. **P4-T5**: run manual Claude Code discovery and close out the phase only after automated and manual validation agree

### Critical Path

`P4-T1 → P4-T2 → P4-T3 → P4-T5`

### Parallel Work Window

After `P4-T2`, the `.mcp.json` work and most automated test work can proceed independently.

---

## Quality Gates

### Phase 3 Quality Gate (Closed)

- [x] CLI installed as `ccdash`
- [x] All 4 MVP commands work
- [x] Focused CLI tests pass
- [x] Setup/install path exists in-repo
- [x] No business logic duplication beyond Phase 1

### Phase 4 Quality Gate (Open)

- [ ] `backend/requirements.txt` includes the pinned MCP SDK dependency and `backend/mcp/` imports cleanly
- [ ] `python -m backend.mcp.server` starts successfully over stdio with the existing test runtime profile
- [ ] All 4 tools are registered and callable
- [ ] Bootstrap reuses `RuntimeContainer(profile=get_runtime_profile("test"))`, `RequestMetadata`, and `container.build_request_context(...)`
- [ ] Automated coverage uses `stdio_client` + `ClientSession`
- [ ] `.mcp.json` is committed and points to the same stdio server launch command validated in tests
- [ ] Claude Code discovers and successfully invokes the tools manually

---

## Files Summary

### Phase 3 Existing Files (Already In Repo)

- `backend/cli/__init__.py`
- `backend/cli/__main__.py`
- `backend/cli/main.py`
- `backend/cli/runtime.py`
- `backend/cli/output.py`
- `backend/cli/commands/status.py`
- `backend/cli/commands/feature.py`
- `backend/cli/commands/workflow.py`
- `backend/cli/commands/report.py`
- `backend/cli/formatters/base.py`
- `backend/cli/formatters/json.py`
- `backend/cli/formatters/markdown.py`
- `backend/cli/formatters/table.py`
- `backend/tests/test_cli_commands.py`
- `pyproject.toml`
- `scripts/setup.mjs`

### Phase 4 Planned Files

- `backend/mcp/__init__.py`
- `backend/mcp/__main__.py`
- `backend/mcp/server.py`
- `backend/mcp/bootstrap.py`
- `backend/mcp/tools/__init__.py`
- `backend/mcp/tools/project.py`
- `backend/mcp/tools/features.py`
- `backend/mcp/tools/workflows.py`
- `backend/mcp/tools/reports.py`
- `backend/tests/test_mcp_server.py` or `backend/tests/mcp/*`
- `.mcp.json`
- `backend/requirements.txt`

---

## Effort Breakdown

### Phase 3

| Task | Status | Effort |
|------|--------|--------|
| CLI package/app/bootstrap | complete | 1 pt |
| Output formatters | complete | 1 pt |
| Four MVP commands | complete | 3 pts |
| CLI tests | complete | 1 pt |
| Packaging/setup integration | complete | 1 pt |
| Validation | complete | 1 pt |
| **Phase 3 Total** | **complete** | **6–7 pts** |

### Phase 4

| Task | Status | Effort |
|------|--------|--------|
| P4-T1 dependency + bootstrap skeleton | pending | 1 pt |
| P4-T2 FastMCP server + tools | pending | 2 pts |
| P4-T3 stdio harness tests | pending | 1 pt |
| P4-T4 `.mcp.json` config | pending | 1 pt |
| P4-T5 manual Claude Code validation | pending | 1 pt |
| **Phase 4 Total** | **pending** | **5–6 pts** |

---

## Ready-to-Execute Checklist

Phase 4 is ready to begin when the implementer follows these repo-specific constraints:

- [x] Treat Phase 3 as complete and reuse its bootstrap/packaging decisions
- [x] Use the existing test runtime profile via `RuntimeContainer(profile=get_runtime_profile("test"))`
- [x] Build request context with `RequestMetadata` and `container.build_request_context(...)`
- [x] Validate via `stdio_client` + `ClientSession`
- [x] Keep `.mcp.json` aligned with the tested stdio command
- [x] Avoid introducing a new local-profile/runtime path just for MCP

---

## Document Metadata

- **Version**: 1.1
- **Last Updated**: 2026-04-12
- **Status**: In Progress (Phase 3 complete; Phase 4 ready for execution)
