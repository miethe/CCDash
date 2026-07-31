---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 5
title: Transport Surfaces
status: completed
created: '2026-07-29'
updated: '2026-07-31'
started: '2026-07-31'
completed: '2026-07-31'
overall_progress: 100
completion_estimate: on-track
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
contributors: []
commit_refs:
- e63f3c0
- c995b3f
- ca79e34
- a81ace6
- 565e948
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T5-001
  description: REST endpoint — GET /api/v1/routing/rollup via _client_v1_routing_rollup.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  priority: high
  estimated_effort: 2h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T00:00Z
  completed: 2026-07-31T00:00Z
  evidence:
  - commit: 5725b75
  verified_by:
  - T5-004
  - T6-006
- id: T5-002
  description: MCP tool — ccdash_routing_rollup tool in backend/mcp/tools/routing.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T5-001
  priority: high
  estimated_effort: 1.5h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T00:00Z
  completed: 2026-07-31T00:00Z
  evidence:
  - commit: e63f3c0
  verified_by:
  - T5-004
  - T6-006
- id: T5-003
  description: CLI command — ccdash routing rollup via backend/cli/commands/routing.py
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T5-002
  priority: high
  estimated_effort: 1.5h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T18:00Z
  completed: 2026-07-31T18:41Z
  evidence:
  - commit: c995b3f
  verified_by:
  - T5-004
  - T6-006
- id: T5-004
  description: Shared DTO + disabled-envelope test — verify all three transports byte-identical
    when disabled
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T5-003
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T19:00Z
  completed: 2026-07-31T19:35Z
  evidence:
  - commit: ca79e34
  verified_by:
  - T6-006
parallelization:
  batch_1:
  - T5-001
  batch_2:
  - T5-002
  batch_3:
  - T5-003
  batch_4:
  - T5-004
  critical_path:
  - T5-001
  - T5-002
  - T5-003
  - T5-004
  estimated_total_time: 6h
blockers:
- id: BLOCKER-P5-D9
  title: D9 — router-owner response to the D5 metric-payload socialization attempt
    is outstanding
  severity: low
  blocking: []
  resolution: Non-blocking per D9's own rationale (decisions-block.md) — informal
    cross-repo GitHub issue opened 2026-07-31 (https://github.com/miethe/MeatySkills/issues/1)
    documenting the D5 metric-payload shape for the router owner; awaiting response.
    Does not gate this phase's completion; tracked here until the issue is closed
    or superseded by Phase 6/DI-1 work.
  created: '2026-07-31'
success_criteria: []
files_modified:
- backend/routers/_client_v1_routing_rollup.py
- backend/routers/client_v1.py
- backend/mcp/tools/routing.py
- backend/mcp/tools/__init__.py
- backend/cli/commands/routing.py
- backend/cli/main.py
- backend/tests/test_routing_rollup_transports.py
- backend/tests/test_client_v1_routing_rollup.py
progress: 100
---

# Phase 5: Transport Surfaces

**Total Tasks**: 4  
**Estimated Effort**: 3 points  
**Key Files**: `_client_v1_routing_rollup.py`, `routing.py` (MCP), `routing.py` (CLI), transport tests

## Objective

Expose Phase-3-computed `routing_rollup` rollup read-only through REST, MCP, and CLI — the same three doors CCDash already opened for `aar_reviews`. No new derivation logic; all three transports use the same Phase-3 service and return the identical DTO shape.

## Implementation Notes

### Architectural Decisions

- **Wave placement**: Runs in same wave as Phase 4 (parallel) — Phase 5 touches routers/mcp/cli, Phase 4 touches jobs/runtime (disjoint)
- **Zero live aggregation**: All three transports read already-persisted rows from Phase 4's sweep via Phase 3's query service
- **Shared DTO contract**: All three transports serialize the exact same `RoutingRollupResponseDTO` with zero per-transport reshaping
- **Default-off disabled state**: REST returns HTTP 200 (not 404) with empty envelope when flag is off (AC-4)

### Patterns and Best Practices

- Clones the shipped `aar_reviews` three-transport pattern exactly
- REST module mirrors `_client_v1_aar_review.py`'s param-extractor + memoized-query + thin-handler pattern
- MCP tool mirrors `reports.py`'s `ccdash_aar_review` tool shape (singleton service, execute_query wrapper, build_envelope)
- CLI command mirrors `report.py`'s `aar_review` command shape (typer.Typer sub-app, error handling, output formatting)

### Known Gotchas

- **ICA-offload eligible**: All four tasks are mechanical clones; cost-shift candidates, but Phase 6 gates must re-run on return
- **Capability string already present**: Phase 1 added `"routing:feedback"` to `_V1_CAPABILITIES` — this phase only consumes it, never adds it again
- **Cache invalidation already handled**: Phase 4's sweep job calls `aclear_project_cache` — Phase 5 only reads via the memoized pattern
- **Resilience pattern**: On repository read failure, degrade to empty/disabled-shaped payload, never HTTP error
- **D9 decision gate**: Socialization of D5 metric-payload to router owner must be documented in completion note before phase seals

### Development Setup

- Familiarity with `_client_v1_aar_review.py` REST module pattern
- Knowledge of FastMCP `@mcp.tool()` decorator and `execute_query` wrapper
- Understanding of Typer CLI command structure and output formatting
- Ability to parametrize tests across multiple transports (REST/MCP/CLI)

## Completion Notes

- All 4 tasks (T5-001–T5-004) are complete; `backend/tests/test_routing_rollup_transports.py`
  (T5-004, commit `ca79e34`) is green — 4/4 assertions pass, including the cross-transport
  byte-identical disabled-envelope comparison (REST HTTP 200 + `data`, MCP `build_envelope`
  normalized back to the DTO level, CLI flat `--json`).
- T5-004 required **zero changes** to any of the three transport modules — confirms the phase's
  own prediction ("if T5-001/T5-002/T5-003 faithfully cloned the AAR-review pattern, this test
  should pass with zero changes required").
- **Review-fix pass (2026-07-31, commits `a81ace6`/`565e948`)**: closed two gaps identified by
  post-completion review before this phase's `status` could flip:
  1. **D9 decision gate resolved**: an informal, real cross-repo socialization attempt of the D5
     metric-payload shape was made — GitHub issue opened on `github.com/miethe/MeatySkills`
     (<https://github.com/miethe/MeatySkills/issues/1>, 2026-07-31), documenting the full DTO shape
     and three concrete router-owner questions. Response is pending (tracked under `BLOCKER-P5-D9`
     below, non-blocking per D9's own rationale) — full record in
     `.claude/worknotes/proof-to-routing-loop/decisions-block.md` § "D9 Socialization Attempt" and
     this plan's Notes → Learnings.
  2. **Enabled+seeded-rows reassembly test coverage added**: `backend/tests/
     test_client_v1_routing_rollup.py` (commit `a81ace6`, 21/21 green) — unit coverage for
     `_build_response_from_rows`/`_row_to_key_dto` (the FR-7 counter-resummation logic previously
     exercised by zero automated tests) plus an end-to-end REST round trip with real seeded
     `routing_rollup` rows and `CCDASH_ROUTING_FEEDBACK_ENABLED=true`, replacing T5-001's
     previously-uncommitted "manual pytest-harness round trip" claim with a durable regression
     test.
- Phase 5's Quality Gates are now fully ticked/justified (see the phase plan's Quality Gates
  section) and `status` is flipped to `completed` with this review-fix pass.

- [x] All three transports operational (GET /api/v1/routing/rollup, MCP tool, CLI command)
- [x] Disabled-state test green (byte-identical across all three when flag is off)
- [x] D9 socialization attempt documented (even if informal) — GitHub issue,
  <https://github.com/miethe/MeatySkills/issues/1>, 2026-07-31
- [x] All three transports use same RoutingRollupResponseDTO with no per-transport reshaping
