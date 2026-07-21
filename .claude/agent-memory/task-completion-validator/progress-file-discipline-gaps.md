---
name: progress-file-discipline-gaps
description: Recurring pattern in CCDash phase-execution runs — a task summary claims "[completed]" with a commit ref, but the phase progress YAML frontmatter still shows status:pending for that task, and/or a reported mid-phase blocker never gets written into the YAML blockers:[] field.
metadata:
  type: project
---

Observed 2026-07-21 in `.claude/progress/research-foundry-run-telemetry/phase-3-progress.md`:
T3-000 (backend-architect seam task) was reported as `[completed] commit:e3d10af` in the task
summary handed to the reviewer, and the commit is real and substantive (173-line contract-mapping
doc). But the progress YAML's `T3-000` entry still shows `status: pending`, no `started`/`completed`
timestamps, no `evidence` block. Separately, T3-006's own completion report describes a detailed
disk-full (ENOSPC) blocker mid-task, but the YAML's top-level `blockers: []` was never updated to
record it — the Error Recovery policy in the dev-execution skill explicitly requires "Document the
blocker in progress tracker," and that step was skipped even though the same session correctly used
`update-status.py` for T3-001 through T3-005.

**Why:** the progress YAML is the single source of truth other agents/reviewers read cheaply (vs.
re-deriving from git log / task summaries). A completed-looking task summary is not sufficient
evidence on its own — the CLI-first update step is a separate, sometimes-skipped action.

**How to apply:** as a reviewer, always diff the task summary's claimed status against the actual
progress YAML for every task, not just the ones flagged as blocked. A real git commit existing does
not imply the tracker was updated; check both independently. Flag any task marked `[completed]` in
prose but `pending` in YAML as a required fix (cheap CLI-script fix, not a rejection of the
underlying work) — see [[env-disk-full-hazard]] for the related blocker-recording gap.
