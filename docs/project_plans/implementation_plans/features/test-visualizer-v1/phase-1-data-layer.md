---
title: "Phase 1: Data Layer - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 1
phase_title: "Data Layer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "18 story points"
duration: "1.5 weeks"
assigned_subagents: [data-layer-expert, python-backend-engineer]
entry_criteria:
  - CCDash backend is running with SQLite (SCHEMA_VERSION 12)
  - Postgres migrations module exists at backend/db/postgres_migrations.py
exit_criteria:
  - SCHEMA_VERSION incremented to 13
  - All 6 new test tables created in both SQLite and Postgres migrations
  - All 6 Repository Protocols defined in base.py
  - All 6 SQLite repository implementations passing unit tests
  - Factory functions wired in factory.py
  - Pydantic DTOs defined in models.py
  - Feature flag CCDASH_TEST_VISUALIZER_ENABLED gates table creation
tags: [implementation, data-layer, test-visualizer, migrations, repositories]
---

# Phase 1: Data Layer

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 18 story points | **Duration**: 1.5 weeks
**Assigned Subagents**: data-layer-expert, python-backend-engineer

---

## Overview

This phase establishes the complete database foundation for the Test Visualizer. It follows the exact same patterns as existing CCDash tables: schema declared in `sqlite_migrations.py` (`_TABLES` string + `_ensure_column` helpers), mirrored in `postgres_migrations.py`, protocol-based repository interfaces in `base.py`, SQLite implementations in `db/repositories/`, and factory functions in `factory.py`.

All 6 new tables use `CREATE TABLE IF NOT EXISTS` so migrations are idempotent. `SCHEMA_VERSION` increments from 12 to 13.

---

## DB Schema Design

### New Tables

#### `test_runs`
Captures a single test execution event (one invocation of a test suite).

```sql
CREATE TABLE IF NOT EXISTS test_runs (
    run_id              TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    git_sha             TEXT DEFAULT '',
    branch              TEXT DEFAULT '',
    agent_session_id    TEXT DEFAULT '',
    env_fingerprint     TEXT DEFAULT '',
    trigger             TEXT DEFAULT 'local',   -- 'local' | 'ci'
    status              TEXT DEFAULT 'complete', -- 'running' | 'complete' | 'failed'
    total_tests         INTEGER DEFAULT 0,
    passed_tests        INTEGER DEFAULT 0,
    failed_tests        INTEGER DEFAULT 0,
    skipped_tests       INTEGER DEFAULT 0,
    duration_ms         INTEGER DEFAULT 0,
    metadata_json       TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_runs_project
    ON test_runs(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_session
    ON test_runs(project_id, agent_session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_sha
    ON test_runs(project_id, git_sha);
```

#### `test_definitions`
Stable identity for each unique test. `test_id` is a stable hash of `(path, name, framework)`.

```sql
CREATE TABLE IF NOT EXISTS test_definitions (
    test_id         TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    path            TEXT NOT NULL,
    name            TEXT NOT NULL,
    framework       TEXT DEFAULT 'pytest',
    tags_json       TEXT DEFAULT '[]',
    owner           TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_defs_project
    ON test_definitions(project_id);
CREATE INDEX IF NOT EXISTS idx_test_defs_path
    ON test_definitions(project_id, path);
```

#### `test_results`
Append-only event log. PK is `(run_id, test_id)` — one result per test per run.

```sql
CREATE TABLE IF NOT EXISTS test_results (
    run_id              TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    status              TEXT NOT NULL,  -- 'passed' | 'failed' | 'skipped' | 'error' | 'xfailed' | 'xpassed'
    duration_ms         INTEGER DEFAULT 0,
    error_fingerprint   TEXT DEFAULT '',
    error_message       TEXT DEFAULT '',
    artifact_refs_json  TEXT DEFAULT '[]',
    stdout_ref          TEXT DEFAULT '',
    stderr_ref          TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, test_id)
);

CREATE INDEX IF NOT EXISTS idx_test_results_test
    ON test_results(test_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_status
    ON test_results(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_fingerprint
    ON test_results(error_fingerprint) WHERE error_fingerprint != '';
```

#### `test_domains`
Configurable domain/subdomain groupings. Self-referencing via `parent_id`.

```sql
CREATE TABLE IF NOT EXISTS test_domains (
    domain_id       TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    parent_id       TEXT REFERENCES test_domains(domain_id),
    description     TEXT DEFAULT '',
    tier            TEXT DEFAULT 'core',  -- 'core' | 'extras' | 'nonfunc'
    sort_order      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_domains_project
    ON test_domains(project_id);
CREATE INDEX IF NOT EXISTS idx_test_domains_parent
    ON test_domains(parent_id) WHERE parent_id IS NOT NULL;
```

#### `test_feature_mappings`
Versioned mapping linking tests to features and domains. Includes provider provenance and confidence.

```sql
CREATE TABLE IF NOT EXISTS test_feature_mappings (
    mapping_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    feature_id          TEXT NOT NULL,   -- FK to CCDash features.id
    domain_id           TEXT REFERENCES test_domains(domain_id),
    provider_source     TEXT NOT NULL,   -- 'repo_heuristics' | 'test_metadata' | 'semantic_llm' | 'user_override'
    confidence          REAL DEFAULT 0.5,
    version             INTEGER DEFAULT 1,
    snapshot_hash       TEXT DEFAULT '',
    is_primary          INTEGER DEFAULT 0,  -- 1 = highest-confidence mapping for this (test_id, feature_id)
    metadata_json       TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mappings_test
    ON test_feature_mappings(project_id, test_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_feature
    ON test_feature_mappings(project_id, feature_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_domain
    ON test_feature_mappings(project_id, domain_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mappings_upsert
    ON test_feature_mappings(test_id, feature_id, provider_source, version);
```

#### `test_integrity_signals`
Stores integrity alert events detected during ingestion. Append-only.

```sql
CREATE TABLE IF NOT EXISTS test_integrity_signals (
    signal_id           TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    git_sha             TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    test_id             TEXT REFERENCES test_definitions(test_id),
    signal_type         TEXT NOT NULL,  -- 'assertion_removed' | 'skip_introduced' | 'xfail_added' | 'broad_exception' | 'edited_before_green'
    severity            TEXT DEFAULT 'medium',  -- 'low' | 'medium' | 'high'
    details_json        TEXT DEFAULT '{}',
    linked_run_ids_json TEXT DEFAULT '[]',
    agent_session_id    TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_integrity_project
    ON test_integrity_signals(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_integrity_sha
    ON test_integrity_signals(project_id, git_sha);
CREATE INDEX IF NOT EXISTS idx_integrity_test
    ON test_integrity_signals(test_id) WHERE test_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_integrity_type
    ON test_integrity_signals(project_id, signal_type, severity);
```

---

## Pydantic Models

Add to `backend/models.py`:

```python
# ── Test Visualizer DTOs ─────────────────────────────────────────────

class TestRunDTO(BaseModel):
    run_id: str
    project_id: str
    timestamp: str
    git_sha: str = ""
    branch: str = ""
    agent_session_id: str = ""
    env_fingerprint: str = ""
    trigger: str = "local"
    status: str = "complete"
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_ms: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class TestDefinitionDTO(BaseModel):
    test_id: str
    project_id: str
    path: str
    name: str
    framework: str = "pytest"
    tags: list[str] = Field(default_factory=list)
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""


class TestResultDTO(BaseModel):
    run_id: str
    test_id: str
    status: str  # 'passed' | 'failed' | 'skipped' | 'error' | 'xfailed' | 'xpassed'
    duration_ms: int = 0
    error_fingerprint: str = ""
    error_message: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    stdout_ref: str = ""
    stderr_ref: str = ""
    created_at: str = ""


class TestDomainDTO(BaseModel):
    domain_id: str
    project_id: str
    name: str
    parent_id: Optional[str] = None
    description: str = ""
    tier: str = "core"
    sort_order: int = 0


class TestFeatureMappingDTO(BaseModel):
    mapping_id: int
    project_id: str
    test_id: str
    feature_id: str
    domain_id: Optional[str] = None
    provider_source: str
    confidence: float = 0.5
    version: int = 1
    snapshot_hash: str = ""
    is_primary: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class TestIntegritySignalDTO(BaseModel):
    signal_id: str
    project_id: str
    git_sha: str
    file_path: str
    test_id: Optional[str] = None
    signal_type: str
    severity: str = "medium"
    details: dict = Field(default_factory=dict)
    linked_run_ids: list[str] = Field(default_factory=list)
    agent_session_id: str = ""
    created_at: str = ""


class DomainHealthRollupDTO(BaseModel):
    domain_id: str
    domain_name: str
    tier: str = "core"
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    integrity_score: float = 1.0
    last_run_at: Optional[str] = None
    children: list["DomainHealthRollupDTO"] = Field(default_factory=list)


class FeatureTestHealthDTO(BaseModel):
    feature_id: str
    feature_name: str
    domain_id: Optional[str] = None
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    integrity_score: float = 1.0
    last_run_at: Optional[str] = None
    open_signals: int = 0


class IngestRunRequest(BaseModel):
    run_id: str
    project_id: str
    timestamp: str
    git_sha: str = ""
    branch: str = ""
    agent_session_id: str = ""
    env_fingerprint: str = ""
    trigger: str = "local"
    test_results: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
```

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| DB-1 | SQLite Schema | Add 6 new test tables + indexes to `_TABLES` in `sqlite_migrations.py`. Increment `SCHEMA_VERSION` to 13. | Tables created idempotently. Existing tables unaffected. DB runs with new schema. | 3 | data-layer-expert | None |
| DB-2 | Postgres Schema | Mirror all 6 tables in `postgres_migrations.py` with Postgres-compatible DDL (TEXT PK, JSONB for JSON columns, proper FK constraints). | Postgres migrations pass without error. JSONB indexes work correctly. | 2 | data-layer-expert | DB-1 |
| DB-3 | Repository Protocols | Add 6 new `@runtime_checkable` Protocol classes to `base.py`: `TestRunRepository`, `TestDefinitionRepository`, `TestResultRepository`, `TestDomainRepository`, `TestMappingRepository`, `TestIntegrityRepository`. Each includes: `upsert()`, `get_by_id()`, `list_paginated()`, `delete_by_source()` plus entity-specific query methods. | Protocols defined. Type-checking passes. Protocol methods documented. | 2 | python-backend-engineer | DB-1 |
| DB-4 | SQLite TestRunRepository | Implement `SqliteTestRunRepository` in `backend/db/repositories/test_runs.py`. Methods: `upsert()`, `get_by_id()`, `list_by_project()`, `list_by_session()`, `get_latest_for_feature()`. | All methods pass unit tests with `_FakeRepo` pattern. Upsert is idempotent. | 2 | python-backend-engineer | DB-3 |
| DB-5 | SQLite TestDefinitionRepository | Implement `SqliteTestDefinitionRepository` in `backend/db/repositories/test_definitions.py`. Methods: `upsert()`, `get_by_id()`, `list_by_project()`, `get_or_create()` (hash-based). | `get_or_create()` is idempotent for same (path, name, framework). Unit tests pass. | 2 | python-backend-engineer | DB-3 |
| DB-6 | SQLite TestResultRepository | Implement `SqliteTestResultRepository` in `backend/db/repositories/test_results.py`. Append-only: no UPDATE on existing rows. Methods: `upsert()`, `get_by_run()`, `get_history_for_test()`, `get_latest_status()`. | Append-only enforced. History query returns all results in timestamp order. | 2 | python-backend-engineer | DB-3 |
| DB-7 | SQLite TestDomainRepository | Implement `SqliteTestDomainRepository` in `backend/db/repositories/test_domains.py`. Methods: `upsert()`, `get_by_id()`, `list_tree()` (returns nested hierarchy), `get_or_create_by_name()`. | `list_tree()` returns proper parent-child nesting. Unit tests pass. | 2 | python-backend-engineer | DB-3 |
| DB-8 | SQLite TestMappingRepository + TestIntegrityRepository | Implement both remaining repositories. `TestMappingRepository`: `upsert()`, `list_by_test()`, `list_by_feature()`, `list_by_domain()`, `get_primary_for_test()`. `TestIntegrityRepository`: `upsert()`, `list_by_project()`, `list_by_sha()`, `list_since()`. | All methods work. Mapping upsert sets `is_primary` correctly based on confidence. | 2 | python-backend-engineer | DB-3 |
| DB-9 | Postgres Implementations | Create stub Postgres implementations in `backend/db/repositories/postgres/test_*.py`. Each class mirrors the SQLite implementation with asyncpg query syntax. Minimum: `upsert()` and `get_by_id()`. | Postgres implementations exist and follow factory pattern. Full parity deferred to DB-10. | 1 | python-backend-engineer | DB-4, DB-5, DB-6, DB-7, DB-8 |
| DB-10 | Factory Functions | Add `get_test_run_repository()`, `get_test_definition_repository()`, `get_test_result_repository()`, `get_test_domain_repository()`, `get_test_mapping_repository()`, `get_test_integrity_repository()` to `factory.py`. | Factory correctly dispatches to SQLite or Postgres based on connection type. Type hints correct. | 1 | python-backend-engineer | DB-4, DB-5, DB-6, DB-7, DB-8, DB-9 |
| DB-11 | Pydantic DTOs | Add all test-related Pydantic models to `backend/models.py` (TestRunDTO, TestDefinitionDTO, TestResultDTO, TestDomainDTO, TestFeatureMappingDTO, TestIntegritySignalDTO, DomainHealthRollupDTO, FeatureTestHealthDTO, IngestRunRequest). | Models validate correctly. JSON serialization works. Field types match DB schema. | 1 | python-backend-engineer | DB-1 |

---

## Quality Gates

- [ ] `SCHEMA_VERSION` is 13 in `sqlite_migrations.py`
- [ ] All 6 tables created without error on fresh SQLite DB
- [ ] All 6 tables created without error on fresh Postgres DB
- [ ] `_TABLES` string is idempotent (`CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`)
- [ ] All 6 Protocol interfaces defined in `base.py` and are `@runtime_checkable`
- [ ] `isinstance(repo, TestRunRepository)` returns `True` for SQLite implementation
- [ ] All SQLite repository unit tests pass (`backend/.venv/bin/python -m pytest backend/tests/test_test_repositories.py -v`)
- [ ] Factory functions dispatch correctly (SQLite vs Postgres)
- [ ] No raw SQL in factory functions
- [ ] Pydantic models serialize to JSON without error

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/db/sqlite_migrations.py` | Modified | SCHEMA_VERSION 12->13, 6 new tables in `_TABLES` |
| `backend/db/postgres_migrations.py` | Modified | 6 new tables in Postgres DDL |
| `backend/db/repositories/base.py` | Modified | 6 new Protocol classes |
| `backend/db/repositories/test_runs.py` | Created | SqliteTestRunRepository |
| `backend/db/repositories/test_definitions.py` | Created | SqliteTestDefinitionRepository |
| `backend/db/repositories/test_results.py` | Created | SqliteTestResultRepository |
| `backend/db/repositories/test_domains.py` | Created | SqliteTestDomainRepository |
| `backend/db/repositories/test_mappings.py` | Created | SqliteTestMappingRepository |
| `backend/db/repositories/test_integrity.py` | Created | SqliteTestIntegrityRepository |
| `backend/db/repositories/postgres/test_runs.py` | Created | PostgresTestRunRepository |
| `backend/db/repositories/postgres/test_definitions.py` | Created | PostgresTestDefinitionRepository |
| `backend/db/repositories/postgres/test_results.py` | Created | PostgresTestResultRepository |
| `backend/db/repositories/postgres/test_domains.py` | Created | PostgresTestDomainRepository |
| `backend/db/repositories/postgres/test_mappings.py` | Created | PostgresMappingRepository |
| `backend/db/repositories/postgres/test_integrity.py` | Created | PostgresIntegrityRepository |
| `backend/db/factory.py` | Modified | 6 new factory functions |
| `backend/models.py` | Modified | ~80 lines of new Pydantic DTOs |
| `backend/tests/test_test_repositories.py` | Created | Unit tests for all 6 repositories |

---

## Integration Notes

- The `test_feature_mappings.feature_id` column references CCDash `features.id` by convention (no FK enforced, since features live in a separate table and may be project-scoped differently).
- `test_integrity_signals.agent_session_id` references `sessions.id` by convention (no FK enforced for same reason).
- `test_runs.agent_session_id` is nullable — local runs not started from CCDash may not have a session ID.
- All JSON columns use `TEXT` in SQLite and `JSONB` in Postgres for consistency with existing pattern.
- `test_id` is a stable SHA-256 hash of `f"{path}::{name}::{framework}"` computed in the parser, not auto-incremented.
