# Changelog

## [Unreleased]

## [0.2.0] - 2026-04-28
### Added

- **Planning Reskin v2**: Comprehensive UI refresh including modal-first navigation, agent roster filtering, triage inbox prioritization, home metrics and chip indicators, graph reskin with improved layouts, feature detail drawer with execution info, and writeback surface. Backend planning session board queries support filtering and state aggregation. Addendum includes caching strategy (SWR + LRU), OTEL instrumentation, and modal-scoped route helpers. (commits 4c02882, 4911484, a471f6e, f3435ac, efd0940, 4943e0e, 75642d7, 0f78eec, ed0d86b, dced2f0, 8b78d74, 635acc8)
- **Feature Surface Data Loading Redesign and Planning Agent Session Board**: Layered list→rollup→modal contracts with two-tier browser cache and unified invalidation bus. Session board renders Kanban-style cards grouped by state/feature/phase/agent/model. Performance budgets and cache invalidation patterns documented. (31847d2, 7b69b56)
- **Feature Surface Remediation v1**: Resolved data-contract gaps from phase 1 reskin including missing fields, type mismatches, and resilience-by-default FE fallbacks. (a5f7564)
- **CCDash landing page and static hosting support**: Public-facing landing page with Nginx templating for static asset delivery and environment-based configuration injection. (21aeec9)
- **Containerized deployment infrastructure**: Unified backend Dockerfile with `CCDASH_RUNTIME_PROFILE` dispatch, hardened frontend nginx image with non-root user and envsubst templating, unified `compose.yaml` with composable `local` (SQLite single-container), `enterprise` (split API/worker with external Postgres), and `postgres` (bundled postgres:17-alpine) profiles, rootless Podman support via UID/GID build args and SELinux bind-mount labels, and operator quickstart guide. Single-command deployment: `docker compose --profile local up --build`. (f14adbc, c408175)
- **Feature flags for runtime-performance hardening**:
  - `VITE_CCDASH_MEMORY_GUARD_ENABLED` (default true): gates frontend memory hardening via transcript ring-buffer cap, document pagination, and in-flight request garbage collection.
  - `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (default false): enables incremental link rebuild with cached-state gating to skip relink when entities are unchanged.
  - `CCDASH_STARTUP_SYNC_LIGHT_MODE` (default false): enables manifest-based filesystem scan skip to reduce startup I/O and sync latency.
- New observability counters: query cache hit/miss tracking, scan-cached/scanned distinctions, and performance health defaults via `runtimePerfDefaults` health endpoint.

### Changed

- `CCDASH_QUERY_CACHE_TTL_SECONDS` default increased from 60s to 600s to align with background cache-warming interval and reduce redundant queries.
- `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` default changed from true to false: link rebuilds are now opt-in after startup to defer I/O-heavy work.
- Polling teardown now triggers after 3 unreachable health checks; frontend displays "backend disconnected" banner with manual retry button.
- Frontend memory stability improvements: transcript ring-buffer cap (configurable via health defaults), document pagination cap, and in-flight request lifecycle GC.
- Backend workflow batch query eliminates N+1 query pattern for fetching linked workflows.
- Filesystem scan manifest skip in light mode bypasses redundant file enumeration when metadata is unchanged.

### Fixed

- **Silent error handling**: Replaced `except: pass` blocks in planning hot paths (`planning_sessions.py:695`, `planning.py:1927`) and six `except: continue` blocks in `parsers/features.py` with logged warnings — partial failures no longer corrupt downstream board cards or skip malformed PRDs invisibly.
- **Accessibility**: PlanCatalog clickable doc-row divs now expose `role="button"`, `tabIndex={0}`, and Enter/Space keyboard activation.
- **Polling teardown** prevents cascade of failed health checks and reconnection storms when the backend goes unreachable.
- **Frontend memory leaks** from unbounded transcript caches and orphaned in-flight requests during disconnections.

### Performance

- **Frontend re-render reduction**: Memoized context provider values in `AppEntityDataContext`, `AppRuntimeContext`, and `AppSessionContext`. Consumers (SessionInspector, ProjectBoard, Planning surfaces) no longer re-render on every parent state change — eliminates per-poll-tick render cascades.
- **Backend N+1 elimination**: Six confirmed N+1 patterns in agent_queries hot paths replaced with batch repository fetches: feature forensics linked-session loops, planning session enrichment, planning-session-board entity-link aggregation, document detail fan-out, integrations stack-observation loop, and session-intelligence rollup gather. New bulk methods on sessions/documents/features/entity_graph repositories.
- **DB indexes**: Added composite indexes for `sessions(conversation_family_id)`, `features(project_id, status)`, and `feature_phases(feature_id, status)` — closes scan gaps on planning summary and feature-list filters.

### Docs

- Added:
  - `docs/guides/runtime-performance-hardening-v1.md`
  - `docs/guides/feature-surface-architecture.md`
  - `docs/guides/planning-reskin-v2-feature-guide.md`
- Updated:
  - `.env.example` with new feature flags and default value changes.
  - `CLAUDE.md` with feature flag descriptions and runtime profile tuning guidance.
- Marked completed plans: feature-surface-redesign, session-board, and reskin addendum. (994d1e8)

## 2026-04-15

### Added

- **CLI timeout configuration**: `--timeout SECONDS` global flag and `CCDASH_TIMEOUT` env var on the standalone CLI (default 30s). Precedence: flag > env > default. `ccdash doctor` and `ccdash target check` display the active timeout and its source.
- **Query caching** for project-status, feature-forensics, workflow-diagnostics, and aar-report endpoints: in-process TTL cache keyed on project-scoped data fingerprint. Default TTL `CCDASH_QUERY_CACHE_TTL_SECONDS=60`. `--no-cache` CLI flag and `bypass_cache=true` query param force miss. OpenTelemetry counters emitted. Graceful degradation when fingerprint unavailable.
- **FeatureForensicsDTO ergonomics**: top-level `name` and `status` alias fields for parity with nested access, plus `telemetry_available: bool` indicator and `sessions_note` field with eventual-consistency guidance.
- **Feature-list pagination & filtering**: default limit raised to 200. Responses include `truncated` and `total` fields. Keyword filter via `--q TEXT` (CLI) / `?q=` (HTTP), case-insensitive substring match. CLI displays truncation hint when results exceed the limit.
- **linked_sessions reconciliation**: `feature_show.linked_sessions` now reconciled with `feature_sessions` endpoint result; CI regression guard added; CLI/MCP output includes eventual-consistency hint. Background cache-warming job scheduled every `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` seconds (default 300; 0 disables).

## 2026-04-13

### Added

- **Standalone CLI** (`ccdash-cli` package): A globally installable operator CLI that talks to a running CCDash server over HTTP, with no repo checkout required.
  - Feature command group: `feature list`, `feature show`, `feature sessions`, `feature documents`
  - Session command group: `session list`, `session show`, `session search`, `session drilldown`, `session family`
  - Report command group: `report aar`, `report feature` (default markdown output)
  - Target management: `target add`, `target remove`, `target list`, `target use`, `target login`, `target logout`, `target check`
  - Diagnostics: `doctor`, `version`
  - Bearer-token authentication via OS keyring or `CCDASH_TOKEN` env var
  - Named target configuration stored in `~/.config/ccdash/config.toml`
  - Standardized pagination (`--limit`, `--offset`) and output modes (`--json`, `--md`, `--output`)
- Versioned client API (`/api/v1/`) with endpoints for instance, project, features, sessions, workflows, and reports
- Shared contract types in `packages/ccdash_contracts/` consumed by both server and CLI
- `VersionMismatchError` (exit code 5) for API compatibility detection
- 85 tests covering client, config, import boundary, and all command groups

### Docs

- Added:
  - `docs/guides/standalone-cli-guide.md` — comprehensive operator reference
  - `docs/guides/cli-migration-guide.md` — migration from repo-local to standalone CLI
- Updated:
  - `README.md` — CLI section now covers both standalone and repo-local entry points
  - `docs/guides/cli-user-guide.md` — cross-references standalone CLI guide

---

## 2026-04-12

### Added

- Transport-neutral agent intelligence queries are now documented as one shared capability exposed through three entry points:
  - REST: `GET /api/agent/project-status`, `GET /api/agent/feature-forensics/{feature_id}`, `GET /api/agent/workflow-diagnostics`, and `POST /api/agent/reports/aar`
  - CLI: `ccdash status project`, `ccdash feature report`, `ccdash workflow failures`, and `ccdash report aar`
  - MCP: `ccdash_project_status`, `ccdash_feature_forensics`, `ccdash_workflow_failure_patterns`, and `ccdash_generate_aar`
- MCP-specific documentation:
  - `docs/guides/mcp-setup-guide.md`
  - `docs/guides/mcp-troubleshooting.md`
  - `backend/mcp/README.md`

### Changed

- Repo docs now describe the Phase 3/4 agent query stack as a transport-neutral application layer consumed by REST, CLI, and MCP.
- README now shows how to use the CLI, how the shipped `.mcp.json` launches `python -m backend.mcp.server`, and how to validate the MCP surface with `backend/tests/test_mcp_server.py`.
- README now links to a dedicated CLI user guide covering the four commands, project override, output modes, setup, and troubleshooting.
- `CLAUDE.md` now includes the `backend/cli/`, `backend/mcp/`, and `/api/agent/*` surfaces in the architecture and command reference.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `CLAUDE.md`
- Added:
  - `docs/guides/cli-user-guide.md`
  - `docs/guides/mcp-setup-guide.md`
  - `docs/guides/mcp-troubleshooting.md`
  - `backend/mcp/README.md`

## 2026-04-06

### Changed

- Repo-level docs now reflect the completed `session-intelligence-canonical-storage-v1` rollout:
  - canonical transcript intelligence is treated as complete
  - `local` versus `enterprise` storage posture is called out explicitly
  - enterprise historical backfill is documented as a checkpointed rollout path
  - `/api/health` validation now points operators to the runtime storage/session-intelligence matrix
  - SkillMeat memory drafting is documented as reviewable and approval-gated rather than auto-published

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/setup-user-guide.md`
  - `docs/execution-workbench-user-guide.md`

## 2026-03-27

### Added

- Telemetry exporter operator docs:
  - `docs/guides/telemetry-exporter-guide.md`
  - `docs/guides/telemetry-exporter-troubleshooting.md`

### Changed

- CCDash telemetry exporter hardening now includes:
  - pending-queue cap enforcement with drop-and-warn behavior
  - synced-row purging after export runs using the retention window
  - exporter observability for batch outcomes, latency, queue depth, error classes, and disabled-state tracking
  - batch span hardening with project, endpoint, and outcome attributes
  - a standalone load test that validates the `<2%` CPU-share target
- README now surfaces the telemetry exporter and links operators to the dedicated guides.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`

## 2026-03-23

### Added

- Dependency-aware execution validation coverage:
  - `components/__tests__/dependencyAwareExecutionUi.test.tsx`

### Changed

- Feature Board, Execution Workbench, Plan Catalog, and Document Modal now surface dependency-aware execution and family-view metadata directly in the shipped UI:
  - blocked-by dependency chips and execution-gate summaries
  - family position and family-sequence metadata
  - navigation affordances back to the board, plans, sessions, analytics, and linked documents
- The dependency-aware execution implementation plan remains the source of truth for the shipped family-view rollout and the linked docs now describe the released behavior.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/execution-workbench-user-guide.md`
  - `docs/execution-workbench-developer-reference.md`
  - `docs/document-entity-user-guide.md`
  - `docs/document-entity-developer-reference.md`

### Added

- Session transcript append rollout docs and progress tracking:
  - `docs/live-update-platform-developer-reference.md`
  - `docs/setup-user-guide.md`
  - `docs/testing-user-guide.md`
  - `.claude/progress/session-transcript-append-deltas-v1/phase-3-progress.md`
  - `.claude/progress/session-transcript-append-deltas-v1/phase-4-progress.md`
  - `.claude/progress/session-transcript-append-deltas-v1/phase-5-progress.md`

### Changed

- Session Inspector now subscribes to `session.{session_id}.transcript` alongside coarse session invalidation and merges safe active-session transcript appends in place.
- Transcript append merge rules now suppress duplicates and fall back to `GET /api/sessions/{id}` on sequence mismatch, missing identifiers, replay gaps, and rewrite-like conflicts.
- Added regression coverage for transcript-topic reconnect, hidden-tab pause/resume, and snapshot-required cursor recovery semantics.
- Live-update developer docs now describe the `session.{session_id}.transcript` append topic, the normalized append contract, and the `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` rollout flag.
- Setup and testing guides now call out the transcript append gate and when Session Inspector appends locally versus refetches the full session detail.
- The session transcript append implementation plan now marks phases 3-5 complete and records the rollout/validation workflow.

## 2026-03-22

### Added

- Standard theme modes rollout docs:
  - `docs/theme-modes-user-guide.md`
  - `docs/theme-modes-developer-reference.md`
- Theme-mode progress tracking for implementation phases 3-5:
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-3-progress.md`
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-4-progress.md`
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-5-progress.md`

### Changed

- `Settings > General > Theme` now controls the real app-wide theme preference and persists `dark`, `light`, and `system`.
- The Settings route now includes a scoped light-mode compatibility bridge so legacy palette-literal controls remain usable under the shipped standard modes.
- Theme guardrails now also cover Settings selector wiring and the scoped Settings compatibility bridge.
- The CCDash standard theme modes implementation plan now marks phases 3-5 complete and the overall plan complete.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
- Added:
  - `docs/theme-modes-user-guide.md`
  - `docs/theme-modes-developer-reference.md`
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-3-progress.md`
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-4-progress.md`
  - `.claude/progress/ccdash-standard-theme-modes-v1/phase-5-progress.md`

## 2026-03-21

### Added

- Theme foundation phase 6 guardrails:
  - `lib/__tests__/themeFoundationGuardrails.test.ts` now protects the foundation-owned shared semantic surfaces from raw palette-literal regressions
  - shared analytics/chart surfaces are checked to stay on the centralized chart adapter
- Theme foundation handoff report:
  - `docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md`

### Changed

- Theme color exceptions policy is now active and explicitly tied to CI-visible foundation guardrails.
- CCDash theme-system foundation tracking now marks phase 6 complete and the implementation plan complete.
- The standard theme modes plan now carries a foundation handoff snapshot instead of assuming a fresh theme audit.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md`
  - `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
  - `docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md`
- Added:
  - `docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md`

## 2026-03-15

### Added

- Phase 5-6 SSE live-update rollout for invalidation-oriented surfaces:
  - feature board and feature modal subscriptions behind `VITE_CCDASH_LIVE_FEATURES_ENABLED`
  - test visualizer subscriptions behind `VITE_CCDASH_LIVE_TESTS_ENABLED`
  - ops panel subscriptions behind `VITE_CCDASH_LIVE_OPS_ENABLED`
- Shared frontend invalidation hook:
  - `services/live/useLiveInvalidation.ts`
- Live-update platform developer reference:
  - `docs/live-update-platform-developer-reference.md`

### Changed

- Sync, feature, test, and ops backend paths now publish project-scoped live invalidation topics in addition to the existing execution/session topics.
- `GET /api/cache/status` now exposes live broker metrics, and the Ops panel renders subscriber/buffer/replay-gap health at a glance.
- Test visualizer hooks now prefer live invalidation and fall back to polling on backoff/closed connections.
- SSE live-update platform tracking now completes phases 5-6 and marks the implementation plan complete.
- Remaining V1 risk is explicitly documented: session live updates still use invalidation plus targeted REST recovery instead of transcript append deltas.

### Docs

- Added:
  - `docs/live-update-platform-developer-reference.md`
- Updated:
  - `.env.example`
  - `README.md`
  - `CHANGELOG.md`
  - `docs/ops-panel-developer-reference.md`
  - `docs/ops-panel-user-guide.md`
  - `docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md`
  - `docs/setup-user-guide.md`
  - `docs/testing-user-guide.md`

## 2026-03-14

### Added

- Workflow Registry surface at `/workflows`:
  - dedicated catalog + detail workflow hub with deep-linkable selected workflow routes
  - explicit correlation-state badges for strong, hybrid, weak, and unresolved workflow entities
  - composition, effectiveness, issues, actions, representative sessions, and recent SkillMeat execution sections
- Frontend regression coverage for:
  - workflow registry route encoding and API query behavior
  - workflow registry catalog/detail render smoke cases
  - workflow action dispatch between internal CCDash navigation and external SkillMeat links
- User documentation for the Workflow Registry:
  - `docs/workflow-registry-user-guide.md`

### Changed

- `/analytics?tab=workflow_intelligence` and `/execution` now provide direct entry points into the Workflow Registry.
- Workflow intelligence documentation now treats `/workflows` as the primary identity-and-correlation hub, with `/analytics` remaining the comparative leaderboard view.
- Workflow Registry and Correlation Surface V1 tracking now completes phases 5-7 and marks the implementation plan complete.

### Docs

- Added:
  - `docs/workflow-registry-user-guide.md`
- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/agentic-sdlc-intelligence-user-guide.md`
  - `docs/agentic-sdlc-intelligence-developer-reference.md`
  - `docs/execution-workbench-user-guide.md`
  - `docs/guides/dev/workflow-skillmeat-integration-developer-reference.md`
  - `docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md`

## 2026-03-12

### Added

- Session block insights for longer Claude Code sessions:
  - configurable `1h`, `3h`, `5h`, and `8h` block windows in `Session Inspector > Analytics`
  - per-block observed workload, display-cost totals, burn rate, and projected end-of-block summaries
  - project-scoped `sessionBlockInsightsEnabled` rollout flag plus global env gate `CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED`
- Documentation for block-insight rollout and interpretation:
  - `docs/session-block-insights-user-guide.md`
  - `docs/session-block-insights-developer-reference.md`

### Changed

- Session Inspector analytics now exposes main-session-only block views without altering canonical workload or cost totals.
- Project Settings now lets operators disable session block insights independently from other analytics surfaces.
- Pricing configuration moved from `Projects` into a dedicated `Settings > AI Platforms` tab with:
  - global platform/family defaults for `Claude Code` and `Codex`
  - detected exact-model rows synthesized from synced sessions across configured projects
  - best-effort provider sync against Anthropic/OpenAI pricing pages with bundled fallback
  - delete support for manual exact-model overrides while protecting required defaults
- Claude/Codex pricing defaults and parser-side fallback estimates were refreshed to current model families and exact-version references.
- Claude Code session context and cost observability tracking now records phase 6 as completed and marks the overall plan set complete.
- Project settings now use typed path-source editors for project roots, plan docs, sessions, and progress paths, with support for local and GitHub-backed plan sources.
- Settings now split integration management into `Integrations > SkillMeat` and `Integrations > GitHub`, including GitHub validation, workspace refresh, and write-capability checks for managed repo workspaces.
- Plan documents can now be edited from the document modal, with local save-in-place support and managed GitHub commit/push write-back for eligible repo-backed plans.

### Docs

- Added:
  - `docs/ai-platforms-pricing-user-guide.md`
  - `docs/session-block-insights-user-guide.md`
  - `docs/session-block-insights-developer-reference.md`
- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/document-entity-user-guide.md`
  - `docs/agentic-sdlc-intelligence-user-guide.md`
  - `docs/agentic-sdlc-intelligence-developer-reference.md`
  - `docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md`
  - `docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md`

## 2026-03-10

### Added

- Claude Code session usage attribution rollout controls:
  - global env gate `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED`
  - project-scoped `usageAttributionEnabled` flag in Project Settings
- User and developer attribution references:
  - `docs/session-usage-attribution-user-guide.md`
  - `docs/session-usage-attribution-developer-reference.md`
- Regression coverage for:
  - attribution feature-flag defaults and overrides
  - attribution-disabled analytics/session behavior
  - workflow-effectiveness rollups carrying attributed token/cost metrics

### Changed

- `/analytics?tab=attribution`, Session Inspector attribution sections, and related session payloads now respect rollout gating instead of assuming attribution is always on.
- Workflow intelligence documentation and rollout notes now treat attribution metrics as additive signals that can be disabled independently from the rest of workflow effectiveness.
- Implementation and PRD tracking for Claude Code session usage attribution V2 now reflect completed delivery status and committed rollout checkpoints.

### Docs

- Added:
  - `docs/session-usage-attribution-user-guide.md`
  - `docs/session-usage-attribution-developer-reference.md`
- Updated:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/agentic-sdlc-intelligence-user-guide.md`
  - `docs/agentic-sdlc-intelligence-developer-reference.md`
  - `docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md`
  - `docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md`

## 2026-03-09

### Added

- Claude Code relay-mirror diagnostics in parser forensics:
  - `usageSummary.relayMirrorTotals` now tracks excluded `data.message.message.*` relay usage separately from observed totals.
- Regression coverage for:
  - relay-mirror exclusion from persisted observed workload.
  - feature-linked session payloads exposing observed/cache/tool-reported token fields.
  - frontend token fallback rules when linked subthreads are present.

### Changed

- Dashboard, Analytics, Session Inspector, Feature Board, and Execution Workbench token surfaces now default to observed workload semantics and label model IO separately.
- Feature and session rollups now expose cache contribution directly instead of implying `tokensIn + tokensOut` is the only meaningful total.
- Commit and artifact-adjacent token tables now label model-IO-style totals explicitly as IO tokens.

### Docs

- Updated:
  - `README.md`
  - `docs/execution-workbench-user-guide.md`
  - `docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md`

## 2026-03-08

### Added

- Agentic SDLC intelligence rollout tooling:
  - `backend/scripts/agentic_intelligence_rollout.py` to sync SkillMeat definitions, backfill stack observations, and recompute workflow rollups.
- Agentic intelligence feature-flag layer:
  - global env gates for SkillMeat integration, stack recommendations, and workflow effectiveness analytics.
  - project-scoped SkillMeat feature flags for the recommended-stack UI and workflow intelligence surfaces.
- Regression coverage for:
  - router disable paths for integrations, execution-context stack recommendations, and workflow analytics.
  - frontend SkillMeat feature-flag helpers.

### Changed

- SkillMeat project settings now expose intelligence-surface toggles in the Settings UI.
- `/execution` and `/analytics` now render explicit disabled-state messaging when project settings turn off stack recommendations or workflow intelligence.
- SkillMeat definition source sync now persists project feature-flag metadata alongside project mappings.

### Docs

- Added:
  - `docs/agentic-sdlc-intelligence-user-guide.md`
  - `docs/agentic-sdlc-intelligence-developer-reference.md`
- Updated:
  - `README.md`
  - `docs/execution-workbench-user-guide.md`
  - `docs/execution-workbench-developer-reference.md`
  - `docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md`

## 2026-03-06

### Added

- Document schema-alignment migration compatibility:
  - legacy root-level superseded schema docs now classify as `spec` for ingestion/backfill compatibility.
  - legacy frontmatter aliases now normalize into canonical fields (for example `test_strategy`, `api_contracts`, `compatibility_notes`, `breaking_changes`, `effort_estimate`, `duration`, `release_target`).
- Rollout coverage for document/feature schema alignment:
  - parser coverage for all canonical document types (`prd`, `implementation_plan`, `phase_plan`, `progress`, `report`, `design_doc`, `spec`, `document`).
  - feature aggregation precedence tests and typed linked-feature source derivation tests.
  - document/feature surface snapshot normalization tests.
  - schema reference hygiene test for superseded spec path references.

### Changed

- Implementation plan status and rollout log for document/feature schema alignment now reflects completed phase 6-7 execution and validation.
- Document schema catalog now includes current rollout status notes for migration compatibility and test coverage.

### Docs

- Updated:
  - `README.md`
  - `docs/document-entity-user-guide.md`
  - `docs/schemas/document_frontmatter/README.md`
  - `docs/project_plans/implementation_plans/refactors/document-feature-schema-alignment-v1.md`

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
- App Impact re-architecture:
  - rebuilt Session Inspector `App Impact` as an outcome/correlation layer using currently captured pipelines (`updatedFiles`, `sessionForensics.testExecution`, linked artifacts/features, queue/API/tool signals).
  - added derived correlation insights, pipeline coverage health panel, and filterable impact event stream.
  - explicitly scoped boundary with `Analytics`: Analytics for resource/behavior telemetry, App Impact for delivery outcomes and inferred conclusions.
- Codex impact event pipeline:
  - Codex parser now emits `impactHistory` events (instead of always empty) from system events, test outcomes, and unmatched tool-result warnings.
  - `ImpactPoint` schema now supports event-first fields with optional legacy numeric impact fields.

### Changed

- Session transcript formatting now supports stronger mapped-event rendering for captured invocation artifacts, including hooks and enriched test runs.
- Session artifact correlation in inspector flows now has stronger linkage between tool logs, mapped transcript cards, artifact groups, and linked sub-thread sessions.
- Session Inspector `Test Status` tab now includes:
  - scrollable `Modified Tests During This Session` list covering all test-file reads/creates/updates/deletes.
  - `Tests Run During This Session` list with one entry per detected test run and parsed result telemetry (framework/status/targets/domains/flags/counts/duration).
- Session `Artifacts` test cards now surface parsed test-run details from correlated source logs so each test artifact can be inspected with run-level metadata.
- Session forensics test-run aggregation now retains full run row history (removed prior run-row truncation).
- Session Inspector header and tab ergonomics:
  - tabs moved to a dedicated full-width row below the title section.
  - added middle Session Context header panel between title and session cost.
  - promoted Linked Feature and Platform into the header context panel.
  - tab ordering updated so `Analytics` follows `Test Status`, and final sequence ends with `Agents`, `Files`, `Activity`.
- Forensics Session Capture:
  - removed duplicate `Platform` field from the Session Capture card now that Platform is promoted to the Session header context panel.

### Fixed

- Fixed unintended `Test Run` labeling regression where non-test shell/tool commands could appear as tests.
  - UI now requires explicit test signals (`testRun` metadata, explicit/inferred test framework, or `toolCategory=test`) before rendering test-run formatting.
- Fixed pytest output parsing gaps for truncated outputs (for example `tail/head` pipelines) by accepting pytest signal patterns without requiring full session headers.

### Docs

- Updated:
  - `README.md`
  - `CHANGELOG.md`
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
