---
type: progress
schema_version: 2
doc_type: progress
prd: skillmeat-artifact-usage-intelligence-exchange-v1
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
phase: 3
phase_title: Ranking & Recommendation Engine
title: "skillmeat-artifact-usage-intelligence-exchange-v1 - Phase 3: Ranking & Recommendation Engine"
status: completed
created: '2026-05-07'
updated: '2026-05-07'
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1/phase-3-ranking-recommendations.md
commit_refs: []
pr_refs: []
execution_model: batch-parallel
overall_progress: 100
completion_estimate: completed
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- data-layer-expert
- python-backend-engineer
- backend-architect
contributors: []
phase_dependencies:
- phase: 2
  status: complete
  description: Phase 2 snapshot ingestion, storage, identity mapping, and diagnostics are complete; Phase 3 ranking and recommendation work is unblocked.
tasks:
- id: T3-001
  title: "DB migration: ranking table"
  description: Add artifact_ranking storage across CCDash custom SQLite/Postgres migration paths with query indexes and repository/factory wiring.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - phase-2-complete
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: medium
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_artifact_ranking_repository.py backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py -q -> 21 passed"
- id: T3-002
  title: ArtifactRankingService
  description: Aggregate usage attribution, workflow effectiveness, snapshot state, and identity mapping into persisted multi-dimensional artifact ranking rows.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-001
  estimated_effort: 3 pts
  assigned_model: sonnet
  model_effort: high
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_artifact_ranking_service.py -q -> 1 passed"
- id: T3-003
  title: ArtifactRecommendationService
  description: Generate all seven advisory recommendation types with evidence, confidence, sample-size, and snapshot-staleness gating.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-002
  estimated_effort: 2.5 pts
  assigned_model: sonnet
  model_effort: high
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_artifact_recommendation_service.py backend/tests/test_artifact_ranking_calibration.py -q -> 9 passed"
- id: T3-004
  title: ArtifactRankingRepository
  description: Add cursor-paginated ranking query methods by project, artifact, workflow, user scope, period, and recommendation filters.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-002
  estimated_effort: 0.5 pts
  assigned_model: sonnet
  model_effort: medium
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_artifact_ranking_repository.py backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py -q -> 21 passed"
- id: T3-005
  title: REST API endpoints and agent query surface
  description: Expose artifact ranking and recommendation queries through analytics REST endpoints and the artifact intelligence agent-query surface.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-003
  - T3-004
  estimated_effort: 0.5 pts
  assigned_model: sonnet
  model_effort: medium
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_agent_queries_artifact_intelligence.py backend/tests/test_agent_router.py backend/tests/test_analytics_router.py -q -> 39 passed"
- id: T3-006
  title: Calibration tests
  description: Add seeded calibration coverage for high-usage optimization targets, zero-usage disable candidates, workflow-specific loading, version regression, cold starts, stale snapshots, and suppression behavior.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-003
  - T3-004
  estimated_effort: 0.5 pts
  assigned_model: sonnet
  model_effort: medium
  completed_at: '2026-05-07'
  validation:
  - "backend/.venv/bin/python -m pytest backend/tests/test_artifact_recommendation_service.py backend/tests/test_artifact_ranking_calibration.py -q -> 9 passed"
parallelization:
  batch_1:
  - T3-001
  - T3-002
  batch_2:
  - T3-003
  - T3-004
  batch_3:
  - T3-005
  - T3-006
  critical_path:
  - phase-2-complete
  - T3-001
  - T3-002
  - T3-003
  - T3-005
  - T3-006
blockers: []
success_criteria:
- id: SC-1
  description: Ranking rows are queryable by project, collection, user, artifact, version, workflow, and period.
  status: completed
- id: SC-2
  description: All seven recommendation types are generated when evidence conditions are met.
  status: completed
- id: SC-3
  description: Recommendations are advisory-only and do not expose automatic mutation fields.
  status: completed
- id: SC-4
  description: Confidence and sample-size gating suppress weak-evidence recommendations.
  status: completed
- id: SC-5
  description: Staleness gating suppresses destructive recommendations on stale snapshots.
  status: completed
- id: SC-6
  description: Calibration tests pass with seeded attribution and snapshot data.
  status: completed
- id: SC-7
  description: REST and agent-query surfaces return filtered ranking and recommendation results.
  status: completed
validation:
  required:
  - Artifact ranking repository, migration, and governance coverage
  - Artifact ranking service algebra coverage
  - Artifact recommendation service and calibration coverage
  - Agent query, agent router, and analytics router coverage
  - Focused Phase 3 lint over touched Python files
---

# skillmeat-artifact-usage-intelligence-exchange-v1 - Phase 3

## Objective

Build the ranking and recommendation engine that turns SkillMeat snapshots plus CCDash usage attribution into queryable artifact rankings and advisory optimization recommendations.

## Current Status

Phase 3 is complete. Phase 2 is complete, the Phase 3 ranking table/repository path is in place, ranking and recommendation services are implemented, REST and agent-query surfaces are wired, and T3-001 through T3-006 are complete.

## Validation Evidence

- 2026-05-07 T3-001/T3-004 repository and migration check: `backend/.venv/bin/python -m pytest backend/tests/test_artifact_ranking_repository.py backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py -q` -> 21 passed.
- 2026-05-07 T3-002 ranking service check: `backend/.venv/bin/python -m pytest backend/tests/test_artifact_ranking_service.py -q` -> 1 passed.
- 2026-05-07 T3-003/T3-006 recommendation and calibration check: `backend/.venv/bin/python -m pytest backend/tests/test_artifact_recommendation_service.py backend/tests/test_artifact_ranking_calibration.py -q` -> 9 passed.
- 2026-05-07 T3-005 API and agent query check: `backend/.venv/bin/python -m pytest backend/tests/test_agent_queries_artifact_intelligence.py backend/tests/test_agent_router.py backend/tests/test_analytics_router.py -q` -> 39 passed.
- 2026-05-07 combined focused Phase 3 suite: 70 passed.
- 2026-05-07 lint: `backend/.venv/bin/python -m ruff check ...` -> failed because the backend venv does not have `ruff` installed (`No module named ruff`).
- 2026-05-07 lint fallback: `ruff check backend/adapters/storage/base.py backend/adapters/storage/enterprise.py backend/adapters/storage/local.py backend/application/ports/core.py backend/application/services/agent_queries/__init__.py backend/application/services/agent_queries/artifact_intelligence.py backend/application/services/agent_queries/models.py backend/config.py backend/data_domains.py backend/db/factory.py backend/db/postgres_migrations.py backend/db/sqlite_migrations.py backend/models.py backend/routers/agent.py backend/routers/analytics.py backend/tests/test_agent_queries_artifact_intelligence.py backend/tests/test_agent_router.py backend/tests/test_analytics_router.py backend/tests/test_sqlite_migrations.py backend/db/repositories/artifact_ranking_repository.py backend/db/repositories/postgres/artifact_ranking_repository.py backend/services/artifact_ranking_service.py backend/services/artifact_recommendation_service.py backend/tests/test_artifact_ranking_calibration.py backend/tests/test_artifact_ranking_repository.py backend/tests/test_artifact_ranking_service.py backend/tests/test_artifact_recommendation_service.py` -> All checks passed.

## Notes

- CCDash uses custom SQLite/Postgres migration modules for this path; the Phase 3 ranking table was added through those migration surfaces rather than Alembic.
- `ArtifactRankingService` persists aggregate and workflow-scoped ranking rows from attributed usage, identity mappings, snapshot metadata, and effectiveness evidence.
- `ArtifactRecommendationService` emits advisory-only recommendations for `disable_candidate`, `load_on_demand`, `workflow_specific_swap`, `optimization_target`, `version_regression`, `identity_reconciliation`, and `insufficient_data`.
- Ranking repository implementations support cursor-paginated project, artifact, workflow, user-scope, and filtered list queries for SQLite and Postgres.
- REST and agent query surfaces expose ranking and recommendation reads without adding automatic mutation or apply behavior.
