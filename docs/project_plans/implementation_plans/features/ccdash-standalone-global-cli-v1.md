---
schema_version: '1.0'
doc_type: implementation_plan
title: CCDash Standalone Global CLI - Implementation Plan
description: Phased implementation plan for turning CCDash into a true globally installed
  CLI backed by a versioned HTTP client contract, local-default targeting, remote-ready
  configuration, and expanded feature/session insight commands.
status: completed
created: '2026-04-12'
updated: '2026-04-13'
feature_slug: ccdash-standalone-global-cli
feature_version: v1
prd_ref: docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
plan_ref: null
scope: Standalone CLI distribution, versioned client API, target config, local-default
  connectivity, remote-ready auth, expanded feature/session commands
effort_estimate: 28-36 story points
effort_estimate_breakdown: 'Phase 1: 4-5 pts | Phase 2: 8-10 pts | Phase 3: 6-7 pts
  | Phase 4: 6-8 pts | Phase 5: 4-6 pts'
priority: high
risk_level: medium
owner: Platform Engineering
contributors:
- Architecture Review Team
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
category: product-planning
tags:
- cli
- distribution
- remote-access
- http-client
- features
- sessions
- packaging
related_documents:
- docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
- docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
- docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md
- docs/guides/cli-user-guide.md
---

# Implementation Plan: CCDash Standalone Global CLI

## Executive Summary

This plan turns the current repo-local CLI into a true globally installable operator tool. The core architectural shift is straightforward:

1. Keep the existing in-repo CLI as a development convenience.
2. Introduce a standalone CLI package that talks to a running CCDash instance over HTTP.
3. Define a versioned server contract for that CLI so packaging and remote access are stable.
4. Expand the command surface toward the richest current data domains: features and sessions.

**Scope**: Standalone distribution, target management, versioned client API, remote-ready auth, expanded feature/session commands

**Total Effort**: 28-36 story points

**Recommended Timeline**: 5 phases across 4-6 weeks

**Critical Path**:

```
Shared contracts and packaging boundary
  ↓
Versioned server-side client API
  ↓
Standalone CLI runtime and target config
  ↓
Feature/session command expansion
  ↓
Release hardening, docs, and validation
```

---

## Implementation Strategy

### Architecture principles

1. **Separate dev CLI from operator CLI**: the current editable-install CLI can remain, but it is not the product distribution.
2. **Network-first standalone runtime**: the global CLI talks to a running CCDash instance over HTTP and does not bootstrap `CorePorts` directly.
3. **Versioned contract**: the standalone CLI consumes only stable, versioned, client-facing endpoints.
4. **Shared schemas**: server DTOs and CLI JSON output come from the same contract package or module set.
5. **Read-only first**: v1 is an operator and investigation tool, not a mutation surface.
6. **Federation-ready target model**: v1 uses one target per command, but stores enough metadata for future multi-instance work.

### Recommended repository shape

The exact folder layout can vary, but the implementation should converge on three explicit concerns:

| Concern | Recommended path |
|---------|------------------|
| Shared client/server contracts | `packages/ccdash_contracts/` |
| Standalone CLI package | `packages/ccdash_cli/` |
| Server-side versioned client API | `backend/routers/client_v1.py` plus supporting services |

If repo policy strongly prefers fewer top-level packages, these can be placed under a different monorepo subtree, but the separation of concerns should remain.

### Why not extend the current CLI in place

The current CLI directly imports backend runtime code and assumes repository-local installation. That is the wrong execution model for a globally installed tool. Reusing every implementation detail would preserve the current coupling instead of removing it.

The right reuse boundary is:

1. Output formatting patterns.
2. Domain vocabulary and command naming.
3. Existing server-side read services and DTO assembly logic.

The wrong reuse boundary is:

1. Direct DB access from the global CLI.
2. Editable-install assumptions.
3. In-process bootstrapping of backend runtime containers.

---

## High-Level Phase Breakdown

| Phase | Goal | Effort | Key deliverables | Assigned subagent(s) |
|------|------|--------|------------------|----------------------|
| 1 | Shared contracts and packaging boundary | 4-5 pts | packaging layout, target model, versioned API contract, ADR-level decisions | `backend-architect`, `python-backend-engineer` |
| 2 | Server-side client API foundation | 8-10 pts | versioned read-only endpoints for instance, project, features, sessions, workflows, reports | `python-backend-engineer`, `backend-architect` |
| 3 | Standalone CLI runtime and distribution | 6-7 pts | standalone package, HTTP client, config store, target commands, doctor, install path | `python-backend-engineer` |
| 4 | Feature and session command expansion | 6-8 pts | feature and session command groups, pagination, search, drilldown, output coverage | `python-backend-engineer`, `documentation-writer` |
| 5 | Remote readiness, docs, and release validation | 4-6 pts | bearer auth, smoke tests, install docs, migration notes, CI/release validation | `python-backend-engineer`, `documentation-writer` |

---

## Phase Dependencies and Sequencing

### Strict dependencies

1. **Phase 2 requires Phase 1** because the server contract and schema boundaries must be defined first.
2. **Phase 3 requires Phase 1 and Phase 2** because the standalone CLI needs a stable contract to call.
3. **Phase 4 requires Phase 2 and Phase 3** because expanded commands depend on both runtime and endpoint coverage.
4. **Phase 5 requires all prior phases** because release validation is only meaningful after the real distribution and command surface exist.

### Parallelization opportunities

1. Shared contract modeling and packaging prototypes can begin in parallel during Phase 1.
2. After Phase 2 endpoint shapes stabilize, CLI target/config work can proceed in parallel with some feature/session command implementation.
3. Documentation can begin once command names and install path are stable, even before final auth hardening.

---

## Detailed Phase Plan

## Phase 1: Shared Contracts and Packaging Boundary

**Goal:** Lock the operator-facing architecture before implementation spreads across server and CLI codepaths.

**Duration:** 3-4 days

**Assigned subagent(s):** `backend-architect`, `python-backend-engineer`

| Task ID | Task | Description | Acceptance criteria | Estimate |
|--------|------|-------------|---------------------|----------|
| P1-T1 | Define package split | Decide standalone CLI package path, shared contract package path, and how the current dev CLI remains supported | Package boundaries documented and unambiguous | 1 pt |
| P1-T2 | Define target model | Specify config schema for named targets, active target resolution, env overrides, and local default behavior | Target resolution order and persisted schema documented | 1 pt |
| P1-T3 | Define versioned client API surface | Enumerate the read-only endpoints required for status, features, sessions, workflows, reports, and instance metadata | Endpoint catalog approved and versioned | 1 pt |
| P1-T4 | Define shared schemas | Identify the DTOs and envelopes shared between server responses and CLI JSON output | Shared contract types listed with ownership | 1 pt |
| P1-T5 | Decide secret storage strategy | Choose preferred token storage behavior for remote targets | Auth storage policy documented | 1 pt |

### Phase 1 Quality Gate

- [ ] Package boundaries are explicit and do not require the standalone CLI to import backend runtime internals
- [ ] A versioned endpoint catalog exists for all planned commands
- [ ] The target/config schema supports local default and named remote targets
- [ ] Shared DTO ownership is clear enough to prevent contract drift
- [ ] Open questions on package naming or publish path are resolved or explicitly deferred

---

## Phase 2: Server-Side Client API Foundation

**Goal:** Expose a stable, versioned HTTP surface for the standalone CLI.

**Duration:** 1-1.5 weeks

**Assigned subagent(s):** `python-backend-engineer`, `backend-architect`

| Task ID | Task | Description | Acceptance criteria | Estimate |
|--------|------|-------------|---------------------|----------|
| P2-T1 | Add instance metadata endpoint | Return instance name, environment, version, and capability summary | CLI can confirm which instance answered | 1 pt |
| P2-T2 | Promote project/workflow endpoints into versioned client surface | Reuse current agent-query services under the new versioned contract | Existing project/workflow CLI coverage works through versioned endpoints | 2 pts |
| P2-T3 | Add feature list/detail endpoints | Provide stable feature list and feature detail payloads with pagination/filter support where appropriate | Feature commands have stable list and detail inputs | 2 pts |
| P2-T4 | Add feature-linked session/documents endpoints | Provide stable endpoints for feature sessions and linked documents | Feature investigations can be done entirely through the client API | 1 pt |
| P2-T5 | Add session intelligence list/detail/search/drilldown/family endpoints | Surface current analytics-backed session intelligence through the versioned contract | Session commands map cleanly to stable server endpoints | 3 pts |
| P2-T6 | Add contract tests | Verify DTO shape and backward-compatible JSON envelopes for all endpoints | Contract tests pass in CI | 1 pt |

### Likely files to create or modify

- `backend/routers/client_v1.py`
- `backend/application/services/...` thin adapter modules as needed
- `packages/ccdash_contracts/src/ccdash_contracts/...`
- `backend/tests/...` contract and router tests

### Phase 2 Quality Gate

- [ ] A versioned client router exists and is registered
- [ ] All planned standalone CLI commands have corresponding server endpoints or a documented defer decision
- [ ] Contract tests verify shape parity between shared DTOs and server responses
- [ ] Existing business logic remains in application services and repositories, not router handlers
- [ ] Instance metadata endpoint is implemented and documented

---

## Phase 3: Standalone CLI Runtime and Distribution

**Goal:** Deliver the new globally installable CLI runtime and core operator commands.

**Duration:** 1 week

**Assigned subagent(s):** `python-backend-engineer`

| Task ID | Task | Description | Acceptance criteria | Estimate |
|--------|------|-------------|---------------------|----------|
| P3-T1 | Scaffold standalone package | Create publishable CLI package with its own `pyproject.toml` and console script | `ccdash` can be installed outside the repo bootstrap flow | 1 pt |
| P3-T2 | Build HTTP client runtime | Add base URL resolution, request client, retries/timeouts, error mapping, and version negotiation hooks | CLI can call the versioned server API reliably | 2 pts |
| P3-T3 | Build config and target store | Persist named targets, active target, env overrides, and local default behavior | Target resolution works exactly as designed | 1 pt |
| P3-T4 | Implement operator commands | Ship `target`, `doctor`, `version`, plus migrated project/workflow commands | Core operator workflow works end-to-end | 2 pts |
| P3-T5 | Add install and smoke tests | Validate clean install via `pipx` or equivalent CI smoke flow | Clean-machine install path is proven | 1 pt |

### Likely files to create or modify

- `packages/ccdash_cli/pyproject.toml`
- `packages/ccdash_cli/src/ccdash_cli/main.py`
- `packages/ccdash_cli/src/ccdash_cli/runtime/...`
- `packages/ccdash_cli/src/ccdash_cli/commands/...`
- `packages/ccdash_cli/tests/...`

### Phase 3 Quality Gate

- [ ] `ccdash --help` works from a standalone install
- [ ] `ccdash doctor` reports target resolution and instance health clearly
- [ ] Target commands work with a persisted config outside the repo
- [ ] Existing status and workflow commands work through HTTP rather than in-process backend bootstrap
- [ ] Install smoke tests prove the CLI works on a clean environment

---

## Phase 4: Feature and Session Command Expansion

**Goal:** Expose the highest-value feature and session investigations from the CLI.

**Duration:** 1-1.5 weeks

**Assigned subagent(s):** `python-backend-engineer`, `documentation-writer`

| Task ID | Task | Description | Acceptance criteria | Estimate |
|--------|------|-------------|---------------------|----------|
| P4-T1 | Implement feature command group | Add `feature list`, `feature show`, `feature sessions`, `feature documents`, and keep `feature report` aligned | Feature workflows are available entirely from the standalone CLI | 2 pts |
| P4-T2 | Implement session command group | Add `session list`, `session show`, `session search`, `session drilldown`, and `session family` | Session intelligence workflows are available entirely from the standalone CLI | 3 pts |
| P4-T3 | Add pagination and filters | Standardize list/search flags across commands and JSON envelope behavior | List/search commands behave consistently | 1 pt |
| P4-T4 | Preserve narrative/reporting output | Keep markdown-first flows for feature reports and AARs | Existing narrative flows remain operator-friendly | 1 pt |
| P4-T5 | Add command-level tests | Cover happy path, not found, bad target, auth failure, and JSON parity scenarios | Command suite is robust in CI | 1 pt |

### Phase 4 Quality Gate

- [ ] At least 10 high-value read-only commands are shipped
- [ ] Feature-linked session workflows are fully usable from the CLI
- [ ] Session search and drilldown commands operate through stable server endpoints
- [ ] JSON output is deterministic and validated in tests
- [ ] Markdown output remains available for narrative report commands

---

## Phase 5: Remote Readiness, Documentation, and Release Validation

**Goal:** Harden the CLI for real operator use beyond localhost.

**Duration:** 3-5 days

**Assigned subagent(s):** `python-backend-engineer`, `documentation-writer`

| Task ID | Task | Description | Acceptance criteria | Estimate |
|--------|------|-------------|---------------------|----------|
| P5-T1 | Add bearer-token auth flow | Support token-backed targets and safe secret storage behavior | Remote targets can authenticate successfully | 2 pts |
| P5-T2 | Harden failure handling | Distinguish auth, connectivity, timeout, and version mismatch failures | Operators get clear actionable diagnostics | 1 pt |
| P5-T3 | Write operator docs | Document install, local default usage, target management, and remote usage | Docs cover the new install and runtime model | 1 pt |
| P5-T4 | Add migration notes | Explain how the new standalone CLI relates to the old repo-local CLI | Developers and operators know which tool to use when | 1 pt |
| P5-T5 | Final release validation | Run local and remote smoke scenarios and validate publishable artifacts | Release checklist passes | 1 pt |

### Phase 5 Quality Gate

- [ ] Remote targets can be configured and authenticated
- [ ] Error handling clearly distinguishes auth and connectivity problems
- [ ] Installation and usage docs are updated for global distribution
- [ ] Migration guidance exists for users of the repo-local CLI
- [ ] Release artifacts and CI validation are green

---

## Testing Strategy

### Contract testing

1. Validate all versioned client endpoints against shared DTOs.
2. Lock JSON envelopes with golden or schema-based tests.
3. Verify older-server or missing-endpoint behavior is surfaced predictably.

### CLI testing

1. Unit-test target resolution and config behavior.
2. Use HTTP mocking for command-level success and failure cases.
3. Run install smoke tests in clean environments using the packaged CLI.

### End-to-end testing

1. Local-default target against a local CCDash instance.
2. Explicit remote target against a non-local base URL.
3. Authenticated remote target with token handling.
4. Feature and session investigation flows end-to-end.

---

## Risks and Mitigation Focus

| Risk | Mitigation focus |
|------|------------------|
| Contract drift between server and CLI | Centralize DTOs in shared contracts and test both sides against them |
| Over-coupling to current router shapes | Route all CLI work through a dedicated versioned client API |
| Packaging complexity stalls delivery | Separate the packaging boundary decision into Phase 1 and do not let it stay implicit |
| Remote auth is bolted on too late | Reserve explicit auth work in Phase 5 and define the target schema early |
| Dev CLI and operator CLI confuse users | Document the difference clearly and preserve the dev CLI only as an internal convenience |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Clean install success | 100% | install smoke tests |
| Local-default status command success | 100% | local E2E workflow |
| Remote target switch success | 100% | named-target E2E workflow |
| Command breadth | >=10 commands | command inventory |
| JSON parity | 100% for supported commands | contract and CLI tests |
| Auth failure clarity | 100% | negative-path test suite |

---

## Recommended Next Steps

1. Approve the package boundary and versioned API direction in Phase 1.
2. Treat the standalone CLI as a new product surface, not just a packaging tweak to the current Typer app.
3. Prioritize feature and session visibility first, because those domains best justify a globally installed CLI.
4. Add progress tracking only after the PRD and implementation plan are approved.
