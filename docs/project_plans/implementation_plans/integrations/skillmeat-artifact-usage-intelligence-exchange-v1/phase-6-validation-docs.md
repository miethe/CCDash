---
schema_version: 3
doc_type: phase_plan
title: "Phase 6: Validation, Privacy & Docs"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 6
phase_title: "Validation, Privacy & Docs"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - All five phases complete and signed off
  - All P5 quality gates passed including runtime smoke T5-008
exit_criteria:
  - Full test suite green (contract, integration, calibration, privacy)
  - Privacy audit checklist signed off: no PII leaks in any export payload shape
  - Calibration report generated confirming recommendation precision
  - Operator docs exist covering snapshot health, export tuning, feature flags
  - CHANGELOG [Unreleased] entry authored
  - Deferred item design specs authored (DF-001, DF-002, DF-003)
  - Plan frontmatter complete (status, commit_refs, files_affected)
  - karen review at phase exit (Tier 3 final gate)
integration_owner: task-completion-validator
ui_touched: false
---

# Phase 6: Validation, Privacy & Docs

## Phase Overview

**Estimate**: 4 pts
**Duration**: ~3 days
**Dependencies**: All previous phases complete and signed off
**Assigned Subagent(s)**: task-completion-validator (primary), documentation-writer (docs), python-backend-engineer (any test fixes)

This is the cross-cutting validation phase. It tests the integrated system, not individual layers. Three independent verification activities can run in parallel: contract tests, privacy audit, and operator docs.

### Parallelization

```yaml
parallelization:
  batch_1:
    # Contract tests, privacy audit, and operator docs can all run in parallel
    - task: T6-001
      assigned_to: task-completion-validator
      model: sonnet
      effort: medium
    - task: T6-002
      assigned_to: task-completion-validator
      model: sonnet
      effort: medium
    - task: T6-003
      assigned_to: documentation-writer
      model: haiku
      effort: low
  batch_2:
    # Calibration review and CHANGELOG after contract/privacy pass
    - task: T6-004
      assigned_to: task-completion-validator
      model: sonnet
      effort: medium
      depends_on: [T6-001, T6-002]
    - task: T6-005
      assigned_to: documentation-writer
      model: haiku
      effort: low
      depends_on: [T6-003]
  batch_3:
    # Deferred item specs and plan finalization last
    - task: T6-006
      assigned_to: documentation-writer
      model: sonnet
      effort: medium
      depends_on: [T6-001, T6-002, T6-003, T6-004, T6-005]
    - task: T6-007
      assigned_to: documentation-writer
      model: haiku
      effort: low
      depends_on: [T6-001, T6-002, T6-003, T6-004, T6-005]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T6-001 | Contract and integration tests | Run and extend the full contract test suite: (1) SkillMeat snapshot fetch → store → query cycle with seeded SkillMeat fixture, (2) rollup export contract test against mock SkillMeat endpoint, (3) ranking API endpoint contract tests for all filter combinations, (4) recommendation API endpoint contract tests for all 7 types, (5) backward-compat assertion: existing artifact outcome endpoint still works. Fix any failures. | All 5 contract test categories pass. Backward-compat assertion green. No regressions in existing test suite. Test run output captured in CI-compatible format. | 1 pt | task-completion-validator | sonnet | medium | All phases complete |
| T6-002 | Privacy audit | Perform end-to-end privacy audit of all export payload shapes: (1) ArtifactUsageRollup — verify no raw_prompt, transcript_text, source_code, absolute_path, unhashed_username, (2) SnapshotFetchRequest — verify no sensitive project metadata leaks, (3) ArtifactRecommendation embed in rollup — verify only advisory fields, (4) user_scope field — verify local mode uses pseudonym or omits, (5) logs audit — verify log statements don't emit sensitive values. Produce a privacy checklist document. | Privacy checklist authored and all 5 audit areas signed off. Test: `test_rollup_privacy.py` passes with enhanced assertions. Test: structured logs for snapshot fetch and rollup export contain no sensitive values. Document: `docs/guides/artifact-intelligence-privacy-audit.md` created with findings and sign-off. | 1 pt | task-completion-validator | sonnet | medium | All phases complete |
| T6-003 | Operator docs | Author operator documentation for the artifact intelligence feature. Cover: (1) enabling the feature (`CCDASH_ARTIFACT_INTELLIGENCE_ENABLED`), (2) SkillMeat snapshot configuration (project ID, collection ID, freshness thresholds), (3) rollup export configuration (interval, user scope mode), (4) interpreting snapshot health in Settings, (5) recommendation types and their staleness thresholds, (6) troubleshooting: snapshot fetch failures, identity resolution issues, privacy guard rejections. | `docs/guides/artifact-intelligence-operator-guide.md` authored. All 6 topics covered. Config var table present. Troubleshooting section has actionable steps for each failure mode. Concise and usage-focused (not verbose — follow doc-finalization-guidance verbosity standards). | 0.5 pts | documentation-writer | haiku | low | None (parallel with T6-001, T6-002) |
| T6-004 | Recommendation calibration review | Generate calibration report from seeded attribution data. Assess: (1) recommendation precision — manually review 10 sample recommendations against expected types, (2) false positive risk — identify any recommendations that could harm users if acted on without context, (3) confidence calibration — verify confidence scores correlate with actual accuracy in seeded data, (4) staleness gating — verify all destructive recommendations are suppressed for stale snapshot. Document findings in a calibration report. | Calibration report generated at `docs/guides/artifact-intelligence-calibration-report-v1.md`. 10 sample recommendations reviewed. False positive risk items identified (if any) and noted for V2. Confidence calibration assessed. All staleness gating verified correct. | 0.5 pts | task-completion-validator | sonnet | medium | T6-001, T6-002 |
| T6-005 | CHANGELOG entry | Add CHANGELOG `[Unreleased]` entry for the artifact intelligence feature. Entry must cover: Added artifact rankings view in Analytics, Added artifact optimization recommendations in Execution Workbench, Added SkillMeat snapshot health in Settings, Added `ccdash artifact` CLI commands and MCP tool. Follow changelog-spec.md categorization rules. | CHANGELOG `[Unreleased]` section contains correct categorized entries for all user-facing additions. `changelog_ref` frontmatter set to `CHANGELOG.md` in main plan. No internal implementation details in changelog. | 0.5 pts | documentation-writer | haiku | low | T6-003 |
| T6-006 | Deferred item design specs (DOC-006) | Author design specs for all three deferred items: (1) `docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md` (DF-001: per-user rollups in local mode — maturity: shaping, prd_ref set), (2) `docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md` (DF-002: recommendation outcomes as training signals — maturity: shaping), (3) `docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md` (DF-003: collection rankings for non-deployed artifacts — maturity: idea). Append all three paths to `deferred_items_spec_refs` in main plan frontmatter. | All three design specs authored with required frontmatter (schema_version: 2, doc_type: design_spec, maturity, prd_ref, problem_statement). `deferred_items_spec_refs` in main plan frontmatter populated with all three paths. Each spec is concise (not full implementation spec — this is a shaping/idea-level placeholder). | 0.5 pts | documentation-writer | sonnet | medium | T6-001, T6-002, T6-003, T6-004, T6-005 |
| T6-007 | Plan frontmatter finalization (DOC-005) | Update main implementation plan frontmatter: set `status: completed`, populate `commit_refs`, `files_affected`, `changelog_ref`, `deferred_items_spec_refs`, `updated` date. Update CLAUDE.md with artifact intelligence pointer (≤3 lines). Update any affected key-context files. | Main plan frontmatter fully populated. CLAUDE.md pointer added (one-liner + path reference). `deferred_items_spec_refs` populated. `findings_doc_ref` set if any findings were captured during execution (null otherwise). | 0.5 pts | documentation-writer | haiku | low | T6-001 through T6-006 |

---

## Privacy Audit Checklist (Reference)

The following fields are explicitly prohibited from all export payloads:

| Field | Reason |
|-------|--------|
| `raw_prompt` / `prompt_text` | Raw session content |
| `transcript_text` / `message_content` | Session transcript |
| `source_code` / `code_snippet` | Local source code |
| `absolute_path` / `file_path` | Local filesystem paths |
| `unhashed_username` / `user_email` | Personally identifiable user data |
| `api_key` / `token` / `secret` | Credentials |

The following fields are **permitted** in rollup payloads:

| Field | Justification |
|-------|--------------|
| `exclusive_tokens` | Aggregate metric, not raw content |
| `supporting_tokens` | Aggregate metric |
| `cost_usd_model_io` | Derived metric |
| `session_count` | Aggregate count |
| `workflow_count` | Aggregate count |
| `success_score`, `efficiency_score`, `quality_score`, `risk_score` | Derived effectiveness scores |
| `user_scope` | Hosted: auth principal scope; Local: pseudonym or omitted |
| `artifact_uuid`, `version_id`, `content_hash` | SkillMeat-defined artifact identity |
| `recommendation` fields | Advisory metadata, no content |

---

## Deferred Items Completion Checklist

- [ ] DF-001 design spec authored: `docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md`
- [ ] DF-002 design spec authored: `docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md`
- [ ] DF-003 design spec authored: `docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md`
- [ ] `deferred_items_spec_refs` in main plan frontmatter populated with all three paths

---

## Quality Gates

- [ ] All contract test categories pass (5 categories)
- [ ] Backward-compat assertion green: existing artifact outcome endpoint unaffected
- [ ] Privacy audit checklist signed off for all 5 audit areas
- [ ] Privacy assertion tests pass with enhanced rollup payload assertions
- [ ] Operator guide authored at `docs/guides/artifact-intelligence-operator-guide.md`
- [ ] Calibration report generated and reviewed
- [ ] CHANGELOG `[Unreleased]` entry present and correctly categorized
- [ ] All three deferred item design specs authored and paths in `deferred_items_spec_refs`
- [ ] Main plan frontmatter complete (status, commit_refs, files_affected, changelog_ref)
- [ ] CLAUDE.md pointer added (≤3 lines)
- [ ] `findings_doc_ref` set or confirmed null
- [ ] **karen final review at phase exit (Tier 3 mandatory gate)**
