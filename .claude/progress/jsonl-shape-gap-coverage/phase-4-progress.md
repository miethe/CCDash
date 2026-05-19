---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 4
phase_title: "Transcript & Session Inspector Rendering (FE)"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["ui-engineer-enhanced"]
contributors: ["frontend-developer"]

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 11
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T4-001"
    name: "Attachment cards in transcript"
    description: "Add collapsible AttachmentCard component to SessionInspector.tsx transcript log renderer. Card header: subtype icon + label. Body: subtype-relevant fields. Unknown subtype: generic 'attachment' card with '(no detail available)'. FE fallback (R-P2): card payload malformed or empty -> render header only, no throw."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.6 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-B1", "AC-C1"]
    files_affected:
      - "components/SessionInspector.tsx"

  - id: "T4-002"
    name: "Permission-mode chips"
    description: "Render {timestamp, mode} entries from permissionModeTransitions[] as chips inline at the correct timestamp position in the transcript timeline. FE fallback (R-P2): permissionModeTransitions null or empty -> no chips rendered, no error state."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.4 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-B4", "OQ-4 confirmed"]
    files_affected:
      - "components/SessionInspector.tsx"
      - "components/Planning/PlanningAgentSessionBoard.tsx"

  - id: "T4-003"
    name: "Turn-duration histogram"
    description: "Add small bar histogram in session summary panel driven by turnDurations[]. Tooltip: messageCount per turn. FE fallback (R-P2): turnDurations null or empty -> panel hidden entirely (not an empty chart frame)."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.4 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-B5", "AC-C2"]
    files_affected:
      - "components/SessionInspector.tsx"

  - id: "T4-004"
    name: "Away-summary banner"
    description: "Render most-recent awaySummaries entry as a collapsible banner at top of transcript. Label: 'Session summary (away)' + timestamp. FE fallback (R-P2): awaySummaries empty or null -> banner absent (no empty frame)."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.4 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-B5", "AC-C3"]
    files_affected:
      - "components/SessionInspector.tsx"

  - id: "T4-005"
    name: "promptId/leafUuid forensics row"
    description: "Render a 'Forensics' metadata row in session header showing promptId and leafUuid values. Values are copy-to-clipboard. FE fallback (R-P2): both null -> row absent; one null, one present -> partial display."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.3 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-A5", "AC-C5"]
    files_affected:
      - "components/SessionInspector.tsx"

  - id: "T4-006"
    name: "Attribution rollup panel"
    description: "Add skillsUsed + pluginsUsed rollup panel in session metadata/analytics tab AND in PlanningAgentSessionBoard.tsx expanded card. Each list: name -> count, sorted descending. FE fallback (R-P2): both lists empty or null -> panel hidden; one list present -> render only that list."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.4 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-A2", "AC-A3", "AC-C4"]
    files_affected:
      - "components/SessionInspector.tsx"
      - "components/Planning/PlanningAgentSessionBoard.tsx"

  - id: "T4-007"
    name: "sessionKind badge + snapshot-churn metric"
    description: "Render 'BG' badge on session list cards and PlanningAgentSessionBoard cards when sessionKind == 'bg'. Render snapshot-churn metric in session summary. Add ai-title provenance line and last-prompt resume hint row in session header. FE fallback (R-P2): sessionKind null -> no badge; leafUuid null -> no resume hint row."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.3 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-A1", "AC-B2", "AC-B3", "AC-C5"]
    files_affected:
      - "components/SessionInspector.tsx"
      - "components/Planning/PlanningAgentSessionBoard.tsx"

  - id: "T4-008"
    name: "Null-handling tests (R-P2 verification)"
    description: "One Vitest test per new component prop: null-input fixture confirms no render crash, no 'undefined' string, no empty placeholder shown when field must be absent."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007"]
    ac_refs: ["AC-A1", "AC-A3", "AC-B1", "AC-B3", "AC-B4", "AC-C2", "AC-C3", "AC-C5"]
    files_affected:
      - "components/__tests__/"
      - "services/__tests__/"

  - id: "T4-009"
    name: "FE unit tests (component rendering)"
    description: "One Vitest test per new component widget covering: data-present render, empty/null render, interaction (copy, expand)."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007"]
    ac_refs: ["AC-C1", "AC-C2", "AC-C3", "AC-C4", "AC-C5", "AC-C7"]
    files_affected:
      - "components/__tests__/"

  - id: "T4-010"
    name: "Perf guard (Risk 3 mitigation)"
    description: "Run codebase-explorer against existing virtualization patterns in SessionInspector.tsx. Confirm attachment cards lazy-render payload bodies on expand (not upfront). If existing virtualization present, verify it covers new card kinds."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T4-001", "T4-002", "T4-003", "T4-004", "T4-005", "T4-006", "T4-007"]
    ac_refs: ["Risk 3 mitigation"]
    files_affected:
      - "components/SessionInspector.tsx"

  - id: "T4-011"
    name: "Phase reviewer gate"
    description: "task-completion-validator confirms: all R-P2 null-handling tests pass; Vitest suite green; no 'undefined' string literals in new component render paths."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T4-008", "T4-009", "T4-010"]
    ac_refs: ["R-P2", "R-P4"]
    files_affected: []

parallelization:
  batch_1: ["T4-001", "T4-002", "T4-003", "T4-004"]
  batch_2: ["T4-005", "T4-006", "T4-007"]
  batch_3: ["T4-008", "T4-009", "T4-010"]
  batch_4: ["T4-011"]
  critical_path: ["T4-001", "T4-008", "T4-011"]

blockers: []

success_criteria:
  - { id: "SC-P4-1", description: "All new component widgets render with data-present and null/empty fixtures.", status: "pending" }
  - { id: "SC-P4-2", description: "No 'undefined' strings, no crashes on missing fields.", status: "pending" }
  - { id: "SC-P4-3", description: "Visual evidence screenshots captured for AC-B1, AC-B4, AC-C2, AC-C3 at desktop >= 1440px.", status: "pending" }
  - { id: "SC-P4-4", description: "Lazy-render confirmed for attachment card bodies.", status: "pending" }
  - { id: "SC-P4-5", description: "Vitest suite passes (no regressions).", status: "pending" }
  - { id: "SC-P4-6", description: "task-completion-validator sign-off.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 4: Transcript & Session Inspector Rendering (FE)

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-4-progress.md \
  -t T4-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update batch_1 (parallel)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-4-progress.md \
  --updates "T4-001:completed,T4-002:completed,T4-003:completed,T4-004:completed"

# Batch update batch_2 (parallel)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-4-progress.md \
  --updates "T4-005:completed,T4-006:completed,T4-007:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-4-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-4-progress.md
```
