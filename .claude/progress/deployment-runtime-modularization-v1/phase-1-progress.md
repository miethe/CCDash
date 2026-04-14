---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 1
title: Runtime Contract and Launch Surface
status: completed
started: '2026-04-14'
completed: '2026-04-14'
commit_refs: ["5496546", "9554151", "7b866bb"]
pr_refs: []
overall_progress: 100
completion_estimate: "completed; Phase 1 runtime contract, launcher, and boot-time guardrail work is fully landed"
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- documentation-writer
contributors:
- codex
tasks:
- id: RUN-001
  description: Freeze the canonical entrypoint for each runtime and align docs, package
    scripts, and tests around those names.
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 2pt
  priority: high
- id: RUN-002
  description: Update `scripts/backend.mjs`, package scripts, and related launch
    helpers so hosted startup resolves to `backend.runtime.bootstrap_api:app` while
    `backend.main:app` stays local-only.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - RUN-001
  estimated_effort: 4pt
  priority: high
- id: RUN-003
  description: Add startup validation that rejects invalid runtime/storage/auth combinations
    and surfaces runtime metadata consistently at boot.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - RUN-001
  estimated_effort: 2pt
  priority: high
parallelization:
  batch_1:
  - RUN-001
  batch_2:
  - RUN-002
  - RUN-003
  critical_path:
  - RUN-001
  - RUN-002
  - RUN-003
  estimated_total_time: 8pt / 3-4 days
blockers: []
success_criteria:
- Local, api, worker, and test each have one explicit bootstrap path with no ambiguous
  hosted default.
- Hosted startup resolves to `backend.runtime.bootstrap_api:app` and never falls
  back to the local profile.
- Invalid runtime, storage, and auth pairings fail fast while runtime metadata is
  visible in startup logs.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-1-progress.md
- backend/config.py
- backend/runtime/bootstrap.py
- backend/runtime/container.py
- backend/runtime_ports.py
- backend/tests/test_runtime_bootstrap.py
- docs/guides/enterprise-session-intelligence-runbook.md
- docs/project_plans/designs/ccdash-runtime-port-adapter-map-v1.md
- docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
- docs/setup-user-guide.md
- package.json
- scripts/backend.mjs
- scripts/dev.mjs
progress: 100
updated: '2026-04-14'
---

# deployment-runtime-modularization-v1 - Phase 1

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-1-progress.md --task RUN-001 --status completed
```

## Objective

Make runtime selection explicit and remove hosted entrypoint ambiguity.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute RUN-001: freeze the canonical entrypoint matrix and align docs, scripts, and tests")

# Batch 2 (after RUN-001)
Task("python-backend-engineer", "Execute RUN-002: route hosted startup to backend.runtime.bootstrap_api:app and keep backend.main:app local-only")
Task("backend-architect", "Execute RUN-003: add startup validation for runtime, storage, and auth combinations plus boot-time metadata")
```
