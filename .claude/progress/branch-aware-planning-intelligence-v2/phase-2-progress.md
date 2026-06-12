---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: batch-parallel
phase: 2
title: "BranchWatcherRegistry Infrastructure"
status: pending
started: null
completed: null
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
owners:
  - backend-architect
contributors:
  - python-backend-engineer
overall_progress: 0
completion_estimate: on-track
total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T2-001
    description: "BranchWatcherRegistry class — new backend/db/branch_watcher.py (OQ-2 resolution); keyed by (project_id, worktree_path); asyncio.Lock on all mutating ops; BranchWatcherEntry dataclass; no modification to FileWatcher.start()"
    status: pending
    assigned_to: [backend-architect]
    dependencies: ["P1-complete", "ADR-008-accepted"]
    estimated_effort: "2 pt"
    assigned_model: sonnet
    model_effort: extended
  - id: T2-002
    description: "register() / unregister() — derives docs_dir + progress_dir from worktree_path; sync_changed_files uses parent project_id (ADR-006); sessions dir excluded from watch scope; asyncio.Lock held during mutation"
    status: pending
    assigned_to: [backend-architect]
    dependencies: [T2-001]
    estimated_effort: "1.5 pt"
    assigned_model: sonnet
    model_effort: extended
  - id: T2-003
    description: "Container registration + stop_all() — register BranchWatcherRegistry in backend/runtime/container.py alongside FileWatcherRegistry; wire stop_all() from RuntimeJobAdapter.stop(); empty-registry no-op"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T2-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T2-004
    description: "Startup hydration + serialization (OQ-3 resolution) — runs after _run_all_projects_sync_job; loads active planning_worktree_contexts rows; register() for valid paths; WARNING + skip for missing paths (OQ-4 resolution); no unilateral terminal-status mutation"
    status: pending
    assigned_to: [backend-architect]
    dependencies: [T2-002, T2-003]
    estimated_effort: "1.5 pt"
    assigned_model: sonnet
    model_effort: extended
  - id: T2-005
    description: "Snapshot API extension — _watcher_registry_snapshot() gains parallel branch_watchers key; existing project_id-keyed dict unchanged; snapshot contract test confirms existing consumers unaffected"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T2-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T2-006
    description: "Seam integration test (R-P3 seam task) — INSERT with status='running' triggers register(); terminal UPDATE triggers unregister(); linting comment at call site: '# BranchWatcherRegistry call site — ADR-008 §3'; verifies AC BWR-SEAM"
    status: pending
    assigned_to: [backend-architect]
    dependencies: [T2-002, T2-004]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
parallelization:
  batch_1: [T2-001]
  batch_2: [T2-002, T2-003, T2-005]
  batch_3: [T2-004]
  batch_4: [T2-006]
  critical_path: [T2-001, T2-002, T2-004, T2-006]
  estimated_total_time: "6 pt (extended effort — longest concurrent phase)"
blockers: []
success_criteria:
  - { id: SC-P2-1, description: "BranchWatcherRegistry in backend/db/branch_watcher.py; (project_id, worktree_path) key; asyncio.Lock present; BranchWatcherEntry defined; FileWatcher.start() unmodified (T2-001)", status: pending }
  - { id: SC-P2-2, description: "register() / unregister() unit tests pass; sessions dir excluded from watch scope; sync_changed_files uses parent project_id (T2-002)", status: pending }
  - { id: SC-P2-3, description: "Container registration + shutdown stop_all() wired; empty-registry no-op; existing FileWatcherRegistry lifecycle unchanged (T2-003)", status: pending }
  - { id: SC-P2-4, description: "Startup hydration serialized after _run_all_projects_sync_job; missing-path WARNING fires; no crash (T2-004)", status: pending }
  - { id: SC-P2-5, description: "branch_watchers snapshot key present; existing snapshot contract unchanged; contract test passes (T2-005)", status: pending }
  - { id: SC-P2-6, description: "Seam integration test passes; linting comment at call site; AC BWR-SEAM target surfaces verified (T2-006)", status: pending }
  - { id: SC-P2-7, description: "task-completion-validator passes; karen milestone sign-off required", status: pending }
files_modified:
  - backend/db/branch_watcher.py
  - backend/runtime/container.py
  - backend/adapters/jobs/runtime_job_adapter.py
  - backend/application/services/agent_queries/planning_command_center.py
---

# branch-aware-planning-intelligence v2 — Phase 2: BranchWatcherRegistry Infrastructure

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

> **R-P3 trigger**: ≥2 owner specialties (backend-architect + python-backend-engineer) with overlapping files.
> `integration_owner: backend-architect`. Seam task: T2-006.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-2-progress.md \
  -t T2-001 -s in_progress
```

---

## Objective

Build the `BranchWatcherRegistry` class in the new `backend/db/branch_watcher.py` (Option A,
OQ-2 resolution), wire it into the container alongside `FileWatcherRegistry`, implement
`register()`/`unregister()` with sessions-dir exclusion and ADR-006 parent `project_id`,
add startup hydration serialized after `_run_all_projects_sync_job` (OQ-3), handle missing
`worktree_path` with WARNING + skip (OQ-4), and prove the call-site seam with a failing→passing
integration test. Runs **parallel with P3 and P4** after P1 completes. **karen milestone at exit.**

**Dependency**: P1 complete (migration v34 + cache param_extractor). ADR-008 accepted (from P0).

---

## Exit Gate (karen milestone)

- [ ] T2-001: `BranchWatcherRegistry` class in `backend/db/branch_watcher.py`; key tuple correct
- [ ] T2-002: `register()` / `unregister()` unit tests pass; sessions dir excluded
- [ ] T2-003: Container registration + shutdown `stop_all()` wired
- [ ] T2-004: Startup hydration serialized after `_run_all_projects_sync_job`; missing-path warning fires
- [ ] T2-005: `branch_watchers` snapshot key present; existing snapshot contract unchanged
- [ ] T2-006: Seam integration test passes; linting comment at call site; AC BWR-SEAM verified
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T2-001 | backend-architect | sonnet | **extended** | P1-complete, ADR-008-accepted |
| T2-002 | backend-architect | sonnet | **extended** | T2-001 |
| T2-003 | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-004 | backend-architect | sonnet | **extended** | T2-002, T2-003 |
| T2-005 | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-006 | backend-architect | sonnet | adaptive | T2-002, T2-004 |

**Batch execution**: T2-001 solo → T2-002 + T2-003 + T2-005 in parallel → T2-004 → T2-006.
