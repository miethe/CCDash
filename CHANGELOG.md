# Changelog

## 2026-03-05

### Added

- Agent/subagent invocation capture improvements:
  - `Task` and `Agent` tool calls now persist richer invocation metadata (`taskId`, description, prompt preview, `subagent_type`, mode/model, background execution flag).
  - Agent invocations are captured as first-class `session_artifacts` (`type=agent`) and correlated to linked sub-thread sessions.
  - Sub-thread naming now prefers captured `subagent_type` and is reflected across transcript links, Session `Artifacts > Agents`, and the top-level `Agents` tab.
- Test run execution enrichment for session transcripts and forensics:
  - command-level extraction for test framework, targets, domain inference, flags, timeout, and capture hints.
  - output-level enrichment for parsed result metrics (`passed`/`failed`/`skipped`/`xfailed`/etc), duration, worker counts, and pass-rate rollups.
  - parser now persists normalized `testRun` metadata and aggregates session-level `sessionForensics.testExecution`.
- Hook invocation capture:
  - Claude `hook_progress` events now persist structured metadata (`hookName`, `hookPath`, `hookEvent`, `hookCommand`) on session logs.
  - Hook events now create first-class `session_artifacts` (`type=hook`) tied to source log IDs.
  - Added `entryContext.hookInvocations` in session forensics for correlation and downstream analytics.
- Default transcript mapping coverage:
  - added built-in mapping `artifact-hook-invocation` for `.claude/hooks/*` paths as `artifact` transcript events.

### Changed

- Session transcript formatting now supports stronger mapped-event rendering for captured invocation artifacts, including hooks and enriched test runs.
- Session artifact correlation in inspector flows now has stronger linkage between tool logs, mapped transcript cards, artifact groups, and linked sub-thread sessions.

### Fixed

- Fixed unintended `Test Run` labeling regression where non-test shell/tool commands could appear as tests.
  - UI now requires explicit test signals (`testRun` metadata, explicit/inferred test framework, or `toolCategory=test`) before rendering test-run formatting.

### Docs

- Updated:
  - `README.md`
  - `docs/testing-user-guide.md`
  - `docs/session-data-discovery.md`
  - `docs/codebase-explorer-developer-reference.md`

## 2026-03-03

### Added

- Incremental Test Visualizer mapping cache keyed by test-definition signature:
  - resolver now reuses existing primary mappings when a test definition is unchanged.
  - each stored mapping now includes `definition_signature`, `resolver_version`, and `mapped_at` metadata.
- Adaptive domain hierarchy assignment for mapping providers:
  - domain paths can now be created at multiple levels (`core`/`support`/`leaf`) instead of only a flat top-level domain.
  - large top-level domains automatically map deeper (sub-domain depth) based on test-volume thresholds.
- Backfill API payload now supports:
  - `force_recompute`
  - `provider_sources`
  - `source`
- New low-priority fallback mapping provider:
  - `path_fallback` assigns baseline domain mappings for tests that do not match feature heuristics.
  - enables full test-to-domain coverage while preserving higher-confidence mappings as primary when available.

### Changed

- `POST /api/tests/mappings/backfill` now performs project-wide incremental resolution over tests found in selected runs:
  - no longer skips a run just because some tests already have primary mappings.
  - resolves only unmapped/changed tests and reports cache reuse counts.
- `POST /api/tests/mappings/import` now runs with resolver version `2` and forces recompute for imported semantic mappings.
- Mapping backfill response includes richer progress and cache telemetry:
  - `tests_considered`
  - `tests_resolved`
  - `tests_reused_cached`
  - `resolver_version`
  - `cache_state`
- Backfill now prunes unmapped leaf domains so stale/orphan domain nodes do not accumulate in the UI.

### Docs

- Updated:
  - `README.md`
  - `docs/testing-user-guide.md`
  - `docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-7-mapping-integrity.md`

### Added (Execution Workbench)

- In-app local terminal run lifecycle support on `/execution`:
  - pre-run policy review modal (command/cwd/env profile + re-check)
  - feature-scoped `Runs` tab with run history and live output stream
  - approval dialog for `requires_approval` blocked runs
- Frontend execution API client methods for:
  - policy checks
  - create/list/get runs
  - event pagination and incremental stream fetch
  - approve/cancel/retry actions
- New execution UI components:
  - `components/execution/ExecutionRunHistory.tsx`
  - `components/execution/ExecutionRunPanel.tsx`
  - `components/execution/ExecutionApprovalDialog.tsx`

### Changed (Execution Workbench)

- `FeatureExecutionWorkbench` now includes a dedicated `Runs` tab and workbench-native run controls instead of copy-only command flows.
- Recommendation actions now support immediate in-app run launch (`Run in Workbench`) for primary and alternative commands.

### Docs (Execution Workbench)

- Added:
  - `docs/execution-workbench-user-guide.md`
  - `docs/execution-workbench-developer-reference.md`
- Updated:
  - `README.md`

## 2026-03-02

### Added

- Cross-platform session parser support via registry routing:
  - Codex parser added for JSONL payload streams (`response_item`, `event_msg`, `turn_context`).
  - Parser registry now attempts Codex parse first, then Claude Code fallback.
  - Nested session scanning (`rglob`) to support dated/nested Codex session directory layouts.
- New session forensic signals persisted to `session_forensics_json`:
  - `resourceFootprint`
  - `queuePressure`
  - `subagentTopology`
  - `toolResultIntensity`
  - `platformTelemetry` (Claude)
  - `codexPayloadSignals` (Codex)
  - `sidecars.toolResults` (Claude)
- New tests:
  - `backend/tests/test_sessions_codex_parser.py`
  - Extended Claude forensics assertions in `backend/tests/test_sessions_parser.py`

### Changed

- Session Inspector forensic surfaces updated to consume and visualize new parser signals:
  - Transcript metadata rail now includes resource, waiting-task, subagent, tool-result, and MCP summaries.
  - Full Forensics tab now includes dedicated sections for queue pressure, resource footprint, subagent topology, tool-result intensity, platform telemetry, and Codex payload signals.
- Claude forensic schema updated to version `3` and now includes `tool_results` sidecar configuration.
- Added package script:
  - `npm run discover:sessions` (`python3 backend/scripts/session_data_discovery.py --platform claude_code`)

### Docs

- Added:
  - `docs/project_plans/reports/session-data-discovery-findings-2026-03-02.md`
  - `docs/project_plans/reports/session-signal-next-analysis-and-lm-assist-deep-dive-2026-03-02.md`
- Updated:
  - `docs/session-data-discovery.md`
  - `README.md`

## 2026-02-22

### Added

- Track A analytics API surface:
  - `GET /api/analytics/overview`
  - `GET /api/analytics/series`
  - `GET /api/analytics/breakdown`
  - `GET /api/analytics/correlation`
  - `POST /api/analytics/alerts`
  - `PATCH /api/analytics/alerts/{id}`
  - `DELETE /api/analytics/alerts/{id}`
- Token timeline series support sourced from persisted session log usage metadata.
- New documentation:
  - `docs/telemetry-analytics-track-a-implementation-reference-2026-02-22.md`
- New tests:
  - `backend/tests/test_tasks_repository.py`
  - `backend/tests/test_analytics_router.py`

### Changed

- Task analytics correctness:
  - completion metrics now count `done`, `deferred`, and `completed` for compatibility.
- Session telemetry persistence:
  - session `dates`, `timeline`, and `impactHistory` are now persisted and rehydrated.
- Tool usage telemetry:
  - `session_tool_usage.total_ms` now populated from tool use/result timing.
- Analytics capture:
  - writes `analytics_entries.metadata_json` context and `analytics_entity_links` associations.
- Dashboard analytics:
  - KPI/model/series cards now sourced from backend analytics endpoints (removed hardcoded display values for core KPIs).
- Session Inspector analytics:
  - token timeline now uses backend series endpoint instead of simulated data.
- Settings alerts:
  - alerts tab now uses persisted backend CRUD operations.

### Migrations

- SQLite schema version bumped to `8`.
- Postgres schema version bumped to `6`.
- Added `sessions` columns:
  - `dates_json`
  - `timeline_json`
  - `impact_history_json`
- Added/ensured `session_tool_usage.total_ms`.

## 2026-02-19

### Added

- Unified document metadata system for plan and progress markdown.
- Typed `Document` fields (subtype/root kind/status normalization/phase/progress/task metrics/feature hints).
- Normalized `document_refs` storage for searchable/linkable extracted references.
- New APIs:
  - `GET /api/documents` (paginated/filterable)
  - `GET /api/documents/catalog` (facet counts)
  - `GET /api/documents/{doc_id}/links` (linked features/tasks/sessions/docs)
- Documents UI upgrades:
  - scope tabs (`Plans`, `PRDs`, `Reports`, `Progress`, `All`)
  - faceted filters and typed-metadata search
  - subtype-aware document modal with normalized links panel

### Changed

- Progress markdown is now synced as first-class `documents` (not only task source).
- Canonical path identity standardized to project-relative slash-normalized paths.
- Document-to-entity mapping strategy now prioritizes explicit refs, then path hints, then inherited doc refs.
- Feature doc resolution in board/modal now supports canonical path matching.
- Frontend document loading now pages API calls to avoid validation failures on large projects.
- `npm run dev` now validates backend health before starting frontend, and exits fast if backend startup fails.
- Added explicit startup scripts for backend-only dev/prod-style runs (`dev:backend`, `start:backend`) and frontend preview (`start:frontend`).
- Added deferred lifecycle support for tasks/phases/features:
  - New `deferred` status option across status controls.
  - Deferred counts contribute to completion and progress calculations.
  - Features move to/remain in `Done` stage when all tasks are terminal (`done` or `deferred`) and now show a deferred caveat indicator.
  - Feature/phase/task filters now include deferred visibility.
- Added completion-equivalence reconciliation across linked feature docs:
  - Feature status now resolves to done when any equivalent completion collection is complete (`PRD`, `Plan`/phase plans, or all progress docs).
  - Inferred completion writes through `status: inferred_complete` to linked PRD/Plan docs that are not already completion-equivalent.
- Document filter facets now normalize status/subtype variants into canonical values.
- Document and feature date derivation now uses normalized source precedence with git-backed file history:
  - batched `git log` extraction for `createdAt`/`updatedAt`
  - dirty/untracked worktree detection for in-progress local edits
  - parser fallback to frontmatter/filesystem when git data is unavailable
- Link rebuild execution now uses cached-state gating:
  - startup full sync skips relink when synced entities are unchanged and logic version matches
  - full relink still runs on force sync, explicit rebuild endpoint, changed-file link-impact, or logic-version bump (`CCDASH_LINKING_LOGIC_VERSION`)

### Fixed

- `/plans` load failures from oversized `limit` requests and slow N+1 link lookups in list endpoint.
- Migration ordering issue for typed `documents` index creation on legacy DBs.
- Reduced frontend false-start state where UI loaded while backend was unavailable (`ECONNREFUSED` proxy errors).

### Docs

- Added `/docs/setup-user-guide.md` with setup, startup, deployment-style runbook, and troubleshooting for `/api` connectivity errors.
- Updated document entity/frontmatter specs with completion-equivalence and canonical filter-value behavior.
- Updated sync/document developer docs with git date extraction strategy and one-time backfill workflow.
- Documented linking rebuild gate and `CCDASH_LINKING_LOGIC_VERSION` usage for deployment-safe relink triggers.
