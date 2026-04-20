---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1
feature_slug: containerized-deployment-v1
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
phase: 5
title: Rootless Podman Compatibility
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
- id: PODMAN-001
  description: Test BUILD_UID/BUILD_GID build args for backend and frontend images
    on rootless Podman 4.6+
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
- id: PODMAN-002
  description: Test named volumes accessible from UID 1000 containers; document SELinux
    label issues
  status: pending
  assigned_to:
  - devops-architect
  dependencies:
  - PODMAN-001
- id: PODMAN-003
  description: Document :Z bind-mount label syntax; test with sample projects.json
    on SELinux host
  status: pending
  assigned_to:
  - platform-engineer
  dependencies:
  - PODMAN-001
- id: PODMAN-004
  description: Run podman-compose config for all profiles; validate depends_on condition
    syntax support
  status: pending
  assigned_to:
  - devops-architect
  dependencies: []
parallelization:
  batch_1:
  - PODMAN-001
  - PODMAN-004
  batch_2:
  - PODMAN-002
  - PODMAN-003
  critical_path:
  - PODMAN-001
  - PODMAN-002
blockers: []
success_criteria: []
---

# containerized-deployment-v1 - Phase 5: Rootless Podman Compatibility

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/containerized-deployment-v1/phase-5-podman-compat.md \
  -t PODMAN-001 -s completed
```

---

## Objective

Validate the full container stack on rootless Podman >= 4.6 with podman-compose >= 1.2. Test UID/GID build args, named volume UID mapping, and SELinux `:Z` bind-mount relabeling. Document any `docker compose` vs `podman-compose` differences and provide overrides where needed.

---

## Task Checklist

- [ ] PODMAN-001: UID/GID build arg validation on rootless Podman (no deps)
- [ ] PODMAN-002: Named volume UID mapping test (depends: PODMAN-001)
- [ ] PODMAN-003: Bind-mount SELinux :Z documentation and test (depends: PODMAN-001)
- [ ] PODMAN-004: podman-compose syntax validation for all profiles (no deps — parallel with PODMAN-001)

---

## Quality Gates

- [ ] `podman build --build-arg BUILD_UID=1000 --build-arg BUILD_GID=1000` succeeds for backend + frontend
- [ ] `podman run --rm ccdash-backend:local id` returns UID 1000
- [ ] `podman-compose --profile local up` starts containers on rootless Podman 4.6+
- [ ] Health checks pass with podman-compose
- [ ] Named volumes accessible without permission errors
- [ ] Bind-mount `:Z` label documented for operators
- [ ] Any compose.yaml incompatibilities documented or overridden

---

## Quick Reference

```bash
# Primary subagent: devops-architect + platform-engineer (sonnet)
Task("devops-architect", "Execute Phase 5 of containerized-deployment-v1: \
  validate rootless Podman compatibility — UID/GID build args, named volumes, \
  SELinux :Z bind-mount labeling, podman-compose syntax. \
  Plan: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md \
  Progress: .claude/progress/containerized-deployment-v1/phase-5-podman-compat.md")
```
