---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 1
phase_title: "Parser & Schema Enrichment"
status: pending
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
commit_refs: []
pr_refs: []

owners: ["python-backend-engineer"]
contributors: ["data-layer-expert"]

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
  - id: "T1-001"
    name: "Parser field captures"
    description: "Extend record_entry_context (~L2219) to accumulate attributionSkill, attributionPlugin, promptId, sessionKind per entry. Extend session-assembly block (~L1857) to roll into skillsUsed, pluginsUsed, promptId. Add thinking.signature capture alongside thinking-block text. Add bridge-session branch for bridgeSessionId/lastSequenceNum."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.75 pt"
    dependencies: []
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T1-002"
    name: "Model fields + types.ts"
    description: "Add nullable fields to AgentSession in backend/models.py: session_kind, prompt_id, leaf_uuid, bridge_session_id, last_sequence_num, plugins_used (JSON array), ai_title_source, permission_mode_transitions (JSON), turn_durations (JSON), away_summaries (JSON), thinking_signatures (JSON). Mirror all new fields in types.ts."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pt"
    dependencies: []
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6"]
    files_affected:
      - "backend/models.py"
      - "types.ts"

  - id: "T1-003"
    name: "DB migrations (SQLite + PostgreSQL)"
    description: "Add ALTER TABLE agent_sessions ADD COLUMN for all 11 new columns. Both SQLite and PostgreSQL paths covered; prompt_id gets an index. Add CONCURRENTLY qualifier on the PostgreSQL index path."
    status: pending
    assigned_to: ["data-layer-expert"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.5 pt"
    dependencies: []
    ac_refs: ["AC-A1", "AC-A3", "AC-A5", "AC-A6"]
    files_affected:
      - "backend/db/migrations.py"

  - id: "T1-004"
    name: "Parser unit tests (Bucket A)"
    description: "Fixture-based tests: each new field populated from a synthetic JSONL fixture. Separate fixture with all new fields absent confirms null-safe behavior."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T1-001", "T1-002", "T1-003"]
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6"]
    files_affected:
      - "backend/tests/"

  - id: "T1-005"
    name: "CI migration smoke (both backends)"
    description: "Add a CI step (or test) that runs the migration sequence against both CCDASH_DB_BACKEND=sqlite and CCDASH_DB_BACKEND=postgres in the test suite."
    status: pending
    assigned_to: ["data-layer-expert"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T1-001", "T1-002", "T1-003"]
    ac_refs: ["AC-A1", "OQ-3 resolution"]
    files_affected:
      - "backend/tests/"

  - id: "T1-006"
    name: "Phase reviewer gate"
    description: "task-completion-validator reviews: schema diff is additive-only, both backend migration tests pass, AC-A1...A6 unit tests green."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T1-004", "T1-005"]
    ac_refs: ["AC-A1", "AC-A2", "AC-A3", "AC-A4", "AC-A5", "AC-A6"]
    files_affected: []

parallelization:
  batch_1: ["T1-001", "T1-002", "T1-003"]
  batch_2: ["T1-004", "T1-005"]
  batch_3: ["T1-006"]
  critical_path: ["T1-001", "T1-004", "T1-006"]

blockers: []

success_criteria:
  - { id: "SC-P1-1", description: "All 8 new fields captured on fixture with data; null-safe on fixture without.", status: "pending" }
  - { id: "SC-P1-2", description: "DB migrations run on both SQLite and PostgreSQL without error.", status: "pending" }
  - { id: "SC-P1-3", description: "prompt_id index created on agent_sessions table.", status: "pending" }
  - { id: "SC-P1-4", description: "Schema diff is additive-only (no DROP, no NOT NULL without DEFAULT).", status: "pending" }
  - { id: "SC-P1-5", description: "task-completion-validator sign-off.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 1: Parser & Schema Enrichment

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-1-progress.md \
  -t T1-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-1-progress.md \
  --updates "T1-001:completed,T1-002:completed,T1-003:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-1-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-1-progress.md
```
