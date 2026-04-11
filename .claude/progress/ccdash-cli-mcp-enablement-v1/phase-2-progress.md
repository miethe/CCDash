---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-cli-mcp-enablement-v1"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: /docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1/phase-2-rest-endpoints.md
phase: 2
title: "REST Composite Endpoints"
status: "in_progress"
started: "2026-04-11"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 10
completion_estimate: "2-3 days"

total_tasks: 4
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["worker"]
contributors: ["explorer"]

tasks:
  - id: "P2-T1"
    description: "Create backend/routers/agent.py, add module-scope query service instances, wire backend/request_scope.py dependencies, and register agent_router in backend/runtime/bootstrap.py."
    status: "in_progress"
    assigned_to: ["worker"]
    dependencies: []
    estimated_effort: "1pt"
    priority: "critical"

  - id: "P2-T2"
    description: "Implement GET /api/agent/project-status and GET /api/agent/feature-forensics/{feature_id} with thin handlers and repo-style parameter documentation."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P2-T1"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P2-T3"
    description: "Implement GET /api/agent/workflow-diagnostics and POST /api/agent/reports/aar, keeping any project_id field reserved/ignored until ReportingQueryService supports it."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P2-T1"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P2-T4"
    description: "Add backend/tests/test_agent_router.py using top-level async unittest patterns, verify OpenAPI visibility, and close the Phase 2 contract gate."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P2-T2", "P2-T3"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["P2-T1"]
  batch_2: ["P2-T2", "P2-T3"]
  batch_3: ["P2-T4"]
  critical_path: ["P2-T1", "P2-T2", "P2-T4"]
  estimated_total_time: "4pt / 2-3 days"

blockers: []

success_criteria:
  - "The router prefix is /api/agent and registration matches backend/runtime/bootstrap.py."
  - "Handlers use backend/request_scope.py and resolve_application_request(...) instead of request.app.state.container.core_ports."
  - "Each handler delegates to exactly one Phase 1 query service with no inline query logic."
  - "AAR request payload documentation does not overstate current project_id support."
  - "A new top-level async unittest module validates all four handlers."
  - "Phase 1 DTOs remain unchanged after HTTP validation."

files_modified:
  - ".claude/progress/ccdash-cli-mcp-enablement-v1/phase-2-progress.md"
  - "backend/routers/agent.py"
  - "backend/runtime/bootstrap.py"
  - "backend/tests/test_agent_router.py"
---

# ccdash-cli-mcp-enablement-v1 - Phase 2: REST Composite Endpoints

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-cli-mcp-enablement-v1/phase-2-progress.md -t P2-TX -s completed
```

## Objective

Expose the completed Phase 1 agent query services through thin `/api/agent/*` HTTP adapters that match current CCDash router, DI, registration, and test conventions.

## Update Workflow

- Complete `P2-T1` first.
- Run `P2-T2` and `P2-T3` in parallel after `P2-T1` is done.
- Start `P2-T4` only after both read-path batches are merged.
- Commit after each completed task or merged batch.
