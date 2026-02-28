---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-1-data-layer.md
phase: 1
title: "Data Layer"
status: "planning"
started: "2026-02-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 11
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["data-layer-expert"]
contributors: ["python-backend-engineer"]

tasks:
  - id: "TASK-1.1"
    description: "Add 6 new test tables + indexes to _TABLES in sqlite_migrations.py. Increment SCHEMA_VERSION to 13."
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-1.2"
    description: "Mirror all 6 tables in postgres_migrations.py with Postgres-compatible DDL (TEXT PK, JSONB for JSON columns, proper FK constraints)."
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["TASK-1.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.3"
    description: "Add 6 new @runtime_checkable Protocol classes to base.py: TestRunRepository, TestDefinitionRepository, TestResultRepository, TestDomainRepository, TestMappingRepository, TestIntegrityRepository."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.4"
    description: "Implement SqliteTestRunRepository in backend/db/repositories/test_runs.py. Methods: upsert(), get_by_id(), list_by_project(), list_by_session(), get_latest_for_feature()."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.5"
    description: "Implement SqliteTestDefinitionRepository in backend/db/repositories/test_definitions.py. Methods: upsert(), get_by_id(), list_by_project(), get_or_create() (hash-based)."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.6"
    description: "Implement SqliteTestResultRepository in backend/db/repositories/test_results.py. Append-only: no UPDATE on existing rows. Methods: upsert(), get_by_run(), get_history_for_test(), get_latest_status()."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.7"
    description: "Implement SqliteTestDomainRepository in backend/db/repositories/test_domains.py. Methods: upsert(), get_by_id(), list_tree() (returns nested hierarchy), get_or_create_by_name()."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.8"
    description: "Implement SqliteTestMappingRepository and SqliteTestIntegrityRepository. Mapping: upsert(), list_by_test(), list_by_feature(), list_by_domain(), get_primary_for_test(). Integrity: upsert(), list_by_project(), list_by_sha(), list_since()."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-1.9"
    description: "Create stub Postgres implementations in backend/db/repositories/postgres/test_*.py. Minimum: upsert() and get_by_id() for each."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.4", "TASK-1.5", "TASK-1.6", "TASK-1.7", "TASK-1.8"]
    estimated_effort: "1pt"
    priority: "medium"

  - id: "TASK-1.10"
    description: "Add 6 factory functions to factory.py: get_test_run_repository(), get_test_definition_repository(), get_test_result_repository(), get_test_domain_repository(), get_test_mapping_repository(), get_test_integrity_repository()."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.4", "TASK-1.5", "TASK-1.6", "TASK-1.7", "TASK-1.8", "TASK-1.9"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-1.11"
    description: "Add all test-related Pydantic models to backend/models.py: TestRunDTO, TestDefinitionDTO, TestResultDTO, TestDomainDTO, TestFeatureMappingDTO, TestIntegritySignalDTO, DomainHealthRollupDTO, FeatureTestHealthDTO, IngestRunRequest."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-1.1"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-1.1"]
  batch_2: ["TASK-1.2", "TASK-1.3", "TASK-1.11"]
  batch_3: ["TASK-1.4", "TASK-1.5", "TASK-1.6", "TASK-1.7", "TASK-1.8"]
  batch_4: ["TASK-1.9"]
  batch_5: ["TASK-1.10"]
  critical_path: ["TASK-1.1", "TASK-1.3", "TASK-1.4", "TASK-1.9", "TASK-1.10"]
  estimated_total_time: "18pt / ~1.5 weeks"

blockers: []

success_criteria:
  - "SCHEMA_VERSION is 13 in sqlite_migrations.py"
  - "All 6 tables created without error on fresh SQLite DB"
  - "All 6 Protocol interfaces defined in base.py and are @runtime_checkable"
  - "All SQLite repository unit tests pass"
  - "Factory functions dispatch correctly (SQLite vs Postgres)"
  - "Pydantic models serialize to JSON without error"
  - "Feature flag CCDASH_TEST_VISUALIZER_ENABLED gates table creation"

files_modified:
  - "backend/db/sqlite_migrations.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/repositories/base.py"
  - "backend/db/repositories/test_runs.py"
  - "backend/db/repositories/test_definitions.py"
  - "backend/db/repositories/test_results.py"
  - "backend/db/repositories/test_domains.py"
  - "backend/db/repositories/test_mappings.py"
  - "backend/db/repositories/test_integrity.py"
  - "backend/db/repositories/postgres/test_runs.py"
  - "backend/db/repositories/postgres/test_definitions.py"
  - "backend/db/repositories/postgres/test_results.py"
  - "backend/db/repositories/postgres/test_domains.py"
  - "backend/db/repositories/postgres/test_mappings.py"
  - "backend/db/repositories/postgres/test_integrity.py"
  - "backend/db/factory.py"
  - "backend/models.py"
  - "backend/tests/test_test_repositories.py"
---

# test-visualizer - Phase 1: Data Layer

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-1-progress.md -t TASK-1.X -s completed
```

---

## Objective

Establish the complete database foundation for the Test Visualizer. Creates 6 new tables (test_runs, test_definitions, test_results, test_domains, test_feature_mappings, test_integrity_signals), repository Protocol interfaces, SQLite implementations, Postgres stubs, factory functions, and Pydantic DTOs. Increments SCHEMA_VERSION from 12 to 13.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (sequential foundation)
Task("data-layer-expert", "Execute TASK-1.1: Add 6 new test tables and indexes to sqlite_migrations.py, increment SCHEMA_VERSION to 13")

# Batch 2 (parallel after TASK-1.1)
Task("data-layer-expert", "Execute TASK-1.2: Mirror 6 tables in postgres_migrations.py with Postgres-compatible DDL")
Task("python-backend-engineer", "Execute TASK-1.3: Add 6 @runtime_checkable Protocol classes to base.py")
Task("python-backend-engineer", "Execute TASK-1.11: Add all test-related Pydantic models to backend/models.py")

# Batch 3 (parallel after TASK-1.3)
Task("python-backend-engineer", "Execute TASK-1.4: Implement SqliteTestRunRepository")
Task("python-backend-engineer", "Execute TASK-1.5: Implement SqliteTestDefinitionRepository")
Task("python-backend-engineer", "Execute TASK-1.6: Implement SqliteTestResultRepository")
Task("python-backend-engineer", "Execute TASK-1.7: Implement SqliteTestDomainRepository")
Task("python-backend-engineer", "Execute TASK-1.8: Implement SqliteTestMappingRepository and SqliteTestIntegrityRepository")

# Batch 4 (after Batch 3)
Task("python-backend-engineer", "Execute TASK-1.9: Create stub Postgres implementations for all 6 test repositories")

# Batch 5 (after Batch 4)
Task("python-backend-engineer", "Execute TASK-1.10: Add 6 factory functions to factory.py")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
