---
type: progress
schema_version: 2
doc_type: progress
prd: runtime-performance-hardening-v1
feature_slug: runtime-performance-hardening
phase: 5
phase_title: Testing & Validation
title: 'runtime-performance-hardening-v1 - Phase 5: Testing & Validation'
status: pending
started: 2026-04-27T17:00Z
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
total_tasks: 10
completed_tasks: 9
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- testing specialist
- python-backend-engineer
- frontend-developer
- react-performance-optimizer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: TEST-501
  description: 'Vitest: transcript ring-buffer cap and truncation marker (FE-101)'
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - FE-101
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-502
  description: 'Vitest: document pagination cap and lazy-load (FE-103)'
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - FE-103
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-503
  description: 'Vitest: polling teardown after N=3 unreachable checks (FE-104)'
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - FE-104
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-504
  description: 'Vitest: in-flight request rejection clearing and 30s TTL (FE-105)'
  status: completed
  assigned_to:
  - react-performance-optimizer
  dependencies:
  - FE-105
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-505
  description: 'Pytest: scope resolver logic on various sync deltas (BE-204)'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-204
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-506
  description: 'Pytest: manifest-based scan skip on unchanged/changed paths (BE-208)'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - BE-208
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-507
  description: 'Pytest: batch workflow query returns correct detail rows; replaces
    N+1 (BE-303)'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-303
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T18:00Z
  completed: 2026-04-27T18:30Z
  evidence:
  - test: backend/tests/test_be303_batch_workflow_query.py
- id: TEST-508
  description: Run 60-min idle + worker running load test; measure tab memory at 1-min
    intervals
  status: pending
  assigned_to:
  - react-performance-optimizer
  dependencies:
  - FE-101
  - FE-102
  - FE-103
  - FE-104
  - FE-105
  - FE-106
  - FE-107
  - OBS-402
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: TEST-509
  description: 'Cold-start benchmark: boot → GET /api/project-status on 50k-session
    workspace; measure p95 latency'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-301
  - BE-202
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T18:00Z
  completed: 2026-04-27T18:30Z
  evidence:
  - test: backend/tests/perf/test_cold_start_benchmark.py
- id: TEST-510
  description: Steady-state cache hit rate validation; measure hit rate during 10-min
    steady-state
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-301
  - OBS-405
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T17:30Z
  completed: 2026-04-27T18:00Z
  evidence:
  - test: backend/tests/perf/test_cache_hit_rate.py
  verified_by:
  - TEST-510
parallelization:
  batch_1:
  - TEST-501
  - TEST-502
  - TEST-503
  - TEST-504
  - TEST-505
  - TEST-506
  - TEST-507
  - TEST-509
  - TEST-510
  batch_2:
  - TEST-508
  critical_path:
  - FE-101
  - FE-107
  - OBS-402
  - TEST-508
  estimated_total_time: 3-4 days
blockers: []
success_criteria:
- id: SC-1
  description: All Vitest coverage >80% for FE changes (TEST-501 through TEST-504)
  status: pending
- id: SC-2
  description: All pytest coverage for BE changes passing (TEST-505 through TEST-507)
  status: pending
- id: SC-3
  description: Load test succeeds; tab memory flat within ±50MB over 60-min idle
  status: pending
- id: SC-4
  description: Cold-start benchmark p95 < 500ms on 50k-session workspace
  status: pending
- id: SC-5
  description: Cache hit rate ≥ 95% in 10-min steady-state operation
  status: pending
files_modified: []
progress: 90
---

# runtime-performance-hardening-v1 - Phase 5: Testing & Validation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/runtime-performance-hardening-v1/phase-5-progress.md \
  -t TEST-501 -s completed
```

---

## Objective

Comprehensive Vitest and pytest coverage for all Phase 1-4 changes, plus execution of the load-test harness and cold-start/cache benchmarks. Phase 5 is the gate before documentation finalization — all quality criteria must pass before Phase 6 begins.

---

## Task Breakdown

| Task ID | Task Name | Subagent(s) | Model | Est. | Dependencies | Status |
|---------|-----------|-------------|-------|------|--------------|--------|
| TEST-501 | Vitest: transcript windowing | frontend-developer | sonnet | 1 pt | FE-101 | pending |
| TEST-502 | Vitest: document pagination | frontend-developer | sonnet | 1 pt | FE-103 | pending |
| TEST-503 | Vitest: polling teardown | frontend-developer | sonnet | 1 pt | FE-104 | pending |
| TEST-504 | Vitest: in-flight request GC | react-performance-optimizer | sonnet | 1 pt | FE-105 | pending |
| TEST-505 | Pytest: scope resolver | python-backend-engineer | sonnet | 1 pt | BE-204 | pending |
| TEST-506 | Pytest: manifest diff | data-layer-expert | sonnet | 1 pt | BE-208 | pending |
| TEST-507 | Pytest: batch workflow query | python-backend-engineer | sonnet | 1 pt | BE-303 | pending |
| TEST-508 | Load-test harness execution | react-performance-optimizer | sonnet | 1 pt | FE-101–FE-107, OBS-402 | pending |
| TEST-509 | Cold-start benchmark | python-backend-engineer | sonnet | 1 pt | BE-301, BE-202 | pending |
| TEST-510 | Cache hit rate validation | python-backend-engineer | sonnet | 0.5 pts | BE-301, OBS-405 | pending |

---

## Orchestration Quick Reference

Ready-to-paste Task() delegation commands per task:

**Batch 1 (all parallel; each depends only on its Phase 1-4 prerequisite):**
```
Task(subagent="frontend-developer", prompt="Implement TEST-501: Write Vitest tests for FE-101 transcript ring-buffer cap. Tests must verify: cap enforcement at 5000 rows, oldest-row drop behavior, truncation marker emission, no unbounded memory growth. Target >80% coverage for modified transcript files. Acceptance: cap enforcement, marker emission, no memory unbounding verified.")
Task(subagent="frontend-developer", prompt="Implement TEST-502: Write Vitest tests for FE-103 document pagination cap. Tests must verify: cap at 2000 documents, lazy-load trigger on scroll, no unbounded array growth. Target >80% coverage for AppEntityDataContext changes. Acceptance: cap at 2000 and lazy-load on scroll verified.")
Task(subagent="frontend-developer", prompt="Implement TEST-503: Write Vitest tests for FE-104 polling teardown. Tests must verify: teardown after exactly 3 unreachable checks, 'backend disconnected' banner rendered, manual retry button functional. Target >80% coverage for AppRuntimeContext changes. Acceptance: teardown, banner, retry all verified.")
Task(subagent="react-performance-optimizer", prompt="Implement TEST-504: Write Vitest tests for FE-105 in-flight request GC. Tests must verify: rejection clears entry from sessionDetailRequestsRef, 30s TTL expiry removes entry, no unbounded map growth after network failures. Target >80% coverage for apiClient.ts changes. Acceptance: rejection clearing, TTL expiry, no unbounded growth verified.")
Task(subagent="python-backend-engineer", prompt="Implement TEST-505: Write pytest tests for BE-204 scope resolver. Tests must cover: scope='full' on large entity change sets, scope='entities_changed' on small partial changes, scope='none' on no-change sync. Cover edge cases. Acceptance: correct scope returned for small/large entity changes and no-change syncs.")
Task(subagent="data-layer-expert", prompt="Implement TEST-506: Write pytest tests for BE-208 filesystem scan manifest. Tests must verify: manifest match skips walk (returns cached result), manifest mismatch triggers full walk, new paths not in manifest trigger walk. Acceptance: manifest match skips walk; mismatch triggers walk.")
Task(subagent="python-backend-engineer", prompt="Implement TEST-507: Write pytest tests for BE-303 batch workflow query. Tests must verify: single query with N workflow IDs returns N detail rows, output structure matches original per-workflow fetch output, no N+1 query pattern. Acceptance: single query returns N rows; output matches original.")
Task(subagent="python-backend-engineer", prompt="Implement TEST-509: Execute cold-start benchmark. Boot the CCDash backend and measure p95 latency for GET /api/project-status on a 50k-session workspace (generate synthetic if real workspace unavailable). Run with new defaults (TTL=600s, deferred_rebuild=false). Acceptance: p95 latency < 500ms.")
Task(subagent="python-backend-engineer", prompt="Implement TEST-510: Execute cache hit rate validation. Run steady-state load test for 10 minutes with queries firing at ~300s warmer interval and TTL=600s. Measure cache hit rate. Acceptance: hit rate ≥ 95% during 10-min steady-state.")
```

**Batch 2 (after FE-107 and OBS-402 complete):**
```
Task(subagent="react-performance-optimizer", prompt="Implement TEST-508: Execute load-test harness (FE-107) against 60-min idle + worker running scenario. Measure tab memory at 1-min intervals using the harness. Export JSON results. Verify tab memory stays within ±50MB of baseline over 60 minutes. Acceptance: tab memory flat within ±50MB of baseline.")
```

---

## Quality Gates

- [ ] TEST-501 through TEST-504: All Vitest coverage >80% for FE changes
- [ ] TEST-505 through TEST-507: All pytest coverage for BE changes; tests passing
- [ ] TEST-508: Load test succeeds; memory flat within ±50MB
- [ ] TEST-509: Cold-start benchmark p95 < 500ms
- [ ] TEST-510: Cache hit rate ≥ 95% in steady-state

---

## Blockers

None.

---

## Notes

- TEST-508 is the most time-intensive task (requires 60-min execution time); schedule early.
- If 50k-session workspace is unavailable for TEST-509, generate a synthetic dataset.
- All unit tests (TEST-501 through TEST-507) can run in full parallel.
- TEST-509 and TEST-510 are backend benchmarks and can run in parallel with unit tests.
- Phase 6 cannot begin until all Phase 5 quality gates pass.

---

## Completion Notes

_(Fill in when phase is complete)_
