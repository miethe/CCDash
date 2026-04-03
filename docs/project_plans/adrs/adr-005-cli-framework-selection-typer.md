---
title: "ADR-005: CLI Framework Selection - Typer"
type: "adr"
status: "accepted"
created: "2026-04-02"
parent_prd: "docs/project_plans/PRDs/features/cli-enablement.md"
depends_on_spike: "docs/project_plans/spikes/cli-framework-and-packaging-spike.md"
tags: ["adr", "cli", "typer", "python", "framework", "tooling"]
---

# ADR-005: CLI Framework Selection - Typer

## Status

Accepted

## Context

CCDash needs a Python CLI supporting ~40 subcommands with nested namespaces, async execution (backend is fully async), multiple output formats (text/json/markdown), and good test ergonomics. The CLI is separate from the web backend (no server dependency) but shares the same core application services and database.

## Decision

**Use Typer as the CLI framework for the `ccdash` command-line tool.**

The CLI is structured as `backend.cli` package:
- `backend/cli/__init__.py`: Entry point, version, global flags
- `backend/cli/commands/`: Organized by domain (sessions/, features/, projects/, etc.)
- `backend/cli/formatters.py`: Output formatting (text, JSON, markdown)
- `backend/cli/bootstrap.py`: In-process service initialization (builds CorePorts, opens DB connection)

## Decision Drivers

1. **Type-hint-first design**: Matches CCDash's existing Pydantic + FastAPI patterns; automatic schema generation from type hints
2. **Native async support**: Typer 0.10+ supports async commands without `asyncio.run()` bridging
3. **Click inheritance**: Inherits battle-tested CliRunner for testing; familiar testing patterns
4. **Rich help generation**: Auto-generated command docs, nested help, examples — no manual help strings
5. **In-process service access**: CLI bootstraps CorePorts directly; SQLite WAL mode handles concurrent CLI + web server access

## Alternatives Considered

1. **argparse (stdlib)**: No dependencies. Pro: standard library. Con: verbose for 40+ commands, manual type hints, manual async, poor help generation.

2. **Click**: Mature, widely used. Pro: excellent plugin system, battle-tested. Con: decorator-heavy, manual type hints (pre-3.7), manual async handling.

3. **Typer** (chosen): Built on Click, type-hint-first. Pro: automatic schema from type hints, native async, auto-generated help, CliRunner inheritance. Con: additional dependency (though minimal).

## Service Access and Bootstrapping

CLI does not require the web server running:
- `backend/cli/bootstrap.py` builds `CorePorts` in-process (same factory as web app)
- Opens SQLite connection directly (or PostgreSQL via env var)
- SQLite WAL mode allows concurrent access from CLI and web server

Example:
```python
async def cmd_sessions_list(output: str = "text"):
    ports = build_core_ports()  # In-process, shares same DB
    sessions = await ports.query_sessions.list(...)
    formatter = get_formatter(output)
    print(formatter.format_sessions(sessions))
```

## Packaging and Distribution

**Development:**
```bash
python -m backend.cli --help
python -m backend.cli sessions list
```

**Installed (pip):**
```bash
pip install -e .  # or pyproject.toml with entry_points
ccdash --help
ccdash sessions list
```

Entry point in `backend/pyproject.toml`:
```toml
[project.scripts]
ccdash = "backend.cli:app"
```

## Testing

Leverages Typer's CliRunner (inherited from Click):

```python
from typer.testing import CliRunner
from backend.cli import app

runner = CliRunner()

def test_sessions_list():
    result = runner.invoke(app, ["sessions", "list"])
    assert result.exit_code == 0
    assert "Session" in result.stdout
```

## Consequences

**Positive:**
- Type hints drive both schema generation and CLI parsing; single source of truth
- Async commands are first-class; no event loop bridging code
- CliRunner provides isolated test environment; no side effects across tests
- Auto-generated help reduces documentation burden
- Shared CorePorts bootstrap code with web backend prevents divergence

**Negative:**
- Adds dependency on Typer (though it's small and widely used)
- In-process service access means CLI shares same DB connection pool as web server; requires careful WAL mode tuning
- 40+ commands require disciplined organization (subcommand directories) to avoid monolithic file

**Risks:**
- CLI and web server contending on SQLite. Mitigate: WAL mode + connection pooling + monitoring for lock timeouts.
- Command bloat if every app feature maps to a CLI command. Mitigate: focus on agent-oriented commands (diagnostic, query, discovery) not full CRUD.

## Related

- `docs/project_plans/spikes/cli-framework-and-packaging-spike.md`
- `docs/project_plans/adrs/adr-003-transport-neutral-agent-query-layer.md`
- `docs/project_plans/adrs/adr-004-mcp-server-dual-transport-strategy.md`
