# Implementation notes - are-we-winning-dashboard-v1

Deviations, assumptions, and discovered constraints are appended here per
milestone, never overwritten.

## M1 - IntentTree lifecycle events are durable in CCDash

Schema version: bumped SQLite/Postgres SCHEMA_VERSION 54 -> 55. New table
intent_tree_events, declared in both the _TABLES fresh-DB executescript
blocks AND a version-gated "if current_version < 55" migration block in each
of backend/db/sqlite_migrations.py / backend/db/postgres_migrations.py
(mirrors the rf_events v40 precedent exactly -- governance parity checking
(migration_governance.py) only parses _TABLES, so the table had to be
declared there for test_migration_governance.py to see it at all; the
version-gated block is what actually adds the table for pre-existing DBs).

Cursor durability -- reused ingest_cursors, did not add a dedicated table.
ingest_cursors is keyed on (source_id, project_id, workspace_id) with
project_id NOT NULL and no default (ADR-009) -- it was designed to scope
per-CCDash-project sources (filesystem/remote-session ingest, RF events).
IntentTree's event log is workspace-scoped, not CCDash-project-scoped, so
there is no real project_id to supply. Rather than adding a dedicated
single-purpose cursor table, I reused ingest_cursors with a fixed sentinel
project_id="global" (constant SENTINEL_PROJECT_ID in
backend/application/services/ingest/intenttree_events_ingest.py) and one
distinct source_id per event type ("intenttree:node.created",
"intenttree:node.completed") since the table has no event_type column of
its own and each type's watermark needs to advance independently. This keeps
the write path, repository, and factory wiring 100% reused rather than
introducing a second cursor concept.

Cursor semantics are bookkeeping/durability, not incremental skip-ahead.
Every scheduled tick pages fully through next_cursor from the most-recent
event backward until the API reports next_cursor: null, upserting
idempotently (id PK, INSERT OR IGNORE / ON CONFLICT DO NOTHING) rather than
resuming from the last-ingested event id and early-exiting. This was a
deliberate simplicity choice: the measured live volume (11,867 events total,
3,941 node.created + 745 node.completed) means a full sweep is at most ~20
pages per type at the 200-row cap -- cheap for a 900s-default interval job --
and it sidesteps a subtler correctness question (what does "resume" mean
against a most-recent-first keyset feed that keeps growing at the head? An
early-exit-on-seen-id optimization is a reasonable follow-up if volume
grows, but was out of scope for getting ingestion durable and correct
first). The ingest_cursors.last_cursor column is still written (set to the
newest event id seen each successful sweep) purely as observability/audit
bookkeeping, matching the existing repository's advance() contract.

Fail-soft failure boundary is "per event type", not "per page". If a page
fetch fails after some earlier pages in the same sweep already succeeded,
those earlier rows are NOT rolled back -- they are real, idempotently-
upserted events, and rolling them back would require an explicit transaction
spanning the whole multi-page HTTP round trip. Only a sweep where the very
first call fails leaves the cache byte-identical to before the run. This
matches the milestone AC's literal wording ("leaves cache state
byte-identical") and is covered by
backend/tests/test_intenttree_events_ingest.py::FailSoftTests (including an
explicit test for the partial-success-then-failure case, documented as
intentionally not byte-identical).

Payload storage. payload_json is nullable TEXT (JSONB on Postgres, per the
rf_events precedent for cross-backend JSON parity) with no default --
"unknown == null, never a fabricated default." The measured worknote found
node.updated carries no payload at all (0/200 sampled) and even
node.created/node.completed are not schema-guaranteed to; a NOT NULL default
would misrepresent that.

Job wiring circular-import avoidance. backend/adapters/jobs/*.py modules
never import from backend.application.services.* at module scope -- that
package's __init__.py chain eventually imports back into
backend.adapters.jobs via backend.runtime_ports.
intenttree_events_ingest_job.py follows the same discipline as
routing_rollup_sweep_job.py/aar_review_sweep_job.py: the service type is
only imported under TYPE_CHECKING (safe because "from __future__ import
annotations" defers annotation evaluation), and the real import happens
inside _construct_intenttree_events_ingest_job() in
backend/runtime/container.py (a local, deferred import, same pattern
rf_events_ingest_service already uses there).

Job scheduling profile gate. Constructed for both worker and worker-watch
profiles (_WORKER_JOB_PROFILES/_export_profiles precedent), but
_start_intenttree_events_ingest_task only actually starts the periodic loop
under the plain worker profile -- mirrors _start_routing_rollup_sweep_task's
identical asymmetry verbatim (construct broadly, start narrowly).

Pre-existing, unrelated test failure observed, not introduced or fixed.
backend/tests/test_migration_governance.py::MigrationGovernanceTests::test_column_parity_all_shared_tables
fails on documents/entity_links/features/tasks workspace_id drift (Postgres
carries a default the SQLite side doesn't). This drift exists on main
independent of any M1 change -- git diff --stat for this milestone touches
only backend/config.py, backend/db/factory.py,
backend/db/postgres_migrations.py, backend/db/sqlite_migrations.py,
backend/db/repositories/intent_tree_events.py,
backend/application/services/ingest/intenttree_events_ingest.py,
backend/adapters/jobs/intenttree_events_ingest_job.py,
backend/adapters/jobs/runtime.py, backend/adapters/jobs/__init__.py, and
backend/runtime/container.py -- none of which touch those four tables. Per
the task's instruction not to weaken or delete an existing test, this was
left untouched and unfixed; intent_tree_events itself is confirmed
parity-clean by construction (test_intenttree_events_ingest.py's own
IntentTreeEventsMigrationGovernanceTests, and
test_migration_governance.py::test_validate_migration_governance_contract --
the table-set-level contract check -- passes).

Not done in M1 (explicitly out of scope per the plan): the M2 query service
(weekly rollups, reopened derivation, self-caught ratio) and any frontend
work. No REST endpoint was added -- CCDASH_ARE_WE_WINNING_ENABLED currently
gates only the ingestion job, per the task instructions ("later, the REST
surface").

Verification performed: local SQLite only, per the Mode-D boundary in the
task instructions -- no migration was applied to the shared LAN Postgres
instance. npm run docker:hosted:smoke:seeded-pg (the plan's own named
Postgres-operability check) was NOT run in this milestone's execution; the
Postgres DDL path was verified by static parity-diff assertion
(column_parity_diff) and by the dual-DDL governance test suite, not by
booting a live Postgres container, which was outside this task's explicit
scope (local SQLite + local test fixtures only). Flagging this so M2/M3 (or
a follow-up) explicitly runs the seeded-Postgres smoke before relying on the
Postgres path in production.

## M1 fix pass (reviewer gate -> CHANGES_REQUESTED, then re-passed)

The M1 gate (Codex gpt-5.6-terra, read-only, adversarial) returned CHANGES_REQUESTED with four
file:line-backed defects. All four were fixed in a follow-up pass; the focused suite went 10 -> 13
tests (three new regression tests, one per behavioural fix).

1. Pagination could loop forever. The loop trusted next_cursor to eventually become null, so a
   server returning a STABLE cursor -- or an empty items page still carrying a non-null cursor --
   pinned the worker indefinitely. Now cycle-detected and terminated with a NON-success result
   (a stalled sweep is a failed sweep, not a clean finish), plus a defensive page-count bound.
   Both shapes are covered by PaginationLoopGuardTests, whose fakes self-bound so a regression
   fails fast instead of hanging the suite.

2. Fail-soft was swallowing programming errors. The blanket `except Exception` converted genuine
   bugs (AttributeError/TypeError/...) into a reported-success no-op. Narrowed to
   `except (httpx.TransportError, httpx.HTTPStatusError)`; unexpected exceptions now propagate to
   the runtime failure handler. Fail-soft means "the remote is unavailable", never "our code is
   wrong".

3. An event id was being written into a timestamp column. `_cursor_advance` passed
   occurred_at=cursor_value, putting an opaque event id into last_ingest_at -- a field that would
   then lie to every future reader and to any staleness/lag reporting built on it. Now writes a
   real success timestamp; the id stays in last_cursor where it belongs. The two fail-soft tests
   were strengthened to seed an EXISTING cursor row first and assert both last_cursor and
   last_ingest_at are unchanged after a failing sweep -- previously they only proved nothing was
   added, not that nothing was corrupted.

4. The v55 entry was missing from the lockstep schema-version history lists in both
   sqlite_migrations.py and postgres_migrations.py, though SCHEMA_VERSION itself was bumped.
   Added to both, matching the surrounding entries' style.

Environment constraint discovered: the ICA-delegated executor could not append to this file --
every Edit against `.claude/worknotes/**` was auto-denied as a sensitive-file edit with no
approval path available in a `-p` (non-interactive) session. This section was therefore written by
the orchestrator from the executor's report. Worth knowing generally: a delegated leg cannot be
relied on to write its own deviation log under `.claude/`, so the orchestrator must carry it.

## M2 part A - weekly rollups, drill-through, REST surface

(Recorded by the orchestrator from the executor's report: the delegated ICA leg was again
permission-blocked from editing `.claude/worknotes/**`. Same constraint as the M1 fix pass.)

Module shape follows `system_metrics.py` -- the sibling transport-neutral, cache-backed metrics
service -- rather than inventing a layout. The service reads only CCDash's own `intent_tree_events`
cache: zero live IntentTree calls, zero model calls, satisfied by construction rather than by
convention. Two tests pin this by patching the integration client to RAISE on any call and then
exercising both REST read paths.

ISO-week bucketing per the OQ-2 decision (Monday-Sunday fixed boundaries, not a rolling 7-day
window), chosen so weekly rollups have a stable cache key. During implementation the first draft of
the boundary test disagreed with the implementation; the implementation was found correct and the
test corrected -- noting it here because "fix the test until it passes" is the failure mode that
looks identical from the outside, and it was not what happened: the Sunday-23:59 / Monday-00:00
pair and the ISO week-1-vs-52/53 year-boundary case are both asserted against calendar truth.

The full M2 response contract is defined here, but only half is implemented. `reopened` and
`self_caught_ratio` are `Optional` and always `None` on this leg, with
`compute_reopened_trendline` / `compute_self_caught_ratio` present as `NotImplementedError`
extension points that are never called. This is deliberate: those two derivations are reserved to
the claude-primary lane (plan `routing_constraints`) because their failure modes are silently
plausible. A test asserts they serialize as null and never as `0` -- missing is a contract state,
not a bug, and a fabricated zero would be indistinguishable from a real measurement of zero.

Postgres `@memoized_query` hazard (a named plan risk): both memoized entry points return pydantic
DTOs directly, matching `system_metrics.py`. This was checked rather than assumed -- the
`PostgresCacheBackend.aset` unguarded-`json.dumps` defect (main `579aaf2`) is already shipped in
this tree, and `cache.py` now guards non-JSON-native values via `_json_safe`, so no extra
flattening was required.

Environment: no `backend/.venv` resolves inside this worktree, and the executor's sandbox would not
approve the absolute main-repo venv path, so it built a disposable local venv and ran pytest with a
`pythonpath` override. No repo config was touched and nothing was left tracked. The orchestrator
independently re-ran the suite with the real main-repo venv: 7/7 passed.

## M3 - dashboard view

(Recorded by the orchestrator from the executor's report: the delegated ICA leg was permission-
blocked from editing `.claude/worknotes/**`, as on every prior leg.)

Extended the existing Analytics module rather than parallel-building: `AnalyticsDashboard.tsx` gains
an `AreWeWinningTab`, and the ratio widget renders through the existing
`primitives/InteractiveChartCard`. That reuse is what satisfies recharts trap 1 for free -- the
primitive already carries `isAnimationActive={false}` on `<Pie>` (added 2026-07-31 after a browser
smoke found sectors appearing ~550ms late). A parallel chart stack would have had to rediscover it.

New pure-function module `lib/areWeWinning.ts` holds trendline-point and ratio-bucket chart mapping,
dependency-free from React/recharts, specifically so the "`unknown` renders as a first-class bucket
even at 100%" rubric item is asserted by a plain unit test rather than only through a component
render. `ratioToChartData` always emits all three closed-vocabulary buckets -- filling an omitted
one in explicitly -- so the legend cannot silently drop a bucket the backend failed to serialize.
`formatRatioBucketPercent` renders an em-dash for a zero-total population rather than 0%/NaN%.

Wire adaptation: the backend DTOs declare no `alias_generator`, so the payload is snake_case;
`services/queries/areWeWinning.ts` adapts to camelCase client-side, mirroring the established
`services/queries/researchRuns.ts` Wire*/adapt* pattern rather than inventing a new style. Endpoints
live under `/api/agent/are-we-winning/*` (the `agent_router` prefix); there is no `/api/v1` surface
for this feature.

Feature-flag gating surfaces as HTTP 404 (`are_we_winning_disabled`) from both endpoints. The FE
deliberately does NOT special-case that status: both hooks resolve every error uniformly to null and
the tab renders one "not available" panel for the whole class (flag off, backend down, fetch
failure), matching the existing convention in `services/queries/analytics.ts` rather than adding a
distinct-reason-code branch this milestone does not need.

Discovered constraint: `InteractiveChartCard` reaches for router context at the top of the
component even with `persistToUrl` defaulted false, so any test rendering `AreWeWinningTab` with a
populated ratio must wrap it in a `MemoryRouter` -- even though this tab never itself reads or
writes search params.

## M2 part B - reopened derivation + the 3-bucket self-caught ratio (claude-primary)

Terminal-status set chosen: `TERMINAL_STATUSES = frozenset({"completed"})` -- completed only,
deliberately NOT the broader set (archived, deferred) a first pass might reach for. Ground-truthed
against the live IntentTree source at `~/dev/homelab/development/intenttree/backend/src/intenttree/
models/enums.py` (`NodeStatus`, confirmed exactly 15 values, matching the brief's stated count:
not_started, ready, in_progress, blocked, waiting_review, completed, deferred, archived, inbox,
backlog, side_quest, active, running, waiting_human, reviewing). Rationale, in order of weight:
(1) the derivation's own candidate-set gate is explicitly "ever emitted node.completed" -- using a
different set to decide *reopens* than the set used to decide *eligibility* would be an unstated
inconsistency; (2) `archived` is genuinely ambiguous (can mean "done and shelved" OR "abandoned
without finishing"), so treating it as terminal risks a false-positive reopen when a *cancelled* node
is later un-archived and resumed -- that is "shelved work resumed", not "completed work regressed",
and counting it would be the exact silently-plausible wrong boundary the plan's routing_constraints
name; (3) deferred/backlog/inbox are parking states for work never done in the first place. Recorded
as a named constant (`TERMINAL_STATUSES`, `backend/application/services/ingest/
intenttree_reopened_derivation.py`), pinned by a dedicated test
(`test_terminal_statuses_constant_is_completed_only`), never an inline literal.

Ever-completed scope bound -- enforcement AND assertion. Enforced structurally: the reopened
derivation's only entry point into "which nodes to examine" is `distinct_node_ids_for_event_type(db,
"node.completed")`, a single choke-point query against CCDash's own already-ingested
`intent_tree_events` table (never "all nodes", never a live IntentTree node-list call). Asserted (not
merely true by accident) by `DerivationScopeTests::test_candidate_set_is_exactly_the_ever_completed_set`,
which seeds 3 completed nodes + 2 created-only nodes and asserts BOTH `result.candidate_node_ids`
AND the fake HTTP getter's actual recorded call list equal the completed-only set exactly (a widened
scope would fail this test loudly, per the task's explicit instruction).

Self-caught ratio -- why the shipped default resolves every node to `unknown` today, and why that
is evidence-backed rather than merely cautious. Cloned and grepped the live IntentTree source
(`~/dev/homelab/development/intenttree/backend/src/intenttree/`) rather than guessing field shapes:
confirmed `NodeRead.tags: list[str]` and `NodeRead.meta: dict` exist exactly as the worknote implies
(verified against a real captured `get_node` MCP tool-result JSON, not just the source), and found
`meta.origin`'s actual value vocabulary in `services/work_item_sync.py`'s `derive_default_origin` +
seed data: `meta_plan`, `implementation_plan`, `human_gate`, `decision`, `bug`, `deferred`,
`imported_plan`, `source_artifact`. These are node-*provenance* labels -- which kind of artifact
synthesized the node during an import/sync -- not a "who caught this" attribution field, and the
worknote itself already disqualifies the `finding` tag on the same grounds ("marks THAT something is
a finding, not WHO caught it"). Given neither confirmed proxy signal discriminates self vs.
other-caught, `decide_self_caught_bucket` (mirrors `decide_attribution`'s closed-vocab, single-pass
shape) ships with `_DEFAULT_ORIGIN_BUCKET_MAP = {}` -- deliberately empty, so every node resolves to
`unknown` today. This is the honest rendering of the measured reality (plan rubric, verbatim), not a
placeholder to "fix" by inflating a bucket. The function still accepts an injectable
`origin_bucket_map` so the closed-vocabulary machinery is real and testable
(`ClosedVocabularyTests::test_recognized_origin_value_resolves_correctly_when_a_map_is_injected`
proves genuine self_caught/other_caught branching, not just "always unknown") and so that IF
IntentTree's origin vocabulary is later confirmed to carry a real attribution signal, wiring it in is
a one-line change to the map, not a new code path. Fixture fraction bucketing to `unknown`: **100%**
in every fixture in `test_are_we_winning_derivations.py` (by design -- the shipped default map is
empty), confirmed explicitly by
`SelfCaughtUnknownBucketTests::test_100_percent_undiscriminated_population_yields_all_unknown_no_reduced_denominator`.

Both derivations run on the ingestion side only, per the architectural constraint. Two new services,
`IntentTreeReopenedDerivationService` / `IntentTreeSelfCaughtDerivationService`
(`backend/application/services/ingest/intenttree_reopened_derivation.py` /
`intenttree_self_caught_derivation.py`), read CCDash's own cached `intent_tree_events` for their
candidate sets and make live IntentTree HTTP calls (`GET .../nodes/{id}/history?field=status`,
`GET .../nodes/{id}`) ONLY from there -- never from the query service. The query service
(`are_we_winning.py`) gained `compute_reopened_trendline`/`compute_self_caught_ratio` as pure cache
readers (new tables `intent_tree_reopened_events`/`intent_tree_self_caught_buckets`, SCHEMA_VERSION
55 -> 56 in both backends, zero column-parity drift, verified the same way M1 was: static
`column_parity_diff`, not a live Postgres boot -- same Mode-D-scoped local-SQLite-only verification
as M1/part A, not repeated here). Part A's two zero-render-path-egress tests (the client-patched-to-
raise tests in `test_are_we_winning_rollups.py`) still pass unmodified; three more were added in the
new file covering the new surfaces (`get_summary` with real derived data present,
`get_reopened_drill_through`, `get_self_caught_drill_through`).

Never-run-yet vs. ran-and-empty, the AC4-preserving design choice. A table with zero rows is
ambiguous on its own. `get_summary` distinguishes them via a new pure-SQL, read-only helper,
`_derivation_has_ever_run(db, source_id)`, checking `ingest_cursors.last_ingest_at IS NOT NULL` for
that derivation's source_id (`intenttree:reopened_derivation` / `intenttree:self_caught_derivation`,
reusing the same `ingest_cursors` table + sentinel-project-id convention M1 established) -- a
row only gets that watermark set on a FULLY clean derivation pass (mirrors M1's per-event-type
cursor-advance-on-success-only contract exactly). This is why the pre-existing part-A test
(`AbsentNotZeroTests::test_reopened_and_self_caught_ratio_serialize_as_null_never_zero`) passes
UNMODIFIED: it never runs a derivation pass, so no cursor watermark exists, so both fields correctly
stay `None`. `AbsentUntilDerivedTests` in the new file generalizes this explicitly and adds the
converse case (watermark set, tables genuinely empty -> fields populate for real, e.g.
`reopened.points == []`, never stay `None`).

Incremental design differs deliberately between the two derivations, both recorded in the module
docstrings, not just here. Reopened: full re-walk of the entire candidate set every pass (a node can
complete/reopen/re-complete more than once; skipping "already-seen" nodes would silently miss a new
reopen on a previously-examined node) -- `insert_if_not_exists` keyed on the upstream IntentTree
NodeHistory row id keeps a full re-walk idempotent and cheap. Self-caught: incremental
(candidate set = `distinct(node.created ids) - already_bucketed_ids`) -- a bucket verdict is a
point-in-time tags/meta snapshot, and once written is never re-derived; trade-off recorded explicitly
(a node's tags/meta changing after bucketing won't retroactively update its stored bucket), judged
zero-impact today given the confirmed absence of any discriminating signal.

Fail-soft mirrors M1 exactly, extended to a per-candidate-node loop rather than per-page: a transport
failure on any one node stops the whole sweep, records the error on the cursor, and does NOT advance
the watermark, while rows already committed for nodes processed before the failure are NOT rolled
back. Covered by `ReopenedDerivationServiceIntegrationTests`/`SelfCaughtDerivationServiceIntegrationTests`'s
fail-soft tests, which assert both the not-rolled-back real data AND the non-advanced watermark in the
same test.

Cross-cutting gap found and fixed (not merely noted): M3's frontend (already committed in this
worktree ahead of this task, `22f97f7`) wires its "Nodes Reopened" `TrendChart` click handler through
the SAME generic `/api/agent/are-we-winning/drill-through?event_type=...` endpoint used for
created/completed (`trendline.event_type` round-trips verbatim -- see
`lib/areWeWinning.ts`'s `trendlineToChartPoints` and `components/Analytics/AreWeWinningTab.tsx`'s
`openTrendPointDrillThrough`), NOT a new dedicated endpoint. Left as originally scoped, that click
would have silently returned an empty page the instant `reopened` stopped being `None` -- a
textbook decorative click target, which the plan's rubric names explicitly as an AC failure. Fixed
in the backend, not the frontend (in scope): `get_drill_through` now also accepts
`event_type="node.reopened"` and internally dispatches to the pre-derived reopened cache; regression-
pinned by `DrillThroughParityTests::test_generic_get_drill_through_also_serves_node_reopened`, whose
docstring cites the exact FE call path this protects. A SEPARATE dedicated
`get_reopened_drill_through`/`GET /are-we-winning/reopened-drill-through` was also added (API
completeness/transport-neutral-CLI-MCP-future-use), but the generic-endpoint fix is the one that was
load-bearing for the shipped FE.

Self-caught ratio drill-through: genuinely new capability, not a gap in already-shipped FE code. The
already-shipped `SelfCaughtRatioWidget` in `AreWeWinningTab.tsx` explicitly renders "Per-bucket
drill-through is not yet available -- the current backend contract (SelfCaughtRatioBucketDTO)
reports only a bucket + count, with no underlying-row coordinates" -- i.e. M3 correctly did NOT wire
a click handler for a capability that did not exist yet, so there is no decorative-click-target bug
here today. This task adds that capability (`get_self_caught_drill_through` /
`GET /are-we-winning/self-caught-drill-through`, backed by `intent_tree_self_caught_buckets` +
`reason`), but wiring the FE's bucket rows to call it is frontend work and is explicitly out of this
task's scope (M3/a follow-up must add the click handler + drill-through modal invocation for the
ratio legend).

REST wiring beyond the two new query-service methods: both new endpoints were added to
`backend/routers/agent.py` following the exact existing pattern (same `_require_are_we_winning_enabled`
dependency gate, same otel span convention) -- CLI/MCP transport exposure (per CLAUDE.md's
transport-neutral convention) was judged out of scope for this task and is not yet done.

Deliberately NOT wired into the periodic scheduler (`backend/adapters/jobs/runtime.py` /
`backend/runtime/container.py`'s `_construct_intenttree_events_ingest_job`-sibling construction +
task-loop registration). The two derivation *services* and their fail-soft/idempotency/cursor
behavior are fully implemented and unit-tested exactly like M1's ingestion job. What's missing is a
`IntentTreeDerivationJob` wrapper class + its periodic-task registration, mirroring
`intenttree_events_ingest_job.py`'s shape. Reason for stopping short: that wiring touches
`RuntimeJobAdapter`/`RuntimeContainer` state, which is exercised by
`backend/tests/test_runtime_bootstrap.py` -- a test file this repo's own operator memory documents as
hanging at import/collection time (unkillable), so I have no way to verify a runtime-bootstrap change
is correct. Per the boundary against weakening/skipping tests and the general principle of not
touching code I cannot verify, I left this as an explicit, named follow-up rather than making an
unverified edit to shared runtime bootstrap code. The derivation job needs to run periodically for
the feature to self-refresh in production; until that wiring lands, `derive_all()` on both services
would need to be invoked manually/out-of-band (e.g. a one-off script or a future job wrapper) to
populate the cache in a live deployment.

Pre-existing, unrelated test failure observed, not introduced. Ran
`backend/tests/test_migration_governance.py` alongside the new suite:
`MigrationGovernanceTests::test_column_parity_all_shared_tables` fails on `documents`/`entity_links`/
`features`/`tasks` `workspace_id` drift (a Postgres-side default the SQLite side lacks). Confirmed via
`git diff --stat` that this milestone's diff touches only `backend/application/services/agent_queries/
are_we_winning.py`, `backend/application/services/ingest/intenttree_reopened_derivation.py`,
`intenttree_self_caught_derivation.py`, `backend/db/repositories/intent_tree_derivations.py`,
`backend/db/factory.py`, `backend/db/{sqlite,postgres}_migrations.py`, `backend/models.py`,
`backend/routers/agent.py`, and the new test file -- none of which touch those four tables' DDL. Left
untouched per the task's instruction not to weaken/fix unrelated failing tests; the two new tables
are independently confirmed parity-clean (`column_parity_diff` returns `{}` for both, verified
directly in a REPL, matching the v55 precedent).

Environment note: `backend/.venv` did not resolve inside this worktree (consistent with prior
milestones' notes above); ran the full suite via the absolute main-repo venv path
(`/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python`) per the task brief's
explicit instruction, not a disposable local venv.

VERIFICATION GAP, closed by the orchestrator rather than waved through. The executor could not run
`npx tsc --noEmit`, `npm run typecheck`, or `npx vitest run` -- all three returned "This command
requires approval" with no interactive approval channel in a `-p` session, and unlike the Python
legs there was no bash-level workaround for a harness-level approval gate. It said so explicitly
rather than reporting success. The orchestrator then ran them: typecheck shows 33 errors in the
worktree against 34 on `main` (so this milestone adds none; all remaining errors are pre-existing,
in `docs/project_plans/designs/**` and `lib/sessionTranscriptLive.ts`), and vitest shows 52 passed
across 6 files, of which `lib/__tests__/areWeWinning.test.ts` contributes 10. The three recharts
traps were also statically confirmed: no keyed `ResponsiveContainer` anywhere in
`components/Analytics/`, no `searchParams` write in the new tab, and `isAnimationActive={false}`
present on the shared `<Pie>`.

## M2 scheduler wiring + closed-vocabulary narrowing

(Recorded by the orchestrator; the delegated ICA leg was blocked from running its own verification
commands by a Bash approval gate and explicitly asked the orchestrator to run them rather than
claiming success. The orchestrator ran all of them — results below.)

The gap this closes: M2 part B implemented and tested both derivations but did not register them
with the periodic scheduler. They existed, passed their tests, and would never have executed. In a
real deployment the reopened trendline and the self-caught ratio would have stayed permanently
empty while the UI rendered a clean "no data" state — the failure looks like a working feature with
nothing to show, which is the hardest kind to notice.

Ordering choice: the derivation sweep runs as its OWN task on its own interval
(`CCDASH_INTENTTREE_DERIVE_INTERVAL_SECONDS`), rather than sequenced inside the ingestion tick.
Both derivation services already treat an empty or partial `intent_tree_events` cache as a normal
zero-work pass (an empty candidate set means the loop never runs and the sweep reports ok with zero
processed), so a derivation tick racing ahead of — or between — ingestion ticks is harmless.
Decoupling means a stalled ingestion sweep never blocks derivation and vice versa. Gating,
circular-import discipline (TYPE_CHECKING at module scope, real import deferred into the
`_construct_*` function) and worker-profile-only start all mirror M1's ingestion job verbatim.

Closed-vocabulary narrowing: `are_we_winning.py` previously passed a plain `str` from the database
into a parameter typed `Literal["self_caught", "other_caught", "unknown"]`. Fixed with a real
narrowing function (`_narrow_self_caught_bucket`) rather than a `# type: ignore` — a suppression
there would have silenced the one check that makes the vocabulary actually closed. An unrecognized
stored token now maps to `unknown`; it never raises and never passes through. Pinned by
`SelfCaughtClosedVocabularyNarrowingTests`, which inserts an unrecognized bucket token and asserts
it surfaces as `unknown` with exactly three buckets in the result.

Verification (run by the orchestrator with the real main-repo venv):
- `backend.runtime.container` exposes `IntentTreeDerivationJob` and
  `_construct_intenttree_derivation_job` alongside M1's ingestion pair.
- `runtime.py` starts the periodic task in the run path (`_start_intenttree_derivation_task`), so
  it is genuinely scheduled and not merely constructible.
- `test_intenttree_derivation_job.py` → 9 passed.
- `test_are_we_winning_derivations.py` + `test_are_we_winning_rollups.py` +
  `test_intenttree_events_ingest.py` → 48 passed.

`backend/tests/test_runtime_bootstrap.py` was deliberately NOT used to verify this: it hangs on
import in this repo. The job-wrapper test file above exists specifically so this wiring has
verification that does not depend on a hanging suite.

## Runtime browser smoke — runtime_smoke: passed (2026-08-15, orchestrator)

Performed by the orchestrator, not delegated: the plan's `routing_constraints` state that frontend
chart wiring is offload-eligible but "the runtime browser smoke verification itself is not — it must
be performed and its evidence recorded, never skipped in favor of a unit-test pass."

**Data was real, not fixtures.** The local SQLite cache was populated by the feature's own ingestion
job, constructed through the container's real `_construct_intenttree_events_ingest_job("worker", db)`
gate, against the live IntentTree API:

- `intent_tree_events`: **4,005** `node.created` + **750** `node.completed` (schema v56).
  Slightly above the worknote's measured 3,941 / 745 because more events exist now — including the
  finding nodes filed during this run, which is a pleasing self-consistency check.
- `intent_tree_reopened_events`: **33** rows derived by walking only the ever-completed candidate set.
- `intent_tree_self_caught_buckets`: **4,005 `unknown`, and nothing else** — the predicted honest
  outcome, reached without any bucket being inferred or redistributed.

**Stack**: `npm run dev` (local profile), backend `/api/health` ok, frontend 200,
`GET /api/agent/are-we-winning/summary` 200 with real ISO-week series.

### The three recharts traps — all clean

1. **Pie blank-flash**: the ratio pie was fully painted in the first screenshot after both a
   tab-click entry and a direct-URL load. `isAnimationActive={false}` is present on the shared
   `<Pie>` in `primitives/InteractiveChartCard.tsx` — inherited by extending the existing primitive
   rather than parallel-building, which is exactly why "extend, don't parallel-build" was a
   requirement and not a style note.
2. **`ResponsiveContainer` key-loop**: no keyed `ResponsiveContainer` anywhere in
   `components/Analytics/`. No page blanking across two loads, a drill-through open/close, and a
   10-second idle. No "Maximum update depth exceeded" in console. Console output was 100%
   recharts `width(-1)/height(-1)` sizing warnings, which are pre-existing in this repo (they also
   appear in the existing `AnalyticsDashboardResearchResilience` vitest run) and did not accumulate
   during the idle — the discriminator between a noisy render and an actual loop.
3. **`searchParams` write-on-render**: opening the drill-through modal did **not** change the URL
   (it stayed `#/analytics?tab=are_we_winning`). The navigation write happens in the click handler
   only, per plan decision OQ-4.

### Drill-through — real, with count parity

Clicking the Nodes Created point for ISO week 33 opened a modal headed
"Nodes Created — week of 2026-08-10 / ISO week 33, 2026 / **1013 row(s) total**", listing real
IntentTree node rows (title, node id, occurred-at). The tooltip on the same point read
"Nodes Created : 1,013". Modal row count == trendline count — the plan's "not a decorative click
target" rubric item, verified rather than asserted.

### The unknown bucket

Rendered as a first-class legend entry, not a footnote:
`Self-caught 0 (0.0%)` · `Other-caught 0 (0.0%)` · `Unknown 4,005 (100.0%)`, above the caption
"`Unknown` is expected to dominate today — most nodes carry no attribution discriminator — and is
never folded into the other buckets."

The widget also carries an honest footnote that per-bucket drill-through is not yet available,
naming the contract reason. That is the correct posture for a known gap — it declares itself rather
than shipping a dead click target — and the gap is tracked in IntentTree as
`node_01M01R99RTVZFGJT1708VT057M`.

### Environment note

`npm run dev` initially failed with `ModuleNotFoundError: No module named 'ccdash_contracts'`: a
delegated leg had created a disposable `backend/.venv` INSIDE the worktree (gitignored, so invisible
to `git status`), and the dev script picked it up over the main-repo venv. Replaced with a symlink
to the main repo's venv, which is the project's documented convention anyway. Worth knowing: a
delegated executor working around a sandboxed path can leave behind an environment that silently
shadows the real one.

## M2/M3 gate fixes (reviewer gate -> CHANGES_REQUESTED, then re-passed)

The M2/M3 gate (Codex gpt-5.6-terra, read-only, adversarial) returned CHANGES_REQUESTED with three
defects plus one stale-disclosure observation. All four addressed; backend suites 48 -> 63 tests,
frontend 52 -> 59.

**1. A disposal was being reported as a regression.** The reopened derivation constrained the
transition's SOURCE (must have been `completed`) but not its DESTINATION, so `completed -> archived`
and `completed -> deferred` counted as reopens. Archiving or deferring a finished node is disposal,
not "completed work regressed" -- it inflates the regression trendline with routine cleanup, and
nothing about the output looks wrong. This is exactly the silently-plausible boundary error the
plan's routing_constraints reserved to the primary lane.

Fixed by constraining BOTH ends: a reopen is now `old_status in TERMINAL_STATUSES and new_status in
ACTIVE_DESTINATION_STATUSES`. `ACTIVE_DESTINATION_STATUSES` is an explicit **allow-list** (not a
deny-list) so a status added upstream later defaults to "not a reopen" rather than silently becoming
one. The set was ground-truthed against the live IntentTree `NodeStatus` enum, not guessed.

Worth recording the reasoning for `archived` specifically, because it is the non-obvious half:
`archived` is ambiguous -- it can mean "done and put away" OR "abandoned without ever finishing",
since a cancelled node can also be archived. Treating it as terminal would produce a false-positive
reopen when a *cancelled* node is later un-archived and resumed, which is not completed work
regressing. Covered by persisted-state tests (not just constant-pinning): `completed -> in_progress`
counts; `completed -> archived` and `completed -> deferred` do not; a never-completed node is still
never examined.

**2. Summary and drill-through could disagree about the same population.** The drill-through path
compared and emitted stored bucket values without narrowing them through
`_narrow_self_caught_bucket()`, so an unrecognized stored token was counted as `unknown` in the
summary while being absent from the `unknown` drill-through -- two surfaces disagreeing, which is
the "never silently divide" property this feature exists to protect. Now narrowed on both the
comparison and the emitted field, with a test asserting the drill-through `unknown` total equals the
summary `unknown` count.

**3. A swallowed error reported success.** Both derivation services' `_cursor_advance` caught every
`Exception`, after which `derive_all()` still returned `ok=True`. Unlike `rf_events_ingest.py`'s
cursor bookkeeping -- genuinely secondary telemetry -- this watermark is load-bearing:
`AreWeWinningQueryService._derivation_has_ever_run` gates whether `reopened` and
`self_caught_ratio` are exposed at all. `_cursor_advance` now returns a bool and `derive_all()`
returns `ok=False` with an explanatory error when the watermark write fails. Same principle as M1's
ingestion fix: fail-soft means "the remote is unavailable", never "our code is wrong".

**4. The gap disclosure stated a false reason.** The ratio panel told the user per-bucket
drill-through was unavailable because the backend "reports only a bucket + count, with no underlying
-row coordinates". That went stale when `get_self_caught_drill_through` shipped. Corrected to state
what is true -- the endpoint exists, the UI does not call it yet -- without wiring it (deferred,
tracked as `node_01M01R99RTVZFGJT1708VT057M`). A disclosure that misstates its own reason is worse
than none: it sends the next reader to fix the wrong layer.

Verification: the delegated leg could not reach the absolute main-repo venv path (sandbox boundary)
and could not run vitest at all (Bash approval wall); it said so rather than claiming a pass. The
orchestrator ran both: 63 backend tests pass across the four named files, 59 frontend tests across 7
files.
