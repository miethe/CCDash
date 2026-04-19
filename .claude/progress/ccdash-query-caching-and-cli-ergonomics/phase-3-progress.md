---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-query-caching-and-cli-ergonomics
feature_slug: ccdash-query-caching-and-cli-ergonomics
phase: 3
title: Cache Foundation
status: completed
created: '2026-04-14'
updated: '2026-04-14'
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners:
- backend-architect
contributors:
- python-backend-engineer
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 11
completed_tasks: 11
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: CACHE-001
  description: "Verify four target endpoints and async patterns in agent_queries/\
    \ and routers/agent.py \u2014 document signatures and cache key strategy"
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 1 pt
  priority: low
  assigned_model: haiku
  model_effort: low
- id: CACHE-002
  description: 'Add cachetools>=5.3.0 to backend/requirements.txt (OQ-2 resolved:
    not present, needed for TTLCache)'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: sonnet
  model_effort: low
- id: CACHE-003
  description: "Create backend/application/services/agent_queries/cache.py with get_data_version_fingerprint()\
    \ and compute_cache_key() \u2014 includes graceful degradation on fingerprint\
    \ failure"
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - CACHE-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: medium
- id: CACHE-004
  description: "Implement @memoized_query async decorator in cache.py \u2014 checks\
    \ key, returns cached or awaits + caches result, increments OTel counters"
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - CACHE-003
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: medium
- id: CACHE-005
  description: Add CCDASH_QUERY_CACHE_TTL_SECONDS (default 60) and CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS
    (default 300) to backend/config.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: sonnet
  model_effort: low
- id: CACHE-006
  description: Apply @memoized_query decorator to all four target endpoints (project
    status, feature forensics/AAR, workflow failures, feature list)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - CACHE-004
  - CACHE-005
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: medium
- id: CACHE-007
  description: 'Implement cache bypass: ?bypass_cache=true in routers/agent.py (REST)
    and --no-cache flag in CLI commands; wire flag to query param'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - CACHE-006
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: CACHE-008
  description: Add agent_query.cache.hit and agent_query.cache.miss OTel counters
    to backend/observability/otel.py; wire into @memoized_query
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - CACHE-004
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: medium
- id: CACHE-009
  description: "Integration test: cache invalidation on sync write \u2014 call, cache\
    \ hit, write new data, sync, call again \u2192 cache miss with fresh result"
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - CACHE-006
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: medium
- id: CACHE-010
  description: "Integration test: TTL expiry \u2014 call (miss), call within TTL (hit),\
    \ wait for TTL, call again (miss). Use short TTL (2 s) for test."
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - CACHE-006
  estimated_effort: 1 pt
  priority: low
  assigned_model: sonnet
  model_effort: low
- id: CACHE-011
  description: 'Graceful degradation test: simulate fingerprint query failure, verify
    error logged, live query executes, no exception bubbles'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - CACHE-004
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
parallelization:
  batch_1:
  - CACHE-001
  - CACHE-002
  - CACHE-005
  batch_2:
  - CACHE-003
  batch_3:
  - CACHE-004
  - CACHE-008
  batch_4:
  - CACHE-006
  - CACHE-011
  batch_5:
  - CACHE-007
  - CACHE-009
  - CACHE-010
  critical_path:
  - CACHE-002
  - CACHE-003
  - CACHE-004
  - CACHE-006
  - CACHE-007
  estimated_total_time: 2-2.5 days
blockers: []
success_criteria:
- id: SC-3.1
  description: Cache utility module complete and tested
  status: pending
- id: SC-3.2
  description: Decorator wraps all four target endpoints
  status: pending
- id: SC-3.3
  description: OTel counters emit correctly (hit/miss)
  status: pending
- id: SC-3.4
  description: Cache invalidation works on data update (fingerprint)
  status: pending
- id: SC-3.5
  description: TTL expiry tested
  status: pending
- id: SC-3.6
  description: Graceful degradation on fingerprint failure
  status: pending
- id: SC-3.7
  description: bypass_cache flag/param works (REST + CLI)
  status: pending
- id: SC-3.8
  description: CCDASH_QUERY_CACHE_TTL_SECONDS config respected; TTL=0 disables cache
  status: pending
- id: SC-3.9
  description: All cache-related tests pass
  status: pending
files_modified:
- backend/application/services/agent_queries/cache.py
- backend/application/services/agent_queries/__init__.py
- backend/requirements.txt
- backend/config.py
- backend/observability/otel.py
- backend/routers/agent.py
- packages/ccdash_cli/src/ccdash_cli/
- backend/tests/
progress: 100
---

# CCDash Query Caching and CLI Ergonomics - Phase 3: Cache Foundation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-3-progress.md \
  -t CACHE-001 -s completed
```

---

## Quick Reference

Batch 1 (CACHE-001, CACHE-002, CACHE-005) can run in parallel — all are independent reads/configs. Remaining batches are sequential per the dependency chain.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| CACHE-001 | haiku | low | `Task("CACHE-001: Inspect backend/application/services/agent_queries/ and backend/routers/agent.py. Identify the four target endpoints: project status rollup, feature forensics/AAR, workflow failures, feature list with aggregates. Document function names, signatures, and whether all are async. Propose cache key construction strategy.", model="haiku")` |
| CACHE-002 | sonnet | low | `Task("CACHE-002: Add 'cachetools>=5.3.0' to backend/requirements.txt. OQ-2 resolved: cachetools is not present in requirements. This provides TTLCache for TTL-based memoization.", model="sonnet")` |
| CACHE-005 | sonnet | low | `Task("CACHE-005: Add CCDASH_QUERY_CACHE_TTL_SECONDS (default 60, int) and CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS (default 300, int) to backend/config.py. Use existing _env_int() pattern. Document defaults in comments.", model="sonnet")` |
| CACHE-003 | sonnet | medium | `Task("CACHE-003: Create backend/application/services/agent_queries/cache.py. Implement get_data_version_fingerprint(context, ports, project_id) — async, queries max updated_at from sessions/features. Implement compute_cache_key(endpoint_name, project_id, params, fingerprint). Graceful degradation: fingerprint failure → log warning, return None (triggers cache miss). Reference: CACHE-002.", model="sonnet")` |
| CACHE-004 | sonnet | medium | `Task("CACHE-004: Implement @memoized_query async decorator in cache.py. Uses cachetools.TTLCache at module level. On call: get fingerprint, compute key, check cache; hit → return; miss → await original, store, return. Increments OTel counters (stubbed; CACHE-008 wires actual instrumentation). Reference: CACHE-003.", model="sonnet")` |
| CACHE-008 | sonnet | medium | `Task("CACHE-008: Add agent_query.cache.hit and agent_query.cache.miss OTel counters to backend/observability/otel.py. Export counter handles for use in @memoized_query decorator (CACHE-004). Optionally add cache size gauge. No measurable latency impact. Reference: CACHE-004.", model="sonnet")` |
| CACHE-006 | sonnet | medium | `Task("CACHE-006: Apply @memoized_query decorator to all four target agent-query service functions. Update signatures if needed to pass config. Verify wrapped functions behave identically to originals. Reference: CACHE-004, CACHE-005.", model="sonnet")` |
| CACHE-011 | sonnet | low | `Task("CACHE-011: Write pytest test simulating fingerprint query DB failure. Verify: error caught and logged, live query executes, no exception to caller. Reference: CACHE-004.", model="sonnet")` |
| CACHE-007 | sonnet | low | `Task("CACHE-007: Add ?bypass_cache=true query param to relevant endpoints in backend/routers/agent.py. Add --no-cache flag to ccdash feature report, ccdash report aar, etc. in packages/ccdash_cli/. Wire CLI flag to REST query param. Bypass increments cache.miss counter. Reference: CACHE-006.", model="sonnet")` |
| CACHE-009 | sonnet | medium | `Task("CACHE-009: Integration test: (1) call endpoint (miss, caches); (2) call again (hit); (3) write new session/feature data triggering sync; (4) call again (fingerprint updated → miss, fresh result). Reference: CACHE-006.", model="sonnet")` |
| CACHE-010 | sonnet | low | `Task("CACHE-010: Integration test: (1) call (miss); (2) call within TTL (hit); (3) wait TTL+1 s (use TTL=2 s in test); (4) call (miss, fresh). Reference: CACHE-006.", model="sonnet")` |

---

## Objective

Implement TTL-based in-process memoization for the four heaviest agent-query endpoints. Cache keys encode project scope + query params + a data-version fingerprint (max `updated_at`) for automatic invalidation on sync. Add bypass escape hatch and OTel instrumentation.

---

## Implementation Notes

### Architectural Decisions

- OQ-2 resolved: `cachetools` is not in `backend/requirements.txt`; adding as a dependency. `cachetools.TTLCache` is the implementation. `functools.lru_cache` was rejected because it lacks TTL support.
- Cache lives in `backend/application/services/agent_queries/cache.py` — transport-neutral. All three transports (REST, CLI, MCP) benefit automatically because they all call the service layer.
- Module-level `TTLCache` instance is the cache store. Size limit should be configured (e.g., `maxsize=128`).
- Fingerprint is a lightweight `SELECT MAX(updated_at)` aggregate — not itself cached, and re-evaluated on every call to ensure freshness before cache lookup.

### Four Target Endpoints

Per the PRD and plan:
1. Project status rollup
2. Feature forensics / AAR report
3. Workflow failures summary
4. Feature list with aggregates

CACHE-001 confirms exact function names before CACHE-006 applies the decorator.

### Graceful Degradation

If fingerprint query fails: log `WARNING`, proceed with live query (cache miss). Never raise to caller. This is the reliability guarantee from the PRD's NFRs.

### Cross-Phase Notes

- Phase 4 (background materialization) depends on CACHE-006 being complete.
- `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` is added in CACHE-005 but consumed by Phase 4's background job.
- CACHE-007's `--no-cache` CLI flag is additive to Phase 1's `--timeout` plumbing; no conflict.

---

## Completion Notes

_(Fill in when phase is complete)_
