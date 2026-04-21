---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2-interaction-performance-addendum"
feature_slug: "ccdash-planning-reskin-v2-interaction-performance-addendum"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 15
title: "Agent Roster Details"
status: "pending"
created: 2026-04-21
updated: 2026-04-21
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["frontend-developer", "python-backend-engineer"]
contributors: []

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "P15-001"
    description: "Add canonical subagentType or displayAgentType to AgentSession."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    assigned_model: "sonnet"
    dependencies: ["P11-001"]
    estimated_effort: "2 pts"
    priority: "high"

  - id: "P15-002"
    description: "Change roster name precedence and root-session label."
    status: "pending"
    assigned_to: ["frontend-developer"]
    assigned_model: "sonnet"
    dependencies: ["P15-001"]
    estimated_effort: "1 pt"
    priority: "high"

  - id: "P15-003"
    description: "Pin roster height to triage height and add internal scrolling."
    status: "pending"
    assigned_to: ["frontend-developer"]
    assigned_model: "sonnet"
    dependencies: []
    estimated_effort: "1 pt"
    priority: "medium"

  - id: "P15-004"
    description: "Add roster row detail modal."
    status: "pending"
    assigned_to: ["frontend-developer"]
    assigned_model: "sonnet"
    dependencies: ["P15-001", "P11-001"]
    estimated_effort: "1.5 pts"
    priority: "high"

  - id: "P15-005"
    description: "Link roster rows to feature/phase quick-view data."
    status: "pending"
    assigned_to: ["frontend-developer"]
    assigned_model: "sonnet"
    dependencies: ["P15-004"]
    estimated_effort: "1 pt"
    priority: "medium"

parallelization:
  batch_1: ["P15-001", "P15-003"]
  batch_2: ["P15-002", "P15-004"]
  batch_3: ["P15-005"]
  critical_path: ["P15-001", "P15-004", "P15-005"]
  estimated_total_time: "2 days"

blockers: []

success_criteria:
  - { id: "SC-15.1", description: "Frontend does not parse human title strings to infer agent type; canonical field used", status: "pending" }
  - { id: "SC-15.2", description: "Subagents show type labels; main/root sessions show 'Orchestrator'; ids appear only as tooltip/detail fallback", status: "pending" }
  - { id: "SC-15.3", description: "Roster and triage panels align at desktop breakpoints; long roster scrolls inside its panel", status: "pending" }
  - { id: "SC-15.4", description: "Clicking any roster row opens agent details modal with links to session, feature, phase/task context, parent/root session, model, token/context data", status: "pending" }
  - { id: "SC-15.5", description: "Roster rows show compact feature/phase/task hints when available; missing metadata has neutral empty state", status: "pending" }
  - { id: "SC-15.6", description: "All tests green", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 15: Agent Roster Details

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-15-progress.md \
  -t P15-001 -s completed
```

---

## Phase Overview

**Title**: Agent Roster Details
**Entry Criteria**: Phase 11 complete. Agent session hydration with type metadata available from backend.
**Exit Criteria**: All tasks complete. Roster displays agent types correctly. Detail modal functional. Quick-view hints displayed where available. Tests green.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-15`

P15-001 (backend canonical type field) and P15-003 (height/scroll) can run in parallel in batch 1. P15-002 (display precedence) and P15-004 (detail modal) both depend on P15-001's field, but they can run in parallel with each other in batch 2. P15-005 (quick-view hints) follows P15-004.

The addendum notes that Phase 15 can proceed in parallel with Phase 14 once agent session display fields are exposed (P15-001). Coordinate with Phase 14's `PlanningQuickViewPanel` since roster rows may open the same panel surface or a separate agent-specific modal.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P15-001 | Add canonical subagentType / displayAgentType to AgentSession | python-backend-engineer | sonnet | 2 pts | P11-001 | pending |
| P15-002 | Change roster name precedence and root-session label | frontend-developer | sonnet | 1 pt | P15-001 | pending |
| P15-003 | Pin roster height to triage; add internal scroll | frontend-developer | sonnet | 1 pt | — | pending |
| P15-004 | Add roster row detail modal | frontend-developer | sonnet | 1.5 pts | P15-001, P11-001 | pending |
| P15-005 | Link roster rows to feature/phase quick-view hints | frontend-developer | sonnet | 1 pt | P15-004 | pending |

### P15-001 Acceptance Criteria
Backend exposes `subagentType` and/or `displayAgentType` directly on `AgentSession` and `AgentSessionDTO`. The field is populated by reusing the existing `_subagent_type_from_logs` logic — not derived in the frontend by parsing `title` or `agentId`. Also expose `linkedFeatureIds`, `phaseHints`, and `taskHints` per the addendum's data contract. Files: `backend/parsers/sessions.py` or equivalent hydration path, `backend/models.py`, `types.ts`.

### P15-002 Acceptance Criteria
`PlanningAgentRosterPanel` display name precedence: (1) `session.subagentType` or `displayAgentType`, (2) `session.title` when it is a human-readable derived label, (3) `"Orchestrator"` for root/main sessions, (4) `session.agentId` only as fallback. Agent id remains visible in `title` attribute and in the detail modal. Files: `components/Planning/PlanningAgentRosterPanel.tsx`.

### P15-003 Acceptance Criteria
At desktop breakpoints, the roster panel height is pinned to match the Triage Inbox height. When the roster row count overflows the pinned height, the panel scrolls internally without affecting the page layout. The pinning approach works across the existing planning grid layout. Files: `components/Planning/PlanningAgentRosterPanel.tsx`, `components/Planning/PlanningRouteLayout.tsx`.

### P15-004 Acceptance Criteria
Clicking any roster row opens an agent detail modal within `/planning`. The modal includes: agent state, model, token/context utilization, link to session, parent/root session reference, linked feature (if `linkedFeatureIds`), phase/task hints, files/artifacts when available, and navigation links to session inspector and feature modal. Constructed using existing components where available. Files: `components/Planning/PlanningAgentRosterPanel.tsx`, new or extended modal component.

### P15-005 Acceptance Criteria
Roster rows render compact inline hints for feature slug, current phase, and active task when that data is available from `linkedFeatureIds`, `phaseHints`, `taskHints`, or session-feature links. When metadata is unavailable, the hint area shows a neutral empty state (not an error or spinner). Files: `components/Planning/PlanningAgentRosterPanel.tsx`.

---

## Quick Reference

### Batch 1 — Unblocked; run in parallel
```
Task("python-backend-engineer", "P15-001: Add canonical subagentType and displayAgentType fields to AgentSession in backend/models.py and types.ts. Reuse existing _subagent_type_from_logs logic — expose the value directly rather than forcing roster to infer from title/agentId. Also add linkedFeatureIds, phaseHints, taskHints per data contract. Depends on Phase 11 (P11-001) being complete.")
Task("frontend-developer", "P15-003: Pin PlanningAgentRosterPanel height to match Triage Inbox at desktop breakpoints. Add internal scroll for overflow. Must not affect page layout. Files: components/Planning/PlanningAgentRosterPanel.tsx, components/Planning/PlanningRouteLayout.tsx")
```

### Batch 2 — After P15-001; run in parallel
```
Task("frontend-developer", "P15-002: Update PlanningAgentRosterPanel display name precedence to: (1) subagentType/displayAgentType, (2) session.title as human label, (3) 'Orchestrator' for root/main sessions, (4) session.agentId as fallback only. Agent id visible in title attribute. Files: components/Planning/PlanningAgentRosterPanel.tsx")
Task("frontend-developer", "P15-004: Add agent detail modal opened from any roster row. Modal shows: agent state, model, token/context utilization, session link, parent/root session, linked feature, phase/task hints, files/artifacts, navigation links. Use existing components where possible. Files: components/Planning/PlanningAgentRosterPanel.tsx")
```

### Batch 3 — After P15-004
```
Task("frontend-developer", "P15-005: Add compact inline feature/phase/task hints to roster rows using linkedFeatureIds, phaseHints, taskHints from AgentSession. Missing data shows neutral empty state. Files: components/Planning/PlanningAgentRosterPanel.tsx")
```

---

## Quality Gates

- [ ] Backend exposes `subagentType`, `displayAgentType`, `linkedFeatureIds`, `phaseHints`, `taskHints`
- [ ] Frontend does not parse title/agentId strings to infer agent type
- [ ] Roster name precedence correct (type → title → Orchestrator → id fallback)
- [ ] Roster height pinned to triage at desktop; overflow scrolls internally
- [ ] Detail modal opens from any row with all required fields
- [ ] Inline hints visible for rows with metadata; neutral empty state for missing
- [ ] Tests green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
