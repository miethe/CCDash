---
type: progress
schema_version: 2
doc_type: progress
prd: "session-intelligence-canonical-storage-v1"
feature_slug: "session-intelligence-canonical-storage-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md
phase: 1
title: "Canonical Transcript Contract Hardening"
status: "in_progress"
started: "2026-04-02"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 10
completion_estimate: "contract audit complete; compatibility and provenance hardening in progress"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "data-layer-expert", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "SICS-001"
    description: "Freeze the canonical transcript identity, lineage, provenance, and fallback contract for session_messages."
    status: "in_progress"
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-002"
    description: "Codify the compatibility projection from canonical transcript rows back into the current session detail DTO/log payload shape."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SICS-001"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-003"
    description: "Normalize parser-to-canonical provenance, role/type, tool metadata, and lineage behavior before transcript persistence."
    status: "pending"
    assigned_to: ["python-backend-engineer", "data-layer-expert"]
    dependencies: ["SICS-001"]
    estimated_effort: "4pt"
    priority: "high"

parallelization:
  batch_1: ["SICS-001"]
  batch_2: ["SICS-002", "SICS-003"]
  critical_path: ["SICS-001", "SICS-002", "SICS-003"]
  estimated_total_time: "10pt / 4-5 days"

blockers: []

success_criteria:
  - "Canonical transcript identity, lineage, provenance, and fallback semantics are explicit and testable."
  - "Canonical transcript rows can reproduce the current session detail log payload without consumer-visible regressions."
  - "Supported platforms persist a consistent transcript contract for provenance, roles, types, tool metadata, and lineage."

files_modified:
  - ".claude/progress/session-intelligence-canonical-storage-v1/phase-1-progress.md"
  - "docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md"

updated: "2026-04-02"
---

# session-intelligence-canonical-storage-v1 - Phase 1

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/session-intelligence-canonical-storage-v1/phase-1-progress.md -t SICS-00X -s completed
```

## Objective

Freeze the canonical transcript contract before enterprise canonicalization, derived intelligence facts, or read-path cutovers rely on it.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute SICS-001: Freeze canonical transcript identity, provenance, lineage, and fallback semantics")

# Batch 2 (after SICS-001)
Task("python-backend-engineer", "Execute SICS-002: Codify canonical-to-session-detail compatibility projection rules")
Task("python-backend-engineer", "Execute SICS-003: Normalize parser-to-canonical provenance, role/type, tool metadata, and lineage behavior")
```
