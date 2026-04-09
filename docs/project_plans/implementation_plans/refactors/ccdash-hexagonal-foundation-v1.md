---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: completed
category: refactors
title: 'Implementation Plan: CCDash Hexagonal Foundation V1'
description: Refactor CCDash into explicit runtime composition, application services,
  and port/adapter boundaries that support auth, hosted deployment, and storage modularization.
summary: Sequence the foundation refactor through runtime composition, request context,
  storage injection, bounded-context service extraction, worker separation, and frontend
  shell cleanup without breaking local-first operation.
author: codex
audience:
- ai-agents
- developers
- platform-engineering
- backend-platform
created: 2026-03-11
updated: '2026-04-07'
commit_refs:
- https://github.com/miethe/CCDash/commit/5993636
- https://github.com/miethe/CCDash/commit/e954416
- https://github.com/miethe/CCDash/commit/9d51672
pr_refs: []
tags:
- implementation
- architecture
- refactor
- hexagonal
- ports-adapters
- runtime
priority: critical
risk_level: high
complexity: high
track: Foundation
timeline_estimate: 4-6 weeks across 6 phases
feature_slug: ccdash-hexagonal-foundation-v1
feature_family: ccdash-platform-foundation
feature_version: v1
lineage_family: ccdash-platform-foundation
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: refactor
linked_features: []
related_documents:
- docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
- docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
- docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
- docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
- docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
- docs/project_plans/designs/ccdash-runtime-port-adapter-map-v1.md
context_files:
- backend/main.py
- backend/db/connection.py
- backend/db/factory.py
- backend/db/sync_engine.py
- backend/project_manager.py
- backend/routers/api.py
- backend/routers/analytics.py
- backend/routers/execution.py
- backend/routers/integrations.py
- contexts/DataContext.tsx
---

# Implementation Plan: CCDash Hexagonal Foundation V1

## Objective

Create the architectural seams CCDash needs before shared auth, hosted deployment, and deeper data-platform work land. The implementation must move composition and adapter selection out of routers and process-global state while preserving the current local-first desktop workflow.

## Scope and Fixed Decisions

In scope:

1. Runtime composition for `local`, `api`, `worker`, and `test` profiles.
2. Request-scoped context carrying principal, workspace/project scope, and trace metadata.
3. Explicit ports for identity, authorization, workspace registry, storage unit of work, job scheduling, and integrations.
4. Migration of the first bounded contexts from router-orchestrated logic to application services.
5. Frontend boundary split so session/auth state and data-access clients are no longer implicit inside `DataContext`.

Out of scope:

1. Full RBAC and SSO feature delivery.
2. Final hosted infrastructure packaging.
3. Storage-engine redesign beyond the seams needed for composition and injection.

Non-negotiables:

1. Preserve existing REST contracts unless a phase explicitly documents a safe additive change.
2. Keep local no-auth operation as a first-class runtime profile.
3. Migrate by bounded context; no big-bang rewrite.
4. Add guardrails that prevent routers from regressing back to direct `connection` or `factory` usage.

## Proposed Module Targets

Suggested package layout for the refactor:

1. `backend/application/`
   - `context.py`
   - `ports/`
   - `services/`
2. `backend/runtime/`
   - `profiles.py`
   - `container.py`
   - `bootstrap_api.py`
   - `bootstrap_worker.py`
   - `bootstrap_local.py`
3. `backend/adapters/`
   - `auth/`
   - `jobs/`
   - `storage/`
   - `integrations/`
4. Frontend:
   - `contexts/AppSessionContext.tsx`
   - `services/apiClient.ts`
   - `services/runtimeProfile.ts`

Package names are illustrative, but the end state must separate application contracts from adapter code.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Runtime Composition Spine | 10 pts | 4-5 days | Yes | Introduce runtime profiles and container/composition boundaries |
| 2 | Request Context and Core Ports | 9 pts | 4 days | Yes | Define request-scoped context and framework-agnostic ports |
| 3 | Storage Injection and Workspace Boundary | 11 pts | 5-6 days | Yes | Replace runtime-type dispatch and singleton workspace coupling |
| 4 | Bounded-Context Service Migration | 14 pts | 1.5 weeks | Yes | Move first backend flows behind application services |
| 5 | Worker and Background Job Separation | 8 pts | 4 days | Partial | Pull watch/sync/analytics/integration refresh behind job adapters |
| 6 | Frontend Shell Split, Guardrails, and Rollout | 10 pts | 4-5 days | Final gate | Split `DataContext`, add architecture tests, document boundaries |

**Total**: ~62 story points over 4-6 weeks

## Implementation Strategy

### Critical Path

1. Land runtime profile/container primitives first.
2. Introduce request context and port contracts before moving business logic.
3. Replace storage and workspace globals before migrating routers to services.
4. Extract worker responsibilities after service seams exist.
5. Finish with frontend shell cleanup, architecture guardrails, and docs.

### Parallel Work Opportunities

1. Phase 5 can begin once Phases 1-3 define the runtime and job interfaces.
2. Frontend shell split in Phase 6 can start after Phase 2 finalizes request/session contracts and Phase 4 stabilizes the first migrated service responses.
3. Documentation and import-guard tests can be added incrementally after each migrated bounded context rather than waiting for the final phase.

### Migration Order

Recommended bounded-context order:

1. Workspace/project context
2. Sessions/documents/features read paths
3. Execution and integrations flows
4. Analytics and background jobs

This keeps the highest-leverage cross-cutting concerns moving first and minimizes churn in feature-specific code.

## Phase 1: Runtime Composition Spine

**Assigned Subagent(s)**: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| ARC-001 | Runtime Profile Model | Define `local`, `api`, `worker`, and `test` runtime profiles with capability flags for watch, sync, jobs, auth, and integrations. | Runtime profile contract exists and can be selected without importing concrete adapters into routers. | 3 pts | backend-architect | None |
| ARC-002 | Composition Container | Add a composition container/bootstrap layer that wires repositories, services, adapters, and observability once per runtime. | `backend/main.py` no longer owns direct adapter selection logic; runtime bootstrap code exists. | 4 pts | backend-architect, python-backend-engineer | ARC-001 |
| ARC-003 | Startup Decomposition | Split API startup, local convenience boot, and test boot paths so future worker startup does not depend on API lifespan. | API startup path can run without mandatory watcher/sync startup; tests can boot a stripped profile. | 3 pts | python-backend-engineer | ARC-002 |

**Phase 1 Quality Gates**

1. API boot path is composition-driven.
2. Local profile still supports current startup behavior.
3. Test profile disables incidental background work by default.

## Phase 2: Request Context and Core Ports

**Assigned Subagent(s)**: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PORT-001 | Request Context Contract | Add a request context object carrying principal, workspace scope, project scope, runtime profile, and tracing metadata. | Request handlers can resolve a typed context even in local no-auth mode. | 3 pts | backend-architect | ARC-003 |
| PORT-002 | Core Port Definitions | Define framework-agnostic ports for `IdentityProvider`, `AuthorizationPolicy`, `WorkspaceRegistry`, `StorageUnitOfWork`, `JobScheduler`, and `IntegrationClient`. | Ports live outside adapter code and are imported by services rather than routers. | 4 pts | backend-architect, python-backend-engineer | PORT-001 |
| PORT-003 | Local Adapter Baselines | Add local/default adapters for no-auth identity, permissive authorization, project/workspace resolution, and in-process jobs. | Local runtime behavior remains functional through adapter implementations of the new ports. | 2 pts | python-backend-engineer | PORT-002 |

**Phase 2 Quality Gates**

1. Request-scoped context is available to migrated handlers.
2. Ports are framework-agnostic and testable.
3. Local adapter profile preserves current behavior without auth regressions.

## Phase 3: Storage Injection and Workspace Boundary

**Assigned Subagent(s)**: data-layer-expert, python-backend-engineer, backend-architect

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| STORE-001 | Storage Unit-of-Work Wiring | Introduce storage composition that resolves repositories through runtime/container wiring rather than `isinstance` checks in `backend/db/factory.py`. | Migrated services obtain repositories from injected storage capabilities, not router-level factory calls. | 4 pts | data-layer-expert, python-backend-engineer | PORT-003 |
| STORE-002 | Workspace Registry Refactor | Replace `project_manager` singleton reads on request paths with an injected workspace/project registry abstraction. | Request paths can resolve workspace/project scope without importing the global singleton directly. | 4 pts | backend-architect, python-backend-engineer | PORT-003 |
| STORE-003 | Compatibility Bridge | Add compatibility adapters so SQLite and Postgres keep working during phased migration. | Existing repositories and migrations remain functional while migrated contexts adopt injected storage. | 3 pts | data-layer-expert | STORE-001 |

**Phase 3 Quality Gates**

1. Migrated contexts no longer choose repositories in routers.
2. Workspace/project resolution is injectable and testable.
3. SQLite and Postgres both pass existing smoke coverage for migrated flows.

## Phase 4: Bounded-Context Service Migration

**Assigned Subagent(s)**: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| SVC-001 | Workspace + Session Services | Extract project/workspace selection and at least the first session/document read paths into application services that accept request context and ports. | `backend/routers/api.py` stops orchestrating these migrated flows directly. | 5 pts | backend-architect, python-backend-engineer | STORE-003 |
| SVC-002 | Feature / Execution / Integration Service Pass | Migrate the first execution and integration orchestration flows to service-layer entry points, using existing `feature_execution` and integration service work as references. | `backend/routers/execution.py` and `backend/routers/integrations.py` primarily map HTTP requests/responses. | 5 pts | python-backend-engineer, backend-architect | SVC-001 |
| SVC-003 | Analytics Router Cleanup | Move analytics request orchestration behind application services and reduce direct repository composition in `backend/routers/analytics.py`. | At least one analytics slice is service-owned and uses injected ports/context. | 4 pts | python-backend-engineer | SVC-001 |

**Phase 4 Quality Gates**

1. Newly migrated routers perform HTTP mapping only.
2. Services own business orchestration and receive request context explicitly.
3. No migrated router imports `backend.db.connection` or `backend.db.factory`.

## Phase 5: Worker and Background Job Separation

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| JOB-001 | Job Adapter Boundary | Move file watch, sync, analytics snapshots, and SkillMeat refresh behind a `JobScheduler`/worker adapter boundary. | Background concerns can be enabled or disabled by runtime profile. | 3 pts | backend-architect, python-backend-engineer | STORE-003 |
| JOB-002 | Worker Bootstrap | Add a worker bootstrap path that runs scheduled/background responsibilities without serving HTTP. | Worker runtime can start independently from the API process. | 3 pts | python-backend-engineer, DevOps | JOB-001 |
| JOB-003 | Local Convenience Profile | Recompose local mode so it can optionally co-run API plus job adapters while hosted API remains stateless. | Local-first workflows still support in-process convenience behavior behind profile flags. | 2 pts | backend-architect | JOB-002 |

**Phase 5 Quality Gates**

1. Hosted API runtime does not require watcher/sync startup.
2. Worker runtime can execute background jobs independently.
3. Local profile preserves current desktop-style workflow.

## Phase 6: Frontend Shell Split, Guardrails, and Rollout

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced, backend-architect, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| UI-001 | Session and Runtime Context Split | Split `contexts/DataContext.tsx` into at least session/auth state, project/runtime state, and data-access client layers. | `DataContext` is no longer the implicit auth/runtime boundary for the app shell. | 4 pts | frontend-developer, ui-engineer-enhanced | PORT-001 |
| UI-002 | Architecture Guardrails | Add architecture tests or lint rules preventing direct router imports of DB connection/factory and direct frontend coupling back into a monolithic context. | CI/local checks fail on new router-to-adapter regressions. | 3 pts | backend-architect, frontend-developer | SVC-003 |
| UI-003 | Port/Adapter Map and Rollout Docs | Document the runtime profile map, port/adapter ownership, migrated bounded contexts, and follow-on dependency points for auth/deployment/data work. | Future PRDs can target stable boundaries without reopening the foundation design. | 3 pts | documentation-writer, backend-architect | UI-001 |

**Phase 6 Quality Gates**

1. Frontend app shell has explicit session/runtime/data boundaries.
2. Guardrails protect the refactor from regression.
3. Port/adapter map is documented and linked from follow-on PRDs.

## Validation and Test Strategy

1. Add unit tests for request context construction, local identity/authorization adapters, and container wiring.
2. Add integration tests proving API and worker profiles can boot independently.
3. Add regression tests for migrated routers to ensure they no longer import `backend.db.connection`, `backend.db.factory`, or `backend.project_manager` directly.
4. Keep SQLite and Postgres smoke coverage for migrated services during the transition.
5. Add frontend tests around new app-shell providers so project switching and local no-auth flows still work.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Refactor lands as extra abstraction without reducing coupling | High | Medium | Make router import removal and composition-root usage explicit acceptance gates for each migrated context. |
| Local-first mode regresses while hosted seams improve | High | Medium | Keep a dedicated local adapter profile and compatibility tests in every phase. |
| Migration stalls halfway across bounded contexts | High | High | Sequence by context, document ownership, and add import guardrails as soon as the first context lands. |
| Worker split adds operational complexity too early | Medium | Medium | Start with profile-based in-process job adapters and a simple worker bootstrap before deeper infrastructure changes. |

## Exit Criteria

This implementation plan is complete when:

1. API, worker, local, and test runtime profiles exist with explicit responsibility boundaries.
2. Request-scoped context and the six core ports are implemented and used by the first migrated services.
3. Migrated routers no longer call `connection.get_connection()`, `backend/db/factory.py`, or `project_manager` directly.
4. Background jobs can run outside the API process.
5. The frontend app shell exposes explicit session/runtime/data boundaries.
6. Architecture guardrails and documentation make the foundation usable by the auth, deployment, and data-platform follow-on work.
