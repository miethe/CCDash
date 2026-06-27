---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 3
phase_title: "API + agent_queries Exposure"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["python-backend-engineer"]
contributors: ["backend-typescript-architect"]

overall_progress: 0
completion_estimate: "on-track"
total_tasks: 8
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T3-001"
    name: "Repository: persist + read new columns"
    description: "Update backend/db/repositories/sessions.py to write and read all 11 new AgentSession columns in INSERT/SELECT."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T2-009"]
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6", "AC-B5"]
    files_affected:
      - "backend/db/repositories/sessions.py"

  - id: "T3-002"
    name: "Router: new query params + response fields"
    description: "Update GET /api/sessions to accept prompt_id and leaf_uuid query params. Update GET /api/sessions/{id} response to include all new fields. Wire into backend/routers/api.py and backend/routers/agent.py."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T2-009"]
    ac_refs: ["AC-A5", "AC-C6"]
    files_affected:
      - "backend/routers/api.py"
      - "backend/routers/agent.py"

  - id: "T3-003"
    name: "agent_queries: forensics surfaces"
    description: "Add search_by_prompt_id(prompt_id), trace_leaf_uuid(leaf_uuid), attribution_breakdown(session_id) to backend/application/services/agent_queries/. Wire into backend/routers/agent.py endpoints."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.4 pt"
    dependencies: ["T2-009"]
    ac_refs: ["AC-A5", "AC-C6", "AC-C4", "OQ-5 (agent_queries confirmed as home)"]
    files_affected:
      - "backend/application/services/agent_queries/"
      - "backend/routers/agent.py"

  - id: "T3-004"
    name: "MCP tools"
    description: "Add to backend/mcp/server.py: search_sessions_by_prompt_id, trace_leaf_uuid, get_attribution_breakdown. Each tool delegates to the agent_queries surface from T3-003."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.2 pt"
    dependencies: ["T2-009"]
    ac_refs: ["AC-C6", "AC-C4"]
    files_affected:
      - "backend/mcp/server.py"

  - id: "T3-005"
    name: "CLI subcommands"
    description: "Add ccdash session search --prompt-id <id> and ccdash session show --leaf-uuid <id> to backend/cli/. Both support --json flag."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.2 pt"
    dependencies: ["T2-009"]
    ac_refs: ["AC-C6"]
    files_affected:
      - "backend/cli/"

  - id: "T3-006"
    name: "types.ts + OpenAPI regen"
    description: "backend-typescript-architect mirrors all new AgentSession fields into types.ts frontend interface. Confirms OpenAPI regeneration includes new query params and response fields."
    status: pending
    assigned_to: ["backend-typescript-architect"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T3-001", "T3-002", "T3-003", "T3-004", "T3-005"]
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6"]
    files_affected:
      - "types.ts"

  - id: "T3-007"
    name: "Contract tests"
    description: "API contract tests: GET /api/sessions?prompt_id=, GET /api/sessions/{id} returns all new fields, attribution_breakdown endpoint, MCP JSON-mode regression for 3 new tools."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T3-006"]
    ac_refs: ["AC-A5", "AC-C4", "AC-C6"]
    files_affected:
      - "backend/tests/"

  - id: "T3-008"
    name: "Phase reviewer gate + seam check (R-P3)"
    description: "task-completion-validator confirms: agent_queries is transport-neutral (no router-side SQL), types.ts in sync with models.py, OpenAPI regen clean. Seam check: T3-006 types.ts delta consumed by P4 without type mismatch."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T3-007"]
    ac_refs: ["R-P3"]
    files_affected: []

parallelization:
  batch_1: ["T3-001", "T3-002", "T3-003"]
  batch_2: ["T3-004", "T3-005"]
  batch_3: ["T3-006", "T3-007"]
  batch_4: ["T3-008"]
  critical_path: ["T3-001", "T3-006", "T3-007", "T3-008"]

blockers: []

success_criteria:
  - { id: "SC-P3-1", description: "Repository round-trip for all 11 new columns.", status: "pending" }
  - { id: "SC-P3-2", description: "GET /api/sessions?prompt_id= returns correct sessions.", status: "pending" }
  - { id: "SC-P3-3", description: "search_by_prompt_id, trace_leaf_uuid, attribution_breakdown in agent_queries; no SQL in routers.", status: "pending" }
  - { id: "SC-P3-4", description: "MCP tools registered and callable.", status: "pending" }
  - { id: "SC-P3-5", description: "CLI subcommands pass exit-0 and --json tests.", status: "pending" }
  - { id: "SC-P3-6", description: "types.ts in sync with models.py.", status: "pending" }
  - { id: "SC-P3-7", description: "task-completion-validator sign-off.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 3: API + agent_queries Exposure

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-3-progress.md \
  -t T3-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update batch_1
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-3-progress.md \
  --updates "T3-001:completed,T3-002:completed,T3-003:completed"

# Batch update batch_2
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-3-progress.md \
  --updates "T3-004:completed,T3-005:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-3-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-3-progress.md
```
