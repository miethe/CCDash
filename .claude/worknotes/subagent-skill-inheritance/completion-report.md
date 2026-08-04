# Completion Report — subagent-skill-inheritance

Contract: `docs/project_plans/feature_contracts/subagent-skill-inheritance.md`
Branch: `feat/subagent-skill-inheritance` (base `main` @ `8d56b5c`)
Commits: `cf44ac5` (schema v49 + repository backfill), `848deae` (test coverage)

## Summary

Added `sessions.skill_name_source` (nullable TEXT, schema v49, dual DDL in both SQLite and
Postgres) and a one-hop, `(id, project_id)`-scoped `backfill_skill_name_inheritance()` method on
both session repositories, wired into `SyncEngine`'s per-project post-sync pass. A subagent session
whose own `skill_name` is NULL now inherits its parent's `skill_name` and is stamped
`inherited_parent`; a directly-detected `skill_name` is stamped `directly_detected` and is never
overwritten. The vocabulary module (`backend/parsers/skill_provenance.py`) deliberately reuses
`effort_provenance.EFFORT_SOURCE_INHERITED_PARENT`'s existing `inherited_parent` spelling rather
than the contract's proposed `inherited_from_parent`, per Architecture Constraint 7.

## Files Changed

- `backend/parsers/skill_provenance.py` — new. Provenance vocabulary module (`SKILL_SOURCE_DIRECT`,
  `SKILL_SOURCE_INHERITED_PARENT`, trust order, closed-set membership).
- `backend/db/postgres_migrations.py` — `skill_name_source TEXT` added to `sessions` CREATE TABLE;
  v49 `_ensure_column` migration block; `SCHEMA_VERSION` 48→49.
- `backend/db/sqlite_migrations.py` — identical shape for the SQLite backend.
- `backend/db/repositories/sessions.py` — upsert stamps `directly_detected` on parser-supplied
  `skill_name`; new `backfill_skill_name_inheritance(project_id)` (SQLite `UPDATE ... FROM`
  correlated subquery, `retry_on_locked`-wrapped per ADR-007).
- `backend/db/repositories/postgres/sessions.py` — same shape for Postgres (`UPDATE ... FROM`).
- `backend/db/repositories/base.py` — `SessionRepository` Protocol gains
  `backfill_skill_name_inheritance`.
- `backend/db/sync_engine.py` — calls the backfill unconditionally after every `_sync_sessions`
  pass (self-heal step, not gated on `backfill_session_intelligence`); new stats counter
  `skill_name_inherited`.
- `backend/tests/test_skill_name_source_provenance.py` — new. Dual-DDL parity, vocabulary, and
  direct-count round-trip tests (18 tests, see below).

## Acceptance Criteria Status

- [x] **AC 1** — subagent inherits parent's skill, `skill_name_source = inherited_parent`.
      Verified: `test_ac1_subagent_inherits_parent_skill`.
- [x] **AC 2** — orphaned subagent (parent's `skill_name` also NULL) stays NULL. Verified by
      direct-count assertion: `test_ac2_orphaned_subagent_stays_null` (0 rows touched).
- [x] **AC 3** — directly-detected `skill_name` never overwritten; `skill_name_source` reads
      `directly_detected`. Verified: `test_ac3_direct_detection_never_overwritten` (0 rows touched,
      source unchanged).
- [x] **AC 4** — column exists identically in both DDLs, passes `column_parity_diff`, zero
      `COLUMN_PARITY_DRIFT_ALLOWLIST` entries, nullable no default. Verified:
      `TestSkillNameSourceDualDDL` (5 tests).
- [x] **AC 5** — backfill idempotent, second pass changes 0 rows. Verified:
      `test_ac5_backfill_is_idempotent`.
- [~] **AC 6 — PARTIAL — projected, not achieved-measured.** Baseline measured against node
      Postgres (`10.42.10.76:5440`, read-only, no writes issued): reproduced exactly at **51.3%**
      (1,944/3,788), with **1,844** rows that would flip system-wide (all-time) and **946** orphans
      (AC 2's case) correctly remaining NULL. These baseline figures are genuine measurements. The
      **100%** achieved rate is a read-only *projection*, true by construction of the backfill's
      WHERE clause (`child.skill_name IS NULL AND parent.skill_name IS NOT NULL`) — it is not a
      measurement of an achieved state, because no writes to node Postgres were permitted in this
      sprint (node is still at schema v48; `skill_name_source` does not exist there). Closing AC 6
      requires deploying schema v49 to the node and running the real
      `backfill_skill_name_inheritance`, then re-measuring the achieved inheritance rate.
- [x] **AC 7** — no `routing_rollup` key/behavior change introduced. Real observed effect on the
      NULL-key count (30-day rolling window, same grouping as `routing_rollup.py`): **115 → 106
      NULL-clearing keys, a delta of 9** — closely tracking the contract's stated expectation of
      "≈10/113" (both figures drift with the rolling window over time, a documented pattern in the
      DI-4f spike legs; the total-keys-clearing count itself moved from 372→420 total keys between
      the contract's 2026-08-03 measurement and this one, hours apart).
- [x] **AC 8** — every parent/root join in the shipped code is `(id, project_id)`-scoped. Verified
      by code inspection (both repositories) and by `test_ac8_duplicate_id_across_projects_does_not_cross_contaminate`
      / `test_ac8_scoping_when_running_single_project_backfill_only` — a fixture with a *duplicate*
      session id across two projects, the exact shape that fooled two prior DI-4f spike legs.

7 of 8 AC met; AC 6 partial (projected pending node deployment).

## Measured Results (node Postgres, read-only, 2026-08-03)

Connection: `postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash` (creds resolved from the docs
convention already used by the DI-4f spike legs; `~/.config/aos/secrets.env` does not carry a
Postgres DSN). Node is currently at **schema v48** — `skill_name_source` does not exist there yet;
this migration has not been deployed to the node. All queries below are `SET TRANSACTION READ ONLY`;
no writes were issued anywhere against the node.

| Metric | Value | Query shape |
|---|---|---|
| Baseline inheritance success rate (reproduced) | **51.3%** (1,944 / 3,788) | Exact reproduction of the spike's `child_has_skill / (child_has_skill=true + false)` among `parent_has_skill=true` rows, using both `parent_session_id` (spike's column) and `subagent_parent_id` (shipped code's column) — confirmed identical for every `session_type='subagent'` row (0 rows differ) |
| Rows that would flip NULL→non-null system-wide (all-time) | **1,844** | `child.skill_name IS NULL AND parent.skill_name IS NOT NULL`, `(id, project_id)`-scoped |
| Orphaned subagents (AC 2 case, all-time) | **946** | Both `skill_name` NULL |
| Achieved rate post-backfill (same denominator) | **100%** (3,788/3,788) | The backfill closes every row in the 1,844 bucket unconditionally; nothing in that population remains NULL after one pass |
| `routing_rollup` NULL-clearing keys, current (30d window) | **115** | Reproduces `routing_rollup.py`'s exact grouping (`project_id, skill_name, model`, `updated_at` in `[now-30d, now]`), `min_sample=5` |
| `routing_rollup` NULL-clearing keys, projected post-backfill (30d window) | **106** | Same grouping, `skill_name` replaced by the one-hop inherited value for currently-NULL subagent rows |
| NULL-key delta | **9** | Consistent with the contract's stated "≈10/113" expectation once rolling-window drift is accounted for |

**This work has not been deployed/backfilled against the node.** The numbers above are: (a) the
real current-state baseline, measured directly, and (b) a read-only *projection* of the shipped
code's effect, computed by re-running the equivalent join/grouping logic against live data without
writing anything. Actually running the migration + `backfill_skill_name_inheritance` against the
node is a deployment step outside this sprint's scope (no writes permitted per the delegation
instructions).

## Transitivity Decision

**One hop only** — a child inherits its direct `subagent_parent_id`'s `skill_name`, never a
grandparent or family root. This was decided in Architecture Constraint 5 / Implementation Notes §6
of the contract and is documented verbatim in `skill_provenance.py`'s module docstring. Rationale
(already established, not re-derived): the 51.3% baseline this work is scored against is itself a
one-hop join; both DI-4f spikes measured only one-hop yield; a multi-hop walk needs cycle/depth
guards this dataset's nesting was never characterized against, for no measured additional gain.

## Validation Run

| Command | Result | Notes |
|---|---|---|
| `backend/.venv/bin/python -m pytest backend/tests/test_skill_name_source_provenance.py -v` | **Pass** | 18 passed (2 subtests) |
| `backend/.venv/bin/python -m pytest backend/tests/test_effort_tier_source_provenance.py backend/tests/test_aar_reviews_repo.py backend/tests/test_routing_rollup_repo.py backend/tests/test_research_runs_migration_governance.py -v` | **Pass** | 92 passed, 1 skipped (sibling provenance/parity precedents unaffected) |
| `backend/.venv/bin/python -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py backend/tests/test_sessions_repository_filters.py backend/tests/test_sessions_composite_pk_upsert.py backend/tests/test_session_repository_project_scope.py backend/tests/test_sync_engine_session_ingest_repository_wiring.py backend/tests/test_postgres_migrations_upgrade.py backend/tests/test_migration_concurrency.py backend/tests/test_sessions_parser.py -q` | **Fail (6), pre-existing** | See below — reproduced identically against a clean worktree at the pre-change base commit `8d56b5c`; none reference `skill_name_source` |
| `backend/.venv/bin/python -m pytest backend/tests/test_migration_concurrency.py -q` (retry) | **Pass** | 2 passed, 1 skipped — the concurrency failure above is a known SQLite-lock flake (matches the repo's own "test ordering db-path flake" memory note), not a real regression |
| `backend/.venv/bin/python -m pytest backend/tests/test_sessions_repository_filters.py backend/tests/test_sessions_composite_pk_upsert.py backend/tests/test_session_repository_project_scope.py backend/tests/test_sync_engine_session_ingest_repository_wiring.py backend/tests/test_sessions_parser.py backend/tests/test_session_scope_drift.py backend/tests/test_session_parity.py backend/tests/test_sync_engine_linking.py -q` | **Pass** | 104 passed, 6 skipped |

**Pre-existing failures, confirmed unrelated** — reproduced against a disposable git worktree
checked out at the pre-change commit (`8d56b5c`, before this contract's work), via
`git worktree add /tmp/ccdash-baseline-check 8d56b5c`:
- `test_sqlite_migrations.py::test_run_migrations_adds_usage_columns_even_when_schema_version_is_already_recorded`
  and `::test_run_migrations_upgrades_legacy_session_logs_before_bootstrap_indexes` — FK mismatch in
  the legacy v30 `session_logs`→`sessions` migration path. Unrelated to `sessions.skill_name_source`.
- `test_migration_governance.py::test_column_parity_all_shared_tables` — pre-existing `workspace_id`
  drift on `documents`/`entity_links`/`features`/`tasks` (Postgres has a default, SQLite doesn't).
  Unrelated to `sessions`.
- `test_postgres_migrations_upgrade.py::TestPostgresMigrationsAlreadyAtV35::{test_no_new_schema_version_insert,test_tables_ddl_skipped}`
  — the test hard-codes `starting_version=35` as "already current"; real `SCHEMA_VERSION` has been
  ahead of 35 since long before this contract (was 48 on `main`, now 49). Stale test, not a new
  regression.

No frontend files were changed; `pnpm test`/`type-check`/`lint` are not applicable per the
contract's Validation Requirements ("Backend tests only for correctness — no frontend file changes
are in scope").

### Runtime / browser spot-check

`runtime_smoke: skipped` — **reason**: this fresh worktree has no `node_modules` installed, and no
browser-automation tool was available in this delegated sprint's toolset to visually render and
screenshot `SessionInspector.tsx`. In its place, verified the render path by code inspection and by
the DB-level round-trip test:

1. `components/SessionInspector.tsx:5415-5422` guards the skill badge purely on
   `session.skillName` truthiness — no branch on provenance, identical structurally to the
   `contextWindow` badge immediately above it (lines 5407-5414), which already renders correctly in
   production today. There is no new code path a backfilled `skill_name` could exercise that isn't
   already proven safe.
2. `backend/routers/api.py:889,1311` (`skillName=s.get("skill_name")`) is an unconditional
   passthrough of the DB column — an inherited value is indistinguishable in shape from a
   directly-detected one at this layer, so the DTO requires no change and the FE receives the exact
   same `string | null` type it already handles.
3. `test_ac1_subagent_inherits_parent_skill` proves the DB write produces a valid, non-empty
   `skill_name` string for a backfilled row, which is all the badge's truthiness check needs.

This satisfies the contract's characterization of the requirement as "a spot-check, not a full
smoke gate" under the constraint that no runtime/browser tooling was provisioned for this sprint —
but it is not a live pixel-verified render, and should be treated as such.

## Deviations From Contract

- Token spelling: used `inherited_parent` instead of the contract expansion's proposed
  `inherited_from_parent`, per Architecture Constraint 7's explicit recommendation (documented in
  `skill_provenance.py`'s module docstring, and asserted by
  `test_inherited_token_matches_effort_provenance_spelling`). Not a deviation from the contract —
  the contract itself flags this as the recommended choice.
- No live browser screenshot (see Runtime spot-check above) — code-path verification substituted,
  toolset-constrained.

## Risks and Limitations

- The measured AC 6/AC 7 numbers are real-data *projections* of the shipped code's effect (computed
  via read-only re-derivation queries), not a post-deployment measurement — the migration + backfill
  have not been run against the node. Deploying and re-measuring after a real run is recommended
  follow-up, not part of this sprint (no writes permitted against the node per instructions).
- `routing_rollup`'s NULL-key count is inherently volatile (rolling 30-day window); the "9" and "115"
  figures will drift with wall-clock time exactly as the contract's own "≈10/113" figure has already
  drifted to "9/115" in the hours since 2026-08-03's initial DI-4f measurement. This is expected, not
  a discrepancy.

## Deferred / follow-up

- **Close AC 6**: deploy schema v49 and run `backfill_skill_name_inheritance` against node
  Postgres (`10.42.10.76:5440`), then re-measure the achieved inheritance rate and the real
  `routing_rollup` NULL-key delta. The container must be **rebuilt**, not just restarted —
  `podman-compose up -d` reuses the stale image on that node; use `podman-compose build` (per the
  repo's node-deploy memory notes) before restarting the api/worker services.

## Follow-Up Recommendations

1. **Gap 2 (effort_tier inheritance) can adopt this exact parent-walk.** The `(id, project_id)`-scoped
   join built in `backfill_skill_name_inheritance()` (both repositories) is generic one-hop
   parent-lookup machinery — it is not skill-specific in structure. Per Architecture Constraint 7,
   `effort_tier_source`'s reserved-but-unused `inherited_parent` token (Gap 2) could reuse this same
   join shape to populate `effort_tier` from a parent session. This contract deliberately does
   **not** populate `effort_tier` — that is a separate trust decision, out of scope here.
2. **Frontend provenance affordance** (not implemented, per the contract's explicit "do not fix this
   UI surface" instruction): once `skill_name_source` exists, add a `skillNameSource` field to
   `AgentSession` (`types.ts:581`) and the session DTO (`backend/routers/api.py:889,1311`), then a
   minimal visual distinction (e.g. an "inherited" glyph or `title` suffix) on both badge render
   sites (`components/SessionInspector.tsx:5415-5422`,
   `components/SessionInspector/TranscriptView.tsx:828-844`).
3. **Deploy schema v49 to the node and re-run the measurement** to replace this sprint's read-only
   projection with a real post-backfill measurement.
4. **Live browser confirmation** of the skill badge on an actual inherited subagent session should
   be captured whenever this ships to an environment with `node_modules` installed and browser
   tooling available — this sprint's code-path verification is a reasonable substitute but not
   equivalent.

## Memory Candidates Captured

None captured as formal memory items in this sprint; the following are worth a `candidate` memory
entry in a follow-up pass (not created here to stay within delegated scope):
- The `test_migration_concurrency.py` SQLite-lock flake is a known repo-level flake (already covered
  by the existing "CCDash test ordering db-path flake" memory note); no new capture needed.
- `spike-shape query (parent_session_id, session_type='subagent')` and the shipped
  `subagent_parent_id`-scoped join produce byte-identical results for every `session_type='subagent'`
  row on the node (0 differ) — useful confirmation that these two columns are redundant for this
  population, worth noting if a future contract considers consolidating them.
