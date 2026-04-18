---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: in-progress
category: refactors
title: 'Implementation Plan: Deployment and Runtime Modularization V1'
description: Turn CCDash runtime profiles into deployable API, worker, local, and test operating modes with explicit launch contracts, health semantics, and packaging.
summary: Close the gap between profile-aware runtime composition already in code and a real hosted operator model by separating entrypoints, background-job ownership, probes, env contracts, and deployment artifacts.
author: codex
audience:
- ai-agents
- developers
- platform-engineering
- backend-platform
- devops
created: 2026-04-08
updated: '2026-04-18'
commit_refs:
- "4c64bff"
- "80f3dfc"
- "20887a8"
pr_refs: []
tags:
- implementation
- runtime
- deployment
- worker
- health
- packaging
- refactor
priority: high
risk_level: high
complexity: high
track: Platform
timeline_estimate: 4-6 weeks across 6 phases
feature_slug: deployment-runtime-modularization-v1
feature_family: ccdash-runtime-platform
feature_version: v1
lineage_family: ccdash-runtime-platform
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: refactor
linked_features: []
related_documents:
- docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
- docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md
- docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md
- docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
- docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md
- docs/setup-user-guide.md
- docs/guides/enterprise-session-intelligence-runbook.md
- .claude/progress/deployment-runtime-modularization-v1/phase-4-progress.md
- .claude/skill-specs/ccdash-skill/implementation-plan.md
context_files:
- backend/main.py
- backend/runtime/bootstrap.py
- backend/runtime/bootstrap_api.py
- backend/runtime/bootstrap_local.py
- backend/runtime/bootstrap_worker.py
- backend/runtime/container.py
- backend/runtime/profiles.py
- backend/runtime_ports.py
- backend/adapters/jobs/runtime.py
- backend/cli/runtime.py
- backend/cli/main.py
- backend/mcp/bootstrap.py
- backend/mcp/server.py
- backend/mcp/README.md
- backend/worker.py
- scripts/dev.mjs
- scripts/backend.mjs
- scripts/worker.mjs
- package.json
- docs/setup-user-guide.md
- deploy/observability/docker-compose.yml
- .claude/skill-specs/ccdash-skill/implementation-plan.md
---

# Implementation Plan: Deployment and Runtime Modularization V1

## Objective

Turn CCDash's runtime-profile work from an internal architectural capability into a real deployment contract. The implementation must make `local`, `api`, `worker`, and `test` observable and operationally distinct at the process, packaging, and health-contract levels without regressing the local-first developer experience.

The main gap is no longer profile modeling inside Python. The gap is that launchers, docs, health semantics, and deployment artifacts still leave operators with an effectively mixed-mode system. This plan closes that gap by making runtime selection explicit, moving hosted background ownership to worker runtime(s), and shipping deployable artifacts plus validation guidance.

## Current Baseline

The plan starts from a partially modular runtime foundation, not a greenfield deployment system:

1. Runtime profiles already exist in code for `local`, `api`, `worker`, and `test`, and runtime/storage pairing is validated.
2. `backend/main.py` and `scripts/backend.mjs` still make the default served HTTP runtime resolve to the `local` profile, even though `bootstrap_api.py` exists.
3. `backend/worker.py` already runs the worker lifecycle separately, but worker behavior still depends on active workspace/project resolution and local-ish job assumptions.
4. `/api/health` exposes a rich runtime payload, but there is no explicit liveness/readiness split and no operator-grade worker probe surface.
5. Setup and enterprise docs describe a hosted API plus worker topology, but repo-level packaging artifacts for API, worker, and frontend are still minimal.
6. Core ports still fall back to local-friendly implementations such as permissive auth, in-process job scheduling, and local workspace registry defaults.
7. CLI and MCP access surfaces are now shipped in-repo as lightweight query adapters using `RuntimeContainer(profile=test)` plus explicit request-context bootstrap, which means deployment-runtime changes must preserve their job-free, side-effect-light execution contract.
8. The `ccdash` Claude Code skill now exists as a natural-language operator surface over these tools, so the final rollout needs to update skill routing, deployment guidance, and troubleshooting references after the runtime contract settles.

This plan therefore focuses on converting the existing runtime seams into a safe operator model rather than redoing the foundational profile work already completed.

## Scope And Fixed Decisions

In scope:

1. Explicit launch contracts and bootstrap selection for `local`, `api`, `worker`, and `test`.
2. Background-job ownership, project/workspace binding rules, and hosted-safe routing of sync/watch/refresh work.
3. Health, readiness, and degraded-state contracts for API and worker runtimes.
4. Deployment packaging and configuration contracts for frontend, API, and worker.
5. Runtime observability, validation coverage, and operator-facing rollout documentation.
6. Compatibility and documentation updates for operator query surfaces now exposed through CLI, MCP, and the `ccdash` skill.

Out of scope:

1. Kubernetes-specific manifests or cluster policy.
2. A distributed queue platform or horizontally sharded worker fleet design.
3. Full auth, RBAC, or SSO product delivery.
4. Multi-region deployment or HA database topology.

Non-negotiables:

1. `npm run dev` and `backend.main:app` remain the one-command local-convenience path.
2. Hosted API startup must never silently fall back to local watch/sync behavior or permissive hosted defaults.
3. Worker responsibilities must be independently startable, restartable, and probeable.
4. Runtime differences should live in composition, launch, and capability guardrails, not in broad route forks.
5. Packaging is container-first, but process-manager equivalents must remain documented and equivalent in behavior.
6. CLI and MCP query surfaces must remain lightweight, non-serving adapters and must not inherit local startup sync, watcher, or worker side effects as hosted runtime work proceeds.

## Target Deployment Shape

### Runtime Entry Points

| Runtime | Canonical entrypoint | Responsibility boundary | Notes |
|------|----------------------|-------------------------|-------|
| Local | `backend.main:app` and `npm run dev` | Desktop-style API plus optional in-process watch/sync/jobs | Preserves current contributor workflow |
| Hosted API | `backend.runtime.bootstrap_api:app` | HTTP serving only, no incidental watcher/startup sync work | Must fail fast on unsupported hosted config |
| Worker | `python -m backend.worker` | Sync, refresh, scheduled jobs, reconciliation, and other background work | Runs independently from HTTP |
| Test | `backend.runtime.bootstrap_test:app` | Deterministic app boot with incidental background work disabled | Used for isolated test harnesses |

### Operator Contract

1. Runtime selection is explicit in the process entrypoint and launch scripts, not inferred only from environment variables.
2. Hosted runtime env contracts are split into shared, API-only, worker-only, and local-only concerns.
3. API and worker each expose liveness, readiness, and detailed degraded-state payloads using a common schema.
4. Worker runtime exposes a lightweight probe surface on a dedicated admin port rather than relying only on logs or process exit codes.
5. Logs, traces, and health payloads identify runtime profile, storage profile, deployment mode, and worker/job role explicitly.

### Operator Query Surfaces

| Surface | Current posture | Deployment-runtime implication |
|------|-----------------|--------------------------------|
| CLI | Lightweight query adapter bootstrapped through `backend/cli/runtime.py` | Must stay side-effect-light and compatible with the stabilized runtime contract |
| MCP | Stdio FastMCP server bootstrapped through `backend/mcp/bootstrap.py` | Must preserve its lightweight bootstrap and transport envelope while runtime semantics evolve |
| `ccdash` skill | Natural-language operator layer over CLI today, with MCP-aware routing planned | Final rollout must update references, recipes, and transport guidance to match the shipped topology |

### Packaging Targets

Illustrative artifact targets for this plan:

1. `deploy/runtime/api` for hosted API container and launch config.
2. `deploy/runtime/worker` for worker container and probe surface config.
3. `deploy/runtime/frontend` for static frontend build/serve contract.
4. `deploy/runtime/compose.hosted.yml` or equivalent smoke-stack artifact for split runtime validation.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Runtime Contract and Launch Surface | 8 pts | 3-4 days | Yes | Make runtime selection explicit and remove hosted entrypoint ambiguity |
| 2 | Worker Ownership and Job Routing | 14 pts | 5-6 days | Yes | Move hosted background responsibilities behind an explicit worker contract while preserving lightweight CLI/MCP tooling posture |
| 3 | Health, Readiness, and Degradation Semantics | 13 pts | 5-6 days | Yes | Give operators real API and worker probes with actionable state plus stable machine-consumable diagnostics |
| 4 | Packaging and Configuration Contracts | 10 pts | 4-5 days | Yes | Ship reproducible build/run artifacts and clear env boundaries |
| 5 | Observability and Hosted Safety Guardrails | 8 pts | 3-4 days | Partial | Ensure runtime metadata and misconfiguration signals are operationally useful |
| 6 | Validation, Documentation, and Rollout | 10 pts | 4-5 days | Final gate | Land test matrix, hosted smoke flow, operator documentation, and skill refresh |

**Total**: ~63 story points over 4-6 weeks

## Implementation Strategy

### Critical Path

1. Freeze entrypoint and launch semantics before adding new packaging artifacts.
2. Separate hosted worker ownership and project binding before finalizing readiness semantics.
3. Define probe contracts before shipping container/process-manager templates.
4. Add observability and config guardrails before rollout documentation claims hosted safety.
5. Finish with automated runtime-matrix validation and operator-facing smoke checks.

### Parallel Work Opportunities

1. Packaging scaffolding can start once Phase 1 freezes canonical entrypoints.
2. Probe payload design in Phase 3 can begin while Phase 2 hardens worker ownership and job-class routing.
3. Documentation updates and hosted smoke scripts can be drafted incrementally once each phase's runtime contract is stable.
4. CLI/MCP compatibility coverage and `ccdash` skill doc updates can be prepared in parallel once Phase 3 locks the probe/detail contract and Phase 4 locks packaging/env boundaries.

### Migration Order

1. Launch surface cleanup
2. Worker/job ownership hardening
3. API and worker probe semantics
4. Packaging and env split
5. Observability and fail-fast guardrails
6. Validation and rollout

## Phase 1: Runtime Contract and Launch Surface

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| RUN-001 | Canonical Entrypoint Matrix | Freeze the canonical entrypoint for each runtime and align docs, package scripts, and tests around those names. | `local`, `api`, `worker`, and `test` each have one explicit operator-facing bootstrap path with no ambiguous default hosted path. | 2 pts | backend-architect | None |
| RUN-002 | Hosted API Launcher Refactor | Update `scripts/backend.mjs`, package scripts, and related launch helpers so hosted startup resolves to `backend.runtime.bootstrap_api:app` while `backend.main:app` stays local-only. | There is no hosted startup path that accidentally boots the local profile. | 4 pts | python-backend-engineer | RUN-001 |
| RUN-003 | Runtime Capability Guardrails | Add startup validation that rejects invalid runtime/storage/auth combinations and surfaces runtime metadata consistently at boot. | Invalid hosted pairings fail fast before serving traffic; runtime metadata is visible in logs and health output. | 2 pts | backend-architect, python-backend-engineer | RUN-001 |

**Phase 1 Quality Gates**

1. Hosted API launch no longer routes through `backend.main:app`.
2. Local developer flow remains unchanged for `npm run dev`.
3. Docs, package scripts, and tests agree on the same runtime contract.

## Phase 2: Worker Ownership and Job Routing

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, data-layer-expert, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| JOB-101 | Background Job Ownership Matrix | Classify all current background work including startup sync, file watch, analytics snapshots, telemetry export, integration refresh, and reconciliation by runtime owner and trigger model, including the API-local manual exception paths for telemetry push-now, integration refresh/backfill, and cache sync endpoints. | Every long-running or scheduled concern is explicitly owned by `local`, `worker`, or an API-local exception path, and those API-local exception paths are named explicitly. | 3 pts | backend-architect, DevOps | RUN-003 |
| JOB-102 | Worker Binding Contract | Replace implicit active-project assumptions with an explicit worker binding contract based on operator configuration or workspace-registry resolution rules. | Worker startup does not rely on interactive local state and can be started intentionally in hosted environments. | 4 pts | backend-architect, python-backend-engineer | JOB-101 |
| JOB-103 | Filesystem Adapter Isolation | Move watcher and filesystem-ingest assumptions behind local/worker-only adapter boundaries and prevent accidental start in `api` or `test` profiles. | API and test runtimes never start watcher/file-ingest behavior; local and worker start it only when allowed by contract. | 2 pts | python-backend-engineer | JOB-101 |
| JOB-104 | Local Co-Run Compatibility | Preserve the current local convenience posture where API plus jobs may co-run, while keeping hosted API stateless and background-free. | Local runtime still supports one-process convenience; hosted API keeps only truly API-local responsibilities. | 3 pts | backend-architect | JOB-102 |
| JOB-105 | CLI/MCP Lightweight Bootstrap Invariants | Codify that CLI and MCP query surfaces remain non-serving, non-job-owning adapters that use lightweight runtime bootstrap and never trigger watcher, startup sync, or worker ownership paths. | CLI and MCP continue to work through runtime modularization without inheriting API/worker side effects or requiring hosted HTTP boot. | 2 pts | backend-architect, python-backend-engineer | JOB-101 |

**Phase 2 Quality Gates**

1. Hosted API no longer owns watcher, startup sync, or scheduled background work.
2. Worker can be started independently with explicit responsibility boundaries.
3. Local runtime still supports current contributor workflows without hidden hosted assumptions.
4. CLI and MCP remain lightweight query adapters with no accidental job or watcher ownership.

## Phase 3: Health, Readiness, and Degradation Semantics

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| OPS-201 | Probe Contract | Define a common liveness, readiness, and detailed-state schema for API and worker runtimes, including degraded-state semantics and recommended probe intervals. | Operators can tell the difference between live, ready, and degraded for both runtimes using one shared contract. | 3 pts | backend-architect, DevOps | JOB-104 |
| OPS-202 | API Probe Split | Refactor the current `/api/health` surface into additive live/ready/detail endpoints or equivalent payloads that distinguish DB, migration, auth, storage, and runtime-capability state. | API probes separate "process is up" from "runtime is ready" and expose actionable degraded signals. | 3 pts | python-backend-engineer | OPS-201 |
| OPS-203 | Worker Probe Surface | Add a lightweight probe server or equivalent admin-port surface for worker runtime that reports job state, checkpoint freshness, backlog, and last-success markers. | Worker runtime is probeable by container orchestrators or process managers without serving the full API router set. | 3 pts | python-backend-engineer, DevOps | OPS-201 |
| OPS-204 | Degradation Tests | Add tests for degraded and unready conditions such as auth provider misconfiguration, pending migrations, missing worker binding, queue backlog, and disabled integrations. | Key failure modes map to predictable probe results and are covered by automated tests. | 2 pts | python-backend-engineer | OPS-202 |
| OPS-205 | Tooling-Facing Diagnostic Contract | Ensure readiness/detail payloads expose stable machine-consumable fields that CLI, MCP, and downstream skill guidance can rely on for troubleshooting and operator flows. | CLI/MCP consumers can surface deployment/runtime diagnosis without scraping human-only logs or undocumented payload details. | 2 pts | python-backend-engineer, documentation-writer | OPS-201 |

**Phase 3 Quality Gates**

1. API and worker each expose operator-grade probe surfaces.
2. Degraded and unready states are consistent across runtimes.
3. Hosted validation no longer depends on interpreting ad hoc log output alone.
4. Probe and detail payloads are stable enough for CLI/MCP and skill-driven troubleshooting flows.

## Phase 4: Packaging and Configuration Contracts

**Assigned Subagent(s)**: DevOps, backend-architect, frontend-developer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PKG-301 | Env Contract Split | Define shared, API-only, worker-only, and local-only environment/secrets contracts and add validation that prevents local defaults from leaking into hosted mode. | Hosted profiles declare required secrets and fail early when mandatory configuration is missing. | 3 pts | backend-architect, DevOps | OPS-204 |
| PKG-302 | Runtime Container Artifacts | Add container-first build artifacts for API, worker, and frontend plus a hosted smoke-stack composition artifact. | Operators can build and run a split CCDash stack reproducibly without reverse-engineering dev scripts. | 4 pts | DevOps, frontend-developer | PKG-301 |
| PKG-303 | Process Manager Equivalents | Document and, where practical, ship example systemd or supervisor launch definitions equivalent to the container topology. | Non-container operators have launch examples that match the same runtime contract. | 1 pt | DevOps | PKG-301 |
| PKG-304 | Frontend/API Serving Boundary | Make the frontend static-build and serving contract explicit so frontend deployment is decoupled from backend runtime assumptions. | Frontend packaging clearly targets hosted API URLs and no longer depends on bundled backend startup behavior. | 2 pts | frontend-developer, documentation-writer | PKG-302 |

**Phase 4 Quality Gates**

1. API, worker, and frontend artifacts are separately buildable and runnable.
2. Hosted env contracts are explicit and validated.
3. Process-manager and container guidance describe the same topology.

## Phase 5: Observability and Hosted Safety Guardrails

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| OBS-401 | Runtime Metadata Telemetry | Tag logs, traces, and metrics with runtime profile, storage profile, deployment mode, project binding, and worker role metadata. | API and worker telemetry can be filtered and interpreted by runtime mode without guesswork. | 2 pts | DevOps, python-backend-engineer | PKG-302 |
| OBS-402 | Misconfiguration Guardrails | Add structured warnings and fail-fast checks for permissive auth fallback, invalid storage pairing, missing secrets, unsupported integration settings, and unsafe worker bindings. | Hosted misconfiguration becomes visible and actionable before it turns into silent mixed-mode behavior. | 3 pts | backend-architect, python-backend-engineer | PKG-301 |
| OBS-403 | Backpressure and Freshness Signals | Expose job backlog, last successful execution times, sync lag, and watcher-disabled state in metrics and detailed health payloads. | Operators can see when worker behavior is degraded even if the process is still live. | 3 pts | DevOps, python-backend-engineer | OPS-203 |

**Phase 5 Quality Gates**

1. Runtime metadata is present in primary observability surfaces.
2. Hosted safety failures are visible and fail fast where appropriate.
3. Worker freshness and backlog signals are available for alerting.

## Phase 6: Validation, Documentation, and Rollout

**Assigned Subagent(s)**: python-backend-engineer, DevOps, documentation-writer, task-completion-validator

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| VAL-501 | Runtime Matrix Test Coverage | Extend automated coverage for runtime entrypoints, invalid config cases, probe semantics, background-job ownership boundaries, and CLI/MCP lightweight bootstrap invariants. | CI covers `local`, `api`, `worker`, and `test` runtime expectations plus key negative cases and proves CLI/MCP do not pick up runtime side effects. | 3 pts | python-backend-engineer | OBS-403 |
| VAL-502 | Hosted Smoke Validation Flow | Add a repeatable hosted smoke workflow covering API start, worker start, probe checks, migrations, one representative background job path, and representative CLI + MCP queries against the stabilized runtime contract. | Staging validation is executable, includes operator-tooling surfaces, and is not dependent on tribal knowledge. | 3 pts | DevOps, task-completion-validator | PKG-302 |
| VAL-503 | Operator Docs and Migration Notes | Update setup and runbook documentation with final commands, env tables, failure modes, local-versus-hosted migration guidance, and explicit CLI/MCP operator-surface posture. | Operator docs match the shipped entrypoints, artifacts, probes, and supported query surfaces exactly. | 2 pts | documentation-writer | VAL-502 |
| VAL-504 | `ccdash` Skill Refresh | Update the `ccdash` skill references, recipes, and transport guidance so it reflects the final deployment/runtime topology, probe semantics, and MCP-aware routing posture. | The skill no longer assumes stale deployment behavior and points operators to the correct runtime, probe, and troubleshooting flows. | 2 pts | documentation-writer, skill-creator | VAL-503 |

**Phase 6 Quality Gates**

1. Runtime matrix coverage passes in CI.
2. Hosted smoke validation succeeds with split API and worker runtimes plus representative CLI and MCP queries.
3. Documentation no longer overstates capabilities that are not actually shipped in launch artifacts.
4. The `ccdash` skill is updated to the final runtime contract and no longer routes through stale deployment guidance.
