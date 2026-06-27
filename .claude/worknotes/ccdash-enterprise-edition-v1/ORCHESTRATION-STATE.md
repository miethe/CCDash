# Orchestration State — CCDash Enterprise Phase 0+1 (resume after compaction)

## Mission
Implement Phase 0 (Enterprise Liveness Hotfix, P0-001…P0-015 + P0-SEC-CORS) AND Phase 1 (Storage Hygiene & DB Perf, P1-001…P1-019 + P0-012) of the CCDash enterprise edition. User confirmed: **include Phase 1**. On completion: **commit all to branch `feat/ccdash-enterprise-edition-v1`** (already created + checked out).

Effort mode: **ultracode** (xhigh + workflows). Opus orchestrates, subagents implement (CLAUDE.md delegation mandate — never edit code directly).

## Branch
`feat/ccdash-enterprise-edition-v1` — created, checked out. HEAD was 9bcf8e8.

## Key references (read if needed)
- PRD (written): `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`
- Decisions block (written, AUTHORITATIVE task list/anchors/batches/routing): `.claude/worknotes/ccdash-enterprise-edition-v1/decisions-block.md`
- Bundle: `docs/project_plans/planning/ccdash-enterprise-edition-v1/` (00,03,06,07 are key)
- Verify-state outputs (full): `/private/tmp/claude-501/.../tasks/w15392w9i.output` (Phase 0), `w1869rwoh.output` (Phase 1) — may be gone after compaction; the decisions-block.md captured all corrected anchors.

## Resolved §8 decisions (do not re-litigate)
- Worker topology: watch-all folded into default `enterprise` profile.
- Transcript storage: canonical session_messages + filesystem SoT; session_logs DROP behind `CCDASH_DROP_SESSION_LOGS_ENABLED` default OFF, staged after P1-010.
- SQLite dev-only; pragmas gated to SQLite path.
- STARTUP_SYNC_LIGHT_MODE: config.py single SoT (default False); align getattr fallbacks→False; in-container compose default `=true`.
- pgvector:pg17 kept for hosted.

## Verify-state corrections (load-bearing — already in decisions block)
1. CCDASH_WORKER_STARTUP_SYNC_ENABLED is compose-only; real gate = CCDASH_STARTUP_SYNC_ENABLED + worker profile capabilities.sync.
2. No active light-mode mismatch (config always defines attr=False → default startup runs FULL today). Real consumer = adapters/jobs/runtime.py ~:730.
3. worker-watch ingestion override = CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED (compose :169).
4. Drifted anchors: analytics.py get_latest_entries=57-83; entity_graph commit :27 upsert :41; sync_engine delete-by-source :3939.

## Progress / where I am
- [DONE] Task#1 verify-state (both phases). 
- [IN PROGRESS] Task#2 author plan+progress. PRD written. Decisions block written.
- JUST LAUNCHED (foreground Agent calls, results pending when this was written):
  1. `implementation-planner` (sonnet) → expand decisions block into:
     - `docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md` (parent)
     - `.../ccdash-enterprise-liveness-storage-v1/phase-0-liveness.md`
     - `.../ccdash-enterprise-liveness-storage-v1/phase-1-storage.md`
  2. `python-backend-engineer` (sonnet) → create:
     - `.claude/progress/ccdash-enterprise-edition-v1/phase-0-progress.md` (T0-001…, ledger_id=P0-xxx, batches batch_0..3)
     - `.claude/progress/ccdash-enterprise-edition-v1/phase-1-progress.md` (T1-001…, batches batch_0..5, destructive flags)

## NEXT STEPS after compaction
1. Verify the 2 delegations landed: check the 3 plan files + 2 progress files exist on disk (Glob/ls). If missing, re-run that delegation.
2. Mark Task#2 completed; set Task#3 (Phase 0 impl) in_progress.
3. **Phase 0 implementation** — fan out per decisions-block batches:
   - batch_0 (parallel): P0-004,005,006,007,009,014,SEC-CORS
   - batch_1: P0-001 → P0-015 (paired) → P0-008, P0-011
   - batch_2: P0-002, P0-003, P0-010
   - batch_3: P0-013 (e2e smoke)
   Agents: devops-architect (compose/entrypoint/e2e), python-backend-engineer (backend wiring). Verify file edits on disk (NOT TaskOutput) for bg agents. Update progress via CLI: `.claude/skills/artifact-tracking/scripts/update-batch.py`.
4. **Phase 1 implementation** — fan out per batches batch_0..5 (see decisions block). data-layer-expert (schema/retention/indexes) + python-backend-engineer (N+1/batching/badges). Destructive tasks flag-gated default OFF.
   - P0-012 canonical-delete lands in Phase 1 batch_1.
   - P1-015 schema-version bump LANDS LAST.
5. **Validation (Task#5)**: backend unit tests (named files only — pytest collection hangs on unscoped; see memory). Runtime smoke for P1-010 UI surface. e2e smoke (P0-013). MANDATORY task-completion-validator review. Then karen (Tier 3 feature-end).
6. **Commit** all to feat/ccdash-enterprise-edition-v1. Commit message co-authored. Update plan/progress status via manage-plan-status.py + update-field.py (commit_refs).

## Critical conventions
- Tests: run NAMED test files, never `pytest backend/tests` (collection hangs — memory: ccdash-pytest-collection-hangs).
- Venv: backend uses main-repo venv `backend/.venv/bin/python`.
- Runtime smoke gate: UI changes need browser smoke or explicit `runtime_smoke: skipped` + reason.
- Resilience-by-default: every new optional backend field needs FE fallback AC (P1-010 badges, P1-019 project_id).
- CLI-first progress updates (0 tokens): update-status.py / update-batch.py under .claude/skills/artifact-tracking/scripts/.

## TaskList (harness tasks)
#1 verify-state [completed]
#2 author plan+progress [completed]
#3 implement Phase 0 [COMPLETED — 15/15 tasks, 47 tests pass]
#4 implement Phase 1 [in_progress]
#5 validate + commit [blocked by #3,#4]

## PHASE 0 DONE (all on disk, verified: ast OK, imports OK, 47 pass/6 skip)
- compose.yaml: ingestion default true(:27), worker-watch profiles=[enterprise,live-watch](:161), FORCE_POLLING true(:175), projects.json read_only false(:48), LIGHT_MODE=true on worker+worker-watch, frontend depends_on api
- entrypoint.sh: worker-watch) case added
- compose.hosted.yml: overlay header, pgvector/pgvector:pg17, SAM_ENDPOINT empty default
- config.py:246 filesystem_source_of_truth default True; added WORKER_WATCH_PROJECT_ID/WORKER_STARTUP_SYNC_ENABLED/WORKER_WATCH_STARTUP_SYNC_ENABLED + PROJECTS_FILE(reads CCDASH_PROJECTS_FILE)
- project_manager.py: _save() atomic (temp+os.replace); :287 uses config.PROJECTS_FILE
- adapters/jobs/runtime.py:731 light_mode getattr fallback True→False (sync_engine:4262 already False)
- bootstrap.py:57-73 CORS localhost gated to local profile / CCDASH_DEV_CORS
- container.py: T0-003 readyz fail on watch_path_count==0 (configured_no_paths, :554-563); T0-014 enterprise-empty-DB warning (:245-285 + call :109); T0-011 wired
- postgres_migrations.py: T0-011 pg_advisory_lock(7413841953141760) around run_migrations, finally-release, Postgres-only
- source_identity.py: source_identity_policy_from_resolved_paths() (:271); wired in sync_engine.py _build_merged_source_identity_policy (:122-184) at sync_project (:3058), env-wins
- NEW: .github/workflows/enterprise-e2e-smoke.yml; deploy/runtime/test-fixtures/sessions/smoke-session.jsonl; deploy/runtime/scripts/smoke-assert.sh (e2e gate; negative readyz=503 case is commented TODO referencing T0-003)
- progress file phase-0: 15/15 completed, overall_progress 100

## PHASE 1 EXECUTION PLAN (file-exclusive waves to avoid clobbering)
Batches in progress file are dependency-ordered; I re-partitioned by FILE OWNER.
WAVE 1 — DONE (76 pass/6 skip; migration idempotency green; combined import OK). 12 tasks marked complete: T1-004,005,006,008,009,011,012,014,017,018,019,P0012.
  Notes: A1 added _ensure_runtime_indexes() + _ensure_column() helpers in both migration files; idx_analytics_point_daily partial-unique WHERE period='point'; 6 badge cols added to sessions DDL+ALTER. A2: connection.py pragmas (cache -131072/synchronous NORMAL/mmap 256MB/wal_autocheckpoint 1000/temp_store MEMORY) try/except, SQLite-only; canonical delete at 3943/3954; telemetry executemany 1465-1499; manifest skip ~4120-4160; backfill asyncio.gather ~2070-2110. A3: entity_graph.bulk_upsert + base.py Protocol; sessions.add_logs executemany ~730-753; usage_attribution 2x executemany; postgres upsert_file_updates→native ON CONFLICT, upsert_logs kept DELETE+executemany (logs can be removed).
WAVE 1 (parallel, disjoint files) — orig plan:
- A1 data-layer-expert OWNS sqlite_migrations.py+postgres_migrations.py: T1-004,005,012,014,019 + badge cols DDL(for T1-010) + analytics unique idx(project_id,metric_type,date(captured_at)) for T1-001. NO SCHEMA_VERSION bump (wave3).
- A2 python-backend-engineer OWNS sync_engine.py+connection.py: T1-006(pragmas dev-only),017(manifest skip),018(batch backfill),P0012(canonical delete),009-sync(telemetry executemany 1457-1486). NOT T1-007.
- A3 data-layer-expert OWNS repositories/entity_graph.py,sessions.py,usage_attribution.py,postgres/sessions.py,base.py(entitygraph proto): T1-008(bulk_upsert),009-repo,011. NOT analytics.py.
WAVE 2 (after wave1; depends on foundation):
- B1 data-layer-expert OWNS repositories/analytics.py+base.py(analytics proto): T1-001(upsert+prune+Protocol),013(HAVING fix),003-repo(telemetry prune method).
- B2 python-backend-engineer OWNS sync_engine.py: T1-007(N+1 CTE rewrite, self-contained raw query),001-caller(call upsert/prune at 5802),003-sched(call prune from worker).
- B3 python-backend-engineer OWNS repositories/sessions.py+routers/api.py+application/services/sessions.py: T1-010(badge materialize: upsert badges+compute+rewrite GET /api/sessions read 622-628). R-P2 FE-fallback AC + runtime smoke.
WAVE 2 — DONE (32 pass/3 skip; combined import OK; badge upsert COALESCE-preserve seam verified). Marked complete: T1-001,003,007,010,013. progress 85% (17/20).
  Notes: B1 analytics upsert_point_entry + prune_entries/prune_telemetry + get_latest_entries window rewrite + base Protocol. B2 _capture_analytics 12-15K→3 queries; config ANALYTICS_RETENTION_DAYS/TELEMETRY_RETENTION_DAYS/RETENTION_PRUNE_ENABLED(default False); _run_retention_prune from post-sync hook gated. B3 badge materialize lazy+COALESCE-preserve, GET /api/sessions reads materialized cols w/ per-session derive+persist fallback (R-P2), response keys commandSlug/latestSummary/subagentType/modelsUsed/agentsUsed/skillsUsed preserved.
  FOLLOW-UPS for Wave 3: (a) Postgres analytics parity needed in backend/db/repositories/postgres/analytics.py (upsert_point_entry, prune_entries_older_than_days, prune_telemetry_older_than_days, get_latest_entries window rewrite — Postgres syntax (captured_at::date)). (b) eager badge wiring in sync_engine = OPTIONAL (lazy+COALESCE sufficient) — SKIP to avoid another sync_engine edit. (c) P1-SMOKE runtime smoke for session-list UI still required before final.
WAVE 3 (sequential — migration-file serialization):
- C1 python-backend-engineer: T1-002(drop session_logs staged, flag CCDASH_DROP_SESSION_LOGS_ENABLED default OFF; migrate 6 consumers off fallback; gated drop migration). OWNS api.py,services/sessions.py,6 consumers,sqlite_migrations.py(drop path),postgres_migrations.py(drop path).
- C2 data-layer-expert (AFTER C1): T1-016(FTS5 session_messages — DEFER-able) + T1-015(SCHEMA_VERSION bump accounting for ALL phase1 DDL). OWNS sqlite_migrations.py,postgres_migrations.py,repositories/session_messages.py.
Verify on disk between waves (ast.parse + import + grep), NOT via TaskOutput. Update progress via update-batch.py.
6 T1-002 consumers: api.py:626,660,812,844,956; _client_v1_features.py:814,849; feature_forensics.py:167; skillmeat_memory_drafts.py:269.
