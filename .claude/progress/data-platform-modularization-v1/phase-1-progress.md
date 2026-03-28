---
type: progress
schema_version: 2
doc_type: progress
prd: "data-platform-modularization-v1"
feature_slug: "data-platform-modularization-v1"
prd_ref: /docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md
phase: 1
title: "Storage Profile Capability Contract"
status: "in_progress"
started: "2026-03-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "data-layer-expert"]
contributors: ["codex"]

tasks:
  - id: "DPM-001"
    description: "Define a concrete capability matrix for local, enterprise, and shared-enterprise modes covering canonical stores, ingestion sources, supported isolation modes, and required guarantees."
    status: "pending"
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "DPM-002"
    description: "Define which runtime profiles may pair with which storage profiles and what each pairing implies for sync, jobs, auth, and integrations."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["DPM-001"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "DPM-003"
    description: "Freeze the domain classification for existing persisted concerns, including current tables and future auth/audit records."
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["DPM-001"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["DPM-001"]
  batch_2: ["DPM-002", "DPM-003"]
  critical_path: ["DPM-001", "DPM-002", "DPM-003"]
  estimated_total_time: "8pt / 3-4 days"

blockers: []

success_criteria:
  - "Storage profiles are defined by capability and ownership, not by environment variables alone."
  - "Runtime/storage combinations are explicit enough for bootstrap validation and docs."
  - "Canonical versus derived domains are stable enough that downstream schema work does not reopen the model."

files_modified:
  - "docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md"
  - ".claude/progress/data-platform-modularization-v1/phase-1-progress.md"
---

# data-platform-modularization-v1 - Phase 1

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/data-platform-modularization-v1/phase-1-progress.md -t DPM-00X -s completed
```

## Objective

Freeze the storage-profile capability contract, runtime/storage pairing rules, and domain ownership boundaries that Phase 2 and later phases depend on.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute DPM-001: Define the capability matrix for local, enterprise, and shared-enterprise storage modes")

# Batch 2 (after DPM-001)
Task("backend-architect", "Execute DPM-002: Define runtime-to-storage pairing rules and implications")
Task("data-layer-expert", "Execute DPM-003: Freeze the domain classification for persisted concerns")
```

## Implementation Notes

_To be filled during implementation._

## Completion Notes

_To be filled when phase completes._
