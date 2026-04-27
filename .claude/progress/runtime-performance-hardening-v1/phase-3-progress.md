---
type: progress
schema_version: 2
doc_type: progress
prd: runtime-performance-hardening-v1
feature_slug: runtime-performance-hardening
phase: 3
phase_title: Cached Query Alignment
title: 'runtime-performance-hardening-v1 - Phase 3: Cached Query Alignment'
status: pending
started: null
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
total_tasks: 4
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- data-layer-expert
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: BE-301
  description: Change CCDASH_QUERY_CACHE_TTL_SECONDS default from 60 to 600 in backend/config.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T15:22Z
  completed: 2026-04-27T15:22Z
  evidence:
  - test: backend/tests/test_cache_warming_job.py
- id: BE-302
  description: 'Add fetch_workflow_details(ids: list[str]) batch repository helper;
    returns list of detail dicts in single query'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T15:22Z
  completed: 2026-04-27T15:22Z
  evidence:
  - test: backend/tests/test_workflow_repository_batch.py
- id: BE-303
  description: Refactor workflow_intelligence.py:157 N+1 loop to call fetch_workflow_details()
    once
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-302
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-304
  description: Keep get_workflow_registry_detail(id) method in repository for backward
    compatibility
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-302
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
parallelization:
  batch_1:
  - BE-301
  - BE-302
  batch_2:
  - BE-303
  - BE-304
  critical_path:
  - BE-302
  - BE-303
  estimated_total_time: 2-3 days
blockers: []
success_criteria:
- id: SC-1
  description: TTL default updated; verified in config.py
  status: pending
- id: SC-2
  description: Batch helper method added; accepts list and returns list of details
  status: pending
- id: SC-3
  description: N+1 loop replaced; query count verified (1 batch query vs. N single
    queries)
  status: pending
- id: SC-4
  description: Single-item method still available; no breaking changes
  status: pending
files_modified: []
progress: 50
---

# runtime-performance-hardening-v1 - Phase 3: Cached Query Alignment

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/runtime-performance-hardening-v1/phase-3-progress.md \
  -t BE-301 -s completed
```

---

## Objective

Align query cache TTL with the warmer interval to eliminate cold-window misses, and replace the N+1 workflow detail fetch loop with a single batch query. Raises `CCDASH_QUERY_CACHE_TTL_SECONDS` default from 60s to 600s and adds `fetch_workflow_details(ids)` batch repository helper.

---

## Task Breakdown

| Task ID | Task Name | Subagent(s) | Model | Est. | Dependencies | Status |
|---------|-----------|-------------|-------|------|--------------|--------|
| BE-301 | Raise TTL default | python-backend-engineer | sonnet | 0.5 pts | None | pending |
| BE-302 | Workflow batch repository helper | data-layer-expert | sonnet | 2 pts | None | pending |
| BE-303 | Replace N+1 loop with batch | python-backend-engineer | sonnet | 2 pts | BE-302 | pending |
| BE-304 | Retain single-item query | python-backend-engineer | sonnet | 1 pt | BE-302 | pending |

---

## Orchestration Quick Reference

Ready-to-paste Task() delegation commands per task:

**Batch 1 (parallel):**
```
Task(subagent="python-backend-engineer", prompt="Implement BE-301: In backend/config.py, change the default value of CCDASH_QUERY_CACHE_TTL_SECONDS from 60 to 600. The warmer cycle runs at 300s; 600s TTL means warmer completes 2 full TTL lifetimes before expiry, eliminating cold windows. Acceptance: default updated; cache hit rate improves relative to 60s default.")
Task(subagent="data-layer-expert", prompt="Implement BE-302: Add fetch_workflow_details(ids: list[str]) method to the workflow repository (likely in backend/application/services/agent_queries/ or backend/db/repositories/). Method accepts list of workflow IDs and returns list of detail dicts in a single query (no N+1). Acceptance: method accepts list; returns details in single query; no N+1 loop.")
```

**Batch 2 (after BE-302):**
```
Task(subagent="python-backend-engineer", prompt="Implement BE-303: Refactor workflow_intelligence.py at approximately line 157. Replace N+1 per-workflow fetch loop with a single call to fetch_workflow_details(ids). Output structure must match original for downstream compatibility. Acceptance: N+1 loop removed; single batch query replaces loop; output structure unchanged.")
Task(subagent="python-backend-engineer", prompt="Implement BE-304: Ensure get_workflow_registry_detail(id) single-item method remains available for backward compatibility. Internal delegation to fetch_workflow_details([id]) is acceptable. Acceptance: single-item method still importable and functional; no breaking changes to callers.")
```

---

## Quality Gates

- [ ] BE-301: TTL default updated; verified in config.py
- [ ] BE-302: Batch helper method added; accepts list and returns list of details
- [ ] BE-303: N+1 loop replaced; query count verified (1 batch query vs. N single queries)
- [ ] BE-304: Single-item method still available; no breaking changes

---

## Blockers

None.

---

## Notes

- Phase 3 can run in parallel with Phases 1 and 2 — no cross-phase dependencies at the code level.
- BE-301 TTL raise from 60s to 600s is a default change only; operators can override via env var.
- OBS-405 (Phase 4) wires the batch-rows counter into BE-303.
- TEST-507 covers BE-303 in Phase 5; TEST-509 and TEST-510 validate the TTL default impact.
- Raising TTL to 600s: if warmer fails silently, data can be stale for 10 min. OBS-406 surfaces `runtimePerfDefaults` in `/api/health` so operators can detect misconfiguration.

---

## Completion Notes

_(Fill in when phase is complete)_
