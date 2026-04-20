---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1
feature_slug: containerized-deployment-v1
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
phase: 7
title: Smoke Validation and Rollout
status: not_started
created: '2026-04-20'
updated: '2026-04-20'
commit_refs: []
pr_refs: []
owners:
- devops-architect
- task-completion-validator
contributors: []
tasks:
- id: SMOKE-001
  description: 'AC-1: docker compose --profile local up; UI on :3000, API on :8000,
    /api/health/ready 200 within 30s'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-002
  description: 'AC-2: docker compose --profile enterprise --profile postgres up; all
    four health checks pass'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-003
  description: 'AC-3: docker compose --profile enterprise up with external CCDASH_DATABASE_URL'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-004
  description: 'AC-4: podman-compose --profile local up on rootless Podman 4.6+; same
    result as SMOKE-001'
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - SMOKE-001
- id: SMOKE-005
  description: 'AC-5: docker compose exec api python -m pytest backend/tests/test_runtime_bootstrap
    -v; all profiles pass'
  status: pending
  assigned_to:
  - task-completion-validator
  dependencies:
  - SMOKE-001
  - SMOKE-002
- id: SMOKE-006
  description: 'AC-6: docker compose exec worker curl http://localhost:9465/readyz
    returns 200'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-007
  description: 'AC-7: Bind-mount session logs; verify sync engine parses without permission
    errors'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-008
  description: 'AC-8: CCDASH_DB_BACKEND=sqlite + --profile enterprise fails fast with
    StorageProfileConfig error'
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: SMOKE-009
  description: 'Image size gates: backend < 400 MB, frontend < 50 MB via docker image
    ls'
  status: pending
  assigned_to:
  - task-completion-validator
  dependencies: []
- id: SMOKE-010
  description: 'Operator quickstart validation: follow containerized-deployment-quickstart.md
    from fresh clone'
  status: pending
  assigned_to:
  - task-completion-validator
  dependencies: []
parallelization:
  batch_1:
  - SMOKE-001
  - SMOKE-002
  - SMOKE-003
  - SMOKE-006
  - SMOKE-007
  - SMOKE-008
  - SMOKE-009
  - SMOKE-010
  batch_2:
  - SMOKE-004
  - SMOKE-005
  critical_path:
  - SMOKE-001
  - SMOKE-004
  - SMOKE-005
blockers: []
success_criteria: []
---

# containerized-deployment-v1 - Phase 7: Smoke Validation and Rollout

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/containerized-deployment-v1/phase-7-smoke-validation.md \
  -t SMOKE-001 -s completed
```

---

## Objective

Execute comprehensive smoke validation covering all AC-1 through AC-8 from the PRD. Verify image size constraints, run end-to-end tests of all profiles on Docker and Podman, execute `test_runtime_bootstrap` inside containers, validate health checks, and confirm the operator quickstart works from a clean clone.

---

## Task Checklist

- [ ] SMOKE-001: AC-1 Docker local profile (no deps)
- [ ] SMOKE-002: AC-2 Docker enterprise + postgres (no deps)
- [ ] SMOKE-003: AC-3 Docker enterprise external Postgres (no deps)
- [ ] SMOKE-004: AC-4 Podman rootless local (depends: SMOKE-001)
- [ ] SMOKE-005: AC-5 test_runtime_bootstrap in container (depends: SMOKE-001, SMOKE-002)
- [ ] SMOKE-006: AC-6 Worker /readyz probe (no deps)
- [ ] SMOKE-007: AC-7 Session log bind-mount (no deps)
- [ ] SMOKE-008: AC-8 SQLite + enterprise contract failure (no deps)
- [ ] SMOKE-009: Image size gates backend + frontend (no deps)
- [ ] SMOKE-010: Operator quickstart validation (no deps)

---

## Quality Gates

- [ ] All AC-1 through AC-8 from PRD acceptance criteria pass
- [ ] Backend image < 400 MB, frontend image < 50 MB
- [ ] `test_runtime_bootstrap` passes in all container profiles
- [ ] Health checks respond correctly for all services
- [ ] Operator quickstart validated end-to-end from fresh clone
- [ ] No P0/P1 bugs; any issues documented and patched
- [ ] `compose.yaml` ready for production deployment

---

## Quick Reference

```bash
# Primary subagent: devops-architect + task-completion-validator (sonnet)
Task("devops-architect", "Execute Phase 7 of containerized-deployment-v1: \
  run full smoke validation for AC-1 through AC-8, image size gates, \
  test_runtime_bootstrap in containers, quickstart validation. \
  Plan: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md \
  Progress: .claude/progress/containerized-deployment-v1/phase-7-smoke-validation.md")
```
