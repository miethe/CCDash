---
doc_type: implementation_plan
status: in-progress
category: enhancements

title: "Implementation Plan: Session Activity/Files Split + Codebase Explorer V1"
description: "Split Session detail Files timeline into Activity + Files and add a full codebase explorer with file/session/feature/document correlations"
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-02-25
updated: 2026-02-25

tags: [implementation, backend, frontend, sessions, files, codebase, explorer]
feature_slug: session-activity-files-split-codebase-explorer-v1
feature_family: session-activity-files-split-codebase-explorer
lineage_family: session-activity-files-split-codebase-explorer
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [session-activity-files-split-codebase-explorer-v1]
related:
  - components/SessionInspector.tsx
  - backend/routers/api.py
  - backend/main.py
  - types.ts
plan_ref: session-activity-files-split-codebase-explorer-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: fullstack-engineering
owners: [fullstack-engineering]
contributors: [ai-agents]

complexity: High
track: Standard
timeline_estimate: "3-5 days across 5 phases"
---

# Implementation Plan: Session Activity/Files Split + Codebase Explorer V1

## Objective

Deliver two distinct outcomes:

1. Split Session detail into `Activity` and `Files` tabs while keeping root-thread scope (selected session + subagents).
2. Add a new `/codebase` explorer page that visualizes project files and correlations to sessions, features, documents, and activity.

## Scope and Fixed Decisions

1. Session tabs:
   - `Activity`: chronological line items for logs, file actions, artifacts, and thinking/tool entries.
   - `Files`: one row per normalized file path with multi-action chips.
2. Scope: both tabs remain root-thread scoped by default.
3. Codebase explorer V1:
   - 3-pane explorer (tree, file list, detail), no graph/network view.
4. Codebase universe:
   - all files under `activeProject.path`
   - exclusions from root `.gitignore` plus built-ins (`.git/`, `node_modules/`, `dist/`, `coverage/`, `.venv/`)
5. Data source constraints:
   - existing tables only; no schema migration.

## Public API and Interface Changes

1. Add backend router `backend/routers/codebase.py`.
2. Register router in `backend/main.py`.
3. Add `GET /api/codebase/tree` with query params:
   - `prefix`, `depth`, `include_untouched`, `search`
4. Add `GET /api/codebase/files` with query params:
   - `prefix`, `search`, `include_untouched`, `action`, `feature_id`, `sort_by`, `sort_order`, `offset`, `limit`
5. Add `GET /api/codebase/files/{file_path:path}` with query param:
   - `activity_limit`
6. Add frontend types in `types.ts`:
   - `SessionActivityItem`, `SessionFileAggregateRow`, `CodebaseTreeNode`, `CodebaseFileSummary`, `CodebaseFileDetail`
7. Update Session detail tabs in `components/SessionInspector.tsx`:
   - add `activity` tab and repoint transcript file jump actions to `activity`
8. Add `components/CodebaseExplorer.tsx`.
9. Add `/codebase` route in `App.tsx`.
10. Add sidebar nav item in `components/Layout.tsx`.
11. Add dependency `pathspec` in `backend/requirements.txt`.

## Data and Behavior Rules

1. `Activity` merges and sorts:
   - `logs`, `updatedFiles`, `linkedArtifacts` by timestamp.
2. `Files` groups by normalized path:
   - one row per file
   - action chips show distinct actions from `{Read, Create, Update, Delete}`.
3. Feature involvement score:
   - action weights: `create=1.00`, `update=0.80`, `delete=0.70`, `read=0.40`
   - base per session-file: `entity_link_confidence * max_action_weight`
   - path-signal bonus from `entity_links.metadata_json.signals` may raise score.
4. Involvement levels:
   - `primary >= 0.75`
   - `supporting 0.50-0.74`
   - `peripheral < 0.50`
5. Path safety:
   - reject traversal and out-of-root access for all codebase file endpoints.

## Architecture and Implementation Phases

## Phase 1: Backend service foundation

1. Create `backend/services/codebase_explorer.py`:
   - scan project tree
   - load/compile `.gitignore` rules via `pathspec`
   - apply built-in excludes
   - normalize/validate paths
   - collect touched-file aggregates from DB
2. Add 30s in-memory cache keyed by project id:
   - tree payload
   - file aggregate map.

## Phase 2: Codebase API router

1. Implement `backend/routers/codebase.py` endpoints:
   - `/tree`, `/files`, `/files/{file_path:path}`
2. Wire pagination/filter/sort in flat files endpoint.
3. Build file detail response:
   - file metadata
   - action rollups
   - related sessions/features/documents
   - recent activity list.
4. Register router in backend app startup.

## Phase 3: Session Inspector split

1. Introduce `ActivityView` in `components/SessionInspector.tsx`.
2. Replace existing event-like file list with:
   - chronological activity tab
   - aggregated per-file files tab
3. Keep transcript deep-links/highlight behavior:
   - route file badge jumps to `activity` with `sourceLogId`.

## Phase 4: Codebase Explorer frontend

1. Create `components/CodebaseExplorer.tsx` with 3 panes:
   - left: file tree with touched indicators
   - middle: sortable/filterable file list
   - right: detail panel (sessions/features/documents/activity)
2. Add cross-entity navigation links:
   - sessions: `/sessions?session=...`
   - features: `/board?feature=...`
   - documents: `/plans?doc=...`
3. Add route and navigation entry.

## Phase 5: Testing and regression checks

1. Add `backend/tests/test_codebase_router.py` coverage for:
   - tree listing
   - untouched toggle
   - `.gitignore` compliance
   - path traversal rejection
   - file detail aggregation
   - involvement level thresholding
2. Validate session split behaviors:
   - read+update appears once in `Files` with both actions
   - `Activity` contains chronologically ordered tool/thought/file/artifact line items
3. Run build regression:
   - `npm run build`
4. Confirm deep-link regressions absent:
   - `/sessions?session=...` still opens selected session.

## Acceptance Criteria

1. Session detail has both `Activity` and `Files` tabs with required semantics.
2. `/codebase` route is available and interactive across all 3 panes.
3. Backend codebase endpoints respond with stable typed payloads and enforce root safety.
4. `.gitignore` and built-in exclusions are respected.
5. Backend tests for new router pass and frontend build succeeds.

