---
type: progress
schema_version: 2
doc_type: progress
prd: "claude-code-session-context-and-cost-observability-v1"
feature_slug: "claude-code-session-context-and-cost-observability-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md
phase: 2
title: "Context signal capture and historical enrichment"
status: "pending"
started: ""
completed: ""
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "pending"

total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer", "backend-architect"]
contributors: ["codex"]

tasks:
  - id: "CCO-2.1"
    description: "Capture hook-provided context_window and cumulative cost data from Claude session sidecars when present."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    estimated_effort: "2pt"
    priority: "high"

  - id: "CCO-2.2"
    description: "Add transcript fallback logic that derives latest live context occupancy from assistant usage records."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["CCO-2.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "CCO-2.3"
    description: "Persist context source and measurement timestamp through parser and sync-engine backfills."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CCO-2.1", "CCO-2.2"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "CCO-2.4"
    description: "Add idempotent historical backfill coverage for context observability fields."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["CCO-2.3"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["CCO-2.1"]
  batch_2: ["CCO-2.2"]
  batch_3: ["CCO-2.3"]
  batch_4: ["CCO-2.4"]
  critical_path: ["CCO-2.1", "CCO-2.2", "CCO-2.3", "CCO-2.4"]
  estimated_total_time: "8pt / ~2 days"

blockers: []

success_criteria:
  - "Hook context_window signals populate current context fields when available."
  - "Transcript fallback populates latest context occupancy when hook data is absent."
  - "Context source and measured-at timestamps are visible in session payloads."
  - "Backfill logic is idempotent for historical sessions."
---

# claude-code-session-context-and-cost-observability-v1 - Phase 2
