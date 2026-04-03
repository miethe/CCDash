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
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "3-4 days"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "python-backend-engineer", "frontend-developer"]
contributors: ["codex"]

tasks:
  - id: "SICS-501"
    description: "Define the CCDash-side draft record, extraction evidence, review status, and linkage back to sessions/features/workflows."
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
    priority: "medium"

parallelization:
  batch_1: ["SICS-501"]
  batch_2: ["SICS-502"]
  batch_3: ["SICS-503"]
  critical_path: ["SICS-501", "SICS-502", "SICS-503"]
  estimated_total_time: "8pt / 3-4 days"

blockers: []

success_criteria:
  - "Memory drafts are stored as reviewable CCDash artifacts with deterministic evidence."
  - "Draft generation is deduplicated, rate-limited, and safe to retry."
  - "Publishing to SkillMeat requires explicit approval and records audit details."

files_modified:
  - ".claude/progress/session-intelligence-canonical-storage-v1/phase-6-progress.md"

updated: "2026-04-03"
---

# session-intelligence-canonical-storage-v1 - Phase 6

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/session-intelligence-canonical-storage-v1/phase-6-progress.md -t SICS-50X -s in_progress
```

## Objective

Turn successful session-intelligence evidence into reviewable SkillMeat memory drafts, then require explicit operator approval before any publish call leaves CCDash.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute SICS-501: Define the persisted session memory draft model, evidence contract, and review states")

# Batch 2
Task("python-backend-engineer", "Execute SICS-502: Add deterministic draft extraction and retry-safe worker generation")

# Batch 3
Task("frontend-developer", "Execute SICS-503: Add operator review and approval UX for SkillMeat memory draft publishing")
Task("python-backend-engineer", "Execute SICS-503: Wire approval-gated SkillMeat publish APIs with auditability and error handling")
```
