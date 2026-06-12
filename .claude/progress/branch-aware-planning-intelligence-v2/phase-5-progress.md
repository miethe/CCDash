---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: batch-parallel
phase: 5
title: "Verification & Profiling"
status: pending
started: null
completed: null
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
owners:
  - python-backend-engineer
contributors: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T5-001
    description: "Multi-watcher integration tests — backend/tests/test_branch_watcher_integration.py: (1) N=2 watchers register/unregister cleanly; (2) startup hydration with N=2 active rows registers both; (3) missing-path row -> WARNING + no crash; (4) AC BWR-SEAM: INSERT triggers register(), terminal UPDATE triggers unregister(); (5) snapshot includes branch_watchers key with N=2 entries"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: ["P2-complete", "P3-complete", "P4-complete"]
    estimated_effort: "1.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T5-002
    description: "Write-amplification profiling (OQ-5) — N=3,4,5 simultaneous sync_changed_files via asyncio.gather; record p50/p95/p99 timings; commit to .claude/worknotes/branch-aware-planning-intelligence/wamp-profiling-report-v2.md; OQ-5 recorded as resolved or flagged with evidence"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T5-001]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T5-003
    description: "Runtime smoke check (R-P4 mandatory) — start dev stack; CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true; verify PlanningTopBar chip renders with branch; chip absent without registered worktree; no console errors; planning board loads. If runtime unavailable: document runtime_smoke: skipped with reason"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T5-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
parallelization:
  batch_1: [T5-001]
  batch_2: [T5-002, T5-003]
  critical_path: [T5-001, T5-002]
  estimated_total_time: "2.5 pt serial + 0.5 pt parallel"
blockers: []
success_criteria:
  - { id: SC-P5-1, description: "All 5 multi-watcher integration scenarios pass; snapshot contract confirmed (T5-001)", status: pending }
  - { id: SC-P5-2, description: "Profiling report committed with p50/p95/p99 at N=3,4,5; OQ-5 recorded as resolved or flagged with evidence (T5-002)", status: pending }
  - { id: SC-P5-3, description: "N<=5 envelope confirmed or flagged with evidence (T5-002)", status: pending }
  - { id: SC-P5-4, description: "Runtime smoke completed or runtime_smoke: skipped with documented reason; AC DEF003-CHIP-SMOKE verified (T5-003)", status: pending }
  - { id: SC-P5-5, description: "task-completion-validator passes; karen milestone sign-off required", status: pending }
files_modified:
  - backend/tests/test_branch_watcher_integration.py
  - backend/tests/test_branch_correlation.py
  - .claude/worknotes/branch-aware-planning-intelligence/wamp-profiling-report-v2.md
---

# branch-aware-planning-intelligence v2 — Phase 5: Verification & Profiling

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

> **R-P4 runtime smoke**: T5-003 is the mandatory runtime smoke task for P4's `*.tsx` changes.
> Per project rule: if runtime unavailable, document `runtime_smoke: skipped` with reason; a clean
> unit-test pass is NOT a substitute for marking P5 complete.
> **Dependency**: P2 + P3 + P4 must ALL be complete before this phase begins.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-5-progress.md \
  -t T5-001 -s in_progress
```

---

## Objective

Run the full multi-watcher integration suite (N=2–3 scenarios proving the BWR-SEAM, startup
hydration, and snapshot contract), execute write-amplification profiling at N=3/4/5 to confirm
the OQ-5 N≤5 operational envelope, and perform the mandatory R-P4 runtime smoke for the
`PlanningTopBar` DEF-003 chip. This phase gates the docs phase (P6). **karen milestone at exit.**

**Dependency**: P2 (BranchWatcherRegistry) + P3 (S2 correlation) + P4 (DEF-003 chip) all complete.

---

## Exit Gate (karen milestone)

- [ ] T5-001: Multi-watcher integration tests pass (all 5 scenarios)
- [ ] T5-002: Profiling report committed; OQ-5 recorded as resolved or flagged with evidence; N≤5 envelope confirmed
- [ ] T5-003: Runtime smoke completed or `runtime_smoke: skipped` with documented reason; AC DEF003-CHIP-SMOKE verified
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T5-001 | python-backend-engineer | sonnet | adaptive | P2+P3+P4-complete |
| T5-002 | python-backend-engineer | sonnet | adaptive | T5-001 |
| T5-003 | python-backend-engineer | sonnet | adaptive | T5-001 |

**Batch execution**: T5-001 solo → T5-002 + T5-003 in parallel.
