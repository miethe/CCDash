---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 5
phase_title: "Forensics Rollups via CLI / MCP / AAR"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["python-backend-engineer"]
contributors: []

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
  - id: "T5-001"
    name: "CLI end-to-end tests"
    description: "End-to-end tests against a local fixture DB: ccdash session search --prompt-id <id> (match, no-match, malformed id). ccdash session show --leaf-uuid <id> (match, no-match). Both --json mode."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.3 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-C6"]
    files_affected:
      - "packages/ccdash_cli/tests/"
      - "backend/tests/"

  - id: "T5-002"
    name: "MCP regression tests"
    description: "JSON-mode regression for: search_sessions_by_prompt_id (match + no-match), trace_leaf_uuid (match + no-match), get_attribution_breakdown (session with data, session without)."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-C4", "AC-C6"]
    files_affected:
      - "backend/tests/test_mcp_server.py"

  - id: "T5-003"
    name: "AAR report attribution integration"
    description: "Update AAR report inputs in agent_queries to include skillsUsed/pluginsUsed breakdown per session. Test: fixture session with known attributionSkill values appears in AAR attribution section."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.2 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-C4 (AAR)"]
    files_affected:
      - "backend/application/services/agent_queries/"

  - id: "T5-004"
    name: "PlanningAgentSessionBoard top-plugins widget"
    description: "Add top-5 pluginsUsed aggregate widget to PlanningAgentSessionBoard.tsx. Aggregate across all sessions in board; show top-5 bar; empty state when no plugin data. FE fallback (R-P2): no plugin data -> empty state, not crash."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.2 pt"
    dependencies: ["T3-008"]
    ac_refs: ["AC-C4"]
    files_affected:
      - "components/Planning/PlanningAgentSessionBoard.tsx"

  - id: "T5-005"
    name: "promptId index decision (OQ-2 resolution)"
    description: "Evaluate whether CLI/MCP forensics filters land from T5-001/T5-002. If queries filter by prompt_id and the index from T1-003 is confirmed necessary (query plan shows seq scan), document rationale in migration comment. If index already present from P1, mark resolved."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.05 pt"
    dependencies: ["T5-001", "T5-002"]
    ac_refs: ["OQ-2"]
    files_affected:
      - "backend/db/migrations.py"

  - id: "T5-006"
    name: "Phase reviewer gate"
    description: "task-completion-validator confirms parity: REST + CLI + MCP query surfaces return consistent shapes for the same input."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T5-005"]
    ac_refs: ["AC-C4", "AC-C6"]
    files_affected: []

parallelization:
  batch_1: ["T5-001", "T5-002", "T5-003"]
  batch_2: ["T5-004"]
  batch_3: ["T5-005", "T5-006"]
  critical_path: ["T5-001", "T5-005", "T5-006"]

blockers: []

success_criteria:
  - { id: "SC-P5-1", description: "CLI --prompt-id and --leaf-uuid tests pass (6 cases).", status: "pending" }
  - { id: "SC-P5-2", description: "MCP regression tests pass for all 3 new tools.", status: "pending" }
  - { id: "SC-P5-3", description: "AAR attribution section populated in fixture test.", status: "pending" }
  - { id: "SC-P5-4", description: "OQ-2 (promptId index) explicitly resolved.", status: "pending" }
  - { id: "SC-P5-5", description: "task-completion-validator sign-off with REST/CLI/MCP parity confirmation.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 5: Forensics Rollups via CLI / MCP / AAR

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-5-progress.md \
  -t T5-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update batch_1 (parallel with P4)
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-5-progress.md \
  --updates "T5-001:completed,T5-002:completed,T5-003:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-5-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-5-progress.md
```
