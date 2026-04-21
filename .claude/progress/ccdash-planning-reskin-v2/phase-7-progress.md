---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 7
title: Backend OQ Write-Back Endpoint + Per-Feature Token-Usage-By-Model
status: completed
created: 2026-04-20
updated: '2026-04-20'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 4
completed_tasks: 4
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
- id: T7-001
  description: Add transport-neutral OQ resolution service method to backend/application/services/agent_queries/
    accepting feature_id, oq_id, answer_text; returns OQ state with resolved flag;
    in-memory cache only (DEFER-03)
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - T0-004
  estimated_effort: 1.5 pts
  priority: high
  assigned_model: sonnet
- id: T7-002
  description: 'Add PATCH /api/planning/features/:id/open-questions/:oq_id REST endpoint
    in backend/routers/features.py or planning.py; request body {answer: string};
    response 200 with OQ state or 202 pending; error handling (404, 400)'
  status: completed
  assigned_to:
  - python-backend-engineer
  - backend-architect
  dependencies:
  - T7-001
  estimated_effort: 1.5 pts
  priority: high
  assigned_model: sonnet
- id: T7-003
  description: 'Add OTEL spans for OQ resolution (span name: planning.oq.resolve,
    attributes: feature_id, oq_id, answer_length, success); integrate with existing
    backend/observability/otel.py'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T7-002
  estimated_effort: 0.5 pts
  priority: medium
  assigned_model: sonnet
- id: T7-004
  description: Extend FeatureForensicsQueryService.build_feature_forensics (and the
    planning feature payload consumed by the Planning Deck) with a tokenUsageByModel
    field {opus:int, sonnet:int, haiku:int, other:int, total:int}. Derive by iterating
    linked_sessions[*], normalizing model via backend/model_identity.derive_model_identity(raw_model)['modelFamily'],
    and summing total_tokens. Preserves legacy total_tokens. Resolves OQ-02 and absorbs
    former DEFER-05. Unit tests cover multi-model, empty, and partial data.
  status: completed
  assigned_to:
  - python-backend-engineer
  - backend-architect
  dependencies:
  - T0-006
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - T7-001
  - T7-004
  batch_2:
  - T7-002
  batch_3:
  - T7-003
  critical_path:
  - T7-001
  - T7-002
  - T7-003
  estimated_total_time: 2-3 days
blockers: []
success_criteria:
- id: SC-7.1
  description: Service method implemented with request validation
  status: pending
- id: SC-7.2
  description: PATCH endpoint callable and validates input
  status: pending
- id: SC-7.3
  description: OQ state updated correctly (resolved flag, answer text)
  status: pending
- id: SC-7.4
  description: OpenTelemetry spans exported with correct attributes
  status: pending
- id: SC-7.5
  description: Error handling for missing/invalid inputs (404 feature, 404 OQ, 400
    empty answer)
  status: pending
- id: SC-7.6
  description: Integration tests pass
  status: pending
- id: SC-7.7
  description: tokenUsageByModel field present on planning feature payload (opus/sonnet/haiku/other
    + total) with unit tests covering multi-model, empty, and partial data (T7-004;
    resolves OQ-02)
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 7: Backend OQ Write-Back Endpoint

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-7-progress.md \
  -t T7-001 -s completed
```

---

## Phase Overview

**Title**: Backend OQ Write-Back Endpoint
**Dependencies**: Phase 0 backend audit (T0-004) complete; can run in parallel with Phases 1-6
**Entry Criteria**: `spikes[]` and `openQuestions[]` confirmed present in feature payload (OQ-01 resolved)
**Exit Criteria**: `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint live with schema validation and OTEL spans

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-7`

Phase 7 is decoupled from the frontend phases and can proceed in parallel with Phases 1-6 once T0-004 completes. The frontend (T6-002) depends on this endpoint being live for integration testing (T9-003), but T6-002 development can proceed against a mock.

Important: OQ frontmatter write-through to filesystem is explicitly deferred (DEFER-03). The endpoint returns 200 OK with in-memory state only.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T7-001 | Transport-neutral OQ resolution service | backend-architect, python-backend-engineer | 1.5 pts | T0-004 | pending |
| T7-002 | REST endpoint wrapper | python-backend-engineer, backend-architect | 1.5 pts | T7-001 | pending |
| T7-003 | OpenTelemetry instrumentation | python-backend-engineer | 0.5 pts | T7-002 | pending |
| T7-004 | Per-feature `tokenUsageByModel` aggregation | python-backend-engineer, backend-architect | 2 pts | T0-006 | pending |

---

## Quick Reference

### Batch 1 — After T0-004 (Phase 0) completes
```
Task("backend-architect", "T7-001: Add OQ resolution service method to backend/application/services/agent_queries/ (or extend planning_query_service.py). Method signature: resolve_open_question(feature_id, oq_id, answer_text) -> OQState. Pydantic validation: answer_text non-empty string. Returns OQ state with resolved=True, answer stored. No filesystem writes (DEFER-03). In-memory/cache only.")
```

### Batch 2 — After T7-001 completes
```
Task("python-backend-engineer", "T7-002: Add PATCH /api/planning/features/{feature_id}/open-questions/{oq_id} endpoint in backend/routers/features.py or new backend/routers/planning.py. Request body: {answer: string}. Response: 200 with updated OQ state, or 202 if file-sync pending. Error handling: 404 for missing feature/OQ, 400 for invalid answer (empty string). Wire to T7-001 service method.")
```

### Batch 3 — After T7-002 completes
```
Task("python-backend-engineer", "T7-003: Add OTEL spans for OQ resolution. Span name: planning.oq.resolve. Attributes: feature_id, oq_id, answer_length (int), success (bool). Integrate with backend/observability/otel.py existing instrumentation pattern. Verify spans export to configured exporter.")
```

### Batch 1b (parallel with T7-001) — After T0-006 (Phase 0) completes
```
Task("python-backend-engineer", "T7-004: Extend backend/application/services/agent_queries/feature_forensics.py (and planning.py / FeatureForensicsDTO) with per-feature tokenUsageByModel field shaped {opus:int, sonnet:int, haiku:int, other:int, total:int}. Iterate linked_sessions[*], normalize each session's model via backend/model_identity.derive_model_identity(raw_model)['modelFamily'], sum total_tokens into the appropriate bucket. Unknown families -> 'other'. total must equal existing total_tokens. Add unit tests: (a) multi-session feature with mixed opus/sonnet/haiku sessions, (b) feature with zero linked sessions, (c) feature with only 'other'/unknown model sessions, (d) lowercase/whitespace variants of model names. Resolves OQ-02 and absorbs former DEFER-05.")
```

---

## Quality Gates

- [ ] Service method implemented with Pydantic request validation
- [ ] PATCH endpoint callable and validates input
- [ ] OQ state updated correctly (resolved=True, answer text stored)
- [ ] OpenTelemetry spans exported with correct attributes
- [ ] Error handling: 404 for missing feature/OQ, 400 for empty answer
- [ ] Integration tests pass
- [ ] `tokenUsageByModel` field present on planning feature payload (T7-004): opus/sonnet/haiku/other buckets + total; unit tests for multi-model, empty, partial data pass; resolves OQ-02

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
