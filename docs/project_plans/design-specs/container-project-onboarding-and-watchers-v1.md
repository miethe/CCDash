---
title: "Design Spec: Container Project Onboarding And Watcher Binding V1"
schema_version: 2
doc_type: design_doc
status: proposed
created: 2026-05-05
updated: 2026-05-05
feature_slug: container-project-onboarding-and-watchers-v1
feature_version: v1
prd_ref: /docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: /docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
related_documents:
  - docs/guides/containerized-deployment-quickstart.md
  - deploy/runtime/README.md
  - deploy/runtime/compose.yaml
  - components/AddProjectModal.tsx
  - components/Settings.tsx
  - backend/routers/projects.py
  - backend/scripts/container_project_onboarding.py
owner: null
contributors: []
priority: high
risk_level: medium
category: infrastructure
tags: [design-spec, containers, projects, watcher, onboarding]
---

# Design Spec: Container Project Onboarding And Watcher Binding V1

## Problem

Containerized CCDash now has a solid runtime contract, but project onboarding still mixes three different concepts:

- registry creation in `projects.json`
- active or request-scoped project selection in the UI/API/CLI
- watcher deployment binding through `CCDASH_WORKER_WATCH_PROJECT_ID`

In v1, `worker-watch` is one-project-per-process. A container binds its project at startup and does not follow UI project switching. The enterprise compose path also mounts `projects.json` read-only, so in-app project creation cannot be the only supported onboarding path for deployed instances.

## Current Architecture Facts

- `POST /api/projects` persists to the workspace registry file.
- `POST /api/projects/active/{project_id}` changes local active project state, but hosted requests use explicit project selection.
- `worker-watch` maps `CCDASH_WORKER_WATCH_PROJECT_ID` into the runtime project binding env and resolves exactly one project during startup.
- The watcher watches paths derived from the selected project's resolved root, sessions, plan docs, progress, and enabled test-result sources.
- The standalone CLI `--project` and `ccdash target add --project` are query scoping controls, not server project creation or watcher deployment controls.

## V1 UX Requirements

1. Project Settings must expose the stable project id and resolved watch paths.
2. Project Settings must generate a copyable watcher env overlay for the selected project.
3. Add Project success should route users toward path validation, manual sync, and watcher env generation.
4. The UI must label watcher changes as requiring a container restart or a new watcher service.
5. The docs and CCDash skill must distinguish registry creation, project selection, and watcher binding.
6. CLI or skill automation may generate deployment inputs, but must not imply it can remotely start or rebind watcher containers.

## Recommended Flow

1. Operator or agent prepares `projects.json` with `backend/scripts/container_project_onboarding.py`.
2. Operator starts API, worker, and frontend with `enterprise` plus `postgres`.
3. Operator starts one `worker-watch` per project that needs live ingest.
4. User opens Project Settings to validate resolved paths and copy watcher env values when adding another project.
5. Validation checks include `/api/projects/active`, feature/session surface probes, and watcher `/detailz`.

## Deferred Product Work

- A first-class "Add Project" wizard that includes path source selection, session root discovery, and post-save actions.
- A deployment-aware server endpoint that can report whether the registry is writable.
- A `ccdash runtime watcher-env --project <id>` standalone CLI helper that prints overlays without mutating server state.
- Managed watcher orchestration for hosted deployments. This requires an explicit supervisor/backend contract and is outside current compose-only examples.

## Non-Goals

- Dynamically scaling `worker-watch` through the browser.
- Rebinding an existing watcher container when the UI active project changes.
- Treating CLI target project defaults as server registry records.
- Writing to read-only enterprise registry mounts from the API.

## Acceptance Criteria

- Operators can create a project registry entry and watcher env overlay from a documented command.
- Project Settings shows the selected project id and the env keys needed for watcher binding.
- Docs state that one watcher process binds one project in v1.
- Skill guidance routes agents to project-registry preparation before watcher startup.
