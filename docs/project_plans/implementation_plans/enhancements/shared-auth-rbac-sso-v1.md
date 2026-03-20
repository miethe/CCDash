---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements
title: "Implementation Plan: Shared Auth, RBAC, and SSO V1"
description: "Implement shared OIDC sign-in, workspace-scoped RBAC, and SkillMeat trust alignment while preserving an explicit local no-auth runtime."
summary: "Deliver shared auth through identity contracts, hosted OIDC adapters, authorization policy enforcement, workspace mapping, frontend session UX, and rollout hardening."
author: codex
owner: platform-engineering
owners: [platform-engineering, security-engineering, fullstack-engineering]
contributors: [ai-agents]
audience: [ai-agents, developers, platform-engineering, security-engineering]
created: 2026-03-20
updated: 2026-03-20
tags: [implementation, auth, oidc, rbac, sso, security, skillmeat]
priority: critical
risk_level: high
complexity: high
track: Identity
timeline_estimate: "4-6 weeks across 7 phases"
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

Introduce a hosted-safe identity and authorization layer for CCDash using OIDC, workspace/project-scoped RBAC, and a shared trust contract with SkillMeat while preserving the explicit local no-auth runtime profile already present in the codebase.

## Current Baseline

1. The hexagonal foundation work already introduced `RequestContext`, `Principal`, runtime profiles, and pluggable core ports.
2. `backend/adapters/auth/local.py` provides a permissive local adapter, but there is no hosted identity adapter, no token/session verification path, and no deny-capable authorization policy.
3. `backend/runtime/container.py` already builds request context per request, which is the correct seam for hosted auth.
4. Several routers and application services accept `RequestContext`, but most business flows still behave as if every caller is the same trusted local operator.
5. `backend/routers/projects.py` still uses the global `project_manager` singleton directly, which is incompatible with real request-scoped tenancy.
6. `contexts/AppSessionContext.tsx` models project switching only; there is no frontend auth/session state or 401/403 handling path.
7. `services/apiClient.ts` performs plain `fetch()` calls with no auth/session-aware retry or denial semantics.

## Fixed Decisions

1. Local desktop and test workflows keep an explicit no-auth adapter and must not silently inherit hosted auth requirements.
2. Hosted sign-in uses Authorization Code + PKCE with an external OIDC issuer; CCDash and SkillMeat share issuer trust, not browser cookies.
3. Principal resolution and authorization decisions live at backend request/service boundaries, not in the UI.
4. V1 uses a resource-action RBAC matrix rather than a generic policy language.
5. Sensitive write, admin, approval, and integration actions must be enforced in services or request dependencies, not only in router copy or frontend gates.
6. Hosted service-to-service SkillMeat calls must reuse the shared trust model or delegated credentials, not a separate ad hoc API-key path.

## Proposed Module Targets

Backend:

1. `backend/adapters/auth/oidc.py`
2. `backend/adapters/auth/session_state.py`
3. `backend/adapters/auth/claims_mapping.py`
4. `backend/application/services/authentication.py`
5. `backend/application/services/authorization.py`
6. `backend/routers/auth.py`
7. `backend/runtime_ports.py`
8. `backend/runtime/bootstrap_api.py`
9. request-context-aware updates in `backend/routers/projects.py`, `backend/routers/integrations.py`, `backend/routers/execution.py`, `backend/routers/live.py`, and hot-path endpoints in `backend/routers/api.py`

Frontend:

1. `services/auth.ts`
2. `contexts/AppAuthContext.tsx`
3. `contexts/AppSessionContext.tsx`
4. `services/apiClient.ts`
5. app-shell entry points and protected-route handling around existing runtime/data providers

Exact paths may shift, but the end state must keep issuer integration, session transport, authorization logic, and UI session state separated.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Identity Contracts and Configuration | 8 pts | 3-4 days | Yes | Finalize the principal, role, resource, and runtime config model for hosted auth |
| 2 | OIDC Adapter and Hosted Session Flow | 11 pts | 4-5 days | Yes | Add issuer validation, login/callback/logout flow, and secure hosted session handling |
| 3 | Authorization Policy and RBAC Matrix | 10 pts | 4 days | Yes | Implement a deny-capable policy layer and canonical permission vocabulary |
| 4 | Workspace Mapping and SkillMeat Trust Alignment | 8 pts | 3-4 days | Partial | Map issuer claims to CCDash scopes and align outbound SkillMeat auth |
| 5 | Backend Enforcement Migration | 11 pts | 4-5 days | Yes | Move sensitive routes and services onto real authorization checks |
| 6 | Frontend Session UX and Protected Shell | 9 pts | 4 days | Partial | Add auth-aware client/session UX without regressing local mode |
| 7 | Audit, Testing, and Rollout Hardening | 9 pts | 3-4 days | Final gate | Add attribution, observability, operator docs, and staged rollout safety |

**Total**: ~66 story points over 4-6 weeks

## Implementation Strategy

### Sequencing Rationale

1. Lock the identity and permission vocabulary before implementing provider-specific auth logic.
2. Land hosted OIDC session handling before migrating route enforcement so the policy layer has real principals to evaluate.
3. Define the RBAC matrix before broad router migration to avoid duplicating authorization rules in many endpoints.
4. Align workspace/project claim mapping before wiring SkillMeat trust and before finalizing frontend workspace UX.
5. Keep local no-auth behavior working throughout by using runtime-profile composition instead of conditionals spread through routers.

### Parallel Work Opportunities

1. Once Phase 1 contracts are stable, Phase 2 backend OIDC work and Phase 3 policy-matrix drafting can run in parallel.
2. Phase 4 claim-mapping work can overlap with the latter half of Phase 6 once `/api/auth/session` and role payload shapes are stable.
3. Documentation, operator setup, and audit dashboard work can begin during Phase 6 after enforcement coverage is clear.

### Critical Path

1. Phase 1 contracts
2. Phase 2 hosted session flow
3. Phase 3 policy engine
4. Phase 5 backend enforcement migration
5. Phase 7 rollout validation

## Phase 1: Identity Contracts and Configuration

**Assigned Subagent(s)**: `backend-architect`, `security-engineering`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-001 | Principal Contract Refinement | Extend the existing application identity model to cover issuer, subject, email, groups, role bindings, auth mode, and service-account identity without breaking local mode. | `Principal` and related request-context contracts can represent both hosted OIDC users and local operators. | 3 pts | backend-architect, python-backend-engineer | None |
| AUTH-002 | Permission Vocabulary and Resource Matrix | Define the canonical resource/action matrix for projects, documents, sessions, tests, execution, integrations, analytics, and admin settings. | The plan has a documented role-resource matrix that can be implemented without reopening product questions. | 3 pts | security-engineering, backend-architect | AUTH-001 |
| AUTH-003 | Hosted Auth Configuration Surface | Define environment/config settings for issuer URL, audience/client IDs, callback URL, secure cookies, trusted proxy expectations, and explicit local-mode enablement. | Hosted and local runtime configuration is explicit, fail-closed, and documented for composition code. | 2 pts | backend-architect, security-engineering | AUTH-001 |

**Phase 1 Quality Gates**

1. Local and hosted principal shapes are both covered by the same request context.
2. Every sensitive V1 action maps to a named permission.
3. Hosted mode cannot start in an ambiguous partially configured auth state.

## Phase 2: OIDC Adapter and Hosted Session Flow

**Assigned Subagent(s)**: `python-backend-engineer`, `backend-architect`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-101 | OIDC Discovery and JWKS Validation | Implement provider-agnostic issuer discovery, JWKS refresh, token verification, and claim validation behind an auth adapter. | Hosted requests fail closed when issuer metadata, signature, audience, or nonce/state validation fails. | 4 pts | python-backend-engineer, security-engineering | AUTH-003 |
| AUTH-102 | Browser Login and Callback Flow | Add login start, callback, logout, and session introspection endpoints using Authorization Code + PKCE. | A browser user can sign in, obtain a server-managed hosted session, refresh the app, and sign out cleanly. | 4 pts | python-backend-engineer | AUTH-101 |
| AUTH-103 | Runtime Composition for Hosted Auth | Update runtime composition so `api` profile can use the hosted identity/authorization adapters while `local` and `test` keep the existing permissive adapters. | `backend/runtime_ports.py` and hosted bootstrap paths compose the correct adapters by profile and configuration. | 3 pts | backend-architect | AUTH-101 |

**Phase 2 Quality Gates**

1. Hosted auth is provider-agnostic at the application boundary.
2. Local runtime behavior remains unchanged when hosted auth is disabled.
3. Hosted session transport uses secure cookies or equivalent server-managed state, not long-lived browser secrets.

## Phase 3: Authorization Policy and RBAC Matrix

**Assigned Subagent(s)**: `backend-architect`, `security-engineering`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-201 | Role Binding Evaluator | Implement the role-to-permission expansion and scope matching logic for workspace and project bindings. | The policy layer can answer allow/deny for named actions using principal bindings and requested scope. | 4 pts | backend-architect, python-backend-engineer | AUTH-002, AUTH-101 |
| AUTH-202 | Authorization Helper API | Add reusable helpers for service-layer authorization, denial reasons, and consistent 401 vs 403 behavior. | Services and routers can enforce permissions through one shared API instead of bespoke checks. | 3 pts | python-backend-engineer | AUTH-201 |
| AUTH-203 | Role Matrix Artifact and Operator Defaults | Finalize the initial roles (`platform_admin`, `workspace_admin`, `contributor`, `reviewer`, `viewer`) and define bootstrap/admin assignment rules. | Default roles are documented, consistent, and usable for operator setup without lockout ambiguity. | 3 pts | security-engineering, backend-architect | AUTH-201 |

**Phase 3 Quality Gates**

1. Authorization decisions are deny-capable and explainable.
2. 401 and 403 responses are consistent across hosted endpoints.
3. The role matrix covers approvals and integrations separately from generic edit access.

## Phase 4: Workspace Mapping and SkillMeat Trust Alignment

**Assigned Subagent(s)**: `backend-architect`, `integrations`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-301 | Claim-to-Scope Mapping | Define how issuer claims, groups, and workspace/project identifiers map into CCDash workspace and project scopes. | Hosted principals resolve to deterministic workspace/project scope without relying on global process state. | 3 pts | backend-architect, security-engineering | AUTH-201 |
| AUTH-302 | SkillMeat Trust Contract | Align outbound SkillMeat integration auth with the shared issuer/delegation model and remove the need for a separate hosted-only credential story. | Hosted CCDash can call SkillMeat under the shared trust model or a documented delegated token path. | 3 pts | integrations, security-engineering | AUTH-101, AUTH-301 |
| AUTH-303 | Workspace Registry and Project Selection Semantics | Refine workspace registry behavior so active project selection, project lookup, and scope resolution are compatible with hosted multi-user usage. | Hosted request scope no longer depends on a single global active-project assumption. | 2 pts | backend-architect | AUTH-301 |

**Phase 4 Quality Gates**

1. Claims map cleanly into CCDash and SkillMeat scope identifiers.
2. Hosted requests do not inherit another user’s active-project state.
3. Service-to-service integration auth uses the shared trust contract.

## Phase 5: Backend Enforcement Migration

**Assigned Subagent(s)**: `python-backend-engineer`, `backend-architect`, `security-engineering`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-401 | Projects and Workspace Router Migration | Refactor `backend/routers/projects.py` and related workspace flows to use request context and workspace registry instead of the global singleton path. | Project list, active project, and update flows are request-scoped and authorization-ready. | 4 pts | python-backend-engineer, backend-architect | AUTH-202, AUTH-303 |
| AUTH-402 | Sensitive Route Authorization Coverage | Apply authorization checks to execution, integrations, live topics, document/task mutation endpoints, analytics exports, and admin settings. | All sensitive write/admin/execute paths require named permissions and produce audited denials. | 5 pts | python-backend-engineer, security-engineering | AUTH-202 |
| AUTH-403 | Service-Layer Guard Rails | Add architecture tests or guardrails that prevent new hot-path routers from bypassing request context and authorization helpers. | New endpoints in covered areas cannot regress to direct router-level singleton or unchecked writes. | 2 pts | backend-architect | AUTH-401, AUTH-402 |

**Phase 5 Quality Gates**

1. Sensitive hosted endpoints enforce named permissions end to end.
2. `projects.py` no longer behaves as a process-global tenant selector in hosted mode.
3. Authorization is enforced in reusable service or dependency seams, not repeated inline across every route.

## Phase 6: Frontend Session UX and Protected Shell

**Assigned Subagent(s)**: `frontend-developer`, `ui-engineer-enhanced`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-501 | Auth-Aware Client and Session Context | Add a frontend auth/session context, `/api/auth/session` integration, and shared 401/403 handling in `services/apiClient.ts`. | The UI can distinguish loading, authenticated, unauthenticated, and unauthorized states without breaking local mode. | 4 pts | frontend-developer | AUTH-102, AUTH-202 |
| AUTH-502 | Hosted Sign-In/Sign-Out and Protected Shell | Add hosted sign-in/out flows, session-aware app shell behavior, and clear local-vs-hosted runtime messaging. | Hosted users can sign in/out cleanly; local users still enter the app without auth friction and with explicit runtime labeling. | 3 pts | ui-engineer-enhanced, frontend-developer | AUTH-501 |
| AUTH-503 | Permission-Aware Workspace UX | Update project/workspace selection and sensitive UI affordances so they reflect backend permissions without relying on UI-only protection. | UI hides or disables protected actions appropriately, but the backend remains the source of truth. | 2 pts | frontend-developer | AUTH-301, AUTH-501 |

**Phase 6 Quality Gates**

1. UI session state is separate from project data-loading state.
2. Local runtime remains deliberate and obvious in the shell.
3. Hosted 401/403 flows do not strand the app in infinite refresh or blank-screen states.

## Phase 7: Audit, Testing, and Rollout Hardening

**Assigned Subagent(s)**: `security-engineering`, `frontend-developer`, `python-backend-engineer`, `documentation-writer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| AUTH-601 | Audit Attribution and Auth Observability | Record principal attribution for privileged actions and add metrics/logging for login failures, denied actions, token/session errors, and issuer health. | Operators can identify who performed sensitive actions and diagnose auth failures in hosted mode. | 3 pts | security-engineering, python-backend-engineer | AUTH-402 |
| AUTH-602 | Validation Suite | Add backend unit/integration tests plus frontend interaction coverage for login, denial, local mode, and protected action scenarios. | Critical auth journeys are covered in automated tests across local and hosted profiles. | 4 pts | python-backend-engineer, frontend-developer | AUTH-402, AUTH-503 |
| AUTH-603 | Rollout and Operator Documentation | Document issuer setup, runtime flags, local-mode behavior, bootstrap admin rules, and staged rollout guidance. | Operators can configure hosted auth safely and developers can still run explicit local no-auth mode. | 2 pts | documentation-writer | AUTH-601, AUTH-602 |

**Phase 7 Quality Gates**

1. Auth failures, denials, and session health are observable.
2. Automated tests cover both hosted and local runtime behavior.
3. Rollout is staged, reversible, and documented well enough for operators to avoid accidental exposure.

## Validation Matrix

1. Local profile:
   - starts without OIDC configuration
   - returns local principal and permissive authorization
   - preserves current project and developer workflows
2. Hosted API profile:
   - rejects unauthenticated requests to protected actions
   - resolves authenticated principals from the configured issuer
   - enforces role/resource permissions consistently
3. Cross-app trust:
   - CCDash and SkillMeat accept the same issuer assumptions
   - workspace/project identifiers map consistently across both apps
4. Audit and observability:
   - privileged actions capture subject attribution
   - denial/failure metrics are queryable

## Major Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hosted auth is layered onto routers while singleton workspace state remains underneath | High | Medium | Make `projects` and scope resolution part of the enforcement migration, not a follow-up |
| Role model is too coarse for approvals and integrations | High | Medium | Finalize the role-resource matrix in Phase 1 and validate against real sensitive workflows in Phase 5 |
| Local users are accidentally forced into hosted assumptions | High | Medium | Keep adapter selection in runtime composition and test local profile explicitly in Phase 7 |
| SkillMeat and CCDash workspace identifiers drift | High | Medium | Treat claim mapping and SkillMeat trust alignment as one planned phase with shared acceptance gates |

## Definition of Done

1. Hosted CCDash authenticates users through an OIDC issuer that is also trusted by SkillMeat.
2. Request-scoped principals and scopes are resolved through runtime composition rather than globals.
3. Sensitive write, execute, integration, and admin paths enforce named permissions with audited attribution.
4. Local no-auth mode remains available through an explicit runtime profile and documented operator/developer setup.
5. Frontend session handling is auth-aware, but backend authorization remains the source of truth.
