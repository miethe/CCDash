---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 6
phase_title: "Integration Seams + Cross-Surface Smoke"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["task-completion-validator"]
contributors: ["ui-engineer-enhanced"]

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T6-001"
    name: "Seam test: JSONL -> parser -> DB"
    description: "Parse a fixture JSONL containing all new event types; assert DB row has all 11 new columns populated correctly; confirm no data loss in attachment system-log entries."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.15 pt"
    dependencies: ["T4-011", "T5-006"]
    ac_refs: ["AC-B1", "AC-B5", "R-P3 seam (P1 <-> P4)"]
    files_affected:
      - "backend/tests/"

  - id: "T6-002"
    name: "Seam test: API -> FE type consistency"
    description: "Verify GET /api/sessions/{id} response shape matches types.ts AgentSession interface field-for-field. No type mismatch between P3 API changes and P4 FE component props."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.1 pt"
    dependencies: ["T4-011", "T5-006"]
    ac_refs: ["R-P3 seam (P3 <-> P4)"]
    files_affected: []

  - id: "T6-003"
    name: "Runtime smoke: new-shape JSONL session"
    description: "Start dev server; open Session Inspector on a fixture session with all new fields. Enumerate R-P1 target_surfaces: (1) SessionInspector.tsx -- attachment cards, permission-mode chips, turn-duration histogram, away-summary banner, promptId/leafUuid forensics row, attribution rollup panel; (2) PlanningAgentSessionBoard.tsx -- sessionKind badge, attribution panel. Assert each surface renders its data. Console must be clean."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.15 pt"
    dependencies: ["T6-001", "T6-002"]
    ac_refs: ["R-P4", "AC-B1", "AC-B4", "AC-C1", "AC-C2", "AC-C3", "AC-C4", "AC-C5"]
    files_affected: []

  - id: "T6-004"
    name: "Runtime smoke: pre-enrichment session (R-P2 verification)"
    description: "Open Session Inspector on a pre-enrichment JSONL session (all new fields absent). Assert: no '---' gap visual noise, no empty placeholder frames, no console errors. Specifically check: no BG badge, no permission chips, no histogram, no away banner, no forensics row, no attribution panel."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T6-001", "T6-002"]
    ac_refs: ["R-P2", "Risk 5 mitigation"]
    files_affected: []

  - id: "T6-005"
    name: "Regression: existing parser + FE tests"
    description: "Run full test suite; confirm no regressions in any existing parser branch, repository, or FE component tests."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T6-003", "T6-004"]
    ac_refs: ["General regression gate"]
    files_affected: []

  - id: "T6-006"
    name: "Phase reviewer + karen end-of-feature"
    description: "task-completion-validator final review with smoke artifact attached. karen end-of-feature pass: confirm all AC-A1...A6, AC-B1...B5, AC-C1...C7 are verifiably covered; no open AC without a verified_by task."
    status: pending
    assigned_to: ["task-completion-validator", "karen"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T6-005"]
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6", "AC-B1", "AC-B2", "AC-B3", "AC-B4", "AC-B5", "AC-C1", "AC-C2", "AC-C3", "AC-C4", "AC-C5", "AC-C6", "AC-C7"]
    files_affected: []

parallelization:
  batch_1: ["T6-001", "T6-002"]
  batch_2: ["T6-003", "T6-004"]
  batch_3: ["T6-005", "T6-006"]
  critical_path: ["T6-001", "T6-003", "T6-005", "T6-006"]

blockers: []

success_criteria:
  - { id: "SC-P6-1", description: "JSONL->DB seam test passes for all 11 new columns.", status: "pending" }
  - { id: "SC-P6-2", description: "API->FE type seam: zero TypeScript type errors.", status: "pending" }
  - { id: "SC-P6-3", description: "Runtime smoke (new-shape): all 8 R-P1 target surfaces render data; console clean.", status: "pending" }
  - { id: "SC-P6-4", description: "Runtime smoke (pre-enrichment): all R-P2 fallbacks active; no visual noise; console clean.", status: "pending" }
  - { id: "SC-P6-5", description: "All existing tests pass (zero regressions).", status: "pending" }
  - { id: "SC-P6-6", description: "task-completion-validator sign-off with smoke artifact.", status: "pending" }
  - { id: "SC-P6-7", description: "karen end-of-feature approval.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 6: Integration Seams + Cross-Surface Smoke

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-6-progress.md \
  -t T6-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update batch_1 (parallel seam tests)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-6-progress.md \
  --updates "T6-001:completed,T6-002:completed"

# Batch update batch_2 (runtime smoke)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-6-progress.md \
  --updates "T6-003:completed,T6-004:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-6-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-6-progress.md
```
