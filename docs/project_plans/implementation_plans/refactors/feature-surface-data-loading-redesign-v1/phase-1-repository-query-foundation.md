---
title: "Phase 1: Repository and Query Foundation"
description: "Add repository methods for backend-backed feature lists, aggregate rollups, and true linked-session pagination across SQLite and Postgres."
audience: [ai-agents, developers]
tags: [implementation, phase, repositories, sqlite, postgres, performance]
created: 2026-04-22
updated: 2026-04-22
category: "product-planning"
status: draft
related:
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
---

# Phase 1: Repository and Query Foundation

**Effort:** 14 pts
**Dependencies:** Phase 0 contracts complete
**Assigned Subagent(s):** data-layer-expert, python-backend-engineer, backend-architect

## Objective

Move feature surface filtering, sorting, totals, aggregate rollups, and linked-session pagination into repository methods with equivalent SQLite and Postgres behavior.

## Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| P1-001 | Query Models | Define repository query option models for feature list filters, sort keys, pagination, rollup field selection, and linked-session includes. | Typed options are shared by SQLite/Postgres implementations and service layer. | 2 pts | backend-architect | P0-002 |
| P1-002 | Feature List Query | Implement storage-backed feature list filtering/search/sort/count. | `list_feature_cards` returns page rows and accurate total for all filters. | 3 pts | data-layer-expert | P1-001 |
| P1-003 | Feature Phase Summary Bulk Query | Replace per-feature `get_phases()` list behavior with bulk phase summaries for page feature IDs. | Feature list can include phase counts/progress without N+1 calls. | 2 pts | python-backend-engineer | P1-002 |
| P1-004 | Feature Rollup Aggregate Query | Implement aggregate rollups for bounded feature IDs from entity links, sessions, tasks, docs, and tests without reading session logs. | Rollup query returns exact/partial metrics and freshness metadata for a page of feature IDs. | 3 pts | data-layer-expert | P1-002 |
| P1-005 | Linked-Session Page Query | Implement true source-level pagination for feature linked sessions with optional inherited thread expansion. | Query returns page, total, and page metadata without materializing all rows first. | 2 pts | python-backend-engineer | P1-004 |
| P1-006 | Index Review | Add or validate indexes for feature filters, entity link lookups, session project/root ordering, document/task feature filters, and test health joins. | Query plans are captured for SQLite and Postgres; indexes are justified. | 1 pt | data-layer-expert | P1-005 |
| P1-007 | Repository Tests | Add SQLite and Postgres-parity tests for filters, sorts, totals, rollups, and linked-session pagination. | Tests fail on in-memory post-pagination semantics and N+1 regressions. | 1 pt | python-backend-engineer | P1-006 |

## Repository Method Targets

### Feature Repository

- `list_feature_cards(project_id, query) -> FeatureCardPage`
- `count_feature_cards(project_id, query) -> int`
- `list_phase_summaries_for_features(project_id, feature_ids) -> dict[str, list[PhaseSummary]]`

### Entity Link / Session Repository

- `get_feature_session_rollups(project_id, feature_ids, options) -> dict[str, FeatureSessionRollup]`
- `list_feature_session_refs(project_id, feature_id, query) -> LinkedSessionPage`
- `count_feature_session_refs(project_id, feature_id, query) -> int`
- `list_session_family_refs(project_id, root_session_ids, query) -> LinkedSessionPage`

### Document / Task / Test Repositories

- Bulk counts by feature ID.
- Latest activity by feature ID.
- Optional summaries for card badges.

## Query Semantics

1. Search should match feature ID, name, summary/description where feasible, and tags when represented in `data_json`.
2. Status filters must support raw status and board stage/effective status.
3. Date filters must support planned, started, completed, and updated ranges.
4. Sort must support updated date, progress, task count, name, status/stage, latest activity, and session count where requested.
5. Totals must reflect the filtered query, not the unfiltered table.
6. Rollups must reject or cap excessive feature ID lists.

## Quality Gates

- [ ] SQLite and Postgres return equivalent result ordering for deterministic fixtures.
- [ ] No board list path performs per-feature linked-session calls.
- [ ] Rollup queries do not fetch session logs.
- [ ] Linked-session endpoint can return page 1 without loading every session in the feature family.
- [ ] Query plans are acceptable for small and large fixtures.

## Migration Notes

1. Keep old repository methods until all callers migrate.
2. Prefer additive repository methods to risky edits of existing broad methods.
3. Add tests around current known bug: v1 in-memory status/category filtering after pagination must be replaced or explicitly avoided.

