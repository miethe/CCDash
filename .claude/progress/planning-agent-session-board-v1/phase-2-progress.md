---
type: progress
schema_version: 2
doc_type: progress
prd: planning-agent-session-board-v1
feature_slug: planning-agent-session-board-v1
phase: 2
phase_title: Rich Board UI and Card Components
status: in_progress
created: '2026-04-25'
updated: '2026-04-25'
prd_ref: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: '2026-04-28'
ui_touched: true
owners:
- fullstack-engineering
contributors:
- ai-agents
tasks:
- id: PASB-201
  title: Board Shell
  description: Add grouped board layout with toolbar controls for grouping and filters.
  status: in_progress
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-104
  acceptance_criteria:
  - Board can switch grouping without layout jumps and handles loading, empty, and
    error states.
  estimate: 2 pts
- id: PASB-202
  title: Session Card
  description: Implement card with agent, session, model, feature, phase/task, state,
    time, token/context summaries, activity marker, and fixed-size live regions.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-201
  acceptance_criteria:
  - Card is readable at compact density, avoids layout jumps, and has accessible labels
    for primary links.
  estimate: 2 pts
- id: PASB-203
  title: Planning Links
  description: Add card actions for transcript, feature planning context, phase operations,
    and parent/root session.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - PASB-202
  acceptance_criteria:
  - All links route to existing surfaces and are hidden or disabled when unavailable.
  estimate: 2 pts
- id: PASB-204
  title: Live Refresh Integration
  description: Reuse existing data/live/cache mechanisms so active session state refreshes
    predictably.
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - PASB-201
  acceptance_criteria:
  - Board updates after session/planning changes without manual reload in normal active
    flows.
  estimate: 2 pts
- id: PASB-205
  title: Motion and Reduced Motion
  description: Add subtle live-state animation, animated state transitions, and reduced-motion
    fallbacks.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-202
  acceptance_criteria:
  - Running/thinking cards communicate live state without expensive layout work; reduced-motion
    users receive static indicators.
  estimate: 2 pts
- id: PASB-206
  title: Relationship Highlighting
  description: Highlight parent/root/sibling sessions and linked planning entities
    on hover, focus, and selection.
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies:
  - PASB-103
  - PASB-202
  acceptance_criteria:
  - Related cards and planning refs are visually connected, while weak relationships
    use lower-confidence styling.
  estimate: 2 pts
parallelization:
  batch_1:
  - PASB-201
  batch_2:
  - PASB-202
  - PASB-204
  batch_3:
  - PASB-203
  - PASB-205
  - PASB-206
total_tasks: 6
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
progress: 0
---
