---
schema_version: "1.0"
doc_type: spike
title: "CLI Framework and Packaging - SPIKE"
description: "Technical research into CLI framework selection, async execution strategy, service access patterns, packaging, output formatting, and testing for CCDash's local CLI."
status: completed
created: 2026-04-02
updated: 2026-04-02
completed_date: 2026-04-02
feature_slug: ccdash-cli
research_questions:
  - Framework comparison (typer vs click vs argparse)
  - Async CLI execution bridging
  - Service access pattern (direct vs HTTP vs hybrid)
  - Packaging and distribution
  - Output formatting architecture
  - Testing strategy
complexity: medium
estimated_research_time: "4h"
related_documents:
  - docs/project_plans/ccdash-cli-mcp-enablement-plan.md
---

# CLI Framework and Packaging - SPIKE

## Executive Summary

This SPIKE investigates how to implement CCDash's local CLI -- a query-first command-line interface for project intelligence, usable by both humans and AI agents. The CLI must share business logic with the async FastAPI backend without requiring the web server to be running.

**Recommendation**: Use **Typer** as the CLI framework with **direct in-process** service access via a lightweight `CLIRuntimeContainer` that bootstraps `CorePorts` without FastAPI. Package as a Python entry point (`ccdash` command) installable from the existing repo. Use a `Formatter` protocol to cleanly separate query logic from `--json`, `--md`, and human-readable output rendering. Bridge async services with `asyncio.run()` at the command boundary.

Key rationale: Typer is built on Click (the ecosystem standard), provides type-hint-driven argument parsing that matches the backend's Pydantic/typing conventions, generates excellent help text with zero boilerplate, and now supports async commands natively. Direct in-process access eliminates the requirement to have the web server running, which is essential for a local-first tool.

---

## Research Question 1: Framework Comparison

### Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Help text quality | High | Auto-generated `--help` for humans and agents |
| Subcommand nesting | High | `ccdash project list`, `ccdash feature report <id>` |
| Type validation | High | Validate IDs, enums, paths from arguments |
| Output formatting hooks | Medium | Easy to wire `--json`/`--md` global options |
| Async support | High | Backend services are all async |
| Testing ergonomics | High | Invoke commands in tests without subprocess |
| Dependency weight | Low | All options are lightweight |
| Maintenance trajectory | Medium | Active maintenance, ecosystem health |

### Comparison Matrix

| Feature | argparse | Click | Typer |
|---------|----------|-------|-------|
| **Source** | stdlib | Pallets (pip) | FastAPI ecosystem (pip) |
| **Paradigm** | Imperative parser construction | Decorator-based | Type-hint inference |
| **Subcommand nesting** | Manual with `add_subparsers` | `@group.command()` decorator chains | `app.add_typer()` for nested groups |
| **Help text** | Manually written per argument | Auto from docstrings + decorators | Auto from type hints + docstrings; Rich-formatted by default |
| **Type validation** | Manual `type=` callables | `click.types` (Choice, Path, etc.) | Python type hints (str, int, Enum, Path) validated automatically |
| **Async commands** | No (manual `asyncio.run`) | No (manual `asyncio.run`) | Yes, native since 0.10+ via AnyIO detection |
| **Testing** | Subprocess or manual namespace | `click.testing.CliRunner` (excellent) | `typer.testing.CliRunner` (inherits Click's) |
| **Shell completion** | Limited | Built-in (bash, zsh, fish) | Built-in (inherited from Click) |
| **Rich output** | Manual | Manual or via plugins | Built-in Rich integration |
| **Dependencies** | None (stdlib) | ~4 transitive deps | Click + typing-extensions (~5 transitive deps) |
| **Boilerplate** | High (verbose parser setup) | Medium (decorators) | Low (function signatures are the API) |
| **Community adoption** | Universal (stdlib) | 38.7% of Python CLI projects | Growing rapidly, same maintainer as FastAPI |
| **Error messages** | Generic | Good, context-aware | Excellent, colored with suggestions |

### argparse Assessment

**Strengths**: Zero dependencies, maximum control, no version-pinning risk.

**Weaknesses for CCDash**: Subcommand nesting is verbose and error-prone. No built-in testing runner -- must parse `Namespace` objects manually or shell out. Help text requires manual formatting for every argument. Type validation requires custom callables. No async support. The amount of boilerplate to support the planned `~40` commands would be significant.

**Verdict**: Appropriate for simple tools with 2-3 commands. Inappropriate for CCDash's breadth of nested subcommands.

### Click Assessment

**Strengths**: Battle-tested, excellent `CliRunner` for testing, clean decorator API, rich plugin ecosystem (click-extra, rich-click, etc.).

**Weaknesses for CCDash**: Requires explicit decorator annotations for every parameter (does not infer from type hints). Async must be bridged manually. More boilerplate than Typer for the same result. The CCDash backend already uses Pydantic and type hints extensively; Click's decorator style is a different paradigm.

**Verdict**: Strong choice. Would work well. But Typer provides the same foundation with less code.

### Typer Assessment

**Strengths**: Function signatures become the CLI API. Type hints drive validation, help text, and completion. Native async support. `typer.testing.CliRunner` inherits Click's testing excellence. Rich integration for colored output. Same maintainer ecosystem as FastAPI (familiar to CCDash contributors). Subcommand nesting via `app.add_typer()` is clean.

**Weaknesses for CCDash**: Adds a dependency (though lightweight). Some advanced Click patterns require dropping to Click's API. Async support is relatively new (0.10+, early 2025) and relies on AnyIO detection.

**Verdict**: Best fit for CCDash. Matches the backend's type-hint-first style, minimizes boilerplate, and provides native async.

### Recommendation: Typer

Typer provides the best alignment with CCDash's existing patterns (type hints, Pydantic, FastAPI ecosystem), the lowest boilerplate for the planned command surface, and native async support. Since it is built on Click, any advanced customization can drop to Click's API without a rewrite.

---

## Research Question 2: Async CLI Execution

### Problem

All CCDash application services (`SessionFacetService`, `AnalyticsOverviewService`, `DocumentQueryService`, etc.) are `async`. The CLI must call these services from synchronous command entry points.

### How Each Framework Handles Async

| Framework | Async Handling |
|-----------|---------------|
| argparse | None. Developer must call `asyncio.run()` manually. |
| Click | None. Developer must call `asyncio.run()` manually or use `@click.pass_context` with a custom async runner. |
| Typer | Native since 0.10+. Detects `async def` command functions and runs them via AnyIO/asyncio automatically. Falls back to `asyncio.run()` if AnyIO is not installed. |

### Recommended Pattern for CCDash

With Typer, async commands work directly:

```python
# backend/cli/commands/status.py
import typer
from backend.cli.runtime import get_ports, get_context

app = typer.Typer()

@app.command()
async def project(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    md_output: bool = typer.Option(False, "--md", help="Output as Markdown"),
):
    """Show current project status summary."""
    ports = get_ports()
    context = get_context()
    service = ProjectStatusQueryService()
    result = await service.get_status(context, ports)
    format_output(result, json=json_output, md=md_output)
```

If Typer's native async detection is insufficient (e.g., edge cases around event loop lifecycle with SQLite connections), the fallback is a thin `run_async` wrapper:

```python
import asyncio
import functools

def run_async(func):
    """Bridge async service calls from sync CLI entry points."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper
```

### Event Loop Considerations

- **aiosqlite**: Creates its own thread-based connection. Works correctly under `asyncio.run()` from a fresh event loop. No conflict.
- **asyncpg**: Connection pool must be created within the event loop. The CLI bootstrap must create the pool inside the same `asyncio.run()` scope as the command execution. This is handled naturally if the `CLIRuntimeContainer.startup()` is called inside the async command function.
- **Connection lifecycle**: The CLI should open and close the database connection per invocation (no persistent daemon). This is fast for SQLite (~5ms) and acceptable for PostgreSQL (~50ms).

### Recommendation

Use Typer's native `async def` commands. Keep the CLI runtime bootstrap (`get_ports()`) lazy-initialized on first use within the async context to ensure the event loop is available for asyncpg pool creation.

---

## Research Question 3: Service Access Pattern

### Option A: Direct In-Process

The CLI bootstraps its own `CorePorts` and database connection. No web server needed.

```
CLI Command --> CLIRuntimeContainer --> CorePorts --> Repositories --> DB
```

**Implementation sketch**:

```python
# backend/cli/runtime.py
from backend.application.ports import CorePorts
from backend.db import connection
from backend.runtime_ports import build_core_ports
from backend.runtime.profiles import get_runtime_profile

_ports: CorePorts | None = None

async def bootstrap_cli() -> CorePorts:
    """Bootstrap CLI runtime -- lightweight, no HTTP server."""
    global _ports
    if _ports is not None:
        return _ports
    db = await connection.get_connection()
    profile = get_runtime_profile("local")  # or a new "cli" profile
    _ports = build_core_ports(db, runtime_profile=profile)
    return _ports

async def teardown_cli() -> None:
    global _ports
    _ports = None
    await connection.close_connection()
```

**Pros**:
- Works offline / without running web server
- Zero network overhead
- Full access to all repositories and services
- Consistent with local-first philosophy
- Simpler deployment (single process)

**Cons**:
- Must manage DB connection lifecycle in CLI process
- Cannot access web-server-only state (live event broker, sync engine tasks)
- Potential SQLite lock contention if web server is also running (mitigated by WAL mode + busy timeout)

### Option B: HTTP Client

The CLI calls the running FastAPI server over `localhost:8000`.

```
CLI Command --> HTTP Client --> FastAPI Router --> Services --> DB
```

**Pros**:
- Always consistent with web server state
- No database lifecycle management in CLI
- Can leverage existing REST endpoints

**Cons**:
- Requires web server to be running (breaks local-first contract)
- Network overhead for local queries
- Must duplicate response parsing
- Cannot access agent-query services that don't yet have REST endpoints
- Adds `httpx` or `aiohttp` dependency for CLI

### Option C: Hybrid (Direct reads, HTTP mutations)

Read operations go direct. Write operations (sync triggers, project switching) go through HTTP.

**Pros**:
- Fast reads without server dependency
- Mutations go through server's lifecycle management

**Cons**:
- Two code paths to maintain
- Confusing failure modes (reads work, writes fail if server is down)
- Mutations are rare in a query-first CLI

### Recommendation: Option A (Direct In-Process)

Direct in-process access is the clear winner for a local-first, query-first CLI tool. It aligns with CCDash's local-first philosophy, eliminates the server dependency, and leverages the existing `build_core_ports()` composition function that was designed for exactly this purpose.

The SQLite WAL mode with the configured 30-second busy timeout (`CCDASH_SQLITE_BUSY_TIMEOUT_MS`) handles concurrent access from both web server and CLI gracefully. For the rare mutation commands (`cache sync`, `project use`), direct DB access is still safe because the write-through pattern writes to filesystem first, then DB.

### Runtime Profile Consideration

A new `"cli"` runtime profile could be added alongside `local`, `api`, `worker`, and `test`:

```python
"cli": RuntimeProfile(
    name="cli",
    capabilities=RuntimeCapabilities(
        watch=False,
        sync=False,   # CLI doesn't run background sync
        jobs=False,    # CLI doesn't run background jobs
        auth=False,    # Local CLI, no auth needed
        integrations=False,
    ),
    recommended_storage_profile="local",
    description="Lightweight CLI profile for query-first local access.",
)
```

Alternatively, reuse `"local"` profile with sync/jobs disabled. The profile choice is a follow-on implementation decision, not a spike-blocking question.

---

## Research Question 4: Packaging and Distribution

### Option 1: Python Package Entry Point

Add a `[project.scripts]` entry to `pyproject.toml` (or equivalent):

```toml
[project.scripts]
ccdash = "backend.cli.main:app"
```

Install with `pip install -e .` from the repo root, which creates the `ccdash` command in the active venv.

**Pros**: Standard Python packaging. Works with the existing venv at `backend/.venv/`. Automatic PATH integration. Supports `ccdash --help` immediately.

**Cons**: Requires pip install step. Only available in the venv.

### Option 2: `python -m backend.cli` Module Execution

Add `backend/cli/__main__.py`:

```python
from backend.cli.main import app
app()
```

Invoke as: `python -m backend.cli status project`

**Pros**: No install step. Works immediately. Good for development.

**Cons**: Verbose invocation. Not ergonomic for daily use or agent shell integration.

### Option 3: Shell Wrapper Script

A thin bash script that activates the venv and runs the module:

```bash
#!/usr/bin/env bash
exec "$(dirname "$0")/backend/.venv/bin/python" -m backend.cli "$@"
```

**Pros**: One-step invocation without pip install. Can be placed in project root.

**Cons**: Platform-specific. Fragile if venv location changes. Not a standard distribution mechanism.

### Option 4: PyInstaller / Nuitka Standalone Binary

Compile to a single binary.

**Pros**: No Python/venv dependency at runtime. Clean distribution.

**Cons**: Large binary size (~50-100MB). Slow build. Complex CI setup. Overkill for a local dev tool used within a Python project.

### Recommendation: Option 1 + Option 2 (Dual)

Provide both:

1. **`python -m backend.cli`** for zero-setup development and CI (works immediately after `npm run setup`).
2. **`ccdash` entry point** via `pip install -e .` for ergonomic daily use and agent shell integration.

The `npm run setup` script can be extended to run `pip install -e .` automatically, making the `ccdash` command available after first-time setup with no extra steps.

A shell wrapper in `bin/ccdash` can serve as a convenience fallback for users who haven't run `pip install -e .`:

```bash
#!/usr/bin/env bash
# Convenience wrapper -- prefer `pip install -e .` for the real entry point
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$SCRIPT_DIR/backend/.venv/bin/python" -m backend.cli "$@"
```

---

## Research Question 5: Output Formatting Architecture

### Design Principle

Query logic and output rendering must be completely separated. A command handler should never contain `print()` or format strings. Instead:

1. Command handler calls application service, receives a typed DTO.
2. Command handler passes DTO to a formatter selected by output mode.
3. Formatter renders the DTO to stdout.

### Formatter Protocol

```python
# backend/cli/formatters/base.py
from typing import Protocol, Any

class OutputFormatter(Protocol):
    def render(self, data: Any, *, title: str = "") -> str:
        """Render data to a string for stdout."""
        ...

class TableFormatter:
    """Human-readable table output (default)."""
    def render(self, data: Any, *, title: str = "") -> str:
        # Use Rich tables or simple column alignment
        ...

class JsonFormatter:
    """Structured JSON output for automation and agents."""
    def render(self, data: Any, *, title: str = "") -> str:
        import json
        # Serialize Pydantic models or dicts to indented JSON
        if hasattr(data, "model_dump"):
            return json.dumps(data.model_dump(), indent=2, default=str)
        return json.dumps(data, indent=2, default=str)

class MarkdownFormatter:
    """Markdown output for reports and documentation."""
    def render(self, data: Any, *, title: str = "") -> str:
        # Render as markdown tables, headers, lists
        ...
```

### Global Output Mode Option

Use a Typer callback to set the output mode globally:

```python
# backend/cli/main.py
import typer
from enum import Enum

class OutputMode(str, Enum):
    human = "human"
    json = "json"
    md = "md"

app = typer.Typer(
    name="ccdash",
    help="CCDash project intelligence CLI.",
    no_args_is_help=True,
)

# Global state for output mode
_output_mode: OutputMode = OutputMode.human

@app.callback()
def main(
    output: OutputMode = typer.Option(
        OutputMode.human,
        "--output", "-o",
        help="Output format: human, json, md",
    ),
    json_flag: bool = typer.Option(False, "--json", help="Shorthand for --output json"),
    md_flag: bool = typer.Option(False, "--md", help="Shorthand for --output md"),
):
    """CCDash project intelligence CLI."""
    global _output_mode
    if json_flag:
        _output_mode = OutputMode.json
    elif md_flag:
        _output_mode = OutputMode.md
    else:
        _output_mode = output
```

### Specialized Renderers per Domain

For complex outputs (feature reports, AAR packs), define domain-specific renderers:

```python
# backend/cli/formatters/features.py

def render_feature_report_table(report: FeatureForensicsDTO) -> str:
    """Rich table with feature metadata, sessions, metrics."""
    ...

def render_feature_report_md(report: FeatureForensicsDTO) -> str:
    """Markdown narrative with sections, tables, evidence links."""
    ...
```

### Recommendation

- Use the `OutputFormatter` protocol for simple data (lists, summaries).
- Use domain-specific renderers for complex reports (feature forensics, AAR).
- Keep all formatters under `backend/cli/formatters/`.
- Use Rich for human-readable output (tables, panels, progress indicators). Rich is already a transitive dependency of Typer.
- JSON output should use Pydantic's `.model_dump()` for consistency with the REST API response shapes.

---

## Research Question 6: Testing Strategy

### Approach 1: Typer/Click CliRunner (Recommended Primary)

Typer inherits Click's `CliRunner`, which invokes commands in-process without subprocess overhead.

```python
# backend/tests/test_cli_status.py
import pytest
from typer.testing import CliRunner
from backend.cli.main import app

runner = CliRunner()

def test_project_status_json():
    result = runner.invoke(app, ["status", "project", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "projectId" in data

def test_project_status_human():
    result = runner.invoke(app, ["status", "project"])
    assert result.exit_code == 0
    assert "Project:" in result.output

def test_unknown_command():
    result = runner.invoke(app, ["nonexistent"])
    assert result.exit_code != 0
```

**Pros**: Fast, in-process, captures stdout/stderr, tests the full command pipeline.

**Cons**: Shares process state. Must mock or use a test database.

### Approach 2: Pytest Parametrize for Output Modes

```python
@pytest.mark.parametrize("flags,expected_key", [
    (["--json"], "projectId"),
    (["--md"], "# Project Status"),
    ([], "Project:"),
])
def test_status_output_modes(flags, expected_key):
    result = runner.invoke(app, ["status", "project"] + flags)
    assert result.exit_code == 0
    assert expected_key in result.output
```

### Approach 3: Unit Test Formatters Independently

```python
def test_json_formatter_serializes_pydantic():
    dto = ProjectStatusDTO(project_id="abc", feature_count=5)
    formatter = JsonFormatter()
    output = formatter.render(dto)
    parsed = json.loads(output)
    assert parsed["project_id"] == "abc"
```

### Approach 4: Integration Tests with Test Database

```python
@pytest.fixture
async def cli_ports(tmp_path):
    """Bootstrap CLI ports with an ephemeral test database."""
    db_path = tmp_path / "test.db"
    os.environ["CCDASH_DB_PATH"] = str(db_path)
    from backend.cli.runtime import bootstrap_cli, teardown_cli
    ports = await bootstrap_cli()
    yield ports
    await teardown_cli()
```

### Recommendation

Layer the testing strategy:

| Layer | Tool | What It Tests |
|-------|------|---------------|
| Formatters | pytest unit tests | Output rendering correctness |
| Commands | `CliRunner` + parametrize | Argument parsing, routing, exit codes, output modes |
| Integration | `CliRunner` + test DB fixture | End-to-end query through real services |
| Smoke | Subprocess (optional) | Entry point resolution, `--help` output |

The `CliRunner` approach should be the workhorse. It is fast, deterministic, and tests the actual Typer command tree. Subprocess tests are only needed for packaging validation (does `ccdash --help` work after `pip install`).

---

## Proposed Command Structure

Based on the CLI design in the existing enablement plan, organized as Typer sub-applications:

```
backend/
  cli/
    __init__.py
    __main__.py            # python -m backend.cli entry point
    main.py                # Root Typer app, global options, sub-app registration
    runtime.py             # CLIRuntimeContainer: bootstrap_cli(), teardown_cli()
    output.py              # OutputMode enum, formatter selection, global state
    commands/
      __init__.py
      project.py           # project list, project use, project show
      status.py            # status project, status feature
      feature.py           # feature list, feature show, feature report, feature sessions
      session.py           # session show, session timeline, session transcript
      workflow.py          # workflow leaderboard, workflow failures
      analytics.py         # analytics overview, analytics attribution
      report.py            # report aar, report project-summary
      cache.py             # cache status, cache sync
    formatters/
      __init__.py
      base.py              # OutputFormatter protocol, JsonFormatter, TableFormatter, MarkdownFormatter
      projects.py          # Project-specific renderers
      features.py          # Feature report renderers
      sessions.py          # Session detail renderers
      analytics.py         # Analytics table/chart renderers
```

### Main App Wiring

```python
# backend/cli/main.py
import typer
from backend.cli.commands import project, status, feature, session, workflow, analytics, report, cache

app = typer.Typer(
    name="ccdash",
    help="CCDash -- local project intelligence CLI.",
    no_args_is_help=True,
)

app.add_typer(project.app, name="project")
app.add_typer(status.app, name="status")
app.add_typer(feature.app, name="feature")
app.add_typer(session.app, name="session")
app.add_typer(workflow.app, name="workflow")
app.add_typer(analytics.app, name="analytics")
app.add_typer(report.app, name="report")
app.add_typer(cache.app, name="cache")
```

### Example Command Implementation

```python
# backend/cli/commands/feature.py
import typer
from backend.cli.runtime import require_ports, require_context
from backend.cli.output import get_formatter

app = typer.Typer(help="Feature intelligence commands.")

@app.command()
async def report(
    feature_id: str = typer.Argument(help="Feature ID to report on"),
):
    """Generate a forensics report for a feature."""
    ports = await require_ports()
    context = await require_context()
    service = FeatureForensicsQueryService()
    result = await service.get_forensics(context, ports, feature_id=feature_id)
    formatter = get_formatter()
    typer.echo(formatter.render(result, title=f"Feature Report: {feature_id}"))
```

---

## SkillMeat Layer Impact

| Layer | Impact | Details |
|-------|--------|---------|
| **DB** | None | CLI reads the existing SQLite/PostgreSQL cache. No schema changes. |
| **Repository** | None | CLI uses existing repositories via `CorePorts.storage`. |
| **Service** | Low | CLI calls existing application services + new agent-query services (from enablement plan Phase 1). |
| **API** | None | CLI does not go through HTTP routers. |
| **CLI (new)** | High | New `backend/cli/` package with commands, formatters, runtime bootstrap. |
| **Frontend** | None | No UI changes. |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SQLite lock contention when web server and CLI run concurrently | Medium | Low | WAL mode + 30s busy timeout already configured. CLI operations are fast reads. |
| Typer async support is immature / breaks | Medium | Low | Fallback to `asyncio.run()` wrapper is trivial (3 lines). |
| Agent-query services not yet built | High | High | CLI MVP can start with existing application services (`SessionFacetService`, `AnalyticsOverviewService`, `DocumentQueryService`). Agent-query layer is Phase 1 of enablement plan. |
| CLI startup time too slow for shell workflows | Medium | Medium | Lazy import pattern. Only import heavy modules when command is invoked. Profile startup and optimize. Target <500ms. |
| `RuntimeProfile` for CLI conflicts with existing profiles | Low | Low | CLI profile is read-only with no sync/jobs. Minimal surface area for conflict. |
| Output format inconsistency between CLI and REST API | Medium | Medium | Share Pydantic DTOs. JSON output should use `model_dump()` to match API shapes. |

---

## Effort Estimation

| Phase | Description | Estimate | Confidence |
|-------|-------------|----------|------------|
| 1. CLI scaffold | Typer app, runtime bootstrap, output framework, `__main__` | 2-3 days | High |
| 2. Core commands (MVP) | `project list/show/use`, `status project`, `feature list/show/report`, `cache status/sync` | 3-4 days | High |
| 3. Formatters | Table, JSON, Markdown renderers for MVP commands | 2-3 days | High |
| 4. Testing | CliRunner tests, formatter unit tests, integration tests | 2-3 days | High |
| 5. Packaging | Entry point, `npm run setup` integration, shell wrapper | 0.5-1 day | High |
| 6. Advanced commands | Workflow, analytics, report, session commands | 3-5 days | Medium |
| **Total MVP (Phases 1-5)** | | **10-14 days** | **High** |
| **Total with advanced** | | **13-19 days** | **Medium** |

Note: These estimates assume agent-query services (from the enablement plan) are built in parallel or already available. If the CLI must use existing lower-level services directly, add 2-3 days for DTO assembly logic in command handlers.

---

## ADR Recommendations

The following decisions are significant enough to warrant Architecture Decision Records:

1. **ADR: CLI Framework Selection -- Typer**
   - Decision: Use Typer over Click/argparse.
   - Context: Type-hint alignment, async support, ecosystem fit.
   - Consequence: Adds `typer` dependency. CLI code style follows function-signature paradigm.

2. **ADR: CLI Service Access -- Direct In-Process**
   - Decision: CLI bootstraps its own CorePorts, does not require running web server.
   - Context: Local-first tool design, query-first usage pattern.
   - Consequence: Must manage DB connection lifecycle. Cannot access web-only state (live events).

3. **ADR: CLI Output Architecture -- Formatter Protocol**
   - Decision: Separate query logic from rendering via OutputFormatter protocol.
   - Context: Three output modes (human, JSON, markdown) across all commands.
   - Consequence: Every command produces a DTO; rendering is a separate concern.

---

## Open Questions

1. **Should the CLI have its own `RuntimeProfile`?** Adding `"cli"` to the profile enum is clean but requires updating `RuntimeProfileName` literal type and any exhaustive matches. Alternatively, reuse `"local"` or `"test"` profile. Recommend: add a `"cli"` profile -- it's a 10-line change and makes the system self-documenting.

2. **Should `ccdash` be a top-level package or remain under `backend/`?** Keeping it under `backend/cli/` is simpler and shares imports naturally. A top-level `ccdash/` package would require restructuring. Recommend: keep under `backend/cli/` for now.

3. **Should the CLI support config file (`.ccdashrc`)?** Not for MVP. Environment variables (`CCDASH_*`) already handle configuration. A config file can be added later if needed.

4. **Should `--project` be a global option or per-command?** Global option on the root callback is more ergonomic: `ccdash --project myproject feature list`. Recommend: global option that overrides the active project for the duration of the command.

5. **Dependency on agent-query services**: The enablement plan defines an `agent_queries/` service layer. The CLI MVP can proceed without it by calling existing services, but the command surface will be richer once those services exist. Coordinate with the agent-query implementation timeline.

---

## Implementation Checklist

Ready for handoff to `implementation-planner`:

- [ ] Add `typer` to `backend/requirements.txt`
- [ ] Create `backend/cli/` package structure (main, runtime, output, commands, formatters)
- [ ] Implement `CLIRuntimeContainer` with lazy `bootstrap_cli()` / `teardown_cli()`
- [ ] Optionally add `"cli"` to `RuntimeProfileName` and `_RUNTIME_PROFILES`
- [ ] Implement root Typer app with global `--json`, `--md`, `--project` options
- [ ] Implement `OutputFormatter` protocol with `TableFormatter`, `JsonFormatter`, `MarkdownFormatter`
- [ ] Implement MVP commands: `project list/show/use`, `status project`, `feature list/show/report`, `cache status/sync`
- [ ] Add `__main__.py` for `python -m backend.cli` invocation
- [ ] Add `[project.scripts]` entry point for `ccdash` command
- [ ] Write `CliRunner`-based tests for all MVP commands
- [ ] Write formatter unit tests
- [ ] Update `npm run setup` to include `pip install -e .`
- [ ] Add `bin/ccdash` shell wrapper as convenience fallback
- [ ] Document CLI usage in project docs

---

## References

- [CCDash CLI and MCP Enablement Plan](../ccdash-cli-mcp-enablement-plan.md)
- [CorePorts composition](../../backend/application/ports/core.py)
- [RuntimeContainer](../../backend/runtime/container.py)
- [Runtime profiles](../../backend/runtime/profiles.py)
- [build_core_ports](../../backend/runtime_ports.py)
- [Typer documentation](https://typer.tiangolo.com/)
- [Typer async support discussion](https://github.com/fastapi/typer/issues/950)
- [Click testing documentation](https://click.palletsprojects.com/en/stable/testing/)
- [async-typer PyPI package](https://pypi.org/project/async-typer/)
- [Python CLI framework comparison (dasroot.net)](https://dasroot.net/posts/2025/12/building-cli-tools-python-click-typer-argparse/)
- [Click CLI and Typer guide (DevToolbox)](https://devtoolbox.dedyn.io/blog/python-click-typer-cli-guide)
