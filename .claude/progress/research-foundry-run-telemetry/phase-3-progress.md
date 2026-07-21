---
type: progress
schema_version: 2
doc_type: progress
prd: research-foundry-run-telemetry
feature_slug: research-foundry-run-telemetry
phase: 3
status: pending
created: 2026-07-21
updated: 2026-07-21
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
commit_refs: []
pr_refs: []

owners: ["backend-architect", "frontend-developer", "ui-engineer-enhanced", "task-completion-validator"]
contributors: []

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 8
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

execution_model: sequential

tasks:
  - id: "T3-000"
    name: "Seam task — contract verification (R-P3)"
    description: "Verify the GET /api/agent/research-runs (+ detail) response DTO field names/types (Phase 2, T2-003/T2-004) exactly match the planned types.ts ResearchRun/ResearchRunMetrics interfaces before any panel work begins; write a short field-by-field mapping note; block T3-002 until this checklist passes."
    status: pending
    assigned_to: ["backend-architect", "frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["Phase 2 complete"]

  - id: "T3-001"
    name: "types.ts entities + queryKeys.ts registry entry"
    description: "Add ResearchRun, ResearchRunMetrics to root types.ts; add researchRunsKeys to services/queryKeys.ts per the existing registry pattern."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T3-000"]

  - id: "T3-002"
    name: "TanStack Query hooks"
    description: "useResearchRuns / useResearchRunDetail hooks wired to the new REST route, following the cache-tier conventions in docs/guides/feature-surface-architecture.md."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1 pt"
    dependencies: ["T3-001"]

  - id: "T3-003"
    name: "Tab shell + KPI strip"
    description: "New id: 'research' entry in AnalyticsDashboard.tsx TAB_LABELS; KPI strip using existing MetricCard."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1.5 pts"
    dependencies: ["T3-002"]

  - id: "T3-004"
    name: "Cost & quality by mode + spend/volume trend + run-level drill table"
    description: "3 remaining panels reusing TrendChart and dense-table patterns already in the file; grain is per-mode/per-run (honest v1 MVP, not per-provider — see Out of Scope in PRD §7)."
    status: pending
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "1.5 pts"
    dependencies: ["T3-003"]

  - id: "T3-005"
    name: "Resilience fallbacks for optional/absent fields (R-P2, FE half)"
    description: "Every optional field from the AC-2-Field backend contract (Phase 2) renders an explicit \"—\" per-cell when absent, never $0.00/NaN/0%; zero-events state renders \"No research runs recorded yet\" across all 4 panels."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T3-004"]
    ac_refs: ["AC-4-Fields"]

  - id: "T3-006"
    name: "Runtime smoke test (R-P4 gate)"
    description: "Start the dev server; capture before/after screenshots at desktop >=1440px for both the empty state (zero events) and the seeded-fixture state, covering every panel in target_surfaces."
    status: pending
    assigned_to: ["frontend-developer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T3-005"]
    ac_refs: ["AC-4", "AC-4-Fields"]

  - id: "T3-007"
    name: "Phase 3 completion review"
    description: "task-completion-validator verifies all Phase 3 ACs, including the seam checklist (T3-000) and runtime smoke evidence (T3-006)."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pts"
    dependencies: ["T3-000", "T3-001", "T3-002", "T3-003", "T3-004", "T3-005", "T3-006"]
    ac_refs: ["AC-4", "AC-4-Fields"]

parallelization:
  batch_1: ["T3-000"]
  batch_2: ["T3-001"]
  batch_3: ["T3-002"]
  batch_4: ["T3-003"]
  batch_5: ["T3-004"]
  batch_6: ["T3-005"]
  batch_7: ["T3-006"]
  batch_8: ["T3-007"]
  critical_path: ["T3-000", "T3-001", "T3-002", "T3-003", "T3-004", "T3-005", "T3-006", "T3-007"]

blockers: []
---

# research-foundry-run-telemetry - Phase 3: Analytics visualization tab

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-3-progress.md \
  -t T3-000 -s completed \
  --started 2026-07-21T00:00Z --completed 2026-07-21T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-3-progress.md \
  --updates "T3-000:completed,T3-001:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-3-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-3-progress.md
```
