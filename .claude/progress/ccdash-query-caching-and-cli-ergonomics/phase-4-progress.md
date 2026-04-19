---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-query-caching-and-cli-ergonomics
feature_slug: ccdash-query-caching-and-cli-ergonomics
phase: 4
title: Background Materialization
status: completed
created: '2026-04-14'
updated: '2026-04-14'
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners:
- python-backend-engineer
contributors: []
execution_model: sequential
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: BG-001
  description: "Inspect backend/adapters/jobs/ \u2014 understand job registration\
    \ pattern, scheduling API, error handling conventions"
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: haiku
  model_effort: low
- id: BG-002
  description: 'Create cache_warming_job() in backend/adapters/jobs/: loop project
    IDs, call two heaviest endpoints (project status, feature list), configurable
    interval, disabled if interval=0'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BG-001
  - CACHE-006
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: medium
- id: BG-003
  description: Register cache_warming_job() in backend/adapters/jobs/ registry; wire
    CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS config; disable if interval=0
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BG-002
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: BG-004
  description: 'Integration test: HTTP request latency unaffected while background
    job runs; cache warm after job completes'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BG-002
  - BG-003
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: BG-005
  description: 'Test: CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0 disables job;
    cache still works on-demand'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BG-003
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: sonnet
  model_effort: low
parallelization:
  batch_1:
  - BG-001
  batch_2:
  - BG-002
  batch_3:
  - BG-003
  batch_4:
  - BG-004
  - BG-005
  critical_path:
  - BG-001
  - BG-002
  - BG-003
  - BG-004
  estimated_total_time: 1-1.5 days
blockers: []
success_criteria:
- id: SC-4.1
  description: Cache materialization job created and registered
  status: pending
- id: SC-4.2
  description: Job runs at configurable interval (default 300 s)
  status: pending
- id: SC-4.3
  description: Job can be disabled (interval=0)
  status: pending
- id: SC-4.4
  description: HTTP requests not blocked by background job
  status: pending
- id: SC-4.5
  description: Job errors logged but do not crash worker
  status: pending
- id: SC-4.6
  description: All background job tests pass
  status: pending
files_modified:
- backend/adapters/jobs/
- backend/tests/
progress: 100
---

# CCDash Query Caching and CLI Ergonomics - Phase 4: Background Materialization

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-4-progress.md \
  -t BG-001 -s completed
```

---

## Quick Reference

Tasks are mostly sequential. BG-004 and BG-005 can run in parallel after BG-003 completes.

**Cross-phase dependency**: BG-002 depends on CACHE-006 (Phase 3) being complete.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| BG-001 | haiku | low | `Task("BG-001: Read backend/adapters/jobs/ directory. Understand job registration pattern, how jobs are scheduled (interval, cron, etc.), and error handling conventions. Document findings for BG-002.", model="haiku")` |
| BG-002 | sonnet | medium | `Task("BG-002: Create cache_warming_job() (or refresh_agent_queries_cache()) in backend/adapters/jobs/. Job: enumerate active project IDs, call project status rollup and feature list endpoints (the two heaviest) to pre-warm cache. Respects CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS; skips if interval=0. Errors logged, never raised. Reference: BG-001, CACHE-006.", model="sonnet")` |
| BG-003 | sonnet | low | `Task("BG-003: Register cache_warming_job in backend/adapters/jobs/ registry (__init__.py or jobs registry). Wire CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS from config. Disable if interval=0. Reference: BG-002.", model="sonnet")` |
| BG-004 | sonnet | low | `Task("BG-004: Integration test: start HTTP server + worker with cache job enabled. Make HTTP request while job is running. Assert HTTP response is fast (not blocked). Assert cache was populated after job run. Reference: BG-002, BG-003.", model="sonnet")` |
| BG-005 | sonnet | low | `Task("BG-005: Test: set CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0. Verify job does not run. Verify cache still works on-demand (direct queries still hit cache). Reference: BG-003.", model="sonnet")` |

---

## Objective

Register a low-priority background job that pre-warms the cache for the two heaviest rollups (project status, feature list aggregates) at a configurable cadence. The job must not block the HTTP request path and must be fully disableable via config.

---

## Implementation Notes

### Architectural Decisions

- Only the two heaviest endpoints are pre-warmed (project status rollup, feature list with aggregates). Feature forensics/AAR and workflow failures are on-demand only — they are project-specific and less predictable in access pattern.
- Job runs at low priority; default cadence is 300 s (5 min). The `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0` sentinel disables the job entirely.
- Job errors must be caught and logged. The worker runtime must continue running if the job fails (graceful degradation).

### Cross-Phase Dependency

BG-002 depends on **CACHE-006** (Phase 3) being complete — the job calls the same wrapped service endpoints. Ensure Phase 3 is merged before starting BG-002.

### Key File

`backend/adapters/jobs/` — inspect existing job registration pattern in BG-001 before implementing BG-002. The pattern is likely an async job function registered in `__init__.py` or a jobs registry dict.

### Known Gotchas

- Project enumeration: the job needs to know which project IDs to warm. Use the existing project manager or projects.json list from `backend/project_manager.py`.
- The background job adapter may use `asyncio.sleep` loops or APScheduler; BG-001 identifies the exact pattern before implementation.

---

## Completion Notes

_(Fill in when phase is complete)_
