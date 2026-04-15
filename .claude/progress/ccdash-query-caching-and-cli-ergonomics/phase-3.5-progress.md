---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-query-caching-and-cli-ergonomics
feature_slug: ccdash-query-caching-and-cli-ergonomics
phase: '3.5'
title: Feature List Pagination and Keyword Filtering
status: completed
created: '2026-04-14'
updated: '2026-04-14'
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners:
- python-backend-engineer
contributors:
- backend-architect
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: PAGINATE-001
  description: Update feature list endpoint default limit from 50 to 200 in backend/routers/agent.py
    or backend/application/services/agent_queries/feature_list.py. Verify no performance
    regression on local target with 200 features.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: PAGINATE-002
  description: 'Add truncated: bool (true if results exceed limit) and total: int
    (total count of all matching features) fields to feature-list response DTO in
    backend/application/services/agent_queries/models.py. Computed by comparing len(results)
    to limit and fetching total count.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PAGINATE-001
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: PAGINATE-003
  description: 'Add CLI truncation hint display in packages/ccdash_cli/ feature-list
    formatter. When truncated: true, display: ''Showing 200 of {total} features. Use
    --limit {total} to see all.'' or similar user-friendly message.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PAGINATE-002
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: sonnet
  model_effort: low
- id: FILTER-001
  description: Add --q <keyword> CLI flag to feature list command in packages/ccdash_cli/
    and ?q=keyword REST query param to backend/routers/agent.py. Wire keyword parameter
    through to service layer.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PAGINATE-001
  estimated_effort: 0.75 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: FILTER-002
  description: 'Implement keyword filter in backend/repositories/features.py. Accept
    optional keyword parameter; filter using case-insensitive substring match on feature
    name and slug: WHERE name ILIKE ''%keyword%'' OR slug ILIKE ''%keyword%''. Filter
    applied at DB query layer, not post-fetch.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - FILTER-001
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: FILTER-003
  description: 'Integration test: call feature list --q ''repo'' and verify only features
    with ''repo'' in name/slug are returned. Test with multiple keywords on test data.
    Verify case-insensitivity.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - FILTER-002
  estimated_effort: 0.75 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: PAGINATE-004
  description: 'Integration test for pagination and truncation: (1) call feature list
    (default 200), verify truncated and total fields correct; (2) with 213 features,
    truncated: true, total: 213; (3) verify CLI formatter displays hint.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PAGINATE-003
  estimated_effort: 0.75 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
parallelization:
  batch_1:
  - PAGINATE-001
  batch_2:
  - PAGINATE-002
  - FILTER-001
  batch_3:
  - PAGINATE-003
  - FILTER-002
  batch_4:
  - FILTER-003
  - PAGINATE-004
  critical_path:
  - PAGINATE-001
  - PAGINATE-002
  - PAGINATE-003
  - PAGINATE-004
  estimated_total_time: 0.75-1 day
blockers: []
success_criteria:
- id: SC-3.5.1
  description: Feature-list default limit is 200
  status: pending
- id: SC-3.5.2
  description: truncated and total fields present in response DTO
  status: pending
- id: SC-3.5.3
  description: 'CLI truncation hint displays correctly when truncated: true'
  status: pending
- id: SC-3.5.4
  description: Keyword filter works via CLI (--q) and REST (?q=)
  status: pending
- id: SC-3.5.5
  description: Filter applied at repository layer, not client-side
  status: pending
- id: SC-3.5.6
  description: Filter is case-insensitive substring match on name and slug
  status: pending
- id: SC-3.5.7
  description: Integration tests for pagination and filtering pass
  status: pending
files_modified:
- backend/routers/agent.py
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/feature_list.py
- backend/repositories/features.py
- packages/ccdash_cli/src/ccdash_cli/
- backend/tests/
progress: 100
---

# CCDash Query Caching and CLI Ergonomics - Phase 3.5: Feature List Pagination and Keyword Filtering

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-3.5-progress.md \
  -t PAGINATE-001 -s completed
```

---

## Quick Reference

PAGINATE-001 unlocks two parallel chains: PAGINATE-002→PAGINATE-003→PAGINATE-004 and FILTER-001→FILTER-002→FILTER-003. Phase 3.5 is independent of Phase 3 and can run in parallel with it or Phase 4.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| PAGINATE-001 | sonnet | low | `Task("PAGINATE-001: Locate the default limit parameter for the feature list endpoint in backend/routers/agent.py or backend/application/services/agent_queries/feature_list.py. Change default from 50 to 200. Verify no performance regression on a local target with 200 features.", model="sonnet")` |
| PAGINATE-002 | sonnet | low | `Task("PAGINATE-002: Add truncated: bool and total: int fields to the feature-list response DTO in backend/application/services/agent_queries/models.py. Compute truncated as len(results) >= limit; compute total via a count query. Reference: PAGINATE-001.", model="sonnet")` |
| PAGINATE-003 | sonnet | low | `Task("PAGINATE-003: Edit the feature-list formatter in packages/ccdash_cli/src/ccdash_cli/. When truncated is true, display: 'Showing {limit} of {total} features. Use --limit {total} to see all.' or equivalent user-friendly message. Reference: PAGINATE-002.", model="sonnet")` |
| FILTER-001 | sonnet | low | `Task("FILTER-001: Add --q <keyword> optional flag to the feature list CLI command in packages/ccdash_cli/src/ccdash_cli/. Add ?q=keyword query param to the feature-list REST endpoint in backend/routers/agent.py. Wire the keyword through to the service layer call. Reference: PAGINATE-001.", model="sonnet")` |
| FILTER-002 | sonnet | low | `Task("FILTER-002: Implement keyword filter in backend/repositories/features.py. Add optional keyword parameter to the feature query method. Apply case-insensitive substring match at DB level: WHERE name ILIKE '%keyword%' OR slug ILIKE '%keyword%'. Do not filter post-fetch. Reference: FILTER-001.", model="sonnet")` |
| FILTER-003 | sonnet | low | `Task("FILTER-003: Write pytest integration test for keyword filtering. Call feature list with --q 'repo'; verify only features containing 'repo' in name/slug are returned. Test multiple keywords. Verify case-insensitivity (e.g., 'REPO' matches 'repo-feature'). Reference: FILTER-002.", model="sonnet")` |
| PAGINATE-004 | sonnet | low | `Task("PAGINATE-004: Write pytest integration test for pagination and truncation. (1) With 213 test features, call feature list default; assert truncated=True, total=213, len(results)=200. (2) Verify CLI formatter displays truncation hint. Reference: PAGINATE-003.", model="sonnet")` |

---

## Objective

Raise the default limit on `feature list` from 50 to 200, add `truncated` and `total` metadata fields to the response DTO, display a truncation hint in CLI output, and implement keyword filtering at the repository layer via `--q` CLI flag and `?q=` REST param. All changes avoid client-side full-list scans.

---

## Implementation Notes

### Architectural Decisions

- Keyword filter is applied at the repository (DB query) layer, not post-fetch in the service layer. This ensures large feature lists are not fully loaded just to be filtered.
- `truncated` and `total` are computed together in the same query: total uses a `COUNT(*)` subquery or separate count; `truncated = len(results) >= limit`.
- SQLite uses `LIKE` for case-insensitive matching by default; PostgreSQL requires `ILIKE`. Use `ILIKE` consistently or abstract via SQLAlchemy's `ilike()` method to support both backends.
- The `--q` flag name is short by design (matches the plan); an alias `--name-contains` may be added for discoverability but is not required.

### Key Files

- `backend/application/services/agent_queries/feature_list.py` — service method; may hold default limit or delegate to router default
- `backend/repositories/features.py` — keyword filter at query layer
- `backend/application/services/agent_queries/models.py` — `truncated` and `total` on response model
- `packages/ccdash_cli/src/ccdash_cli/` — formatter and `--q` flag

### Cross-Phase Notes

- Phase 3.5 is independent of Phase 3 (cache foundation); the two can run in parallel. If feature-list is also a cached endpoint, Phase 3 cache layer wraps the service method after PAGINATE-002 completes.
- TEST-003.5 in Phase 5 provides comprehensive validation; FILTER-003 and PAGINATE-004 are immediate regression guards.

---

## Completion Notes

_(Fill in when phase is complete)_
