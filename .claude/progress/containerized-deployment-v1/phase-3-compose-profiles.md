---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1
feature_slug: containerized-deployment-v1
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
phase: 3
title: Unified compose.yaml with Profiles
status: not_started
created: '2026-04-20'
updated: '2026-04-20'
commit_refs: []
pr_refs: []
owners:
- devops-architect
- platform-engineer
contributors: []
tasks:
- id: COMP-001
  description: Write deploy/runtime/compose.yaml with local/enterprise/postgres profiles;
    backend + frontend services
  status: pending
  assigned_to:
  - devops-architect
  - platform-engineer
  dependencies: []
- id: COMP-002
  description: 'Add healthcheck blocks to backend services (api: /api/health/ready,
    worker: /readyz on 9465)'
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - COMP-001
- id: COMP-003
  description: "Wire depends_on with condition: service_healthy for worker\u2192api\
    \ (enterprise) and api/worker\u2192postgres"
  status: pending
  assigned_to:
  - platform-engineer
  dependencies:
  - COMP-002
- id: COMP-004
  description: Write deploy/runtime/.env.example covering all CCDASH_* vars for all
    three profiles
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - COMP-001
parallelization:
  batch_1:
  - COMP-001
  batch_2:
  - COMP-002
  - COMP-004
  batch_3:
  - COMP-003
  critical_path:
  - COMP-001
  - COMP-002
  - COMP-003
blockers: []
success_criteria: []
---

# containerized-deployment-v1 - Phase 3: Unified compose.yaml with Profiles

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/containerized-deployment-v1/phase-3-compose-profiles.md \
  -t COMP-001 -s completed
```

---

## Objective

Write `deploy/runtime/compose.yaml` as the canonical compose file with three composable profiles (`local`, `enterprise`, `postgres`), replacing `compose.hosted.yml`. Services must include health checks, `depends_on` with conditions, and UID/GID mapping for rootless Podman compatibility.

---

## Task Checklist

- [ ] COMP-001: compose.yaml base structure with three profiles (no deps)
- [ ] COMP-002: Health checks on all backend services (depends: COMP-001)
- [ ] COMP-003: depends_on with condition: service_healthy (depends: COMP-002)
- [ ] COMP-004: .env.example covering all CCDASH_* vars (depends: COMP-001, parallel with COMP-002)

---

## Quality Gates

- [ ] `docker compose config --profiles local,enterprise,postgres -f deploy/runtime/compose.yaml` valid
- [ ] `podman-compose config` passes (or incompatibility noted)
- [ ] `--profile local up --no-start` creates backend + frontend containers
- [ ] `--profile enterprise up --no-start` creates api + worker + frontend
- [ ] `--profile postgres up --no-start` creates postgres + api + worker + frontend
- [ ] All services have health checks or documented absence
- [ ] `.env.example` operator-ready with no baked secrets

---

## Quick Reference

```bash
# Primary subagent: devops-architect + platform-engineer (sonnet)
Task("devops-architect", "Execute Phase 3 of containerized-deployment-v1: \
  write deploy/runtime/compose.yaml with local/enterprise/postgres profiles, \
  health checks, depends_on conditions, and .env.example. \
  Plan: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md \
  Progress: .claude/progress/containerized-deployment-v1/phase-3-compose-profiles.md")
```
