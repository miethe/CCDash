---
type: progress
schema_version: 2
doc_type: progress
prd: "runtime-performance-hardening-v1"
feature_slug: "runtime-performance-hardening"
phase: 1
phase_title: "Frontend Memory Hardening"
title: "runtime-performance-hardening-v1 - Phase 1: Frontend Memory Hardening"
status: planning
started: null
completed: null
created: 2026-04-20
updated: 2026-04-20
prd_ref: "docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md"
plan_ref: "docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md"
commit_refs: []
pr_refs: []
execution_model: batch-parallel
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["react-performance-optimizer", "ui-engineer-enhanced", "frontend-developer"]
contributors: []
model_usage:
  primary: "sonnet"
  external: []
tasks:
  - id: "FE-101"
    description: "Cap session.logs to 5000 rows; emit transcriptTruncated marker on drop"
    status: "pending"
    assigned_to: ["react-performance-optimizer", "ui-engineer-enhanced"]
    dependencies: []
    estimated_effort: "3 pts"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-102"
    description: "Add react-virtual to log list rendering; reduce DOM node count"
    status: "pending"
    assigned_to: ["frontend-developer", "ui-engineer-enhanced"]
    dependencies: ["FE-101"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-103"
    description: "Introduce MAX_DOCUMENTS_IN_MEMORY (2000); lazy-load beyond cap"
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: []
    estimated_effort: "3 pts"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-104"
    description: "Teardown setInterval and EventSource after N=3 consecutive unreachable checks"
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: []
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-105"
    description: "Clear entries on rejection; add 30s TTL to sessionDetailRequestsRef; GC on insert"
    status: "pending"
    assigned_to: ["react-performance-optimizer"]
    dependencies: []
    estimated_effort: "2 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-106"
    description: "Gate all changes behind VITE_CCDASH_MEMORY_GUARD_ENABLED feature flag (default true)"
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["FE-101", "FE-102", "FE-103", "FE-104", "FE-105"]
    estimated_effort: "1 pt"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "FE-107"
    description: "Create test harness for 60-min idle + worker running memory profile"
    status: "pending"
    assigned_to: ["react-performance-optimizer", "frontend-developer"]
    dependencies: ["FE-101", "FE-102", "FE-103", "FE-104", "FE-105", "FE-106"]
    estimated_effort: "2 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "adaptive"

parallelization:
  batch_1: ["FE-101", "FE-103", "FE-104", "FE-105"]
  batch_2: ["FE-102"]
  batch_3: ["FE-106"]
  batch_4: ["FE-107"]
  critical_path: ["FE-101", "FE-102", "FE-106", "FE-107"]
  estimated_total_time: "5-6 days"

blockers: []

success_criteria:
  - { id: "SC-1", description: "Transcript truncation marker appears in UI; log array capped at 5000 rows", status: "pending" }
  - { id: "SC-2", description: "Virtual list rendering reduces DOM nodes; no memory spike from large logs", status: "pending" }
  - { id: "SC-3", description: "Document array capped at 2000; lazy-load verified on scroll", status: "pending" }
  - { id: "SC-4", description: "Polling stops after 3 unreachable checks; banner visible and persistent", status: "pending" }
  - { id: "SC-5", description: "sessionDetailRequestsRef entries cleared on error; no memory growth after network failures", status: "pending" }
  - { id: "SC-6", description: "Feature flag disables all memory hardening without breaking existing behavior", status: "pending" }
  - { id: "SC-7", description: "Load-test harness runs successfully; baseline metrics captured", status: "pending" }

files_modified: []
---

# runtime-performance-hardening-v1 - Phase 1: Frontend Memory Hardening

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/runtime-performance-hardening-v1/phase-1-progress.md \
  -t FE-101 -s completed
```

---

## Objective

Implement frontend memory hardening to prevent tab memory growth beyond 2GB+ during sustained operation. Delivers transcript ring-buffer cap, virtual list rendering, document pagination cap, polling lifecycle teardown, and in-flight request GC — all gated behind a feature flag.

---

## Task Breakdown

| Task ID | Task Name | Subagent(s) | Model | Est. | Dependencies | Status |
|---------|-----------|-------------|-------|------|--------------|--------|
| FE-101 | Transcript ring-buffer cap | react-performance-optimizer, ui-engineer-enhanced | sonnet | 3 pts | None | pending |
| FE-102 | Session log virtualization | frontend-developer, ui-engineer-enhanced | sonnet | 2 pts | FE-101 | pending |
| FE-103 | Document pagination cap | frontend-developer | sonnet | 3 pts | None | pending |
| FE-104 | Polling lifecycle teardown | frontend-developer | sonnet | 2 pts | None | pending |
| FE-105 | In-flight request GC | react-performance-optimizer | sonnet | 2 pts | None | pending |
| FE-106 | Memory guard feature flag | frontend-developer | sonnet | 1 pt | FE-101, FE-102, FE-103, FE-104, FE-105 | pending |
| FE-107 | Load-test harness setup (frontend) | react-performance-optimizer, frontend-developer | sonnet | 2 pts | FE-101 through FE-106 | pending |

---

## Orchestration Quick Reference

Ready-to-paste Task() delegation commands per task:

**Batch 1 (parallel):**
```
Task(subagent="react-performance-optimizer", prompt="Implement FE-101: Cap session.logs to 5000 rows in SessionInspector.tsx / sessionTranscriptLive.ts. Emit transcriptTruncated marker when rows are dropped. Ring buffer must drop oldest rows. Render 'older messages hidden' marker in UI. Gate behind VITE_CCDASH_MEMORY_GUARD_ENABLED (implement flag skeleton even if wiring comes in FE-106). Acceptance: ring buffer drops oldest rows; marker rendered in UI.")
Task(subagent="frontend-developer", prompt="Implement FE-103: Introduce MAX_DOCUMENTS_IN_MEMORY = 2000 constant in AppEntityDataContext.tsx. Loop stops at 2000; subsequent pages fetch on scroll/filter. No unbounded pagination. Acceptance: document array capped at 2000; lazy-load verified on scroll.")
Task(subagent="frontend-developer", prompt="Implement FE-104: Add polling lifecycle teardown to AppRuntimeContext.tsx. Teardown setInterval and EventSource after N=3 consecutive unreachable checks. Show 'backend disconnected' persistent banner. Provide manual retry button. Acceptance: polling stopped after 3 failures; banner shown; retry works.")
Task(subagent="react-performance-optimizer", prompt="Implement FE-105: Clear sessionDetailRequestsRef entries on rejection in apiClient.ts. Add 30s TTL to entries; GC stale entries on insert. Map size must be bounded. Acceptance: no growth after network failures; memory does not leak.")
```

**Batch 2 (after FE-101):**
```
Task(subagent="frontend-developer", prompt="Implement FE-102: Add react-virtual (or @tanstack/react-virtual) to session log list rendering in SessionInspector.tsx. Verify react-virtual compatibility with React 19 before merging. DOM node count must be constant; virtualization reduces memory footprint of large logs. Acceptance: DOM node count constant; virtualization reduces memory footprint.")
```

**Batch 3 (after FE-101 through FE-105):**
```
Task(subagent="frontend-developer", prompt="Implement FE-106: Gate all Phase 1 changes (FE-101 through FE-105) behind VITE_CCDASH_MEMORY_GUARD_ENABLED feature flag defaulting to true. Flag disabled must restore original behavior. Acceptance: flag disabled → original behavior; flag enabled → all memory hardening active.")
```

**Batch 4 (after FE-106):**
```
Task(subagent="react-performance-optimizer", prompt="Implement FE-107: Create load-test harness for 60-min idle + worker running memory profile. Harness measures tab memory at 1-min intervals using browser performance APIs. Export results as JSON. Acceptance: harness runs successfully; baseline metrics captured.")
```

---

## Quality Gates

- [ ] FE-101: Transcript truncation marker appears in UI; log array capped at 5000 rows
- [ ] FE-102: Virtual list rendering reduces DOM nodes; no memory spike from large logs
- [ ] FE-103: Document array capped at 2000; lazy-load verified on scroll
- [ ] FE-104: Polling stops after 3 unreachable checks; banner visible and persistent
- [ ] FE-105: `sessionDetailRequestsRef` entries cleared on error; no memory growth after network failures
- [ ] FE-106: Feature flag disables all memory hardening without breaking existing behavior
- [ ] FE-107: Load-test harness runs successfully; baseline metrics captured

---

## Blockers

None.

---

## Notes

- FE-102 depends on react-virtual React 19 compatibility; verify in feature branch before merging. Fallback: CSS-overflow with DOM cap.
- FE-104 polling teardown events feed OBS-402 counter in Phase 4.
- FE-107 harness output feeds TEST-508 in Phase 5.
- All Phase 1 tasks are independent of Phases 2-4 and can run in full parallel with those phases.

---

## Completion Notes

_(Fill in when phase is complete)_
