---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-hexagonal-foundation-v1"
feature_slug: "ccdash-hexagonal-foundation-v1"
prd_ref: /docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md
phase: 2
title: "Request Context and Core Ports"
status: "in-progress"
started: "2026-03-13"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "4 days"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "PORT-001"
    description: "Add a request context object carrying principal, workspace scope, project scope, runtime profile, and tracing metadata."
    status: "in_progress"
    assigned_to: ["backend-architect"]
    dependencies: ["ARC-003"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "PORT-002"
    description: "Define framework-agnostic ports for IdentityProvider, AuthorizationPolicy, WorkspaceRegistry, StorageUnitOfWork, JobScheduler, and IntegrationClient."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["PORT-001"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "PORT-003"
    description: "Add local/default adapters for no-auth identity, permissive authorization, project/workspace resolution, and in-process jobs."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["PORT-002"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["PORT-001"]
  batch_2: ["PORT-002"]
  batch_3: ["PORT-003"]
  critical_path: ["PORT-001", "PORT-002", "PORT-003"]
  estimated_total_time: "9pt / 4 days"

blockers: []

success_criteria:
  - "Request handlers can resolve a typed request context even in local no-auth mode."
  - "Core ports are framework-agnostic, live outside adapter code, and are importable by services."
  - "Local runtime behavior remains functional through the new local adapter baselines."

files_modified:
  - ".claude/progress/ccdash-hexagonal-foundation-v1/phase-2-progress.md"
---
