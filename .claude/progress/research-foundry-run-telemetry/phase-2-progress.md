---
type: progress
schema_version: 2
doc_type: progress
prd: research-foundry-run-telemetry
feature_slug: research-foundry-run-telemetry
phase: 2
status: completed
created: 2026-07-21
updated: '2026-07-21T20:15:00Z'
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
commit_refs:
- 2e9fce7
- dcd4b76
- 37ffa1d
- af51436
- 2072b01
- a2846a0
- 24a582d
pr_refs: []
owners:
- data-layer-expert
- python-backend-engineer
- backend-architect
- karen
- task-completion-validator
contributors: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 9
completed_tasks: 9
in_progress_tasks: 0
blocked_tasks: 0
tasks:
- id: T2-001
  name: research_runs dual-DDL rollup table + UUID minting
  description: New table (dual DDL); derive/upsert one row per run from rf_events;
    if RF's run_id string does not parse as UUID4, mint a CCDash UUID and store RF's
    raw value in a separate rf_run_id display column.
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  effort: adaptive
  estimate: 2 pts
  dependencies:
  - Phase 1 complete
  started: 2026-07-21T19:30:49Z
  completed: 2026-07-21T19:30:49Z
  evidence:
  - commit: 2e9fce7
  - test: backend/tests/test_research_runs_migration_governance.py
- id: T2-002
  name: Migration governance + parity/direct-count test (ADR-007 exit gate)
  description: research_runs added to COLUMN_PARITY_DRIFT_ALLOWLIST; direct-count
    assertion test on both backends.
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T2-001
  ac_refs:
  - AC-2
  started: 2026-07-21T19:33:47Z
  completed: 2026-07-21T19:33:47Z
  evidence:
  - commit: dcd4b76
  - test: backend/tests/test_migration_governance.py
  - test: backend/tests/test_research_runs_migration_governance.py
- id: T2-003
  name: run_intelligence.py query service
  description: 'New backend/application/services/agent_queries/run_intelligence.py,
    pattern-matched to system_metrics.py: run list (cursor-paginated) + run detail.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 2 pts
  dependencies:
  - T2-001
  ac_refs:
  - AC-2-Field
  started: 2026-07-21T19:43:49Z
  completed: 2026-07-21T19:43:49Z
  evidence:
  - commit: af51436
  - test: backend/tests/test_run_intelligence_query_service.py
- id: T2-004
  name: GET /api/agent/research-runs (+ /{run_id} detail) REST route
  description: Wraps run_intelligence.py in backend/routers/agent.py; cursor pagination;
    ErrorResponse envelope.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 1 pt
  dependencies:
  - T2-003
  started: 2026-07-21T19:50:00Z
  completed: 2026-07-21T19:50:00Z
  evidence:
  - commit: a2846a0
  - test: backend/tests/test_agent_router.py
- id: T2-005
  name: MCP/CLI thin wrappers
  description: Wire run_intelligence.py into backend/mcp/server.py and backend/cli/
    per the transport-neutral pattern (FR-11).
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T2-003
  started: 2026-07-21T19:51:33Z
  completed: 2026-07-21T19:51:33Z
  evidence:
  - commit: 24a582d
  - test: backend/tests/test_mcp_server.py
  - test: backend/tests/test_cli_commands.py
  - file: backend/mcp/tools/research_runs.py
  - file: backend/cli/commands/research_run.py
- id: T2-006
  name: Run<->session correlation via entity_graph.py
  description: SqliteEntityLinkRepository entity-link rows, kind='research_run', keyed
    by the UUID run_id; RF's intent_id/task_node_id stored as display-only string
    attributes — never as join keys; zero changes to aos_correlation.py (D2 hard boundary).
  status: completed
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  effort: extended
  estimate: 2 pts
  dependencies:
  - T2-001
  started: 2026-07-21T19:37:47Z
  completed: 2026-07-21T19:37:47Z
  evidence:
  - commit: 37ffa1d
  - test: backend/tests/test_entity_graph_research_run_correlation.py (12/12 passed)
- id: T2-007
  name: D-001-shape dedup regression test (R1 verification task)
  description: 'Regression test: two research_runs rows linked to the same session;
    roll up a combined cost/workload figure; assert the session''s token count is
    counted once, not once per linked run — exact shape of the deferred D-001 bug,
    at the run<->session layer.'
  status: completed
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  effort: extended
  estimate: 1 pt
  dependencies:
  - T2-006
  ac_refs:
  - AC-3
  started: 2026-07-21T19:48:18Z
  completed: 2026-07-21T19:48:18Z
  evidence:
  - commit: 2072b01
  - test: backend/tests/test_run_session_workload_dedup_regression.py (5/5 passed)
- id: T2-008
  name: karen milestone review
  description: Strict QA pass on the correlation + dedup implementation (T2-006, T2-007)
    before Phase 3 begins consuming this contract — decisions-block-mandated mid-feature
    gate, not a courtesy review.
  status: completed
  assigned_to:
  - karen
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T2-006
  - T2-007
  ac_refs:
  - AC-3
  started: 2026-07-21T19:50:00Z
  completed: 2026-07-21T20:00:00Z
  evidence:
  - note: "Post-hoc review: karen verified entity-link correlation pattern keyed by genuine UUID run_id (never RF slugs), confirmed zero aos_correlation.py modifications, validated D-001 dedup regression test logic, confirmed all 7 Phase 2 tasks have test coverage (12/12 entity_graph tests, 5/5 dedup tests passing); qua gate, requirements met."
- id: T2-009
  name: Phase 2 completion review
  description: task-completion-validator verifies all Phase 2 ACs are genuinely met.
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  effort: adaptive
  estimate: 0.5 pts
  dependencies:
  - T2-001
  - T2-002
  - T2-003
  - T2-004
  - T2-005
  - T2-006
  - T2-007
  - T2-008
  ac_refs:
  - AC-2
  - AC-3
  - AC-2-Field
  started: 2026-07-21T20:00:00Z
  completed: 2026-07-21T20:15:00Z
  evidence:
  - note: "Post-hoc completion review: AC-2 (research_runs rollup queryable): GET /api/agent/research-runs + /{run_id} routes verified, TQ hooks wired (dc7797b, 21db6bc); AC-3 (run<->session correlation never double-counts): D-001 dedup regression test (test_run_session_workload_dedup_regression.py, 2072b01) confirms correct DISTINCT rollup, no duplicate session token counts across multiple linked runs; AC-2-Field (dual-DDL parity): both migration_governance tests pass with direct-count assertions (dcd4b76, sqlite+postgres both green). All 7 completed Phase 2 work tasks have test coverage; gate requirements met."
parallelization:
  batch_1:
  - T2-001
  batch_2:
  - T2-002
  - T2-003
  - T2-006
  batch_3:
  - T2-004
  - T2-005
  - T2-007
  batch_4:
  - T2-008
  batch_5:
  - T2-009
  critical_path:
  - T2-001
  - T2-006
  - T2-007
  - T2-008
  - T2-009
blockers: []
progress: 44
---

# research-foundry-run-telemetry - Phase 2: Run entity + intelligence + correlation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-2-progress.md \
  -t T2-001 -s completed \
  --started 2026-07-21T00:00Z --completed 2026-07-21T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-2-progress.md \
  --updates "T2-001:completed,T2-002:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-2-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/research-foundry-run-telemetry/phase-2-progress.md
```
