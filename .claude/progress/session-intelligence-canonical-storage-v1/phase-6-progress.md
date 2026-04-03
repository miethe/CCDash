---
type: progress
schema_version: 2
doc_type: progress
prd: "session-intelligence-canonical-storage-v1"
feature_slug: "session-intelligence-canonical-storage-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md
phase: 6
title: "SkillMeat Memory Draft Loop"
status: "in_progress"
started: "2026-04-03"
completed: ""
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "3-4 days"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer", "frontend-developer"]
contributors: ["codex"]

tasks:
  - id: "SICS-501"
    description: "Define the CCDash-side memory draft record, extraction evidence, review status, and linkage back to sessions/features/workflows."
    status: "in_progress"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["SICS-201", "SICS-202", "SICS-203"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-502"
    description: "Build the worker logic that selects successful sessions and drafts candidate SkillMeat context modules or guideline snippets."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SICS-501"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-503"
    description: "Add operator review and approval before calling the SkillMeat write API for accepted draft artifacts."
    status: "pending"
    assigned_to: ["frontend-developer", "python-backend-engineer"]
    dependencies: ["SICS-502"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["SICS-501"]
  batch_2: ["SICS-502"]
  batch_3: ["SICS-503"]
  critical_path: ["SICS-501", "SICS-502", "SICS-503"]
  estimated_total_time: "8pt / 3-4 days"

blockers: []

success_criteria:
  - "Memory drafts are stored as reviewable CCDash artifacts with source evidence and publish status."
  - "Draft generation is deterministic and retry-safe for successful sessions."
  - "Publishing to SkillMeat remains opt-in, auditable, and failure-tolerant."

files_modified:
  - ".claude/progress/session-intelligence-canonical-storage-v1/phase-6-progress.md"

updated: "2026-04-03"
---

# session-intelligence-canonical-storage-v1 - Phase 6

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/session-intelligence-canonical-storage-v1/phase-6-progress.md -t SICS-50X -s completed
```

## Objective

Draft reviewable SkillMeat memory candidates from successful sessions and require explicit approval before publish.

## Execution Notes

1. Reuse existing session-intelligence derivation seams for candidate evidence instead of introducing a second transcript parser path.
2. Keep draft persistence profile-aware and storage-backed in both SQLite and Postgres so local review remains possible even when publish is unsupported.
3. Reuse the existing SkillMeat integration and approval-flow conventions for API wiring, auditability, and operator UX.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("python-backend-engineer", "Execute SICS-501: add memory-draft persistence model, repository methods, DTOs, and read APIs grounded in current session-intelligence patterns")

# Batch 2
Task("python-backend-engineer", "Execute SICS-502: implement deterministic draft extraction and worker scheduling for successful sessions")

# Batch 3
Task("frontend-developer", "Execute SICS-503: add review and approval UI for memory drafts using the backend publish contract")
Task("python-backend-engineer", "Execute SICS-503: add approval-gated SkillMeat publish endpoints, audit state transitions, and failure handling")
```
