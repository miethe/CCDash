---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: sequential
phase: 4
title: "Frontend Surface (DEF-003)"
status: pending
started: null
completed: null
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
owners:
  - ui-engineer-enhanced
contributors: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T4-001
    description: "Phase 1 reconciliation — inspect shipped PlanningTopBar.tsx and CommandCenterFeatureCard.tsx against v1 plan files_affected; confirm DEF-003 chip genuinely absent/incomplete; record one-paragraph reconciliation note; no Phase-1-shipped UI re-authored"
    status: pending
    assigned_to: [ui-engineer-enhanced]
    dependencies: ["P1-complete"]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T4-002
    description: "PlanningTopBar branch chip — DEF-003 chip reading PlanningCommandCenterItemDTO.worktree?.branch (optional chaining); chip rendered when non-null/non-empty; chip hidden (not rendered, no error) when null/absent; unit test covers both states"
    status: pending
    assigned_to: [ui-engineer-enhanced]
    dependencies: [T4-001]
    estimated_effort: "1.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T4-003
    description: "Resilience + DTO seam verification (R-P3 seam task) — verify worktree.branch propagation contract types.ts -> services/queries/planning.ts -> PlanningTopBar; resilience test: no crash on absent worktree DTO field; AC BRANCH-EMPTY-FALLBACK PlanningTopBar.tsx surface met"
    status: pending
    assigned_to: [ui-engineer-enhanced]
    dependencies: [T4-002]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T4-004
    description: "R-P4 smoke pointer task — document that authoritative runtime smoke for P4 *.tsx changes is T5-003 (Phase 5); confirm PlanningTopBar and CommandCenter as AC DEF003-CHIP-SMOKE target surfaces; no status: completed on P4 or P5 without T5-003 smoke result"
    status: pending
    assigned_to: [ui-engineer-enhanced]
    dependencies: [T4-003]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
parallelization:
  batch_1: [T4-001]
  batch_2: [T4-002]
  batch_3: [T4-003]
  batch_4: [T4-004]
  critical_path: [T4-001, T4-002, T4-003, T4-004]
  estimated_total_time: "3 pt sequential"
blockers: []
success_criteria:
  - { id: SC-P4-1, description: "Reconciliation note written; confirmed-shipped Phase 1 items explicitly excluded; no Phase 1 UX re-authored (T4-001)", status: pending }
  - { id: SC-P4-2, description: "DEF-003 chip renders when worktree.branch non-null/non-empty; chip absent (no error) when null/absent; unit test covers both states (T4-002)", status: pending }
  - { id: SC-P4-3, description: "Resilience test passes (no crash on absent worktree); types.ts type shape verified; optional chaining present; AC BRANCH-EMPTY-FALLBACK PlanningTopBar.tsx surface met (T4-003)", status: pending }
  - { id: SC-P4-4, description: "T5-003 identified as R-P4 smoke owner; PlanningTopBar.tsx and CommandCenter documented as AC DEF003-CHIP-SMOKE target surfaces (T4-004)", status: pending }
  - { id: SC-P4-5, description: "task-completion-validator passes", status: pending }
files_modified:
  - components/Planning/PlanningTopBar.tsx
  - types.ts
---

# branch-aware-planning-intelligence v2 — Phase 4: Frontend Surface (DEF-003)

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

> **Scope guard**: P4 is intentionally thin — DEF-003 chip + verified-unshipped gaps only. Do NOT re-author Phase 1 UI.
> **R-P4 trigger**: P4 touches `*.tsx` → authoritative runtime smoke is T5-003 in Phase 5.
> **integration_owner**: `ui-engineer-enhanced`. Runs **parallel with P2 and P3** after P1 completes.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-4-progress.md \
  -t T4-001 -s in_progress
```

---

## Objective

Verify reconciliation of Phase 1 shipped UI, then implement the DEF-003 branch chip on
`PlanningTopBar` reading `PlanningCommandCenterItemDTO.worktree?.branch` with full resilience
(chip hidden when field absent, no error boundary triggered). Prove the DTO propagation seam
from `types.ts` → query hook → component. The authoritative runtime smoke is deferred to T5-003
in Phase 5 (project rule: R-P4 trigger on `*.tsx` changes).

**Dependency**: P1 complete (branch_filter cache dimension available; `worktree.branch` already populated by Phase 1 backend).

---

## Exit Gate

- [ ] T4-001: Reconciliation note present; Phase 1 shipped items excluded; no Phase 1 UX re-authored
- [ ] T4-002: DEF-003 chip renders; chip absent when `worktree` absent or `branch` null/empty; unit test passes
- [ ] T4-003: Resilience test passes; `types.ts` shape verified; AC BRANCH-EMPTY-FALLBACK `PlanningTopBar.tsx` surface met
- [ ] T4-004: T5-003 smoke pointer documented; AC DEF003-CHIP-SMOKE target surfaces identified
- [ ] `task-completion-validator` passes

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T4-001 | ui-engineer-enhanced | sonnet | adaptive | P1-complete |
| T4-002 | ui-engineer-enhanced | sonnet | adaptive | T4-001 |
| T4-003 | ui-engineer-enhanced | sonnet | adaptive | T4-002 |
| T4-004 | ui-engineer-enhanced | sonnet | adaptive | T4-003 |

**Batch execution**: Fully sequential — T4-001 → T4-002 → T4-003 → T4-004.
