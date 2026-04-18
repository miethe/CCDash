---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 6
title: Validation, Documentation, and Rollout
status: in_progress
started: '2026-04-18'
commit_refs: []
pr_refs: []
overall_progress: 5
completion_estimate: "just started; runtime matrix validation and hosted smoke workflow are kicking off ahead of documentation and skill refresh work"
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 2
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- DevOps
- documentation-writer
- task-completion-validator
- skill-creator
contributors:
- codex
tasks:
- id: VAL-501
  description: Extend automated coverage for runtime entrypoints, invalid config cases,
    probe semantics, background-job ownership boundaries, and CLI/MCP lightweight
    bootstrap invariants.
  status: in_progress
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OBS-403
  estimated_effort: 3pt
  priority: high
- id: VAL-502
  description: Add a repeatable hosted smoke workflow covering API start, worker
    start, probe checks, migrations, one representative background job path, and
    representative CLI + MCP queries against the stabilized runtime contract.
  status: in_progress
  assigned_to:
  - DevOps
  - task-completion-validator
  dependencies:
  - PKG-302
  estimated_effort: 3pt
  priority: high
- id: VAL-503
  description: Update setup and runbook documentation with final commands, env tables,
    failure modes, local-versus-hosted migration guidance, and explicit CLI/MCP
    operator-surface posture.
  status: pending
  assigned_to:
  - documentation-writer
  dependencies:
  - VAL-502
  estimated_effort: 2pt
  priority: medium
- id: VAL-504
  description: Update the `ccdash` skill references, recipes, and transport guidance
    so it reflects the final deployment/runtime topology, probe semantics, and MCP-aware
    routing posture.
  status: pending
  assigned_to:
  - documentation-writer
  - skill-creator
  dependencies:
  - VAL-503
  estimated_effort: 2pt
  priority: medium
parallelization:
  batch_1:
  - VAL-501
  - VAL-502
  batch_2:
  - VAL-503
  batch_3:
  - VAL-504
  critical_path:
  - VAL-502
  - VAL-503
  - VAL-504
  estimated_total_time: 10pt / 4-5 days
blockers: []
success_criteria:
- Runtime matrix coverage passes in CI across `local`, `api`, `worker`, and `test`
  expectations, including key negative cases and CLI/MCP bootstrap invariants.
- Hosted smoke validation succeeds with split API and worker runtimes plus representative
  CLI and MCP queries against the shipped runtime contract.
- Operator documentation matches shipped entrypoints, launch artifacts, probes, failure
  modes, and supported query surfaces without overstating unshipped capabilities.
- The `ccdash` skill reflects the final runtime contract, probe semantics, and MCP-aware
  routing posture without stale deployment guidance.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-6-progress.md
progress: 5
updated: '2026-04-18'
---

# deployment-runtime-modularization-v1 - Phase 6

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-6-progress.md --task VAL-501 --status completed
```

## Objective

Close Phase 6 by validating the final runtime contract in CI and hosted smoke flows, then align operator documentation and the `ccdash` skill to the shipped API, worker, probe, and CLI/MCP rollout posture.

## Validation and Rollout Snapshot

| Concern | Current state | Notes |
| --- | --- | --- |
| Runtime matrix coverage | in progress | Test expansion is starting for `local`, `api`, `worker`, and `test` entrypoint expectations plus negative runtime-config cases. |
| Hosted smoke validation | in progress | The rollout checklist is being assembled around split API/worker startup, probes, migrations, one representative job path, and CLI/MCP operator queries. |
| Operator docs alignment | not started | Setup and runbook updates will follow the smoke-validation flow so commands, env tables, and failure modes match the shipped artifacts. |
| `ccdash` skill alignment | not started | Skill references and recipes remain queued until the final runtime contract and docs wording are locked. |

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("python-backend-engineer", "Execute VAL-501: extend runtime matrix coverage for entrypoints, negative config cases, probe semantics, and CLI/MCP bootstrap invariants")
Task("DevOps", "Execute VAL-502: add the repeatable hosted smoke validation flow for split API/worker runtime startup, probes, migrations, representative jobs, and CLI/MCP queries")

# Batch 2 (after VAL-502)
Task("documentation-writer", "Execute VAL-503: update setup and runbook documentation to match the shipped runtime contract and rollout posture")

# Batch 3 (after VAL-503)
Task("documentation-writer", "Execute VAL-504: refresh the ccdash skill guidance for the final runtime topology, probes, and MCP-aware routing posture")
```

## Kickoff Notes

- Phase 6 opened with VAL-501 and VAL-502 active so validation can proceed in parallel while preserving the documentation dependency chain.
- VAL-503 is intentionally gated on VAL-502 to keep operator docs aligned to the repeatable hosted smoke flow rather than provisional launch steps.
- VAL-504 remains queued behind VAL-503 so the `ccdash` skill inherits the finalized docs language and runtime-routing guidance instead of stale deployment assumptions.
