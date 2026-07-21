---
type: progress
schema_version: 2
doc_type: progress
prd: research-foundry-run-telemetry
feature_slug: research-foundry-run-telemetry
phase: 4
status: pending
created: 2026-07-21
updated: 2026-07-21
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
commit_refs: []
pr_refs: []

owners: ["documentation-writer", "changelog-generator", "karen", "task-completion-validator"]
contributors: []

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 12
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

tasks:
  - id: "T4-001"
    name: "DOC-006: DF-001 per-provider cost/quality splits spec"
    description: "Author docs/project_plans/design-specs/rf-per-provider-cost-quality-splits.md (maturity: idea — needs the source_cards ingestion decision first); prd_ref set to the parent PRD."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-002"
    name: "DOC-006: DF-002 useful-source-rate-by-domain spec"
    description: "Author docs/project_plans/design-specs/rf-useful-source-rate-by-domain.md (maturity: idea)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-003"
    name: "DOC-006: DF-003 extraction-failure-rate-by-extractor spec"
    description: "Author docs/project_plans/design-specs/rf-extraction-failure-rate-by-extractor.md (maturity: idea)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-004"
    name: "DOC-006: DF-004 search-to-report-latency spec"
    description: "Author docs/project_plans/design-specs/rf-search-to-report-latency.md (maturity: idea — needs RF to add a report-completion timestamp)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-005"
    name: "DOC-006: DF-005 claim-ledger panel spec"
    description: "Author docs/project_plans/design-specs/rf-claim-ledger-panel.md (maturity: idea — requires ingesting RF's claim ledger §11.4 as a new entity)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-006"
    name: "DOC-006: DF-006 SkillMeat-promotion panel spec"
    description: "Author docs/project_plans/design-specs/rf-skillmeat-promotion-panel.md (maturity: idea — cross-system, SkillMeat writeback tracking)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-007"
    name: "DOC-006: DF-007 IntentTree intent_id resolution spec"
    description: "Author docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md (maturity: idea — needs live IntentTree API access from CCDash's backend)."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 3 complete"]

  - id: "T4-008"
    name: "Operator guide"
    description: "Update or extend docs/guides/remote-ingest-operator-guide.md with the rf ingest source, CCDASH_RF_TELEMETRY_ENABLED flag, and the new capability string."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007"]

  - id: "T4-009"
    name: "CHANGELOG [Unreleased] entry"
    description: "Add an entry per .claude/specs/changelog-spec.md categorization rules; verify [Unreleased] contains an entry matching this feature before the release gate."
    status: pending
    assigned_to: ["changelog-generator"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 1-3 complete"]

  - id: "T4-010"
    name: "Plan/PRD frontmatter finalization"
    description: "Populate deferred_items_spec_refs (all 7 paths from T4-001–T4-007) in the parent plan; set commit_refs/files_affected/updated; confirm findings_doc_ref remains null or is finalized if populated."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007", "T4-008", "T4-009"]

  - id: "T4-011"
    name: "karen end-of-feature review"
    description: "Strict QA pass across all 4 phases: re-verify AC-1 through AC-5 are genuinely met (not superficially), confirm the AC coverage matrix is green, confirm D-001 dedup and dual-DDL parity gates actually passed rather than being marked complete without evidence."
    status: pending
    assigned_to: ["karen"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007", "T4-008", "T4-009", "T4-010"]
    ac_refs: ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"]

  - id: "T4-012"
    name: "Phase 4 completion review"
    description: "task-completion-validator verifies Phase 4's own task list (docs, specs, frontmatter) is genuinely complete."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007", "T4-008", "T4-009", "T4-010", "T4-011"]

parallelization:
  batch_1: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007", "T4-009"]
  batch_2: ["T4-008"]
  batch_3: ["T4-010"]
  batch_4: ["T4-011"]
  batch_5: ["T4-012"]
  critical_path: ["T4-001", "T4-008", "T4-010", "T4-011", "T4-012"]

blockers: []
---

# research-foundry-run-telemetry - Phase 4: Hardening + docs + deferred specs

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-4-progress.md \
  -t T4-001 -s completed \
  --started 2026-07-21T00:00Z --completed 2026-07-21T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-4-progress.md \
  --updates "T4-001:completed,T4-002:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-4-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-4-progress.md
```
