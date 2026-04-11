---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-cli-mcp-enablement-v1"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: /docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1/phase-1-agent-queries.md
phase: 1
title: "Agent Query Foundation"
status: "in_progress"
started: "2026-04-11"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 70
completion_estimate: "on-track"

total_tasks: 8
completed_tasks: 5
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["worker"]
contributors: ["explorer"]

tasks:
  - id: "P1-T1"
    description: "Create the agent_queries package, shared DTOs/submodels, canonical freshness/source-ref helpers, and export surface."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: []
    estimated_effort: "1pt"
    priority: "critical"

  - id: "P1-T2"
    description: "Implement ProjectStatusQueryService plus backend/tests/test_agent_queries_project_status.py using the real repository/service APIs."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P1-T1"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "P1-T3"
    description: "Implement FeatureForensicsQueryService plus backend/tests/test_agent_queries_feature_forensics.py using existing feature/session/document/task correlation helpers."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P1-T1"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "P1-T4"
    description: "Implement WorkflowDiagnosticsQueryService plus backend/tests/test_agent_queries_workflow_diagnostics.py by reusing workflow registry/effectiveness/failure-pattern helpers."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P1-T1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "P1-T5"
    description: "Implement ReportingQueryService plus backend/tests/test_agent_queries_reporting.py with deterministic AAR output built from existing correlated sources."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P1-T1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "P1-T6"
    description: "Add shared fixtures, helper tests, cross-service regressions, and coverage verification for the agent_queries module."
    status: "in_progress"
    assigned_to: ["worker"]
    dependencies: ["P1-T2", "P1-T3", "P1-T4", "P1-T5"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "P1-T7"
    description: "Write integration tests against a real SQLite test database and verify DTO JSON round-trips."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P1-T6"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P1-T8"
    description: "Document the agent_queries architecture in README.md and complete architecture review/sign-off checks."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P1-T2", "P1-T3", "P1-T4", "P1-T5", "P1-T6", "P1-T7"]
    estimated_effort: "1pt"
    priority: "medium"

parallelization:
  batch_1: ["P1-T1"]
  batch_2: ["P1-T2", "P1-T3", "P1-T4", "P1-T5"]
  batch_3: ["P1-T6"]
  batch_4: ["P1-T7"]
  batch_5: ["P1-T8"]
  critical_path: ["P1-T1", "P1-T2", "P1-T6", "P1-T7", "P1-T8"]
  estimated_total_time: "15pt / 5-7 days"

blockers: []

success_criteria:
  - "Shared DTO contracts are frozen before service implementation begins."
  - "P1-T2 through P1-T5 each own exactly one service file and one unit test file."
  - "All services return explicit ok/partial/error status semantics."
  - "Canonical data_freshness and source_refs helpers are used across all DTOs."
  - "Pytest coverage for backend/application/services/agent_queries exceeds 90%."
  - "Integration tests pass against a real SQLite fixture database."
  - "No business logic duplication is introduced relative to existing analytics, session intelligence, workflow, or feature-correlation helpers."

files_modified:
  - ".claude/progress/ccdash-cli-mcp-enablement-v1/phase-1-progress.md"
  - "backend/application/services/agent_queries/__init__.py"
  - "backend/application/services/agent_queries/models.py"
  - "backend/application/services/agent_queries/_filters.py"
  - "backend/application/services/agent_queries/project_status.py"
  - "backend/application/services/agent_queries/feature_forensics.py"
  - "backend/application/services/agent_queries/workflow_intelligence.py"
  - "backend/application/services/agent_queries/reporting.py"
  - "backend/application/services/agent_queries/README.md"
  - "backend/tests/test_agent_queries_project_status.py"
  - "backend/tests/test_agent_queries_feature_forensics.py"
  - "backend/tests/test_agent_queries_workflow_diagnostics.py"
  - "backend/tests/test_agent_queries_reporting.py"
  - "backend/tests/test_agent_queries_shared.py"
  - "backend/tests/test_agent_queries_integration.py"
  - "backend/tests/fixtures/agent_queries_test_data.py"
---

# ccdash-cli-mcp-enablement-v1 - Phase 1: Agent Query Foundation

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-cli-mcp-enablement-v1/phase-1-progress.md -t P1-TX -s completed
```

## Objective

Freeze the transport-neutral `agent_queries` contract, then implement the four Phase 1 services on top of the repo's real application-service and repository APIs without duplicating workflow or feature-correlation logic.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("worker", "Execute P1-T1: create shared DTOs/submodels, freshness/source-ref helpers, and the export surface for backend/application/services/agent_queries")

# Batch 2 (after P1-T1)
Task("worker", "Execute P1-T2: implement ProjectStatusQueryService and backend/tests/test_agent_queries_project_status.py using the real repository/service APIs")
Task("worker", "Execute P1-T3: implement FeatureForensicsQueryService and backend/tests/test_agent_queries_feature_forensics.py using existing feature/session/document/task correlation helpers")
Task("worker", "Execute P1-T4: implement WorkflowDiagnosticsQueryService and backend/tests/test_agent_queries_workflow_diagnostics.py by reusing workflow registry/effectiveness/failure-pattern helpers")
Task("worker", "Execute P1-T5: implement ReportingQueryService and backend/tests/test_agent_queries_reporting.py with deterministic AAR output built from existing correlated sources")

# Batch 3
Task("worker", "Execute P1-T6: add shared fixtures, helper tests, cross-service regressions, and coverage verification")

# Batch 4
Task("worker", "Execute P1-T7: add SQLite-backed integration coverage and DTO JSON round-trip tests")

# Batch 5
Task("worker", "Execute P1-T8: document the agent_queries architecture in README.md and complete architecture review checks")
```

## Validation Notes

- Phase 1 plan and task contracts were revalidated on 2026-04-11 against the current repo APIs, packaging flow, and official Typer/MCP documentation.
- CLI packaging work in later phases must add backend packaging metadata plus an editable install step to `scripts/setup.mjs`; the repo does not currently expose a `ccdash` console script.
- MCP validation in later phases must use the pinned SDK's documented client harness, not a speculative `mcp.test_client()` helper.
