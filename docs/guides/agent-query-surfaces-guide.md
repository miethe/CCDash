# Agent Query Surfaces Guide

This guide explains what data CCDash exposes through the shared agent query layer, how to use it through CLI or MCP, what practical workflows look like, and which enhancements are likely next.

## Overview

CCDash now exposes one transport-neutral intelligence layer in `backend/application/services/agent_queries/`.

That same data is available through three surfaces:

- REST via `/api/agent/*`
- CLI via `ccdash`
- MCP via the `ccdash_*` tools

The current CLI and MCP surfaces expose the same four cross-domain reads:

- project status
- feature forensics
- workflow failure diagnostics
- after-action review generation

## What Data Is Available

### Project Status

Available through:

- CLI: `ccdash status project`
- MCP: `ccdash_project_status`
- REST: `GET /api/agent/project-status`

Data returned includes:

- project identity
- feature counts by status
- recent sessions
- 7-day cost and token summary
- top workflows
- sync freshness
- blocked features

Use it when you want to understand the current shape of a project before starting work.

### Feature Forensics

Available through:

- CLI: `ccdash report feature <feature-id>`
- MCP: `ccdash_feature_forensics`
- REST: `GET /api/agent/feature-forensics/{feature_id}`

Data returned includes:

- feature id, slug, and status
- linked sessions
- linked documents
- linked tasks
- iteration count
- total cost and tokens
- workflow mix
- rework signals
- failure patterns
- representative sessions
- summary narrative

Use it when you need execution history and evidence for one feature.

### Workflow Failure Diagnostics

Available through:

- CLI: `ccdash workflow failures`
- MCP: `ccdash_workflow_failure_patterns`
- REST: `GET /api/agent/workflow-diagnostics`

Data returned includes:

- project or feature-scoped workflow diagnostics
- workflow effectiveness and session counts
- failure counts
- top performers
- problem workflows

Use it when you suspect delivery friction is workflow-shaped rather than feature-shaped.

### After-Action Report

Available through:

- CLI: `ccdash report aar --feature <feature-id>`
- MCP: `ccdash_generate_aar`
- REST: `POST /api/agent/reports/aar`

Data returned includes:

- scope statement
- timeline
- key metrics
- turning points
- workflow observations
- bottlenecks
- successful patterns
- lessons learned
- evidence links

Use it when you want a structured retrospective or handoff artifact.

## CLI Versus MCP

### Use CLI When

- you want deterministic local output
- you want to pipe JSON into shell tools
- you want a quick operator-facing read from a terminal
- you are validating or debugging the data surface directly

Examples:

```bash
ccdash status project
ccdash report feature FEAT-123 --json
ccdash workflow failures --md
ccdash report aar --feature FEAT-123
```

### Use MCP When

- you want Claude Code or another MCP client to pull CCDash context on demand
- you want the agent to reason over project state without manual copy/paste
- you want the intelligence surface embedded in an agent workflow

Current MCP tools:

- `ccdash_project_status`
- `ccdash_feature_forensics`
- `ccdash_workflow_failure_patterns`
- `ccdash_generate_aar`

## Practical Workflows

### Workflow 1: Start Work On A Feature

1. Run `project status` to understand overall project health.
2. Pull `feature forensics` for the target feature.
3. Review linked sessions, rework signals, and representative evidence.
4. If the feature looks noisy or stuck, pull `workflow failure diagnostics`.
5. Start implementation with better context.

### Workflow 2: Investigate Delivery Problems

1. Run `workflow failures`.
2. Identify the worst-performing workflow or pattern.
3. Narrow to a specific feature with `feature forensics`.
4. Compare session evidence and failure patterns.
5. Use the results to choose a different execution strategy.

### Workflow 3: Close Out A Feature

1. Pull `feature forensics` to review what happened.
2. Generate `report aar`.
3. Use the AAR as a handoff note, retrospective input, or implementation summary.

## How To Utilize It Well

Use the surfaces as layered context rather than isolated commands.

Recommended order:

1. Start broad with `project status`.
2. Narrow to a feature with `feature forensics`.
3. Check systemic issues with `workflow failure diagnostics`.
4. Capture lessons with `after-action report`.

That order works well for both humans and agents because it moves from broad situational awareness to specific execution evidence.

## Testing And Validation

CLI smoke coverage:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_cli_commands.py -q
```

MCP stdio coverage:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
```

Manual MCP startup:

```bash
backend/.venv/bin/python -m backend.mcp.server
```

## Current Limitations

- The surface is read-only.
- The tool set is intentionally small: four high-value composite reads.
- Data quality depends on CCDash project resolution and the local CCDash cache being healthy.
- Manual Claude Code discovery/invocation remains the final end-user validation step for the MCP path.

## Likely Future Enhancements

Useful next additions would include:

- feature listing and filtering tools
- stale plan or stale progress detection
- top cost-driver reporting
- blocker and dependency summaries
- richer workflow filtering
- time-window filters
- easier explicit project selection and listing
- markdown-native or template-aware reporting output for agents
- eventual safe write operations such as note capture or progress updates
- MCP resources or prompts in addition to tools

## Related Docs

- [CLI User Guide](/Users/miethe/dev/homelab/development/CCDash/docs/guides/cli-user-guide.md)
- [MCP Setup Guide](/Users/miethe/dev/homelab/development/CCDash/docs/guides/mcp-setup-guide.md)
- [MCP Troubleshooting](/Users/miethe/dev/homelab/development/CCDash/docs/guides/mcp-troubleshooting.md)
- [backend/mcp/README.md](/Users/miethe/dev/homelab/development/CCDash/backend/mcp/README.md)
