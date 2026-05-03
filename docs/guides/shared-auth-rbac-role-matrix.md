---
title: Shared Auth RBAC Role Matrix
description: Operator defaults for hosted shared auth roles, bindings, bootstrap, and lockout prevention
audience: operators, developers, security
tags: [auth, rbac, sso, operations]
created: 2026-05-03
updated: 2026-05-03
category: operations
status: active
related: ["../project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md"]
---

# Shared Auth RBAC Role Matrix

This guide documents the initial hosted RBAC roles implemented by `RoleBindingAuthorizationPolicy`. Use it when bootstrapping an enterprise, assigning team/workspace/project access, or reviewing lockout risk.

Local and test profiles do not use this matrix for enforcement. They use the local no-auth permissive policy so a local operator can continue using CCDash without hosted identity setup.

## Binding Scopes

Bindings are evaluated against the requested resource scope in this order: `enterprise`, `team`, `workspace`, `project`, plus direct `user` bindings. A binding can authorize the same scope or a descendant scope when the request ancestry matches.

Valid binding scope types are:

- `enterprise:{enterprise_id}`
- `team:{team_id}`
- `workspace:{workspace_id}`
- `project:{project_id}`
- `user:{subject_key}`
- `owned_entity:{owned_entity_id}` for explicitly owned resources only

Use the narrowest scope that matches the operational need. Prefer team bindings for team-wide operators, workspace/project bindings for implementation teams, and direct user bindings only for exceptions.

## Canonical Roles

| Role | Aliases accepted by policy | Bind at | Purpose |
|------|----------------------------|---------|---------|
| `EA` enterprise admin | `enterprise_admin`, `enterprise-admin`, `enterprise:admin` | `enterprise` | Full enterprise administration and break-glass access. |
| `TA` team admin | `team_admin`, `team-admin`, `team:admin` | `team` | Team-scoped administration and project operations. Cannot perform enterprise-only provider, pricing mutation, cross-team integration, or path-sync actions. |
| `PM` project maintainer | `project_maintainer`, `project-maintainer`, `project:maintainer`, `project_owner`, `project-owner`, `maintainer`, `owner`, `operator`, `admin` | `workspace`, `project`, or direct `user` exception | Project implementation role: read/write project data, tasks, sessions, tests, execution run creation/cancel/retry/prepare, project maintenance, and GitHub workspace refresh. |
| `PV` project viewer | `project_viewer`, `project-viewer`, `project:viewer`, `viewer`, `member` | `workspace`, `project`, or direct `user` exception | Read-only project access, project switching to bound projects, reports, session mappings diagnosis, live read topics, and non-file codebase activity/tree views. |
| `IO` integration operator | `integration_operator`, `integration-operator`, `integration:operator` | `enterprise`, `team`, `workspace`, `project`, or service-account user binding | Integration-only operator for SkillMeat and GitHub integration actions. Does not grant generic project edit access. |
| `XA` execution approver | `execution_approver`, `execution-approver`, `execution:approver` | `enterprise`, `team`, `workspace`, `project`, or direct `user` binding | Approval/start authority for execution flows. Does not grant generic execution create/cancel/retry or project edit access. |
| `AA` analyst/auditor | `analyst`, `auditor`, `analyst_auditor`, `analyst-auditor` | `enterprise`, `team`, `workspace`, `project`, or direct `user` binding | Read/audit role: read permissions, Prometheus analytics export, audit reads, link audit, notifications, and AAR generation. |

Unknown role strings grant nothing. Prefix a role or direct scope with `deny:`, `deny.`, or `deny/` to create an explicit deny; explicit deny wins over allow.

## Operator Defaults

Recommended initial hosted bindings:

| Subject | Binding | Scope | Notes |
|---------|---------|-------|-------|
| Bootstrap enterprise owner | `EA` | `enterprise:{enterprise_id}` | Required first hosted admin. Keep at least two human `EA` subjects after setup. |
| Team lead or platform owner | `TA` | `team:{team_id}` | Lets the team manage its users/roles and operate team projects without enterprise-wide authority. |
| Project implementer | `PM` | `project:{project_id}` or `workspace:{workspace_id}` | Use workspace only when the same team should maintain every project in the workspace. |
| Read-only stakeholder | `PV` | `project:{project_id}` or `workspace:{workspace_id}` | Default for observers, reviewers, and dashboards that do not mutate data. |
| Integration service account | `IO` | Narrowest integration scope | Use stable `service:{issuer_id}:{client_id}` subjects and avoid combining with `PM` unless the service also performs project writes. |
| Release approver | `XA` | Project, workspace, or team scope | Assign separately from `PM`; ordinary project edit access must not imply approval authority. |
| Auditor or analyst | `AA` | Enterprise, team, workspace, or project scope | Prefer `AA` over `PV` when audit reads, analytics export, or link audit access is required. |

## Approvals and Integrations

Approvals and integrations are intentionally separate from generic edit access:

- `PM` can create, cancel, retry, and prepare execution runs, but does not receive `execution.run:approve` or `execution.launch:start`.
- `XA` receives `execution:read`, `execution.run:approve`, `execution.launch:start`, `live:subscribe`, and `live.execution:subscribe` only.
- `PM` receives `integration:read` and `integration.github.workspace:refresh`, but not broad SkillMeat/GitHub settings or write-probe powers.
- `IO` receives `integration:read` and all `integration.*` permissions only.

For production, assign `XA` to human approval groups and `IO` to integration operators or service accounts. Do not use `PM` as a substitute for either role.

## Bootstrap and Admin Assignment

Hosted first-run must be fail-closed unless both are configured:

- a bootstrap enterprise
- at least one bootstrap admin subject key or verified provider claim

The bootstrap admin receives `EA` only on the bootstrap enterprise. After first-run:

- create additional `EA`, `TA`, service-account, `IO`, `XA`, and `AA` bindings through audited admin operations
- require `admin.role:manage` or `admin.user:manage` at the containing scope for admin and ownership changes
- let `TA` manage team-scoped users and roles only
- do not let `TA` assign `EA`, mutate provider configuration, or change cross-team ownership

## Local No-Auth Behavior

In local and test runtime profiles, CCDash uses `PermitAllAuthorizationPolicy`, which allows every action. The local identity provider may emit an `owner` membership when a workspace/project header is present, but enforcement still comes from the permissive local/test policy.

Hosted API runtimes use `RoleBindingAuthorizationPolicy`. Hosted mode must never infer local operator access from a missing identity, missing bootstrap config, or empty membership list.

## Lockout Prevention

Before enabling hosted auth or changing provider/group mappings:

- Keep at least two independently authenticated `EA` subjects on the enterprise.
- Verify every `EA` binding uses a stable provider subject key, not an email address or display name.
- Keep one documented break-glass `EA` path that does not depend on a mutable team/group claim.
- Test `/api/auth/session` and one admin-protected endpoint with the bootstrap admin before removing local access.
- Stage role removals by adding the replacement binding first, then validating access, then removing the old binding.
- Use explicit denies sparingly and include an operator-readable reason in the binding record. Denies can override inherited enterprise/team/workspace access.
- Treat unknown role aliases as no access during migration; confirm imported aliases normalize to the canonical IDs above.

