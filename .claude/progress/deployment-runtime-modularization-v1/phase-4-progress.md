---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 4
title: Packaging and Configuration Contracts
status: in_progress
started: '2026-04-18'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 50
completion_estimate: "in progress; env contract guardrails are landed and process-manager examples now match the split runtime topology, but container-first packaging artifacts remain incomplete"
total_tasks: 4
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 1
owners:
- DevOps
- backend-architect
- frontend-developer
- documentation-writer
contributors:
- codex
tasks:
- id: PKG-301
  description: Define shared, API-only, worker-only, and local-only environment/secrets
    contracts and add validation that prevents local defaults from leaking into hosted
    mode.
  status: completed
  assigned_to:
  - backend-architect
  - DevOps
  dependencies:
  - OPS-204
  estimated_effort: 3pt
  priority: high
- id: PKG-302
  description: Add container-first build artifacts for API, worker, and frontend plus
    a hosted smoke-stack composition artifact.
  status: pending
  assigned_to:
  - DevOps
  - frontend-developer
  dependencies:
  - PKG-301
  estimated_effort: 4pt
  priority: high
- id: PKG-303
  description: Document and ship example systemd and supervisor launch definitions
    equivalent to the split API, worker, and frontend topology.
  status: completed
  assigned_to:
  - DevOps
  dependencies:
  - PKG-301
  estimated_effort: 1pt
  priority: medium
- id: PKG-304
  description: Make the frontend static-build and serving contract explicit so frontend
    deployment stays decoupled from backend runtime assumptions.
  status: pending
  assigned_to:
  - frontend-developer
  - documentation-writer
  dependencies:
  - PKG-302
  estimated_effort: 2pt
  priority: medium
parallelization:
  batch_1:
  - PKG-301
  batch_2:
  - PKG-302
  - PKG-303
  batch_3:
  - PKG-304
  critical_path:
  - PKG-301
  - PKG-302
  - PKG-304
  estimated_total_time: 10pt / 4-5 days
blockers: []
success_criteria:
- Hosted env contracts are explicit and fail early when required inputs are missing.
- Process-manager examples describe the same frontend, API, and worker split as the
  hosted runtime contract.
- Operator docs point at shipped examples without implying container orchestration
  artifacts that are not yet in the repo.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-4-progress.md
- docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
- docs/setup-user-guide.md
- docs/guides/enterprise-session-intelligence-runbook.md
- deploy/runtime/README.md
- deploy/runtime/systemd/ccdash-api.service
- deploy/runtime/systemd/ccdash-worker.service
- deploy/runtime/systemd/ccdash-frontend.service
- deploy/runtime/supervisor/ccdash.conf
progress: 50
updated: '2026-04-18'
---

# deployment-runtime-modularization-v1 - Phase 4

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-4-progress.md --task PKG-303 --status completed
```

## Objective

Ship operator-facing packaging guidance that matches the hosted runtime contract, with explicit env boundaries and non-container launch examples for the same frontend, API, and worker split.

## Packaging Contract Snapshot

| Concern | Current state | Notes |
| --- | --- | --- |
| Env contract split | landed | Hosted guardrails already fail fast for invalid storage, missing API bearer token, missing worker binding, and telemetry exporter requirements. |
| Process-manager equivalents | landed | Repo now ships `deploy/runtime/systemd` and `deploy/runtime/supervisor` examples for API, worker, and frontend. |
| Container-first artifacts | pending | The examples intentionally mirror the split topology but do not claim container images or compose bundles exist in `deploy/runtime` yet. |
| Frontend serving boundary | pending | Docs now call out the current `vite preview` helper as an operator example, not a hardened edge-serving story. |

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute PKG-301: lock the shared/api/worker/local env contract and hosted fail-fast rules")

# Batch 2 (after PKG-301)
Task("DevOps", "Execute PKG-302: add container-first API, worker, and frontend packaging artifacts")
Task("DevOps", "Execute PKG-303: ship process-manager examples that mirror the split runtime topology")

# Batch 3 (after PKG-302)
Task("frontend-developer", "Execute PKG-304: make the frontend serving boundary explicit and decoupled from backend runtime assumptions")
```

## Completion Notes

- Added `deploy/runtime/README.md` as the operator entrypoint for the split topology, env ownership, probe surfaces, and example process-manager usage.
- Added systemd unit examples for `backend.runtime.bootstrap_api:app`, `python -m backend.worker`, and the current frontend preview helper.
- Added a supervisor example that keeps the same API/worker/frontend separation without implying new queueing or orchestration behavior.
- Updated operator docs so they reference the shipped examples and describe the current frontend helper as repo-aligned rather than production-edge hardening.
