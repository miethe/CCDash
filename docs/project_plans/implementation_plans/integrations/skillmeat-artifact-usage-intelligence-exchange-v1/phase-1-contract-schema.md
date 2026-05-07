---
schema_version: 3
doc_type: phase_plan
title: "Phase 1: Contract & Schema Foundation"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 1
phase_title: "Contract & Schema Foundation"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - PRD approved and decisions block reviewed
  - Existing telemetry_exporter.py and skillmeat_client.py understood
exit_criteria:
  - JSON schema files parse and validate sample payloads
  - Pydantic DTOs round-trip serialize/deserialize cleanly
  - TypeScript types compile without errors
  - Backward-compat assertion confirms existing artifact outcome schema untouched
  - Unit tests for schema validation pass
integration_owner: python-backend-engineer
ui_touched: false
---

# Phase 1: Contract & Schema Foundation

## Phase Overview

**Estimate**: 5 pts
**Duration**: ~3–4 days
**Dependencies**: None (first phase)
**Assigned Subagent(s)**: python-backend-engineer (primary), ui-engineer-enhanced (parallel FE types)

### Scope

Define the complete data contracts for this feature before any I/O or computation code is written:

1. `skillmeat-artifact-snapshot-v1` JSON schema — the snapshot SkillMeat will send to CCDash
2. `ccdash-artifact-usage-rollup-v1` JSON schema — the rollup CCDash will send back to SkillMeat
3. Pydantic DTOs for all new models in `backend/models.py` and a new `backend/db/schemas/artifact_intelligence.py`
4. TypeScript interfaces in `types.ts` for all new response shapes
5. Backward-compatibility assertion verifying existing artifact outcome payload schema is unmodified

### Parallelization

```yaml
parallelization:
  batch_1:
    # Run in parallel — no file overlap
    - task: T1-001
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
    - task: T1-002
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
  batch_2:
    # FE types depend on BE schemas being defined; run after batch_1
    - task: T1-003
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: low
      depends_on: [T1-001, T1-002]
  batch_3:
    # Validation depends on all schemas and types
    - task: T1-004
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T1-001, T1-002, T1-003]
    - task: T1-005
      assigned_to: python-backend-engineer
      model: sonnet
      effort: low
      depends_on: [T1-001]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T1-001 | Snapshot schema & Pydantic DTOs | Author `skillmeat-artifact-snapshot-v1` JSON schema. Add Pydantic models: `SkillMeatArtifactSnapshot`, `SnapshotArtifact`, `SnapshotFreshnessMeta`. Add to `backend/models.py` or new `backend/db/schemas/artifact_intelligence.py`. | Schema validates sample snapshot JSON. Pydantic model round-trips to/from JSON without loss. Required fields enforced; optional fields default correctly. `schemaVersion` field present and validated. | 2 pts | python-backend-engineer | sonnet | medium | None |
| T1-002 | Rollup schema & Pydantic DTOs | Author `ccdash-artifact-usage-rollup-v1` JSON schema. Add Pydantic models: `ArtifactUsageRollup`, `ArtifactUsageStats`, `ArtifactEffectivenessStats`, `ArtifactRecommendationEmbed`. Ensure rollup schema is additive relative to existing artifact outcome schema. | Schema validates sample rollup JSON. Pydantic models round-trip cleanly. Backward-compat assertion confirms existing `artifact-outcome-v1` schema fields are unchanged. New rollup fields are all optional (no breaking required fields). | 2 pts | python-backend-engineer | sonnet | medium | None |
| T1-003 | TypeScript interfaces | Add TypeScript interfaces to `types.ts`: `ArtifactSnapshot`, `ArtifactSnapshotItem`, `ArtifactRankingRow`, `ArtifactRecommendation`, `SnapshotHealth`. Each interface must have an explicit `?` for all optional fields so FE fallback handling is compile-enforced. | Interfaces compile without TypeScript errors. All optional BE fields marked `?`. No `any` types. Import from `@/types` works correctly in a stub consumer file. AC-T1-FE-fallback: FE handles any missing field on `ArtifactRankingRow` — undefined fields render gracefully, no runtime exceptions. | 1 pt | ui-engineer-enhanced | sonnet | low | T1-001, T1-002 |
| T1-004 | Schema validation unit tests | Write pytest unit tests for all new Pydantic models: valid payloads parse, invalid payloads raise `ValidationError`, optional fields default, `schemaVersion` mismatches rejected. Include one test for existing artifact outcome payload confirming no regression. | All validation tests pass. Existing artifact outcome test still green. Minimum 8 test cases across snapshot and rollup schemas. | 0.5 pts | python-backend-engineer | sonnet | medium | T1-001, T1-002, T1-003 |
| T1-005 | Feature flag wiring | Add `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` env var to `backend/config.py` (default: false). Gate snapshot fetch and export behind this flag. Document in `.env.example`. | Config var present, default false, documented. Import succeeds. Flag is checked in a stub that logs "artifact intelligence disabled" when false. | 0.5 pts | python-backend-engineer | sonnet | low | T1-001 |

---

## Structured ACs

#### AC T1-003-FE-Fallback: FE handles missing fields on ArtifactRankingRow
- target_surfaces:
    - types.ts
- propagation_contract: >
    All fields on `ArtifactRankingRow` that correspond to new backend fields must be typed as optional (`?`).
    TypeScript compiler enforces null/undefined handling at call sites.
- resilience: >
    If any field is missing or null at runtime, UI components using the type must not throw.
    Optional chaining (`?.`) or explicit null checks required at render sites.
- visual_evidence_required: false
- verified_by:
    - T1-004

---

## Key Files Affected

- `backend/models.py` — new Pydantic models for snapshot and rollup
- `backend/db/schemas/artifact_intelligence.py` (new) — artifact intelligence schema definitions
- `backend/config.py` — `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` flag
- `.env.example` — document new flag
- `types.ts` — new TypeScript interfaces
- `backend/tests/test_artifact_intelligence_schemas.py` (new) — schema validation tests

---

## Quality Gates

- [ ] `skillmeat-artifact-snapshot-v1` JSON schema parses and validates sample payload
- [ ] `ccdash-artifact-usage-rollup-v1` JSON schema parses and validates sample payload
- [ ] Backward-compat assertion: existing artifact outcome tests still green
- [ ] Pydantic models round-trip serialize/deserialize without data loss
- [ ] TypeScript interfaces compile without errors; all optional BE fields marked `?`
- [ ] `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` env var present in config and `.env.example`
- [ ] Minimum 8 unit tests pass for schema validation
