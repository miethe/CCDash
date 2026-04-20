---
type: context
schema_version: 2
doc_type: context
prd: "containerized-deployment-v1"
feature_slug: "containerized-deployment-v1"
prd_ref: docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
title: "Containerized Deployment Infrastructure - Development Context"
status: active
created: 2026-04-20
updated: 2026-04-20
commit_refs: []
pr_refs: []

critical_notes_count: 0
implementation_decisions_count: 4
active_gotchas_count: 0
agent_contributors: []
agents: []

phase_status:
  - phase: 1
    status: not-started
    reason: null
  - phase: 2
    status: not-started
    reason: null
  - phase: 3
    status: not-started
    reason: null
  - phase: 4
    status: not-started
    reason: null
  - phase: 5
    status: not-started
    reason: null
  - phase: 6
    status: not-started
    reason: null
  - phase: 7
    status: not-started
    reason: null

blockers: []
decisions: []
---

# Containerized Deployment Infrastructure - Development Context

**Status**: Active (not started)
**Created**: 2026-04-20
**Last Updated**: 2026-04-20

> Shared worknotes for all agents working on `containerized-deployment-v1`. Add observations, decisions, and gotchas here as execution proceeds.

---

## Feature Summary

Transform CCDash from a three-terminal multi-process setup into a first-class containerized platform. A single unified backend image with entrypoint dispatch on `CCDASH_RUNTIME_PROFILE` replaces separate api/worker Dockerfiles. A hardened frontend nginx image and a `compose.yaml` with `local`, `enterprise`, and `postgres` profiles provide one-command deployment via `docker compose` or `podman-compose`. No config architecture changes — thin wrapper over existing `backend/runtime/` profile dispatch.

---

## Locked Decisions (PRD §2 / §8)

| Decision | Value |
|---|---|
| Backend image strategy | Single image; entrypoint dispatches on `CCDASH_RUNTIME_PROFILE` |
| Frontend image | Separate multi-stage nginx image (Node 22 build + nginx 1.27-alpine runtime) |
| Compose profiles | Three composable profiles: `local`, `enterprise`, `postgres` |
| Docker + Podman parity | Non-root UID/GID build args; named volumes; no Docker-specific extensions; tested on Podman >= 4.6 + podman-compose >= 1.2 |
| SQLite vs Postgres | `local` profile uses SQLite named volume; `enterprise`/`postgres` require Postgres; mismatch fails fast via `StorageProfileConfig.validate_contract()` |
| Data volume | Named volume default for `data/`; bind-mount override documented with `:Z` SELinux label note |
| Registry publication | Manual by maintainers; tagging convention `ghcr.io/ccdash/backend:<version>` documented only |

---

## Phase Summary

| Phase | Title | Progress File | Owners | Status |
|---|---|---|---|---|
| 1 | Backend Dockerfile Consolidation | [phase-1-backend-dockerfile.md](./../progress/containerized-deployment-v1/phase-1-backend-dockerfile.md) | devops-architect, python-backend-engineer | not-started |
| 2 | Frontend Dockerfile Hardening | [phase-2-frontend-dockerfile.md](./../progress/containerized-deployment-v1/phase-2-frontend-dockerfile.md) | devops-architect, python-backend-engineer | not-started |
| 3 | Unified compose.yaml with Profiles | [phase-3-compose-profiles.md](./../progress/containerized-deployment-v1/phase-3-compose-profiles.md) | devops-architect, platform-engineer | not-started |
| 4 | Postgres Profile Wiring | [phase-4-postgres-profile.md](./../progress/containerized-deployment-v1/phase-4-postgres-profile.md) | devops-architect | not-started |
| 5 | Rootless Podman Compatibility | [phase-5-podman-compat.md](./../progress/containerized-deployment-v1/phase-5-podman-compat.md) | devops-architect, platform-engineer | not-started |
| 6 | Documentation Finalization | [phase-6-documentation.md](./../progress/containerized-deployment-v1/phase-6-documentation.md) | documentation-writer, changelog-generator | not-started |
| 7 | Smoke Validation and Rollout | [phase-7-smoke-validation.md](./../progress/containerized-deployment-v1/phase-7-smoke-validation.md) | devops-architect, task-completion-validator | not-started |

---

## Critical Path

Phase 1 → Phase 3 → Phase 4 → Phase 5 → Phase 7

Phase 2 is independent of Phase 1 and can run in parallel. Phase 6 overlaps with Phase 7 start.

---

## References

- **PRD**: `docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md`
- **Existing compose**: `deploy/runtime/compose.hosted.yml`
- **Existing Dockerfiles**: `deploy/runtime/api/Dockerfile`, `deploy/runtime/worker/Dockerfile`, `deploy/runtime/frontend/Dockerfile`
- **Runtime profiles**: `backend/runtime/profiles.py`
- **Env vars**: `backend/config.py`
