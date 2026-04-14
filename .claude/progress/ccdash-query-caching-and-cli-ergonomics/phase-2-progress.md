---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-query-caching-and-cli-ergonomics
feature_slug: ccdash-query-caching-and-cli-ergonomics
phase: 2
title: DTO Alias Fields
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
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: DTO-001
  description: Inspect FeatureForensicsDTO and identify canonical feature name/status
    field sources in models.py and feature_forensics.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 1 pt
  priority: low
  assigned_model: haiku
  model_effort: low
- id: DTO-002
  description: 'Add name: str = '''', status: str = '''', and telemetry_available:
    {tasks: bool, documents: bool, sessions: bool} top-level fields to FeatureForensicsDTO
    with docstring note'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - DTO-001
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: DTO-003
  description: 'Populate alias fields and telemetry_available in FeatureForensicsQueryService
    (get_forensics method): name/status from feature row; telemetry_available.tasks
    = len(dto.linked_tasks) > 0, etc.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - DTO-002
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: DTO-004
  description: Update CLI formatters and MCP tool schema to use top-level name/status
    fields and include telemetry_available indicator in feature detail output
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - DTO-003
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: DTO-005
  description: "Add pytest regression test: dto.name == dto.<nested>, dto.status ==\
    \ dto.<nested>, and telemetry_available.sessions == (len(dto.linked_sessions)\
    \ > 0) \u2014 CI guard for parity"
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - DTO-004
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
  model_effort: low
- id: DTO-006
  description: 'Verify backward compatibility: old nested access still deserializes
    and functions; no breaking schema changes'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - DTO-005
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: haiku
  model_effort: low
parallelization:
  batch_1:
  - DTO-001
  batch_2:
  - DTO-002
  batch_3:
  - DTO-003
  batch_4:
  - DTO-004
  batch_5:
  - DTO-005
  batch_6:
  - DTO-006
  critical_path:
  - DTO-001
  - DTO-002
  - DTO-003
  - DTO-004
  - DTO-005
  - DTO-006
  estimated_total_time: 1-1.5 days
blockers: []
success_criteria:
- id: SC-2.1
  description: FeatureForensicsDTO updated with name, status, and telemetry_available
    fields
  status: pending
- id: SC-2.2
  description: Fields populated correctly in service layer (alias + telemetry_available)
  status: pending
- id: SC-2.3
  description: CLI and MCP formatters use top-level fields and surface telemetry_available
  status: pending
- id: SC-2.4
  description: Regression test asserts parity between alias fields and nested values,
    including telemetry_available semantics
  status: pending
- id: SC-2.5
  description: 'Backward compatibility: old nested access still works'
  status: pending
- id: SC-2.6
  description: No schema-level breaking changes
  status: pending
files_modified:
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/feature_forensics.py
- packages/ccdash_cli/src/ccdash_cli/
- backend/mcp/server.py
- backend/tests/
progress: 100
---

# CCDash Query Caching and CLI Ergonomics - Phase 2: DTO Alias Fields

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-2-progress.md \
  -t DTO-001 -s completed
```

---

## Quick Reference

Tasks are fully sequential. Phase 2 is independent of Phase 1 and can run concurrently with it.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| DTO-001 | haiku | low | `Task("DTO-001: Read backend/application/services/agent_queries/models.py and feature_forensics.py. Identify FeatureForensicsDTO class, its feature_slug and feature_status fields, and where they are populated. Document exact field names and nesting structure.", model="haiku")` |
| DTO-002 | sonnet | low | `Task("DTO-002: Add name: str = '', status: str = '', and telemetry_available: dict with tasks/documents/sessions bool fields to FeatureForensicsDTO in backend/application/services/agent_queries/models.py. Add docstring: 'Alias fields: mirror canonical nested values. telemetry_available indicates data completeness.' OQ-3 resolved: feature_status is a plain str, no union type.", model="sonnet")` |
| DTO-003 | sonnet | low | `Task("DTO-003: Populate dto.name, dto.status, and dto.telemetry_available in FeatureForensicsQueryService (get_forensics method). name/status from feature row; telemetry_available.tasks = len(dto.linked_tasks) > 0, telemetry_available.documents = len(dto.linked_documents) > 0, telemetry_available.sessions = len(dto.linked_sessions) > 0. Reference: DTO-002.", model="sonnet")` |
| DTO-004 | sonnet | low | `Task("DTO-004: Search packages/ccdash_cli/ and backend/mcp/ for nested access patterns extracting feature name/status. Update to use dto.name and dto.status top-level fields. Include telemetry_available in feature detail output (e.g., 'Session telemetry: available'). Reference: DTO-003.", model="sonnet")` |
| DTO-005 | sonnet | low | `Task("DTO-005: Write pytest test in backend/tests/ loading a FeatureForensicsDTO fixture. Assert dto.name == dto.<nested_name_path>, dto.status == dto.<nested_status_path>, and telemetry_available.sessions == (len(dto.linked_sessions) > 0). CI regression guard. Reference: DTO-004.", model="sonnet")` |
| DTO-006 | haiku | low | `Task("DTO-006: Manually verify backward compatibility — old code drilling into nested FeatureForensicsDTO fields still deserializes without error. Confirm no breaking schema changes. Reference: DTO-005.", model="haiku")` |

---

## Objective

Add top-level `name`, `status`, and `telemetry_available` fields to `FeatureForensicsDTO`. The alias fields let CLI, MCP, and agent consumers read feature identity without nested access. The `telemetry_available` object indicates whether tasks, documents, and sessions data is populated (non-empty), helping callers reason about data gaps. Fields are populated once in the service layer; all transports read the flat DTO.

---

## Implementation Notes

### Architectural Decisions

- Alias fields are set in the service layer (`FeatureForensicsQueryService.get_forensics`), not in the Pydantic model itself (no `@model_validator`). This keeps model validation simple and makes the population site visible.
- OQ-3 resolved: `feature_status` is a plain `str`, so alias fields are `str = ""` with no Optional needed.
- `telemetry_available` is a nested object (tasks/documents/sessions booleans), computed as `len(array) > 0` for each. Use a simple inline dict or a small Pydantic model (`TelemetryAvailable`).
- Backward compatibility: existing nested fields are preserved; no removals or renames.

### Key Files

- `backend/application/services/agent_queries/models.py` — DTO definition
- `backend/application/services/agent_queries/feature_forensics.py` — population site

### Patterns and Best Practices

- After constructing the DTO: `dto.name = feature_row.feature_name; dto.status = feature_row.feature_status`
- Pydantic v2 models require `model_config = ConfigDict(populate_by_name=True)` if using aliases. Since these are new additive fields (not Pydantic `alias`), no config change needed.

### Cross-Phase Notes

- Phase 2 is independent of Phase 1; both can run in parallel.
- Phase 3 (cache) wraps the service methods that return FeatureForensicsDTO; DTO-003's population is upstream of any cache wrapper.

---

## Completion Notes

_(Fill in when phase is complete)_
