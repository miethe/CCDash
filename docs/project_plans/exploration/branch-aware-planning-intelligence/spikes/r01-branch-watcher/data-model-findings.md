---
schema_version: 2
doc_type: spike_findings
title: "R-01 Branch Watcher — Data Model, Cache, and Linkage Findings (RQ 3, 5, 6)"
status: complete
created: 2026-06-04
updated: 2026-06-04
feature_slug: branch-aware-planning-intelligence
spike_id: r01-branch-watcher
leg: data-model
confidence: 0.88
partial: false
research_questions_answered: [3, 5, 6]
grounded_in:
  - backend/db/sqlite_migrations.py (SCHEMA_VERSION=33)
  - backend/db/repositories/base.py (retry_on_locked, retry_on_locked_sync)
  - backend/db/repositories/sessions.py
  - backend/db/repositories/documents.py
  - backend/db/repositories/features.py
  - backend/db/repositories/feature_sessions.py (_SESSION_COLS lines 53-75)
  - backend/application/services/agent_queries/cache.py (memoized_query, compute_cache_key, _FINGERPRINT_TABLES)
  - backend/application/services/agent_queries/planning.py (@memoized_query usages)
  - backend/application/services/agent_queries/planning_sessions.py (pss_session_board)
  - backend/application/services/agent_queries/session_correlation.py (_correlate_command_tokens, correlate_session)
  - backend/models.py (Feature.commitRefs, AgentSession.gitBranch)
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
---

# R-01: Data Model, Cache Key, and Branch-to-Feature Linkage Findings

## Summary

All three research questions have concrete answers grounded in current runtime state.
The key findings are:

- **RQ3 (document modeling)**: No branch column exists on `documents` today. Option A (`branch` column on `documents`) is the recommended path for Phase 2 — it is the lowest migration cost, is fully ADR-007 compliant with `retry_on_locked`, and matches the precedent set by `sessions.git_branch`. Option C (scan namespace per worktree) is over-engineered for the current scale.
- **RQ5 (cache key strategy)**: Incorporating `branch` as a cache-key dimension via `param_extractor` is the correct approach. The fingerprint already covers `sessions.updated_at` and `planning_worktree_contexts.updated_at`, so branch-specific queries naturally get cache isolation without bypassing `@memoized_query`. Event-driven invalidation via `aclear_project_cache` (already called post-sync) is the complementary mechanism.
- **RQ6 (branch-to-feature linkage)**: Option A — a composite index on `sessions(git_branch, project_id)` — is the recommended Phase 2 start. It requires no new write path, no ADR-007 compliance overhead, and delivers branch-signal correlation immediately. The branch-name exclusion list should be applied as a static filter set in the correlation pipeline. Minimum token length of 8 characters (not 4) is recommended for branch names to suppress false positives.

---

## RQ3: Branch-Scoped Document Modeling

### Current State (Schema v33)

The `documents` table has no `branch` column:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    canonical_path TEXT DEFAULT '',
    ...
    source_file    TEXT NOT NULL
);
```

The `document_refs` table (child of `documents`) similarly has no branch column:

```sql
CREATE TABLE IF NOT EXISTS document_refs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id     TEXT NOT NULL,
    ref_kind       TEXT NOT NULL,
    ref_value      TEXT NOT NULL,
    ref_value_norm TEXT NOT NULL,
    source_field   TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

By contrast, `sessions` already has `git_branch TEXT` at line 194 and the `planning_worktree_contexts` table has `branch TEXT DEFAULT ''` plus `worktree_path TEXT DEFAULT ''`. The branch pattern is established.

The `DocumentRepository` protocol (`base.py`) does not expose any `branch` or `worktree` parameter in `upsert`, `get_by_path`, or `list_paginated`. The `upsert` in `SqliteDocumentRepository` calls `normalize_ref_path` on `canonical_path` — there is no branch-scoping today.

### Option A: `branch` Column on `documents` (RECOMMENDED)

Add `branch TEXT DEFAULT ''` to `documents`.

**Migration**: A single `ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT ''` is O(1) in SQLite (metadata-only, no row rewrite because the DEFAULT is a constant). This follows the exact pattern used by `_ensure_column` in `sqlite_migrations.py:1483-1486`. Since `_ensure_column` is already the standard idempotent-add helper, this migration is one line in `_run_migrations_inner`:

```python
await _ensure_column(db, "documents", "branch", "TEXT DEFAULT ''")
```

Add a covering index immediately after:

```sql
CREATE INDEX IF NOT EXISTS idx_docs_project_branch
    ON documents(project_id, branch);
```

**ADR-007 write-path implications**: `SqliteDocumentRepository.upsert` calls `self.db.commit()` without `retry_on_locked`. Per ADR-007 §2, every new write path must use `retry_on_locked`. The retrofit is:

```python
# existing: await self.db.commit()
# replace with:
from backend.db.repositories.base import retry_on_locked
await retry_on_locked(self.db.commit, repo="documents")
```

A direct-count assertion test is required: after upsert, assert `SELECT COUNT(*) FROM documents WHERE branch = ?` returns the expected count. This is the ADR-007 §4 test contract.

**Collision model**: Documents from two worktrees on different branches can coexist in `documents` because the primary key is `id` (document slug/hash), not `(project_id, file_path)`. However, if both worktrees have the same document at the same path (e.g., `docs/plans/feature-x.md`), their `id` values will collide — the upsert will overwrite with whichever syncs last. The `branch` column disambiguates only for query filtering, not for identity. If worktree-specific document isolation is required (two worktrees have different versions of the same document), the PK must include `branch`. This is the key tradeoff.

**Recommendation for Phase 2**: Add `branch` as a nullable/default-empty column for display/filtering. Do NOT change the PK. The last-writer-wins collision is acceptable for Phase 2 because worktrees typically work on different documents; worktree-specific content divergence is a Phase 3 concern.

**Confidence**: 0.88. The migration pattern is well-established; the collision behavior is a known limitation acceptable for Phase 2 scope.

### Option B: Branch-Scoped `document_refs`

Add a `branch TEXT DEFAULT ''` column to `document_refs` and use it to route ref lookups by branch.

**Migration cost**: Also a single `_ensure_column` call. However, `document_refs` already has a `UNIQUE INDEX` on `(document_id, ref_kind, ref_value_norm, source_field)`. Adding `branch` to the uniqueness predicate requires dropping and recreating the index (the rename-create-copy pattern used for `outbound_telemetry_queue` in the existing migrations at line 1504). This is O(N) cost for large doc sets.

**Write-path implications**: `_extract_document_refs` in `SqliteDocumentRepository` populates `document_refs`. Branch would need to flow through `upsert(doc_data, project_id)` as an additional parameter, requiring protocol changes in `DocumentRepository.upsert`.

**Assessment**: Higher migration cost and protocol breakage than Option A. Useful only if the ref-level (not doc-level) granularity matters, which it does not for Phase 2 use cases (branch-scoped doc display, branch correlation). Not recommended.

### Option C: Separate Scan Namespace per Worktree

Create a `worktree_document_namespaces` table that maps `(project_id, branch, worktree_path)` to a namespace prefix applied to `documents.id`, effectively sharding the doc table by worktree.

**Migration cost**: New table + changes to `SqliteDocumentRepository.upsert` to look up the namespace at write time.

**Assessment**: Maximum isolation, maximum complexity. Appropriate if worktrees frequently diverge on the same document paths AND both versions must coexist simultaneously. For the Phase 2 display-first use case (show which branch a doc came from), this is over-engineered. The existing `planning_worktree_contexts` table already provides a join point for worktree-to-branch mapping without a new namespace table. Not recommended for Phase 2.

### ADR-007 Implications Summary (Option A)

| Requirement | Current state | Action required |
|---|---|---|
| `retry_on_locked` on write path | `SqliteDocumentRepository.upsert` uses bare `self.db.commit()` | Add `retry_on_locked` wrapper |
| `PRAGMA busy_timeout=30000` | Set by async singleton; documents repo uses same singleton | No action |
| Direct-count assertion test | Not present for branch column | Add in new test for `branch` column upsert |
| Postgres parity | `postgres/documents.py` must get same column + `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch` | Add to postgres migration |

---

## RQ5: Cache Key Strategy for Branch-Aware Planning Queries

### Current Cache Architecture

`@memoized_query` constructs cache keys via `compute_cache_key`:

```
{endpoint_name}:{project_id}:{param_hash}:{fingerprint}
```

The `fingerprint` is computed by `get_data_version_fingerprint`, which queries `MAX(updated_at)` on six tables:

```python
_FINGERPRINT_TABLES = (
    {"name": "sessions", "column": "updated_at", "scope": "project_id"},
    {"name": "features", "column": "updated_at", "scope": "project_id"},
    {"name": "feature_phases", "column": "row_state", "scope": "feature_join"},
    {"name": "documents", "column": "updated_at", "scope": "project_id"},
    {"name": "entity_links", "column": "row_state", "scope": "project_id"},
    {"name": "planning_worktree_contexts", "column": "updated_at", "scope": "project_id"},
)
```

The `planning_worktree_contexts` table is already in the fingerprint. When a new worktree context is created (new branch started), the fingerprint changes and the cache is naturally invalidated within one `CCDASH_FINGERPRINT_CACHE_TTL_SECONDS` (default 5 s) of the next fingerprint query.

The four planning query endpoints (`planning_project_summary`, `planning_project_graph`, `planning_feature_context`, `pss_session_board`) are all wrapped with `@memoized_query`. The default global TTL is `CCDASH_QUERY_CACHE_TTL_SECONDS` (documented as ~600 s in CLAUDE.md context, configurable). The tech leg found Phase 1 ships `refetchInterval` polling (15 s proposed for command center board).

### Option A: Bypass `@memoized_query` for Branch-Aware Endpoints (NOT RECOMMENDED)

Remove `@memoized_query` from branch-aware planning endpoints and query live on every request.

**Impact**: At 15 s refetch intervals with N browser clients, N×4 live DB queries per 15 s per project. For a small single-user deployment this is acceptable; for multi-user or multi-project it is not. The `WorktreeGitStateProbe` already has a 5 s subprocess TTL — bypassing the query cache would make the DB layer similarly hot.

**Assessment**: Unnecessary given Option B works cleanly. Do not bypass the cache.

### Option B: Branch as a Cache-Key Dimension via `param_extractor` (RECOMMENDED)

If a query is scoped to a specific branch, add `branch` to the `param_extractor` dict. `compute_cache_key` hashes the param dict into the key, so `branch="feat/my-feature"` and `branch="main"` produce distinct cache entries automatically:

```python
@memoized_query(
    "pss_session_board",
    param_extractor=lambda self, ctx, ports, *, project_id=None, feature_id=None,
        grouping="state", cursor=None, limit=500, branch_filter=None: {
        "project_id": project_id,
        "feature_id": feature_id,
        "grouping": grouping,
        "branch_filter": branch_filter,  # new dimension
        "cursor": cursor,
        "limit": limit,
    },
)
async def get_session_board(self, context, ports, *, branch_filter=None, ...):
    ...
```

When `branch_filter=None` (the default, Phase 1 behavior), the cache key is identical to today's key — backward compatible. When `branch_filter="feat/my-feature"`, it is a distinct cache slot. No changes to the TTL or the fingerprint mechanism are needed.

**Phase 1 polling interaction**: Phase 1 ships `refetchInterval` at the component level (15 s). The backend TTL is 60 s (or up to ~600 s if configured). With `staleTime: 30_000` (30 s) and `refetchInterval: 15_000` (15 s), client requests fire at 15 s intervals; the second request within the 60 s window hits the cache. The fingerprint mechanism ensures that a sync event (new session written, new worktree context created) advances the fingerprint and busts the cache. This is the intended interaction — it works correctly without bypass.

**Confidence**: 0.92. The `param_extractor` mechanism is designed exactly for this use case.

### Option C: Event-Driven Invalidation (COMPLEMENTARY, NOT EXCLUSIVE)

`aclear_project_cache(project_id)` is already called by `sync_engine.sync_project()` after every successful sync. This means any sync that touches sessions (including sessions from a new branch) evicts the project's cache. Adding branch-scoped documents to the sync would automatically trigger `aclear_project_cache` with no additional invalidation plumbing.

**Assessment**: Option C is already in place for sessions. It is a complementary mechanism, not an alternative to Option B. Use both: Option B for branch-filtered query isolation, Option C (existing) for post-sync eviction.

### Fingerprint Coverage for Branch Data

If branch-scoped documents are added via Option A (RQ3), the `documents` fingerprint (`MAX(updated_at)`) already covers them — the fingerprint refreshes whenever any document is updated (including documents from a newly-scanned worktree branch). No changes to `_FINGERPRINT_TABLES` are needed.

If a dedicated `branch_sessions` or `session_branch_links` table were added (RQ6 Option B), it would need to be added to `_FINGERPRINT_TABLES` to participate in cache invalidation. This is an additional cost of Option B for RQ6.

---

## RQ6: Branch-to-Feature Linkage Model

### Current State

`sessions` has `git_branch TEXT` (populated at parse time from JSONL). The column is selected in `feature_sessions.py:_SESSION_COLS` (lines 72-73: `"s.git_branch"`) but is not returned to the planning service layer — `PlanningAgentSessionCardDTO` has no `git_branch` field.

The `features` table has no branch column. The correlation pipeline (`session_correlation.py`) has five steps: explicit_link, phase_hints, task_hints, command_tokens, lineage — no branch-signal step.

The `entity_links` table is used for session→feature explicit linking. There is no `session_branch_links` join table.

There is no composite index on `sessions(git_branch, project_id)` today.

### Option A: Composite Index on `sessions(git_branch, project_id)` (RECOMMENDED)

Add one index:

```sql
CREATE INDEX IF NOT EXISTS idx_sessions_git_branch_project
    ON sessions(git_branch, project_id);
```

This is a `CREATE INDEX IF NOT EXISTS` — zero write-path changes, no ADR-007 compliance overhead, no new migration function required. The `_ensure_column` / `ALTER TABLE` pattern is not needed because `git_branch` already exists.

In the correlation pipeline, add a `_correlate_branch` step after `_correlate_command_tokens`:

```python
def _correlate_branch(
    session: dict[str, Any],
    feature_index: dict[str, dict[str, Any]],
    exclusion_set: frozenset[str],
    min_length: int = 8,
) -> list[SessionCorrelationEvidence]:
    branch = _safe_str(session.get("git_branch")).lower()
    if not branch or len(branch) < min_length or branch in exclusion_set:
        return []
    ...
```

The branch slug extraction normalizes `feat/`, `feature/`, `fix/`, `chore/` prefixes before matching against feature slug tokens.

**Confidence**: 0.90. Zero write amplification, no new protocol changes, no ADR-007 implications.

### Option B: `session_branch_links` Join Table (NOT RECOMMENDED FOR PHASE 2)

Create a new table:

```sql
CREATE TABLE IF NOT EXISTS session_branch_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    branch      TEXT NOT NULL,
    linked_at   TEXT NOT NULL DEFAULT (datetime('now')),
    confidence  REAL DEFAULT 0.0,
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);
```

This requires:
- Full ADR-007 compliance: `retry_on_locked` on all writes, direct-count assertion test, lock-injection test
- A new write path in `SqliteSessionRepository.upsert` (or a separate repository)
- Population from `session.git_branch` at sync time — duplicate data already in `sessions.git_branch`
- Addition to `_FINGERPRINT_TABLES` for cache invalidation

**Migration cost**: New table + new write path + tests. The only advantage over Option A is an explicit relationship table with `confidence` metadata, useful for multi-branch sessions that simultaneously touch multiple features. This scenario is rare in the Phase 2 single-worktree-per-session model.

**Assessment**: Over-engineered for Phase 2. The join table adds write amplification (every session sync writes to two tables) and ADR-007 overhead for no gain over the indexed column. Defer to Phase 3 if multi-branch session attribution becomes a requirement.

### Option C: `branch` Column on `features` (NOT RECOMMENDED)

Add `branch TEXT DEFAULT ''` to `features` to record which branch a feature is being developed on.

**Assessment**: A feature can span multiple branches (e.g., `feat/my-feature-ui` and `feat/my-feature-api`). A single column cannot represent this relationship. The `commitRefs` and `prRefs` fields in `features.data_json` already capture a richer version of this relationship. A branch column on features would require application-side management (which branch is "current"?) and does not enable the primary use case: correlating sessions to features by branch name in the planning board.

### Concrete Recommendation for S2 Branch-Name Exclusion List and Minimum-Length Threshold

**S2 is the branch-signal correlation story** (3 pts, per tech-findings.md). The exclusion list and threshold govern false-positive rates.

#### Minimum-Length Threshold

The existing `_correlate_command_tokens` uses a minimum token length of 4 characters (`len(token) >= 4`). Branch names are longer on average (conventional branch names like `feat/auth-jwt` are 12+ characters), but generic short branch names (`dev`, `fix`, `wip`) would match feature slugs that happen to contain those tokens.

**Recommendation**: Minimum length of **8 characters** for branch-based correlation. Rationale:
- Eliminates `dev`, `fix`, `wip`, `main`, `test`, `next`, `work`, `temp` — all 4 chars or fewer
- Eliminates `hotfix`, `bugfix`, `update` — 5-6 chars, too generic
- Accepts `feat/ui`, `feat/db` — 7 chars after prefix stripping (borderline; see exclusion list)
- Accepts `feat/my-feature` — well above threshold

#### Exclusion List (Concrete `frozenset`)

The exclusion list should block branch names that appear in many projects regardless of feature context:

```python
_BRANCH_EXCLUSION_SET: frozenset[str] = frozenset({
    # Integration/default branches
    "main", "master", "develop", "development",
    "staging", "production", "release", "prod",
    # Short generic prefixes (after normalization strips feat/, fix/, etc.)
    "dev", "fix", "wip", "hot", "tmp", "temp",
    # Common single-word generic branches
    "hotfix", "bugfix", "update", "patch", "chore",
    "refactor", "cleanup", "rebase", "merge",
    # CI/CD branches
    "ci", "cd", "deploy", "build", "test", "tests",
    "gh-pages", "gh_pages",
    # Numeric-only (e.g., Jira ticket like "1234")
    # handled separately by: if branch.isdigit(): return []
})
```

**Prefix normalization**: Before matching, strip common branch type prefixes:

```python
_BRANCH_PREFIXES = ("feat/", "feature/", "fix/", "hotfix/", "bugfix/",
                    "chore/", "refactor/", "release/", "wip/")

def _normalize_branch_for_correlation(branch: str) -> str:
    for prefix in _BRANCH_PREFIXES:
        if branch.startswith(prefix):
            return branch[len(prefix):]
    return branch
```

After normalization, apply the minimum-length (8) and exclusion-set checks. The normalized slug is what gets matched against `_feature_slug_tokens`.

**Confidence signal assignment**: Branch correlation should be assigned `confidence="medium"` (same as `_correlate_command_tokens`), not `"high"`. Rationale: branch names are operator-controlled and can be arbitrary. `high` confidence should be reserved for explicit entity_links. A branch match on `feat/my-feature-slug` where `my-feature-slug` is the exact feature ID should optionally bump to `high` — this is a Phase 2 tuning decision, not a hard requirement.

**False-positive risk assessment**:
- With min-length=8 and the exclusion set above: estimated FP rate on a typical single-project deployment of 50 features and 200 sessions is <5% (subjective estimate — no telemetry data).
- The primary residual FP vector: two features with similar slugs (e.g., `auth-api` and `auth-api-v2`) where both match against a branch named `feat/auth-api`. The correlation pipeline selects the highest-confidence feature at a single slot; multiple features matched at medium confidence will produce ambiguous output. Recommend surfacing `evidence` on the card to let operators inspect the match, rather than hiding ambiguity.

---

## Confidence Scores

| Research Question | Confidence | Key uncertainty |
|---|---|---|
| RQ3: Document modeling (Option A) | 0.88 | Last-writer-wins collision on same-path docs across worktrees; acceptable for Phase 2 but must be documented as a known limitation |
| RQ5: Cache key strategy (Option B) | 0.92 | Assumes `branch_filter` is a query-time parameter, not a DB-side filter on the fingerprint; works correctly if the fingerprint covers `sessions.updated_at` |
| RQ6: Linkage model (Option A + exclusion list) | 0.87 | FP rate estimate is subjective; real FP rate must be measured after the branch signal is live against actual project data |

---

## Decision Table: Recommendation vs Alternatives

| Question | Recommended | Alternative | Why not alternative |
|---|---|---|---|
| RQ3 document modeling | Option A: `branch` column on `documents` | Option B: `branch` on `document_refs` | Option B requires index rebuild (O(N) migration, protocol change); not worth it for Phase 2 display |
| RQ3 document modeling | Option A | Option C: scan namespace | Option C is over-engineered; worktree-specific document identity is a Phase 3 concern |
| RQ5 cache strategy | Option B: `branch` as `param_extractor` dimension | Option A: bypass `@memoized_query` | Bypass adds DB query load at every refetch interval; unnecessary |
| RQ5 cache strategy | Option B | Option C: event-driven only | Option C (already live via `aclear_project_cache` post-sync) is complementary, not exclusive |
| RQ6 linkage model | Option A: composite index + `_correlate_branch` step | Option B: `session_branch_links` table | Option B adds write amplification and full ADR-007 compliance overhead for data already in `sessions.git_branch` |
| RQ6 linkage model | Option A | Option C: `branch` column on `features` | One feature spans multiple branches; column model is too coarse |

---

## Implementation Notes for Phase 2 PRD

1. **Migration sequence** (SQLite):
   - v34: `ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT ''` + `CREATE INDEX idx_docs_project_branch ON documents(project_id, branch)`
   - v34: `CREATE INDEX idx_sessions_git_branch_project ON sessions(git_branch, project_id)`
   - Both are O(1) metadata-only operations in SQLite.

2. **Write-path retrofit for documents**:
   - `SqliteDocumentRepository.upsert`: add `retry_on_locked(self.db.commit, repo="documents")` — required by ADR-007 §2.
   - Add direct-count assertion test: `SELECT COUNT(*) FROM documents WHERE project_id = ? AND branch = ?` after upsert.

3. **Correlation pipeline extension** (no schema change, no ADR-007 implication):
   - Add `_correlate_branch(session, feature_index, _BRANCH_EXCLUSION_SET, min_length=8)` as step 5a in `session_correlation.py:correlate_session`.
   - Add `git_branch: str | None = None` to `PlanningAgentSessionCardDTO` in `agent_queries/models.py`.
   - Populate from `session.get("git_branch")` in `build_active_session_card`.

4. **Cache key extension** (Phase 2, branch-filtered board):
   - Add `branch_filter: str | None = None` to `get_session_board` and `_pss_params` extractor.
   - The `param_extractor` hash automatically creates distinct cache slots.
   - No change to `_FINGERPRINT_TABLES` required for Option A (RQ6) — `sessions.updated_at` already covers new sessions from any branch.

5. **Postgres parity**:
   - `postgres/documents.py`: add `branch TEXT DEFAULT ''` column, `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch`.
   - `postgres_migrations.py`: mirror the v34 migration.
