---
title: "Phase 0: Inventory, Contracts, Guardrails"
description: "Inventory existing feature surface data needs and define DTO contracts, budgets, and parity fixtures before implementation."
audience: [ai-agents, developers]
tags: [implementation, phase, inventory, contracts, performance]
created: 2026-04-22
updated: 2026-04-22
category: "product-planning"
status: draft
related:
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
---

# Phase 0: Inventory, Contracts, Guardrails

**Effort:** 8 pts
**Dependencies:** None
**Assigned Subagent(s):** lead-architect, backend-architect, frontend-developer, react-performance-optimizer

## Objective

Create the authoritative map of every metric, count, filter, sort, search field, and modal section currently supported by the feature surfaces. Use that map to define DTOs and performance budgets before repository or UI changes begin.

## Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| P0-001 | Feature Surface Inventory | Inventory fields used by board cards, list view, modal overview, phases, docs, relations, sessions, test status, history, PlanningHomePage, FeatureExecutionWorkbench, and SessionInspector links. | Field map lists current source, target contract, exact/derived status, and owning component. | 2 pts | frontend-developer | None |
| P0-002 | Filter/Sort/Search Inventory | Document every feature query control: text search, status/stage, category, date ranges, progress, tasks, dependency state, quality signals, and completed/done grouping. | Query matrix defines backend parameter names, operators, default sort, and total semantics. | 1 pt | backend-architect | P0-001 |
| P0-003 | Rollup Contract Draft | Define `FeatureRollupDTO` fields for session counts, primary roots, subthreads, token/cost totals, latest activity, model/provider summary, task/doc/test metrics, and freshness. | DTO draft supports all current card metrics without full linked sessions. | 2 pts | lead-architect | P0-001 |
| P0-004 | Modal Section Contract Draft | Define section contracts for overview, phases/tasks, docs, relations, sessions, test status, and history/activity. | Each modal tab has source endpoint, cache key, loading state, and failure mode. | 1 pt | frontend-developer | P0-001 |
| P0-005 | Performance Budgets | Define request count, payload size, latency, and cache budget targets for board and modal. | Budgets are documented and later tests can assert them. | 1 pt | react-performance-optimizer | P0-003 |
| P0-006 | Parity Fixture Plan | Identify or create fixtures representing small, medium, and large projects with linked sessions, subthreads, docs, tests, and mixed statuses. | Fixture plan supports old-vs-new parity and performance tests. | 1 pt | backend-architect | P0-002 |

## Required Contract Decisions

### Feature List DTO

Must contain enough data for layout, grouping, filtering labels, status display, progress display, and document/dependency indicators:

- `id`, `name`, `status`, `effectiveStatus`, `category`, `tags`
- `summary`, `description` preview, `priority`, `riskLevel`, `complexity`
- `totalTasks`, `completedTasks`, `deferredTasks`, `phaseCount`
- `plannedAt`, `startedAt`, `completedAt`, `updatedAt`
- `documentCoverage`, `qualitySignals`, `dependencyState`
- `primaryDocuments` summary, not full document content
- `familyPosition`, `relatedFeatureCount`

### Feature Rollup DTO

Must contain card-level aggregates without session logs:

- `featureId`
- `sessionCount`, `primarySessionCount`, `subthreadCount`
- `totalCost`, `displayCost`, `observedTokens`, `modelIOTokens`, `cacheInputTokens`
- `latestSessionAt`, `latestActivityAt`
- `modelFamilies`, `providers`, `workflowTypes`
- `linkedDocCount`, `linkedTaskCount`, `testCount`, `failingTestCount`
- `precision`: `exact`, `eventually_consistent`, or `partial`
- `freshness`: timestamp/source revision

### Modal Section Contracts

- Overview shell must be cheap and always safe to load on open.
- Sessions section must page at the source and offer explicit enrichment includes.
- History/activity must not require loading full linked session arrays.
- Docs and relations can reuse existing lightweight document/link metadata.

## Quality Gates

- [ ] Field inventory covers every current visible feature/card/modal metric.
- [ ] Query matrix covers all current filters/sorts/search behavior.
- [ ] DTO contracts identify exact vs eventually consistent values.
- [ ] Performance budgets are measurable.
- [ ] No implementation begins before DTO owners sign off on metric coverage.

## Notes for Implementers

1. Start from `components/ProjectBoard.tsx` and trace every use of `Feature`, `FeatureSessionLink`, and `FeatureSessionSummary`.
2. Treat missing field mapping as a blocker; the redesign must preserve the feature set.
3. Record any metric that is only possible from session logs so it can be moved out of card rendering or explicitly marked as detail-only.

