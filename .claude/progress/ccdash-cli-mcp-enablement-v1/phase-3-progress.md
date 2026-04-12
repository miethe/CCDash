---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-cli-mcp-enablement-v1"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: /docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1/phase-3-4-cli-mcp.md
phase: 3
title: "CLI MVP"
status: "in-progress"
started: "2026-04-11"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["worker"]
contributors: ["explorer"]

tasks:
  - id: "P3-T1"
    description: "Create backend/cli package structure, Typer root app, and a lightweight runtime/bootstrap path aligned with current RuntimeContainer and RequestMetadata patterns."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: []
    estimated_effort: "1pt"
    priority: "critical"

  - id: "P3-T2"
    description: "Implement CLI output abstraction and human/json/markdown formatters, including any new backend Python dependencies required for rendering."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P3-T1"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T3"
    description: "Implement the four MVP commands as thin adapters over Phase 1 query services with project override and error handling."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P3-T1", "P3-T2"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "P3-T4"
    description: "Add CliRunner coverage for all commands and output modes, including partial/error-path validation."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P3-T3"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T5"
    description: "Add editable packaging and setup integration so npm run setup installs the ccdash console entry point."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P3-T1", "P3-T4"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T6"
    description: "Validate CLI help, focused tests, and setup/install behavior; measure startup path and document any follow-up performance work."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P3-T5"]
    estimated_effort: "1pt"
    priority: "medium"

parallelization:
  batch_1: ["P3-T1"]
  batch_2: ["P3-T2"]
  batch_3: ["P3-T3"]
  batch_4: ["P3-T4", "P3-T5"]
  batch_5: ["P3-T6"]
  critical_path: ["P3-T1", "P3-T2", "P3-T3", "P3-T4", "P3-T5", "P3-T6"]
  estimated_total_time: "8pt / 5-7 days"

blockers: []

success_criteria:
  - "CLI bootstrap uses current CCDash runtime/request-context conventions rather than introducing a duplicate context path."
  - "`backend/requirements.txt` and packaging metadata install all CLI dependencies required by the implementation."
  - "`python -m backend.cli --help` and `ccdash --help` both work after setup."
  - "All four MVP commands succeed with valid human/json/markdown output."
  - "CliRunner coverage exercises success, partial, and error paths for all commands."
  - "Phase 3 introduces no business-logic duplication relative to Phase 1 query services."

files_modified:
  - ".claude/progress/ccdash-cli-mcp-enablement-v1/phase-3-progress.md"
  - "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1/phase-3-4-cli-mcp.md"
---

# ccdash-cli-mcp-enablement-v1 - Phase 3: CLI MVP

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-cli-mcp-enablement-v1/phase-3-progress.md -t P3-TX -s completed
```

## Objective

Build the CLI surface as a thin local adapter over Phase 1 query services, then package it so `npm run setup` installs a working `ccdash` command in the backend virtual environment.

## Validation Notes

- Phase 1 and Phase 2 are already complete in the current repo.
- No existing CLI package or console-script metadata exists, so Phase 3 owns the full adapter/bootstrap/testing/packaging path.
- Packaging must account for the namespace-style `backend` package layout at repo root.
