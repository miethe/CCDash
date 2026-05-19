---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 7
phase_title: "Documentation Finalization"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["documentation-writer"]
contributors: ["ai-artifacts-engineer"]

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 9
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "haiku"
  external: []

tasks:
  - id: "T7-001"
    name: "CHANGELOG [Unreleased] entry"
    description: "Add [Unreleased] entry under Added category covering: new attachment/permission-mode/turn-duration/away-summary surfaces in Session Inspector; sessionKind background-session labeling; promptId/leafUuid forensics search via CLI (--prompt-id, --leaf-uuid) and MCP; attribution rollup panel."
    status: pending
    assigned_to: ["changelog-generator"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.15 pt"
    dependencies: ["T6-006"]
    ac_refs: ["changelog_required: true"]
    files_affected:
      - "CHANGELOG.md"

  - id: "T7-002"
    name: "README + CLI guide delta"
    description: "Update docs/guides/ with new CLI flags: --prompt-id usage, --leaf-uuid usage, attribution breakdown. Update any README section referencing session parse capabilities."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.15 pt"
    dependencies: ["T6-006"]
    ac_refs: ["AC-C6 (docs)"]
    files_affected:
      - "docs/guides/"
      - "README.md"

  - id: "T7-003"
    name: "CLAUDE.md session-data pointer"
    description: "If parser conventions change in a way agents must know (new event type handling, new field names), add a one-liner + path reference to CLAUDE.md §Session data. Max 3 lines per addition."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T6-006"]
    ac_refs: []
    files_affected:
      - "CLAUDE.md"

  - id: "T7-004"
    name: "ccdash skill SPEC update (CONDITIONAL)"
    description: "CONDITION: P5 ships new CLI commands (--prompt-id, --leaf-uuid, --attribution-plugin, --attribution-skill). If condition true: update .claude/skills/ccdash/SPEC.md Capability Coverage matrix; bump SPEC.md Changelog + updated date. If false: skip with note 'N/A - no new CLI command syntax'."
    status: pending
    assigned_to: ["ai-artifacts-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T6-006"]
    ac_refs: ["OQ per decisions block §7"]
    files_affected:
      - ".claude/skills/ccdash/SPEC.md"

  - id: "T7-005"
    name: "cli-timeout-debugging cross-link (CONDITIONAL)"
    description: "CONDITION: Forensics CLI flags (--prompt-id, --leaf-uuid) introduce timeout-sensitive behavior. If condition true: add cross-link in docs/guides/cli-timeout-debugging.md referencing these flags and recommended --timeout values. If false: skip."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T6-006"]
    ac_refs: []
    files_affected:
      - "docs/guides/cli-timeout-debugging.md"

  - id: "T7-006"
    name: "Plan frontmatter finalization"
    description: "Set status: completed; populate commit_refs, pr_refs, files_affected, updated in this plan's frontmatter."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T7-001", "T7-002", "T7-003"]
    ac_refs: []
    files_affected:
      - "docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md"

  - id: "T7-007"
    name: "Deferred items + findings confirmation"
    description: "Confirm deferred items triage table is N/A (no deferred items). If findings_doc_ref was populated during execution, finalize findings doc status draft -> accepted."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T7-001", "T7-002", "T7-003"]
    ac_refs: []
    files_affected: []

  - id: "T7-008"
    name: "Feature guide"
    description: "Create .claude/worknotes/jsonl-shape-gap-coverage/feature-guide.md. Sections: What Was Built (new transcript surfaces, forensics CLI/MCP, attribution rollup), Architecture Overview (parser -> models -> repositories -> routers -> agent_queries -> FE), How to Test (fixture commands, CLI examples), Test Coverage Summary, Known Limitations (backfill excluded; historical sessions show '---')."
    status: pending
    assigned_to: ["documentation-writer"]
    assigned_model: haiku
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T7-001", "T7-002", "T7-003"]
    ac_refs: []
    files_affected:
      - ".claude/worknotes/jsonl-shape-gap-coverage/feature-guide.md"

  - id: "T7-009"
    name: "Phase reviewer gate"
    description: "task-completion-validator confirms: CHANGELOG entry present and correctly categorized; conditional tasks resolved with documented outcome."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "—"
    dependencies: ["T7-006", "T7-007", "T7-008"]
    ac_refs: []
    files_affected: []

parallelization:
  batch_1: ["T7-001", "T7-002", "T7-003"]
  batch_2: ["T7-004", "T7-005"]
  batch_3: ["T7-006", "T7-007", "T7-008"]
  batch_4: ["T7-009"]
  critical_path: ["T7-001", "T7-006", "T7-009"]

blockers: []

success_criteria:
  - { id: "SC-P7-1", description: "CHANGELOG [Unreleased] entry present under Added category.", status: "pending" }
  - { id: "SC-P7-2", description: "CLI guide updated with --prompt-id and --leaf-uuid examples.", status: "pending" }
  - { id: "SC-P7-3", description: "CLAUDE.md updated (or confirmed unchanged with note).", status: "pending" }
  - { id: "SC-P7-4", description: "T7-004 and T7-005 resolved (shipped or explicitly marked N/A).", status: "pending" }
  - { id: "SC-P7-5", description: "Plan frontmatter complete (status: completed).", status: "pending" }
  - { id: "SC-P7-6", description: "Deferred items confirmed N/A; findings doc finalized if any.", status: "pending" }
  - { id: "SC-P7-7", description: "Feature guide created.", status: "pending" }
  - { id: "SC-P7-8", description: "task-completion-validator sign-off.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 7: Documentation Finalization

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-7-progress.md \
  -t T7-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update batch_1 (parallel)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-7-progress.md \
  --updates "T7-001:completed,T7-002:completed,T7-003:completed"

# Batch update batch_2 (conditional tasks)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-7-progress.md \
  --updates "T7-004:completed,T7-005:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-7-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-7-progress.md
```
