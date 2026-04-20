---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1
feature_slug: containerized-deployment-v1
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
phase: 1
title: Backend Dockerfile Consolidation
status: not_started
created: '2026-04-20'
updated: '2026-04-20'
commit_refs: []
pr_refs: []
owners:
- devops-architect
- python-backend-engineer
contributors: []
tasks:
- id: BE-001
  description: Create deploy/runtime/Dockerfile as multi-stage Python 3.12-slim image
    consolidating api + worker Dockerfiles
  status: pending
  assigned_to:
  - devops-architect
  - python-backend-engineer
  dependencies: []
- id: BE-002
  description: Write deploy/runtime/entrypoint.sh to dispatch on CCDASH_RUNTIME_PROFILE
    (local/api/worker)
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-001
- id: BE-003
  description: Add BUILD_UID and BUILD_GID build args (default 1000:1000) to Dockerfile;
    verify non-root UID
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - BE-001
- id: BE-004
  description: Execute backend.tests.test_runtime_bootstrap inside container for all
    three profiles
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - BE-002
  - BE-003
parallelization:
  batch_1:
  - BE-001
  batch_2:
  - BE-002
  - BE-003
  batch_3:
  - BE-004
  critical_path:
  - BE-001
  - BE-002
  - BE-004
blockers: []
success_criteria: []
---

# containerized-deployment-v1 - Phase 1: Backend Dockerfile Consolidation

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/containerized-deployment-v1/phase-1-backend-dockerfile.md \
  -t BE-001 -s completed
```

---

## Objective

Consolidate `deploy/runtime/api/Dockerfile` and `deploy/runtime/worker/Dockerfile` into a single `deploy/runtime/Dockerfile` with an entrypoint script that dispatches on `CCDASH_RUNTIME_PROFILE`. Image must run as non-root UID 1000 by default and be < 400 MB compressed.

---

## Task Checklist

- [ ] BE-001: Unified multi-stage Dockerfile (no deps)
- [ ] BE-002: entrypoint.sh dispatch script (depends: BE-001)
- [ ] BE-003: BUILD_UID/BUILD_GID build args (depends: BE-001)
- [ ] BE-004: Runtime bootstrap testing in container (depends: BE-002, BE-003)

---

## Quality Gates

- [ ] `docker build -t ccdash-backend:test deploy/runtime/` succeeds
- [ ] `docker run --rm ccdash-backend:test id` shows UID 1000
- [ ] entrypoint dispatches correctly for `local`, `api`, `worker` profiles
- [ ] `backend.tests.test_runtime_bootstrap` passes inside container for all three profiles
- [ ] Image size < 400 MB (verify via `docker image ls`)
- [ ] `docker history --no-trunc ccdash-backend:test | grep -i secret` returns nothing

---

## Quick Reference

```bash
# Primary subagent: devops-architect + python-backend-engineer (sonnet)
Task("devops-architect", "Execute Phase 1 of containerized-deployment-v1: \
  create deploy/runtime/Dockerfile consolidating api+worker, add entrypoint.sh \
  dispatch on CCDASH_RUNTIME_PROFILE, add BUILD_UID/BUILD_GID args. \
  Plan: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md \
  Progress: .claude/progress/containerized-deployment-v1/phase-1-backend-dockerfile.md")
```
