---
type: progress
schema_version: 2
doc_type: progress
prd: "agentic-sdlc-intelligence-foundation-v1"
feature_slug: "agentic-sdlc-intelligence-foundation-v1"
prd_ref: /docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
phase: 1
title: "SkillMeat integration contract and definition cache"
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
  - id: "ASI-1"
    description: "Add project-scoped SkillMeat integration settings for enablement, base URL, and project/workspace mapping through the existing project config flow."
    status: "completed"
    assigned_to: ["python-backend-engineer", "backend-architect"]
    dependencies: []
    estimated_effort: "2pt"
    priority: "high"

  - id: "ASI-2"
    description: "Implement a read-only SkillMeat client for artifacts, workflows, and context modules with timeout handling, graceful degradation, and normalized DTO output."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-1"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-3"
    description: "Add SQLite/Postgres cache tables and repository support for external definition sources and cached definitions with upsert/list/get operations."
    status: "completed"
    assigned_to: ["data-layer-expert", "backend-architect"]
    dependencies: ["ASI-1"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "ASI-4"
    description: "Add an on-demand sync service and API for SkillMeat definitions that returns counts, timestamps, and non-fatal warnings."
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["ASI-2", "ASI-3"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["ASI-1"]
  batch_2: ["ASI-2", "ASI-3"]
  batch_3: ["ASI-4"]
  critical_path: ["ASI-1", "ASI-2", "ASI-4"]
  estimated_total_time: "10pt / ~1 week"

blockers: []

success_criteria:
  - "Project SkillMeat settings persist and round-trip through the project configuration flow."
  - "SkillMeat client fetches artifacts, workflows, and context modules into normalized DTOs."
  - "SQLite and Postgres migration paths create external definition source and cache tables in parity."
  - "Definition sync stores provenance, version, and raw snapshots without crashing when SkillMeat is unavailable."

files_modified:
  - "backend/models.py"
  - "backend/db/sqlite_migrations.py"
  - "backend/db/postgres_migrations.py"
  - "backend/db/repositories/base.py"
  - "backend/db/repositories/intelligence.py"
  - "backend/db/repositories/postgres/intelligence.py"
  - "backend/db/factory.py"
  - "backend/services/integrations/skillmeat_client.py"
  - "backend/services/integrations/skillmeat_sync.py"
  - "backend/routers/integrations.py"
  - "backend/main.py"
  - "backend/tests/test_skillmeat_client.py"
  - "backend/tests/test_intelligence_repository.py"
  - "backend/tests/test_integrations_router.py"
  - "types.ts"
  - "components/Settings.tsx"
---

# agentic-sdlc-intelligence-foundation-v1 - Phase 1

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/agentic-sdlc-intelligence-foundation-v1/phase-1-progress.md -t ASI-X -s completed
```

## Completion Notes

- Project settings now expose `skillMeat` enablement, base URL, project mapping, workspace mapping, and timeout values.
- SQLite/Postgres now persist external definition sources, cached definitions, stack observations, and stack components.
- SkillMeat sync and cache listing endpoints are available under `/api/integrations/skillmeat/*`.
