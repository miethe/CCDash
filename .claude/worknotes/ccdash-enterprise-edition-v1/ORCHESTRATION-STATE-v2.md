---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash EE v1 — Orchestration State v2 (Phase 3 FUs + Phase 5 + Phase 6 resume)"
status: in_progress
created: 2026-06-01
updated: 2026-06-01
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents]
---

# Orchestration State v2 — finish the edition (resume-after-compaction)

## Mission (user-approved scope, 2026-06-01)
Full remaining roadmap on a worktree off `feat/ccdash-enterprise-edition-v1`:
**Phase 3 follow-ups (BOTH, incl. destructive composite-PK) → Phase 5 (all 16) → Phase 6 (all 13)**.
Merge back to `feat/ccdash-enterprise-edition-v1` + exit worktree when done.
ARC/MeatyWiki = scaffold behind off-by-default capability flags (roadmap default, NOT full depth).
Cmd-K (P5-009 XL) + New Spec (P5-010 L) are P2 → time-box / do last; they can slip per roadmap.

## Environment (LOAD-BEARING)
- Worktree: `/Users/miethe/dev/homelab/development/CCDash/.claude/worktrees/ee-phase-3fu-5-6`
  on branch `feat/ccdash-ee-phase-3fu-5-6` (off feat HEAD 32d0f0e). Session is EnterWorktree'd into it.
  `npm install` done (417 pkgs). Merge target: `feat/ccdash-enterprise-edition-v1`.
- Venv: no venv in worktree — use main-repo `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python`
  with `PYTHONPATH=<worktree>`.
- Tests: explicit files ONLY (unscoped `pytest backend/tests` collection HANGS). Pattern:
  `PYTHONPATH=<worktree> <venv>/python -m pytest backend/tests/test_X.py -p no:cacheprovider --no-header -q`
- NEVER run `test_runtime_bootstrap` in the worktree (hangs — imports backend.main). Run it in the MAIN
  repo (`cd /Users/.../CCDash && ...`) POST-MERGE. Needed for P3-006-FU ports-composition + P6-007.
- DB snapshot taken: `data/ccdash_cache.db.pre-P3003FU.20260601.bak` (10GB, main repo) — forward-only safety.
- FE/UI changes need `npm run dev` browser smoke before `completed` (or explicit `runtime_smoke: skipped`+reason).
- Resilience-by-default: every new optional backend field needs an FE fallback AC.
- task-completion-validator per phase; karen at edition-end (Tier 3).

## Plan refs
- Roadmap: docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md (Phase 5 §458, Phase 6 §540)
- Backlog (task table): .../07-issue-task-backlog.md (Phase 5 §224 P5-001..016; Phase 6 §251 P6-001..013)
- UX/data spec for Phase 5: .../04-planning-command-center-ux-data-spec.md (§7 endpoints, §12 ACs)
- Phase 3 FU detail: .claude/worknotes/ccdash-enterprise-edition-v1/phase-3-status-and-next-pass.md

## CRITICAL correction for P3-003-FU
Live DB + partial-Phase-3 DBs are already at SCHEMA_VERSION=30 (single-column PK, gated path). So the
composite-PK step MUST be a NEW `current_version < 31` block with SCHEMA_VERSION→31, and be idempotent
(no-op if sessions PK already composite). A `<30` block would be skipped by already-30 DBs.

## Status log (updated mid-run)
- [DONE] Phase 3 FUs — committed **a7032dc**. Composite PK SCHEMA_VERSION→31 (13 child tables, idempotent v31,
  foreign_key_check empty); durable queue live (asyncpg repo, drain loop, build_core_ports selects durable when
  JOB_QUEUE_BACKEND!=memory; compose enterprise→postgres). 120 tests pass; phase-exit gate green.
- [DONE] Phase 5 Wave 1 — committed **d0c2f10**. Schema v32 (features.owners_json/linked_docs_json + council_reviews
  + research_notes tables) + contracts (Feature.tokenUsageByModel, ProjectWorkItemCounts token/cost, ARC/MeatyWiki
  capability flags, scaffold model stubs).
- [DONE] Phase 5 Wave 2 — committed **ec6fb3f**. P5-002 (source='backend'), P5-003 portfolio+token rollups,
  P5-004 next-work, P5-008 PR status (fail-soft), P5-012/013 ARC+MeatyWiki scaffolds, P5-015 artifact telemetry.
  177 tests pass (1 PRE-EXISTING OQ-resolver-mock failure on base — unrelated, deselected).
- [IN PROGRESS] Phase 5 Wave 3 (FE) — FE-A (P5-001 runtime cap + portfolio/next-work hooks + 4 lenses) DONE 20/20;
  FE-C (P5-011 real sparkline / P5-016 SSE multi-proj / P5-014 click-through) DONE 21/21; FE-B (P5-006 detail shell
  + P5-007 Artifacts tab + Research/Council empty-states) RUNNING. queryKeys added: capabilitiesKeys.launch(),
  analyticsKeys.artifactRankings(projectId), multiProjectPlanningKeys.portfolioRollup/nextWork.
  NEXT after FE-B: consolidated tsc --noEmit + vitest, then MANDATORY FE runtime smoke (npm run dev + browser
  localhost:3000 — fresh/empty worktree DB is fine; do NOT migrate the live 10GB DB), then commit Wave 3.
- [PENDING] Phase 5 Wave 4 — P5-009 Cmd-K + P5-010 New Spec (time-boxed P2; New Spec needs a NEW POST scaffold
  endpoint — minimal or descope to stub if budget low).
- [PENDING] Phase 6 — OTEL/retention/partitioning/load-test/e2e-gate/CORS(check P0-SEC-CORS)/unskip-FU004/SSE-smoke/
  publish-isolation/docs. P6-007 + P3-006-FU ports test = run test_runtime_bootstrap in MAIN repo POST-MERGE.
- [PENDING] Merge to feat/ccdash-enterprise-edition-v1 (squash), test_runtime_bootstrap in MAIN repo, karen review,
  ExitWorktree(keep) + `git worktree remove`. NOTE: 1 pre-existing failing test (test_planning_query_service.py::
  ResolveOpenQuestionServiceTests::test_resolve_open_question_updates_overlay_and_sets_otel_success) fails on base too.

## Phase 5 task inventory (P0 first)
P0: P5-001 runtime capability flag (replace Vite build-time const); P5-002 tokenUsageByModel on Feature
(fix PlanningTokenTelemetry.source=unavailable); P5-003 cross-project token/cost rollup endpoint;
P5-004 ranked next-work endpoint.
P1: P5-005 Feature.data_json→columnar (forward-only migration); P5-006 deep-link /planning/feature/:id +
lazy per-tab shell; P5-007 SkillMeat artifacts tab (surface existing data); P5-008 live PR status (cached,
fail-soft, capability-gated); P5-011 real sparklines/tokensSaved (no fictions); P5-016 SSE → session board+CC.
P2: P5-009 Cmd-K (XL, last); P5-010 New Spec (L, last); P5-012 ARC scaffold (flag-gated empty-state);
P5-013 MeatyWiki scaffold (flag-gated); P5-014 attention click-through beyond ROW_LIMIT=8; P5-015 emit
ArtifactVersionOutcomePayload.

## Phase 5 owner-batch DAG (synthesized from 4 recon maps — file-ownership = parallel-safety)
Capabilities endpoint = `GET /api/execution/launch/capabilities` → routers/execution.py:282 → models.py:3034 LaunchCapabilitiesDTO
(already has multiProjectCommandCenterEnabled=False). Add arcEnabled/meatyWikiEnabled (env-driven, default OFF, config._env_bool).
Route /planning/feature/:id ALREADY exists (App.tsx:112 → PlanningNodeDetail, NOT tabbed). lib/planning-routes.ts does
NOT exist — it's services/planningRoutes.ts. Capabilities NOT read for MPCC today (build-time const in constants.ts:420).

WAVE 1 (parallel, file-disjoint) — schema + contracts:
- W1-SCHEMA (data-layer-expert): ONE v32 bump. P5-005 (owners_json+linked_docs_json cols+backfill+GIN; tags_json
  already done; phases already in feature_phases table) + P5-012 council_reviews DDL + P5-013 research_notes DDL.
  OWNS: sqlite_migrations.py, postgres_migrations.py, repositories/features.py, repositories/postgres/features.py.
- W1-CONTRACTS (python-backend-engineer): P5-002 Feature.tokenUsageByModel field; P5-003 ProjectWorkItemCounts
  +total_tokens/+total_cost; capability flags arcEnabled/meatyWikiEnabled (config.py + LaunchCapabilitiesDTO +
  execution.py constructor + execution.ts interface); CouncilReview + ResearchNote model stubs.
  OWNS: models.py, config.py, routers/execution.py, services/execution.ts (interface only).

WAVE 2 (parallel after W1; file-disjoint) — services/endpoints:
- W2-ROLLUPS (python-backend-engineer) OWNS agent.py + system_metrics.py + MPCC + planning.py + NEW planning_next_work.py:
  P5-002 planning.py _build_token_telemetry fix (drop getattr guard, populate Feature.tokenUsageByModel at repo/context
  read; source="backend"); P5-003 portfolio rollup `GET /api/agent/planning/portfolio/rollup` + token rollup
  `GET /api/agent/system/token-rollup` (system_metrics GROUP BY project_id,model_family; Semaphore(10); @memoized_query);
  P5-004 `GET /api/agent/planning/next-work` (REUSE _build_items_for_scope/_matches_filters/_sort_items; cursor over
  (updated_at,id)); ALSO adds the P5-012 council route `GET /api/agent/features/{id}/council` (calls W2-SCAFFOLDS service).
- W2-SCAFFOLDS (python-backend-engineer) OWNS planning_command_center.py + github_client.py + integrations.py + main.py +
  NEW council/research repos+services: P5-008 live PR status (`GET /api/agent/planning/features/{id}/pr-status`; aiohttp
  GitHub fetch, cached ~60s, fail-soft to stored ref, capability-gated on GitHubIntegrationSettings.token; _pr_dto async);
  P5-012 council repo+query-service (empty-state when CCDASH_ARC_ENABLED off); P5-013 research repo+query-service +
  meatywiki router `GET /api/integrations/meatywiki/research` + register in main.py (empty-state when off).
- W2-TELEMETRY (python-backend-engineer) OWNS workflow_effectiveness.py + artifact_ranking_repository.py +
  telemetry_exporter.py: P5-015 propagate content_hash from ranking evidence_json.snapshot.contentHash so
  ArtifactVersionOutcomePayload emits (path ~90% wired; data-density fix only).

WAVE 3 (FE; #4 first to own queryKeys.ts, then #5∥#6) — needs Wave 2 endpoints:
- W3-CAP (ui-engineer-enhanced) OWNS services/queryKeys.ts (ALL new keys: capabilities + artifactRankings) +
  services/queries/planning.ts (gating) + CommandCenter/PlanningCommandCenter.tsx + NEW queries/capabilities hook:
  P5-001 runtime capability flag — useLaunchCapabilitiesQuery (staleTime 60s); replace build-time const at planning.ts
  473/521 + PlanningCommandCenter.tsx 78-106; default mode 'multi' when caps.multiProjectCommandCenterEnabled.
- W3-DETAIL (ui-engineer-enhanced, after W3-CAP) OWNS NEW components/Planning/FeatureDetailShell.tsx + App.tsx:112
  (1-line element swap) + services/planningRoutes.ts (FEATURE_DETAIL_TABS) + services/queries/analytics.ts (rankings
  hook using key from W3-CAP): P5-006 lazy per-tab shell (Overview/Plan/Tasks/Sessions/Artifacts/Research/Council/Logs/
  Decisions/Blockers/Next — Overview eager+shared context, rest lazy-on-activate; Sessions/Logs cursor+virtualized, never
  bulk); P5-007 Artifacts tab (reuse ArtifactRankingsView); Research/Council tabs = capability-gated empty-states.
- W3-HOME (ui-engineer-enhanced, ∥ W3-DETAIL) OWNS PlanningHomePage.tsx + PlanningSummaryPanel.tsx: P5-011 replace
  synthesized sparkline (use useDashboardChartQuery task_velocity daily) + DELETE tokensSavedPct (no real source);
  P5-016 onInvalidate also invalidate multiProjectPlanningKeys.all(); P5-014 AttentionColumn +N more → onSeeAll(bucket)
  → setStatusBucket (beyond ROW_LIMIT=8).

WAVE 4 (LAST, time-boxed P2) — UX net-new:
- W4-UX (ui-engineer-enhanced) OWNS PlanningTopBar.tsx + NEW CommandPalette + (backend) NEW spec-create endpoint:
  P5-009 Cmd-K real palette (query GET /api/v1/features?q + /api/v1/sessions/search + /api/documents?q; single-project
  first, cross-project fan-out optional); P5-010 New Spec (needs NEW POST scaffold-to-disk endpoint — minimal; if budget
  low, descope to documented stub). LOWEST priority — may slip per roadmap.

ACs (doc04 §12): AC-1 portfolio default 4 lenses ≤2 cold reqs + viewport-defer; AC-2 runtime gate no rebuild; AC-3 modal
+ /feature/:id share TQ cache (hover-prefetch, no double-fetch); AC-4 transcripts per-session-on-click, cursor+virtualized;
AC-5 tokenTelemetry.source=="backend" (FE fallback if absent — resilience); AC-6 Research/Council/Artifacts capability-gated
empty-states; AC-7 next-work from real readiness/dependency, no fictions.
FE runtime-smoke gate MANDATORY before Phase 5 completed.

## Phase 6 task inventory
P0: P6-002 scheduled retention+VACUUM/ANALYZE job; P6-004 skillmeat-scale load test; P6-005 container e2e CI gate.
P1: P6-001 OTEL instruments (9); P6-003 PG time-series partitioning; P6-006 CORS honor FRONTEND_ORIGIN
(check: P0-SEC-CORS may already cover); P6-008 wire-boundary SSE smoke (dep P3-014 done); P6-009 publish-exception
isolation; P6-013 doc container_project_onboarding.py.
P2: P6-007 un-skip FU-004 bootstrap tests (run in MAIN repo); P6-010 confirm live-fanout OTEL; P6-011 doc
_COMPACT_PAYLOAD_KEYS; P6-012 fix PRD status drift (manage-plan-status.py).

## Phase 6 owner-batch DAG (synthesized from 2 recon maps)
ALREADY SATISFIED (mark complete, NO code): P6-006 CORS (bootstrap.py:61-76 honors CCDASH_FRONTEND_ORIGIN +
gates localhost behind dev flag); P6-010 live-fanout OTEL (all 4 instruments exist+emit: otel.py:415/421/431/425;
P3-014 reconnect confirmed).
DEFER w/ rationale: P6-003 PG partitioning — NOT additive (TEXT captured_at/occurred_at, SERIAL PK, FK from
analytics_entity_links, unique-partial idx_analytics_point_daily). Destructive rewrite → needs dedicated spike.
P6-002 retention + existing indexes already bound growth. Document the defer; don't force it.
TRIVIAL (Opus via CLI): P6-012 — manage-plan-status.py on planning-command-center-v1 + enterprise-live-session-ingest-v1
(both stuck status: draft; AAR exists → set shipped/completed).

WAVE A (foundational): A1 (python-backend-engineer) OWNS backend/observability/otel.py — add ~7 new instruments +
record_ helpers (pattern: module global _x=None, declare in initialize(), meter.create_*, Prom mirror, record_* with
try/except). Net-new (others already exist): (1) analytics-snapshot duration+rows, (2) badge-derive latency, (3) sync
INSERT batch counter, (4) fingerprint duration histogram, (6) sqlite cache-miss GAUGE (counter exists), (7) startup-sync
duration, (8) feature-poll-interval gauge, (9) link-rebuild COMMIT counter (scope counter exists). Payload-bytes(5)
already done for feature-surface.

WAVE B (parallel after A1; file-disjoint):
- B1 (python-backend-engineer) OWNS backend/db/sync_engine.py: P6-001 call-sites — analytics duration/rows (~2779/5939),
  INSERT batch (~1545), startup-sync duration (~3218), link-rebuild commit (~3375); P6-009 wrap the 8 publish_* calls
  (3249,3256,3380,3387,3479,3485,4162,4169) in try/except (log+continue, never abort sync).
- B2 (python-backend-engineer) OWNS routers/api.py + routers/cache.py + application/services/agent_queries/cache.py:
  P6-001 badge latency (api.py:692 slow path), fingerprint duration (cache.py:634), sqlite cache-miss gauge (cache.py:1180).
- B3 (python-backend-engineer) OWNS adapters/jobs/runtime.py + config.py: P6-002 _start_retention_prune_task() (~after :260,
  guard RETENTION_PRUNE_ENABLED, default 24h; calls prune_entries_older_than_days + _prune_telemetry_events + VACUUM/ANALYZE
  — PG: VACUUM(ANALYZE) per-table outside txn; SQLite: VACUUM only); P6-001 feature-poll-interval gauge (~runtime.py:1087).
- B4 (python-backend-engineer) OWNS NEW backend/tests/test_skillmeat_scale_load.py + NEW SSE wire test + bootstrap.py +
  test_runtime_bootstrap.py: P6-004 load test (@pytest.mark.perf, in-memory mock like test_cold_start_benchmark.py;
  ingest+bundle+multi-proj fan-out p95); P6-008 NOTIFY→listener→broker→SSE end-to-end test (fake asyncpg fire_notification
  + httpx AsyncClient on /api/live/stream); P6-007 un-skip FU-004 (fields exist bootstrap.py:185/233/302-303; remove skips
  616/680/716/1057; leave 1333 with justified code comment — macOS Mach-port leak needs subprocess harness).
  ⚠️ B4 must NOT run test_runtime_bootstrap in worktree (hangs) — Opus runs it in MAIN repo POST-MERGE to validate P6-007 + P3-006-FU.
- B5 (general/docs) OWNS .github/workflows/enterprise-e2e-smoke.yml + deploy/runtime/scripts/smoke-assert.sh +
  docs + bus.py docstring: P6-005 uncomment smoke-no-paths job (T0-003 landed) + broaden path filter to backend/** +
  document that branch-protection must mark it required (can't set via repo); P6-011 expand _COMPACT_PAYLOAD_KEYS contract
  (bus.py:23-30 docstring or new docs/live-events guide); P6-013 expand containerized-deployment-quickstart.md to frame
  container_project_onboarding.py as a required pre-deploy step + flag reference.
