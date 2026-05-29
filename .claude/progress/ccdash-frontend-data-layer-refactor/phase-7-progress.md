---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 7
title: Validation, Docs & Epic D Gate
status: not_started
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs: []
pr_refs: []
owners:
- ui-engineer-enhanced
contributors:
- documentation-writer
- documentation-complex
- ai-artifacts-engineer
- karen
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 11
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external:
  - haiku
tasks:
- id: T7-001
  description: Full guardrail suite — run vitest against noHandRolledCache.test.ts, dataArchitecture.test.ts, FeatureSurfaceRegressionMatrix.test.tsx, featureSurfaceDecoupling.test.ts, ProjectBoardEagerLoop.test.tsx; all green; fix regressions
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T6-005
- id: T7-002
  description: Comprehensive runtime smoke all surfaces (Dashboard, SessionInspector, PlanCatalog, ProjectBoard, Planning Home/AgentSessionBoard/GraphPanel, FeatureModal, Analytics); verify above-fold request counts (Dashboard ≤1, Planning ≤1, Analytics ≤1)
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-001
- id: T7-003
  description: Update docs/guides/feature-surface-architecture.md — two-layer cache model (backend @memoized_query 600s + client TQ QueryClient 30s-5min); update hook API section; remove LRU/featureCacheBus references; add queryKey registry reference
  status: pending
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  model_effort: adaptive
  dependencies:
  - T7-002
- id: T7-004
  description: Add CHANGELOG [Unreleased] entries — Performance (TQ migration, instant back-nav), Changed (Dashboard ≤1 request, paginated tasks/features), Improved (3 lists virtualized); follow changelog-spec.md rules
  status: pending
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  model_effort: adaptive
  dependencies:
  - T7-002
- id: T7-005
  description: Update CLAUDE.md with ≤3-line pointer to frontend data layer (TQ QueryClient, services/queries/, queryKeys.ts, bundle endpoints, feature-surface-architecture.md)
  status: pending
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  model_effort: adaptive
  dependencies:
  - T7-003
- id: T7-006
  description: DOC-006 — Author docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md (maturity:shaping); enumerate AC-D1 entry criteria; document 3 SSR blockers with file:line; list preconditions; update parent plan deferred_items_spec_refs
  status: pending
  assigned_to:
  - documentation-complex
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-002
- id: T7-007
  description: DOC-006 — Author docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md stub (status:draft, blocked by entry-criteria gate); one-paragraph scope, SSR blocker list, entry-criteria gate reference; no implementation tasks
  status: pending
  assigned_to:
  - documentation-complex
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-006
- id: T7-008
  description: Update parent plan frontmatter lifecycle fields — status:completed, files_affected final list, changelog_ref:CHANGELOG.md, deferred_items_spec_refs populated, updated date
  status: pending
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  model_effort: adaptive
  dependencies:
  - T7-007
- id: T7-009
  description: Check .claude/specs/skills-index.md + planning SPEC.md — update if two-layer cache model or queryKey registry pattern should appear in Capability Coverage matrix; otherwise document N/A
  status: pending
  assigned_to:
  - ai-artifacts-engineer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-008
- id: T7-010
  description: karen end-of-feature review — verify all PRD ACs met (AC-A1–A3, AC-B1–B4, AC-C1–C4, AC-D1 gate only); all guardrail tests green; CHANGELOG present; Epic D gate doc authored; no deferred items missing spec
  status: pending
  assigned_to:
  - karen
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-009
- id: T7-011
  description: task-completion-validator gate (P7)
  status: pending
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T7-010
parallelization:
  batch_1:
  - T7-001
  batch_2:
  - T7-002
  batch_3:
  - T7-003
  - T7-004
  - T7-006
  batch_4:
  - T7-005
  - T7-007
  batch_5:
  - T7-008
  batch_6:
  - T7-009
  batch_7:
  - T7-010
  batch_8:
  - T7-011
  critical_path:
  - T7-001
  - T7-002
  - T7-006
  - T7-007
  - T7-008
  - T7-009
  - T7-010
  - T7-011
blockers: []
success_criteria:
- id: SC-7.1
  description: vitest run exits 0; all guardrail and regression test suites green
  status: pending
- id: SC-7.2
  description: Comprehensive runtime smoke all 7 target surfaces pass
  status: pending
- id: SC-7.3
  description: docs/guides/feature-surface-architecture.md updated — two-layer cache model, no references to deleted files
  status: pending
- id: SC-7.4
  description: CHANGELOG [Unreleased] updated with Performance, Changed, Improved entries
  status: pending
- id: SC-7.5
  description: CLAUDE.md updated with ≤3-line data layer pointer
  status: pending
- id: SC-7.6
  description: docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md authored (DOC-006)
  status: pending
- id: SC-7.7
  description: docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md stub created (DOC-006)
  status: pending
- id: SC-7.8
  description: deferred_items_spec_refs in parent plan frontmatter populated
  status: pending
- id: SC-7.9
  description: Plan frontmatter lifecycle fields complete (status:completed, changelog_ref, files_affected)
  status: pending
- id: SC-7.10
  description: Planning skill SPEC.md updated (or N/A documented)
  status: pending
- id: SC-7.11
  description: karen end-of-feature review passed
  status: pending
- id: SC-7.12
  description: task-completion-validator sign-off
  status: pending
files_modified:
- docs/guides/feature-surface-architecture.md
- CHANGELOG.md
- CLAUDE.md
- docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md
- docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md
- docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
---

# CCDash Frontend Data Layer Refactor - Phase 7: Validation, Docs & Epic D Gate

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-7-progress.md \
  -t T7-001 -s completed
```

---

## Objective

Full guardrail suite, comprehensive runtime smoke, docs update, CHANGELOG, CLAUDE.md pointer, and Epic D entry-criteria gate doc. `karen` runs end-of-feature review. T7-003/T7-004/T7-006 can run in parallel after T7-002. Documentation tasks use haiku; Epic D spec uses sonnet.
