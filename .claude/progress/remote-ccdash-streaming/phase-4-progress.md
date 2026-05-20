---
schema_version: 2
doc_type: progress
type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 4
phase_title: Workspace Auth + Multi-Project Routing
status: in_progress
created: '2026-05-20'
updated: '2026-05-20'
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
adr_refs:
- docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md
- docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
- docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md
spike_ref: docs/project_plans/spikes/remote-ccdash-streaming.md
commit_refs: []
pr_refs: []
owners:
- backend-architect
- data-layer-expert
contributors:
- python-backend-engineer
execution_model: batch-parallel
overall_progress: 0
completion_estimate: on-track
total_tasks: 10
completed_tasks: 3
in_progress_tasks: 2
blocked_tasks: 0
runtime_smoke: pending
runtime_smoke_reason:
  Backend-only phase. Batch 3 (T4-004/T4-005) partial: 128 remaining failures (74
    TestClient auth-override + 49 db-lock + 5 misc). Batches 1+2 (security gate) green
    (69/69). Phase NOT complete.
tasks:
- id: T4-001
  description: "Schema migration for workspace-scoped auth + scoping. Add `workspaces`\
    \ table\n(workspace_id PK, name, status, created_at) and `workspace_tokens` table\n\
    (token_id PK, workspace_id, project_id, hashed_token UNIQUE, scope,\ncreated_at,\
    \ last_used_at, revoked_at, description) with partial indexes\n`ix_workspace_tokens_workspace`\
    \ and `ix_workspace_tokens_hash` over\n`revoked_at IS NULL` rows (ADR-008 \xA7\
    Schema). Add NOT NULL `workspace_id TEXT`\ncolumn to every scoped table: sessions,\
    \ documents, tasks, features, links,\nprogress_files, ingest_cursors. Backfill\
    \ `default-local` workspace row plus\none workspace_token row equivalent to today's\
    \ CCDASH_AUTH_TOKEN; backfill\n`workspace_id = 'default-local'` on all existing\
    \ rows. Migration must be\nidempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE\
    \ \u2026 ADD COLUMN IF NOT\nEXISTS` or guarded via PRAGMA-style introspection\
    \ for SQLite); reversible\nby drop-and-revert. Use existing migration runner under\
    \ `backend/db/migrations`.\nNOTE: do NOT use Argon2 hashing in migration backfill\
    \ \u2014 the migration\ninserts a single token row whose plaintext equals the\
    \ legacy\nCCDASH_AUTH_TOKEN; T4-006 hashes when present. For the bootstrap row,\n\
    store the argon2id hash of the current env token (the auth backend rejects\nraw\
    \ equality).\n"
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies: []
  evidence:
  - file: backend/db/sqlite_migrations.py
  - file: backend/db/postgres_migrations.py
  - file: backend/tests/test_migrations_v29.py
  - test: backend/tests/test_migrations_v29.py
  verified_by:
  - T4-007
  started: '2026-05-20T16:00:00Z'
  completed: '2026-05-20T17:30:00Z'
- id: T4-002
  description: "Implement `AuthContext` dataclass and `WorkspaceTokenAuthBackend`\
    \ (replacement\nin `api`/`worker` profiles; `local` profile keeps `SingleBearerAuthBackend`).\n\
    Location: `backend/adapters/auth/workspace_token.py` plus refactor of\n`backend/adapters/auth/bearer.py:22,\
    \ 74-109`.\n\nAuthContext = (workspace_id, project_id, token_id, scope). Backend\
    \ MUST:\n(a) argon2id-verify inbound bearer against `workspace_tokens.hashed_token`\n\
    \    rows where `revoked_at IS NULL`;\n(b) cache `(secret_fingerprint -> AuthContext)`\
    \ in a process-local LRU\n    (size 256, TTL 60s) keyed by SHA-256(secret) \u2014\
    \ never store the secret\n    plaintext. On revocation event (T4-002b in same\
    \ task), invalidate by\n    token_id. The LRU is short-TTL specifically because\
    \ the 1-request\n    revocation gate (ADR-008 hard gate #2) requires a revoked\
    \ token to\n    fail on its very next use \u2014 therefore on each LRU hit, re-check\n\
    \    `revoked_at IS NULL` against the DB in a single index lookup OR drop\n  \
    \  the LRU entirely if benchmark shows argon2 verify <10ms (see ADR-008\n    Risks);\n\
    (c) attach AuthContext to `request.state.auth_context` for downstream\n    dependencies;\n\
    (d) update `last_used_at` asynchronously (do not block request);\n(e) log only\
    \ the first 6 chars of any secret \u2014 never the full bearer;\n(f) honor `x-ccdash-project-id`\
    \ ONLY if it equals `AuthContext.project_id`;\n    mismatch returns 403 with code\
    \ `workspace_project_mismatch`;\n(g) reject `401` with code `invalid_token` on\
    \ miss; reject `401` with\n    code `revoked_token` when match exists but `revoked_at\
    \ IS NOT NULL`.\n\nWire as FastAPI dependency `get_auth_context(request) -> AuthContext`;\n\
    register in api/worker runtime profiles only. Local profile retains\nlegacy bearer\
    \ guard for backwards compat (synthesizes AuthContext with\n`workspace_id=\"default-local\"\
    `, `project_id=runtime_container.bound_project`).\n"
  status: completed
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  dependencies:
  - T4-001
  evidence:
  - file: backend/adapters/auth/context.py
  - file: backend/adapters/auth/workspace_token.py
  - file: backend/adapters/auth/dependency.py
  - test: backend/tests/test_workspace_token_auth.py
  verified_by:
  - T4-008
  started: '2026-05-20T17:30:00Z'
  completed: '2026-05-20T19:30:00Z'
- id: T4-003
  description: "Refactor `RuntimeContainer` (backend/runtime/container.py:67) to support\n\
    request-scoped multi-project binding per ADR-010. Replace\n`bound_project: ProjectBinding`\
    \ (startup-time, single) with\n`resolve_binding(project_id: str) -> ProjectBinding`\
    \ backed by an\nin-process LRU (maxsize 64). `ProjectBinding` is an immutable\
    \ dataclass:\n(project_id, project_meta, paths: ProjectPathResolver, storage:\n\
    ScopedStorageFacade). Bindings are lazy \u2014 never pre-populated.\n\nAdd FastAPI\
    \ dependency `get_project_binding(auth: AuthContext = Depends(\nget_auth_context),\
    \ container: RuntimeContainer = Depends(get_container))\n-> ProjectBinding`. Worker\
    \ profile (`backend/worker.py`,\n`backend/runtime/runtime.py:107-127`) retains\
    \ startup-time single-project\nbinding for now \u2014 multi-project workers are\
    \ out-of-scope for v1 (ADR-010\n\xA7Decision).\n\nDeprecate `x-ccdash-project-id`\
    \ as a routing input: log a deprecation\nwarning when present; honor it only as\
    \ an equality assertion against\n`AuthContext.project_id` (already enforced in\
    \ T4-002). Update the\n`workspace_tokens` row resolver to be the single source\
    \ of routing.\n\nCache invalidation surface: `RuntimeContainer.evict_binding(project_id)`\n\
    for use by project-rename or project-delete admin paths (callers TBD).\n\nSmoke:\
    \ confirm api profile boots and serves at least 2 projects under\ndifferent tokens\
    \ in a single test.\n"
  status: completed
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  dependencies:
  - T4-001
  evidence:
  - file: backend/runtime/container.py
  - file: backend/runtime/dependencies.py
  - test: backend/tests/test_runtime_container_routing.py
  verified_by:
  - T4-008
  started: '2026-05-20T17:30:00Z'
  completed: '2026-05-20T19:30:00Z'
- id: T4-004
  description: "Workspace scoping wave 1 \u2014 sessions + documents + tasks + features\n\
    repositories. Every method that returns scoped data takes an explicit\n`workspace_id:\
    \ str` parameter (NOT a default-None; callers must pass it).\nEvery SQL SELECT/UPDATE/DELETE\
    \ adds `WHERE workspace_id = :workspace_id`.\nMutators (insert/upsert) accept\
    \ `workspace_id` and write it.\n\nFiles: backend/db/repositories/sessions.py,\n\
    backend/db/repositories/documents.py,\nbackend/db/repositories/tasks.py,\nbackend/db/repositories/features.py.\n\
    \nThread `workspace_id = auth.workspace_id` from each router/service caller\n\
    site. Routers that already accept a Depends(get_auth_context) get the\nAuthContext\
    \ injected; pass `auth.workspace_id` into the repository.\n\nAll existing tests\
    \ under backend/tests/ continue passing \u2014 supply\n`workspace_id=\"default-local\"\
    ` everywhere the test factory creates\nfixtures, via a shared fixture helper.\n"
  status: in_progress
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies:
  - T4-001
  - T4-002
  evidence: []
  verified_by: []
- id: T4-005
  description: "Workspace scoping wave 2 \u2014 links + progress_files + ingest_cursors\n\
    repositories, plus analytics + cache surfaces.\n\nFiles: backend/db/repositories/links.py,\n\
    backend/db/repositories/analytics.py,\nbackend/db/repositories/base.py (if a common\
    \ helper is needed),\nplus the progress-file repository wherever it lives\n(codebase-explorer\
    \ to identify) and the cursor repo\n(`backend/db/repositories/ingest_cursors.py`\
    \ per Phase-2 work).\n\nSame contract as T4-004: explicit `workspace_id` parameter,\
    \ WHERE\npredicate on every query, mutator writes the column.\n\nSpecific care\
    \ for `ingest_cursors`: ADR-009 stores cursors keyed by\n(source_id, project_id);\
    \ v1 binds 1 token to 1 project so cursor lookups\nnaturally select rows whose\
    \ `workspace_id = auth.workspace_id`. Add the\npredicate as defense-in-depth.\
    \ The ingest router (Phase 3) must thread\n`auth.workspace_id` into the cursor\
    \ advance and dedup paths.\n"
  status: in_progress
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies:
  - T4-001
  - T4-002
  evidence: []
  verified_by: []
- id: T4-006
  description: "Implement `backend/scripts/migrate_bearer_to_workspace_token.py` per\n\
    ADR-008 \xA7Migration Path. Idempotent: running twice does nothing the\nsecond\
    \ time. CLI: `python -m backend.scripts.migrate_bearer_to_workspace_token`\nwith\
    \ optional `--token VALUE` (default reads CCDASH_AUTH_TOKEN env),\n`--workspace\
    \ default-local`, `--project <current bound>`. Steps:\n(1) ensure `default-local`\
    \ workspace row exists;\n(2) compute argon2id hash of the token; insert `workspace_tokens`\
    \ row if\n    no existing row has the same hash AND `revoked_at IS NULL`;\n(3)\
    \ print `token_id` and the next-step instructions (env-var swap);\n(4) exit 0\
    \ on success / no-op; exit non-zero only on DB error.\n\nReversible: emit `rollback.sql`\
    \ next to the script with DROP statements\nfor the two new tables and ALTER ...\
    \ DROP COLUMN for the seven\n`workspace_id` columns (SQLite limitation: column\
    \ drop requires table\nrebuild \u2014 document this caveat at top of rollback.sql).\n\
    \nAdd `auth_mode: \"workspace_token\" | \"single_bearer\"` to the health\nendpoint\
    \ response so operators can verify the post-migration state.\n"
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T4-001
  - T4-002
  evidence: []
  verified_by: []
- id: T4-007
  description: "Reflection test `backend/tests/test_workspace_scoping.py` per ADR-008\n\
    Risks \xA71. Test walks every public method on every class under\n`backend/db/repositories/`\
    \ and asserts:\n(a) if the method name does not start with `_` and is not in a\
    \ small\n    explicit exemption set (factory helpers, schema introspection\n \
    \   utilities \u2014 list each by name with a justification comment),\n    the\
    \ method MUST accept a `workspace_id` parameter (positional or\n    keyword);\n\
    (b) the method's source (via inspect.getsource) contains either the\n    literal\
    \ `workspace_id` predicate substring OR delegates to a helper\n    that does (e.g.,\
    \ `_scope(query, workspace_id)`).\n\nThe test is the safety net for new repo methods\
    \ \u2014 any future PR that\nadds a method without the predicate fails CI. Document\
    \ the exemption\nprocess at top of the file. Run via `pytest backend/tests/test_workspace_scoping.py\
    \ -v`.\n"
  status: pending
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T4-004
  - T4-005
  evidence: []
  verified_by: []
- id: T4-008
  description: "Integration tests for ADR-008 hard gates. New file\n`backend/tests/test_workspace_auth_integration.py`\
    \ exercising the FastAPI\nTestClient against the api runtime profile:\n(1) cross-workspace\
    \ read attempt returns 403 on direct query (GET\n    /api/sessions/<id> where\
    \ id belongs to workspace B and token is\n    workspace A) and returns an empty\
    \ list on list endpoints (GET\n    /api/sessions with workspace A token sees only\
    \ A's rows);\n(2) revoked token rejected on next use \u2014 issue request, revoke\
    \ token in\n    DB, issue request again, assert 401 with code `revoked_token`;\n\
    (3) `x-ccdash-project-id` mismatch returns 403 with code\n    `workspace_project_mismatch`;\n\
    (4) migration script idempotency \u2014 fresh DB and already-migrated DB both\n\
    \    yield exit 0 and identical post-state row counts;\n(5) `auth_mode` health\
    \ probe returns `workspace_token` in api profile and\n    `single_bearer` in local\
    \ profile.\n\nUse existing test fixtures from backend/tests/conftest.py; extend\
    \ the\nDB fixture with two workspaces (alpha, beta) and tokens for each.\n"
  status: pending
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  dependencies:
  - T4-004
  - T4-005
  - T4-006
  evidence: []
  verified_by: []
- id: T4-009
  description: "Operator-facing surface: write `docs/guides/auth-modes.md` per ADR-008\n\
    Risks \xA7\"Operator confusion\". Covers: when each auth backend is used\n(profile\
    \ \u2192 backend mapping), token rotation playbook, revocation flow,\nmigration\
    \ steps from single-bearer to workspace tokens, daemon.toml\ntoken storage permissions\
    \ (mode 0600). Cross-reference ADR-008 and\nADR-010. Update `docs/guides/cli-timeout-debugging.md`\
    \ only if a new\nauth-related timeout/error surfaces.\n\nAlso: extend health endpoint\
    \ payload \u2014 add `auth_mode` field\n(`workspace_token` | `single_bearer`).\
    \ Update OpenAPI schema if the\nhealth endpoint has one. Mention in the existing\
    \ health-endpoint guide.\n"
  status: pending
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  dependencies:
  - T4-006
  - T4-008
  evidence: []
  verified_by: []
- id: T4-010
  description: "Phase exit validation. Run:\n(1) `backend/.venv/bin/python -m pytest\
    \ backend/tests/ -v` \u2014 full backend\n    suite passes;\n(2) `python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py\n\
    \    -f .claude/progress/remote-ccdash-streaming/phase-4-progress.md`;\n(3) `python\
    \ .claude/skills/artifact-tracking/scripts/ac-coverage-report.py\n    --plan docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md\n\
    \    --progress .claude/progress/remote-ccdash-streaming/phase-4-progress.md`;\n\
    (4) Senior code review via senior-code-reviewer agent on the diff\n    (security-critical\
    \ phase per implementation plan \xA7Subagent Assignments).\n(5) Capture pytest\
    \ output count + green test summary as evidence.\n\nMark phase status=completed\
    \ only after all four pass. Record evidence\nin this progress file's tasks via\
    \ update-status.py with --evidence.\n"
  status: pending
  assigned_to:
  - task-completion-validator
  - senior-code-reviewer
  assigned_model: sonnet
  dependencies:
  - T4-007
  - T4-008
  - T4-009
  evidence: []
  verified_by: []
parallelization:
  batch_1:
  - T4-001
  batch_2:
  - T4-002
  - T4-003
  batch_3:
  - T4-004
  - T4-005
  batch_4:
  - T4-006
  - T4-007
  batch_5:
  - T4-008
  - T4-009
  batch_6:
  - T4-010
progress: 30
---

# Phase 4: Workspace Auth + Multi-Project Routing — Progress

## Scope (from implementation plan §Phase 4 + ADR-008 / ADR-010)

- Per-workspace token table (`workspace_tokens`) with argon2id-hashed bearer
  tokens; resolves to `(workspace_id, project_id)`.
- `AuthContext{workspace_id, project_id, token_id, scope}` injected into every
  authenticated request via FastAPI dependency.
- All repository methods that touch session / document / task / feature / link
  / progress / cursor data add a mandatory `workspace_id` parameter and
  `WHERE workspace_id = :workspace_id` predicate (explicit filtering; RLS
  deferred to v2 per ADR-008 §Workspace Scoping Enforcement).
- `RuntimeContainer` refactored to `resolve_binding(project_id)` with LRU
  cache; per-request project binding driven from `AuthContext.project_id`.
- `x-ccdash-project-id` header demoted from routing input to equality
  assertion against `AuthContext.project_id`; mismatch = 403.
- Migration script `migrate_bearer_to_workspace_token.py` upgrades existing
  single-tenant deployments idempotently.

## Hard Gates (ADR-008 E3)

| Gate | Verified by |
|---|---|
| Cross-workspace read returns 403 (direct) or empty (list) | T4-008 §1 |
| Revoked token rejected within 1 request | T4-008 §2 |
| Migration script is idempotent | T4-006, T4-008 §4 |
| Legacy single-bearer in `local` profile unchanged | T4-002 (local-path retention) + existing CI |
| `x-ccdash-project-id` cannot widen scope | T4-008 §3 |
| Every scoped repo method takes `workspace_id` | T4-007 reflection test |

## Batching Notes

- Batch 1 is sequential gating: schema must land before auth backend or repo
  scoping can compile.
- Batch 2 (auth backend + container refactor) is parallel — distinct files,
  distinct ownership.
- Batch 3 (repo scoping) is split across two waves by file family to keep
  reviewer load tractable. No parallel edits to the same file.
- Batch 4 (migration script + reflection test) is independent of Batch 5 and
  can begin as soon as Batch 3 is in.
- Batch 5 (integration tests + operator docs) is the validation surface.
- Batch 6 is the validator gate.

## Out of Scope (deferred)

- OIDC / OAuth migration — v2 (ADR-008 §Non-Goals).
- mTLS — v2.
- Postgres RLS — v2 (explicit-filter v1 is forward-compatible).
- Worker-profile multi-project routing — v1 worker stays single-project per
  ADR-010 §Decision.
- Token expiration / TTL — v1 tokens are revoked manually.

## Batch 3 partial-completion blockers (2026-05-20)

Batch 3 (T4-004 + T4-005) landed the repository workspace-scoping change but
left **128 backend test failures** uncovered. Pre-Phase-4 baseline was ~22
pre-existing failures, so Phase 4 introduced ~106 net new failures across
these clusters:

| Cluster | Count | Root cause | Fix shape |
|---|---|---|---|
| TestClient routes returning 401 (JSONDecodeError / 401 body) | ~64 | Routes use `Depends(get_auth_context)`; test fixtures don't override the dependency to return `AuthContext.synthesize_local(...)` | Wire `app.dependency_overrides[get_auth_context]` in each TestClient fixture (test_client_v1_contract.py, test_test_visualizer_router.py, test_client_v1_write_paths.py, test_client_v1_feature_surface.py, test_features_router_linked_sessions.py, test_features_router_aliases.py, test_feature_forensics_endpoint_agreement.py, test_analytics_router.py, test_artifact_intelligence_phase6_contracts.py) |
| `database is locked` errors | ~10 | Concurrent TestClient lifecycle interaction with aiosqlite singleton; surfaced after Batch 3 caller updates | Investigate aiosqlite connection scoping in `backend/db/connection.py` + test fixtures; likely unrelated to Phase 4 but exposed by it |
| Direct repo calls still missing `workspace_id` | ~30 | Test fixup agents hit "Prompt is too long" and did not finish updating every `.upsert()` / `.list_paginated()` / `.list_*` / `.count_*` / `.get_*facets()` caller | Mechanical: add `workspace_id="default-local"` to remaining call sites in: test_repositories_bulk_fetch.py, test_sessions_source_ref.py, test_mapping_resolver.py, test_feature_list_query.py (~2 remaining), test_features_repository.py, test_phase3_repository_migration.py, etc. |
| New regressions introduced by fixup | ~3 | Agent passed `workspace_id` to functions that don't accept it (workflow_registry.py:880) and removed required args from a session_ingest_service call (line 121, 160) | Revert those specific edits |

### Batches still passing (security gate intact)

- T4-001 migration v29: 36/36 green
- T4-002 WorkspaceTokenAuthBackend: 33/33 green
- T4-003 RuntimeContainer.resolve_binding: 33/33 green (with T4-002)
- Phase 4 contract surfaces: AuthContext frozen dataclass, argon2id verify, LRU + revocation, x-ccdash-project-id equality assertion, ProjectBinding LRU — all present and tested.

### Recommended next session

1. Single focused fixup pass — wire `app.dependency_overrides[get_auth_context]` in all listed TestClient fixtures (one mechanical sweep).
2. Investigate the "database is locked" cluster — likely a test isolation issue, may need `aiosqlite` connection-per-fixture.
3. Revert the two non-test regressions in `backend/services/workflow_registry.py:880` and `backend/ingestion/session_ingest_service.py:121,160`.
4. Re-run full suite; expect green except the ~22 pre-existing failures.
5. Then proceed to T4-006 (migration script), T4-007 (reflection test), T4-008 (integration tests), T4-009 (docs), T4-010 (validation).

### Why this session stopped here

Three consecutive `Agent` delegations hit the "Prompt is too long" cap mid-work,
producing partial commits and surfacing additional regressions. Continuing the
fixup loop was yielding sub-linear progress (231 → 140 → 128 failures across
three rounds while introducing new regressions). Stopping and committing the
substantial in-progress work preserves the security-gate landing while making
the remaining repair scope visible.
