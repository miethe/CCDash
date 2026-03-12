---
type: progress
schema_version: 2
doc_type: progress
prd: "project-path-sources-and-github-integration-v1"
feature_slug: "project-path-sources-and-github-integration-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 2
title: "Path resolver and repo workspace backend"
status: "pending"
started: ""
completed: ""
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "pending"

total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "PPG-6"
    description: "Implement ProjectPathResolver and resolved-path bundle DTOs."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["PPG-5"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "PPG-7"
    description: "Implement filesystem and GitHub project-path providers."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["PPG-6"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "PPG-8"
    description: "Implement repo workspace cache lifecycle and stable local workspace creation."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["PPG-6"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "PPG-9"
    description: "Normalize GitHub URL input into structured repo refs."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["PPG-6"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "PPG-10"
    description: "Add explicit error categories for GitHub validation and workspace failures."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["PPG-7", "PPG-8", "PPG-9"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["PPG-6"]
  batch_2: ["PPG-7", "PPG-8", "PPG-9"]
  batch_3: ["PPG-10"]
  critical_path: ["PPG-6", "PPG-8", "PPG-10"]
  estimated_total_time: "9pt / ~4 days"

blockers: []

success_criteria:
  - "Resolver returns concrete local paths for project_root, filesystem, and github_repo sources."
  - "GitHub-backed roots resolve to stable local workspace paths."
  - "Distinct repos and branches coexist without path collisions."

files_modified: []
---

# project-path-sources-and-github-integration-v1 - Phase 2
