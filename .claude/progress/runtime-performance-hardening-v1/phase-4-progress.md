---
type: progress
schema_version: 2
doc_type: progress
prd: runtime-performance-hardening-v1
feature_slug: runtime-performance-hardening
phase: 4
phase_title: Observability & Telemetry
title: 'runtime-performance-hardening-v1 - Phase 4: Observability & Telemetry'
status: completed
started: 2026-04-27T15:56Z
completed: null
created: '2026-04-20'
updated: '2026-04-27'
prd_ref: docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: batch-parallel
overall_progress: 0
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- backend-architect
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: OBS-401
  description: Define and register four new Prometheus counters in backend/observability/
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 1.5 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: OBS-402
  description: Increment ccdash_frontend_poll_teardown_total when polling stops in
    Phase 1 (FE-104)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OBS-401
  - FE-104
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: OBS-403
  description: Increment ccdash_link_rebuild_scope{scope} with correct label in Phase
    2 dispatch (BE-205)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OBS-401
  - BE-205
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: OBS-404
  description: Increment ccdash_filesystem_scan_cached_total when light-mode scan
    skipped (BE-209)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OBS-401
  - BE-209
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: OBS-405
  description: Increment ccdash_workflow_detail_batch_rows with batch size in Phase
    3 (BE-303)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OBS-401
  - BE-303
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: OBS-406
  description: Extend /api/health response with runtimePerfDefaults block reporting
    TTL, deferred-rebuild, light-mode knobs
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
parallelization:
  batch_1:
  - OBS-401
  - OBS-406
  batch_2:
  - OBS-402
  - OBS-403
  - OBS-404
  - OBS-405
  critical_path:
  - OBS-401
  - OBS-403
  estimated_total_time: 1-2 days
blockers: []
success_criteria:
- id: SC-1
  description: All four counters registered; /metrics response valid
  status: pending
- id: SC-2
  description: Teardown counter increments on polling stop
  status: pending
- id: SC-3
  description: Rebuild-scope counter increments with correct label
  status: pending
- id: SC-4
  description: Scan-cache counter increments on light-mode skips
  status: pending
- id: SC-5
  description: Batch-rows counter increments with batch size
  status: pending
- id: SC-6
  description: Health endpoint includes runtimePerfDefaults with accurate values
  status: pending
files_modified: []
progress: 100
---

# runtime-performance-hardening-v1 - Phase 4: Observability & Telemetry

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/runtime-performance-hardening-v1/phase-4-progress.md \
  -t OBS-401 -s completed
```

---

## Objective

Wire four new Prometheus counters into the performance hardening instrumentation points and extend `/api/health` with a `runtimePerfDefaults` block. Provides operators visibility into teardown events, rebuild scopes, scan cache hits, and batch query sizes.

---

## Task Breakdown

| Task ID | Task Name | Subagent(s) | Model | Est. | Dependencies | Status |
|---------|-----------|-------------|-------|------|--------------|--------|
| OBS-401 | Register Prometheus counters | backend-architect | sonnet | 1.5 pts | None | pending |
| OBS-402 | Wire teardown counter | python-backend-engineer | sonnet | 0.5 pts | OBS-401, FE-104 | pending |
| OBS-403 | Wire rebuild-scope counter | python-backend-engineer | sonnet | 0.5 pts | OBS-401, BE-205 | pending |
| OBS-404 | Wire scan-cache counter | python-backend-engineer | sonnet | 0.5 pts | OBS-401, BE-209 | pending |
| OBS-405 | Wire batch-rows counter | python-backend-engineer | sonnet | 0.5 pts | OBS-401, BE-303 | pending |
| OBS-406 | Add health runtimePerfDefaults block | backend-architect | sonnet | 1 pt | None | pending |

---

## Orchestration Quick Reference

Ready-to-paste Task() delegation commands per task:

**Batch 1 (parallel; OBS-401 and OBS-406 are independent):**
```
Task(subagent="backend-architect", prompt="Implement OBS-401: Define and register four new Prometheus counters in backend/observability/otel.py (or appropriate observability module). Counters: ccdash_frontend_poll_teardown_total (no labels), ccdash_link_rebuild_scope (label: scope with values full|entities_changed|none), ccdash_filesystem_scan_cached_total (no labels), ccdash_workflow_detail_batch_rows (gauge or histogram for row count). All counters must appear in /metrics output with correct labels. Acceptance: all four registered; /metrics output valid.")
Task(subagent="backend-architect", prompt="Implement OBS-406: Extend /api/health response with a runtimePerfDefaults object block reporting the resolved (effective after env var overrides) values of: CCDASH_QUERY_CACHE_TTL_SECONDS, CCDASH_STARTUP_DEFERRED_REBUILD_LINKS, CCDASH_STARTUP_SYNC_LIGHT_MODE. Read from backend/config.py. Acceptance: block present in health response; values reflect effective env var values on both SQLite and PostgreSQL.")
```

**Batch 2 (after OBS-401 and respective phase tasks):**
```
Task(subagent="python-backend-engineer", prompt="Implement OBS-402: Wire ccdash_frontend_poll_teardown_total counter increment into the polling teardown path (FE-104 in AppRuntimeContext.tsx or equivalent backend log path). Increment after 3 unreachable checks trigger teardown. Acceptance: counter increments after teardown; verifiable in /metrics.")
Task(subagent="python-backend-engineer", prompt="Implement OBS-403: Wire ccdash_link_rebuild_scope{scope} counter increment into BE-205 rebuild dispatch (backend/db/sync_engine.py). Increment with scope='full', scope='entities_changed', or scope='none' label as appropriate. Acceptance: counter increments for each rebuild with correct scope label.")
Task(subagent="python-backend-engineer", prompt="Implement OBS-404: Wire ccdash_filesystem_scan_cached_total counter increment into BE-209 light-mode scan skip path. Increment when manifest match causes scan to be skipped. Acceptance: counter increments when light-mode scan is skipped.")
Task(subagent="python-backend-engineer", prompt="Implement OBS-405: Wire ccdash_workflow_detail_batch_rows counter/gauge increment into BE-303 batch query path (workflow_intelligence.py). Record batch size on each call to fetch_workflow_details(). Acceptance: counter increments with row count on each batch call.")
```

---

## Quality Gates

- [ ] OBS-401: All four counters registered; `/metrics` response valid
- [ ] OBS-402: Teardown counter increments on polling stop
- [ ] OBS-403: Rebuild-scope counter increments with correct label
- [ ] OBS-404: Scan-cache counter increments on light-mode skips
- [ ] OBS-405: Batch-rows counter increments with batch size
- [ ] OBS-406: Health endpoint includes runtimePerfDefaults with accurate values

---

## Blockers

None.

---

## Notes

- OBS-401 must complete before OBS-402 through OBS-405 can start.
- OBS-406 is independent of OBS-401; can be parallelized.
- OBS-402 is a cross-phase wire from frontend (FE-104) to backend counter — coordinate with Phase 1 owner.
- Phase 4 formally depends on Phases 1-3 for the instrumentation points to exist, but OBS-401 and OBS-406 can start as soon as the phase begins.
- TEST-508 (Phase 5) uses OBS-402 for validation.

---

## Completion Notes

_(Fill in when phase is complete)_
