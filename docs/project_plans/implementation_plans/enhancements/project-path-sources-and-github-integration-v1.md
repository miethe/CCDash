---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
status: completed
category: enhancements
title: 'Implementation Plan: Project Path Sources and GitHub Integration V1'
description: Implement typed path references, managed GitHub repo workspaces, and
  a dedicated Integrations settings surface.
summary: Refactor project path handling behind a resolver/provider layer, add GitHub
  integration services, migrate the Settings UI, and optionally enable plan-document
  write-back.
created: 2026-03-12
updated: '2026-04-07'
commit_refs:
- https://github.com/miethe/CCDash/commit/180c52f
- https://github.com/miethe/CCDash/commit/10e3a75
- https://github.com/miethe/CCDash/commit/5aa509b
pr_refs: []
priority: high
risk_level: high
complexity: High
track: Settings / Integrations
timeline_estimate: 3-5 weeks across 7 phases
feature_slug: project-path-sources-and-github-integration-v1
feature_family: project-configuration-and-integrations
feature_version: v1
lineage_family: project-configuration-and-integrations
lineage_parent: null
lineage_children: []
lineage_type: enhancement
owner: fullstack-engineering
owners:
- fullstack-engineering
- platform-engineering
- integrations
contributors:
- ai-agents
audience:
- ai-agents
- developers
- engineering-leads
tags:
- implementation
- settings
- github
- integrations
- repositories
- project-paths
prd: docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
related:
- backend/models.py
- backend/project_manager.py
- backend/routers/projects.py
- backend/routers/integrations.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- components/Settings.tsx
- components/AddProjectModal.tsx
- contexts/DataContext.tsx
- types.ts
plan_ref: project-path-sources-and-github-integration-v1
linked_sessions: []
---

# Implementation Plan: Project Path Sources and GitHub Integration V1

## Objective

Replace the current string-based single-root path model with a typed path-reference system that can resolve from project root, GitHub, or the local filesystem, while introducing a dedicated Integrations settings area for SkillMeat and GitHub.

## Current Baseline

1. `backend/models.py` defines `Project` with:
   - `path`
   - `planDocsPath`
   - `sessionsPath`
   - `progressPath`
   - `skillMeat`
2. `backend/project_manager.py` derives active paths directly from those strings.
3. `components/Settings.tsx` renders directory path inputs and embeds SkillMeat configuration inline in the Projects tab.
4. `backend/routers/integrations.py` only exposes SkillMeat-specific endpoints under `/api/integrations/skillmeat`.
5. Filesystem consumers assume a concrete local path by the time they execute.

## Fixed Decisions

1. GitHub-backed paths will resolve through managed local workspaces in V1.
2. The storage model will use typed path references, even if the UI accepts URL-like shortcuts.
3. GitHub credentials will be integration-scoped, not embedded inside `Project`.
4. Read support ships before write support.
5. V1 write support is limited to plan documents and remains explicitly opt-in.
6. SkillMeat remains project-scoped configuration, but its editor moves into the new Integrations tab.

## Target Architecture

### 1. Project path model

Introduce a typed model for path-backed fields.

Recommended backend/frontend types:

1. `PathSourceKind = "project_root" | "github_repo" | "filesystem"`
2. `ProjectPathField = "root" | "plan_docs" | "sessions" | "progress"`
3. `GitRepoRef`
   - `provider`
   - `repoUrl`
   - `repoSlug`
   - `branch`
   - `repoSubpath`
   - `writeEnabled`
4. `ProjectPathReference`
   - `field`
   - `sourceKind`
   - `displayValue`
   - `filesystemPath`
   - `relativePath`
   - `repoRef`
5. `ProjectPathConfig`
   - `root`
   - `planDocs`
   - `sessions`
   - `progress`

Backward compatibility:

1. Keep legacy fields readable during migration.
2. Derive legacy effective values from the new structure until all consumers are migrated.
3. Add a one-time migration path for existing `projects.json` data.

### 2. Path resolution layer

Create a new backend service boundary, for example:

1. `backend/services/project_paths/models.py`
2. `backend/services/project_paths/resolver.py`
3. `backend/services/project_paths/providers/base.py`
4. `backend/services/project_paths/providers/filesystem.py`
5. `backend/services/project_paths/providers/github.py`

Resolver responsibilities:

1. validate a `ProjectPathReference`
2. resolve it into a concrete local path
3. expose diagnostics for UI status badges
4. enforce inheritance from resolved root when `sourceKind == "project_root"`

### 3. Managed repo workspace layer

Create a repo workspace manager that makes GitHub-backed paths look local to the rest of CCDash.

Recommended services:

1. `backend/services/repo_workspaces/manager.py`
2. `backend/services/repo_workspaces/github_client.py`
3. `backend/services/repo_workspaces/git_runner.py`
4. `backend/services/repo_workspaces/cache.py`

Responsibilities:

1. authenticate against GitHub using integration settings
2. clone or mirror repos into a managed cache root
3. materialize branch-specific workspaces
4. refresh workspaces on demand
5. return effective local paths for repo subdirectories
6. optionally support controlled write operations for plan documents

### 4. Integration settings split

Introduce a higher-level integrations surface.

Recommended shape:

1. `/api/integrations/skillmeat/*` remains or is nested under a broader router.
2. Add `/api/integrations/github/*` for:
   - settings get/update
   - credential validation
   - repo/path validation
   - workspace refresh
   - write capability checks
3. Add integration settings persistence separate from `Project`.

### 5. Consumer contract

Downstream services should stop reconstructing paths ad hoc and instead consume resolved path bundles from one source of truth.

Primary consumers:

1. `backend/project_manager.py`
2. sync engine and parsers
3. document loading and cache browsing
4. codebase explorer / safe-path enforcement

## Phase Breakdown

## Phase 1: Domain model and migration scaffolding

Assigned Subagent(s): `backend-architect`, `python-backend-engineer`

Goals:

1. Define typed path-reference models in backend and frontend.
2. Add project-level compatibility/migration behavior.
3. Define integration settings models for GitHub.

Tasks:

1. Extend `backend/models.py` with path source and GitHub repo reference models.
2. Extend `types.ts` with matching frontend interfaces.
3. Add migration helpers in `backend/project_manager.py` to load legacy projects into the new shape.
4. Decide where GitHub integration settings persist:
   - app-level settings file
   - local database table
   - another non-repo-tracked store
5. Keep the existing simple `Project` fields derivable until all callers migrate.

Acceptance Gate:

1. Existing projects still load without modification.
2. New project config can represent all required path-source combinations.
3. Type validation rejects invalid root/path-source combinations.

## Phase 2: Path resolver and repo workspace backend

Assigned Subagent(s): `backend-architect`, `python-backend-engineer`

Goals:

1. Centralize path validation and resolution.
2. Provide a managed local workspace for GitHub-backed sources.

Tasks:

1. Implement `ProjectPathResolver`.
2. Implement filesystem and GitHub source providers.
3. Implement repo workspace cache lifecycle:
   - cache root initialization
   - clone or mirror bootstrap
   - branch checkout or worktree creation
   - subpath resolution
4. Normalize GitHub URL input into structured refs.
5. Add error categories for:
   - invalid GitHub URL
   - missing branch
   - missing subpath
   - auth failure
   - clone/fetch failure

Acceptance Gate:

1. Resolver returns concrete local paths for all supported source kinds.
2. A GitHub-backed root resolves to a stable local workspace path.
3. Distinct repos and branches can coexist without path collisions.

## Phase 3: Integration settings and credentials

Assigned Subagent(s): `backend-architect`, `integrations`, `security-engineering`

Goals:

1. Add GitHub integration settings and validation APIs.
2. Move toward a reusable integrations boundary instead of one-off SkillMeat handling.

Tasks:

1. Add persistence for GitHub integration settings.
2. Add endpoints for:
   - get/update GitHub settings
   - validate credential
   - validate repo ref/path
   - refresh repo workspace
   - check write capability
3. Refactor `backend/routers/integrations.py` or split it so SkillMeat and GitHub are peers under the Integrations surface.
4. Ensure secrets are masked in all API responses and logs.
5. Define read-only vs write-enabled status in the GitHub settings contract.

Acceptance Gate:

1. A user can save and validate GitHub credentials without storing them inside project records.
2. The API can verify repo access and nested path validity for a candidate GitHub path reference.
3. SkillMeat endpoints continue working after router refactor.

## Phase 4: Project API and active path consumption

Assigned Subagent(s): `python-backend-engineer`, `backend-architect`

Goals:

1. Route all project path access through the resolver.
2. Keep existing backend features working against resolved local paths.

Tasks:

1. Update `backend/routers/projects.py` to accept and return the new project-path config.
2. Refactor `ProjectManager.get_active_paths()` into a resolved-path bundle API.
3. Update sync, parsers, document loading, and safe-path checks to consume resolved paths.
4. Preserve defaults for local-only projects and the default example project.
5. Add effective-path metadata for diagnostics where useful.

Acceptance Gate:

1. Legacy local projects behave the same after the refactor.
2. GitHub-backed plan docs and progress paths are discoverable by existing backend workflows.
3. No downstream consumer depends on raw GitHub URLs as filesystem paths.

## Phase 5: Settings UI restructure and per-field editors

Assigned Subagent(s): `frontend-developer`, `ui-engineer-enhanced`

Goals:

1. Expose the new source selector UX in Projects.
2. Move SkillMeat into a dedicated Integrations tab and add GitHub controls.

Tasks:

1. Add a top-level `integrations` tab in `components/Settings.tsx`.
2. Add nested sub-tabs for `SkillMeat` and `GitHub`.
3. Remove the embedded SkillMeat editor from the Project Settings pane.
4. Add per-field source selectors and source-aware inputs for:
   - root
   - plan docs
   - sessions
   - progress
5. Add GitHub URL helper text and effective-path preview states.
6. Add validation/status badges for path resolution and GitHub auth.
7. Keep the default path editing flow simple for local-only users.

Acceptance Gate:

1. Users can configure local-only projects without extra friction.
2. Users can paste a GitHub repo/tree URL and see validation feedback.
3. SkillMeat and GitHub settings are available from the new Integrations tab.

## Phase 6: Plan-document write support

Assigned Subagent(s): `backend-architect`, `python-backend-engineer`

Goals:

1. Add the minimum safe write path requested by product scope.
2. Keep the rest of repo-backed path usage read-only.

Tasks:

1. Add a write-capable repo workspace operation for plan documents only.
2. Gate write behavior behind:
   - GitHub integration enabled
   - credential with write scope
   - explicit write toggle enabled
   - eligible target document path
3. Decide V1 branch strategy:
   - write directly to configured branch, or
   - write to a dedicated integration branch
4. Add audit or activity logging for repo writes.
5. Make write support unavailable when prerequisites are missing.

Acceptance Gate:

1. Plan-document write support is impossible unless explicitly enabled.
2. A repo-backed plan document can be updated through the controlled write path.
3. Non-plan artifact writes remain out of scope.

## Phase 7: Validation, tests, and rollout hardening

Assigned Subagent(s): `code-reviewer`, `task-completion-validator`, `frontend-developer`, `python-backend-engineer`

Goals:

1. Cover migration and repo-backed edge cases.
2. Reduce rollout risk for local-first users.

Tasks:

1. Backend unit tests for:
   - project migration
   - GitHub URL normalization
   - path resolution
   - repo workspace errors
   - credential masking
2. Backend integration tests for:
   - GitHub settings save/validate flows
   - project update with repo-backed refs
   - active-path consumption by sync/document services
3. Frontend tests where practical for:
   - source selector behavior
   - tab movement from Projects to Integrations
   - validation messaging
4. Manual QA scenarios:
   - local-only project
   - GitHub root with default-relative plan/progress paths
   - mixed local + GitHub overrides
   - invalid branch/path
   - read-only GitHub token
   - write-enabled plan-document update

Acceptance Gate:

1. Local-only project configuration remains stable.
2. Repo-backed paths resolve and sync successfully in supported scenarios.
3. GitHub write support stays disabled unless fully configured.

## Data and Persistence Notes

Recommended persisted concerns:

1. `Project` stores typed path references and project-scoped SkillMeat config.
2. GitHub integration settings store:
   - enabled flag
   - masked credential metadata
   - clone/cache root
   - default write policy
   - optional branch strategy
3. Repo workspace state stores:
   - repo slug/url
   - branch/ref
   - local cache path
   - last fetch status
   - last sync timestamp

## Affected Files and Likely Touchpoints

Backend:

1. `backend/models.py`
2. `backend/project_manager.py`
3. `backend/routers/projects.py`
4. `backend/routers/integrations.py`
5. `backend/main.py`
6. `backend/db/sqlite_migrations.py` or equivalent persistence target
7. `backend/db/postgres_migrations.py` or equivalent persistence target
8. new `backend/services/project_paths/*`
9. new `backend/services/repo_workspaces/*`

Frontend:

1. `types.ts`
2. `components/Settings.tsx`
3. `components/AddProjectModal.tsx`
4. `contexts/DataContext.tsx`
5. new service module for GitHub integration APIs

## Risks and Mitigations

1. Risk: legacy path consumers are missed during refactor.
   - Mitigation: move callers behind one resolved-path API and grep for direct field access.
2. Risk: repo cache strategy becomes brittle across branches.
   - Mitigation: centralize workspace lifecycle in one manager and test branch/subpath combinations.
3. Risk: integration settings sprawl between app and project scopes.
   - Mitigation: keep credentials/global workspace policy app-scoped and repo selections project-scoped.
4. Risk: write support delays the read-path delivery.
   - Mitigation: keep Phase 6 isolated and shippable behind a flag after read-only functionality is stable.

## Delivery Strategy

1. Ship Phases 1-5 as the primary functional milestone for repo-backed path reads and UI restructuring.
2. Enable Phase 6 only after read-path validation is stable.
3. Roll out with migration-safe defaults:
   - existing projects remain local-only
   - GitHub integration disabled by default
   - plan-document write support disabled by default

## Definition of Done

1. The new PRD acceptance criteria are satisfied.
2. Existing local-only projects continue to operate after migration.
3. GitHub-backed path fields resolve through managed local workspaces.
4. SkillMeat and GitHub settings live under the new Integrations tab.
5. Tests cover migration, resolver logic, and the main UI flows.

## Execution Notes

1. Phases 5-7 landed on March 12, 2026 with typed project-path editors, a dedicated Integrations surface, controlled plan-document write-back, and targeted frontend/backend tests.
2. V1 GitHub writes use the configured branch directly; no integration-only branch indirection was added in this iteration.
3. The implementation plan remains `in-progress` until unrelated repo-wide `pnpm typecheck` failures are cleared in:
   - `components/TranscriptMappedMessageCard.tsx`
   - `constants.ts`
   - `contexts/DataContext.tsx`
