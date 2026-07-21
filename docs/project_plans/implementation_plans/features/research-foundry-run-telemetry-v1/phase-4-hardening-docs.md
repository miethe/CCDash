---
title: "Phase 4: Hardening + docs + deferred specs"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-21
updated: 2026-07-21
feature_slug: "research-foundry-run-telemetry"
feature_version: "v1"
phase: 4
phase_title: "Hardening + docs + deferred specs"
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
entry_criteria:
  - "Phase 3 exit gate passed: Provider Economics tab runtime-smoked at >=1440px"
exit_criteria:
  - "All 7 DOC-006 deferred-item specs authored; deferred_items_spec_refs populated in parent plan"
  - "Operator guide + CHANGELOG entry landed"
  - "karen end-of-feature review passed; AC coverage matrix green"
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: []
owner: null
contributors: []
priority: medium
risk_level: low
category: "product-planning"
tags: [phase-plan, implementation, docs, deferred-items, karen-gate]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - docs/guides/remote-ingest-operator-guide.md
  - CHANGELOG.md
  - docs/project_plans/design-specs/rf-per-provider-cost-quality-splits.md
  - docs/project_plans/design-specs/rf-useful-source-rate-by-domain.md
  - docs/project_plans/design-specs/rf-extraction-failure-rate-by-extractor.md
  - docs/project_plans/design-specs/rf-search-to-report-latency.md
  - docs/project_plans/design-specs/rf-claim-ledger-panel.md
  - docs/project_plans/design-specs/rf-skillmeat-promotion-panel.md
  - docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md
---

# Phase 4: Hardening + docs + deferred specs

**Parent Plan**: [Research Foundry Run Telemetry — Implementation Plan](../research-foundry-run-telemetry-v1.md)
**Duration**: ~0.5–1 week
**Effort**: 6 story points
**Dependencies**: Phase 3 complete (MVP scope locked, so deferred-item specs describe what actually shipped)
**Team Members**: `documentation-writer`, `changelog-generator`, `karen`, `task-completion-validator`

---

## Phase Overview

This phase closes out the feature: operator-facing docs, the CHANGELOG entry, and — per the
mandatory DOC-006 rule — **one design-spec authoring task per deferred item** named in PRD §12,
rather than a single bundled "deferred specs" line item. Each of the 7 rows in the PRD's Contract
Reality / Deferred Items table gets its own task, its own spec file, and its own entry in
`deferred_items_spec_refs`.

### Goals

- Author all 7 DOC-006 deferred-item design specs (DF-001–DF-007).
- Operator guide covering the new `rf` ingest source + `CCDASH_RF_TELEMETRY_ENABLED` flag.
- CHANGELOG `[Unreleased]` entry (this PRD sets `changelog_required: true`).
- `karen` end-of-feature review + AC coverage matrix green across all 5 structured ACs (AC-1–AC-5).

### Architecture Focus

- **Layer**: Documentation Finalization
- **Patterns**: `.claude/skills/planning/references/deferred-items-and-findings.md` DOC-006 checklist
- **Standards**: `.claude/specs/changelog-spec.md` categorization rules

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|----------------------|----------|-------------|-------|--------|---------------|
| T4-001 | DOC-006: DF-001 per-provider cost/quality splits spec | Author `docs/project_plans/design-specs/rf-per-provider-cost-quality-splits.md` (`maturity: idea` — needs the `source_cards` ingestion decision first); `prd_ref` set to the parent PRD | Spec documents both unblock paths (RF schema v2 vs. `source_cards` join) | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-002 | DOC-006: DF-002 useful-source-rate-by-domain spec | Author `docs/project_plans/design-specs/rf-useful-source-rate-by-domain.md` (`maturity: idea`) | Spec names the `source_cards.url`/`canonical_url` dependency explicitly | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-003 | DOC-006: DF-003 extraction-failure-rate-by-extractor spec | Author `docs/project_plans/design-specs/rf-extraction-failure-rate-by-extractor.md` (`maturity: idea`) | Spec names the `source_card.extractor` dependency explicitly | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-004 | DOC-006: DF-004 search-to-report-latency spec | Author `docs/project_plans/design-specs/rf-search-to-report-latency.md` (`maturity: idea` — needs RF to add a report-completion timestamp) | Spec names the missing timestamp field as the precise unblock | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-005 | DOC-006: DF-005 claim-ledger panel spec | Author `docs/project_plans/design-specs/rf-claim-ledger-panel.md` (`maturity: idea` — requires ingesting RF's claim ledger §11.4 as a new entity) | Spec scopes the follow-up feature (new `claims` ingest + correlation to `research_runs`) | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-006 | DOC-006: DF-006 SkillMeat-promotion panel spec | Author `docs/project_plans/design-specs/rf-skillmeat-promotion-panel.md` (`maturity: idea` — cross-system, SkillMeat writeback tracking) | Spec names the `search_run.writebacks.skillmeat_candidate_ids` join as the unblock | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-007 | DOC-006: DF-007 IntentTree `intent_id` resolution spec | Author `docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md` (`maturity: idea` — needs live IntentTree API access from CCDash's backend) | Spec documents the opaque-string v1 behavior and the exact unblock condition (IntentTree API wiring) | 0.5 pts | documentation-writer | sonnet | adaptive | Phase 3 complete |
| T4-008 | Operator guide | Update or extend `docs/guides/remote-ingest-operator-guide.md` with the `rf` ingest source, `CCDASH_RF_TELEMETRY_ENABLED` flag, and the new capability string | Guide accurate and concise, matching existing operator-guide conventions | 0.5 pts | documentation-writer | haiku | adaptive | T4-001 through T4-007 |
| T4-009 | CHANGELOG `[Unreleased]` entry | Add an entry per `.claude/specs/changelog-spec.md` categorization rules; verify `[Unreleased]` contains an entry matching this feature before the release gate | Entry exists under `[Unreleased]`, correctly categorized; `changelog_ref` frontmatter set to `CHANGELOG.md` | 0.5 pts | changelog-generator | haiku | adaptive | Phase 1–3 complete |
| T4-010 | Plan/PRD frontmatter finalization | Populate `deferred_items_spec_refs` (all 7 paths from T4-001–T4-007) in the parent plan; set `commit_refs`/`files_affected`/`updated`; confirm `findings_doc_ref` remains `null` or is finalized if populated | Frontmatter lifecycle fields complete per `.claude/skills/artifact-tracking/schemas/field-reference.md` | 0.5 pts | documentation-writer | haiku | adaptive | T4-001 through T4-009 |
| T4-011 | `karen` end-of-feature review | Strict QA pass across all 4 phases: re-verify AC-1 through AC-5 are genuinely met (not superficially), confirm the AC coverage matrix is green, confirm D-001 dedup and dual-DDL parity gates actually passed rather than being marked complete without evidence | `karen` sign-off recorded; any gaps documented and blocking until resolved | 0.5 pts | karen | sonnet | adaptive | T4-001 through T4-010 |
| T4-012 | Phase 4 completion review | `task-completion-validator` verifies Phase 4's own task list (docs, specs, frontmatter) is genuinely complete | Reviewer sign-off recorded; feature ready for Wrap-Up (Feature Guide + PR) | 0.5 pts | task-completion-validator | sonnet | adaptive | T4-001 through T4-011 |

**Phase 4 total: 6 pts**

---

## Quality Gates

- [ ] All 7 DOC-006 specs authored with `prd_ref` set back to the parent PRD (T4-001–T4-007)
- [ ] `deferred_items_spec_refs` in the parent plan lists all 7 paths (T4-010)
- [ ] Operator guide updated (T4-008)
- [ ] CHANGELOG `[Unreleased]` entry present and correctly categorized (T4-009)
- [ ] `findings_doc_ref` finalized if populated, or confirmed `null` (T4-010)
- [ ] `karen` end-of-feature sign-off recorded, AC coverage matrix green across AC-1–AC-5 (T4-011)
- [ ] `task-completion-validator` sign-off recorded (T4-012)

---

## Key Files Modified

| File Path | Purpose | Subagent |
|-----------|---------|----------|
| `docs/guides/remote-ingest-operator-guide.md` | New `rf` source + flag documentation | documentation-writer |
| `CHANGELOG.md` | `[Unreleased]` entry | changelog-generator |
| `docs/project_plans/design-specs/rf-*.md` (×7) | DF-001–DF-007 deferred-item specs | documentation-writer |

---

## Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-21

[Return to Parent Plan](../research-foundry-run-telemetry-v1.md)
