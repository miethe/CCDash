---
type: progress
schema_version: 2
doc_type: progress
prd: are-we-winning-dashboard
feature_slug: are-we-winning-dashboard
phase: 2
milestone: M2
title: M2 — Weekly rollups, reopened derivation, and the self-caught ratio are correct
status: pending
created: 2026-08-14
updated: '2026-08-15'
prd_ref: docs/project_plans/PRDs/features/are-we-winning-dashboard-v1.md
plan_ref: docs/project_plans/implementation_plans/features/are-we-winning-dashboard-v1.md
itt_node_id: node_01M009H6DGAKD5VCC8QCM0KP0K
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
commit_refs: []
pr_refs: []
depends_on:
- 1
owners:
- opus-orchestrator
contributors: []
tasks:
- id: T2-001
  title: 'Transport-neutral query service: ISO-week created/completed rollups + drill-through
    + REST'
  status: completed
  assigned_to:
  - ica-executor
  routing: 'ica / claude-sonnet-5[1m] (offload-eligible: direct event counts)'
  dependencies: []
  started: 2026-08-15T03:00Z
  completed: 2026-08-15T03:20Z
  evidence:
  - commit: 6b0c0f4
  - test: backend/tests/test_are_we_winning_rollups.py (7 passed)
  - ac: zero-egress asserted by client-patched-to-raise tests on both REST paths
  verified_by:
  - T2-003
- id: T2-002
  title: Reopened derivation (ever-completed set only) + 3-bucket self-caught ratio
  status: completed
  assigned_to:
  - python-backend-engineer
  routing: claude-primary (MUST-stay per plan routing_constraints — silently-plausible
    failure mode)
  dependencies:
  - T2-001
  started: 2026-08-15T03:10Z
  completed: 2026-08-15T03:40Z
  evidence:
  - commit: 7b454db
  - commit: fd6c953
  - test: backend/tests/test_are_we_winning_derivations.py (34 passed)
  - test: backend/tests/test_intenttree_derivation_job.py (9 passed)
  - runtime: 33 reopened events derived; 4005 self-caught buckets all unknown
  verified_by:
  - T2-003
- id: T2-003
  title: AC validation gate (bucket boundary, derivation scope, unknown-bucket, no
    render-path egress)
  status: pending
  assigned_to:
  - codex-executor
  routing: codex / gpt-5.6-terra (read-only)
  dependencies:
  - T2-002
total_tasks: 3
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
progress: 66
overall_progress: 66
---

# M2 — Weekly rollups, reopened derivation, and the self-caught ratio are correct

Milestone execution record. Acceptance criteria live in the implementation plan
(`docs/project_plans/implementation_plans/features/are-we-winning-dashboard-v1.md`);
deviations are logged to `.claude/worknotes/are-we-winning-dashboard/implementation-notes.md`.
