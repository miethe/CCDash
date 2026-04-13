# Migrating from the Repo-Local CLI to the Standalone CLI

CCDash now offers a standalone CLI that works from any directory without a repository checkout. This guide explains the transition from the repo-local CLI to the new standalone tool.

## Overview

The **repo-local CLI** (`backend/.venv/bin/ccdash`) is tightly coupled to the CCDash development environment. It runs directly in-process, bootstrapping the database and importing backend code. This approach requires the backend virtual environment and only works inside the repo.

The **standalone CLI** (`ccdash`) is installed globally via `pipx` and communicates with a running CCDash server over HTTP. This design lets you query projects from any terminal without a repository checkout or virtual environment activation.

Both CLIs share the same underlying intelligence layer (`backend/application/services/agent_queries/`), so commands produce equivalent results.

## Quick Start

Install the standalone CLI:

```bash
pipx install ccdash-cli
```

Verify the installation:

```bash
ccdash --version
ccdash target show
ccdash doctor
```

The `doctor` command checks connectivity to the CCDash server and reports its status.

## What Changed

| Aspect | Repo-Local | Standalone |
|--------|-----------|-----------|
| Installation | Part of `npm run setup` | `pipx install ccdash-cli` |
| Location | `backend/.venv/bin/ccdash` | `ccdash` (in PATH) |
| Works from | Inside CCDash repo only | Any directory |
| Backend access | In-process, direct import | HTTP to localhost:8000 |
| Virtual environment | Requires `.venv` activation | Not required |
| Prerequisites | Backend .venv, database running | CCDash server listening |
| Configuration | Reads local environment | Targets (named servers) + auth |

## Command Mapping

| Old (Repo-Local) | New (Standalone) | Notes |
|---|---|---|
| `backend/.venv/bin/ccdash status project` | `ccdash status project` | Project summary unchanged. |
| `backend/.venv/bin/ccdash feature report FEAT-123` | `ccdash report feature FEAT-123` | Also: `ccdash feature show FEAT-123` for detailed output. |
| `backend/.venv/bin/ccdash workflow failures` | `ccdash workflow failures` | Workflow failure patterns unchanged. |
| `backend/.venv/bin/ccdash report aar --feature FEAT-123` | `ccdash report aar --feature FEAT-123` | After-action reports unchanged. |

## New Capabilities

The standalone CLI extends the old one with:

- **Feature exploration**: `ccdash feature list`, `ccdash feature show <id>`, `ccdash feature sessions <id>`, `ccdash feature documents <id>`
- **Session exploration**: `ccdash session list`, `ccdash session show <id>`, `ccdash session search <query>`, `ccdash session drilldown <id>`, `ccdash session family <id>`
- **Report generation**: `ccdash report feature <id>` (new format vs legacy `feature report`)
- **Target management**: `ccdash target add <name>`, `ccdash target remove <name>`, `ccdash target list`, `ccdash target show`, `ccdash target use <name>`
- **Authentication**: `ccdash target login <name>`, `ccdash target logout <name>`, `ccdash target check`
- **Server diagnostics**: `ccdash doctor` (connectivity check), `ccdash --version` (root version flag)

## When to Use Which

**Use the standalone CLI for:**
- Day-to-day operator work querying CCDash
- Scripts and automation that run outside the repo
- Remote server queries (via target configuration)
- Teams without access to the CCDash source repo

**Use the repo-local CLI only for:**
- CCDash development and debugging
- Validating changes to the backend intelligence layer
- Testing before pushing changes

## Prerequisites

### For Standalone CLI

- A running CCDash server on localhost:8000 (or configured via target)
- For local development: `npm run dev` starts the server
- Internet access (only if connecting to a remote server)

### For Repo-Local CLI

- CCDash repo checked out locally
- Python 3.10+
- `npm run setup` completed
- Backend virtual environment activated (Unix: `source backend/.venv/bin/activate`; Windows: `backend\.venv\Scripts\activate`)

## Output Modes

Both CLIs support the same output formatting:

- Human-readable (default)
- `--json` or `--output json` for JSON
- `--md` or `--output markdown` for Markdown

Example:

```bash
ccdash status project --json
ccdash feature show FEAT-123 --md
ccdash workflow failures --output markdown
```

## Global Flags

The standalone CLI supports:

- `--target <name>` - Override the default target (named server)
- `--project <id>` - Override the active project
- `--output <format>` - Set output mode (json, markdown, human)

Example:

```bash
ccdash --target staging status project
ccdash --project my-project feature show FEAT-123
ccdash --output json workflow failures
```

## Target Configuration

Named targets let you switch between servers without re-typing the URL:

```bash
# Add a local server
ccdash target add local http://localhost:8000

# Add a remote server
ccdash target add staging https://staging-ccdash.company.com

# Use a target
ccdash --target staging status project

# List configured targets
ccdash target list

# Inspect the resolved target and auth source
ccdash target show

# Remove a target
ccdash target remove staging
```

Authentication is resolved per target:

```bash
ccdash target show
ccdash target login staging
ccdash target check staging
ccdash target logout staging
```

## Troubleshooting

**CLI not found:**
Ensure `pipx` installed the CLI to a PATH directory. Verify with `which ccdash`.

**Server connection refused:**
Confirm the CCDash server is running. For local dev, start it with `npm run dev`. Inspect the resolved target with `ccdash target show`, then run `ccdash doctor`.

**Project not resolved:**
Pass `--project <id>` to override the active project, or confirm the configured project exists.

**Authentication error:**
Log in with `ccdash target login <target>`, inspect the resolved auth state with `ccdash target show`, and verify live credentials with `ccdash target check`.

**Output mode conflict:**
Do not combine `--json` and `--md` in the same invocation. Choose one.

## Migration Path

1. Install the standalone CLI: `pipx install ccdash-cli`
2. Verify it works: `ccdash --version`
3. Test a query: `ccdash status project`
4. Configure targets for any remote servers
5. Remove the repo-local CLI from your workflow (keep it in the repo for development)

## Further Reading

- [CLI User Guide](cli-user-guide.md) - In-depth repo-local CLI documentation
- `ccdash --help` - Built-in command reference
- `ccdash <command> --help` - Per-command documentation
