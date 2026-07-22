---
schema_version: 2
doc_type: phase_plan
title: "Phase 7: Documentation Finalization + Deferred-Items Design Specs"
status: draft
created: 2026-07-22
phase: 7
phase_title: "Documentation Finalization + Deferred-Items Design Specs"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- Phase 6 sealed and its karen end-of-P4 milestone review passed.
exit_criteria:
- All docs land (CHANGELOG, CLAUDE.md pointer, capability/operator doc, LAN deployment note).
- DOC-006 covers every open/deferred item (OQ-3, OQ-4, OQ-6-if-unresolved) with a design spec or
  explicit N/A rationale.
- CHANGELOG [Unreleased] entry present.
- ac-coverage-report + validate-phase-completion clean.
---

# Phase 7: Documentation Finalization + Deferred-Items Design Specs

**Duration**: 0.5-1 day
**Dependencies**: Phase 6 sealed + karen milestone passed
**Assigned Subagent(s)**: `documentation-writer` (primary, haiku for most tasks), `changelog-generator`, `ai-artifacts-engineer` (only if a project skill's domain shifts)
**Points**: 2-3 (decisions block §4 anchor: H6 hidden-plumbing budget — docs, CHANGELOG, CLAUDE.md
pointer, DOC-006 design specs)

## Overview

Close out the remaining-work slice of the CCDash Automated AAR Review Loop with docs, a CHANGELOG
entry, a CLAUDE.md pointer, an operator/capability doc for the v1 LAN endpoint, and design specs for
every deferred/open item surfaced across Phases 1-6. **This is the end-of-feature milestone — requires
a `karen` review in addition to `task-completion-validator`.**

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| DOC-001 | Update CHANGELOG | Add a `[Unreleased]` entry covering: DTO reconciliation (schema_version bump), the new `aar_reviews` persisted rollup, the 5th flag, the FE review panel, the v1 LAN endpoint + `aar-review` capability, and the gated autonomous worker (flag-gated, default-off). Categorization rules in `.claude/specs/changelog-spec.md`. | Entry exists under `[Unreleased]` with correct categorization; `changelog_ref` frontmatter set to `CHANGELOG.md`. | 0.25 pt | changelog-generator | haiku | adaptive | Phase 6 sealed |
| DOC-002 | Update README (if applicable) | Rebuild README if CLI commands, endpoints, or screenshots changed for this feature. | README reflects current state or is confirmed N/A. | 0.25 pt | documentation-writer | haiku | adaptive | Phase 6 sealed |
| DOC-003 | Author operator/capability doc | Author or extend an operator-facing guide covering the v1 LAN `aar-review` endpoint, the `aar-review` capability string, and the `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` flag (default-off) — mirroring `docs/guides/external-api-lan-deployment.md`'s existing pattern. | Guide documents the endpoint, capability, and worker flag; cross-referenced from `external-api-lan-deployment.md` if that doc already exists. | 0.5 pt | documentation-writer | haiku | adaptive | Phase 6 sealed |
| DOC-004 | Update CLAUDE.md pointer + context files | Add a ≤3-line CLAUDE.md pointer for the AAR review loop (persisted rollup, flags, guards, worker flag) following progressive disclosure; update any affected key-context files. | Pointer added per progressive-disclosure convention (detail lives in a key-context file or this plan, not CLAUDE.md itself). | 0.5 pt | documentation-writer | haiku | adaptive | Phase 6 sealed |
| DOC-005 | Update plan frontmatter | Set `status: completed`, populate `commit_refs`, `files_affected`, `updated`; set `deferred_items_spec_refs` from DOC-006's output. | Frontmatter complete per the lifecycle spec. | 0.25 pt | documentation-writer | haiku | adaptive | DOC-001 through DOC-004 |
| DOC-006 | Author design specs for deferred items | For each row in the parent plan's Deferred Items Triage Table (OQ-3, OQ-4, and OQ-6-if-unresolved-per-Phase-5's T5-002), author a `design_spec` at the row's `Target Spec Path` with `maturity: shaping` (or `idea` if further research is needed), `prd_ref` set to the parent PRD, and append the resulting path to `deferred_items_spec_refs`. If Phase 5 fully resolved OQ-6 with no open follow-up, mark that row "N/A — resolved in Phase 5, see ADR addendum" instead of authoring a spec. | All 3 deferred items have a design_spec OR a documented N/A-with-rationale; `deferred_items_spec_refs` populated accordingly. | 1 pt | documentation-writer | sonnet | adaptive | Phase 6 sealed |
| DOC-007 | Finalize findings doc (if populated) | If `findings_doc_ref` was populated during any phase, ensure all findings are captured, advance status `draft` → `accepted`, populate `promoted_to`. Skip with "N/A — no findings captured" if `findings_doc_ref` is null. | Findings doc finalized OR marked N/A. | 0.25 pt | documentation-writer | haiku | adaptive | DOC-006 |
| DOC-008 | Update affected project-level skills | Check `.claude/specs/skills-index.md` for any custom skill whose domain this feature touches (e.g., a future `aar-review` operator skill). Update SPEC.md if applicable. Skip with "N/A — no project-level skill domains affected" if none apply. | All affected skills current, or documented N/A. | 0.5 pt | ai-artifacts-engineer, documentation-writer | sonnet | adaptive | Phase 6 sealed |

## Phase 7 Quality Gates

- [ ] CHANGELOG `[Unreleased]` section contains an entry matching this feature.
- [ ] Operator/capability doc authored (DOC-003).
- [ ] CLAUDE.md pointer + context files updated (DOC-004).
- [ ] Plan frontmatter complete (DOC-005).
- [ ] Design specs authored for all 3 deferred items (or documented N/A) — `deferred_items_spec_refs`
  populated (DOC-006).
- [ ] Findings doc finalized if any findings were captured (DOC-007).
- [ ] Project-level custom skills updated (or N/A) (DOC-008).
- [ ] `ac-coverage-report.py` and `validate-phase-completion.py` run clean across all 7 phases.
- [ ] `task-completion-validator` review passes.
- [ ] **`karen` end-of-feature review passes.**

## Phase 7 Success Criteria

All exit criteria in this file's frontmatter are met, the `karen` end-of-feature review has passed,
and the Wrap-Up (Feature Guide + PR) step in the parent plan may proceed.
