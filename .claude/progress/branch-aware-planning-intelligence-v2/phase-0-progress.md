---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: batch-parallel
phase: 0
title: "Prerequisites & Seam Decision"
status: pending
started: null
completed: null
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
owners:
  - data-layer-expert
  - backend-architect
contributors: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T0-001
    description: "ADR-007 Retrofit — replace bare self.db.commit() with retry_on_locked in SqliteDocumentRepository.upsert; confirm retry_on_locked import from base.py; PRAGMA busy_timeout = 30000 confirmed"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: []
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T0-002
    description: "Direct-count assertion test — SELECT COUNT(*) FROM documents WHERE project_id=? AND branch=? returns expected count (ADR-007 §4) in backend/tests/test_documents_adr007.py"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T0-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T0-003
    description: "Lock-injection test — inject SQLITE_BUSY on first commit() call; assert retry succeeds and row is persisted (ADR-007 §5 pattern)"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T0-001]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T0-004
    description: "Postgres parity — ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch; Postgres direct-count assertion test mirroring T0-002"
    status: pending
    assigned_to: [data-layer-expert]
    dependencies: [T0-001]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T0-005
    description: "Draft + Accept ADR-008 — author adr-008-branch-watcher-registry-planning-service-seam.md; OQ-1/OQ-2/OQ-3/OQ-4 all resolved with matching decisions-block §7 resolutions; status: accepted; backend-architect review required"
    status: pending
    assigned_to: [backend-architect]
    dependencies: [T0-001]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: extended
parallelization:
  batch_1: [T0-001]
  batch_2: [T0-002, T0-003, T0-004, T0-005]
  critical_path: [T0-001, T0-005]
  estimated_total_time: "2 pt serial + 1 pt parallel"
blockers: []
success_criteria:
  - { id: SC-P0-1, description: "SqliteDocumentRepository.upsert uses retry_on_locked; no bare self.db.commit() remains (T0-001)", status: pending }
  - { id: SC-P0-2, description: "Direct-count test passes on SQLite (T0-002)", status: pending }
  - { id: SC-P0-3, description: "Lock-injection test passes; row present post-retry (T0-003)", status: pending }
  - { id: SC-P0-4, description: "Postgres direct-count test passes; branch in ON CONFLICT clause (T0-004)", status: pending }
  - { id: SC-P0-5, description: "ADR-008 status accepted; OQ-1/OQ-2/OQ-3/OQ-4 resolved (T0-005)", status: pending }
  - { id: SC-P0-6, description: "task-completion-validator passes; karen milestone sign-off obtained", status: pending }
files_modified:
  - backend/db/repositories/documents.py
  - backend/tests/test_documents_adr007.py
  - docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md
---

# branch-aware-planning-intelligence v2 — Phase 0: Prerequisites & Seam Decision

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-0-progress.md \
  -t T0-001 -s in_progress
```

---

## Objective

Retrofit `SqliteDocumentRepository.upsert` to comply with ADR-007 (`retry_on_locked` +
direct-count assertion tests on SQLite and Postgres, lock-injection test), then draft and
accept ADR-008 formalizing the `BranchWatcherRegistry`↔planning-service call-site seam
(OQ-1/OQ-2/OQ-3/OQ-4 resolved). Both must be satisfied before any Phase 2 registry
infrastructure is authored. **karen milestone required at exit.**

---

## Exit Gate (karen milestone)

- [ ] T0-001: `SqliteDocumentRepository.upsert` uses `retry_on_locked`; no bare commit remains
- [ ] T0-002: Direct-count assertion test passes (SQLite)
- [ ] T0-003: Lock-injection test passes; row present post-retry
- [ ] T0-004: Postgres parity — `ON CONFLICT DO UPDATE SET branch` + direct-count test passes
- [ ] T0-005: ADR-008 `status: accepted`; OQ-1/OQ-2/OQ-3/OQ-4 all resolved per decisions-block §7
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T0-001 | data-layer-expert | sonnet | adaptive | — |
| T0-002 | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-003 | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-004 | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-005 | backend-architect | sonnet | **extended** | T0-001 |

**Batch execution**: Run T0-001 first (solo). Then T0-002 + T0-003 + T0-004 + T0-005 in parallel.
