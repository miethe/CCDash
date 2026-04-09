---
schema_version: "1.0"
doc_type: phase_plan
title: "Phase 3–4: CLI and MCP Implementation"
description: "Implement Python CLI (Typer) and MCP server (FastMCP) for agent and operator access to CCDash intelligence."
status: draft
created: "2026-04-02"
updated: "2026-04-02"
phase: "3-4"
phase_title: "CLI MVP and MCP MVP"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md"
entry_criteria:
  - Phase 1 (agent query services) complete and tested
  - Phase 2 (REST endpoints) complete and tested (recommended but not strictly required)
  - Python 3.10+ and Typer/FastMCP SDK research complete (see SPIKE docs)
  - SQLite with WAL mode and busy timeout configured
exit_criteria:
  - Phase 3: CLI installed as `ccdash` command, all 4 MVP commands working, tests passing, startup <500ms
  - Phase 4: MCP server starts via `python -m backend.mcp.server`, all 4 tools callable, `.mcp.json` configured, Claude Code discovers tools
  - Both phases: Zero business logic duplication with Phase 1 services
priority: high
effort_estimate: 11-13
effort_estimate_unit: story_points
effort_estimate_breakdown: "Phase 3: 6–7 pts | Phase 4: 5–6 pts"
duration_estimate: 10-14
duration_estimate_unit: days
can_parallelize: true
parallelization_note: "Phase 3 and 4 can proceed in parallel after Phase 1 is stable. They do not depend on each other."
---

# Phase 3–4: CLI and MCP Implementation

## Phase Overview

**Goal**: Expose Phase 1 agent query services via two delivery channels:
- **Phase 3 (CLI)**: Local command-line interface for operators and scripts using Typer framework
- **Phase 4 (MCP)**: Agent-facing tools for Claude Code using FastMCP stdio transport

**Why Together**: Both phases have similar architecture (thin adapters around Phase 1 services) and can proceed in parallel once Phase 1 is stable.

**Key Invariant**: No business logic duplication. Both CLI and MCP delegate to Phase 1 query services.

---

## PHASE 3: CLI Implementation

### Overview

The CLI (`ccdash` command) is a local, operator-friendly interface for CCDash intelligence. It bootstraps its own database connection and CorePorts instance, requiring no running web server. Output supports human-readable (default), JSON (agents/scripts), and Markdown (reports) formats.

**Core Commands** (MVP):
- `ccdash status project` — display project status
- `ccdash feature report <id>` — display feature forensics
- `ccdash workflow failures` — display problematic workflows
- `ccdash report aar --feature <id>` — generate markdown after-action review

---

## Phase 3 Task Breakdown

### P3-T1: Create CLI Package Structure and Typer App

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: Phase 1 complete

**Description**:
Set up the CLI package with Typer app structure and dependency injection.

**Detailed Tasks**:

1. Create `backend/cli/` directory structure:
   ```
   backend/cli/
     __init__.py
     __main__.py              # python -m backend.cli entry point
     main.py                  # Root Typer app
     runtime.py               # CLI bootstrap (CorePorts, DB)
     output.py                # OutputMode enum, formatter selection
     commands/
       __init__.py
       status.py              # ccdash status project
       feature.py             # ccdash feature report <id>
       workflow.py            # ccdash workflow failures
       report.py              # ccdash report aar
     formatters/
       __init__.py
       base.py                # OutputFormatter protocol
       table.py               # TableFormatter (human-readable)
       json.py                # JsonFormatter (--json)
       markdown.py            # MarkdownFormatter (--md)
   ```

2. Create `backend/cli/__main__.py`:
   ```python
   from backend.cli.main import app

   if __name__ == "__main__":
       app()
   ```

3. Create `backend/cli/main.py` (Typer root app):
   ```python
   import typer
   from enum import Enum

   class OutputMode(str, Enum):
       human = "human"
       json = "json"
       markdown = "markdown"

   app = typer.Typer(help="CCDash CLI for project intelligence access")

   # Global options callback
   @app.callback()
   def main(
       output: OutputMode = typer.Option(
           OutputMode.human,
           "--output",
           help="Output format: human, json, or markdown",
       ),
       project: str | None = typer.Option(
           None,
           "--project",
           help="Override active project ID",
       ),
   ):
       """CCDash command-line interface for agent and operator access."""
       # Set globals for command handlers to access
       import backend.cli.runtime as runtime
       runtime.OUTPUT_MODE = output
       runtime.PROJECT_OVERRIDE = project

   # Register subcommand groups
   app.add_typer(status_app, name="status", help="Show project and feature status")
   app.add_typer(feature_app, name="feature", help="Feature-focused commands")
   app.add_typer(workflow_app, name="workflow", help="Workflow diagnostics")
   app.add_typer(report_app, name="report", help="Generate reports (AAR, summaries)")
   ```

4. Create `backend/cli/runtime.py` (CLI bootstrap):
   ```python
   import asyncio
   from backend.application.ports import CorePorts
   from backend.db import connection
   from backend.runtime_ports import build_core_ports
   from backend.runtime.profiles import get_runtime_profile
   from backend.config import STORAGE_PROFILE

   # Globals set by main() callback
   OUTPUT_MODE = "human"
   PROJECT_OVERRIDE: str | None = None

   _ports: CorePorts | None = None

   async def bootstrap_cli() -> CorePorts:
       """Bootstrap CLI runtime: lightweight, no HTTP server."""
       global _ports
       if _ports is not None:
           return _ports
       db = await connection.get_connection()
       profile = get_runtime_profile("local")  # or new "cli" profile
       _ports = build_core_ports(
           db,
           runtime_profile=profile,
           storage_profile=STORAGE_PROFILE,
       )
       return _ports

   async def teardown_cli() -> None:
       global _ports
       _ports = None
       await connection.close_connection()

   def get_context() -> RequestContext:
       """Get request context with optional project override."""
       ctx = RequestContext.from_environment()
       if PROJECT_OVERRIDE:
           ctx.project.project_id = PROJECT_OVERRIDE
       return ctx
   ```

5. Create `backend/cli/output.py`:
   ```python
   from enum import Enum
   from backend.cli.formatters.base import OutputFormatter
   from backend.cli.formatters.table import TableFormatter
   from backend.cli.formatters.json import JsonFormatter
   from backend.cli.formatters.markdown import MarkdownFormatter

   class OutputMode(str, Enum):
       human = "human"
       json = "json"
       markdown = "markdown"

   def get_formatter(mode: OutputMode) -> OutputFormatter:
       match mode:
           case OutputMode.json:
               return JsonFormatter()
           case OutputMode.markdown:
               return MarkdownFormatter()
           case _:
               return TableFormatter()
   ```

**Files to Create**:
- `backend/cli/__init__.py`
- `backend/cli/__main__.py`
- `backend/cli/main.py`
- `backend/cli/runtime.py`
- `backend/cli/output.py`
- `backend/cli/commands/__init__.py`
- `backend/cli/formatters/__init__.py`

**Acceptance Criteria**:
- [ ] `python -m backend.cli --help` works
- [ ] Typer app structure created with subcommand groups
- [ ] Output mode global available to command handlers
- [ ] Bootstrap functions (CLI runtime init/teardown) functional
- [ ] No import errors

---

### P3-T2: Implement Output Formatters

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer  
**Depends on**: P3-T1

**Description**:
Implement the three output formatter classes (human-readable table, JSON, Markdown).

**Detailed Tasks**:

1. Create `backend/cli/formatters/base.py`:
   ```python
   from typing import Protocol, Any

   class OutputFormatter(Protocol):
       """Protocol for output formatters."""
       
       def render(self, data: Any, *, title: str = "") -> str:
           """Render data to a string for stdout."""
           ...
   ```

2. Create `backend/cli/formatters/table.py`:
   - Use Rich library (already in requirements for backend) for table rendering
   - Render Pydantic models to human-readable tables and text
   - Example: ProjectStatusDTO → "Project: my-project | Features: 5 done, 2 in-progress | Cost: $23.45"

3. Create `backend/cli/formatters/json.py`:
   ```python
   import json
   from pydantic import BaseModel

   class JsonFormatter:
       def render(self, data: Any, *, title: str = "") -> str:
           if isinstance(data, BaseModel):
               return json.dumps(data.model_dump(mode="json"), indent=2, default=str)
           return json.dumps(data, indent=2, default=str)
   ```

4. Create `backend/cli/formatters/markdown.py`:
   - Render Pydantic models to markdown (headers, tables, lists, code blocks)
   - Example: AARReportDTO → markdown with # Scope, ## Timeline, etc.

**Files to Create**:
- `backend/cli/formatters/base.py`
- `backend/cli/formatters/table.py`
- `backend/cli/formatters/json.py`
- `backend/cli/formatters/markdown.py`

**Acceptance Criteria**:
- [ ] All 3 formatters implement OutputFormatter protocol
- [ ] JSON formatter produces valid JSON
- [ ] Table formatter uses Rich for clean output
- [ ] Markdown formatter produces valid markdown
- [ ] Formatters handle nested objects (lists, dicts, Pydantic models)

---

### P3-T3: Implement Core CLI Commands

**Effort**: 3 story points  
**Duration**: 2–3 days  
**Assignee**: Backend Engineer  
**Depends on**: P3-T1, P3-T2

**Description**:
Implement the four MVP commands: status, feature, workflow, report.

**Detailed Tasks**:

1. Create `backend/cli/commands/status.py`:
   ```python
   import typer
   from backend.cli.runtime import bootstrap_cli, get_context
   from backend.cli.output import get_formatter, OUTPUT_MODE
   from backend.application.services.agent_queries import ProjectStatusQueryService

   status_app = typer.Typer()

   @status_app.command()
   async def project(
       json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
       md_output: bool = typer.Option(False, "--md", help="Output as Markdown"),
   ):
       """Show current project status summary."""
       ports = await bootstrap_cli()
       context = get_context()
       service = ProjectStatusQueryService()
       result = await service.get_status(context, ports)
       
       # Select formatter
       if json_output:
           formatter = get_formatter("json")
       elif md_output:
           formatter = get_formatter("markdown")
       else:
           formatter = get_formatter("human")
       
       print(formatter.render(result, title="Project Status"))
   ```

2. Create `backend/cli/commands/feature.py`:
   ```python
   # ccdash feature report <id>
   ```

3. Create `backend/cli/commands/workflow.py`:
   ```python
   # ccdash workflow failures
   ```

4. Create `backend/cli/commands/report.py`:
   ```python
   # ccdash report aar --feature <id>
   ```

5. Each command:
   - Calls one Phase 1 query service
   - Supports human/JSON/Markdown output modes
   - Exits 0 on success, non-zero on error
   - Writes error messages to stderr

**Files to Create**:
- `backend/cli/commands/status.py`
- `backend/cli/commands/feature.py`
- `backend/cli/commands/workflow.py`
- `backend/cli/commands/report.py`

**Acceptance Criteria**:
- [ ] All 4 commands exist and are invocable
- [ ] Each command outputs valid data in all 3 formats (human/JSON/MD)
- [ ] Commands exit 0 on success, non-zero on error
- [ ] Error messages are user-friendly
- [ ] JSON output is valid (pipe to jq)
- [ ] Markdown output is valid markdown

---

### P3-T4: Write CliRunner Tests for All Commands

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P3-T3

**Description**:
Write comprehensive CliRunner tests for all 4 MVP commands using Typer's test utilities.

**Detailed Tasks**:

1. Create `backend/tests/cli/test_commands_status.py`:
   - Test `ccdash status project` with human/JSON/Markdown output
   - Test with missing/stale database
   - Test with empty project

2. Create similar test modules for feature, workflow, report commands

3. Use pytest fixtures for:
   - CLI test database
   - Pre-seeded test data
   - CliRunner instance

4. Test matrix per command:
   - Happy path (complete data)
   - Partial availability (status: partial returned)
   - Error case (feature not found, etc.)
   - Output format validation (JSON parseable, etc.)

**Files to Create**:
- `backend/tests/cli/__init__.py`
- `backend/tests/cli/conftest.py` (fixtures)
- `backend/tests/cli/test_commands_status.py`
- `backend/tests/cli/test_commands_feature.py`
- `backend/tests/cli/test_commands_workflow.py`
- `backend/tests/cli/test_commands_report.py`

**Acceptance Criteria**:
- [ ] All CliRunner tests pass
- [ ] Each command tested in all 3 output modes
- [ ] Error cases handled gracefully
- [ ] No unhandled exceptions
- [ ] JSON output validates with jq

---

### P3-T5: Create Entry Point and Integration with npm run setup

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer + DevOps  
**Depends on**: P3-T1 through P3-T4

**Description**:
Package the CLI as a pip entry point and integrate with `npm run setup`.

**Detailed Tasks**:

1. Add to `pyproject.toml` (or `setup.py`):
   ```toml
   [project.scripts]
   ccdash = "backend.cli.main:app"
   ```

2. Modify `npm run setup` script:
   ```bash
   npm run setup:python
   cd backend && pip install -e .
   cd ..
   ```

3. Create optional shell wrapper in `bin/ccdash` for convenience:
   ```bash
   #!/usr/bin/env bash
   SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
   exec "$SCRIPT_DIR/backend/.venv/bin/python" -m backend.cli "$@"
   ```

4. Update README.md with CLI usage guide:
   - `ccdash --help` overview
   - Quick start example
   - Output format options
   - Common workflows

**Files to Create/Modify**:
- `pyproject.toml` (add [project.scripts])
- `npm run setup` script (extend)
- `bin/ccdash` (optional convenience wrapper)
- `README.md` (add CLI section)

**Acceptance Criteria**:
- [ ] `pip install -e .` installs `ccdash` command
- [ ] `ccdash --help` works after install
- [ ] `npm run setup` includes the install step
- [ ] Shell wrapper (if created) works as fallback
- [ ] README documents CLI usage

---

### P3-T6: Verify Startup Performance and Integration

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer  
**Depends on**: P3-T5

**Description**:
Benchmark CLI startup time and verify it works alongside the running web server (concurrent SQLite access).

**Detailed Tasks**:

1. Benchmark startup time:
   ```bash
   time ccdash status project --json > /dev/null
   ```
   - Target: <500 ms from invocation to first output
   - Run on development machine with SQLite
   - If over budget, profile and optimize (lazy imports, deferred DB init)

2. Test concurrent access:
   - Run `npm run dev:backend` (FastAPI web server)
   - In another terminal: `ccdash status project`
   - Verify both succeed without lock timeouts
   - Repeat 5 times to ensure stability

3. Create performance notes in CLI README or dev docs

**Files to Modify**:
- `README.md` (add performance notes)

**Acceptance Criteria**:
- [ ] CLI startup <500 ms measured with `time` command
- [ ] CLI and web server can read simultaneously without locks
- [ ] No SQLite "database is locked" errors in repeated runs
- [ ] Performance notes documented

---

## PHASE 4: MCP Implementation

### Overview

The MCP server exposes CCDash intelligence as tools for coding agents like Claude Code. It uses the FastMCP framework with stdio transport as primary and optional Streamable HTTP as secondary. The server bootstraps its own CorePorts instance and has no dependency on the web server running.

**Core Tools** (MVP):
- `ccdash_project_status` — get project status
- `ccdash_feature_forensics` — get feature forensics
- `ccdash_workflow_failure_patterns` — identify problematic workflows
- `ccdash_generate_aar` — generate after-action review

---

## Phase 4 Task Breakdown

### P4-T1: Add MCP Dependency and Create Package Structure

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: Phase 1 complete

**Description**:
Add FastMCP to dependencies and create the MCP package structure.

**Detailed Tasks**:

1. Update `backend/requirements.txt`:
   ```
   mcp>=1.8,<2
   ```

2. Create `backend/mcp/` directory structure:
   ```
   backend/mcp/
     __init__.py
     __main__.py              # python -m backend.mcp.server entry point
     server.py                # FastMCP instance + stdio bootstrap
     bootstrap.py             # Lazy CorePorts initialization
     context.py               # MCP RequestContext builder
     tools/
       __init__.py            # register_tools() aggregator
       project.py             # ccdash_project_status
       features.py            # ccdash_feature_forensics
       workflows.py           # ccdash_workflow_failure_patterns
       reports.py             # ccdash_generate_aar
   ```

3. Create `backend/mcp/__main__.py`:
   ```python
   from backend.mcp.server import mcp

   if __name__ == "__main__":
       mcp.run(transport="stdio")
   ```

4. Create `backend/mcp/bootstrap.py` (lazy CorePorts init):
   ```python
   import asyncio
   from backend.application.ports import CorePorts
   from backend.db import connection
   from backend.runtime_ports import build_core_ports
   from backend.runtime.profiles import get_runtime_profile
   from backend.config import STORAGE_PROFILE

   _ports: CorePorts | None = None

   async def get_ports() -> CorePorts:
       """Get or initialize CorePorts (lazy, per-tool-call)."""
       global _ports
       if _ports is None:
           db = await connection.get_connection()
           profile = get_runtime_profile("local")
           _ports = build_core_ports(
               db,
               runtime_profile=profile,
               storage_profile=STORAGE_PROFILE,
           )
       return _ports
   ```

5. Create `backend/mcp/context.py`:
   ```python
   from backend.application.context import RequestContext

   def build_mcp_context(project_id: str | None = None) -> RequestContext:
       """Build RequestContext for MCP tool calls."""
       ctx = RequestContext.from_environment()
       if project_id:
           ctx.project.project_id = project_id
       return ctx
   ```

**Files to Create**:
- `backend/mcp/__init__.py`
- `backend/mcp/__main__.py`
- `backend/mcp/bootstrap.py`
- `backend/mcp/context.py`
- `backend/mcp/tools/__init__.py`

**Files to Modify**:
- `backend/requirements.txt` (add mcp>=1.8,<2)

**Acceptance Criteria**:
- [ ] `pip install -r requirements.txt` installs mcp successfully
- [ ] `python -m backend.mcp.server --help` works (or shows expected startup message)
- [ ] Package imports without errors

---

### P4-T2: Implement FastMCP Server and Core Tools

**Effort**: 3 story points  
**Duration**: 2–3 days  
**Assignee**: Backend Engineer  
**Depends on**: P4-T1

**Description**:
Implement the FastMCP server and all 4 core tools.

**Detailed Tasks**:

1. Create `backend/mcp/server.py`:
   ```python
   from mcp.server.fastmcp import FastMCP
   from backend.mcp.tools import register_tools

   mcp = FastMCP(
       "CCDash Intelligence",
       log_level="WARNING",
   )

   # Register all tools
   register_tools(mcp)

   # Optional: register resources (Phase 5)
   # register_resources(mcp)
   ```

2. Create `backend/mcp/tools/project.py`:
   ```python
   @mcp.tool(description="Get current project status with feature counts, session activity, and cost trends.")
   async def ccdash_project_status(
       project_id: str | None = None,
   ) -> dict:
       """Get project status for planning and status checks."""
       ports = await get_ports()
       ctx = build_mcp_context(project_id)
       service = ProjectStatusQueryService()
       result = await service.get_status(ctx, ports)
       return {
           "status": result.status,
           "data": result.model_dump(),
           "meta": {
               "project_id": result.project_id,
               "generated_at": result.generated_at.isoformat(),
               "data_freshness": result.data_freshness.isoformat(),
           },
       }
   ```

3. Create `backend/mcp/tools/features.py`:
   ```python
   @mcp.tool(description="Get detailed feature development history including sessions, costs, and failure patterns.")
   async def ccdash_feature_forensics(feature_id: str) -> dict:
       """Get feature forensics for analysis and planning."""
       # Similar pattern to project_status
   ```

4. Create `backend/mcp/tools/workflows.py`:
   ```python
   @mcp.tool(description="Identify problematic workflows with high failure rates or low effectiveness.")
   async def ccdash_workflow_failure_patterns(
       feature_id: str | None = None,
   ) -> dict:
       """Get workflow diagnostics and failure patterns."""
       # Similar pattern
   ```

5. Create `backend/mcp/tools/reports.py`:
   ```python
   @mcp.tool(description="Generate an after-action review with scope, timeline, metrics, and lessons learned.")
   async def ccdash_generate_aar(feature_id: str) -> dict:
       """Generate an AAR report for a feature."""
       # Similar pattern
   ```

6. Create `backend/mcp/tools/__init__.py`:
   ```python
   def register_tools(mcp) -> None:
       """Register all MCP tools."""
       from . import project, features, workflows, reports
       # Tools are auto-registered via @mcp.tool() decorators
   ```

**Files to Create**:
- `backend/mcp/server.py`
- `backend/mcp/tools/project.py`
- `backend/mcp/tools/features.py`
- `backend/mcp/tools/workflows.py`
- `backend/mcp/tools/reports.py`

**Acceptance Criteria**:
- [ ] All 4 tools defined with @mcp.tool() decorator
- [ ] Tools have descriptive docstrings (agent-facing UX)
- [ ] Each tool returns response envelope: {status, data, meta}
- [ ] No unhandled exceptions (all error handling via status: error)
- [ ] Tools callable via mcp.test_client()

---

### P4-T3: Write MCP Tool Tests

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P4-T2

**Description**:
Write unit tests for all 4 MCP tools using mcp.test_client() in-memory transport.

**Detailed Tasks**:

1. Create `backend/tests/mcp/test_tools_project.py`:
   ```python
   import pytest
   from mcp.test_client import test_client

   @pytest.mark.asyncio
   async def test_ccdash_project_status():
       """Test project_status tool returns valid response."""
       async with test_client(mcp_server=mcp) as client:
           result = await client.call_tool("ccdash_project_status", {})
           assert result is not None
           data = json.loads(result[0].text)
           assert "status" in data
           assert "data" in data
           assert "meta" in data
   ```

2. Create similar test modules for features, workflows, reports tools

3. Test scenarios:
   - Happy path: valid params, complete data
   - Partial: subsystem unavailable, status: partial
   - Error: feature not found, status: error
   - Optional params: None, empty list, etc.

**Files to Create**:
- `backend/tests/mcp/__init__.py`
- `backend/tests/mcp/conftest.py` (fixtures)
- `backend/tests/mcp/test_tools_project.py`
- `backend/tests/mcp/test_tools_features.py`
- `backend/tests/mcp/test_tools_workflows.py`
- `backend/tests/mcp/test_tools_reports.py`

**Acceptance Criteria**:
- [ ] All mcp.test_client() tests pass
- [ ] Each tool tested for happy path and error cases
- [ ] Response envelope valid (status, data, meta fields present)
- [ ] No unhandled exceptions

---

### P4-T4: Create .mcp.json Configuration for Claude Code

**Effort**: 1 story point  
**Duration**: 0.5 day  
**Assignee**: Backend Engineer  
**Depends on**: P4-T2

**Description**:
Create `.mcp.json` configuration file for Claude Code discovery.

**Detailed Tasks**:

1. Create `.mcp.json` at repository root:
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

2. Add to `.gitignore` (if needed):
   - Nothing; `.mcp.json` should be committed

3. Create user documentation:
   - How Claude Code discovers MCP servers
   - How to enable in Claude Code (open settings, add .mcp.json path)
   - Troubleshooting (server not starting, tools not discovered)

**Files to Create**:
- `.mcp.json` (at repo root)
- `docs/guides/mcp-setup-guide.md` (user guide)

**Acceptance Criteria**:
- [ ] `.mcp.json` exists at repo root
- [ ] Claude Code can read and parse `.mcp.json`
- [ ] Stdio command line correct (python -m backend.mcp.server)
- [ ] Environment variables passed correctly

---

### P4-T5: Manual Testing with Claude Code and Documentation

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer + Architecture Reviewer  
**Depends on**: P4-T4

**Description**:
Manually test MCP server with Claude Code and write developer documentation.

**Detailed Tasks**:

1. Manual testing:
   - Open CCDash repo in Claude Code
   - Verify `.mcp.json` is recognized
   - Verify MCP server process launches
   - Call each tool from Claude Code chat
   - Verify responses are correct and complete

2. Create `backend/mcp/README.md`:
   - Overview of MCP server
   - How to add a new tool (template, conventions)
   - Tool design guidelines (docstrings, response format)
   - Testing expectations

3. Create troubleshooting guide:
   - "Server not starting"
   - "Tools not discovered"
   - "Tool calls timeout"
   - "Permission denied"

**Files to Create**:
- `backend/mcp/README.md`
- `docs/guides/mcp-troubleshooting.md`

**Acceptance Criteria**:
- [ ] Manual E2E test with Claude Code successful (tools callable, responses valid)
- [ ] README provides guidance for future tool development
- [ ] Troubleshooting guide covers common issues
- [ ] No critical issues found in testing

---

## Quality Gates

### Phase 3 Quality Gate (CLI)

All of the following must be true:

1. **`python -m backend.cli --help` works**
2. **All 4 MVP commands exist and exit 0 with valid output**
3. **Each command works in all 3 output modes** (human/JSON/Markdown)
4. **JSON output is valid** (pipe to jq)
5. **CLI startup <500 ms** (measured with time command)
6. **CliRunner tests passing** (all commands, all modes)
7. **`ccdash` command available** after `npm run setup`
8. **CLI + web server coexist** without SQLite lock errors

### Phase 4 Quality Gate (MCP)

All of the following must be true:

1. **`python -m backend.mcp.server` starts without error**
2. **`.mcp.json` exists and is valid**
3. **All 4 core tools callable via mcp.test_client()**
4. **All tools return valid response envelope** (status, data, meta)
5. **All tools handle errors gracefully** (no unhandled exceptions)
6. **mcp.test_client() tests passing** (all tools, all scenarios)
7. **Claude Code discovers tools** (manual verification)
8. **Claude Code can call tools successfully** (manual verification)

---

## Files Summary

### Phase 3 Files

**New files created**:
- `backend/cli/__init__.py`
- `backend/cli/__main__.py`
- `backend/cli/main.py`
- `backend/cli/runtime.py`
- `backend/cli/output.py`
- `backend/cli/commands/__init__.py`
- `backend/cli/commands/status.py`
- `backend/cli/commands/feature.py`
- `backend/cli/commands/workflow.py`
- `backend/cli/commands/report.py`
- `backend/cli/formatters/__init__.py`
- `backend/cli/formatters/base.py`
- `backend/cli/formatters/table.py`
- `backend/cli/formatters/json.py`
- `backend/cli/formatters/markdown.py`
- `backend/tests/cli/__init__.py`
- `backend/tests/cli/conftest.py`
- `backend/tests/cli/test_commands_status.py`
- `backend/tests/cli/test_commands_feature.py`
- `backend/tests/cli/test_commands_workflow.py`
- `backend/tests/cli/test_commands_report.py`
- `bin/ccdash` (optional convenience wrapper)

**Files modified**:
- `pyproject.toml` (add [project.scripts] entry)
- `npm run setup` script (extend with pip install -e .)
- `README.md` (add CLI section)

**Phase 3 total**: ~1800 lines (commands + formatters + tests)

### Phase 4 Files

**New files created**:
- `backend/mcp/__init__.py`
- `backend/mcp/__main__.py`
- `backend/mcp/server.py`
- `backend/mcp/bootstrap.py`
- `backend/mcp/context.py`
- `backend/mcp/tools/__init__.py`
- `backend/mcp/tools/project.py`
- `backend/mcp/tools/features.py`
- `backend/mcp/tools/workflows.py`
- `backend/mcp/tools/reports.py`
- `backend/tests/mcp/__init__.py`
- `backend/tests/mcp/conftest.py`
- `backend/tests/mcp/test_tools_project.py`
- `backend/tests/mcp/test_tools_features.py`
- `backend/tests/mcp/test_tools_workflows.py`
- `backend/tests/mcp/test_tools_reports.py`
- `.mcp.json` (at repo root)
- `docs/guides/mcp-setup-guide.md`
- `docs/guides/mcp-troubleshooting.md`
- `backend/mcp/README.md`

**Files modified**:
- `backend/requirements.txt` (add mcp>=1.8,<2)

**Phase 4 total**: ~1500 lines (tools + tests + docs)

---

## Dependencies & Sequencing

### Phase 3 and 4 Can Proceed in Parallel

- **Phase 3** depends only on Phase 1 (query services)
- **Phase 4** depends only on Phase 1 (query services)
- Phases 3 and 4 have no dependencies on each other
- Both can start immediately after Phase 1 is stable

### Recommended Sequencing (Optimal)

1. **Phase 1**: Complete and quality gate
2. **Phase 2**: Complete (recommended validation gate)
3. **Phase 3 + Phase 4 in parallel**: Both can proceed after Phase 1

### Minimal Sequencing (If Timeline Tight)

1. **Phase 1**: Complete and quality gate
2. **Phase 3 + Phase 4 in parallel**: Skip Phase 2 (not required for Phase 3/4, only for REST API users)

---

## Effort Breakdown

### Phase 3: CLI

| Task | Effort | Duration |
|------|--------|----------|
| P3-T1: CLI structure | 1 pt | 0.5–1 d |
| P3-T2: Output formatters | 1 pt | 1 d |
| P3-T3: Core commands | 3 pts | 2–3 d |
| P3-T4: CliRunner tests | 1 pt | 1 d |
| P3-T5: Entry point + npm setup | 1 pt | 0.5–1 d |
| P3-T6: Performance + integration | 1 pt | 1 d |
| **Phase 3 Total** | **6–7 pts** | **5–7 d** |

### Phase 4: MCP

| Task | Effort | Duration |
|------|--------|----------|
| P4-T1: Package + structure | 1 pt | 0.5–1 d |
| P4-T2: FastMCP server + tools | 3 pts | 2–3 d |
| P4-T3: Tool tests | 1 pt | 1 d |
| P4-T4: .mcp.json config | 1 pt | 0.5 d |
| P4-T5: Manual testing + docs | 1 pt | 1 d |
| **Phase 4 Total** | **5–6 pts** | **5–7 d** |

### Combined (if parallel)

**Total Effort**: 11–13 story points  
**Total Duration**: 5–7 days (in parallel) vs 10–14 days (sequential)

---

## Success Metrics

- [ ] All CLI commands pass CliRunner tests
- [ ] CLI startup <500 ms
- [ ] All MCP tools pass mcp.test_client() tests
- [ ] No business logic duplication with Phase 1
- [ ] CLI and web server coexist without locks
- [ ] Claude Code discovers and calls MCP tools successfully
- [ ] All JSON output valid (jq parsing succeeds)
- [ ] All markdown output valid (markdown parsers accept)

---

## Next Steps

After Phase 3–4 complete:

- **Phase 5** (deferred): Streamable HTTP MCP transport, extended tool catalog, MCP resources, portfolio analysis
- **Phase 6** (deferred): Web UI convergence (routers call agent_queries services)
- **Ongoing**: User feedback, tool refinement, additional commands/tools based on agent usage patterns

---

## Document Version

- Version: 1.0
- Created: 2026-04-02
- Status: Draft (ready for Phase 3–4 kickoff)
