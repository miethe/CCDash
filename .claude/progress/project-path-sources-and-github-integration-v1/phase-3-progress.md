---
type: progress
schema_version: 2
doc_type: progress
prd: "project-path-sources-and-github-integration-v1"
feature_slug: "project-path-sources-and-github-integration-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 3
title: "Integration settings and credentials"
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

owners: ["backend-architect", "integrations", "security-engineering"]
contributors: ["codex"]

tasks:
  - id: "PPG-11"
    description: "Add persistence for GitHub integration settings outside project records."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["PPG-4", "PPG-8"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "PPG-12"
    description: "Add GitHub settings, credential validation, path validation, workspace refresh, and write-capability endpoints."
    status: "pending"
    assigned_to: ["integrations", "python-backend-engineer"]
    dependencies: ["PPG-11", "PPG-10"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "PPG-13"
    description: "Refactor the integrations router so SkillMeat and GitHub are peers."
    status: "pending"
    assigned_to: ["integrations"]
    dependencies: ["PPG-12"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "PPG-14"
    description: "Mask GitHub secrets in API responses and logs."
    status: "pending"
    assigned_to: ["security-engineering"]
    dependencies: ["PPG-11", "PPG-12"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "PPG-15"
    description: "Define read-only vs write-enabled status in the GitHub settings contract."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["PPG-11"]
    estimated_effort: "1pt"
    priority: "medium"

parallelization:
  batch_1: ["PPG-11", "PPG-15"]
  batch_2: ["PPG-12"]
  batch_3: ["PPG-13", "PPG-14"]
  critical_path: ["PPG-11", "PPG-12", "PPG-13"]
  estimated_total_time: "8pt / ~3 days"

blockers: []

success_criteria:
  - "GitHub credentials save and validate without living in project records."
  - "The API verifies repo access and nested path validity for GitHub path references."
  - "SkillMeat endpoints continue to work after the router refactor."

files_modified: []
---

# project-path-sources-and-github-integration-v1 - Phase 3
