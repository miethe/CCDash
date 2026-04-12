---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-cli-mcp-enablement-v1"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: /docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1/phase-3-4-cli-mcp.md
phase: 4
title: "MCP MVP"
status: "in-progress"
started: "2026-04-12"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "pending"

total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["worker"]
contributors: ["explorer"]

tasks:
  - id: "P4-T1"
    description: "Add the MCP SDK dependency and create the backend/mcp package skeleton on the existing test-profile runtime bootstrap path."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: []
    estimated_effort: "1pt"
    priority: "critical"

  - id: "P4-T2"
    description: "Implement the FastMCP server entry point plus the four thin tool adapters over the existing Phase 1 query services."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P4-T1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "P4-T3"
    description: "Add SDK-supported stdio transport tests using stdio_client and ClientSession to validate initialize, list_tools, and call_tool against the real server."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P4-T2"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P4-T4"
    description: "Commit the workspace .mcp.json config that points Claude Code at the same stdio launch command exercised by the harness."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P4-T2"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "P4-T5"
    description: "Run manual Claude Code discovery and tool invocation, reconcile any differences with the automated harness, and close Phase 4 only after both paths agree."
    status: "pending"
    assigned_to: ["worker"]
    dependencies: ["P4-T3", "P4-T4"]
    estimated_effort: "1pt"
    priority: "medium"

parallelization:
  batch_1: ["P4-T1"]
  batch_2: ["P4-T2"]
  batch_3: ["P4-T3", "P4-T4"]
  batch_4: ["P4-T5"]
  critical_path: ["P4-T1", "P4-T2", "P4-T3", "P4-T5"]
  estimated_total_time: "5pt / 4-6 days"

blockers: []

success_criteria:
  - "Phase 4 bootstrap uses the existing test runtime profile with `RuntimeContainer(profile=get_runtime_profile(\"test\"))`, `RequestMetadata`, and `container.build_request_context(...)`."
  - "No MCP code uses `RequestContext.from_environment()` or a separate local runtime profile."
  - "`python -m backend.mcp.server` starts successfully over stdio and exposes all four MVP tools."
  - "Automated coverage uses `stdio_client` + `ClientSession` and exercises `initialize`, `list_tools`, and `call_tool`."
  - ".mcp.json points Claude Code at the same stdio server launch command validated by the harness."
  - "Manual Claude Code discovery and tool invocation succeed before the phase is marked complete."

files_modified:
  - ".claude/progress/ccdash-cli-mcp-enablement-v1/phase-4-progress.md"
---

# ccdash-cli-mcp-enablement-v1 - Phase 4: MCP MVP

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-cli-mcp-enablement-v1/phase-4-progress.md -t P4-TX -s in_progress
```

## Objective

Build the MCP surface as a thin stdio adapter over Phase 1 query services, using the existing test-profile runtime bootstrap and the SDK-supported `stdio_client` + `ClientSession` harness.

## Update Workflow

- Update `P4-T1` through `P4-T5` as implementation lands and keep the progress summary in sync with the current worktree.
- Reuse the existing test-profile bootstrap from `backend/cli/runtime.py`; do not add a second runtime path for MCP.
- Keep validation anchored to the SDK-supported `stdio_client` + `ClientSession` harness and the workspace `.mcp.json` discovery path.
- Record manual Claude Code discovery results before moving the phase to complete.

## Validation Notes

- Phase 3 is already landed in the current worktree; the CLI package, Typer/Rich formatting, editable packaging metadata, and console-script path already exist.
- Phase 4 starts from the existing CLI runtime/bootstrap pattern rather than replanning packaging or a local-profile startup path.
- `backend/cli/runtime.py` is the bootstrap baseline to reuse for MCP: `RuntimeContainer(profile=get_runtime_profile("test"))`, `RequestMetadata`, and `container.build_request_context(...)`.
- The repo does **not** yet contain `backend/mcp/` or a committed `.mcp.json`.
- Validation must use the SDK-supported stdio harness (`stdio_client` + `ClientSession`) and not a speculative `mcp.test_client` helper.

## Execution Plan

### Batch 1

`Task("worker", "Execute P4-T1: add the MCP SDK dependency and create the backend/mcp package skeleton on the existing test-profile runtime bootstrap path")`

### Batch 2

`Task("worker", "Execute P4-T2: implement the FastMCP server entry point plus the four thin tool adapters over the existing Phase 1 query services")`

### Batch 3

`Task("worker", "Execute P4-T3: add SDK-supported stdio transport tests with stdio_client and ClientSession against the real server")`
`Task("worker", "Execute P4-T4: commit the workspace .mcp.json config and align it with the tested stdio launch command")`

### Batch 4

`Task("worker", "Execute P4-T5: run manual Claude Code discovery and tool invocation, then close the phase after automated and manual validation agree")`
