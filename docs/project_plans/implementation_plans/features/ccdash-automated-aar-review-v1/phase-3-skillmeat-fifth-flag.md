---
schema_version: 2
doc_type: phase_plan
title: "Phase 3: SkillMeat Artifact-Review Linkage + 5th Flag"
status: draft
created: 2026-07-22
phase: 3
phase_title: "SkillMeat Artifact-Review Linkage + 5th Flag"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- Phase 2 sealed (enrichment evidence contract frozen; no-LLM test green).
exit_criteria:
- 5th flag (new_skill_or_agent_need) unit-tested against fixtures.
- SkillMeat linkage is deterministic and strictly read-only.
- Recommendation evidence is attached to flag output; no SkillMeat catalog mutation exists anywhere
  in the diff.
---

# Phase 3: SkillMeat Artifact-Review Linkage + 5th Flag

**Duration**: ~0.5-1 sprint
**Dependencies**: Phase 2 sealed (task-level scaffolding may start once Phase 2's evidence contract, T2-001, is frozen)
**Assigned Subagent(s)**: `python-backend-engineer` (sole agent per decisions block §2 — consumes existing `artifact_intelligence` read APIs)
**Points**: 3-5 (decisions block §4 anchor: H3 — 5th flag = ranking-lookup + threshold correlation,
>=3 pts; SkillMeat read wiring is low plumbing since the service already exists)

## Overview

Wire `ArtifactIntelligenceQueryService` rankings/recommendations into the `stack_ineffectiveness`
flag's evidence, and implement the 5th canonical flag `new_skill_or_agent_need`: a deterministic
correlation of (a) repeated `generic_agent_vs_specialist` triggers at volume and (b) repeated
`missing_artifacts` patterns across a project, cross-referenced against SkillMeat effectiveness/cost
rankings. Recommendation output is **evidence only** (drafts) — never a catalog mutation (Hard
Invariant #2).

**Boundary rationale** (decisions block §1): the full verdict (all 5 flags + reconciled 3-value) must
exist before it is rendered/exposed in Phase 4.

## Deterministic Rule Annotations (OQ-7 compliance)

- `new_skill_or_agent_need` is a **threshold-over-aggregation** rule: count of
  `generic_agent_vs_specialist` triggers + count of `missing_artifacts` triggers, aggregated per
  project over a bounded lookback window, compared against a static configured threshold. No
  semantic "should we build a new skill" judgment is computed — that call stays upstream in
  op/ARC synthesis.
- SkillMeat ranking correlation is a **lookup** against
  `ArtifactIntelligenceQueryService`'s existing ranking/recommendation output — read-only, no new
  ranking logic invented in this repo.

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T3-001 | Wire `ArtifactIntelligenceQueryService` into `stack_ineffectiveness` | Read existing rankings/recommendations from `artifact_intelligence.py` and attach as additional evidence to `stack_ineffectiveness` when a matching stack/tool signature has a known SkillMeat ranking. | Evidence includes the SkillMeat ranking/recommendation reference when a match exists; flag trigger logic (from Phase 1/2) is unchanged. | 1 pt | python-backend-engineer | sonnet | adaptive | Phase 2 sealed |
| T3-002 | Implement `new_skill_or_agent_need` (5th flag) | Implement the deterministic aggregation rule: count `generic_agent_vs_specialist` + `missing_artifacts` triggers per project over a bounded lookback window; compare against a static, env-configurable threshold; cross-reference SkillMeat effectiveness/cost rankings for the implicated task domain. | Flag triggers only when the aggregation crosses the threshold; evidence names the trigger count, window, and any correlated SkillMeat ranking. | 2 pts | python-backend-engineer | sonnet | adaptive | T3-001 |
| T3-003 | Attach recommendation-draft evidence (read-only) | Attach a recommendation *evidence* string (e.g., "SkillMeat ranks skill X above the currently-used generic agent for this task domain") to the 5th flag's output — never a SkillMeat catalog write, never an artifact creation call. | Recommendation text is a plain evidence string in the DTO, sourced from existing `artifact_intelligence` read output only. | 1 pt | python-backend-engineer | sonnet | adaptive | T3-002 |
| T3-004 | 5th-flag fixture suite | Build/extend fixtures: below-threshold, at-threshold, above-threshold aggregation counts; with and without a matching SkillMeat ranking. | Fixture suite unit-tested and green across all combinations. | 1 pt | python-backend-engineer | sonnet | adaptive | T3-002, T3-003 |
| T3-005 | No-write review checklist (Hard Invariant #2) | Manual diff review confirming zero SkillMeat/skills/agents catalog mutation calls, zero ARC/swarm dispatch calls, anywhere in the Phase 3 diff. | Checklist recorded in this phase's progress notes; `task-completion-validator` confirms during its pass. | 0.5 pt | backend-architect | sonnet | adaptive | T3-001, T3-002, T3-003 |

## Structured Acceptance Criteria

#### AC P3.1: SkillMeat linkage is read-only (Hard Invariant #2)
- target_surfaces:
    - backend/application/services/agent_queries/aar_review.py
    - backend/application/services/agent_queries/artifact_intelligence.py
- propagation_contract: `aar_review.py` calls only `artifact_intelligence.py`'s existing read methods
  (rankings/recommendations query surface); no new write method is added to
  `artifact_intelligence.py` and no SkillMeat API mutation call exists anywhere in this phase's diff.
- resilience: If no SkillMeat ranking exists for a given tool/stack signature, `stack_ineffectiveness`
  and `new_skill_or_agent_need` still evaluate on their non-SkillMeat evidence alone — absence of a
  ranking is a contract state ("no ranking available"), never an error.
- visual_evidence_required: false
- verified_by: [T3-005]

#### AC P3.2: 5th flag stays deterministic aggregation, never semantic recommendation authorship
- target_surfaces:
    - backend/application/services/agent_queries/aar_review.py
- propagation_contract: The threshold/window/count values feeding `new_skill_or_agent_need` are
  static configuration, not model-derived; the recommendation-evidence string (T3-003) is templated
  from existing ranking data, never generated by a model call.
- resilience: N/A (invariant AC).
- visual_evidence_required: false
- verified_by: [T3-004, T2-008 regression]

## Phase 3 Quality Gates

- [ ] 5th flag unit-tested across below/at/above-threshold cases.
- [ ] SkillMeat linkage confirmed read-only (no write method, no catalog mutation).
- [ ] Recommendation evidence attached, never a catalog write.
- [ ] `task-completion-validator` review passes; no-write checklist recorded.

## Phase 3 Success Criteria

All exit criteria in this file's frontmatter are met. The full 5-flag + reconciled 3-value verdict
now exists and is ready to be rendered/exposed in Phase 4.
