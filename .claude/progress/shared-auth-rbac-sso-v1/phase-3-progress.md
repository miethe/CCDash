---
type: progress
schema_version: 2
doc_type: progress
prd: shared-auth-rbac-sso-v1
feature_slug: shared-auth-rbac-sso-v1
prd_ref: docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md
execution_model: batch-parallel
phase: 3
title: Authorization Policy and 3-Tier RBAC Matrix
status: in_progress
started: '2026-05-03'
completed: null
commit_refs:
- ebb75eb
- 262d036
- fd7af48
pr_refs: []
overall_progress: 100
completion_estimate: at-risk
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- platform-engineering
- security-engineering
contributors:
- backend-architect
- security-engineering
- python-backend-engineer
model_usage:
  primary: codex
  external: []
tasks:
- id: AUTH-201
  description: Implement role-to-permission expansion and scope matching logic for user, team, enterprise, workspace, and project bindings.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - AUTH-002
  - AUTH-004
  - AUTH-101
  estimated_effort: 4 pts
  priority: critical
  assigned_model: codex
  model_effort: high
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Implemented RoleBindingAuthorizationPolicy with role-to-permission expansion, direct principal scopes, explicit deny handling, scope containment for user/team/enterprise/workspace/project/owned_entity, and auth-capable API runtime composition; backend/.venv/bin/python -m pytest backend/tests/test_authorization_policy.py -v passed (13 tests); py_compile for authorization/core/runtime/test modules passed.
- id: AUTH-202
  description: Add reusable helpers for service-layer authorization, denial reasons, and consistent 401 vs 403 behavior.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - AUTH-201
  estimated_effort: 3 pts
  priority: critical
  assigned_model: codex
  model_effort: high
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Added transport-neutral authorization helpers, AuthorizationDenied denial object, and FastAPI request-scope HTTP mapping for consistent 401/403 responses with reason/code/action/resource propagation; backend/.venv/bin/python -m pytest backend/tests/test_authorization_policy.py -v passed (19 tests); compileall and git diff --check passed.
- id: AUTH-203
  description: Finalize initial tier-aware roles and bindings for enterprise, team, and user scopes, and define bootstrap/admin assignment rules.
  status: completed
  assigned_to:
  - security-engineering
  - backend-architect
  dependencies:
  - AUTH-201
  estimated_effort: 3 pts
  priority: high
  assigned_model: codex
  model_effort: medium
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Added docs/guides/shared-auth-rbac-role-matrix.md documenting canonical role IDs and aliases, binding scopes, bootstrap/admin defaults, local no-auth behavior, lockout prevention, and separate approval/integration operator powers; guide sanity-checked with sed/rg/wc.
- id: AUTH-204
  description: Define enterprise, team, user, workspace, and project grant inheritance and conflict resolution rules.
  status: completed
  assigned_to:
  - backend-architect
  - security-engineering
  dependencies:
  - AUTH-201
  estimated_effort: 2 pts
  priority: high
  assigned_model: codex
  model_effort: medium
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Added immutable AUTHORIZATION_SCOPE_RULES artifact and focused inheritance tests covering enterprise/team/workspace/project descent, project non-inheritance upward, direct user self grants, owned entity exact bindings, parent-scope inherited access, explicit deny precedence, and artifact immutability; backend/.venv/bin/python -m pytest backend/tests/test_authorization_scope_inheritance.py backend/tests/test_authorization_policy.py -v passed (30 tests, 5 subtests); py_compile and git diff --check passed.
parallelization:
  batch_1:
  - AUTH-201
  batch_2:
  - AUTH-202
  - AUTH-203
  - AUTH-204
  critical_path:
  - AUTH-201
  - AUTH-202
  estimated_total_time: 4-5 days
blockers:
- id: PHASE2-VALIDATION-001
  title: Phase 2 runtime bootstrap validation remains at risk
  severity: medium
  blocking:
  - phase-completion-gate
  resolution: Re-run runtime bootstrap validation after clearing the previously observed Python hang.
  created: '2026-05-02'
success_criteria:
- id: SC-1
  description: Authorization decisions are deny-capable and explainable.
  status: completed
- id: SC-2
  description: 401 and 403 responses are consistent across hosted endpoints.
  status: completed
- id: SC-3
  description: The role matrix covers approvals and integrations separately from generic edit access.
  status: completed
- id: SC-4
  description: User/team/enterprise inheritance rules are explicit enough to implement without reopening the model mid-build.
  status: completed
---

# Phase 3 Progress: Authorization Policy and 3-Tier RBAC Matrix

Phase 3 establishes the deny-capable RBAC evaluator, reusable enforcement helpers, role matrix, and inheritance rules that downstream backend enforcement phases will consume.
