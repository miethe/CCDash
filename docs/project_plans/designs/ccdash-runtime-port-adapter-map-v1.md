---
doc_type: design_spec
status: completed
category: refactors

title: "Design Spec: CCDash Runtime Port/Adapter Map V1"
description: "Reference map for runtime profiles, ownership boundaries, and migrated frontend/backend seams after the hexagonal foundation refactor."
author: codex
audience: [ai-agents, developers, platform-engineering]
created: 2026-03-13
updated: 2026-03-13

tags: [design, refactor, runtime, ports-adapters, hexagonal]
feature_slug: ccdash-hexagonal-foundation-v1
feature_family: ccdash-platform-foundation
lineage_family: ccdash-platform-foundation
lineage_parent: "docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md"
lineage_children: []
linked_features: []
related:
  - "docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md"
  - "docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md"
  - "docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md"
  - "docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md"
owner: platform-engineering
owners: [platform-engineering]
contributors: [codex]
---

## Runtime profiles

| Profile | HTTP | Startup sync | Watcher | Scheduled jobs | Integrations |
| --- | --- | --- | --- | --- | --- |
| `local` | Yes | Yes | Yes | Yes | Yes |
| `api` | Yes | No | No | No | Yes |
| `worker` | No | Yes | No | Yes | Yes |
| `test` | Yes | No | No | No | No |

## Backend ownership map

### Composition shell

- `backend/runtime/bootstrap.py` builds the FastAPI app, registers routers, and exposes runtime health.
- `backend/runtime/container.py` owns runtime-scoped composition only: DB connection, storage ports, request context construction, and lifecycle delegation.

### Runtime-managed adapters

- `backend/adapters/jobs/runtime.py` owns startup sync, analytics snapshot scheduling, SkillMeat refresh-on-startup, and optional file watching.
- `backend/adapters/jobs/local.py` remains the in-process scheduler primitive used by local, worker, and test profiles.
- `backend/worker.py` is the non-HTTP worker entrypoint for background-only execution.

### Application service boundary

- `backend/routers/execution.py` and `backend/routers/integrations.py` now map HTTP requests/responses only for migrated flows.
- `backend/application/services/execution.py` owns execution policy, run lifecycle, approval, cancel, and retry behavior.
- `backend/application/services/integrations.py` owns SkillMeat sync, refresh, definition listing, and observation backfill/listing behavior.

## Frontend ownership map

### Session/project boundary

- `contexts/AppSessionContext.tsx` owns configured projects, active project resolution, and project mutation flows.

### Entity/data boundary

- `contexts/AppEntityDataContext.tsx` owns sessions, documents, tasks, alerts, notifications, features, and mutation helpers.

### Runtime shell boundary

- `contexts/AppRuntimeContext.tsx` owns app-shell loading state, polling, runtime health, and full refresh orchestration.
- `services/runtimeProfile.ts` normalizes `/api/health` into a frontend-friendly runtime-status shape.

### Data-access boundary

- `services/apiClient.ts` is the typed fetch layer for app-shell data loading and mutations.
- `contexts/DataClientContext.tsx` injects the client so React providers do not call `fetch` directly.
- `contexts/DataContext.tsx` remains a compatibility facade that composes providers and exposes `useData()`.

## Guardrails

- Backend architecture test: `backend/tests/test_architecture_boundaries.py`
  Protects migrated routers from direct `backend.db.connection` and `backend.db.factory` imports.
- Frontend architecture test: `contexts/__tests__/dataArchitecture.test.ts`
  Protects `contexts/DataContext.tsx` from regressing into a fetch-owning monolith.

## Follow-on dependency points

### Shared auth / RBAC / SSO

- Extend `IdentityProvider` and `AuthorizationPolicy` implementations without changing router signatures.
- Feed authenticated principal/session state into `AppSessionContext.tsx` rather than reintroducing shell-wide implicit state.

### Hosted deployment modularization

- Deploy `backend.runtime.bootstrap_api:app` as the stateless hosted API profile.
- Deploy `python -m backend.worker` separately for background sync/refresh/scheduled jobs.
- Keep `backend.main:app` as the local-convenience entrypoint only; it is not a hosted API bootstrap.

### Data platform modularization

- Replace `FactoryStorageUnitOfWork` behind `CorePorts.storage` without rewriting migrated router code.
- Continue moving remaining router flows onto `backend/application/services/*` before tightening the router guardrail allowlist further.
