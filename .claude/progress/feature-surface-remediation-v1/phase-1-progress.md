---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-remediation-v1
feature_slug: feature-surface-remediation-v1
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
execution_model: batch-parallel
phase: 1
title: 'G2: URL Encoding on Write Paths'
status: completed
created: '2026-04-24'
updated: '2026-04-26'
started: 2026-04-24T00:00Z
completed: '2026-04-24'
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
contributors:
- python-backend-engineer
model_usage:
  primary: sonnet
  external: []
tasks:
- id: G2-001
  description: "Encode feature/phase/task IDs in apiClient.ts write paths \u2014 update\
    \ updateFeatureStatus(), updatePhaseStatus(), updateTaskStatus() to use encodeURIComponent()\
    \ with RFC 3986 inline comment"
  status: completed
  assigned_to:
  - frontend-developer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
  started: '2026-04-24T15:30:00Z'
  completed: '2026-04-24T15:59:16Z'
  evidence:
  - test: services/__tests__/apiClient.test.ts
  - test: backend/tests/test_client_v1_write_paths.py
  verified_by:
  - G2-002
- id: G2-002
  description: "Unit test encoding with reserved-char IDs \u2014 add \u22656 test\
    \ cases in services/__tests__/apiClient.test.ts covering #, ?, &, space, %, +"
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - G2-001
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
  started: '2026-04-24T15:30:00Z'
  completed: '2026-04-24T15:59:16Z'
  evidence:
  - test: services/__tests__/apiClient.test.ts
  - test: backend/tests/test_client_v1_write_paths.py
  verified_by:
  - G2-002
- id: G2-003
  description: "Optional: Backend validation of decoded IDs \u2014 short note or test\
    \ in backend/tests/test_client_v1_write_paths.py confirming encoded paths resolve\
    \ correctly"
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - G2-002
  estimated_effort: 0 pts (optional)
  priority: low
  assigned_model: sonnet
  started: '2026-04-24T15:30:00Z'
  completed: '2026-04-24T15:59:16Z'
  evidence:
  - test: services/__tests__/apiClient.test.ts
  - test: backend/tests/test_client_v1_write_paths.py
  verified_by:
  - G2-002
parallelization:
  batch_1:
  - G2-001
  batch_2:
  - G2-002
  batch_3:
  - G2-003
  critical_path:
  - G2-001
  - G2-002
  estimated_total_time: 1-2 days
blockers: []
success_criteria:
- id: SC-1
  description: Three write methods in apiClient.ts (updateFeatureStatus, updatePhaseStatus,
    updateTaskStatus) use encodeURIComponent() on all ID params
  status: met
- id: SC-2
  description: "Unit tests pass: \u22656 test cases with reserved characters (#, ?,\
    \ &, space, %, +)"
  status: met
- id: SC-3
  description: Existing tests for updateFeatureStatus, updatePhaseStatus, updateTaskStatus
    remain green after changes
  status: met
- id: SC-4
  description: No encoding/decoding round-trip bugs in browser console or backend
    logs
  status: met
files_modified:
- services/apiClient.ts
- services/__tests__/apiClient.test.ts
- backend/tests/test_client_v1_write_paths.py
progress: 100
---

# feature-surface-remediation-v1 — Phase 1: G2: URL Encoding on Write Paths

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/feature-surface-remediation-v1/phase-1-progress.md \
  -t G2-001 -s completed \
  --started 2026-04-24T00:00Z --completed 2026-04-24T00:00Z
```

---

## Objective

Fix silent URL encoding failures in `services/apiClient.ts` write paths by applying `encodeURIComponent()` to all feature/phase/task ID parameters before URL string interpolation. Covers the G2 gap from the feature-surface-data-loading-redesign review.

---

## Acceptance Criteria

- Three methods use `encodeURIComponent()` on all ID params; no raw string interpolation in URL paths; inline docs reference RFC 3986 § 2.2.
- ≥6 unit test cases for mixed ID strings (containing `#`, `?`, `&`, space, `%`, `+`); all pass; no encoding/decoding round-trip bugs.
- (Optional) Backend test passes for feature with special-char ID updated via encoded path.

---

## Implementation Notes

### Context

`services/apiClient.ts` write paths use raw string interpolation: e.g. `` `/features/${featureId}/status` ``. IDs containing reserved URL characters (`#`, `?`, `&`, spaces) break silently — requests route incorrectly or are rejected. Fix is client-side only; FastAPI/Starlette decodes percent-encoded path segments automatically.

### Known Gotchas

- Encoding is additive: IDs without special chars are unaffected. Verify with existing test fixtures.
- Do not double-encode: if an ID is already encoded, `encodeURIComponent()` will encode the `%` — ensure inputs are raw IDs.
- G2-003 is optional; skip if backend tests already cover round-trip or if backend accepts raw IDs without decoding.

---

## Quick Reference — Task() Delegation

```bash
# Phase 1 batch 1 (independent)
Task(frontend-developer): "Implement G2-001 in services/apiClient.ts — see phase-1-progress.md"

# Phase 1 batch 2 (after G2-001)
Task(frontend-developer): "Implement G2-002 in services/__tests__/apiClient.test.ts — see phase-1-progress.md"

# Phase 1 batch 3 (optional, after G2-002)
Task(python-backend-engineer): "Implement G2-003 in backend/tests/test_client_v1_write_paths.py — see phase-1-progress.md"
```

---

## Completion Notes

_Fill in when phase is complete._
