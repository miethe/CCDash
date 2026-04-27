---
type: progress
schema_version: 2
doc_type: progress
prd: runtime-performance-hardening-v1
feature_slug: runtime-performance-hardening
phase: 2
phase_title: Link Rebuild Dedup & Throttling
title: 'runtime-performance-hardening-v1 - Phase 2: Link Rebuild Dedup & Throttling'
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
total_tasks: 9
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- data-layer-expert
- backend-architect
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: BE-201
  description: Determine if rebuild_for_entities(ids) method exists in EntityLinksRepository;
    document findings
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-202
  description: Change CCDASH_STARTUP_DEFERRED_REBUILD_LINKS default from true to false
    in backend/config.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-203
  description: 'If BE-201 finds method missing: add rebuild_for_entities(ids) to EntityLinksRepository;
    if exists: skip'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - BE-201
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-04-27T15:12Z
  completed: 2026-04-27T15:12Z
  evidence:
  - test: backend/tests/test_entity_links_rebuild_for_entities.py
- id: BE-204
  description: Refactor _should_rebuild_links_after_full_sync() to return scope object
    (full|entities_changed|none)
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-205
  description: Wire scope resolver output into rebuild dispatch; call rebuild_for_entities()
    when scope is entities_changed
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-204
  - BE-203
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-206
  description: Gate incremental rebuild dispatch behind CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED
    (default false)
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-205
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-207
  description: Memoize rglob(root, pattern) results for the life of a sync run
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 2 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-208
  description: Add filesystem_scan_manifest migration (path, mtime, size); implement
    manifest diff logic
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  estimated_effort: 2 pts
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
- id: BE-209
  description: Implement manifest-based scan skip when CCDASH_STARTUP_SYNC_LIGHT_MODE=true
    and inode stats unchanged
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-208
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: adaptive
parallelization:
  batch_1:
  - BE-201
  - BE-202
  - BE-204
  - BE-207
  - BE-208
  batch_2:
  - BE-203
  batch_3:
  - BE-205
  - BE-209
  batch_4:
  - BE-206
  critical_path:
  - BE-201
  - BE-203
  - BE-205
  - BE-206
  estimated_total_time: 4-5 days
blockers: []
success_criteria:
- id: SC-1
  description: Method existence audit documented; decision point cleared
  status: pending
- id: SC-2
  description: Default changed; verified via backend/config.py
  status: pending
- id: SC-3
  description: Repository method added (if needed) with correct signature
  status: pending
- id: SC-4
  description: Scope resolver logic sound; returns correct scope in test cases
  status: pending
- id: SC-5
  description: Incremental dispatch wired; partial rebuild verified on small entity
    changes
  status: pending
- id: SC-6
  description: Feature flag gates incremental logic correctly
  status: pending
- id: SC-7
  description: Memoization reduces directory traversal count to 1 per sync run
  status: pending
- id: SC-8
  description: Migration runs cleanly; manifest table populated
  status: pending
- id: SC-9
  description: Light mode enabled → scan skipped on unchanged manifests
  status: pending
files_modified: []
progress: 66
---

# runtime-performance-hardening-v1 - Phase 2: Link Rebuild Dedup & Throttling

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/runtime-performance-hardening-v1/phase-2-progress.md \
  -t BE-201 -s completed
```

---

## Objective

Eliminate redundant startup link rebuilds and reduce filesystem scan overhead. Delivers scope-aware rebuild dispatch (full | entities_changed | none), incremental rebuild support, rglob memoization per sync run, and filesystem scan manifest caching for light-mode skip.

---

## Task Breakdown

| Task ID | Task Name | Subagent(s) | Model | Est. | Dependencies | Status |
|---------|-----------|-------------|-------|------|--------------|--------|
| BE-201 | Audit EntityLinksRepository | data-layer-expert | sonnet | 1 pt | None | pending |
| BE-202 | Default deferred-rebuild to false | python-backend-engineer | sonnet | 1 pt | None | pending |
| BE-203 | Implement rebuild_for_entities | data-layer-expert | sonnet | 2 pts | BE-201 | pending |
| BE-204 | Extend scope resolver | backend-architect | sonnet | 2 pts | None | pending |
| BE-205 | Incremental rebuild dispatch | python-backend-engineer | sonnet | 2 pts | BE-204, BE-203 | pending |
| BE-206 | Gate incremental rebuild | python-backend-engineer | sonnet | 1 pt | BE-205 | pending |
| BE-207 | rglob memoization | python-backend-engineer | sonnet | 2 pts | None | pending |
| BE-208 | Filesystem scan manifest table | data-layer-expert | sonnet | 2 pts | None | pending |
| BE-209 | Light-mode scan skip | python-backend-engineer | sonnet | 1 pt | BE-208 | pending |

---

## Orchestration Quick Reference

Ready-to-paste Task() delegation commands per task:

**Batch 1 (parallel):**
```
Task(subagent="data-layer-expert", prompt="Implement BE-201: Audit backend/db/repositories/links.py (or equivalent) to determine if rebuild_for_entities(ids: list[str]) method exists. Document findings clearly. Decision: if method exists, BE-203 can be skipped; if not, BE-203 is required. Acceptance: method existence determined and documented.")
Task(subagent="python-backend-engineer", prompt="Implement BE-202: In backend/config.py, change the default value of CCDASH_STARTUP_DEFERRED_REBUILD_LINKS from true to false. Acceptance: default changed; boot with default config triggers at most 1 full rebuild.")
Task(subagent="backend-architect", prompt="Implement BE-204: Refactor _should_rebuild_links_after_full_sync() in backend/db/sync_engine.py to return Literal['full', 'entities_changed', 'none'] instead of boolean. Determine scope based on sync deltas. Acceptance: method signature changed; logic determines correct scope.")
Task(subagent="python-backend-engineer", prompt="Implement BE-207: Memoize rglob(root, pattern) results for the life of a sync run in backend/db/sync_engine.py. Use a per-sync-run dict; do not share across runs. Document the per-run scoping assumption in code comments. Acceptance: one directory traversal per sync run; sessions/docs/progress scans share one walk.")
Task(subagent="data-layer-expert", prompt="Implement BE-208: Add filesystem_scan_manifest table migration to backend/db/migrations.py with columns (path, mtime, size). Implement manifest diff logic that compares current fs stats against stored manifest. Acceptance: migration runs on SQLite and PostgreSQL; diff logic detects unchanged paths.")
```

**Batch 2 (after BE-201):**
```
Task(subagent="data-layer-expert", prompt="Implement BE-203 (contingent on BE-201 audit): If rebuild_for_entities(ids) is missing from EntityLinksRepository, add it. Method accepts list[str] of entity IDs and rebuilds inbound/outbound edges for those entities only. If method already exists per BE-201, skip this task and mark completed. Acceptance: method exists with correct signature or confirmed already present.")
```

**Batch 3 (after BE-204 and BE-203):**
```
Task(subagent="python-backend-engineer", prompt="Implement BE-205: In backend/db/sync_engine.py, wire the scope resolver output (from BE-204) into rebuild dispatch. Call rebuild_for_entities() when scope is entities_changed; call full rebuild when scope is full; skip when scope is none. Acceptance: correct dispatch for each scope value; partial rebuild verified on small entity changes.")
Task(subagent="python-backend-engineer", prompt="Implement BE-209: In backend/db/sync_engine.py, implement manifest-based scan skip when CCDASH_STARTUP_SYNC_LIGHT_MODE=true and manifest stats match current inode stats (using BE-208 manifest table). Acceptance: light mode enabled → scan skipped on unchanged manifests; disabled or manifest miss → full walk.")
```

**Batch 4 (after BE-205):**
```
Task(subagent="python-backend-engineer", prompt="Implement BE-206: Gate incremental rebuild dispatch (BE-205) behind CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED env var (default false) in backend/config.py. When flag is disabled, scope resolver always returns 'full'. Acceptance: flag disabled → full rebuild always; flag enabled → actual scope used.")
```

---

## Quality Gates

- [ ] BE-201: Method existence audit documented; decision point cleared
- [ ] BE-202: Default changed; verified via `backend/config.py`
- [ ] BE-203: Repository method added (if needed) with correct signature
- [ ] BE-204: Scope resolver logic sound; returns correct scope in test cases
- [ ] BE-205: Incremental dispatch wired; partial rebuild verified on small entity changes
- [ ] BE-206: Feature flag gates incremental logic correctly
- [ ] BE-207: Memoization reduces directory traversal count to 1 per sync run
- [ ] BE-208: Migration runs cleanly; manifest table populated
- [ ] BE-209: Light mode enabled → scan skipped on unchanged manifests

---

## Blockers

None.

---

## Notes

- BE-203 is a contingent task: if BE-201 finds method exists, BE-203 is a no-op (mark completed immediately).
- BE-205 depends on both BE-203 and BE-204; schedule only after both complete.
- BE-206 defaults to `false` — incremental rebuild is opt-in for v1; validate correctness before flipping default.
- BE-207 scope memoization is per-sync-run only; cross-run sharing would introduce stale result bugs.
- OBS-403 (Phase 4) wires counter into BE-205 dispatch; OBS-404 wires into BE-209.
- TEST-505 covers BE-204; TEST-506 covers BE-208 in Phase 5.

---

## Completion Notes

_(Fill in when phase is complete)_
