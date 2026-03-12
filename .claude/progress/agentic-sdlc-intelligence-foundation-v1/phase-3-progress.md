---
type: progress
schema_version: 2
doc_type: progress
prd: "agentic-sdlc-intelligence-foundation-v1"
feature_slug: "agentic-sdlc-intelligence-foundation-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
phase: 3
title: "Effectiveness scoring and derived analytics"
status: "completed"
started: "2026-03-07"
completed: "2026-03-07"
commit_refs: ["181edb9", "b10d3e9"]
pr_refs: []

overall_progress: 100
completion_estimate: "completed"

total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer", "backend-architect"]
contributors: ["codex"]

tasks:
  - id: "ASI-9"
    description: "Define metric formulas for success, efficiency, quality, and risk using existing CCDash signals."
    status: "completed"
    assigned_to: ["backend-architect"]
    dependencies: []
    estimated_effort: "2pt"
    priority: "high"

  - id: "ASI-10"
    description: "Implement the scoring engine and materialized rollup generation for workflow, agent, skill, context module, and stack scopes."
    status: "completed"
    assigned_to: ["python-backend-engineer", "backend-architect"]
    dependencies: ["ASI-9"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "ASI-11"
    description: "Detect repeated low-yield patterns such as queue waste, repeated debug loops, and weak validation paths."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-9", "ASI-10"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-12"
    description: "Add workflow-effectiveness and failure-pattern analytics endpoints with project, feature, and date filters."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-10", "ASI-11"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["ASI-9"]
  batch_2: ["ASI-10"]
  batch_3: ["ASI-11"]
  batch_4: ["ASI-12"]
  critical_path: ["ASI-9", "ASI-10", "ASI-11", "ASI-12"]
  estimated_total_time: "12pt / ~1 week"

blockers: []

success_criteria:
  - "Metric formulas are documented in code and produce deterministic outputs on fixtures."
  - "Effectiveness rollups can be recomputed deterministically for workflow, agent, skill, context module, and stack scopes."
  - "Failure patterns are ranked with evidence that explains each flag."
  - "Analytics endpoints support project, feature, and date-filtered effectiveness and failure-pattern queries."

files_modified:
  - "backend/db/sqlite_migrations.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/repositories/base.py"
  - "backend/db/repositories/intelligence.py"
  - "backend/db/repositories/postgres/intelligence.py"
  - "backend/models.py"
  - "backend/services/workflow_effectiveness.py"
  - "backend/routers/analytics.py"
  - "backend/tests/test_intelligence_repository.py"
  - "backend/tests/test_workflow_effectiveness.py"
  - "backend/tests/test_analytics_router.py"
---
