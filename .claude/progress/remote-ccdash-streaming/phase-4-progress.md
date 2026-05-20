---
schema_version: 2
doc_type: progress
type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 4
phase_title: Workspace Auth + Multi-Project Routing
status: pending
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
in_progress_tasks: 0
blocked_tasks: 0
runtime_smoke: pending
runtime_smoke_reason: Backend-only phase; smoke gate to be satisfied via FastAPI TestClient
  contract tests in T4-008 plus auth-mode health probe in T4-009.
tasks:
- id: T4-001
  description: 'Schema migration for workspace-scoped auth + scoping. Add `workspaces`
    table

    (workspace_id PK, name, status, created_at) and `workspace_tokens` table

    (token_id PK, workspace_id, project_id, hashed_token UNIQUE, scope,

    created_at, last_used_at, revoked_at, description) with partial indexes

    `ix_workspace_tokens_workspace` and `ix_workspace_tokens_hash` over

    `revoked_at IS NULL` rows (ADR-008 §Schema). Add NOT NULL `workspace_id TEXT`

    column to every scoped table: sessions, documents, tasks, features, links,

    progress_files, ingest_cursors. Backfill `default-local` workspace row plus

    one workspace_token row equivalent to today''s CCDASH_AUTH_TOKEN; backfill

    `workspace_id = ''default-local''` on all existing rows. Migration must be

    idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT

    EXISTS` or guarded via PRAGMA-style introspection for SQLite); reversible

    by drop-and-revert. Use existing migration runner under `backend/db/migrations`.

    NOTE: do NOT use Argon2 hashing in migration backfill — the migration

    inserts a single token row whose plaintext equals the legacy

    CCDASH_AUTH_TOKEN; T4-006 hashes when present. For the bootstrap row,

    store the argon2id hash of the current env token (the auth backend rejects

    raw equality).

    '
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
    \ in a process-local LRU\n    (size 256, TTL 60s) keyed by SHA-256(secret) — never\
    \ store the secret\n    plaintext. On revocation event (T4-002b in same task),\
    \ invalidate by\n    token_id. The LRU is short-TTL specifically because the 1-request\n\
    \    revocation gate (ADR-008 hard gate #2) requires a revoked token to\n    fail\
    \ on its very next use — therefore on each LRU hit, re-check\n    `revoked_at\
    \ IS NULL` against the DB in a single index lookup OR drop\n    the LRU entirely\
    \ if benchmark shows argon2 verify <10ms (see ADR-008\n    Risks);\n(c) attach\
    \ AuthContext to `request.state.auth_context` for downstream\n    dependencies;\n\
    (d) update `last_used_at` asynchronously (do not block request);\n(e) log only\
    \ the first 6 chars of any secret — never the full bearer;\n(f) honor `x-ccdash-project-id`\
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
  description: 'Refactor `RuntimeContainer` (backend/runtime/container.py:67) to support

    request-scoped multi-project binding per ADR-010. Replace

    `bound_project: ProjectBinding` (startup-time, single) with

    `resolve_binding(project_id: str) -> ProjectBinding` backed by an

    in-process LRU (maxsize 64). `ProjectBinding` is an immutable dataclass:

    (project_id, project_meta, paths: ProjectPathResolver, storage:

    ScopedStorageFacade). Bindings are lazy — never pre-populated.


    Add FastAPI dependency `get_project_binding(auth: AuthContext = Depends(

    get_auth_context), container: RuntimeContainer = Depends(get_container))

    -> ProjectBinding`. Worker profile (`backend/worker.py`,

    `backend/runtime/runtime.py:107-127`) retains startup-time single-project

    binding for now — multi-project workers are out-of-scope for v1 (ADR-010

    §Decision).


    Deprecate `x-ccdash-project-id` as a routing input: log a deprecation

    warning when present; honor it only as an equality assertion against

    `AuthContext.project_id` (already enforced in T4-002). Update the

    `workspace_tokens` row resolver to be the single source of routing.


    Cache invalidation surface: `RuntimeContainer.evict_binding(project_id)`

    for use by project-rename or project-delete admin paths (callers TBD).


    Smoke: confirm api profile boots and serves at least 2 projects under

    different tokens in a single test.

    '
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
  description: 'Workspace scoping wave 1 — sessions + documents + tasks + features

    repositories. Every method that returns scoped data takes an explicit

    `workspace_id: str` parameter (NOT a default-None; callers must pass it).

    Every SQL SELECT/UPDATE/DELETE adds `WHERE workspace_id = :workspace_id`.

    Mutators (insert/upsert) accept `workspace_id` and write it.


    Files: backend/db/repositories/sessions.py,

    backend/db/repositories/documents.py,

    backend/db/repositories/tasks.py,

    backend/db/repositories/features.py.


    Thread `workspace_id = auth.workspace_id` from each router/service caller

    site. Routers that already accept a Depends(get_auth_context) get the

    AuthContext injected; pass `auth.workspace_id` into the repository.


    All existing tests under backend/tests/ continue passing — supply

    `workspace_id="default-local"` everywhere the test factory creates

    fixtures, via a shared fixture helper.

    '
  status: pending
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies:
  - T4-001
  - T4-002
  evidence: []
  verified_by: []
- id: T4-005
  description: 'Workspace scoping wave 2 — links + progress_files + ingest_cursors

    repositories, plus analytics + cache surfaces.


    Files: backend/db/repositories/links.py,

    backend/db/repositories/analytics.py,

    backend/db/repositories/base.py (if a common helper is needed),

    plus the progress-file repository wherever it lives

    (codebase-explorer to identify) and the cursor repo

    (`backend/db/repositories/ingest_cursors.py` per Phase-2 work).


    Same contract as T4-004: explicit `workspace_id` parameter, WHERE

    predicate on every query, mutator writes the column.


    Specific care for `ingest_cursors`: ADR-009 stores cursors keyed by

    (source_id, project_id); v1 binds 1 token to 1 project so cursor lookups

    naturally select rows whose `workspace_id = auth.workspace_id`. Add the

    predicate as defense-in-depth. The ingest router (Phase 3) must thread

    `auth.workspace_id` into the cursor advance and dedup paths.

    '
  status: pending
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
    ADR-008 §Migration Path. Idempotent: running twice does nothing the\nsecond time.\
    \ CLI: `python -m backend.scripts.migrate_bearer_to_workspace_token`\nwith optional\
    \ `--token VALUE` (default reads CCDASH_AUTH_TOKEN env),\n`--workspace default-local`,\
    \ `--project <current bound>`. Steps:\n(1) ensure `default-local` workspace row\
    \ exists;\n(2) compute argon2id hash of the token; insert `workspace_tokens` row\
    \ if\n    no existing row has the same hash AND `revoked_at IS NULL`;\n(3) print\
    \ `token_id` and the next-step instructions (env-var swap);\n(4) exit 0 on success\
    \ / no-op; exit non-zero only on DB error.\n\nReversible: emit `rollback.sql`\
    \ next to the script with DROP statements\nfor the two new tables and ALTER ...\
    \ DROP COLUMN for the seven\n`workspace_id` columns (SQLite limitation: column\
    \ drop requires table\nrebuild — document this caveat at top of rollback.sql).\n\
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
    Risks §1. Test walks every public method on every class under\n`backend/db/repositories/`\
    \ and asserts:\n(a) if the method name does not start with `_` and is not in a\
    \ small\n    explicit exemption set (factory helpers, schema introspection\n \
    \   utilities — list each by name with a justification comment),\n    the method\
    \ MUST accept a `workspace_id` parameter (positional or\n    keyword);\n(b) the\
    \ method's source (via inspect.getsource) contains either the\n    literal `workspace_id`\
    \ predicate substring OR delegates to a helper\n    that does (e.g., `_scope(query,\
    \ workspace_id)`).\n\nThe test is the safety net for new repo methods — any future\
    \ PR that\nadds a method without the predicate fails CI. Document the exemption\n\
    process at top of the file. Run via `pytest backend/tests/test_workspace_scoping.py\
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
    \ A's rows);\n(2) revoked token rejected on next use — issue request, revoke token\
    \ in\n    DB, issue request again, assert 401 with code `revoked_token`;\n(3)\
    \ `x-ccdash-project-id` mismatch returns 403 with code\n    `workspace_project_mismatch`;\n\
    (4) migration script idempotency — fresh DB and already-migrated DB both\n   \
    \ yield exit 0 and identical post-state row counts;\n(5) `auth_mode` health probe\
    \ returns `workspace_token` in api profile and\n    `single_bearer` in local profile.\n\
    \nUse existing test fixtures from backend/tests/conftest.py; extend the\nDB fixture\
    \ with two workspaces (alpha, beta) and tokens for each.\n"
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
  description: 'Operator-facing surface: write `docs/guides/auth-modes.md` per ADR-008

    Risks §"Operator confusion". Covers: when each auth backend is used

    (profile → backend mapping), token rotation playbook, revocation flow,

    migration steps from single-bearer to workspace tokens, daemon.toml

    token storage permissions (mode 0600). Cross-reference ADR-008 and

    ADR-010. Update `docs/guides/cli-timeout-debugging.md` only if a new

    auth-related timeout/error surfaces.


    Also: extend health endpoint payload — add `auth_mode` field

    (`workspace_token` | `single_bearer`). Update OpenAPI schema if the

    health endpoint has one. Mention in the existing health-endpoint guide.

    '
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
    \ backend/tests/ -v` — full backend\n    suite passes;\n(2) `python .claude/skills/artifact-tracking/scripts/validate-phase-completion.py\n\
    \    -f .claude/progress/remote-ccdash-streaming/phase-4-progress.md`;\n(3) `python\
    \ .claude/skills/artifact-tracking/scripts/ac-coverage-report.py\n    --plan docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md\n\
    \    --progress .claude/progress/remote-ccdash-streaming/phase-4-progress.md`;\n\
    (4) Senior code review via senior-code-reviewer agent on the diff\n    (security-critical\
    \ phase per implementation plan §Subagent Assignments).\n(5) Capture pytest output\
    \ count + green test summary as evidence.\n\nMark phase status=completed only\
    \ after all four pass. Record evidence\nin this progress file's tasks via update-status.py\
    \ with --evidence.\n"
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
