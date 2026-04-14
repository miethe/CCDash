---
schema_version: 2
doc_type: progress
type: progress
prd: "ccdash-query-caching-and-cli-ergonomics"
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
phase: "2.5"
title: "Feature-Show linked_sessions Reconciliation"
status: pending
created: 2026-04-14
updated: 2026-04-14
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners: ["python-backend-engineer"]
contributors: ["backend-architect"]
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "REC-001"
    description: "Investigate linked_sessions disagreement: feature_show returns [] while feature sessions <id> returns 70+ sessions for same feature. Inspect backend/routers/agent.py feature-show and feature sessions endpoints. Determine if intentional filter or bug. Document findings."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: []
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "medium"

  - id: "REC-002"
    description: "Reconcile endpoints to agree: if bug, update inline array construction to match endpoint; if filter, document rationale explicitly. Both feature_show.linked_sessions and feature sessions must return identical arrays for the same feature."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["REC-001"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "REC-003"
    description: "Add hint to feature-show response DTO: one-line note 'sessions: N available — run ccdash feature sessions <id> for details'. Displayed in CLI or MCP output. Nudges operators toward authoritative endpoint."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["REC-002"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "REC-004"
    description: "Eventual-consistency documentation: if session linkage is eventually-consistent (background job), add docs/guides/ entry explaining timing. If synchronous, note in DTO docstring. Update cli-timeout-debugging.md to mention if applicable."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["REC-001"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "REC-005"
    description: "Add integration test: load a feature with sessions; call both feature_show and feature sessions; assert linked_sessions arrays are equal. CI regression guard to prevent future endpoint divergence."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["REC-003"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

parallelization:
  batch_1: ["REC-001"]
  batch_2: ["REC-002", "REC-004"]
  batch_3: ["REC-003"]
  batch_4: ["REC-005"]
  critical_path: ["REC-001", "REC-002", "REC-003", "REC-005"]
  estimated_total_time: "0.5-0.75 days"

blockers: []

success_criteria:
  - { id: "SC-2.5.1", description: "Root cause of linked_sessions disagreement investigated and documented", status: "pending" }
  - { id: "SC-2.5.2", description: "Inline array reconciled to match endpoint (or documented as filtered subset)", status: "pending" }
  - { id: "SC-2.5.3", description: "Hint added to feature-show DTO output directing callers to authoritative endpoint", status: "pending" }
  - { id: "SC-2.5.4", description: "Integration test asserts endpoint agreement on every CI pass", status: "pending" }
  - { id: "SC-2.5.5", description: "Eventual-consistency behavior documented if applicable", status: "pending" }
  - { id: "SC-2.5.6", description: "All tests pass", status: "pending" }

files_modified:
  - "backend/routers/agent.py"
  - "backend/application/services/agent_queries/models.py"
  - "backend/application/services/agent_queries/feature_forensics.py"
  - "backend/tests/"
  - "docs/guides/"
---

# CCDash Query Caching and CLI Ergonomics - Phase 2.5: Feature-Show linked_sessions Reconciliation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-2.5-progress.md \
  -t REC-001 -s completed
```

---

## Quick Reference

REC-001 is the first step — all others flow from it. REC-002 and REC-004 can run in parallel (REC-004 only requires REC-001 root-cause findings). Phase 2.5 starts after Phase 2 completes.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| REC-001 | sonnet | medium | `Task("REC-001: Investigate the linked_sessions disagreement between feature_show endpoint (returns []) and feature sessions <id> endpoint (returns 70+ sessions). Inspect backend/routers/agent.py for both endpoints. Determine if the inline array is intentionally filtered or a bug. Document findings inline.", model="sonnet")` |
| REC-002 | sonnet | low | `Task("REC-002: Based on REC-001 findings, reconcile feature_show.linked_sessions to match feature sessions endpoint. If bug: fix inline array construction. If filter: preserve behavior but add explicit documentation. Both endpoints must return identical linked_sessions for the same feature. Reference: REC-001.", model="sonnet")` |
| REC-003 | sonnet | low | `Task("REC-003: Add a hint to the feature-show response (DTO or CLI formatter): 'sessions: N available — run ccdash feature sessions <id> for details'. Make it visible in CLI output and MCP tool output. Nudges callers toward authoritative endpoint. Reference: REC-002.", model="sonnet")` |
| REC-004 | haiku | low | `Task("REC-004: Based on REC-001 root-cause: if session linkage is eventually-consistent (background sync job), document timing in docs/guides/ and update cli-timeout-debugging.md accordingly. If synchronous, add a note to the DTO docstring only. Reference: REC-001.", model="haiku")` |
| REC-005 | sonnet | low | `Task("REC-005: Write pytest integration test that loads a feature with sessions, calls both feature_show and feature sessions endpoints, and asserts linked_sessions arrays are equal. Test runs on every CI pass to prevent future endpoint divergence. Reference: REC-003.", model="sonnet")` |

---

## Objective

Investigate and reconcile the data disagreement between `feature_show.linked_sessions` inline array and the dedicated `feature sessions <id>` endpoint. After reconciliation, both endpoints return identical data for the same feature. A hint is added to feature-show output to nudge callers toward the authoritative endpoint.

---

## Implementation Notes

### Architectural Decisions

- REC-001 root cause is the decision gate: the fix (REC-002) or documentation approach (REC-004) depends entirely on the findings.
- If behavior is intentional filtering (e.g., only explicit session links in inline array), preserve and document it clearly rather than changing the filter logic unexpectedly.
- The hint in REC-003 is low-risk: additive-only text in formatter output; no schema changes required.

### Key Files

- `backend/routers/agent.py` — both `feature show` and `feature sessions` route handlers live here; compare their query paths
- `backend/application/services/agent_queries/feature_forensics.py` — inline `linked_sessions` construction
- `backend/application/services/agent_queries/models.py` — DTO hint field (if added as DTO field vs. formatter string)

### Cross-Phase Notes

- Phase 2.5 depends on Phase 2 (DTO alias fields) being complete; the `linked_sessions` field already exists on the DTO.
- TEST-002.5 in Phase 5 provides an additional integration test layer; REC-005 is the immediate regression guard.
- If eventual-consistency is found, REC-004 coordinates with DOC-004 (cli-timeout-debugging guide) in Phase 5.

---

## Completion Notes

_(Fill in when phase is complete)_
