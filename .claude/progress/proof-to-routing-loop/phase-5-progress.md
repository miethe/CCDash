---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 5
title: "Transport Surfaces"
status: pending
created: "2026-07-29"
updated: "2026-07-29"
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["python-backend-engineer"]
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T5-001"
    description: "REST endpoint — GET /api/v1/routing/rollup via _client_v1_routing_rollup.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    priority: "high"
    estimated_effort: "2h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T5-002"
    description: "MCP tool — ccdash_routing_rollup tool in backend/mcp/tools/routing.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T5-001"]
    priority: "high"
    estimated_effort: "1.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T5-003"
    description: "CLI command — ccdash routing rollup via backend/cli/commands/routing.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T5-002"]
    priority: "high"
    estimated_effort: "1.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T5-004"
    description: "Shared DTO + disabled-envelope test — verify all three transports byte-identical when disabled"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T5-003"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

parallelization:
  batch_1: ["T5-001"]
  batch_2: ["T5-002"]
  batch_3: ["T5-003"]
  batch_4: ["T5-004"]
  critical_path: ["T5-001", "T5-002", "T5-003", "T5-004"]
  estimated_total_time: "6h"

blockers: []

success_criteria: []

files_modified:
  - "backend/routers/_client_v1_routing_rollup.py"
  - "backend/routers/client_v1.py"
  - "backend/mcp/tools/routing.py"
  - "backend/mcp/tools/__init__.py"
  - "backend/cli/commands/routing.py"
  - "backend/cli/main.py"
  - "backend/tests/test_routing_rollup_transports.py"

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

*Fill in when phase is complete*

- All three transports operational (GET /api/v1/routing/rollup, MCP tool, CLI command)
- Disabled-state test green (byte-identical across all three when flag is off)
- D9 socialization attempt documented (even if informal)
- All three transports use same RoutingRollupResponseDTO with no per-transport reshaping
