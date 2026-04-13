---
schema_version: "1.0"
doc_type: prd
title: "CCDash Standalone Global CLI"
description: "Ship CCDash as a true globally installed CLI that connects to local or remote CCDash instances over HTTP, defaults to local development workflows, and exposes broad read-only insights across projects, features, sessions, workflows, and reports."
status: draft
created: "2026-04-12"
updated: "2026-04-12"
feature_slug: "ccdash-standalone-global-cli"
feature_version: "v1"
prd_ref: null
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md"
owner: platform-engineering
contributors: ["Architecture Review Team"]
priority: high
risk_level: medium
category: "product-planning"
tags: ["cli", "distribution", "remote-access", "features", "sessions", "http-client", "federation"]
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
related_documents:
  - docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
  - docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md
  - docs/guides/cli-user-guide.md
  - README.md
---

# PRD: CCDash Standalone Global CLI v1

## 1. Feature brief & metadata

**Feature name:** CCDash Standalone Global CLI

**Filepath:** `docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md`

**Date:** 2026-04-12

**Author:** Architecture Review Team

**Related implementation plan:** `docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md`

**Related predecessor:** `docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md`

---

## 2. Executive summary

**Priority:** HIGH

CCDash now has a functioning CLI surface, but it is still a developer-local adapter installed from the repository into `backend/.venv` and executed in-process against the backend runtime. That is useful for local development, but it is not yet a true globally installed operator tool.

This feature evolves the CLI into a standalone, globally installable product that connects to a running CCDash instance over HTTP. The CLI will default to a local CCDash target for the common developer workflow, while laying the contract and configuration groundwork for remote targets and, later, federated multi-instance access.

The product goal is not only packaging. The standalone CLI should expose a materially broader read-only insight surface than the current four-command MVP, especially around:

1. **Features**: list, inspect, trace linked sessions, review documents, and generate reports.
2. **Sessions**: list, inspect, search intelligence, drill into concerns, and navigate thread families.
3. **Projects and workflows**: status, failure patterns, and operational diagnostics.
4. **Connectivity**: named targets, local-default behavior, remote-ready authentication, and clear instance identity.

This PRD proposes a stable client/server contract for that CLI so the tool can be installed anywhere and pointed at whichever CCDash instance the user needs.

---

## 3. Context & background

### Current state

The recently completed CLI/MCP work established a solid first step:

1. A Typer-based `ccdash` command exists.
2. The CLI can render human, JSON, and markdown output.
3. It is installed through `pip install -e .` during `npm run setup`.
4. It directly bootstraps `CorePorts` and the local backend runtime instead of calling a networked CCDash instance.

That architecture is intentionally repo-local. It assumes:

1. The user has the CCDash repository checked out.
2. The user has run the project bootstrap.
3. The CLI is executed from the project-managed virtual environment or from a PATH entry pointing into that virtual environment.

### Structural gap

The current CLI is not a distributable operator product. It is a development affordance bound to the CCDash source tree and local Python environment. It does not yet solve these needs:

1. Install `ccdash` once on a machine and use it from any working directory.
2. Point the CLI at a CCDash instance running elsewhere.
3. Persist and switch between named targets.
4. Offer broad read-only access to CCDash data domains without requiring local DB access or an editable install.

### Data opportunity

CCDash already exposes rich read surfaces that are relevant to a standalone CLI:

1. Composite project intelligence via `/api/agent/*`.
2. Feature detail and linked session data via `/api/features/*`.
3. Session intelligence listing, detail, search, and drilldown via `/api/analytics/session-intelligence*`.

The missing piece is a stable, versioned, CLI-oriented client contract and a standalone distribution that consumes it.

---

## 4. Problem statement

Users cannot treat CCDash as a normal globally installed command-line tool. The current CLI is coupled to the repo checkout, local virtual environment, and in-process backend runtime. That prevents widespread operational use, makes remote access awkward, and limits the CLI surface to a narrow MVP rather than broad read-only access to CCDash's feature and session intelligence.

---

## 5. User personas

| Persona | Description | Primary need |
|---------|-------------|--------------|
| **Local operator** | Developer or tech lead running CCDash locally and wanting fast terminal access without opening the browser | Local-default CLI with zero repo-path friction |
| **Remote operator** | Engineer or manager querying a shared CCDash deployment from a laptop or jump box | Named remote targets and stable auth/config behavior |
| **Automation engineer** | CI/CD or scheduled job author consuming structured CCDash insights | JSON-first command output and stable exit codes |
| **Analyst / investigator** | User exploring feature delivery and session behavior to understand why work succeeded or failed | Broad read-only feature and session command coverage |

---

## 6. Goals & success metrics

| Goal | Metric | Target |
|------|--------|--------|
| Installable as a real operator tool | `pipx install ...` yields a working `ccdash` binary on a clean machine | 100% |
| Local-first without repo coupling | `ccdash status project` works against a default local server with no repo checkout requirement | 100% |
| Remote-ready connectivity | User can switch to a configured remote target in one command and successfully query it | 100% |
| Broader insight coverage | At least 10 high-value read-only commands ship in v1, centered on features and sessions | >=10 commands |
| Contract stability | CLI JSON output matches versioned server DTOs exactly | 100% for covered endpoints |
| Performance | Common commands return first output quickly against local deployments | p95 < 1.5 s |
| Clear failures | Unreachable server, invalid auth, and unknown entities return actionable errors and non-zero exits | 100% |

---

## 7. User stories

### Epic 1: Standalone installation and targeting

| ID | Story | Phase |
|----|-------|-------|
| US-1 | As a local operator, I want to install `ccdash` globally once so I can invoke it from any directory | 1 |
| US-2 | As a local operator, I want the CLI to default to my local CCDash instance so I do not need to pass a URL constantly | 1 |
| US-3 | As a remote operator, I want to save and switch named CCDash targets so I can inspect different environments quickly | 1 |

### Epic 2: Project and feature visibility

| ID | Story | Phase |
|----|-------|-------|
| US-4 | As a project operator, I want `ccdash status project` to query a running CCDash instance instead of a local repo runtime | 2 |
| US-5 | As an investigator, I want to list features and inspect feature details from the CLI | 3 |
| US-6 | As an investigator, I want to view the sessions linked to a feature so I can reconstruct execution history | 3 |
| US-7 | As an operator, I want report generation commands to keep working in standalone mode | 3 |

### Epic 3: Session intelligence visibility

| ID | Story | Phase |
|----|-------|-------|
| US-8 | As an investigator, I want to list sessions with filters and pagination from the CLI | 3 |
| US-9 | As an investigator, I want to inspect a single session and its thread family from the CLI | 3 |
| US-10 | As an investigator, I want to search session intelligence and drill into concerns without opening the browser | 3 |

### Epic 4: Remote-ready operations

| ID | Story | Phase |
|----|-------|-------|
| US-11 | As a remote operator, I want token-based authentication for remote targets | 4 |
| US-12 | As a future platform owner, I want the CLI target model to be federation-ready, even if v1 does not aggregate across instances | 4 |

---

## 8. Functional requirements

### 8.1 Distribution and packaging

| ID | Requirement |
|----|-------------|
| DIST-1 | CCDash shall ship a standalone Python distribution for the CLI that can be installed without checking out the CCDash repository |
| DIST-2 | The standalone CLI shall expose the `ccdash` console command |
| DIST-3 | The recommended installation path shall be `pipx`, with plain `pip install` also supported |
| DIST-4 | The standalone CLI package shall not require direct SQLite or backend runtime access for normal operation |
| DIST-5 | The existing in-repo editable-install CLI may remain for development, but it shall be treated as a dev surface, not the primary operator distribution |
| DIST-6 | `ccdash --version` and `ccdash doctor` shall be available in the standalone distribution |
| DIST-7 | Packaging shall support future release automation for wheels and source distributions |

### 8.2 Target resolution and configuration

| ID | Requirement |
|----|-------------|
| TARGET-1 | The CLI shall resolve a target in this order: explicit flag, environment variable, named active target, local default |
| TARGET-2 | The default local target shall point to `http://127.0.0.1:8000` unless overridden |
| TARGET-3 | The CLI shall persist named targets in a user-scoped config file outside the repo |
| TARGET-4 | The CLI shall support commands to list targets, show the active target, add or update a target, and switch the active target |
| TARGET-5 | Each target record shall include a stable target name, base URL, auth mode, and optional token reference |
| TARGET-6 | The CLI shall include an instance metadata call so users can confirm which CCDash instance answered a command |
| TARGET-7 | Unreachable or misconfigured targets shall produce actionable error messages that mention the failing base URL |

### 8.3 CLI command surface

The v1 command surface shall prioritize read-only access to features and sessions.

| Group | Required commands |
|-------|-------------------|
| `status` | `ccdash status project`, `ccdash workflow failures` |
| `feature` | `ccdash feature list`, `ccdash feature show <feature-id>`, `ccdash feature sessions <feature-id>`, `ccdash feature report <feature-id>`, `ccdash feature documents <feature-id>` |
| `session` | `ccdash session list`, `ccdash session show <session-id>`, `ccdash session search <query>`, `ccdash session drilldown --concern <concern>`, `ccdash session family <root-session-id>` |
| `report` | `ccdash report aar --feature <feature-id>` |
| `target` | `ccdash target list`, `ccdash target show`, `ccdash target use <name>` |

| ID | Requirement |
|----|-------------|
| CMD-1 | All read commands shall support human-readable output and JSON output |
| CMD-2 | Markdown output shall remain supported where the underlying payload is narrative-first, including feature reports and AAR reports |
| CMD-3 | List commands shall support pagination and common filter flags where the backend supports them |
| CMD-4 | Entity detail commands shall return non-zero exit codes for unknown features or sessions |
| CMD-5 | The standalone CLI shall preserve the current high-value reporting workflows from the repo-local CLI |
| CMD-6 | Help text shall describe commands in operator language, not internal backend terminology |

### 8.4 Server-side client contract

| ID | Requirement |
|----|-------------|
| API-1 | CCDash shall expose a versioned, read-only HTTP contract for standalone CLI consumption |
| API-2 | The CLI shall consume only versioned client-facing endpoints, not UI-specific or unstable internal routes |
| API-3 | The server contract shall cover project status, workflow diagnostics, feature list/detail/sessions/documents, session list/detail/search/drilldown/family, and AAR report generation |
| API-4 | DTOs and envelopes used by the standalone CLI shall be shared contract types so server responses and CLI JSON output do not drift |
| API-5 | Server handlers shall remain thin adapters over existing application services and repositories; the CLI contract shall not duplicate business logic |
| API-6 | The server shall provide an instance metadata endpoint returning instance name, version, and environment identity suitable for CLI display |
| API-7 | The standalone CLI contract shall be explicitly versioned to support later remote/federated evolution without breaking scripts |

### 8.5 Authentication and security

| ID | Requirement |
|----|-------------|
| AUTH-1 | Local-default targets may operate without authentication if the local deployment is configured that way |
| AUTH-2 | Remote targets shall support bearer-token authentication in v1 |
| AUTH-3 | Tokens shall be stored via an operator-safe approach, preferably OS keychain integration with a file fallback only if necessary |
| AUTH-4 | The CLI shall never print full secrets in logs, output, or diagnostics |
| AUTH-5 | Authentication failures shall be distinguishable from connectivity failures in both output and exit codes |

### 8.6 Federation preparedness

| ID | Requirement |
|----|-------------|
| FED-1 | v1 shall support exactly one target per command invocation |
| FED-2 | The target/config model shall be designed so future versions can query or aggregate across multiple CCDash instances |
| FED-3 | Responses shall include instance identity metadata so future federation work can merge results safely |
| FED-4 | Cross-instance aggregation, fan-out queries, and conflict resolution are out of scope for v1 |

---

## 9. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | The standalone CLI shall run on macOS, Linux, and Windows |
| NFR-2 | The CLI shall degrade gracefully when the target server is older or missing a supported endpoint |
| NFR-3 | Common commands against a healthy local target shall return first output in under 1.5 seconds at p95 |
| NFR-4 | JSON output shall be deterministic and script-friendly |
| NFR-5 | The CLI shall keep dependencies lean enough for fast `pipx` installation |
| NFR-6 | The versioned client contract shall be documented and test-covered |

---

## 10. Scope

### In scope

1. Standalone global installation of the CLI.
2. Local-default target behavior backed by HTTP to a running CCDash instance.
3. Named remote targets and target switching.
4. Read-only feature, session, project, workflow, and report commands.
5. Shared DTOs and a versioned CLI-facing server API contract.
6. Remote-ready auth foundations for bearer tokens.

### Out of scope

1. Write or mutation commands.
2. Multi-instance aggregation or federation fan-out in v1.
3. Browser-based target management UI.
4. Replacing the dev-only in-process CLI used for backend development workflows.
5. Full SSO or enterprise RBAC design.

---

## 11. Dependencies and assumptions

| Type | Item | Notes |
|------|------|-------|
| Dependency | Existing feature and session read services | The standalone CLI depends on current server-side data quality and route coverage |
| Dependency | Versioned HTTP contract | A stable API must exist before broad CLI command expansion can ship safely |
| Dependency | Packaging and release workflow | The CLI needs a publishable distribution path separate from local editable install assumptions |
| Assumption | Local operators will often have a CCDash server running on localhost | This justifies the local-default target model |
| Assumption | Feature and session read access are the highest-value domains for the next CLI iteration | This drives command prioritization |

---

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| CLI binds to unstable internal endpoints | Medium | High | Introduce a versioned client contract and shared DTOs before broad command expansion |
| Packaging split creates duplication with current dev CLI | Medium | Medium | Keep dev CLI as a thin local-only surface and converge formatting/output utilities where possible |
| Remote auth design is too weak for later federation | Medium | High | Standardize target metadata, auth hooks, and instance identity in v1 even if federation is deferred |
| Command surface grows faster than backend contract maturity | Medium | Medium | Phase feature/session commands behind stable server endpoints and acceptance gates |
| Users confuse local-default behavior with embedded/offline mode | Low | Medium | Document clearly that standalone CLI talks to a running instance and add `ccdash doctor` diagnostics |

---

## 13. Target state

After this feature ships:

1. A user can install `ccdash` globally via `pipx`.
2. `ccdash` works from any directory and defaults to a local CCDash server.
3. The same binary can be pointed at a remote CCDash deployment with a named target.
4. Operators can inspect projects, features, sessions, workflows, and reports without opening the browser.
5. The CLI is built on a stable, versioned client contract suitable for later federation work.

---

## 14. Acceptance criteria

| ID | Acceptance criterion |
|----|----------------------|
| AC-1 | `pipx install ...` produces a working `ccdash` command on a clean machine |
| AC-2 | `ccdash doctor` reports the resolved target, server reachability, and instance metadata |
| AC-3 | With a local CCDash server running on default settings, `ccdash status project` succeeds without extra target flags |
| AC-4 | Users can store at least two named targets and switch between them with `ccdash target use <name>` |
| AC-5 | `ccdash feature list --json` returns a valid JSON envelope matching the versioned server contract |
| AC-6 | `ccdash feature show <feature-id>` returns non-zero with a clear error for an unknown feature |
| AC-7 | `ccdash feature sessions <feature-id> --json` returns linked-session data for that feature |
| AC-8 | `ccdash session list --json` returns a paginated list of sessions |
| AC-9 | `ccdash session show <session-id>` returns detail for a known session |
| AC-10 | `ccdash session search "<query>" --json` returns search results from the session intelligence surface |
| AC-11 | `ccdash session drilldown --concern <concern>` returns a structured drilldown when supported by the server |
| AC-12 | `ccdash report aar --feature <feature-id> --md` continues to emit a markdown report |
| AC-13 | Authentication failures and connection failures produce distinct user-facing errors |
| AC-14 | CLI JSON output remains consistent with the versioned server DTOs across supported commands |
| AC-15 | The server-side client contract and the CLI package both have automated tests in CI |

---

## 15. Implementation outline

| Phase | Goal |
|------|------|
| 1 | Define shared contracts, package boundaries, target model, and versioned client API shape |
| 2 | Implement the server-side versioned client API for project, feature, session, workflow, and instance metadata reads |
| 3 | Build the standalone CLI package, target store, HTTP client runtime, and core operator commands |
| 4 | Expand feature and session commands, add auth support, and validate local/remote workflows |
| 5 | Finalize packaging, documentation, and release validation |

This implementation approach is detailed in `docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md`.
