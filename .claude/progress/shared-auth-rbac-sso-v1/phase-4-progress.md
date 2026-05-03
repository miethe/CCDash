---
type: progress
schema_version: 2
doc_type: progress
prd: shared-auth-rbac-sso-v1
feature_slug: shared-auth-rbac-sso-v1
prd_ref: docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md
execution_model: batch-parallel
phase: 4
title: Scope Mapping and SkillMeat Trust Alignment
status: in_progress
started: '2026-05-03'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- platform-engineering
- security-engineering
contributors:
- backend-architect
- security-engineering
- integrations
model_usage:
  primary: codex
  external: []
tasks:
- id: AUTH-301
  description: Define how provider claims, groups, organizations, and workspace/project identifiers map into CCDash enterprise/team/workspace/project scopes.
  status: completed
  assigned_to:
  - backend-architect
  - security-engineering
  dependencies:
  - AUTH-201
  - AUTH-204
  - AUTH-091
  estimated_effort: 4 pts
  priority: critical
  assigned_model: codex
  model_effort: high
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Implemented provider-neutral claim-to-scope mapping for Local/Clerk/OIDC-style claims, wired Clerk/OIDC providers through the mapper, resolved hosted request enterprise/team/workspace/project context from claims before local fallbacks, and prevented hosted principals without project/workspace claims from inheriting global active project state; backend/.venv/bin/python -m unittest backend.tests.test_claims_mapping backend.tests.test_auth_providers backend.tests.test_request_context backend.tests.test_authorization_policy backend.tests.test_authorization_scope_inheritance passed (83 tests); compileall for auth adapters and runtime container passed.
- id: AUTH-302
  description: Align outbound SkillMeat integration auth with the shared provider/delegation model and remove the need for a separate hosted-only credential story.
  status: completed
  assigned_to:
  - integrations
  - security-engineering
  dependencies:
  - AUTH-101
  - AUTH-301
  - AUTH-090
  estimated_effort: 3 pts
  priority: high
  assigned_model: codex
  model_effort: medium
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Implemented shared CCDash-to-SkillMeat trust metadata headers for hosted Clerk/OIDC principals while preserving local no-auth and explicit API-key behavior; threaded request context through SkillMeat validation, sync, refresh, and memory publish clients; backend/.venv/bin/python -m pytest backend/tests/test_skillmeat_trust.py backend/tests/test_skillmeat_client.py backend/tests/test_integrations_router.py backend/tests/test_skillmeat_memory_drafts.py passed (24 tests).
- id: AUTH-303
  description: Refine workspace registry behavior so active project selection, project lookup, and scope resolution are compatible with hosted multi-user usage under enterprise/team/user context.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - AUTH-301
  estimated_effort: 3 pts
  priority: high
  assigned_model: codex
  model_effort: high
  started: '2026-05-03'
  completed: '2026-05-03'
  verified_by: codex-orchestrator
  evidence:
  - Refined workspace registry scope resolution with explicit active-project fallback control, kept local active-project compatibility, prevented hosted request context and shared project resolution from inheriting process-global active project, and made hosted /api/projects/active* reads request-selected while rejecting hosted active-project mutation; backend/.venv/bin/python -m pytest backend/tests/test_project_manager.py backend/tests/test_project_paths.py backend/tests/test_request_context.py backend/tests/test_claims_mapping.py passed (62 tests); compileall and git diff --check passed.
parallelization:
  batch_1:
  - AUTH-301
  batch_2:
  - AUTH-302
  - AUTH-303
  critical_path:
  - AUTH-301
  - AUTH-303
  estimated_total_time: 4 days
blockers: []
success_criteria:
- id: SC-1
  description: Claims map cleanly into CCDash and SkillMeat scope identifiers across Local, Clerk, and generic OIDC modes.
  status: in_progress
- id: SC-2
  description: Hosted requests do not inherit another user's active-project state.
  status: completed
- id: SC-3
  description: Service-to-service integration auth uses the shared trust contract.
  status: completed
- id: SC-4
  description: User/team/enterprise context resolves consistently before workspace/project access is evaluated.
  status: completed
quality_gates:
- Claims map cleanly into CCDash and SkillMeat scope identifiers across Local, Clerk, and generic OIDC modes.
- Hosted requests do not inherit another user's active-project state.
- Service-to-service integration auth uses the shared trust contract.
- User/team/enterprise context resolves consistently before workspace/project access is evaluated.
---

# Phase 4 Progress: Scope Mapping and SkillMeat Trust Alignment

Phase 4 maps hosted identity claims into deterministic CCDash scopes, aligns outbound SkillMeat trust, and removes process-global active-project assumptions from hosted request semantics.
