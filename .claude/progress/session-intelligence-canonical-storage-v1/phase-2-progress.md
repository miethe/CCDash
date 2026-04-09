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
status: "completed"
started: "2026-04-02"
completed: "2026-04-02"
commit_refs: ["bf4d5f5", "896af79", "c7fd361"]
pr_refs: []

overall_progress: 100
completion_estimate: "completed"

total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["data-layer-expert", "backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "SICS-101"
    description: "Update enterprise ingest so Postgres session_messages is the authoritative transcript target rather than a mirrored compatibility store."
    status: "completed"
    assigned_to: ["data-layer-expert", "python-backend-engineer"]
    dependencies: ["SICS-003"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "SICS-102"
    description: "Define the transcript block strategy for embeddings, including block unit, dedupe, and refresh rules."
    status: "completed"
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: ["SICS-001"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "SICS-103"
    description: "Add enterprise-only migration support for pgvector, session_embeddings, and related indexes/capability checks while keeping local mode unaffected."
    status: "completed"
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

files_modified:
  - ".claude/progress/session-intelligence-canonical-storage-v1/phase-2-progress.md"
  - "docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md"
  - "docs/guides/session-transcript-contract-guide.md"
  - "backend/db/sync_engine.py"
  - "backend/application/ports/core.py"
  - "backend/adapters/storage/base.py"
  - "backend/adapters/storage/local.py"
  - "backend/adapters/storage/enterprise.py"
  - "backend/db/factory.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/migration_governance.py"
  - "backend/data_domains.py"
  - "backend/data_domain_layout.py"
  - "backend/runtime/bootstrap.py"
  - "backend/runtime/container.py"
  - "backend/db/repositories/session_embeddings.py"
  - "backend/db/repositories/postgres/session_embeddings.py"
  - "backend/tests/test_session_messages_groundwork.py"
  - "backend/tests/test_sync_engine_transcript_canonicalization.py"
  - "backend/tests/test_migration_governance.py"
  - "backend/tests/test_runtime_bootstrap.py"
  - "backend/tests/test_storage_adapter_composition.py"
  - "backend/tests/test_data_domain_ownership.py"

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

## Completion Notes

- Documented the Phase 2 mixed block strategy as per-message blocks plus 5-row sliding windows, with content-addressed dedupe and additive refresh rules.
- Updated enterprise sync so canonical `session_messages` rows become the primary transcript persistence path, while legacy `session_logs` remain fallback-only when canonical projection is unavailable.
- Added an enterprise-only `pgvector` substrate with `app.session_embeddings`, storage capability seams, runtime health fields, and governance/ownership rules that explicitly permit the new observed-entity concern without requiring SQLite parity.

## Validation Notes

- `backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py backend/tests/test_runtime_bootstrap.py backend/tests/test_storage_adapter_composition.py backend/tests/test_data_domain_ownership.py backend/tests/test_session_messages_groundwork.py backend/tests/test_sync_engine_transcript_canonicalization.py -q` -> `66 passed`
- `backend/.venv/bin/python -m py_compile backend/runtime/bootstrap.py backend/db/postgres_migrations.py backend/db/migration_governance.py backend/runtime/container.py backend/application/ports/core.py backend/adapters/storage/base.py backend/adapters/storage/local.py backend/adapters/storage/enterprise.py backend/db/factory.py backend/data_domains.py backend/data_domain_layout.py backend/db/repositories/session_embeddings.py backend/db/repositories/postgres/session_embeddings.py` -> `passed`
