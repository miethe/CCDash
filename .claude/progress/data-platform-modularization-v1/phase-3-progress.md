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
commit_refs: ["49acb10", "91934ed", "fe23fc1", "d472718", "79638df"]
pr_refs: []

overall_progress: 95
completion_estimate: "implementation landed; broader phase-close validation and push bookkeeping still remain"

total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 1

owners: ["data-layer-expert", "backend-architect"]
contributors: ["codex"]

tasks:
  - id: "DPM-201"
    description: "Audit current tables and repositories, then classify them by domain, canonical owner, and profile-specific behavior."
    status: "completed"
    assigned_to: ["data-layer-expert"]
    dependencies: ["DPM-003"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "DPM-202"
    description: "Define how Postgres schemas or table groups separate identity/access, canonical app data, integration snapshots, operational state, and audit records; document the SQLite-local equivalent where physical separation is limited."
    status: "completed"
    assigned_to: ["data-layer-expert", "backend-architect"]
    dependencies: ["DPM-201"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "DPM-203"
    description: "Update repository/module ownership so domain responsibilities are explicit and future auth/session work does not land in cache-only abstractions."
    status: "completed"
    assigned_to: ["backend-architect"]
    dependencies: ["DPM-202"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["DPM-201"]
  batch_2: ["DPM-202"]
  batch_3: ["DPM-203"]
  critical_path: ["DPM-201", "DPM-202", "DPM-203"]
  estimated_total_time: "10pt / 4-5 days"

blockers:
  - "Phase closure is still withheld until broader validation and push requirements are satisfied."

success_criteria:
  - "Every persisted concern has a domain owner and target store."
  - "Postgres isolation strategy is explicit for dedicated and shared-instance deployments."
  - "Repository ownership no longer assumes one undifferentiated persistence layer."

files_modified:
  - ".claude/progress/data-platform-modularization-v1/phase-3-progress.md"
  - "backend/data_domain_layout.py"
  - "backend/application/ports/__init__.py"
  - "backend/application/ports/core.py"
  - "backend/adapters/storage/base.py"
  - "backend/adapters/storage/local.py"
  - "backend/adapters/storage/enterprise.py"
  - "backend/db/factory.py"
  - "backend/db/repositories/__init__.py"
  - "backend/db/repositories/entity_graph.py"
  - "backend/db/repositories/runtime_state.py"
  - "backend/db/repositories/links.py"
  - "backend/db/repositories/postgres/entity_graph.py"
  - "backend/db/repositories/postgres/runtime_state.py"
  - "backend/db/repositories/postgres/links.py"
  - "docs/guides/data-domain-ownership-matrix.md"
  - "backend/tests/test_storage_adapter_composition.py"
  - "backend/tests/test_data_domain_layout.py"
  - "backend/tests/test_runtime_bootstrap.py"
  - "backend/tests/test_request_context.py"
  - "backend/tests/test_data_domain_ownership.py"
  - "backend/tests/test_session_messages_groundwork.py"
  - "docs/guides/data-domain-schema-layout.md"
  - "docs/guides/storage-profiles-guide.md"
---

# data-platform-modularization-v1 - Phase 3

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/data-platform-modularization-v1/phase-3-progress.md -t DPM-20X -s completed
```

## Objective

Classify the current persistence surface by domain, codify the schema-boundary layout for local and enterprise storage, and expose additive domain-grouped storage seams so future auth and canonical session work can build on explicit ownership instead of a broad cache layer.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("data-layer-expert", "Execute DPM-201: audit current tables and repositories against the approved domain matrix")

# Batch 2 (after DPM-201)
Task("data-layer-expert", "Execute DPM-202: codify schema boundary layout for Postgres and SQLite-local equivalents")

# Batch 3 (after DPM-202)
Task("backend-architect", "Execute DPM-203: expose additive domain-grouped storage seams and make repository ownership explicit")
```

## Completion Notes

- Added `backend/data_domain_layout.py` as the code-owned source of truth for schema boundaries and repository ownership.
- Added `docs/guides/data-domain-schema-layout.md` so the Postgres schema posture and SQLite-local equivalents are explicit for follow-on implementation work.
- Extended `StorageUnitOfWork` with additive domain-grouped views for workspace metadata, observed product data, ingestion state, integration snapshots, and operational state while preserving the existing entity-level accessors.
- Split the mixed link/state repository modules into domain-oriented `entity_graph` and `runtime_state` modules for both SQLite and Postgres, while leaving compatibility exports in the old module paths.
- Exported the grouped storage protocols from `backend/application/ports/__init__.py` and added focused tests to verify schema-boundary coverage, repository ownership mapping, and the grouped storage seam on both local and enterprise adapters.

## Validation Notes

- `backend/.venv/bin/python -m pytest backend/tests/test_data_domain_layout.py backend/tests/test_data_domain_ownership.py backend/tests/test_runtime_bootstrap.py backend/tests/test_request_context.py backend/tests/test_storage_adapter_composition.py -q` -> `48 passed`
- `backend/.venv/bin/python -m pytest backend/tests/test_session_messages_groundwork.py -q` -> `12 passed`
