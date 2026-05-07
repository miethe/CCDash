---
schema_version: 3
doc_type: phase_plan
title: "Phase 3: Ranking & Recommendation Engine"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 3
phase_title: "Ranking & Recommendation Engine"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - Phase 2 complete: snapshot stored and queryable, identity mapping operational
  - At least one project has attributed sessions in session_usage_analytics
exit_criteria:
  - Ranking rows queryable by project, collection, user, artifact, version, workflow, period
  - All 7 recommendation types generated where evidence conditions met
  - Advisory-only assertion: no recommendation triggers automatic mutation
  - Confidence and sample-size gating suppress weak-evidence recommendations
  - Staleness gating suppresses destructive recommendation types on stale snapshots
  - Calibration test passes with seeded attribution data
  - backend-architect review of ranking algebra signed off
  - karen review at phase exit per Tier 3 gate
integration_owner: python-backend-engineer
ui_touched: false
---

# Phase 3: Ranking & Recommendation Engine

## Phase Overview

**Estimate**: 8 pts
**Duration**: ~5–6 days
**Dependencies**: Phase 2 complete
**Assigned Subagent(s)**: python-backend-engineer (primary), backend-architect (ranking algebra review)

This is the highest-risk and highest-point phase. It contains three algorithmically-flagged (H3) services. The phase is divided into two internal batches to allow a backend-architect checkpoint between the ranking computation and the recommendation classifier.

### Scope

1. **batch_1 — Ranking Computation**: `ArtifactRankingService` that aggregates usage attribution, workflow effectiveness, snapshot state, and identity mapping into multi-dimensional ranking rows. Stores results in `artifact_ranking` table.
2. **batch_2 — Recommendation Classifier**: `ArtifactRecommendationService` implementing all 7 recommendation types with evidence gating, confidence thresholds, and staleness suppression. Exposes ranking and recommendation queries via REST API and agent query surface.

### Parallelization

```yaml
parallelization:
  batch_1:
    # Ranking computation: identity resolver + ranking service
    - task: T3-001
      assigned_to: data-layer-expert
      model: sonnet
      effort: medium
    - task: T3-002
      assigned_to: python-backend-engineer
      model: sonnet
      effort: high
      depends_on: [T3-001]
  # CHECKPOINT: backend-architect reviews ranking algebra after batch_1
  batch_2:
    # Recommendation classifier: runs after ranking algebra is validated
    - task: T3-003
      assigned_to: python-backend-engineer
      model: sonnet
      effort: high
      depends_on: [T3-002]
    - task: T3-004
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T3-002]
  batch_3:
    # API exposure and calibration tests last
    - task: T3-005
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T3-003, T3-004]
    - task: T3-006
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T3-003, T3-004]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T3-001 | DB migration: ranking table | Create Alembic migration for `artifact_ranking` table: (id, project_id, collection_id, user_scope, artifact_id, artifact_uuid, version_id, workflow_id, period, exclusive_tokens, supporting_tokens, cost_usd, session_count, workflow_count, last_observed_at, avg_confidence, success_score, efficiency_score, quality_score, risk_score, context_pressure, sample_size, identity_confidence, snapshot_fetched_at, computed_at). Indexes: (project_id, period), (artifact_uuid, period), (workflow_id, period). | Migration runs and rolls back cleanly. All columns present. Compound indexes verified via EXPLAIN. | 1 pt | data-layer-expert | sonnet | medium | Phase 2 complete |
| T3-002 | ArtifactRankingService | Create `backend/services/artifact_ranking_service.py`. Aggregates from `session_usage_attributions`, `workflow_effectiveness` rollups, `artifact_identity_map`, and `artifact_snapshot_cache`. Computes ranking dimensions: usage, token, cost, confidence, recency, success, efficiency, quality, risk, context_pressure. Writes rows to `artifact_ranking` table. Handles cold-start (< min sample size → null confidence). Handles missing snapshot gracefully. | Ranking rows computed correctly against seeded attribution data. Cold-start rows have confidence=null and suppressed recommendations. Missing snapshot rows set identity_confidence=null. All 10 ranking dimensions populated. Unit tests for ranking algebra pass (see test scenarios below). | 3 pts | python-backend-engineer | sonnet | high | T3-001 |
| T3-003 | ArtifactRecommendationService | Create `backend/services/artifact_recommendation_service.py`. Implements all 7 recommendation types with evidence gating: `disable_candidate` (always-loaded, no usage, no policy), `load_on_demand` (narrow workflow usage + high context pressure), `workflow_specific_swap` (alternative has materially better effectiveness), `optimization_target` (high-utilization + poor efficiency/high cost/high risk), `version_regression` (newer version worse than prior with adequate sample), `identity_reconciliation` (observed usage but unresolved identity), `insufficient_data` (sample size or confidence or freshness below threshold). Each recommendation includes: evidence (token/session counts), confidence, affected_artifact_ids, scope, next_action (non-mutating). Staleness gating per OQ-5 thresholds (see architecture decisions in main plan). | All 7 recommendation types generated under correct conditions. Advisory-only assertion: no recommendation includes `auto_apply: true` or mutation fields. Confidence and sample-size gating suppress weak recommendations. Staleness gating applied per type (see AC detail below). Unit tests cover all 7 types including suppression conditions. | 2.5 pts | python-backend-engineer | sonnet | high | T3-002 |
| T3-004 | ArtifactRankingRepository | Create `backend/db/repositories/artifact_ranking_repository.py` with query methods: `get_rankings_by_project(project_id, period, filters)`, `get_rankings_by_artifact(artifact_uuid, period)`, `get_rankings_by_workflow(workflow_id, period)`, `get_rankings_by_user_scope(project_id, user_scope, period)`. All queries cursor-paginated. | All query methods return correct results against seeded ranking rows. Cursor pagination works. Filters (artifact_type, recommendation_type, period) correctly applied. | 0.5 pts | python-backend-engineer | sonnet | medium | T3-002 |
| T3-005 | REST API endpoints | Add ranking and recommendation query endpoints to `backend/routers/analytics.py`: `GET /api/analytics/artifact-rankings` (filters: project, collection, user, period, artifact_type, workflow, recommendation_type), `GET /api/analytics/artifact-recommendations` (filters: project, recommendation_type, min_confidence). Add agent query to `backend/application/services/agent_queries/artifact_intelligence.py`. Register endpoints in router. | Endpoints return correct responses against seeded ranking rows. Filter parameters correctly narrow results. OpenAPI docs present for both endpoints. Agent query callable via `ccdash` CLI. 400 returned on invalid filter params. | 0.5 pts | python-backend-engineer | sonnet | medium | T3-003, T3-004 |
| T3-006 | Calibration tests | Write seeded calibration tests using realistic attribution data covering: known-high-usage artifact (optimization_target), known-zero-usage artifact (disable_candidate), narrow-workflow artifact (load_on_demand), version regression scenario, cold-start project (all suppressed except insufficient_data), stale snapshot (destructive types suppressed). | All 6 calibration scenarios produce expected recommendation types. Suppression conditions verified. Calibration report generated (test output JSON). | 0.5 pts | python-backend-engineer | sonnet | medium | T3-003, T3-004 |

---

## Structured ACs

#### AC T3-002-Ranking-Algebra: Ranking computation test scenarios
- target_surfaces:
    - backend/services/artifact_ranking_service.py
    - backend/tests/test_artifact_ranking_service.py
- propagation_contract: >
    Ranking service reads from session_usage_attributions (via session_usage_analytics.py),
    workflow_effectiveness rollups, artifact_identity_map, and artifact_snapshot_cache.
    Writes computed rows to artifact_ranking table.
    Downstream: recommendation service reads from artifact_ranking.
- resilience: >
    If workflow_effectiveness rollup is missing for an artifact, effectiveness scores default to null (not 0).
    If snapshot is missing, identity_confidence defaults to null and snapshot-dependent fields null.
    Cold-start rows (sample_size < threshold) have confidence=null and are emitted with insufficient_data recommendation only.
- visual_evidence_required: false
- verified_by:
    - T3-006

**Required test scenarios for T3-002 (H3 compliance)**:
1. Artifact with high exclusive_tokens + low efficiency_score → optimization_target candidate
2. Artifact with 0 sessions in 30d lookback → disable_candidate candidate (if always-loaded)
3. Artifact with usage in only 1 of 5 workflows → load_on_demand candidate
4. Two versions of same artifact: v1 success_score 0.9, v2 success_score 0.65, sample ≥ 5 → version_regression
5. Cold-start: 2 sessions only → insufficient_data, no other recommendations
6. Missing snapshot: ranking row emitted with identity_confidence=null
7. Unresolved identity: identity_reconciliation recommendation generated
8. Workflow-scoped artifact used outside its declared workflow → anomaly captured in ranking row

#### AC T3-003-Advisory-Only: No recommendation triggers mutation
- target_surfaces:
    - backend/services/artifact_recommendation_service.py
- propagation_contract: >
    All ArtifactRecommendation objects have a `next_action` field that is advisory prose only.
    No recommendation object includes mutation fields (auto_apply, apply_url, patch_payload, etc.).
- resilience: >
    This is a structural invariant, not a runtime fallback. The Pydantic model for
    ArtifactRecommendation must not define mutation fields. This is enforced at schema level.
- visual_evidence_required: false
- verified_by:
    - T3-006

#### AC T3-003-Staleness-Gating: Destructive recommendations suppressed on stale snapshots
- target_surfaces:
    - backend/services/artifact_recommendation_service.py
    - backend/tests/test_artifact_recommendation_service.py
- propagation_contract: >
    For each recommendation type, compare snapshot_fetched_at against per-type max age thresholds
    (see OQ-5 resolution in main plan). If snapshot exceeds threshold, suppress recommendation and
    instead emit insufficient_data with rationale_code: stale_snapshot.
- resilience: >
    If snapshot_fetched_at is null (no snapshot), all recommendation types except
    identity_reconciliation and insufficient_data are suppressed.
- visual_evidence_required: false
- verified_by:
    - T3-006

---

## Key Files Affected

- `backend/db/migrations/versions/XXXX_artifact_ranking_table.py` (new)
- `backend/services/artifact_ranking_service.py` (new)
- `backend/services/artifact_recommendation_service.py` (new)
- `backend/db/repositories/artifact_ranking_repository.py` (new)
- `backend/routers/analytics.py` — new endpoints
- `backend/application/services/agent_queries/artifact_intelligence.py` — ranking/recommendation queries
- `backend/models.py` — `ArtifactRankingRow`, `ArtifactRecommendation` response models
- `backend/tests/test_artifact_ranking_service.py` (new)
- `backend/tests/test_artifact_recommendation_service.py` (new)
- `backend/tests/test_artifact_ranking_calibration.py` (new)

---

## Quality Gates

- [ ] Alembic migration for `artifact_ranking` table runs and rolls back cleanly
- [ ] Ranking computation passes all 8 required test scenarios
- [ ] All 7 recommendation types generate under correct conditions
- [ ] Advisory-only assertion: no recommendation includes mutation fields (enforced at schema level)
- [ ] Confidence and sample-size gating suppress weak-evidence recommendations
- [ ] Staleness gating applied per OQ-5 thresholds for all destructive recommendation types
- [ ] Cold-start handling: <min_sample_size → null confidence, only `insufficient_data` emitted
- [ ] All 6 calibration scenarios produce expected recommendation types
- [ ] REST API endpoints return correct responses with working filters
- [ ] **backend-architect review of ranking algebra signed off between batch_1 and batch_2**
- [ ] **karen review at phase exit (Tier 3 mandatory gate)**
