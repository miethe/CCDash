---
leg_id: risk
confidence: 0.75
conclusion: "A new RF run entity is mechanically tractable within CCDash's layered architecture (strong dual-DDL/ingest precedent), but the correlation-key mismatch is a real design gap — RF's ids are non-UUID strings incompatible with the AOS sidecar-URN graph — and any run↔session rollup must apply D-001's dedup discipline from day one or it will reproduce the same over-count bug at a second layer."
tractability: tractable_with_conditions
correlation_strategy: "Do not extend aos_correlation.py's UUID-URN sidecar graph (RF ids are non-UUID semantic strings, e.g. intent_research_foundry_search_router). Link via a dedicated entity_links row (kind=research_run) keyed by RF's UUID run_id, carrying intent_id/task_node_id as opaque string attributes for display, not as join keys."
plumbing_estimate_points: 20
---

# Risk Spike: Research Foundry Run Telemetry — Correlation, DDL, Volume, Coupling

## 0. Correction to Prior-Art Leg's Claim (load-bearing)

`spikes/priorart-spike.md:14,23,187` states that AOS correlation indexing (676bcca) added
literal `aos_run_uuid` / `aos_session_uuid` / `aos_trace_uuid` / `aos_work_uuid` **columns**
to the `sessions` table. Direct read of runtime truth contradicts this:

- The actual T5-006 detection columns are `model_slug`, `workflow_id`, `subagent_parent_id`,
  `skill_name`, `context_window` (`backend/db/sqlite_migrations.py:228-234`; confirmed against
  CLAUDE.md "Session columns" section). There is no `aos_*_uuid` column anywhere in
  `backend/db/sqlite_migrations.py` or `backend/db/postgres_migrations.py` (grep: zero hits).
- AOS correlation is **not a stored column model at all**. It is a read-time derivation
  (`backend/services/aos_correlation.py:234` `derive_aos_correlation`) over three additive
  sources: (1) `AOS-ID:` footers in transcript text, (2) inline `urn:aos:<kind>:<uuid>`
  mentions in transcript text, (3) an external per-machine sidecar JSONL at
  `~/.aos/correlation/events.jsonl` (`aos_correlation.py:148-152`, path from `AOS_ID_HOME`).
  The result may be cached into `session_forensics_json.aosCorrelation`
  (`aos_correlation.py:333-336`, `_session_forensics_correlation`) but that is a JSON blob,
  not typed columns.
- `AOS_KINDS = (turn, session, run, feature, artifact, app, service, trace)`
  (`aos_correlation.py:16-25`) — "run" and "trace" are URN **kinds**, not column names, and
  there is no "work" kind at all.

This matters for the exploration verdict: the charter's premise ("map RF ids onto
`aos_*_uuid` columns") targets something that doesn't exist as a joinable DB artifact. The
real integration surface is the **sidecar-URN graph walk** (`_build_sidecar_index`,
`_expand_related_urns`, `aos_correlation.py:424-481`), which is UUID-string based, not a SQL
column at all. See §2 for why RF still can't plug into that graph directly.

## 1. Correlation-Key Mapping Analysis

| CCDash side | RF side (spec §16 `execution_event`) | Compatible? |
|---|---|---|
| `urn:aos:<kind>:<UUID>` (canonical 8-4-4-4-12 hex, `aos_correlation.py:27-30` `UUID_PATTERN`) | `intent_id: intent_research_foundry_search_router` (semantic slug string) | **No** — fails `UUID_RE`/`AOS_URN_RE`, `parse_aos_reference` returns `None` |
| same | `task_node_id: task_source_discovery_mvp` (semantic slug) | **No** — same reason |
| same | `event_id: exec_search_2026_06_21_001` (semantic slug) | **No** — same reason |
| same | `search_run.run_id` (RF spec §11.2, declared `string`, not typed as UUID) | **Maybe** — depends on RF's actual `run_id` generation; if RF emits a real UUID4 for `run_id`, this is the one field with a shot at joining the sidecar graph |

**Why this is a real gap, not a nitpick**: `_sanitize_sidecar_event` (`aos_correlation.py:366-421`)
only recognizes an event as resolvable if `kind`+`uuid` parse against `AOS_KINDS`/`UUID_PATTERN`,
or if `aos_<kind>_uuid`/`aos_<kind>_urn` raw fields parse the same way. RF's telemetry shape
(RF spec §16, lines 935-963) carries none of those — it is a flat `intent_id`/`task_node_id`
namespace with no `urn:aos:` convention. Feeding RF's raw event JSON into the sidecar file
verbatim would produce `unresolved_sidecar_row` diagnostics (`aos_correlation.py:207-216`) for
every line — silently inert, not silently wrong, but zero linkage value.

**Recommended strategy** (do not force-fit the AOS graph):

1. CCDash's own new `research_runs.run_id` column should be a genuine UUID (CCDash-generated
   at ingest time if RF doesn't supply one, or accepted as-is if RF's `run_id` is already a
   UUID4 — confirm with RF's tech-spike leg).
2. Link run↔session via **`backend/db/repositories/links.py`** entity-link rows (the existing
   generic linking primitive: `kind="research_run"`, `entity_id=run_id`,
   `linked_kind="session"`, `linked_id=session_id`), not via the AOS URN graph. `intent_id`/
   `task_node_id` are carried as **display-only string attributes** on the run row (for
   operator legibility and for IntentTree cross-reference by a human/downstream system), never
   as SQL join keys.
3. If/when RF or IntentTree later adopts `urn:aos:` UUIDs for its own nodes (out of scope per
   charter — "requires an RF-side or IntentTree-side alignment first"), the entity-link row can
   be supplemented with an AOS URN without a schema change (link rows are attribute-flexible).

### 1.1 Does a new run entity aggravate D-001?

**Yes, structurally identical failure mode, if not guarded.** D-001
(`docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`) is a session-token
double-count when a session joins to N features without `DISTINCT`/`GROUP BY` dedup
(`backend/routers/analytics.py`, `_session_usage_metrics`). A run↔session link is the same
one-to-many shape (one run may link N sessions; one session may link N runs via repeated
intent re-tries). Any future "combined workload" or "total cost" rollup that sums
`research_runs.provider_spend_usd` joined against `sessions.total_tokens` without deduplicating
on the join key will reproduce D-001's exact bug, but now cross-system (RF cost × AOS session
cost double-counted together). **Mitigation is cheap if designed in now**: apply D-001's
Option A (`SELECT DISTINCT`/`GROUP BY` before sum) as a hard rule for any new run-aware
rollup, and add the D-001-style regression test (two runs sharing one session; assert session
tokens counted once) alongside the new feature's own tests — do not wait for a second finding.

## 2. Dual-DDL Parity Checklist + Plumbing Estimate

CCDash's migration governance is automated and will hard-fail CI on drift
(`backend/db/migration_governance.py`, `backend/tests/test_migration_governance.py`) — this
is a strong tractability signal: the guardrail exists, it just must be satisfied.

**Per-table checklist** (repeat for `research_runs` and `run_events`):

- [ ] `CREATE TABLE IF NOT EXISTS` block in `backend/db/sqlite_migrations.py` under a new
      versioned migration block (precedent: `sqlite_migrations.py:3762-3800`, v36
      `ingest_cursors` — 39 lines for one table + one index + one column backfill)
- [ ] Matching `CREATE TABLE IF NOT EXISTS` block in `backend/db/postgres_migrations.py`
      (precedent: `postgres_migrations.py:3301-3336`) — same version number, same column set,
      Postgres-native types (`JSONB` not `TEXT`, `SERIAL`/`BIGSERIAL` not `AUTOINCREMENT`) per
      `_difference_categories` allowed drift categories (`migration_governance.py:287-301`)
- [ ] `get_sqlite_migration_tables()`/`get_postgres_migration_tables()` parity — auto-verified
      by `test_migration_governance.py:test_shared_migration_tables_match_across_backends`;
      no manual allowlist entry needed unless the table is enterprise-only
- [ ] New repository module implementing the relevant `Protocol` in
      `backend/db/repositories/base.py` (precedent: `ingest_cursors.py`, 251 net-new lines
      for one table's CRUD + stats)
- [ ] Every write path wrapped in `retry_on_locked` (`base.py:114`) — direct precedent already
      applied to `sessions.py`, `execution.py`, `projects.py`, `worktree_contexts.py`
- [ ] Direct-count assertion test post-write (ADR-007 §4) — precedent:
      `backend/tests/test_ingest_cursor_repository.py`
- [ ] `PRAGMA busy_timeout=30000` on any independent sync connection touching the new tables
      (only relevant if a sync-side/CLI path opens its own connection; the async singleton
      already sets this)

**Budget** (backend-only; excludes RF-side emission and FE tab per charter's out-of-scope):

| Slice | Points | Basis |
|---|---|---|
| `research_runs` table: dual DDL + repo + governance + direct-count test | 5 | Comparable to `ingest_cursors` v36 slice (~39+34 DDL lines, 251-line repo) |
| `run_events` table (cursor-paginated child log): dual DDL + repo + tests | 5 | Same shape as `session_messages`/`ingest_cursors`; cursor pagination adds ~1pt over a flat table |
| Ingest write path (reuse idempotent NDJSON pattern + `ingest_cursors` row for an `rf` source) + health wiring | 3 | Transport already exists (ADR-014/015); marginal cost is a new source type + dedup key (`event_id`) |
| Run↔session entity-link adapter (§1 strategy) + regression test for D-001-shape dedup | 5 | Novel logic, no direct precedent; higher uncertainty |
| Transport-neutral query service (`run_intelligence.py`) + REST route + capability flag | 2 | Follows the well-worn `agent_queries/` → `routers/agent.py` pattern |
| **Total** | **20** | |

## 3. Ingestion Volume / Write-Path Risk

RF's telemetry cadence is **per-search-run** (RF spec §11.2/§16 examples: `latency_ms` in the
tens of seconds, one `execution_event` per intent/task invocation), not per-message like
session JSONL. This is materially lower write frequency than the existing session ingest path.

**Correction to the charter's framing**: `CCDASH_SYNC_COALESCING_ENABLED`
(`backend/config.py:1268-1277`) guards the **filesystem watcher's** `(project_id, trigger)`
sync-dispatch path (`backend/db/sync_engine.py:3212-3238`) — it exists to coalesce redundant
*local JSONL rescans*. RF is not a filesystem source; it is an external service pushing over
HTTP (or absent entirely, per the tech leg). **The sync coalescing guard does not apply to RF
ingestion at all** — treating it as if it does would be a false sense of protection. The
correct write-path safety net is the one already built for exactly this shape (external
push, idempotent by id): the remote-ingest pattern's `event_id`-keyed dedup + `ingest_cursors`
per-source cursor row + dead-letter queue (`docs/guides/remote-ingest-operator-guide.md:36-39`).
**Reuse that, don't invent a new coalescing mechanism.**

Given low cadence + existing idempotent-batch infrastructure, write-lock contention risk from
RF ingestion specifically is **low**, conditional on: (a) writes go through `retry_on_locked`
like every other write path (ADR-007), and (b) RF ingestion does not itself trigger a
filesystem sync/reconcile pass (it shouldn't need to — it's not a session source).

## 4. Cross-System Coupling / Resilience-by-Default

RF runs as an independent service (node `:7432`, per user's global context) with its own
uptime/deploy lifecycle, separate from CCDash's. Per CLAUDE.md's "Resilience-by-default" rule
("every new optional backend field requires an explicit FE fallback AC; missing is a contract
state, not a bug"), every RF-sourced field must degrade gracefully:

- **If RF telemetry never arrives for a given run**: `research_runs` rows created via ingest
  only — no synthetic/backfilled rows. Absent run = absent row (not a null-filled row), same
  posture as `ingest_sources` degrading to zero/null documented for the offline-CLI mode.
- **If RF stops flowing mid-stream**: existing precedent is `/api/health/detail`'s
  `ingest_sources[]` array with `CCDASH_INGEST_SOURCE_FRESH_SECONDS`/`_STALE_SECONDS`
  (`backend/config.py:1166-1177`) — register an `rf` source entry so staleness is observable
  exactly like other remote sources, rather than a bespoke "RF health" surface.
- **If a session has no linked RF run** (the common case pre-rollout and for non-research
  sessions): all RF-derived UI fields (provider spend, citation coverage, etc.) must render an
  explicit empty/absent state, never `0`/`NaN` masquerading as "no cost incurred." This is the
  same class of bug as D-001 (a display artifact from an unhandled join edge) — absence must
  be a distinct rendered state.
- **Capability advertisement**: extend `/api/v1/capabilities`
  (`backend/routers/client_v1.py:146-147`) with a `research-runs:*` capability string so
  external consumers (IntentTree, LAN agents) that predate this feature don't hard-fail on an
  unknown field — same contract already established for `sessions:detail`/`sessions:cross-project`.
- **What breaks if RF telemetry stops flowing entirely**: nothing in CCDash's existing surfaces
  (sessions, planning, analytics) — the new run entity is additive by construction (new table,
  new endpoint, new tab). The only failure mode is the new surface itself going stale/empty,
  which is an acceptable, observable, non-cascading degradation if the health-source pattern
  above is followed.

## 5. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| RF ids (`intent_id`/`task_node_id`/`event_id`) are non-UUID strings; cannot join the AOS sidecar-URN graph | Medium | Certain (confirmed by spec inspection, §1) | Link via `entity_links` (kind=`research_run`) keyed by a CCDash/RF-supplied UUID `run_id`; carry RF's semantic ids as display attributes, not join keys |
| Prior-art leg's claim of literal `aos_*_uuid` columns is inaccurate | Low (documentation risk) | Confirmed | This spike corrects the record (§0); downstream design docs referencing those column names must be revised before implementation |
| New run↔session rollup reproduces D-001's multi-parent over-count | Medium | Medium-High if any "combined cost/workload" metric ships without dedup | Apply D-001 Option A (`DISTINCT`/`GROUP BY` before sum) as a hard rule; ship the D-001-shape regression test alongside the new rollup, don't defer it |
| Dual-DDL drift (SQLite vs Postgres column/type mismatch) | Medium | Low — governance test suite auto-fails on table-set drift (`test_migration_governance.py`) | Follow the `ingest_cursors` v36 precedent exactly; run `test_migration_governance.py` before merge |
| Sync-coalescing guard mistakenly assumed to protect RF writes | Low | Medium (charter itself frames it this way) | This spike clarifies (§3): reuse the remote-ingest idempotent-batch pattern instead; coalescing guard is filesystem-watcher-scoped only |
| RF service down/absent — new surface goes stale | Low (non-cascading) | Medium (separate deploy lifecycle, node `:7432`) | Register as an `ingest_sources[]` entry with freshness thresholds; explicit absent-state rendering, not zero-filled |
| Ingest volume spike (many concurrent RF runs) causes write-lock contention | Low | Low (RF run cadence is coarse — per-intent, not per-message) | `retry_on_locked` on every write path (ADR-007); reuse dead-letter queue for permanent failures |
| Scope creep: run entity absorbs session-forensics responsibilities already owned by `aos_correlation.py` | Low | Low if §1 strategy is followed (deliberately non-overlapping) | Keep run entity and AOS correlation as parallel, independently-queryable systems; cross-link, don't merge |

## 6. Blast Radius

**Additive-only if the §1 linking strategy is followed**: two new tables
(`research_runs`, `run_events`), one new repository module, one new transport-neutral query
service, one new REST namespace (`/api/agent/research-runs*` or `/api/v1/ingest/research-runs`),
one new entity-link kind, one new `ingest_sources` health entry, one new capability string.
**Zero modification** to existing `sessions`, `aos_correlation.py`, `analytics.py`
(`_session_usage_metrics`), or `planning_sessions.py` code paths is required — the correlation
strategy in §1 explicitly avoids touching the AOS URN graph or its sanitize/index functions.
The only shared-surface touch is `backend/db/repositories/links.py` (adding a new linkable
entity kind, additive) and `backend/routers/client_v1.py` (capability list, additive).

**Conditions for the `tractable_with_conditions` verdict**:

1. Accept the §1 correlation strategy (entity-link table, not AOS-URN-graph extension) as the
   design baseline before implementation — do not attempt to retrofit RF ids into
   `aos_correlation.py`'s UUID parser.
2. Any run-aware analytics rollup ships with the D-001-shape dedup test from day one.
3. RF ingestion reuses the existing idempotent NDJSON/`ingest_cursors` transport rather than
   inventing a new write path or relying on the filesystem-sync coalescing guard.
