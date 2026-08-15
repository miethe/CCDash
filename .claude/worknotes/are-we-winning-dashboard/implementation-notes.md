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
