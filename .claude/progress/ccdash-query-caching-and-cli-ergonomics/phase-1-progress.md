---
schema_version: 2
doc_type: progress
type: progress
prd: "ccdash-query-caching-and-cli-ergonomics"
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
phase: 1
title: "CLI Timeout Plumbing"
status: pending
created: 2026-04-14
updated: 2026-04-14
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners: ["python-backend-engineer"]
contributors: []
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "CLI-001"
    description: "Explore CLI and RuntimeClient timeout setup — inspect client.py, identify _DEFAULT_TIMEOUT, verify construction site"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    estimated_effort: "1 pt"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "CLI-002"
    description: "Add --timeout global flag to CLI root (Typer); store resolved value; flag > env > default precedence"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-001"]
    estimated_effort: "2 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "CLI-003"
    description: "Add CCDASH_TIMEOUT env var fallback; implement flag > env > default resolution"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-002"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "CLI-004"
    description: "Wire resolved timeout into RuntimeClient construction — single construction point, no per-request overrides"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-003"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "CLI-005"
    description: "Update ccdash doctor and ccdash target check to display active timeout + source (flag/env/default)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-004"]
    estimated_effort: "1 pt"
    priority: "low"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "CLI-006"
    description: "Regression test: 4 scenarios — no flag/no env, flag set, env set, both set. Backward compat verified."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-005"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

parallelization:
  batch_1: ["CLI-001"]
  batch_2: ["CLI-002"]
  batch_3: ["CLI-003"]
  batch_4: ["CLI-004"]
  batch_5: ["CLI-005"]
  batch_6: ["CLI-006"]
  critical_path: ["CLI-001", "CLI-002", "CLI-003", "CLI-004", "CLI-005", "CLI-006"]
  estimated_total_time: "1-1.5 days"

blockers: []

success_criteria:
  - { id: "SC-1.1", description: "CLI accepts --timeout flag with valid values", status: "pending" }
  - { id: "SC-1.2", description: "CCDASH_TIMEOUT env var respected", status: "pending" }
  - { id: "SC-1.3", description: "Flag > env > default precedence enforced", status: "pending" }
  - { id: "SC-1.4", description: "ccdash doctor / ccdash target check display active timeout", status: "pending" }
  - { id: "SC-1.5", description: "Backward-compat test passes (no timeout specified = default 30 s)", status: "pending" }
  - { id: "SC-1.6", description: "No breaking changes to existing CLI invocations", status: "pending" }

files_modified:
  - "packages/ccdash_cli/src/ccdash_cli/runtime/client.py"
  - "packages/ccdash_cli/src/ccdash_cli/cli.py"
  - "packages/ccdash_cli/tests/"
---

# CCDash Query Caching and CLI Ergonomics - Phase 1: CLI Timeout Plumbing

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-1-progress.md \
  -t CLI-001 -s completed
```

---

## Quick Reference

Tasks are fully sequential (each depends on the previous). No parallelization within this phase.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| CLI-001 | haiku | low | `Task("CLI-001: Inspect packages/ccdash_cli/src/ccdash_cli/runtime/client.py — identify _DEFAULT_TIMEOUT, verify timeout is passed at client construction, note the CLI root command entry point location. Document findings inline.", model="haiku")` |
| CLI-002 | sonnet | low | `Task("CLI-002: Add --timeout global flag to CLI root Typer group. Default 30 s (current hardcoded). Accept float/int seconds. Store resolved value for RuntimeClient construction. Reference: CLI-001 findings.", model="sonnet")` |
| CLI-003 | sonnet | low | `Task("CLI-003: Add CCDASH_TIMEOUT env var fallback. Flag > env > default (30 s). Wire in CLI startup before RuntimeClient is constructed. Reference: CLI-002.", model="sonnet")` |
| CLI-004 | sonnet | low | `Task("CLI-004: Pass resolved timeout to RuntimeClient(timeout=...) at construction. Single construction point in context setup or command group handler. Reference: CLI-003.", model="sonnet")` |
| CLI-005 | sonnet | low | `Task("CLI-005: Update ccdash doctor and ccdash target check output tables to show active timeout and its source label (flag / env: CCDASH_TIMEOUT / default). Reference: CLI-004.", model="sonnet")` |
| CLI-006 | sonnet | low | `Task("CLI-006: Write pytest tests covering 4 timeout precedence scenarios. Verify backward compat: no flag + no env = 30 s default. Reference: CLI-005.", model="sonnet")` |

---

## Objective

Resolve the hardcoded `_DEFAULT_TIMEOUT` constant in `RuntimeClient` and wire a configurable timeout through the CLI flag (`--timeout`) and env var (`CCDASH_TIMEOUT`). Surface the active timeout in `ccdash doctor` and `ccdash target check` output.

---

## Implementation Notes

### Architectural Decisions

- Timeout resolution happens once at CLI startup (command group invocation context), not per-request or per-command. This keeps RuntimeClient construction clean.
- Standard Typer pattern: `@app.callback()` on the root group captures the `--timeout` option and stores it in a `typer.Context` or a simple module-level config singleton before subcommands execute.

### Key File

`packages/ccdash_cli/src/ccdash_cli/runtime/client.py` — OQ-1 resolved: RuntimeClient uses a shared `httpx.Client` constructed once; timeout is passed at construction.

### Patterns and Best Practices

- Precedence: CLI flag beats `os.getenv("CCDASH_TIMEOUT")` beats hardcoded 30 s default. Use `float(os.getenv("CCDASH_TIMEOUT", 30))` as env fallback.
- `ccdash doctor` output source label: emit `(flag)`, `(env: CCDASH_TIMEOUT)`, or `(default)` depending on resolution path.

### Cross-Phase Notes

- Phase 1 and Phase 2 are independent and can run concurrently.
- Phase 3 (cache) adds `--no-cache` CLI flag; CLI-004's RuntimeClient wiring pattern is the model to follow.

---

## Completion Notes

_(Fill in when phase is complete)_
