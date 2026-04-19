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
status: completed
started: '2026-04-18'
completed: '2026-04-18'
commit_refs:
- "4c64bff"
- "80f3dfc"
- "20887a8"
pr_refs: []
overall_progress: 100
completion_estimate: "completed; env contracts, hosted packaging artifacts, process-manager equivalents, and frontend serving boundaries are fully landed"
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
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
  status: completed
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
  status: completed
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
- Hosted packaging artifacts are separately buildable for API, worker, and frontend,
  with a repo-shipped hosted compose example for smoke validation.
- Process-manager examples describe the same frontend, API, and worker split as the
  hosted runtime contract.
- Frontend deployment targets hosted API URLs without depending on bundled backend
  startup behavior.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-4-progress.md
- docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
- docs/setup-user-guide.md
- docs/guides/enterprise-session-intelligence-runbook.md
- .env.example
- backend/config.py
- backend/runtime/bootstrap.py
- backend/runtime/container.py
- backend/tests/test_runtime_bootstrap.py
- backend/tests/test_storage_profiles.py
- deploy/runtime/README.md
- deploy/runtime/api/Dockerfile
- deploy/runtime/worker/Dockerfile
- deploy/runtime/frontend/Dockerfile
- deploy/runtime/frontend/default.conf.template
- deploy/runtime/compose.hosted.env.example
- deploy/runtime/compose.hosted.yml
- deploy/runtime/systemd/ccdash-api.service
- deploy/runtime/systemd/ccdash-worker.service
- deploy/runtime/systemd/ccdash-frontend.service
- deploy/runtime/supervisor/ccdash.conf
- package.json
- vite.config.ts
- services/apiClient.ts
- services/runtimeBase.ts
- services/live/client.ts
- services/live/connectionManager.ts
- services/__tests__/runtimeBase.test.ts
- services/__tests__/liveConnectionManager.test.ts
progress: 100
updated: '2026-04-18'
---

# deployment-runtime-modularization-v1 - Phase 4

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-4-progress.md --task PKG-303 --status completed
```

## Objective

Close the Phase 4 packaging contract by shipping explicit hosted env validation, container-first API/worker/frontend artifacts, process-manager equivalents, and a frontend serving boundary that matches the split runtime topology.

## Packaging Contract Snapshot

| Concern | Current state | Notes |
| --- | --- | --- |
| Env contract split | landed | Hosted guardrails now fail fast for invalid storage, missing API bearer token, missing worker binding, and missing telemetry exporter requirements. |
| Process-manager equivalents | landed | Repo ships `deploy/runtime/systemd` and `deploy/runtime/supervisor` examples for API, worker, and frontend. |
| Container-first artifacts | landed | Repo ships API, worker, and frontend Dockerfiles plus `deploy/runtime/compose.hosted.yml` and an example env file for smoke validation. |
| Frontend serving boundary | landed | Frontend runtime base URL/build behavior is explicit in the repo and deployment docs instead of being implied by bundled backend startup. |

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

- Added hosted runtime packaging artifacts for API, worker, and frontend under `deploy/runtime/`, including Dockerfiles, a hosted compose example, and an example env contract file for split-stack smoke validation.
- Landed backend env-contract validation for hosted mode so enterprise storage, API bearer auth, worker binding, and telemetry exporter requirements fail fast instead of falling back to local-friendly defaults.
- Shipped systemd and supervisor examples that use the same `backend.runtime.bootstrap_api:app`, `python -m backend.worker`, and frontend process separation as the container topology.
- Made the frontend serving boundary explicit in repo code and docs so hosted frontend builds target the API base/runtime contract directly rather than assuming bundled backend startup behavior.
