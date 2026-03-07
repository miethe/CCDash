---
type: progress
schema_version: 2
doc_type: progress
prd: "agentic-sdlc-intelligence-foundation-v1"
feature_slug: "agentic-sdlc-intelligence-foundation-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
phase: 2
title: "Observed stack extraction and resolution"
status: "completed"
started: "2026-03-07"
completed: "2026-03-07"
commit_refs: ["1d75483"]
pr_refs: []

overall_progress: 100
completion_estimate: "completed"

total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer", "backend-architect", "data-layer-expert"]
contributors: ["codex"]

tasks:
  - id: "ASI-5"
    description: "Add schema and repository support for stack observations and stack components."
    status: "completed"
    assigned_to: ["data-layer-expert", "python-backend-engineer"]
    dependencies: []
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-6"
    description: "Build a session evidence extractor over sessions, artifacts, commands, badges, and forensics to emit candidate stack observations."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-5"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-7"
    description: "Match observed stack components to cached SkillMeat definitions using deterministic resolution rules and source attribution."
    status: "completed"
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["ASI-5", "ASI-6"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-8"
    description: "Add a project-scoped backfill path that computes session stack observations without requiring a full external definition re-sync."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-6", "ASI-7"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["ASI-5"]
  batch_2: ["ASI-6"]
  batch_3: ["ASI-7"]
  batch_4: ["ASI-8"]
  critical_path: ["ASI-5", "ASI-6", "ASI-7", "ASI-8"]
  estimated_total_time: "11pt / ~1 week"

blockers: []

success_criteria:
  - "Session observations store explicit, inferred, and resolved stack components."
  - "Historical sessions produce evidence-backed observations with confidence and forensics context."
  - "Resolver deterministically marks components as resolved or unresolved with source attribution."
  - "Backfill can process existing project sessions without re-syncing external definitions."

files_modified:
  - "backend/models.py"
  - "backend/db/sqlite_migrations.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/repositories/base.py"
  - "backend/db/repositories/intelligence.py"
  - "backend/db/repositories/postgres/intelligence.py"
  - "backend/services/integrations/skillmeat_resolver.py"
  - "backend/services/stack_observations.py"
  - "backend/routers/integrations.py"
  - "backend/tests/test_stack_observations.py"
  - "backend/tests/test_integrations_router.py"
---

# agentic-sdlc-intelligence-foundation-v1 - Phase 2

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/agentic-sdlc-intelligence-foundation-v1/phase-2-progress.md -t ASI-X -s completed
```

## Completion Notes

- Historical sessions can now be backfilled into stack observations without re-syncing SkillMeat definitions.
- Observation extraction uses session badges, commands, artifacts, and session forensics.
- Deterministic resolution maps artifact, workflow, and context-module candidates to cached SkillMeat definitions when exact evidence exists.
