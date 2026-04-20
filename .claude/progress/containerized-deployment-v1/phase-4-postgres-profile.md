---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1
feature_slug: containerized-deployment-v1
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
phase: 4
title: Postgres Profile Wiring
status: not_started
created: '2026-04-20'
updated: '2026-04-20'
commit_refs: []
pr_refs: []
owners:
- devops-architect
contributors: []
tasks:
- id: PG-001
  description: Add postgres:17-alpine service to compose.yaml under --profile postgres
    with named volume and pg_isready health check
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - COMP-001
- id: PG-002
  description: 'Verify api + worker have depends_on: postgres: condition: service_healthy
    in postgres profile'
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - PG-001
  - COMP-003
- id: PG-003
  description: Run docker compose --profile postgres up smoke test; verify all health
    checks pass and database accessible
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - PG-001
  - PG-002
parallelization:
  batch_1:
  - PG-001
  batch_2:
  - PG-002
  batch_3:
  - PG-003
  critical_path:
  - PG-001
  - PG-002
  - PG-003
blockers: []
success_criteria: []
---

# containerized-deployment-v1 - Phase 4: Postgres Profile Wiring

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/containerized-deployment-v1/phase-4-postgres-profile.md \
  -t PG-001 -s completed
```

---

## Objective

Wire the `postgres:17-alpine` service into the `--profile postgres` compose profile with a named volume (`ccdash-postgres`), `pg_isready` health check, and `CCDASH_POSTGRES_*` credential env vars. Verify api runs migrations before becoming healthy so the worker's `depends_on: api: condition: service_healthy` is safe.

---

## Task Checklist

- [ ] PG-001: postgres service definition in compose.yaml (depends: COMP-001 from Phase 3)
- [ ] PG-002: depends_on ordering for api + worker (depends: PG-001, COMP-003)
- [ ] PG-003: Smoke test — postgres profile all services healthy (depends: PG-001, PG-002)

---

## Quality Gates

- [ ] Postgres service defined with correct image, environment, and named volume
- [ ] Health check `pg_isready` returns success within 30 s
- [ ] api + worker depend on postgres with health condition
- [ ] Named volume `ccdash-postgres` created and mapped correctly
- [ ] Smoke test passes: all services healthy, database accessible from both containers

---

## Quick Reference

```bash
# Primary subagent: devops-architect (sonnet)
Task("devops-architect", "Execute Phase 4 of containerized-deployment-v1: \
  wire postgres:17-alpine service into --profile postgres with named volume, \
  health check, and depends_on ordering. Run smoke test. \
  Plan: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md \
  Progress: .claude/progress/containerized-deployment-v1/phase-4-postgres-profile.md")
```
