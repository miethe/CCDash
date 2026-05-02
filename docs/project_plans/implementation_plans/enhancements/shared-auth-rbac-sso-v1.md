---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements
title: "Implementation Plan: Shared Auth, RBAC, and SSO V1"
description: "Implement modular shared auth with local, Clerk, and generic OIDC providers, hierarchical RBAC, and SkillMeat trust alignment while preserving an explicit local no-auth runtime."
summary: "Deliver shared auth through provider abstraction, hosted auth adapters, hierarchical user/team/enterprise RBAC, workspace mapping, frontend session UX, and rollout hardening."
author: codex
owner: platform-engineering
owners: [platform-engineering, security-engineering, fullstack-engineering]
contributors: [ai-agents]
audience: [ai-agents, developers, platform-engineering, security-engineering]
created: 2026-03-20
updated: 2026-05-02
tags: [implementation, auth, oidc, rbac, sso, security, skillmeat]
priority: critical
risk_level: high
complexity: high
track: Identity
timeline_estimate: "6-8 weeks across 8 phases"
feature_slug: shared-auth-rbac-sso-v1
feature_family: shared-identity-access
feature_version: v1
lineage_family: shared-identity-access
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
linked_features: []
related_documents:
  - docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  - docs/project_plans/reports/agentic-sdlc-intelligence-v2-integration-overview-2026-03-08.md
  - docs/setup-user-guide.md
  - examples/skillmeat/project_plans/implementation_plans/features/aaa-rbac-foundation-v1.md
  - examples/skillmeat/project_plans/implementation_plans/features/aaa-rbac-enterprise-readiness-part-2-v1.md
context_files:
  - backend/application/context.py
  - backend/application/ports/core.py
  - backend/runtime/container.py
  - backend/runtime_ports.py
  - backend/runtime/profiles.py
  - backend/adapters/auth/local.py
  - backend/routers/projects.py
  - backend/routers/integrations.py
  - backend/routers/execution.py
  - backend/routers/live.py
  - contexts/AppSessionContext.tsx
  - contexts/AppRuntimeContext.tsx
  - services/apiClient.ts
---

# Implementation Plan: Shared Auth, RBAC, and SSO V1

## Objective

Introduce a hosted-safe identity and authorization layer for CCDash using a modular auth-provider system, hierarchical user/team/enterprise RBAC, workspace/project scoping, and a shared trust contract with SkillMeat while preserving the explicit local no-auth runtime profile already present in the codebase.

## Current Baseline

1. The hexagonal foundation work already introduced `RequestContext`, `Principal`, runtime profiles, and pluggable core ports.
2. `Principal` already carries email, groups, and hierarchical memberships; Phase 1 should refine hosted issuer/provider semantics, service-account identity, and claim mapping rather than re-adding those core fields.
3. `RequestContext` already carries `EnterpriseScope`, `TeamScope`, `TenancyContext`, `ScopeBinding`, and `StorageScope`; the remaining work is to make hosted enforcement consistently consume those scopes.
4. Runtime profiles already compose `StaticBearerTokenIdentityProvider` for the `api` auth capability and `PermitAllAuthorizationPolicy` for permissive local authorization. Hosted auth still needs a provider registry, Clerk/OIDC validation, session flow, and a deny-capable policy.
5. Identity/audit storage repository ports and local/Postgres stubs already exist, including identity access and privileged-action audit surfaces. Auth implementation should build on those ports instead of introducing a parallel storage abstraction.
6. `backend/runtime/container.py` already builds request context per request, which is the correct seam for hosted auth.
7. Several routers and application services accept `RequestContext`, and SkillMeat integration routes are partly request-context aware, but many flows still behave as if every caller is the same trusted local operator.
8. `backend/routers/projects.py`, GitHub integration helpers, and adjacent routers still rely on active-project/path globals that are incompatible with real request-scoped tenancy.
9. `contexts/AppSessionContext.tsx` models project switching only; there is no frontend auth/session state or 401/403 handling path.
10. `services/apiClient.ts` performs plain `fetch()` calls with no auth/session-aware retry or denial semantics, and many protected frontend surfaces still bypass it with direct `fetch()` usage.
11. The integrations surface has partially improved request-context plumbing, but Phase 0 still needs to validate current tests and helper boundaries before it becomes an auth-enforcement migration target.

## Plan Validation Update

Validation date: 2026-05-02

1. This plan has been refreshed against the current repository baseline before development. Existing `Principal`, `RequestContext`, runtime-profile auth composition, identity/audit storage ports, and SkillMeat request-context work are now treated as baseline, not new scope.
2. Phase 0 is an execution gate: complete AUTH-090 and AUTH-091 before starting hosted provider work in Phase 1 or Phase 2. AUTH-092 can run alongside those tasks, but hosted provider implementation should not begin until the backend baseline and enforcement inventory are current.
3. Phase 1 should focus on deltas: hosted issuer/provider metadata, provider configuration, service-account representation, permission vocabulary, claim-to-scope rules, and bootstrap defaults.
4. The highest remaining baseline risk is uneven tenancy migration: SkillMeat routes are partly request-context aware, while GitHub integration helpers, project selection, and file/path-oriented routers still use active project globals.
5. Scope remains unchanged at a product level: modular local/Clerk/OIDC auth, hosted-safe RBAC, SkillMeat trust alignment, frontend session UX, auditability, and explicit local no-auth mode.

## Fixed Decisions

1. Local desktop and test workflows keep an explicit no-auth adapter and must not silently inherit hosted auth requirements.
2. Hosted auth uses a pluggable provider contract aligned with SkillMeat's AAA model: at minimum `Local`, `Clerk`, and generic `OIDC` providers must be supported through one backend abstraction.
3. Principal resolution and authorization decisions live at backend request/service boundaries, not in the UI.
4. V1 uses a resource-action RBAC matrix plus hierarchical binding scopes for `user`, `team`, and `enterprise` levels rather than a generic policy language.
5. Sensitive write, admin, approval, and integration actions must be enforced in services or request dependencies, not only in router copy or frontend gates.
6. Hosted service-to-service SkillMeat calls must reuse the shared trust model or delegated credentials, not a separate ad hoc API-key path.
7. Workspace/project access must nest under the active user/team/enterprise authorization context rather than acting as the top-level tenancy primitive.

## Proposed Module Targets

Backend:

1. `backend/adapters/auth/providers/base.py`
2. `backend/adapters/auth/providers/local.py`
3. `backend/adapters/auth/providers/clerk.py`
4. `backend/adapters/auth/providers/oidc.py`
5. `backend/adapters/auth/provider_factory.py`
6. `backend/adapters/auth/session_state.py`
7. `backend/adapters/auth/claims_mapping.py`
8. `backend/application/services/authentication.py`
9. `backend/application/services/authorization.py`
10. `backend/routers/auth.py`
11. `backend/runtime_ports.py`
12. `backend/runtime/bootstrap_api.py`
13. request-context-aware updates in `backend/routers/projects.py`, `backend/routers/integrations.py`, `backend/routers/execution.py`, `backend/routers/live.py`, `backend/routers/features.py`, `backend/routers/analytics.py`, `backend/routers/codebase.py`, `backend/routers/cache.py`, `backend/routers/session_mappings.py`, `backend/routers/test_visualizer.py`, sensitive `backend/routers/pricing.py`, and hot-path endpoints in `backend/routers/api.py`

Frontend:

1. `services/auth.ts`
2. `contexts/AppAuthContext.tsx`
3. `contexts/AppSessionContext.tsx`
4. `services/apiClient.ts`
5. `services/request.ts` or equivalent shared auth-aware fetch wrapper
6. provider-specific frontend integration surfaces for Clerk and generic hosted auth where required
7. migration of protected request paths in existing services/components onto the shared auth-aware transport
8. app-shell entry points and protected-route handling around existing runtime/data providers

Exact paths may shift, but the end state must keep issuer integration, session transport, authorization logic, and UI session state separated.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 0 | Preflight Stabilization and Scope Inventory | 6 pts | 2-3 days | Yes | Stabilize auth-adjacent seams and inventory the real backend/frontend migration surface before auth implementation begins |
| 1 | Identity Contracts, Provider Abstraction, and Configuration | 10 pts | 4 days | Yes | Finalize the principal, user/team/enterprise subject model, and modular provider config for hosted auth |
| 2 | Auth Provider Adapters and Hosted Session Flow | 12 pts | 4-5 days | Yes | Add provider selection, Clerk/generic OIDC validation, login/callback/logout flow, and secure hosted session handling |
| 3 | Authorization Policy and 3-Tier RBAC Matrix | 12 pts | 4-5 days | Yes | Implement a deny-capable policy layer and canonical permission vocabulary across user/team/enterprise scopes |
| 4 | Scope Mapping and SkillMeat Trust Alignment | 10 pts | 4 days | Partial | Map provider claims into enterprise/team/workspace/project scopes and align outbound SkillMeat auth |
| 5 | Backend Enforcement Migration | 11 pts | 4-5 days | Yes | Move sensitive routes and services onto real authorization checks |
| 6 | Frontend Session UX and Protected Shell | 12 pts | 4-5 days | Partial | Add auth-aware client/session UX and migrate protected request paths without regressing local mode |
| 7 | Audit, Testing, and Rollout Hardening | 9 pts | 3-4 days | Final gate | Add attribution, observability, operator docs, and staged rollout safety |

**Total**: ~82 story points over 6-8 weeks

## Implementation Strategy

### Sequencing Rationale

1. Execute AUTH-090 and AUTH-091 first to validate the integrations/request-scope baseline and inventory the real migration surface before hosted provider work begins.
2. Lock the provider abstraction, identity model, and permission vocabulary before implementing provider-specific auth logic.
3. Land hosted provider/session handling before migrating route enforcement so the policy layer has real principals to evaluate.
4. Define the 3-tier RBAC matrix before broad router migration to avoid duplicating authorization rules in many endpoints.
5. Align enterprise/team/workspace/project claim mapping before wiring SkillMeat trust and before finalizing frontend workspace UX.
6. Keep local no-auth behavior working throughout by using runtime-profile composition instead of conditionals spread through routers.

### Parallel Work Opportunities

1. Once Phase 0 inventory is complete, Phase 1 identity contracts and frontend transport planning can run in parallel.
2. Once Phase 1 contracts are stable, Phase 2 provider-adapter work and Phase 3 policy-matrix drafting can run in parallel.
3. Phase 4 claim-mapping work can overlap with the latter half of Phase 6 once `/api/auth/session` and role payload shapes are stable.
4. Documentation, operator setup, and audit dashboard work can begin during Phase 6 after enforcement coverage is clear.

### Critical Path

1. Phase 0 preflight stabilization
2. Phase 1 contracts
3. Phase 2 hosted session flow
4. Phase 3 policy engine
5. Phase 5 backend enforcement migration
6. Phase 7 rollout validation

## Phase 0: Preflight Stabilization and Scope Inventory

**Assigned Subagent(s)**: `backend-architect`, `python-backend-engineer`, `frontend-developer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-090 | Integrations Baseline Repair | Validate the current partial request-context migration in `backend/routers/integrations.py`, repair any remaining code/test drift, and confirm helper boundaries before auth enforcement is layered on top. | Integrations router code and tests agree on current helper/module boundaries, and the touched request-scoped integration flows are green again. | 2 pts | python-backend-engineer | None |
| AUTH-091 | Backend Enforcement Surface Inventory | Enumerate routers/services still relying on active-project globals or direct singleton/path access, including project selection, GitHub integration helpers, file-backed routers, and remaining SkillMeat edges; classify them by sensitivity and map them onto the RBAC/resource model. | The plan has an explicit migration inventory for high-risk router/helper surfaces instead of a partial hot-path list, and the inventory reflects the current `RequestContext`/scope baseline. | 2 pts | backend-architect | None |
| AUTH-092 | Frontend Transport Inventory and Migration Strategy | Inventory direct `fetch()` callers that will need auth/session-aware behavior and define the shared transport abstraction plus migration order for protected surfaces. | Frontend auth work is no longer limited to `services/apiClient.ts`; protected request paths have an explicit migration strategy. | 2 pts | frontend-developer | None |

**Phase 0 Task Status**

1. AUTH-091 inventory captured on 2026-05-02 against the current backend router/service baseline; downstream enforcement work remains in Phase 5 and must not be treated as complete.

### AUTH-091 Backend Enforcement Surface Inventory

Sensitivity key: `critical` can mutate credentials, repository state, execution state, or cross-tenant project selection; `high` can trigger privileged processing, write records, or expose broad project data; `medium` is project-scoped read or diagnostics that still needs tenancy enforcement.

| Surface | Current direct access / active-project dependency | Sensitivity | Proposed RBAC resource/action | Migration priority |
|---------|---------------------------------------------------|-------------|-------------------------------|--------------------|
| `backend/routers/projects.py` | Uses `core_ports.workspace_registry` but still exposes process-global active project selection through `GET /active`, `GET /active/paths`, and `POST /active/{project_id}`. | critical | `project:list`, `project:read`, `project:create`, `project:update`, `project:switch` scoped under user/team/enterprise workspace bindings. | P0: replace global active-project mutation with request-scoped workspace/project selection before hosted rollout. |
| `backend/routers/integrations.py` SkillMeat routes and `backend/application/services/integrations.py` | SkillMeat routes now resolve `RequestContext`, but config validation still has standalone helper behavior; sync, refresh, observation backfill, memory draft generate/review/publish mutate integration-derived state and call external SkillMeat. | critical | `integration.skillmeat:read`, `integration.skillmeat:sync`, `integration.skillmeat:backfill`, `integration.skillmeat.memory:generate`, `integration.skillmeat.memory:review`, `integration.skillmeat.memory:publish`. | P0/P1: enforce service-layer checks on sync/backfill/publish first, then read checks on definitions/observations/drafts. |
| GitHub integration helpers: `backend/routers/integrations.py`, `backend/services/integrations/github_settings_store.py`, `backend/services/repo_workspaces/*` | GitHub settings are file-backed global state; helpers read/write token/cache settings, clone/fetch workspaces under configured cache roots, and validate write capability without request-scoped tenancy. | critical | `integration.github:read_settings`, `integration.github:update_settings`, `integration.github:validate`, `integration.github.workspace:refresh`, `integration.github:write_probe`. | P0: move settings and workspace cache ownership under enterprise/team scope before enabling hosted admin access. |
| `backend/routers/execution.py` and `backend/application/services/execution.py` | Router uses `RequestContext`, but run creation, approval, cancel, retry, launch prepare/start, and worktree context create/update require named authorization; launch paths can affect local worktrees and execution state. | critical | `execution:read`, `execution.run:create`, `execution.run:approve`, `execution.run:cancel`, `execution.run:retry`, `execution.launch:prepare`, `execution.launch:start`, `worktree_context:create`, `worktree_context:update`. | P0/P1: enforce approve/start/create before read-only history; keep checks in application service as well as route dependency. |
| `backend/routers/live.py` and live topic helpers | Already calls `authorization_policy.authorize` per normalized topic, but `topic_authorization()` maps generic topic prefixes and only includes project id from context when present. | high | `live:subscribe` with resource-specific aliases: `live.execution:subscribe`, `live.session:subscribe`, `live.feature:subscribe`, `live.project:subscribe`. | P1: tighten topic-to-resource mapping and require project/session ownership before replay or subscription. |
| Features and planning: `backend/routers/features.py`, `backend/routers/client_v1.py`, `backend/routers/_client_v1_features.py`, `backend/routers/planning.py` | Client V1 feature surfaces mostly resolve `RequestContext`; `POST /api/client/v1/features/rollups`, `POST /api/client/v1/reports/aar`, and `PATCH /api/planning/features/{feature_id}/open-questions/{oq_id}` trigger compute/writeback or pending sync. | high | `feature:read`, `feature.rollup:compute`, `report.aar:generate`, `planning.open_question:resolve`, `document:read`, `task:read`. | P1: guard planning writeback and report/rollup compute; apply read checks to feature modal/document/session projections. |
| Analytics exports and mutations: `backend/routers/analytics.py` | Uses `RequestContext` plus `resolve_project`, but alert create/update/delete, notification reads, workflow analytics, and Prometheus export expose or mutate project-wide telemetry. | high | `analytics:read`, `analytics.export:prometheus`, `analytics.alert:create`, `analytics.alert:update`, `analytics.alert:delete`, `analytics.notification:read`. | P1: protect alert mutations and exports first; read dashboards can follow with scoped project checks. |
| `backend/routers/codebase.py` and `backend/services/codebase_explorer.py` | Directly imports `project_manager`, resolves active project and filesystem root, and serves tree, file lists, file content, and file details. | high | `codebase:read_tree`, `codebase:file_read`, `codebase:activity_read`. | P0/P1: migrate off direct singleton and enforce project path ownership before serving file content. |
| Cache, links, and maintenance: `backend/routers/cache.py` | Uses app-state `sync_engine` plus active project from workspace registry; sync/rescan/rebuild/sync-paths can scan local paths; manual link creation writes entity links. | critical | `cache:read_status`, `cache.operation:read`, `cache.sync:trigger`, `cache.links:rebuild`, `cache.paths:sync`, `entity_link:create`, `link_audit:run`. | P0: enforce trigger/rebuild/sync-paths and manual link creation; then scope read operations and operation history. |
| `backend/routers/session_mappings.py` | Directly imports `project_manager`, reads active project, and persists project-specific session mapping rules through global active state. | high | `session_mapping:read`, `session_mapping:diagnose`, `session_mapping:update`. | P0/P1: migrate to request-scoped project and require update permission for mapping writes. |
| `backend/routers/test_visualizer.py` | Direct `project_manager` lookup and fallback project construction; sync, ingest, import mappings, and mapping backfill use app-state sync engine / DB repositories and can write large test datasets. | high | `test:read`, `test.sync:trigger`, `test.run:ingest`, `test.mapping:import`, `test.mapping:backfill`, `test.metrics:read`. | P1: enforce ingest/import/backfill/sync first; then protect metrics, run details, and health reads by project. |
| Pricing/admin: `backend/routers/pricing.py` | Pricing catalog is global DB state; router imports `project_manager` but mutations do not currently bind to request context or admin authorization. | critical | `admin.pricing:read`, `admin.pricing:update`, `admin.pricing:sync`, `admin.pricing:reset`, `admin.pricing:delete`. | P0: admin-only guard all catalog mutations and remove unused active-project coupling. |
| Documents/task mutation paths | `backend/application/services/documents.py` is read-oriented, but planning open-question resolution, entity-link creation, feature rollup compute, and document/task metadata projections touch document/task-derived state. No standalone document write router is visible in this baseline. | high | `document:read`, `document.link:create`, `task:read`, `planning.task:update`, `planning.open_question:resolve`. | P1: guard existing mutation paths; revisit if a dedicated document/task write router is added. |

**Phase 0 Quality Gates**

1. Integrations/request-scope drift is reduced enough that auth work starts from a stable baseline.
2. AUTH-090 and AUTH-091 are complete before Phase 1 hosted provider design or Phase 2 provider implementation begins.
3. The backend enforcement inventory covers singleton-dependent routes beyond `projects.py`, including GitHub integration helpers and file/path-oriented operational endpoints.
4. The frontend transport plan explicitly accounts for protected direct `fetch()` callers.

## Phase 1: Identity Contracts, Provider Abstraction, and Configuration

**Assigned Subagent(s)**: `backend-architect`, `security-engineering`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-001 | Principal Contract Refinement | Refine the existing application identity model for hosted issuer/provider metadata, subject normalization, auth mode, and service-account identity while preserving the already-present email, groups, and hierarchical memberships fields. | `Principal` and related request-context contracts can represent local operators plus hosted users resolved through Local, Clerk, or generic OIDC providers without duplicating existing identity fields. | 3 pts | backend-architect, python-backend-engineer | AUTH-090, AUTH-091 |
| AUTH-002 | Permission Vocabulary and Resource Matrix | Define the canonical resource/action matrix for projects, documents, sessions, tests, execution, integrations, analytics, admin settings, codebase access, and file-backed maintenance endpoints. | The plan has a documented role-resource matrix that can be implemented without reopening product questions. | 3 pts | security-engineering, backend-architect | AUTH-001, AUTH-091 |
| AUTH-003 | Hosted Auth Configuration Surface | Define environment/config settings for provider selection, Clerk keys/endpoints, generic issuer URL, audience/client IDs, callback URL, secure cookies, trusted proxy expectations, and explicit local-mode enablement on top of the existing runtime-profile auth capability composition. | Hosted and local runtime configuration is explicit, fail-closed, and documented for composition code across StaticBearer/local, Clerk, and generic OIDC modes. | 2 pts | backend-architect, security-engineering | AUTH-001 |
| AUTH-004 | Subject Hierarchy and Ownership Model | Define the authoritative `user`, `team`, and `enterprise` scope model, including how workspace/project bindings inherit from or attach to those tiers. | The plan has an explicit three-tier ownership and binding model aligned with SkillMeat's AAA direction and usable for repository/service enforcement. | 2 pts | backend-architect, security-engineering | AUTH-001, AUTH-091 |

**Phase 1 Task Status**

1. AUTH-002 matrix drafted on 2026-05-02 from the AUTH-091 inventory. Treat this as the canonical V1 permission vocabulary for implementation planning, pending AUTH-001 principal-contract finalization; do not mark Phase 1 complete from this note alone.

### AUTH-002 Canonical V1 Resource/Action Matrix

Role key: `LO` local operator, `EA` enterprise admin, `TA` team admin, `PM` project maintainer, `PV` project viewer, `IO` integration operator, `XA` execution approver, `AA` analyst/auditor. Grants are scoped by the subject binding: enterprise grants may flow to teams/projects inside that enterprise, team grants may flow to bound workspaces/projects, and project grants apply only to the named project unless AUTH-004 narrows inheritance.

| Resource group | Canonical V1 actions | AUTH-091 inventory mapping | Default role grants |
|----------------|----------------------|----------------------------|---------------------|
| Projects | `project:list`, `project:read`, `project:create`, `project:update`, `project:switch` | `backend/routers/projects.py` active project and workspace selection | `LO` all in local mode; `EA` all enterprise projects; `TA` all team projects; `PM` read/update/switch bound projects; `PV`, `AA` list/read/switch bound projects |
| Documents | `document:read`, `document.link:create`, `document.metadata:read` | document projections, entity-link creation, feature/document detail surfaces | `LO`, `EA`, `TA`, `PM` all; `PV`, `AA` read/metadata only |
| Tasks | `task:read`, `planning.task:update` | task projections and planning-derived task updates | `LO`, `EA`, `TA`, `PM` all; `PV`, `AA` read only |
| Sessions | `session:read`, `session.artifact:read`, `session.timeline:read` | feature/session projections, live session views, AAR/report inputs | `LO`, `EA`, `TA`, `PM` all; `PV`, `AA` read only |
| Tests | `test:read`, `test.metrics:read`, `test.sync:trigger`, `test.run:ingest`, `test.mapping:import`, `test.mapping:backfill` | `backend/routers/test_visualizer.py` read, sync, ingest, import, and backfill paths | `LO`, `EA`, `TA`, `PM` all; `AA` read/metrics; `PV` read only |
| Execution | `execution:read`, `execution.run:create`, `execution.run:approve`, `execution.run:cancel`, `execution.run:retry`, `execution.launch:prepare`, `execution.launch:start`, `worktree_context:create`, `worktree_context:update` | `backend/routers/execution.py` run, approval, retry/cancel, launch, and worktree-context paths | `LO`, `EA` all; `TA`, `PM` read/create/cancel/retry/prepare and worktree context on bound projects; `XA` approve/start plus read; `AA` read only |
| Integrations | `integration:read`, `integration.skillmeat:sync`, `integration.skillmeat:backfill`, `integration.skillmeat.memory:generate`, `integration.skillmeat.memory:review`, `integration.skillmeat.memory:publish`, `integration.github:read_settings`, `integration.github:update_settings`, `integration.github:validate`, `integration.github.workspace:refresh`, `integration.github:write_probe` | SkillMeat routes, integration service helpers, GitHub settings store, repo workspace cache helpers | `LO`, `EA` all; `TA` read plus team-scoped settings/update/validate; `IO` all integration actions on assigned scopes; `PM` read and workspace refresh on bound projects |
| Analytics | `analytics:read`, `analytics.export:prometheus`, `analytics.alert:create`, `analytics.alert:update`, `analytics.alert:delete`, `analytics.notification:read` | `backend/routers/analytics.py` dashboards, exports, alerts, and notifications | `LO`, `EA`, `TA` all; `PM` read/notifications and project alerts; `AA` read/export/notifications; `PV` read only |
| Admin settings | `admin.settings:read`, `admin.settings:update`, `admin.user:manage`, `admin.role:manage`, `admin.audit:read` | hosted auth setup, bootstrap/admin assignment, audit and operator settings surfaces | `LO` all in local mode; `EA` all; `TA` team-scoped read/user/role management; `AA` audit/read only |
| Codebase access | `codebase:read_tree`, `codebase:file_read`, `codebase:activity_read` | `backend/routers/codebase.py` tree, file content, details, and activity | `LO`, `EA`, `TA`, `PM` all on bound projects; `PV`, `AA` tree/activity only unless explicitly granted file read |
| Cache and file-backed maintenance | `cache:read_status`, `cache.operation:read`, `cache.sync:trigger`, `cache.links:rebuild`, `cache.paths:sync`, `entity_link:create`, `link_audit:run` | `backend/routers/cache.py`, file-backed project/cache/link maintenance paths | `LO`, `EA` all; `TA`, `PM` bound project maintenance except cross-project path sync; `AA` status/operation/link audit read |
| Live topics | `live:subscribe`, `live.execution:subscribe`, `live.session:subscribe`, `live.feature:subscribe`, `live.project:subscribe` | `backend/routers/live.py` topic authorization and replay/subscription helpers | Any role with the matching underlying resource read may subscribe to that topic; execution live topics additionally require `execution:read` |
| Session mappings | `session_mapping:read`, `session_mapping:diagnose`, `session_mapping:update` | `backend/routers/session_mappings.py` active-project mapping reads, diagnosis, and writes | `LO`, `EA`, `TA`, `PM` all on bound projects; `PV`, `AA` read/diagnose only |
| Pricing/admin catalog | `admin.pricing:read`, `admin.pricing:update`, `admin.pricing:sync`, `admin.pricing:reset`, `admin.pricing:delete` | `backend/routers/pricing.py` global pricing catalog reads and mutations | `LO`, `EA` all; `AA` read only |
| Planning/writeback | `feature:read`, `feature.rollup:compute`, `report.aar:generate`, `planning.open_question:resolve`, `planning.writeback:sync` | features/client V1 rollups, AAR reports, planning open-question resolution, planning pending sync/writeback | `LO`, `EA`, `TA`, `PM` all on bound projects; `PV`, `AA` read/report generation only unless granted writeback |

Implementation rules:

1. Permission names are stable API identifiers; router/service code should reference these exact strings through constants, not invent route-local aliases.
2. Local no-auth mode maps to `LO` through the existing permissive runtime profile only; hosted mode must never infer `LO` from missing identity.
3. `EA` is the hosted break-glass/admin role for enterprise scope. `TA` can delegate within its team scope but cannot mutate enterprise-wide provider, pricing, or cross-team integration settings.
4. `PM` owns project operations but not enterprise/team administration. `PV` is read-only except for project switching to bound projects.
5. `IO`, `XA`, and `AA` are purpose-built roles that may be combined with viewer/maintainer roles; they do not grant broad project write access by themselves.
6. Denials for write/admin/execute actions must be audited with principal, resource, action, requested scope, and denial reason.

**Phase 1 Quality Gates**

1. Local and hosted principal shapes are both covered by the same request context.
2. The provider model explicitly supports Local, Clerk, and generic OIDC modes through one contract.
3. Every sensitive V1 action maps to a named permission across user/team/enterprise tiers.
4. Hosted mode cannot start in an ambiguous partially configured auth state.
5. Existing `RequestContext` scope objects and identity/audit repository ports are reused rather than replaced.

## Phase 2: Auth Provider Adapters and Hosted Session Flow

**Assigned Subagent(s)**: `python-backend-engineer`, `backend-architect`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-101 | Provider Registry and Generic OIDC Validation | Implement the provider registry/factory plus generic issuer discovery, JWKS refresh, token verification, and claim validation behind the shared auth-provider abstraction. | Hosted requests fail closed when provider metadata, signature, audience, or nonce/state validation fails; provider selection is configuration-driven. | 4 pts | python-backend-engineer, security-engineering | AUTH-003, AUTH-004 |
| AUTH-102 | Clerk and Browser Session Flow | Add Clerk as a first-class built-in provider and implement browser login start, callback, logout, and session introspection flows that can be reused across hosted providers. | A browser user can sign in through Clerk or a generic hosted provider, obtain a server-managed hosted session, refresh the app, and sign out cleanly. | 5 pts | python-backend-engineer | AUTH-101 |
| AUTH-103 | Runtime Composition for Hosted Auth | Update runtime composition so `api` profile can use the selected hosted identity/authorization adapters while `local` and `test` keep the existing permissive adapters. | `backend/runtime_ports.py` and hosted bootstrap paths compose the correct adapters by profile and configuration. | 3 pts | backend-architect | AUTH-101, AUTH-102 |

**Phase 2 Quality Gates**

1. Hosted auth is provider-agnostic at the application boundary while still supporting Clerk as a first-class built-in option.
2. Local runtime behavior remains unchanged when hosted auth is disabled.
3. Hosted session transport uses secure cookies or equivalent server-managed state, not long-lived browser secrets.

## Phase 3: Authorization Policy and 3-Tier RBAC Matrix

**Assigned Subagent(s)**: `backend-architect`, `security-engineering`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-201 | Role Binding Evaluator | Implement the role-to-permission expansion and scope matching logic for user, team, enterprise, workspace, and project bindings. | The policy layer can answer allow/deny for named actions using principal bindings and requested scope. | 4 pts | backend-architect, python-backend-engineer | AUTH-002, AUTH-004, AUTH-101 |
| AUTH-202 | Authorization Helper API | Add reusable helpers for service-layer authorization, denial reasons, and consistent 401 vs 403 behavior. | Services and routers can enforce permissions through one shared API instead of bespoke checks. | 3 pts | python-backend-engineer | AUTH-201 |
| AUTH-203 | Role Matrix Artifact and Operator Defaults | Finalize the initial tier-aware roles and bindings for enterprise, team, and user scopes, and define bootstrap/admin assignment rules. | Default roles are documented, consistent, and usable for operator setup without lockout ambiguity. | 3 pts | security-engineering, backend-architect | AUTH-201 |
| AUTH-204 | Hierarchical Scope Inheritance Rules | Define how enterprise-level, team-level, user-level, workspace-level, and project-level grants compose, override, or narrow access. | Inheritance and conflict resolution rules are explicit, testable, and consistent with SkillMeat's AAA direction. | 2 pts | backend-architect, security-engineering | AUTH-201 |

**Phase 3 Quality Gates**

1. Authorization decisions are deny-capable and explainable.
2. 401 and 403 responses are consistent across hosted endpoints.
3. The role matrix covers approvals and integrations separately from generic edit access.
4. User/team/enterprise inheritance rules are explicit enough to implement without reopening the model mid-build.

## Phase 4: Scope Mapping and SkillMeat Trust Alignment

**Assigned Subagent(s)**: `backend-architect`, `integrations`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-301 | Claim-to-Scope Mapping | Define how provider claims, groups, organizations, and workspace/project identifiers map into CCDash enterprise/team/workspace/project scopes. | Hosted principals resolve to deterministic enterprise/team/workspace/project scope without relying on global process state. | 4 pts | backend-architect, security-engineering | AUTH-201, AUTH-204, AUTH-091 |
| AUTH-302 | SkillMeat Trust Contract | Align outbound SkillMeat integration auth with the shared provider/delegation model and remove the need for a separate hosted-only credential story. | Hosted CCDash can call SkillMeat under the shared trust model or a documented delegated token path across Clerk or generic OIDC deployments. | 3 pts | integrations, security-engineering | AUTH-101, AUTH-301, AUTH-090 |
| AUTH-303 | Workspace Registry and Project Selection Semantics | Refine workspace registry behavior so active project selection, project lookup, and scope resolution are compatible with hosted multi-user usage under enterprise/team/user context. | Hosted request scope no longer depends on a single global active-project assumption. | 3 pts | backend-architect | AUTH-301 |

**Phase 4 Quality Gates**

1. Claims map cleanly into CCDash and SkillMeat scope identifiers across Local, Clerk, and generic OIDC modes.
2. Hosted requests do not inherit another user’s active-project state.
3. Service-to-service integration auth uses the shared trust contract.
4. User/team/enterprise context resolves consistently before workspace/project access is evaluated.

## Phase 5: Backend Enforcement Migration

**Assigned Subagent(s)**: `python-backend-engineer`, `backend-architect`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-401 | Workspace and Singleton Router Migration | Refactor `backend/routers/projects.py` plus the inventory-defined singleton-dependent router paths onto request context and workspace registry semantics. | High-risk router flows no longer depend on process-global active project selection in hosted mode and instead respect enterprise/team/user context. | 4 pts | python-backend-engineer, backend-architect | AUTH-202, AUTH-303, AUTH-091 |
| AUTH-402 | Sensitive Route Authorization Coverage | Apply authorization checks to execution, integrations, live topics, document/task mutation endpoints, analytics exports, admin settings, codebase access, cache/maintenance operations, and other inventory-classified protected surfaces. | All sensitive write/admin/execute paths require named permissions and produce audited denials. | 5 pts | python-backend-engineer, security-engineering | AUTH-202, AUTH-091 |
| AUTH-403 | Service-Layer Guard Rails | Add architecture tests or guardrails that prevent new hot-path routers from bypassing request context and authorization helpers. | New endpoints in covered areas cannot regress to direct router-level singleton or unchecked writes. | 2 pts | backend-architect | AUTH-401, AUTH-402 |

**Phase 5 Quality Gates**

1. Sensitive hosted endpoints enforce named permissions end to end.
2. Inventory-defined singleton-dependent routers no longer behave as process-global tenant selectors in hosted mode.
3. Authorization is enforced in reusable service or dependency seams, not repeated inline across every route.

## Phase 6: Frontend Session UX and Protected Shell

**Assigned Subagent(s)**: `frontend-developer`, `ui-engineer-enhanced`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-501 | Auth-Aware Client and Session Context | Add a frontend auth/session context, `/api/auth/session` integration, provider metadata, and shared 401/403 handling in the canonical request client/wrapper. | The UI can distinguish loading, authenticated, unauthenticated, unauthorized, provider, and tier context states without breaking local mode. | 4 pts | frontend-developer | AUTH-092, AUTH-102, AUTH-202 |
| AUTH-502 | Protected Request Transport Migration | Move inventory-defined protected request paths off ad hoc `fetch()` calls and onto the shared auth-aware transport, starting with execution, feature detail/modals, integrations, analytics mutation paths, and operational panels. | Protected frontend surfaces consistently inherit auth/session semantics instead of reimplementing them locally. | 3 pts | frontend-developer | AUTH-501 |
| AUTH-503 | Hosted Sign-In/Sign-Out and Protected Shell | Add hosted sign-in/out flows, session-aware app shell behavior, and clear local-vs-hosted runtime messaging. | Hosted users can sign in/out cleanly; local users still enter the app without auth friction and with explicit runtime labeling. | 3 pts | ui-engineer-enhanced, frontend-developer | AUTH-501 |
| AUTH-504 | Permission-Aware Workspace UX | Update enterprise/team/workspace/project selection and sensitive UI affordances so they reflect backend permissions without relying on UI-only protection. | UI hides or disables protected actions appropriately, but the backend remains the source of truth. | 2 pts | frontend-developer | AUTH-301, AUTH-502 |

**Phase 6 Quality Gates**

1. UI session state is separate from project data-loading state.
2. Local runtime remains deliberate and obvious in the shell.
3. Hosted 401/403 flows do not strand the app in infinite refresh or blank-screen states.
4. Protected request paths do not bypass the shared auth-aware transport.
5. Enterprise/team/user context is visible and switchable where appropriate without becoming the source of truth for authorization.

## Phase 7: Audit, Testing, and Rollout Hardening

**Assigned Subagent(s)**: `security-engineering`, `frontend-developer`, `python-backend-engineer`, `documentation-writer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-601 | Audit Attribution and Auth Observability | Record principal attribution for privileged actions and add metrics/logging for login failures, denied actions, token/session errors, and issuer health. | Operators can identify who performed sensitive actions and diagnose auth failures in hosted mode. | 3 pts | security-engineering, python-backend-engineer | AUTH-402 |
| AUTH-602 | Validation Suite | Add backend unit/integration tests plus frontend interaction coverage for login, denial, local mode, protected action scenarios, and migrated transport behavior. | Critical auth journeys are covered in automated tests across local and hosted profiles. | 4 pts | python-backend-engineer, frontend-developer | AUTH-402, AUTH-504 |
| AUTH-603 | Rollout and Operator Documentation | Document issuer setup, runtime flags, local-mode behavior, bootstrap admin rules, and staged rollout guidance. | Operators can configure hosted auth safely and developers can still run explicit local no-auth mode. | 2 pts | documentation-writer | AUTH-601, AUTH-602 |

**Phase 7 Quality Gates**

1. Auth failures, denials, and session health are observable.
2. Automated tests cover both hosted and local runtime behavior.
3. Rollout is staged, reversible, and documented well enough for operators to avoid accidental exposure.

## Validation Matrix

1. Local profile:
   - starts without hosted auth configuration
   - returns local principal and permissive authorization
   - preserves current project and developer workflows
2. Hosted API profile:
   - rejects unauthenticated requests to protected actions
   - resolves authenticated principals from the configured provider (`Local`, `Clerk`, or generic `OIDC`)
   - enforces role/resource permissions consistently
3. Hierarchical RBAC:
   - user, team, and enterprise bindings resolve consistently
   - workspace/project access composes under the active higher-tier context
4. Cross-app trust:
   - CCDash and SkillMeat accept the same provider/issuer assumptions
   - workspace/project identifiers map consistently across both apps
5. Audit and observability:
   - privileged actions capture subject attribution
   - denial/failure metrics are queryable
6. Preflight stabilization:
   - integration-router baseline tests are green for the touched request-scoped paths
   - protected frontend request paths use the shared auth-aware transport

## Major Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hosted auth is layered onto routers while singleton workspace state remains underneath | High | Medium | Make `projects` and scope resolution part of the enforcement migration, not a follow-up |
| Role model is too coarse for approvals and integrations | High | Medium | Finalize the role-resource matrix in Phase 1 and validate against real sensitive workflows in Phase 5 |
| Local users are accidentally forced into hosted assumptions | High | Medium | Keep adapter selection in runtime composition and test local profile explicitly in Phase 7 |
| SkillMeat and CCDash workspace identifiers drift | High | Medium | Treat claim mapping and SkillMeat trust alignment as one planned phase with shared acceptance gates |
| Provider-specific claim models drift between Clerk and generic OIDC | High | Medium | Normalize claims through one provider abstraction and make provider-specific mapping rules explicit in Phase 4 |
| Frontend protected flows keep bypassing the shared auth-aware transport | High | Medium | Inventory direct `fetch()` callers up front and make transport migration an explicit Phase 6 task |
| Auth work lands on top of unstable integration/request-scope seams | Medium | Medium | Add a preflight stabilization phase and require green targeted tests before Phase 1 begins |

## Definition of Done

1. Hosted CCDash authenticates users through a modular provider system that supports Clerk and generic OIDC, while preserving explicit local no-auth mode.
2. Request-scoped principals and scopes are resolved through runtime composition rather than globals.
3. Sensitive write, execute, integration, and admin paths enforce named permissions with audited attribution across user/team/enterprise tiers.
4. Workspace/project access composes correctly under the higher-tier authorization model and shared SkillMeat trust contract.
5. Frontend session handling is auth-aware, but backend authorization remains the source of truth.
