---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: pending
category: enhancements
title: "PRD: Shared Auth, RBAC, and SSO V1"
description: "Add shared identity, role-based access control, and single sign-on across CCDash and SkillMeat using a common OIDC-based identity model."
summary: "Introduce provider-agnostic SSO and authorization for hosted/shared use while preserving a deliberate local no-auth mode."
created: 2026-03-11
updated: 2026-03-11
priority: critical
risk_level: high
complexity: High
track: Identity
timeline_estimate: "4-6 weeks after foundation refactor"
feature_slug: shared-auth-rbac-sso-v1
feature_family: shared-identity-access
feature_version: v1
lineage_family: shared-identity-access
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  kind: prerequisite
lineage_children: []
lineage_type: enhancement
problem_statement: "CCDash has no first-class user identity or authorization model today, which prevents secure multi-user hosting and shared sign-in with SkillMeat."
owner: platform-engineering
owners: [platform-engineering, security-engineering, fullstack-engineering]
contributors: [ai-agents]
audience: [developers, platform-engineering, engineering-leads]
tags: [prd, auth, rbac, sso, oidc, security, skillmeat]
related_documents:
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  - docs/project_plans/reports/agentic-sdlc-intelligence-v2-integration-overview-2026-03-08.md
  - docs/setup-user-guide.md
context_files:
  - backend/main.py
  - backend/routers/integrations.py
  - backend/services/integrations/skillmeat_client.py
  - backend/project_manager.py
  - contexts/DataContext.tsx
implementation_plan_ref: ""
---

# PRD: Shared Auth, RBAC, and SSO V1

## Executive Summary

CCDash currently assumes trusted local usage. That assumption breaks down as soon as the app is hosted for multiple users or expected to share authentication with SkillMeat. This PRD defines a provider-agnostic identity and authorization model based on OpenID Connect, workspace-scoped RBAC, and shared sign-in across both apps through a common issuer.

The target is not just “add login.” The target is a stable access model that can protect projects, execution controls, integration settings, and potentially sensitive session/test data without making local development painful.

## Current State

1. There is no authenticated principal in API requests.
2. Project selection is global process state, not user-scoped state.
3. UI data loading is not separated from session/auth concerns.
4. SkillMeat integration supports optional bearer credentials for outbound calls, but CCDash itself has no inbound auth model.
5. Role-like concepts exist only in domain data or UI copy, not as enforceable permissions.

## Problem Statement

As a platform operator, when CCDash is deployed for more than one person, I cannot safely expose it because the app has no identity boundary, no authorization checks, and no shared login path with SkillMeat. As a result, the only safe operating model is trusted local use, which blocks multi-user collaboration and cross-app consistency.

## Goals

1. Support SSO between CCDash and SkillMeat through a shared external identity provider.
2. Introduce enforceable RBAC for core CCDash resources and actions.
3. Preserve a local no-auth profile for desktop and single-user workflows.
4. Define a claim and membership model that can align CCDash projects with SkillMeat project/workspace scopes.
5. Ensure all auth is implemented through application/service boundaries, not UI-only gates.

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Hosted CCDash auth model | None | OIDC-backed sign-in and authenticated API requests |
| Cross-app sign-in experience with SkillMeat | Separate/manual credentials | Same issuer and session continuity through SSO |
| Protected actions with explicit authorization checks | 0 | All sensitive write/admin/execute flows |
| Local setup steps required for single-user mode | Minimal | No material increase in local-only mode |

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | CCDash must support OIDC-based sign-in using Authorization Code + PKCE for the browser-facing experience. | Must | Provider choice stays configurable. |
| FR-2 | Backend must validate issuer metadata, JWKS, and token/session claims from the configured identity provider. | Must | Shared trust contract with SkillMeat. |
| FR-3 | Define a canonical `Principal` model including user id, email/username, groups, memberships, and service-account support. | Must | Principal must flow through request context. |
| FR-4 | Define resource-oriented RBAC for at least: projects, documents, sessions, test data, execution runs, approvals, integrations, and admin settings. | Must | Permissions must be enforceable in services. |
| FR-5 | Define default roles such as `platform_admin`, `workspace_admin`, `contributor`, `reviewer`, and `viewer`. | Must | Final names may change; capability model may not. |
| FR-6 | Preserve a local development adapter that allows explicit no-auth operation. | Must | Local mode must be deliberate and visible, not accidental. |
| FR-7 | Support outbound service-to-service auth from CCDash to SkillMeat using the shared trust model or delegated credentials. | Should | Prevent separate ad hoc API key stories in hosted mode. |
| FR-8 | Provide audit attribution for privileged actions such as project updates, execution approvals, settings changes, and integration refresh. | Must | Required for operator trust. |

## Authorization Model

### Protected Resource Groups

1. Workspace and project administration
2. Session and transcript visibility
3. Documents, plans, and progress artifacts
4. Test visualizer and integrity data
5. Execution workbench launch/cancel/approve actions
6. SkillMeat and other integration configuration
7. Analytics and exports

### Initial Policy Shape

1. Role bindings must be scoped at least to workspace or project level.
2. Execution approval permissions must be independent from basic read/write project permissions.
3. Integration settings and secrets must be admin-only by default.
4. Sensitive raw transcript or artifact payloads should support stronger permissions than summary views if needed.

## Shared SSO Strategy

1. CCDash and SkillMeat must trust the same external issuer.
2. Shared sign-on is achieved through issuer session continuity, not by trying to share app cookies directly.
3. The apps should normalize workspace/project identifiers so claims can map cleanly into both systems.
4. Hosted mode should avoid long-lived browser-stored secrets.

## Non-Functional Requirements

1. Security posture must support hosted deployment behind TLS and a reverse proxy.
2. Auth implementation must remain provider-agnostic at the application boundary.
3. Fail-closed behavior is required in hosted mode when issuer validation fails.
4. Observability must include auth failures, authorization denials, and token/session health signals.

## In Scope

1. Shared sign-in architecture with a common issuer.
2. CCDash principal model and authorization enforcement.
3. UI session awareness and protected-route behavior.
4. Audit attribution for sensitive actions.

## Out of Scope

1. Fine-grained ABAC or policy-language adoption in V1.
2. End-user self-service org management.
3. Full identity-provider provisioning automation.
4. SkillMeat-side implementation details beyond the shared contract assumptions.

## Dependencies and Assumptions

1. Depends on `ccdash-hexagonal-foundation-v1` to introduce request context and identity ports.
2. Assumes the chosen identity provider supports OIDC discovery, JWKS validation, and standard browser sign-in flows.
3. Assumes SkillMeat can either trust the same issuer directly or participate in a compatible delegated-auth model.
4. Assumes hosted CCDash uses a deployment profile where reverse proxy, TLS, and secure cookies/headers are available.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Auth is bolted onto routers without a real domain model | High | Medium | Make principal and authorization policy first-class application concepts. |
| Local-first users are burdened by hosted security defaults | Medium | Medium | Keep an explicit local profile with separate composition. |
| Role model is too coarse for execution and secret management | High | Medium | Separate approval/admin capabilities from generic contributor access. |
| CCDash and SkillMeat scopes drift | High | Medium | Define shared workspace/project mapping contract up front. |

## Acceptance Criteria

1. Hosted CCDash can authenticate users through an OIDC issuer also trusted by SkillMeat.
2. API requests carry a validated principal into service-layer authorization checks.
3. Sensitive routes and actions enforce role or permission checks with audit attribution.
4. Local no-auth mode still works through a separate explicit adapter/composition path.
5. The project has a documented role/resource matrix that later implementation plans can execute without reopening the product model.
