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
status: "completed"
started: "2026-04-11"
completed: "2026-04-11"
commit_refs: ["7be7227", "d5fc82b", "b4b0319"]
pr_refs: []

overall_progress: 100
completion_estimate: "complete"

total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["worker"]
contributors: ["explorer"]

tasks:
  - id: "P3-T1"
    description: "Create backend/cli package structure, Typer root app, and a lightweight runtime/bootstrap path aligned with current RuntimeContainer and RequestMetadata patterns."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: []
    estimated_effort: "1pt"
    priority: "critical"

  - id: "P3-T2"
    description: "Implement CLI output abstraction and human/json/markdown formatters, including any new backend Python dependencies required for rendering."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P3-T1"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T3"
    description: "Implement the four MVP commands as thin adapters over Phase 1 query services with project override and error handling."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P3-T1", "P3-T2"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "P3-T4"
    description: "Add CliRunner coverage for all commands and output modes, including partial/error-path validation."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P3-T3"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T5"
    description: "Add editable packaging and setup integration so npm run setup installs the ccdash console entry point."
    status: "completed"
    assigned_to: ["worker"]
    dependencies: ["P3-T1", "P3-T4"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P3-T6"
    description: "Validate CLI help, focused tests, and setup/install behavior; measure startup path and document any follow-up performance work."
    status: "completed"
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
  - "backend/requirements.txt"
  - "backend/cli/__init__.py"
  - "backend/cli/__main__.py"
  - "backend/cli/main.py"
  - "backend/cli/runtime.py"
  - "backend/cli/output.py"
  - "backend/cli/commands/__init__.py"
  - "backend/cli/commands/status.py"
  - "backend/cli/commands/feature.py"
  - "backend/cli/commands/workflow.py"
  - "backend/cli/commands/report.py"
  - "backend/cli/formatters/__init__.py"
  - "backend/cli/formatters/base.py"
  - "backend/cli/formatters/_utils.py"
  - "backend/cli/formatters/json.py"
  - "backend/cli/formatters/markdown.py"
  - "backend/cli/formatters/table.py"
  - "backend/tests/test_cli_commands.py"
  - "pyproject.toml"
  - "scripts/setup.mjs"
  - "README.md"
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
- Phase 3 is complete; `backend/cli`, repo-root `pyproject.toml`, `scripts/setup.mjs`, and the shipped Typer/Rich packaging path already exist in-repo.
- The implemented bootstrap uses the lightweight `RuntimeContainer(profile=test)` + `RequestMetadata` + `build_request_context(...)` pattern and should be treated as the baseline for Phase 4.
- Phase 4 is still unstarted and must build on this landed CLI surface rather than replanning packaging or local-profile startup.
- `backend/.venv/bin/ccdash --help` passes after editable install.
- `backend/.venv/bin/python -m backend.cli --help` passes.
- `backend/.venv/bin/python -m pytest backend/tests/test_cli_commands.py -q` passes (`8 passed`).
- `npm run setup` could not be executed in this environment because `node`/`npm` are not installed on PATH, but `scripts/setup.mjs` was updated and the equivalent editable install path succeeded via `backend/.venv/bin/python -m pip install ... -e .`.
