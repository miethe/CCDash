---
title: "ADR-008: Workspace-Scoped Bearer Tokens for Multi-Workspace Remote CCDash"
type: "adr"
status: "accepted"
created: "2026-05-10"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
tags: ["adr", "auth", "security", "multi-tenant", "workspaces"]
---

# ADR-008: Workspace-Scoped Bearer Tokens for Multi-Workspace Remote CCDash

## Status

Accepted (SPIKE-resolved 2026-05-10)

## Context

Today's auth is a single static bearer (`backend/adapters/auth/bearer.py:22, 74-109`) read from `CCDASH_AUTH_TOKEN`, applied uniformly to every authenticated route. The `x-ccdash-project-id` header is an unauthenticated hint that does not reroute data access (`backend/runtime/container.py:67`). For multi-workspace remote operation, this is insufficient: every workspace must be able to (a) ingest only into its own scope, (b) read only its own data, and (c) have its tokens revoked independently. Four options were evaluated: (1) per-workspace static tokens, (2) OIDC/OAuth, (3) mTLS with per-workspace client certs, (4) git-identity (Entire-style).

## Decision

**v1 ships workspace-scoped static bearer tokens.** The existing single-tenant bearer guard is extended (not replaced) with a `workspace_tokens` table that resolves an inbound `Authorization: Bearer <token>` to a `(workspace_id, project_id)` pair. The auth dependency injects an `AuthContext{workspace_id, project_id, token_id}` into every authenticated request. All repository queries that touch session/document/task/feature data become **workspace-scoped** by passing `workspace_id` from `AuthContext` as an explicit predicate.

The legacy single-bearer mode (`CCDASH_AUTH_TOKEN`) continues to work in `local` runtime profile. In `api`/`worker` profiles, it is deprecated; a one-shot migration script (`backend/scripts/migrate_bearer_to_workspace_token.py`) creates a single workspace + token equivalent to today's single-bearer setup.

OIDC, mTLS, and git-identity are deferred to post-v1 (see Non-Goals in design-spec §7).

## Decision Drivers

1. **Smallest viable step from today.** The existing bearer guard is ~50 lines of code. Replacing it with a DB-backed lookup adds ~100 lines and one table. OIDC requires a relying-party flow, JWKS rotation, an IdP dependency — wildly disproportionate for a v1 that just needs multi-workspace isolation.
2. **No new runtime dependencies.** A token table is plain SQL. OIDC adds `python-jose` or `authlib` and an IdP. mTLS adds cert lifecycle and reverse-proxy mTLS termination. v1 should not pay these costs to ship.
3. **Aligns with daemon distribution.** The daemon (ADR-015) takes a single token from `daemon.toml`. Static tokens fit that model exactly. OIDC would require interactive flows on a headless daemon — a poor UX.
4. **Migration is straightforward.** One row insert + one env-var swap. Existing single-tenant deployments upgrade without downtime.
5. **Forward path to OIDC is unblocked.** The `AuthContext` shape is identical whether populated by a token lookup or a JWT claim. v2 can swap the resolver without touching repositories.

## Decision Matrix

Scored 1 (worst) to 5 (best). Weights reflect the v1 priority of *minimum viable multi-workspace*.

| Criterion (weight) | Per-workspace static tokens | OIDC/OAuth | mTLS | Git-identity |
|---|---|---|---|---|
| Code-change surface (×3) | **5** | 1 | 2 | 2 |
| New runtime dependencies (×2) | **5** | 2 | 3 | 4 |
| Daemon UX (headless) (×2) | **5** | 2 | 4 | 4 |
| Token rotation/revocation (×2) | 4 | **5** | 3 | 2 |
| Multi-workspace isolation strength (×2) | 4 | **5** | **5** | 3 |
| Migration from today (×1) | **5** | 2 | 2 | 2 |
| Operator burden (run the IdP / cert authority) (×2) | **5** | 2 | 1 | 4 |
| **Weighted total** | **70** | 41 | 47 | 47 |

Static tokens win for v1. OIDC wins on rotation and isolation strength but loses badly on every other axis. The forward migration path to OIDC is preserved.

## Schema

A new table:

```sql
CREATE TABLE workspace_tokens (
    token_id        TEXT PRIMARY KEY,                  -- stable opaque ID for revocation/audit
    workspace_id    TEXT NOT NULL,
    project_id      TEXT NOT NULL,                     -- v1 binds 1 token to 1 project; relax in v2
    hashed_token    TEXT NOT NULL UNIQUE,              -- argon2id of the bearer secret
    scope           TEXT NOT NULL,                     -- 'ingest_write' | 'read' | 'admin'
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    revoked_at      TEXT,
    description     TEXT
);

CREATE INDEX ix_workspace_tokens_workspace ON workspace_tokens (workspace_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_workspace_tokens_hash ON workspace_tokens (hashed_token) WHERE revoked_at IS NULL;
```

A `workspaces` table is also introduced (one row per logical tenant) with `(workspace_id, name, created_at, status)`.

## Auth Flow

```
Request: Authorization: Bearer <secret>
  │
  ▼
WorkspaceTokenAuthBackend (replaces SingleBearerAuthBackend in api/worker profiles)
  │  argon2 verify(secret) against workspace_tokens.hashed_token
  │  check revoked_at IS NULL
  │  reject 401 on miss
  ▼
AuthContext{workspace_id, project_id, token_id, scope}  ←  attached to request.state
  │
  ▼
Repository/service layer  ←  reads AuthContext, passes workspace_id as scope filter
```

The `x-ccdash-project-id` header is honored **only if** it equals `AuthContext.project_id`; mismatch returns `403`. This closes the bypass risk surfaced in design-spec §8.

## Workspace Scoping Enforcement

Every repository method that returns session/document/task/feature/link data adds a `workspace_id: str` parameter, sourced from `AuthContext`. The implementation pattern in v1 is **explicit predicate filtering** — every SELECT carries `WHERE workspace_id = :workspace_id`.

Postgres Row-Level Security (RLS) is **considered for v2**, not v1. Reasons:

1. SQLite (the default DB) does not support RLS. Two enforcement mechanisms (RLS for Postgres, manual filter for SQLite) is exactly the kind of dual-implementation tax the project's estimation heuristics flag (H2). One enforcement mechanism for v1.
2. Auditing 100% of queries for the `workspace_id` predicate is mechanical and can be enforced by a dedicated test in `backend/tests/test_workspace_scoping.py` that inspects every repository method via reflection.
3. RLS makes service-layer test fixtures harder (every test needs a session-bound role).

The migration plan to RLS in v2 is independent of this ADR; the explicit-filter approach is forward-compatible.

## Migration Path (today → v1)

1. **Schema migration**: add `workspaces`, `workspace_tokens`, plus a non-null `workspace_id` column on every scoped table (`sessions`, `documents`, `tasks`, `features`, `links`, `progress_files`, `ingest_cursors` from ADR-009).
2. **Backfill**: insert one workspace `default-local` and one token row equivalent to the existing `CCDASH_AUTH_TOKEN`. Backfill `workspace_id = 'default-local'` on every existing row.
3. **Auth flag flip**: in `api`/`worker` profiles, switch the dependency from `SingleBearerAuthBackend` to `WorkspaceTokenAuthBackend`. `local` profile keeps the legacy backend (no auth) for backwards compatibility.
4. **Operator action**: deploy ⇒ run `backend/scripts/migrate_bearer_to_workspace_token.py` once ⇒ verify health endpoint returns `auth_mode: workspace_token`.

The migration is reversible: drop the new tables, revert the auth backend swap, the `workspace_id` columns become unused (forward-tolerable).

## Hard Gates (from E3)

| Gate | Target | Verification |
|---|---|---|
| Cross-workspace read attempt returns 403 or empty | 403 on direct query, empty on list endpoints | `backend/tests/test_workspace_scoping.py` covers every repository method |
| Token revocation takes effect within 1 request | A revoked token is rejected on its very next use | Test issues a request with a revoked token and asserts `401`; no caching layer caches `AuthContext` longer than 1 request |
| Migration script is idempotent | Running twice does nothing the second time | Migration script tests on fresh + already-migrated DBs |
| No regression in legacy single-bearer tests in `local` profile | All existing auth tests pass unchanged | CI gate |
| `x-ccdash-project-id` cannot widen scope | Requests with mismatched header return 403 | Dedicated security test |

## Consequences

### Positive

- Multi-workspace data isolation by construction (every query carries `workspace_id`).
- Token rotation and revocation are first-class operations.
- Audit trail via `last_used_at` and `token_id`.
- Migration story is single-step and reversible.
- No new external dependencies; SQLite-compatible.

### Negative

- Tokens are long-lived and must be transported securely. Mitigated: tokens stored in `daemon.toml` (mode 0600) on workstation; never written to project files; rotation is a one-line CLI command.
- No automatic expiration in v1. Tokens are revoked manually. (OIDC fixes this in v2.)
- Every repository method gains a `workspace_id` parameter — wide change surface, but mechanical.
- The auth backend in `local` profile diverges from `api`/`worker` profiles. Acceptable: `local` is single-user-on-laptop and does not need multi-workspace.

### Risks

| Risk | Mitigation |
|---|---|
| Forgotten `workspace_id` predicate on a new query → cross-workspace leak | Reflection test (`test_workspace_scoping.py`) walks every repository method and asserts the parameter exists; CI gate |
| Token leaked via logs | Auth backend MUST hash before logging; `WorkspaceTokenAuthBackend` truncates to first 6 chars in any log line |
| Argon2id verify cost too high (>10ms/req) | Benchmark in E3; if cost is excessive, cache `(hashed_token → AuthContext)` in process-local LRU with 60s TTL; revocation invalidates by `token_id` not by hash |
| Operator confusion: which profile uses which auth | Health endpoint returns `auth_mode`; documented in `docs/guides/auth-modes.md` |

## Related

- ADR-014 (transport — uses this auth)
- ADR-015 (daemon — carries this token in config)
- ADR-009 (sync port — `ingest_cursors` table is workspace-scoped)
- ADR-010 (multi-project routing — depends on `AuthContext.project_id`)
- Bearer guard today: `backend/adapters/auth/bearer.py:22, 74-109`
- Container project binding today: `backend/runtime/container.py:67`
