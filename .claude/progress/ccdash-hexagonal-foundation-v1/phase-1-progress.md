---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-hexagonal-foundation-v1"
feature_slug: "ccdash-hexagonal-foundation-v1"
prd_ref: /docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md
phase: 1
title: "Runtime Composition Spine"
status: "in_progress"
started: "2026-03-12"
completed:
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "4-5 days"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "ARC-001"
    description: "Define local, api, worker, and test runtime profiles with capability flags for watch, sync, jobs, auth, and integrations."
    status: "in_progress"
    assigned_to: ["backend-architect"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "ARC-002"
    description: "Add a composition container/bootstrap layer that wires repositories, services, adapters, and observability once per runtime."
    status: "pending"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["ARC-001"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "ARC-003"
    description: "Split API startup, local convenience boot, and test boot paths so future worker startup does not depend on API lifespan."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ARC-002"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["ARC-001"]
  batch_2: ["ARC-002"]
  batch_3: ["ARC-003"]
  critical_path: ["ARC-001", "ARC-002", "ARC-003"]
  estimated_total_time: "10pt / 4-5 days"

blockers: []

success_criteria:
  - "Runtime profile contract exists and can be selected without importing concrete adapters into routers."
  - "backend/main.py no longer owns direct adapter selection logic; runtime bootstrap code exists."
  - "API startup path can run without mandatory watcher or sync startup, and tests can boot a stripped profile."

files_modified:
  - "docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md"
  - ".claude/progress/ccdash-hexagonal-foundation-v1/phase-1-progress.md"
---

# ccdash-hexagonal-foundation-v1 - Phase 1

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-hexagonal-foundation-v1/phase-1-progress.md -t ARC-001 -s completed
```
