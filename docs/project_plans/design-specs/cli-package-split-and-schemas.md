---
schema_version: "1.0"
doc_type: design-spec
title: "CCDash CLI Package Split and Shared Schemas"
status: draft
created: "2026-04-12"
feature_slug: "ccdash-standalone-global-cli"
prd_ref: "docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md"
---

# CCDash CLI Package Split and Shared Schemas

## Problem Statement

The current `ccdash` console script is registered in the root `pyproject.toml` and resolves to
`backend.cli.main:app`. Every invocation bootstraps the full backend runtime: it opens a DB
connection, instantiates a `RuntimeContainer`, builds `CorePorts`, and runs async query services
against the local SQLite file. This works for in-repo development but makes global installation
impossible — the user would need to ship and configure the entire server stack just to run CLI
queries against a remote CCDash instance.

The solution is a three-package layout: the existing server package stays untouched, a new
lightweight standalone CLI package talks to the server over HTTP, and a shared contracts package
owns the DTOs that both sides must agree on.

---

## Package Layout

```
packages/
  ccdash_contracts/     # Shared Pydantic DTOs and envelope types
  ccdash_cli/           # Standalone HTTP-backed Typer CLI

backend/                # Existing server package (unchanged)
pyproject.toml          # Root — dev-only, editable installs, no published artifact
```

### Why a separate `packages/` directory

The existing `pyproject.toml` uses `setuptools.packages.find` with `include = ["backend*"]`.
Placing new packages under `packages/` keeps them outside that glob and prevents accidental
co-packaging. Each sub-package has its own `pyproject.toml` and is a first-class publish unit.

---

## P1-T1: Package Definitions

### `packages/ccdash_contracts/`

Owns all Pydantic models that cross the server/CLI boundary. Versioned independently.

```toml
# packages/ccdash_contracts/pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ccdash-contracts"
version = "0.1.0"
description = "Shared Pydantic DTOs for CCDash server and CLI."
requires-python = ">=3.10"
dependencies = ["pydantic>=2.0"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["ccdash_contracts*"]
```

Source layout: `packages/ccdash_contracts/src/ccdash_contracts/`.

### `packages/ccdash_cli/`

A Typer application that accepts a server URL and an optional API key, fetches data from the
CCDash REST API, and renders it using the same output formatters as the dev CLI.

```toml
# packages/ccdash_cli/pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ccdash-cli"
version = "0.1.0"
description = "Standalone CCDash CLI for remote project intelligence access."
requires-python = ">=3.10"
dependencies = [
    "ccdash-contracts>=0.1.0",
    "typer>=0.12",
    "httpx>=0.27",
    "pydantic>=2.0",
]

[project.scripts]
ccdash = "ccdash_cli.main:app"

[tool.setuptools.packages.find]
where = ["src"]
include = ["ccdash_cli*"]
```

Source layout: `packages/ccdash_cli/src/ccdash_cli/`.

### Root `pyproject.toml` (dev orchestration only)

The root package is not published. It wires editable installs together so in-repo development
keeps working without any changes to existing workflows.

```toml
# pyproject.toml (root, dev-only)
[project]
name = "ccdash"
version = "0.1.0"
description = "CCDash dev meta-package (not published)."
requires-python = ">=3.10"
dependencies = [
    "ccdash-contracts",   # editable
    "fastapi",
    "uvicorn",
    # ... existing server deps
]

[project.scripts]
ccdash = "backend.cli.main:app"   # dev CLI remains the active entry point

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
```

The backend editable install continues to resolve `ccdash` to `backend.cli.main:app`. When
`ccdash-cli` is installed globally it shadows this with its own entry point — the two never
coexist in the same environment.

---

## Package Boundary Rule

> The standalone CLI (`ccdash_cli`) MUST NOT import any `backend.*` module, directly or
> transitively. This boundary is enforced by the absence of `backend` or `ccdash` (root) as a
> dependency in `packages/ccdash_cli/pyproject.toml`. CI should add an import guard test that
> asserts `import backend` raises `ModuleNotFoundError` inside the `ccdash_cli` package's test
> environment.

The dev CLI at `backend/cli/` remains the reference implementation for command UX and formatter
logic. When the standalone CLI diverges, the dev CLI is the authority because it has direct access
to ground truth (DB + filesystem).

---

## Dev CLI Continuity

No changes are required for the existing developer workflow:

| Workflow | Entry point | Imports |
|---|---|---|
| `npm run dev` / in-repo | `backend.cli.main:app` | `backend.*` directly |
| Global install (`pip install ccdash-cli`) | `ccdash_cli.main:app` | `ccdash_contracts` + `httpx` only |
| MCP server | `backend.mcp.server` | `backend.*` directly |

The two CLIs share command names and output formatters by design; the dev CLI's formatters can
be extracted to `ccdash_contracts` or a separate `ccdash_formatters` package in a later phase
if sharing becomes necessary. For now, the standalone CLI duplicates or re-implements rendering.

---

## P1-T4: Shared Schema Ownership

### Models that move to `ccdash_contracts`

These are the DTOs in `backend/application/services/agent_queries/models.py` that are returned
by the REST API and must be deserializable by the CLI without the backend runtime.

| Model | Rationale |
|---|---|
| `QueryStatus` | Literal type used in every envelope |
| `AgentQueryEnvelope` | Base for all response DTOs; CLI checks `.status` |
| `SessionSummary` | Embedded in `ProjectStatusDTO` |
| `SessionRef` | Embedded in `FeatureForensicsDTO` and `WorkflowDiagnosticsDTO` |
| `CostSummary` | Embedded in `ProjectStatusDTO` |
| `WorkflowSummary` | Embedded in `ProjectStatusDTO` |
| `WorkflowDiagnostic` | Embedded in `WorkflowDiagnosticsDTO` |
| `DocumentRef` | Embedded in `FeatureForensicsDTO` |
| `TaskRef` | Embedded in `FeatureForensicsDTO` |
| `TimelineData` | Embedded in `AARReportDTO` |
| `KeyMetrics` | Embedded in `AARReportDTO` |
| `TurningPoint` | Embedded in `AARReportDTO` |
| `WorkflowObservation` | Embedded in `AARReportDTO` |
| `Bottleneck` | Embedded in `AARReportDTO` |
| `ProjectStatusDTO` | Top-level response for `GET /api/agent/project-status` |
| `FeatureForensicsDTO` | Top-level response for `GET /api/agent/feature-forensics/{id}` |
| `WorkflowDiagnosticsDTO` | Top-level response for `GET /api/agent/workflow-diagnostics` |
| `AARReportDTO` | Top-level response for `POST /api/agent/reports/aar` |

In practice this is the entire current contents of `models.py`. The file was already written as
"Shared DTO contracts" (its module docstring says so), making migration a rename rather than a
split.

### Models that stay server-side only

| Model / Construct | Location | Rationale |
|---|---|---|
| `AARReportRequest` | `backend/routers/agent.py` | HTTP request body; CLI builds this locally before POST |
| `RequestContext` | `backend/application/context.py` | Internal request scope, never serialized over wire |
| `CorePorts` | `backend/application/ports.py` | Runtime dependency injection, no CLI relevance |
| `RuntimeContainer` | `backend/runtime/container.py` | Server lifecycle object |
| All `backend/db/repositories/` models | `backend/db/` | DB-layer row objects, not public contract |

### Ownership Rule

`ccdash-contracts` is the source of truth for all wire-format DTOs. The server imports from
`ccdash_contracts`; the standalone CLI imports from `ccdash_contracts`. Neither owns the models
independently. A field change to a shared DTO requires a `ccdash-contracts` version bump before
either consumer merges the change.

The dev CLI at `backend/cli/` is permitted to import `backend.application.services.agent_queries`
directly during the transition period, because those models are still re-exported from there. Once
the server switches its own import to `ccdash_contracts`, the re-export in
`backend/application/services/agent_queries/models.py` becomes a thin alias:

```python
# backend/application/services/agent_queries/models.py (post-migration)
from ccdash_contracts import *  # noqa: F401,F403 — re-export for backwards compat
```

This keeps the dev CLI import paths valid without a separate PR to update every command file.

---

## Versioning

`ccdash-contracts` uses semver independent of the server release:

- **Patch** (`0.1.x`): adding optional fields with defaults, documentation fixes.
- **Minor** (`0.x.0`): adding new top-level DTOs, adding required fields with server-side
  defaults (non-breaking for existing CLI deserialization because Pydantic ignores extra fields).
- **Major** (`x.0.0`): removing or renaming fields, changing field types.

The server pins `ccdash-contracts>=0.1.0,<1.0.0` (compatible release). The standalone CLI pins
the same range. A major version bump requires coordinated server and CLI releases.

`ccdash-cli` versions independently from both `ccdash-contracts` and the server. CLI patch
releases can update rendering or add `--flag` options without touching contracts.

---

## Open Questions

| # | Question | Status |
|---|---|---|
| 1 | Publish to PyPI vs. a private index (GitHub Packages / internal registry)? | Deferred to phase 2; implement as private-index-ready but do not publish in phase 1. |
| 2 | Should `ccdash_cli` formatters be extracted to a shared `ccdash_formatters` package to avoid duplication with `backend/cli/output.py`? | Deferred; duplicate for now, extract if divergence becomes a maintenance problem. |
| 3 | API key / auth header scheme for the standalone CLI (`--api-key`, env var `CCDASH_API_KEY`)? | Deferred to P2 (HTTP client implementation); env var approach is assumed. |
| 4 | Monorepo tooling: use `uv workspaces` or plain editable installs? | Deferred; plain editable installs (`pip install -e packages/ccdash_contracts`) are sufficient for phase 1. |
