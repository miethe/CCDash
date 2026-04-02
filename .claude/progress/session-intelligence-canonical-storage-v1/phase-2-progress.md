---
type: progress
schema_version: 2
doc_type: progress
prd: "session-intelligence-canonical-storage-v1"
feature_slug: "session-intelligence-canonical-storage-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md
phase: 2
title: "Enterprise Transcript Canonicalization And Embeddings Substrate"
status: "in-progress"
started: "2026-04-02"
completed: ""
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "in-progress"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["data-layer-expert", "backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "SICS-101"
    description: "Update enterprise ingest so Postgres session_messages is the authoritative transcript target rather than a mirrored compatibility store."
    status: "pending"
    assigned_to: ["data-layer-expert", "python-backend-engineer"]
    dependencies: ["SICS-003"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "SICS-102"
    description: "Define the transcript block strategy for embeddings, including block unit, dedupe, and refresh rules."
    status: "pending"
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: ["SICS-001"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-103"
    description: "Add enterprise-only migration support for pgvector, session_embeddings, and related indexes/capability checks while keeping local mode unaffected."
    status: "pending"
    assigned_to: ["data-layer-expert"]
    dependencies: ["SICS-101", "SICS-102"]
    estimated_effort: "5pt"
    priority: "high"

parallelization:
  batch_1: ["SICS-101", "SICS-102"]
  batch_2: ["SICS-103"]
  critical_path: ["SICS-101", "SICS-102", "SICS-103"]
  estimated_total_time: "12pt / 1 week"

blockers: []

success_criteria:
  - "Enterprise transcript writes are canonical and backfillable."
  - "Embedding storage is additive, enterprise-scoped, content-addressed, and health-checkable."
  - "Local mode still runs without enterprise-only extension requirements."

files_modified: []

updated: "2026-04-02"
---

# session-intelligence-canonical-storage-v1 - Phase 2

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/session-intelligence-canonical-storage-v1/phase-2-progress.md -t SICS-10X -s completed
```

## Objective

Promote `session_messages` into the enterprise canonical transcript substrate and define the embedding block strategy that later search and intelligence work will consume.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("data-layer-expert", "Execute SICS-101: Make enterprise transcript writes canonical and backfillable")
Task("backend-architect", "Execute SICS-102: Define the transcript block strategy for embeddings and refresh rules")

# Batch 2 (after SICS-101 and SICS-102)
Task("data-layer-expert", "Execute SICS-103: Add enterprise-only pgvector and embedding storage substrate")
```

## Execution Notes

- SICS-101 should preserve local fallback behavior while making enterprise canonical rows the primary transcript target.
- SICS-102 should lock the embedding unit, dedupe rule, and refresh/reindex rule before any storage migration depends on them.
- SICS-103 should remain enterprise-scoped so local SQLite does not require `pgvector` or embedding tables.
