---
schema_version: 3
doc_type: phase_plan
title: "Phase 2: Snapshot Ingestion & Storage"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 2
phase_title: "Snapshot Ingestion & Storage"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - Phase 1 complete: schemas validated, Pydantic DTOs round-trip, TS types compile
  - CCDASH_ARTIFACT_INTELLIGENCE_ENABLED flag available
exit_criteria:
  - CCDash fetches and stores a SkillMeat artifact snapshot for a configured project/collection
  - Freshness metadata queryable from repository
  - Identity mapping (UUID/hash/alias) stored and queryable
  - Snapshot diagnostics query returns snapshot age and unresolved identity count
  - Integration test: fetch → store → query cycle passes with seeded SkillMeat fixture
  - Existing skillmeat_client.py behavior unaffected
integration_owner: python-backend-engineer
ui_touched: false
---

# Phase 2: Snapshot Ingestion & Storage

## Phase Overview

**Estimate**: 6 pts
**Duration**: ~4–5 days
**Dependencies**: Phase 1 complete
**Assigned Subagent(s)**: python-backend-engineer (primary), data-layer-expert (migration + query optimization)

### Scope

Build the persistence and fetch layer for SkillMeat project artifact snapshots:

1. DB migration: two new tables — `artifact_snapshot_cache` (stores snapshot metadata and artifact rows) and `artifact_identity_map` (maps CCDash observed names to SkillMeat UUIDs/hashes)
2. Extend `backend/services/integrations/skillmeat_client.py` with snapshot fetch method
3. `ArtifactSnapshotRepository` for snapshot storage, retrieval, and freshness queries
4. `ArtifactIdentityMapper` service for three-tier identity resolution (UUID/hash → alias fuzzy → unresolved quarantine)
5. Snapshot diagnostics query for Settings surface (snapshot age, unresolved count)
6. Sync engine integration so snapshot is refreshed on project sync

### Parallelization

```yaml
parallelization:
  batch_1:
    # DB migration and schema must come first
    - task: T2-001
      assigned_to: data-layer-expert
      model: sonnet
      effort: medium
  batch_2:
    # Client and repository can proceed after tables exist
    - task: T2-002
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T2-001]
    - task: T2-003
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T2-001]
  batch_3:
    # Identity resolver and diagnostics depend on client + repo
    - task: T2-004
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T2-002, T2-003]
    - task: T2-005
      assigned_to: python-backend-engineer
      model: sonnet
      effort: low
      depends_on: [T2-003]
  batch_4:
    # Integration test and sync wiring last
    - task: T2-006
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T2-002, T2-003, T2-004]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T2-001 | DB migration: snapshot tables | Create Alembic migration adding `artifact_snapshot_cache` (id, project_id, collection_id, schema_version, generated_at, fetched_at, artifact_count, status, raw_json) and `artifact_identity_map` (id, project_id, ccdash_name, ccdash_type, skillmeat_uuid, content_hash, match_tier, confidence, resolved_at, unresolved_reason). Add indexes on (project_id, fetched_at) and (project_id, ccdash_name). | Migration runs cleanly on both SQLite and PostgreSQL. Tables created with correct columns and types. Indexes present. `alembic downgrade` removes tables cleanly. | 1.5 pts | data-layer-expert | sonnet | medium | Phase 1 complete |
| T2-002 | skillmeat_client.py: snapshot fetch | Extend `backend/services/integrations/skillmeat_client.py` with `fetch_project_artifact_snapshot(project_id, collection_id) -> SkillMeatArtifactSnapshot`. Uses `CCDASH_SKILLMEAT_API_URL`. Respects `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED`. Handles 404 (project not found), 429 (rate limit with retry), and network errors with structured logging. | Snapshot fetch returns `SkillMeatArtifactSnapshot` on success. 404 returns None with log. 429 retries up to 3× with exponential backoff. Network errors raise `SkillMeatClientError`. Existing client methods unchanged (regression test passes). | 1 pt | python-backend-engineer | sonnet | medium | T2-001 |
| T2-003 | ArtifactSnapshotRepository | Create `backend/db/repositories/artifact_snapshot_repository.py` with: `save_snapshot(snapshot)`, `get_latest_snapshot(project_id)`, `get_snapshot_freshness(project_id) -> SnapshotFreshnessMeta`, `get_unresolved_identity_count(project_id) -> int`. Uses async SQLite/PostgreSQL connection. | All repository methods work against seeded test DB. `get_snapshot_freshness` returns correct `fetched_at` and `generated_at`. `get_unresolved_identity_count` returns accurate count. Follows existing repository pattern in `backend/db/repositories/`. | 1.5 pts | python-backend-engineer | sonnet | medium | T2-001 |
| T2-004 | ArtifactIdentityMapper service | Create `backend/services/identity_resolver.py` implementing three-tier resolution: (1) UUID/content-hash exact match, (2) alias/name fuzzy match with configurable confidence threshold (`CCDASH_IDENTITY_FUZZY_THRESHOLD`, default 0.85), (3) unresolved quarantine with `identity_reconciliation` recommendation flag. Persists results to `artifact_identity_map`. | Tier-1 match resolves on UUID or content hash. Tier-2 fuzzy match produces confidence score; below threshold → quarantine. Quarantined entries stored with `match_tier: unresolved` and `unresolved_reason`. Seeded test with 3 known mismatch scenarios passes (see AC detail below). | 1.5 pts | python-backend-engineer | sonnet | medium | T2-002, T2-003 |
| T2-005 | Snapshot diagnostics query | Add `get_snapshot_diagnostics(project_id) -> SnapshotDiagnostics` to `ArtifactSnapshotRepository`. Returns: `snapshot_age_seconds`, `artifact_count`, `resolved_count`, `unresolved_count`, `is_stale` (based on configurable `CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS`). Expose on a new agent query in `backend/application/services/agent_queries/`. | Diagnostics query returns correct values against seeded data. `is_stale` correctly reflects staleness threshold. Agent query registered and callable. | 0.5 pts | python-backend-engineer | sonnet | low | T2-003 |
| T2-006 | Integration test: fetch → store → query | Write integration test that: (1) seeds a mock SkillMeat snapshot fixture, (2) calls `fetch_project_artifact_snapshot`, (3) stores via `ArtifactSnapshotRepository.save_snapshot`, (4) runs `ArtifactIdentityMapper` against seeded CCDash usage names, (5) asserts freshness query returns expected values, (6) asserts unresolved count matches known mismatches in fixture. | Integration test passes end-to-end. Fixture includes: 3 UUID-resolvable artifacts, 2 alias-resolvable artifacts, 2 unresolved artifacts. All assertions pass. | 0.5 pts | python-backend-engineer | sonnet | medium | T2-002, T2-003, T2-004 |

---

## Structured ACs

#### AC T2-004-Identity-Resolution: Three-tier resolution test scenarios
- target_surfaces:
    - backend/services/identity_resolver.py
    - backend/tests/test_identity_resolver.py
- propagation_contract: >
    Identity resolver is called with (observed_name, ccdash_type, snapshot_artifacts_list).
    Result stored in artifact_identity_map table. Downstream ranking service reads from this table.
- resilience: >
    Unresolved artifacts are quarantined with match_tier=unresolved, not silently dropped.
    Ranking rows for unresolved artifacts are still emitted with identity_confidence=null
    and trigger an `identity_reconciliation` recommendation.
- visual_evidence_required: false
- verified_by:
    - T2-006

**Required test scenarios for T2-004 (H3 compliance)**:
1. Exact UUID match → tier-1 resolution, confidence 1.0
2. Exact content-hash match → tier-1 resolution, confidence 1.0
3. Alias fuzzy match above threshold (e.g., "frontend-design" → "frontend-design-skill") → tier-2, confidence ≥ 0.85
4. Alias fuzzy match below threshold → quarantine, `identity_reconciliation` flagged
5. Artifact in snapshot not in CCDash usage → not quarantined (no CCDash name to resolve)
6. CCDash observed name not in snapshot at any tier → quarantine with `unresolved_reason: not_in_snapshot`
7. Snapshot artifact with `status: disabled` → still identity-mapped but flagged as disabled in ranking

---

## Key Files Affected

- `backend/db/migrations/versions/XXXX_artifact_snapshot_tables.py` (new)
- `backend/services/integrations/skillmeat_client.py` — add `fetch_project_artifact_snapshot`
- `backend/db/repositories/artifact_snapshot_repository.py` (new)
- `backend/services/identity_resolver.py` (new)
- `backend/application/services/agent_queries/artifact_intelligence.py` (new — diagnostics query)
- `backend/tests/test_snapshot_ingestion.py` (new — integration test)
- `backend/tests/test_identity_resolver.py` (new — identity resolution unit tests)
- `backend/config.py` — `CCDASH_IDENTITY_FUZZY_THRESHOLD`, `CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS`

---

## Quality Gates

- [ ] Alembic migration runs and rolls back cleanly on SQLite and PostgreSQL
- [ ] `fetch_project_artifact_snapshot` handles 404, 429, and network errors correctly
- [ ] `ArtifactSnapshotRepository` all methods work against seeded test DB
- [ ] Identity resolver passes all 7 required test scenarios
- [ ] Snapshot diagnostics query returns correct freshness and unresolved count
- [ ] Integration test: fetch → store → query passes end-to-end with 7-artifact fixture
- [ ] Existing `skillmeat_client.py` behavior unaffected (regression tests green)
