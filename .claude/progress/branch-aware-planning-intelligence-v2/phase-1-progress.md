---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: batch-parallel
phase: 1
title: "Data Layer"
status: pending
started: null
completed: null
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
owners:
  - data-layer-expert
contributors: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T1-001
    description: "Migration v34 — ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT '' via _ensure_column; CREATE INDEX idx_docs_project_branch ON documents(project_id, branch); idempotent"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: ["P0-complete"]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T1-002
    description: "Migration v34 — CREATE INDEX idx_sessions_git_branch_project ON sessions(git_branch, project_id); index-only, no write path, zero ADR-007 cost"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T1-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T1-003
    description: "Migration v34 — Postgres parity: ALTER TABLE documents ADD COLUMN IF NOT EXISTS branch TEXT DEFAULT ''; composite index + sessions index in postgres_migrations.py"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T1-001]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T1-004
    description: "branch_filter param_extractor dimension on 4 endpoints: planning_project_summary, planning_project_graph, planning_feature_context, pss_session_board; branch_filter=None key MUST be byte-identical to Phase 1 key; aclear_project_cache evicts all branch slots"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T1-002]
    estimated_effort: "1.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
parallelization:
  batch_1: [T1-001]
  batch_2: [T1-002, T1-003]
  batch_3: [T1-004]
  critical_path: [T1-001, T1-002, T1-004]
  estimated_total_time: "3 pt serial + overlap"
blockers: []
success_criteria:
  - { id: SC-P1-1, description: "Migration v34 applies cleanly on fresh + upgraded SQLite DB; documents.branch column present; idx_docs_project_branch exists (T1-001)", status: pending }
  - { id: SC-P1-2, description: "idx_sessions_git_branch_project exists; EXPLAIN QUERY PLAN confirms index use (T1-002)", status: pending }
  - { id: SC-P1-3, description: "Postgres migration v34 applies clean; column + indexes present (T1-003)", status: pending }
  - { id: SC-P1-4, description: "branch_filter=None cache key byte-identical to Phase 1 key — regression test passes on all 4 endpoints (T1-004)", status: pending }
  - { id: SC-P1-5, description: "branch_filter='feat/x' produces a distinct cache slot; aclear_project_cache evicts all branch-filtered slots (T1-004)", status: pending }
  - { id: SC-P1-6, description: "task-completion-validator passes", status: pending }
files_modified:
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/application/services/agent_queries/cache.py
  - backend/application/services/agent_queries/planning_sessions.py
  - backend/application/services/agent_queries/planning_command_center.py
  - backend/application/services/agent_queries/planning.py
---

# branch-aware-planning-intelligence v2 — Phase 1: Data Layer

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-1-progress.md \
  -t T1-001 -s in_progress
```

---

## Objective

Deliver DB migration v34 (`documents.branch` column + `idx_docs_project_branch` + 
`idx_sessions_git_branch_project`) on both SQLite and Postgres, and add `branch_filter`
as a `param_extractor` cache dimension on all four `@memoized_query` planning endpoints —
ensuring `branch_filter=None` remains byte-identical to the Phase 1 cache key (no regression).
This data layer is the gate for P2, P3, and P4 to begin in parallel.

**Dependency**: P0 must be complete (ADR-007 retrofit + ADR-008 accepted).

---

## Exit Gate

- [ ] T1-001: Migration v34 applies cleanly on SQLite (fresh + upgraded); `documents.branch` column + index present
- [ ] T1-002: `idx_sessions_git_branch_project` exists; `EXPLAIN QUERY PLAN` uses index
- [ ] T1-003: Postgres migration v34 applies clean; column + both indexes present
- [ ] T1-004: `branch_filter=None` key byte-identical to Phase 1 key (regression test); distinct slot for `branch_filter='feat/x'`; `aclear_project_cache` evicts all branch slots
- [ ] `task-completion-validator` passes

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T1-001 | data-layer-expert | sonnet | adaptive | P0-complete |
| T1-002 | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-003 | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-004 | data-layer-expert | sonnet | adaptive | T1-002 |

**Batch execution**: T1-001 solo → T1-002 + T1-003 in parallel → T1-004.
