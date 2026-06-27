---
schema_version: 2
doc_type: progress
type: progress
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
phase: 2
phase_title: "New Event-Type Handling"
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
total_tasks: 9
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T2-001"
    name: "Attachment branch (14 subtypes)"
    description: "Add type: 'attachment' branch with per-subtype dispatch table. 6 subtypes (hook_success, file, nested_memory, edited_text_file, opened_file_in_ide, selected_lines_in_ide) additionally call add_artifact(). All subtypes produce a 'attachment:<subtype>' system-log entry. Unknown subtype: log attachment.unknown_subtype at DEBUG and store as 'attachment:unknown'."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: extended
    estimate: "1.25 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-B1", "OQ-1 (denormalized lean confirmed)"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-002"
    name: "ai-title branch"
    description: "New type: 'ai-title' branch: set AgentSession.title from aiTitle when titleSource != 'manual'; set aiTitleSource = 'ai-title'."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.25 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-B2"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-003"
    name: "last-prompt branch"
    description: "New type: 'last-prompt' branch: capture lastPrompt snippet (first 200 chars) and leafUuid into session metadata."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.25 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-B3", "AC-A5 (leafUuid)"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-004"
    name: "permission-mode branch"
    description: "New type: 'permission-mode' transition branch: append {timestamp, mode} to permissionModeTransitions[]."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.25 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-B4", "OQ-4 (per-turn timeline confirmed)"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-005"
    name: "bridge-session guard"
    description: "Verify/reinforce type: 'bridge-session' branch (started in T1-001) does not conflict with new event branches; add test coverage."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.1 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-A6"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-006"
    name: "system.subtype dispatch (4 new values)"
    description: "Extend system entry dispatch for turn_duration (append to turnDurations[]), away_summary (create artifact kind: 'away_summary', truncate at 8 KB), bridge_status (append to system event log), local_command (append to system event log). Add agent-setting and agent-name low-volume stubs."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: extended
    estimate: "0.5 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-B5"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-007"
    name: "Tool-category classifier extension"
    description: "Add TaskCreate, TaskUpdate, TaskList, Monitor, EnterWorktree, ExitWorktree, AskUserQuestion, ToolSearch, SendMessage, NotebookEdit to the classifier near parser.py ~L3066-3140. Each maps to a toolCategory value. Unclassified names fall back to 'other'."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T1-006"]
    ac_refs: ["AC-C7"]
    files_affected:
      - "backend/parsers/platforms/claude_code/parser.py"

  - id: "T2-008"
    name: "Parser unit tests (Bucket B)"
    description: "One fixture per new event type; attachment fixture covers all 14 subtypes + 1 unknown-subtype fixture; system.subtype fixture covers all 4 new values."
    status: pending
    assigned_to: ["python-backend-engineer"]
    assigned_model: sonnet
    effort: adaptive
    estimate: "0.25 pt"
    dependencies: ["T2-001", "T2-002", "T2-003", "T2-004", "T2-005", "T2-006", "T2-007"]
    ac_refs: ["AC-B1", "AC-B2", "AC-B3", "AC-B4", "AC-B5", "AC-C7"]
    files_affected:
      - "backend/tests/"

  - id: "T2-009"
    name: "Phase reviewer gate"
    description: "task-completion-validator reviews: fixture coverage, unknown-subtype fallback, no regressions to existing parser branches."
    status: pending
    assigned_to: ["task-completion-validator"]
    assigned_model: sonnet
    effort: extended
    estimate: "—"
    dependencies: ["T2-008"]
    ac_refs: ["AC-B1", "AC-B2", "AC-B3", "AC-B4", "AC-B5"]
    files_affected: []

parallelization:
  batch_1: ["T2-001"]
  batch_2: ["T2-002", "T2-003", "T2-004", "T2-005"]
  batch_3: ["T2-006", "T2-007"]
  batch_4: ["T2-008", "T2-009"]
  critical_path: ["T2-001", "T2-008", "T2-009"]

blockers: []

success_criteria:
  - { id: "SC-P2-1", description: "All 14 attachment subtypes produce system-log entries.", status: "pending" }
  - { id: "SC-P2-2", description: "Unknown-subtype fallback fixture passes (no exception; stores as 'attachment:unknown').", status: "pending" }
  - { id: "SC-P2-3", description: "All 4 new system.subtype values handled.", status: "pending" }
  - { id: "SC-P2-4", description: "All 10 new tool names classify correctly.", status: "pending" }
  - { id: "SC-P2-5", description: "No regressions in existing parser branch tests.", status: "pending" }
  - { id: "SC-P2-6", description: "task-completion-validator sign-off.", status: "pending" }
---

# jsonl-shape-gap-coverage - Phase 2: New Event-Type Handling

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-2-progress.md \
  -t T2-001 -s completed \
  --started 2026-05-19T00:00Z --completed 2026-05-19T00:00Z

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-2-progress.md \
  --updates "T2-001:completed,T2-002:completed,T2-003:completed,T2-004:completed"

# Validate this file
python .claude/skills/artifact-tracking/scripts/validate_artifact.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-2-progress.md

# Phase gate check
python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py \
  -f .claude/progress/jsonl-shape-gap-coverage/phase-2-progress.md
```
