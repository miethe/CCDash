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
commit_refs: ["e97f277"]
pr_refs: []

overall_progress: 90
completion_estimate: "implementation landed; waiting on unrelated repo-wide typecheck cleanup before phase closure"

total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 1

owners: ["backend-architect", "data-layer-expert"]
contributors: ["codex"]

tasks:
  - id: "DPM-001"
    description: "Define a concrete capability matrix for local, enterprise, and shared-enterprise modes covering canonical stores, ingestion sources, supported isolation modes, and required guarantees."
    status: "completed"
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "DPM-002"
    description: "Define which runtime profiles may pair with which storage profiles and what each pairing implies for sync, jobs, auth, and integrations."
    status: "completed"
    assigned_to: ["backend-architect"]
    dependencies: ["DPM-001"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "DPM-003"
    description: "Freeze the domain classification for existing persisted concerns, including current tables and future auth/audit records."
    status: "completed"
    assigned_to: ["data-layer-expert"]
    dependencies: ["DPM-001"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["DPM-001"]
  batch_2: ["DPM-002", "DPM-003"]
  critical_path: ["DPM-001", "DPM-002", "DPM-003"]
  estimated_total_time: "8pt / 3-4 days"

blockers:
  - "Repo-wide `pnpm typecheck` still fails outside the Phase 1 write set (`components/SessionInspector.tsx`, `lib/sessionTranscriptLive.ts`, and multiple `examples/skillmeat/ui` test files)."

success_criteria:
  - "Storage profiles are defined by capability and ownership, not by environment variables alone."
  - "Runtime/storage combinations are explicit enough for bootstrap validation and docs."
  - "Canonical versus derived domains are stable enough that downstream schema work does not reopen the model."

files_modified:
  - "docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md"
  - ".claude/progress/data-platform-modularization-v1/phase-1-progress.md"
  - "backend/config.py"
  - "backend/runtime/bootstrap.py"
  - "backend/runtime/container.py"
  - "backend/data_domains.py"
  - "backend/tests/test_runtime_bootstrap.py"
  - "backend/tests/test_storage_profiles.py"
  - "backend/tests/test_data_domain_ownership.py"
  - "docs/guides/storage-profiles-guide.md"
  - "docs/guides/data-domain-ownership-matrix.md"
  - "docs/ops-panel-developer-reference.md"
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

## Completion Notes

- Centralized stricter storage-profile validation in `backend/config.py`, including explicit local-vs-enterprise backend checks and isolation-mode enforcement.
- Expanded runtime health reporting in `backend/runtime/container.py` and `backend/runtime/bootstrap.py` so `/api/health` exposes the Phase 1 storage contract surface.
- Added a code-owned domain ownership matrix in `backend/data_domains.py` plus docs in `docs/guides/data-domain-ownership-matrix.md`.
- Extended backend coverage with storage-profile, runtime bootstrap, and data-domain ownership tests.

## Validation Notes

- `PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/test_storage_profiles.py backend/tests/test_runtime_bootstrap.py backend/tests/test_data_domain_ownership.py -q` -> `26 passed`
- `pnpm typecheck` remains red due to pre-existing repo issues outside this phase's files.
