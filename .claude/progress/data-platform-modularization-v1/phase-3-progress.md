---
type: progress
schema_version: 2
doc_type: progress
prd: "data-platform-modularization-v1"
feature_slug: "data-platform-modularization-v1"
prd_ref: /docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md
phase: 3
title: "Domain Ownership and Schema Layout"
status: "in_progress"
started: "2026-03-30"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 15
completion_estimate: "Phase tracker initialized; schema/repository ownership contract is landing first"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["data-layer-expert", "backend-architect"]
contributors: ["codex"]

tasks:
  - id: "DPM-201"
    description: "Audit current tables and repositories, then classify them by domain, canonical owner, and profile-specific behavior."
    status: "in_progress"
    assigned_to: ["data-layer-expert"]
    dependencies: ["DPM-003"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "DPM-202"
    description: "Define how Postgres schemas or table groups separate identity/access, canonical app data, integration snapshots, operational state, and audit records; document the SQLite-local equivalent where physical separation is limited."
    status: "pending"
    assigned_to: ["data-layer-expert", "backend-architect"]
    dependencies: ["DPM-201"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "DPM-203"
    description: "Update repository/module ownership so domain responsibilities are explicit and future auth/session work does not land in cache-only abstractions."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["DPM-202"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["DPM-201"]
  batch_2: ["DPM-202", "DPM-203"]
  critical_path: ["DPM-201", "DPM-202", "DPM-203"]
  estimated_total_time: "10pt / 4-5 days"

blockers: []

success_criteria:
  - "Every persisted concern has a domain owner and target store."
  - "Postgres isolation strategy is explicit for dedicated and shared-instance deployments."
  - "Repository ownership no longer assumes one undifferentiated persistence layer."

files_modified:
  - ".claude/progress/data-platform-modularization-v1/phase-3-progress.md"
---

# data-platform-modularization-v1 - Phase 3

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/data-platform-modularization-v1/phase-3-progress.md -t DPM-20X -s completed
```

## Objective

Make the domain-to-schema and repository ownership model explicit enough that Phase 4 auth/audit storage and future canonical session work do not reopen the storage boundary decisions.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("data-layer-expert", "Execute DPM-201: audit current tables and repositories against the approved domain matrix")

# Batch 2 (after DPM-201)
Task("data-layer-expert", "Execute DPM-202: codify Postgres schema groups and the SQLite-local equivalent")
Task("backend-architect", "Execute DPM-203: realign repository ownership so domain boundaries are explicit in modules and docs")
```
