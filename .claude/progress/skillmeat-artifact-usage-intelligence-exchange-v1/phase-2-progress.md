---
type: progress
schema_version: 2
doc_type: progress
prd: skillmeat-artifact-usage-intelligence-exchange-v1
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
phase: 2
phase_title: Snapshot Ingestion & Storage
title: "skillmeat-artifact-usage-intelligence-exchange-v1 - Phase 2: Snapshot Ingestion & Storage"
status: in_progress
created: '2026-05-07'
updated: '2026-05-07'
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1/phase-2-snapshot-ingestion.md
commit_refs: []
pr_refs: []
execution_model: batch-parallel
overall_progress: 17
completion_estimate: on_track
total_tasks: 6
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- data-layer-expert
contributors: []
phase_dependencies:
- phase: 1
  status: complete
  description: Phase 1 contract/schema foundation is complete; Phase 2 migration work is unblocked.
tasks:
- id: T2-001
  title: "DB migration: snapshot tables"
  description: Create custom SQLite/Postgres migrations adding artifact_snapshot_cache and artifact_identity_map tables with required indexes. CCDash does not use Alembic for this path and has no downgrade migration flow.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - phase-1-complete
  estimated_effort: 1.5 pts
  assigned_model: sonnet
  model_effort: medium
- id: T2-002
  title: "skillmeat_client.py: snapshot fetch"
  description: Extend SkillMeat client with fetch_project_artifact_snapshot, feature-flag enforcement, API URL usage, structured error handling, and retry behavior.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T2-001
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: medium
- id: T2-003
  title: ArtifactSnapshotRepository
  description: Add repository methods for saving snapshots, retrieving the latest snapshot, querying freshness, and counting unresolved identities.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T2-001
  estimated_effort: 1.5 pts
  assigned_model: sonnet
  model_effort: medium
- id: T2-004
  title: ArtifactIdentityMapper service
  description: Implement three-tier identity resolution using UUID/content-hash exact matching, alias fuzzy matching, and unresolved quarantine with recommendation flagging.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T2-002
  - T2-003
  estimated_effort: 1.5 pts
  assigned_model: sonnet
  model_effort: medium
- id: T2-005
  title: Snapshot diagnostics query
  description: Add get_snapshot_diagnostics and register an agent query returning snapshot age, artifact counts, resolved/unresolved counts, and staleness.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T2-003
  estimated_effort: 0.5 pts
  assigned_model: sonnet
  model_effort: low
- id: T2-006
  title: "Integration test: fetch -> store -> query"
  description: Add an end-to-end integration test covering mock SkillMeat snapshot fetch, repository storage, identity mapping, freshness query, and unresolved count assertions.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T2-002
  - T2-003
  - T2-004
  estimated_effort: 0.5 pts
  assigned_model: sonnet
  model_effort: medium
parallelization:
  batch_1:
  - T2-001
  batch_2:
  - T2-002
  - T2-003
  batch_3:
  - T2-004
  - T2-005
  batch_4:
  - T2-006
  critical_path:
  - phase-1-complete
  - T2-001
  - T2-003
  - T2-004
  - T2-006
blockers: []
success_criteria:
- id: SC-1
  description: CCDash fetches and stores a SkillMeat artifact snapshot for a configured project or collection.
  status: pending
- id: SC-2
  description: Snapshot freshness metadata is queryable from the repository.
  status: pending
- id: SC-3
  description: Identity mapping for UUID, hash, alias, and unresolved cases is stored and queryable.
  status: pending
- id: SC-4
  description: Snapshot diagnostics return snapshot age and unresolved identity count.
  status: pending
- id: SC-5
  description: Fetch, store, resolve, and query integration coverage passes with the seeded SkillMeat fixture.
  status: pending
- id: SC-6
  description: Existing skillmeat_client.py behavior remains unaffected.
  status: pending
validation:
  required:
  - Custom SQLite and PostgreSQL migration bootstrap/idempotent upgrade coverage for artifact_snapshot_cache and artifact_identity_map; no Alembic downgrade path exists in CCDash.
  - SkillMeat snapshot client error-handling tests for 404, 429, and network failures
  - ArtifactSnapshotRepository seeded database tests
  - Identity resolver coverage for all required three-tier resolution scenarios
  - Snapshot diagnostics query test
  - End-to-end fetch -> store -> query integration test
---

# skillmeat-artifact-usage-intelligence-exchange-v1 - Phase 2

## Objective

Build the persistence, fetch, identity mapping, diagnostics, and integration-test layer for SkillMeat artifact snapshots after Phase 1 contracts are complete.

## Current Status

Phase 2 is in progress. Phase 1 is complete, the Phase 1 blocker is resolved, and T2-001 is complete. T2-002 through T2-006 remain pending.

## Validation Evidence

- 2026-05-07 T2-001: `backend/.venv/bin/python -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py -q` -> 18 passed in 0.63s.
- 2026-05-07 T2-001 ownership follow-up: `backend/.venv/bin/python -m pytest backend/tests/test_data_domain_layout.py backend/tests/test_data_domain_ownership.py -q` -> failed on unrelated contract drift outside T2-001 scope (`feature_sessions`, `session_memory_drafts`, `planning_worktree_contexts`, `filesystem_scan_manifest`); new artifact snapshot tables were classified.

## Notes

- T2-001 used CCDash's custom migration modules (`backend/db/sqlite_migrations.py`, `backend/db/postgres_migrations.py`) rather than Alembic. There is no downgrade path in this migration system.
- `artifact_snapshot_cache` and `artifact_identity_map` are shared integration snapshot tables across SQLite and Postgres and are classified as refreshable, scope-owned integration data.
