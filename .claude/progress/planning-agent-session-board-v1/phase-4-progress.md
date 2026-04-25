---
type: progress
schema_version: 2
doc_type: progress
prd: planning-agent-session-board-v1
feature_slug: planning-agent-session-board-v1
phase: 4
phase_title: Next-Run Prompt Preview and Context Composer
status: pending
created: '2026-04-25'
updated: '2026-04-25'
prd_ref: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: '2026-04-30'
ui_touched: true
owners:
- fullstack-engineering
contributors:
- ai-agents
tasks:
- id: PASB-401
  title: Preview Contract
  description: Define next-run preview DTO with command, prompt, context refs, transcript
    refs, and warnings.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - PASB-101
  acceptance_criteria:
  - Contract can represent /dev:execute-phase, /dev:quick-feature, or plan-specific
    continuation prompts.
  estimate: 2 pts
- id: PASB-402
  title: Prompt Composer
  description: Implement deterministic prompt composer from feature, phase, batch/task,
    selected sessions, and artifact refs.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - PASB-401
  acceptance_criteria:
  - Preview output is stable, copyable, and explains missing context warnings.
  estimate: 3 pts
- id: PASB-403
  title: Preview Panel UI
  description: Add UI for selecting prior sessions/context refs and rendering command
    plus prompt skeleton.
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-402
  acceptance_criteria:
  - User can inspect and copy command and prompt separately.
  estimate: 2 pts
- id: PASB-404
  title: Launch Sheet Alignment
  description: Where provider/model/worktree choices are shown, reuse existing launch
    preparation labels and constraints.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - PASB-403
  acceptance_criteria:
  - UI does not introduce a competing execution path or bypass approval semantics.
  estimate: 1 pt
- id: PASB-405
  title: Context Tray Interactions
  description: Add explicit controls to add/remove session cards, phase refs, artifact
    refs, and transcript refs from the prompt context tray.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - PASB-403
  acceptance_criteria:
  - Context selection is inspectable, reversible, and updates preview output immediately.
  estimate: 1 pt
- id: PASB-406
  title: Optional Drag-to-Compose
  description: Add drag-to-compose only if click and keyboard alternatives are implemented
    first.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-405
  acceptance_criteria:
  - Dragging a card adds context to preview only; it never executes or launches work.
  estimate: 1 pt
parallelization:
  batch_1:
  - PASB-401
  batch_2:
  - PASB-402
  batch_3:
  - PASB-403
  - PASB-404
  - PASB-405
  batch_4:
  - PASB-406
total_tasks: 6
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
progress: 33
---

# Phase 4: Next-Run Prompt Preview and Context Composer

## Objective
Generate a copyable CLI command and prompt skeleton for continuing work. Let users choose feature, phase, batch/task, prior sessions, and artifact refs. Keep flow copy/preview-only.

## Batch Execution Plan

### Batch 1: PASB-401 (Preview Contract)
Backend Pydantic models + endpoint skeleton + verify frontend types.

### Batch 2: PASB-402 (Prompt Composer)
Deterministic prompt composition service logic.

### Batch 3: PASB-403 + PASB-404 + PASB-405 (Parallel FE)
Preview panel UI, launch sheet alignment, context tray interactions.

### Batch 4: PASB-406 (Drag-to-Compose)
Optional drag-to-compose with click/keyboard alternatives.
