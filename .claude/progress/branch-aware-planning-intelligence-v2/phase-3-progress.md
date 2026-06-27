---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence-v2
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
execution_model: batch-parallel
phase: 3
title: "S2 Branch-Signal Correlation"
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
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
tasks:
  - id: T3-001
    description: "Module-level correlation constants — _BRANCH_EXCLUSION_SET (frozenset: main/master/develop/dev/HEAD/release/hotfix/staging/prod/production); _BRANCH_PREFIXES list; _normalize_branch_for_correlation() strips prefix, lowercases, normalizes _->-; collocated with _correlate_command_tokens"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: ["P1-complete"]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T3-002
    description: "_correlate_branch() implementation — step 5a in correlate_session() after _correlate_command_tokens; (1) Codex null-branch early-exit on None->[];  (2) normalize; (3) min-length <8 chars->[];  (4) exclusion set->[];  (5) match slug tokens vs feature_index; (6) confidence='medium'; no high confidence assigned"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T3-001]
    estimated_effort: "2 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T3-003
    description: "Correlation unit tests — backend/tests/test_branch_correlation.py: (1) positive match feat/my-feature->medium evidence; (2) exclusion-set reject main/develop->[];  (3) min-length 7-char->[], 8-char non-excluded->evidence; (4) regression: _correlate_command_tokens suite still passes"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T3-002]
    estimated_effort: "1 pt"
    assigned_model: sonnet
    model_effort: adaptive
  - id: T3-004
    description: "Codex null-branch disclosure AC (R-01 precondition 4) — test_codex_null_branch_no_correlation: git_branch=None -> [] from _correlate_branch; test_codex_null_branch_ui_disclosure: branch_filter=None planning query returns Codex sessions; structured log fields branch_slug + normalized_slug; AC-S2-CODEX verified"
    status: pending
    assigned_to: [python-backend-engineer]
    dependencies: [T3-002]
    estimated_effort: "0.5 pt"
    assigned_model: sonnet
    model_effort: adaptive
parallelization:
  batch_1: [T3-001]
  batch_2: [T3-002]
  batch_3: [T3-003, T3-004]
  critical_path: [T3-001, T3-002, T3-003]
  estimated_total_time: "3.5 pt serial + 0.5 pt parallel"
blockers: []
success_criteria:
  - { id: SC-P3-1, description: "_BRANCH_EXCLUSION_SET is frozenset; _normalize_branch_for_correlation strips prefixes, lowercases, normalizes hyphens; collocated with _correlate_command_tokens (T3-001)", status: pending }
  - { id: SC-P3-2, description: "_correlate_branch present as step 5a after _correlate_command_tokens; Codex early-exit on None; [] on <8 chars; [] for exclusion-set; medium confidence returned (T3-002)", status: pending }
  - { id: SC-P3-3, description: "All 4 unit test cases pass; zero regression on existing correlation pipeline tests (T3-003)", status: pending }
  - { id: SC-P3-4, description: "Codex null-branch test passes; planning queries with branch_filter=None include Codex sessions; structured log fields present; AC-S2-CODEX met (T3-004)", status: pending }
  - { id: SC-P3-5, description: "task-completion-validator passes", status: pending }
files_modified:
  - backend/application/services/agent_queries/session_correlation.py
  - backend/tests/test_branch_correlation.py
---

# branch-aware-planning-intelligence v2 — Phase 3: S2 Branch-Signal Correlation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

> **H3 floor**: `_correlate_branch` is an algorithmic correlation service → ≥3 pts floor honored (P3 = 4 pts per decisions block §4).
> Runs **parallel with P2 and P4** after P1 completes.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/branch-aware-planning-intelligence/phase-3-progress.md \
  -t T3-001 -s in_progress
```

---

## Objective

Implement `_correlate_branch()` as step 5a in `correlate_session()` within
`backend/application/services/agent_queries/session_correlation.py`, with a prefix-stripping
normalizer, a 10-branch exclusion set, an 8-character min-length guard, and `medium` confidence
evidence output. Ship unit tests plus an explicit Codex null-branch disclosure test (R-01
precondition 4 / AC-S2-CODEX). Runs concurrently with P2 and P4 after P1 exits.

**Dependency**: P1 complete (`idx_sessions_git_branch_project` index available).

---

## Exit Gate

- [ ] T3-001: Constants + normalizer defined at module level; collocated with `_correlate_command_tokens`
- [ ] T3-002: `_correlate_branch` present as step 5a; Codex early-exit; min-length guard; exclusion-set; medium confidence
- [ ] T3-003: All 4 test cases pass; zero regression on existing correlation pipeline tests
- [ ] T3-004: Codex null-branch disclosure test passes; AC-S2-CODEX met; structured log fields present
- [ ] `task-completion-validator` passes

---

## Quick Reference

| Task | Assigned | Model | Effort | Deps |
|------|----------|-------|--------|------|
| T3-001 | python-backend-engineer | sonnet | adaptive | P1-complete |
| T3-002 | python-backend-engineer | sonnet | adaptive | T3-001 |
| T3-003 | python-backend-engineer | sonnet | adaptive | T3-002 |
| T3-004 | python-backend-engineer | sonnet | adaptive | T3-002 |

**Batch execution**: T3-001 → T3-002 → T3-003 + T3-004 in parallel.
