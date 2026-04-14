---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: completed
category: enhancements
title: "PRD: Project Path Sources and GitHub Integration V1"
description: "Add per-path source selectors, GitHub-backed project paths, and a dedicated Integrations settings area for SkillMeat and GitHub."
summary: "Generalize project path configuration so each path can resolve from project root, GitHub, or the local filesystem, while introducing a modular GitHub integration and repo-workspace layer."
created: 2026-03-12
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/180c52f
- https://github.com/miethe/CCDash/commit/10e3a75
- https://github.com/miethe/CCDash/commit/5aa509b
pr_refs: []
priority: high
risk_level: high
complexity: High
track: Settings / Integrations
timeline_estimate: "3-5 weeks"
feature_slug: project-path-sources-and-github-integration-v1
feature_family: project-configuration-and-integrations
feature_version: v1
lineage_family: project-configuration-and-integrations
lineage_parent: null
lineage_children: []
lineage_type: enhancement
problem_statement: "CCDash assumes a single local filesystem project root today, which blocks repo-backed document sources, per-path overrides, and a scalable integrations model."
owner: fullstack-engineering
owners: [fullstack-engineering, platform-engineering, integrations]
contributors: [ai-agents]
audience: [developers, product, platform-engineering, engineering-leads]
tags: [prd, settings, github, integrations, project-paths, repositories]
related_documents:
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
  - docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
context_files:
  - components/Settings.tsx
  - components/AddProjectModal.tsx
  - contexts/DataContext.tsx
  - types.ts
  - backend/models.py
  - backend/project_manager.py
  - backend/routers/projects.py
  - backend/routers/integrations.py
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
---

# PRD: Project Path Sources and GitHub Integration V1

## Executive Summary

CCDash currently models project configuration around one local root path plus a small set of path strings derived from that root. That is sufficient for purely local projects, but it breaks down for teams whose plan docs or progress artifacts live in GitHub repositories, teams that want one field to resolve from a different repo than the main project, and future integrations that should read and write through a modular repository abstraction rather than ad hoc path logic.

This enhancement introduces per-field path source selectors, GitHub-backed project paths, and a first-class Integrations area in Settings. V1 should let users choose where each project path resolves from, use GitHub repositories as effective project roots or per-field overrides, and manage GitHub and SkillMeat integration settings in a dedicated location. The backend should resolve repo-backed sources into managed local workspaces so current parsers, sync, and filesystem-based features continue to operate with minimal downstream change.

## Current State

1. `Project` persists a single local `path`, a relative `planDocsPath`, a relative `progressPath`, and an absolute `sessionsPath`.
2. `ProjectManager.get_active_paths()` derives effective directories by concatenating those path strings against one local root.
3. The Settings UI presents directory paths inline inside the Projects tab and assumes:
   - `Project Root Path` is local filesystem only.
   - `Plan Documents Path` is relative to root.
   - `Progress/Tasks Path` is relative to root.
   - `Sessions Path` is absolute filesystem only.
4. SkillMeat configuration is embedded inside the Project Settings editor rather than a reusable integrations surface.
5. The only existing integrations router is scoped to `/api/integrations/skillmeat`.
6. Filesystem consumers such as sync, document parsing, codebase exploration, and cache browsing expect locally accessible paths.

## Problem Statement

As a CCDash operator, I need each project path field to resolve from the most appropriate source: the configured project root, a different local filesystem location, or a GitHub repository and subdirectory. Without that flexibility, CCDash cannot model common setups where plan docs live in a separate repo, progress docs live elsewhere, or the effective project root itself is GitHub-backed rather than local.

I also need GitHub integration to be managed separately from project editing, both because credentials and clone behavior are cross-cutting concerns and because the app should evolve toward a modular integrations architecture that can later support direct repo providers, hosted environments, and Backstage-style integrations.

## Goals

1. Add a source selector for each directory path field in Project Settings.
2. Support GitHub-backed project roots and GitHub-backed overrides for non-root path fields.
3. Preserve "use project root" as the default behavior for non-root fields.
4. Resolve repo-backed paths into managed local workspaces so existing parsing and filesystem features continue to work.
5. Move integration management into a top-level Settings tab with sub-tabs for `SkillMeat` and `GitHub`.
6. Add GitHub credential and workspace settings needed to support repo-backed reads and opt-in plan-document writes.
7. Keep the implementation modular so future providers can use the same path-resolution and workspace contracts.

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Project path fields with selectable source kinds | 0 | All supported directory fields |
| GitHub-backed plan/progress/project-root configurations | Unsupported | Supported for at least root, plan docs, and progress |
| Existing filesystem parsers/features after repo-backed config | N/A | No functional regression |
| Integrations UI surface | SkillMeat embedded in Projects | Dedicated Integrations tab with SkillMeat + GitHub |
| Git-backed plan doc update flow | Unsupported | Optional opt-in write path for plan documents |

## User Stories

1. As a user, I can set Project Root to a GitHub repo URL so CCDash treats that repo as the effective root for default-relative fields.
2. As a user, I can keep Project Root local but point `Plan Documents Path` at a different GitHub repo.
3. As a user, I can point `Progress/Tasks Path` to another local filesystem location without changing the main project root.
4. As a user, I can paste a GitHub repo or tree URL that includes branch and nested directory context, and CCDash resolves it correctly.
5. As a user, I can configure GitHub credentials once in Settings rather than re-entering them per project.
6. As an operator, I can keep GitHub read-only by default and explicitly opt into plan-document write support.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Project Settings must expose a source selector adjacent to each directory-path field. | Must | Applies to all supported path-backed project fields. |
| FR-2 | Non-root path fields must support `project_root`, `github_repo`, and `filesystem` source kinds. | Must | `project_root` remains default. |
| FR-3 | Project Root must support `filesystem` and `github_repo` source kinds. | Must | `project_root` is not valid for the root field itself. |
| FR-4 | When Project Root is GitHub-backed, non-root fields using `project_root` must resolve relative to the checked-out repo workspace. | Must | This is the core inheritance behavior. |
| FR-5 | GitHub-backed fields must accept repo URLs that may include branch and nested directory context. | Must | UI may accept a single URL-like input, but storage should normalize it. |
| FR-6 | Each GitHub-backed field must support pointing to a distinct repository from other fields. | Must | Per-field repo override support. |
| FR-7 | CCDash must maintain a local managed workspace for each referenced GitHub repo/branch combination needed for parsing or browsing. | Must | Enables local filesystem semantics for existing services. |
| FR-8 | Settings must include a new top-level `Integrations` tab with sub-tabs for `SkillMeat` and `GitHub`. | Must | SkillMeat UI moves out of Projects. |
| FR-9 | GitHub integration settings must include a PAT/API key entry point and repo-workspace settings required for repo-backed paths. | Must | See GitHub settings section below. |
| FR-10 | GitHub write support must be optional, scoped, and disabled by default. | Must | Initial write target is plan documents only. |
| FR-11 | Repo-backed path resolution failures must surface actionable validation and runtime status in the UI. | Must | Includes auth, branch, missing path, and clone errors. |
| FR-12 | The implementation must use provider-like abstractions so additional repository backends can be added later. | Must | Future Backstage or direct git providers. |

## GitHub Settings Requirements

1. The new GitHub sub-tab must support:
   - enabling/disabling the integration
   - PAT/API key entry and validation
   - a local clone/cache root for managed repo workspaces
   - default read-only vs write-enabled behavior
   - default branch/write strategy for plan-document updates
   - repo refresh or sync controls and status
2. Credentials must be stored outside project documents and outside any git-tracked settings artifacts.
3. Validation must distinguish:
   - credential validity
   - repo access
   - branch existence
   - nested path existence
   - write permission availability when write support is enabled

## Recommended Product/Architecture Decisions

### 1. Structured storage, URL-friendly input

Users should be allowed to paste GitHub URLs directly into the field, including `tree/<branch>/<subdir>` forms. Internally CCDash should normalize this into structured data rather than storing opaque strings as the canonical representation.

Recommended internal shape:

1. `sourceKind`
2. `displayPath`
3. `relativePath` or `subpath`
4. `repoRef` with:
   - provider
   - repo URL or owner/repo slug
   - branch or ref
   - nested repo path
   - write intent

### 2. Managed local repo workspaces

V1 should use a local repo-workspace manager rather than direct remote reads for parsers. The preferred pattern is:

1. clone or mirror repositories locally under an app-managed cache root
2. materialize branch-specific workspaces as needed
3. hand downstream services resolved local filesystem paths

This keeps current file-based parsing, sync, and codebase navigation largely intact while allowing future providers to swap in different fetch strategies.

### 3. Write support is opt-in and narrowly scoped

GitHub write access should not be required for repo-backed reads. When enabled, V1 write support should be limited to plan-document edits only. Recommended write behavior:

1. default to disabled
2. validate write permission before exposing save/publish actions
3. write through a controlled git service
4. prefer explicit branch targeting over silent direct writes to default branch

### 4. Provider abstraction for future integrations

The system should not hardcode GitHub path logic inside `ProjectManager`. Instead, path resolution should depend on a reusable source-provider contract so later integrations can add direct git, hosted SCM, or Backstage-backed implementations without replacing the product model.

## Non-Functional Requirements

1. Path resolution must be deterministic and debuggable.
2. Repo-backed path setup must not require downstream parsers to understand GitHub APIs directly.
3. Credential handling must avoid plain-text exposure in UI responses and logs.
4. Existing local-only projects must continue to function without migration friction.
5. Repo workspace refresh should be efficient enough for normal settings-save and sync flows.
6. The model must be backward compatible with existing `projects.json` entries during migration.

## In Scope

1. Per-field path source selection in Project Settings.
2. GitHub-backed root, plan-doc, progress, and session path configuration model.
3. A managed local repo workspace layer for GitHub-backed sources.
4. Top-level Integrations Settings tab with nested SkillMeat and GitHub sections.
5. Global GitHub credential and workspace settings.
6. Optional plan-document write enablement and validation.
7. Migration from legacy project path fields to the new path-source model.

## Out of Scope

1. Full GitHub pull request lifecycle automation in V1.
2. Direct remote parsing without a local workspace layer.
3. Supporting non-GitHub SCM providers in V1.
4. Arbitrary bidirectional git writes for every parsed artifact type.
5. Replacing the current local-first operating model for users who do not need repo-backed paths.

## Dependencies and Assumptions

1. CCDash can persist local integration secrets in a non-repo-tracked application storage location or equivalent secret store.
2. The current backend path consumers can be adapted to consume resolved local paths instead of raw project strings.
3. GitHub API and git CLI access are available in environments where GitHub-backed paths are configured.
4. Existing SkillMeat project configuration remains project-scoped even after moving the UI into a dedicated Integrations area.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Path model becomes too stringly typed and hard to validate | High | Medium | Normalize UI input into typed path-reference objects. |
| Repo cloning logic leaks into many unrelated services | High | Medium | Centralize in a repo workspace manager and path resolver service. |
| GitHub PAT ends up stored in `projects.json` | High | Medium | Store credentials in dedicated integration secrets storage, not project documents. |
| Branch/path parsing for GitHub URLs is ambiguous | Medium | High | Parse into structured refs, surface validation status, and allow explicit branch correction. |
| Write support creates unsafe repo mutations | High | Medium | Keep read-only default and limit V1 writes to explicit plan-document flows. |
| Settings UI becomes more confusing | Medium | Medium | Preserve `project_root` as default, show effective resolved path summaries, and use per-field validation badges. |

## Acceptance Criteria

1. A project can configure Project Root as either local filesystem or GitHub repo.
2. Each non-root directory field can choose between `project_root`, `github_repo`, and `filesystem`.
3. If Project Root is GitHub-backed, default-relative path fields resolve against the repo workspace and operate correctly.
4. A non-root field can independently point to a different GitHub repo and nested directory.
5. Settings includes a dedicated `Integrations` tab with `SkillMeat` and `GitHub` sub-tabs.
6. GitHub settings support credential entry, validation, and managed workspace configuration.
7. Repo-backed reads work through locally resolved workspaces so existing parsers and sync features continue to function.
8. Plan-document write support is disabled by default and only becomes available when GitHub write access is explicitly configured.
9. Legacy projects without the new path-source model still load and migrate safely.
