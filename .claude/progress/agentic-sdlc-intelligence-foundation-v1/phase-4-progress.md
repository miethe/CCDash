---
type: progress
schema_version: 2
doc_type: progress
prd: "agentic-sdlc-intelligence-foundation-v1"
feature_slug: "agentic-sdlc-intelligence-foundation-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
phase: 4
title: "Recommended stack service and execution-context integration"
status: "in_progress"
started: "2026-03-07"
completed: ""
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "in_progress"

total_tasks: 4
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer", "backend-architect", "frontend-developer"]
contributors: ["codex"]

tasks:
  - id: "ASI-13"
    description: "Extend backend/frontend types with recommended stack, alternatives, evidence, and warnings."
    status: "in_progress"
    assigned_to: ["python-backend-engineer", "frontend-developer"]
    dependencies: []
    estimated_effort: "2pt"
    priority: "high"

  - id: "ASI-14"
    description: "Implement deterministic recommender that merges feature rules with historical effectiveness and definition resolution."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["ASI-13"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "ASI-15"
    description: "Add similar-work retrieval for recommendation evidence with bounded relevance and similarity reasons."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-14"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-16"
    description: "Wire recommended stack into the feature execution context endpoint and keep command recommendations intact."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-13", "ASI-14", "ASI-15"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["ASI-13"]
  batch_2: ["ASI-14"]
  batch_3: ["ASI-15"]
  batch_4: ["ASI-16"]
  critical_path: ["ASI-13", "ASI-14", "ASI-15", "ASI-16"]
  estimated_total_time: "11pt / ~1 week"

blockers: []

success_criteria:
  - "Execution-context payload adds stack recommendation fields without breaking current command recommendation consumers."
  - "Primary stack, alternatives, evidence, and definition-resolution warnings degrade cleanly when SkillMeat data is partial or missing."
  - "Similar-work examples are bounded, relevant, and include deterministic similarity reasons."
  - "Existing command recommendations remain unchanged while stack recommendations are exposed alongside them."

files_modified: []
---
