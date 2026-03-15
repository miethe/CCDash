---
type: progress
schema_version: 2
doc_type: progress
prd: "sse-live-update-platform-v1"
feature_slug: "sse-live-update-platform-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md
phase: 2
title: "SSE Delivery Endpoint and Runtime Wiring"
status: "pending"
started: "2026-03-14"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["backend-architect", "python-backend-engineer"]
contributors: ["codex"]

tasks:
  - id: "LIVE-101"
    description: "Add GET /api/live/stream with topic subscription input, heartbeat frames, disconnect cleanup, and SSE framing."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["LIVE-003"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "LIVE-102"
    description: "Wire broker/publisher into backend startup without hard-coding transport logic into every router."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["LIVE-003"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "LIVE-103"
    description: "Support replay from recent buffered events where possible and emit snapshot_required when the requested cursor cannot be satisfied."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["LIVE-101"]
    estimated_effort: "3pt"
    priority: "high"

parallelization:
  batch_1: ["LIVE-101", "LIVE-102"]
  batch_2: ["LIVE-103"]
  critical_path: ["LIVE-101", "LIVE-103"]
  estimated_total_time: "9pt / 4 days"

blockers: []

success_criteria:
  - "Stream endpoint returns valid text/event-stream responses with heartbeat frames."
  - "Subscriber cleanup runs on disconnect without leaking broker subscribers."
  - "Runtime container exposes the broker and publisher seam through startup wiring."
  - "Replay requests yield recent buffered events or explicit snapshot_required messages."

files_modified:
  - ".claude/progress/sse-live-update-platform-v1/phase-2-progress.md"
  - "backend/adapters/live_updates/sse_stream.py"
  - "backend/routers/live.py"
  - "backend/runtime/container.py"
  - "backend/runtime/bootstrap.py"
  - "backend/tests/test_live_router.py"
  - "backend/tests/test_runtime_bootstrap.py"

progress: 0
updated: "2026-03-14"
---

# sse-live-update-platform-v1 - Phase 2

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/sse-live-update-platform-v1/phase-2-progress.md --task LIVE-101 --status in_progress
```

## Objective

Expose the broker through a reusable SSE endpoint and runtime wiring that future surface migrations can adopt incrementally.
