---
schema_version: 2
doc_type: progress
type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 2
phase_title: Sync Engine Port Abstraction
status: completed
created: '2026-05-12'
updated: '2026-05-12'
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
adr_refs:
- docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
- docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md
- docs/project_plans/adrs/adr-006-remote-session-ingest-transport-ndjson-http.md
commit_refs:
- 79fca4b
- ef419d0
- e5da1dd
- c52a38c
pr_refs: []
owners:
- python-backend-engineer
- data-layer-expert
contributors: []
execution_model: batch-parallel
overall_progress: 0
completion_estimate: on-track
total_tasks: 8
completed_tasks: 8
in_progress_tasks: 0
blocked_tasks: 0
tasks:
- id: T2-001
  description: Define IngestEvent, IngestCursor dataclasses + SessionIngestSource
    Protocol in backend/application/ports/ingest.py. Mirror ADR-009 §Decision shape.
    Add to backend/application/ports/__init__.py exports.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies: []
  evidence:
  - test: backend/tests/test_ingest_port.py
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  verified_by:
  - T2-008
- id: T2-002
  description: Add ingest_cursors table + sessions.source_ref column via SCHEMA_VERSION
    bump. Update both backend/db/sqlite_migrations.py and backend/db/postgres_migrations.py.
    Backfill source_ref from source_file for existing fs rows (UPDATE sessions SET
    source_ref='fs:'||source_file WHERE source_ref IS NULL AND source_file IS NOT
    NULL). Add non-unique index on (project_id, source_ref). No unique constraint
    until Phase 4 introduces workspace_id.
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies: []
  evidence:
  - v28 migration implemented: source_ref column + backfill + ix_sessions_source_ref
      index + ingest_cursors table on both SQLite and Postgres. 8/8 new tests pass.
      10/10 sync regression tests pass.
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  verified_by:
  - T2-008
- id: T2-003
  description: 'Create IngestCursorRepository protocol in backend/db/repositories/base.py
    and concrete SQLite + Postgres implementations in backend/db/repositories/ingest_cursors.py.
    Methods: get_or_create(source_id, project_id, workspace_id) -> IngestCursor; advance(source_id,
    project_id, workspace_id, cursor_value, occurred_at) -> None; record_error(source_id,
    project_id, workspace_id, error_message) -> None. Plus repository unit tests.'
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  dependencies:
  - T2-001
  - T2-002
  evidence:
  - test: backend/tests/test_ingest_cursor_repository.py
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  verified_by:
  - T2-008
- id: T2-004
  description: Add source_ref helper + write path in sessions repository (backend/db/repositories/sessions.py).
    When upserting from an IngestEvent path, populate source_ref. Do NOT change existing
    ON CONFLICT(id) clause. Existing callers continue to set only source_file. Add
    helper compute_source_ref(source_id, payload) for the FilesystemSource path.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T2-002
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  evidence:
  - test: backend/tests/test_sessions_source_ref.py
  verified_by:
  - T2-008
- id: T2-005
  description: 'Implement FilesystemSource in backend/db/ingest/filesystem_source.py.
    Wraps existing parser logic (backend/parsers/sessions.py): scans sessions_dir,
    parses JSONL, yields IngestEvent with source_ref=''fs:<canonical-rel-path>'',
    schema_version=''1.0'', cursor_value=mtime ISO timestamp. ack() updates ingest_cursors
    via IngestCursorRepository. Sources directory has __init__.py exporting FilesystemSource.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T2-001
  - T2-003
  - T2-004
  completed: '2026-05-12T01:45:00Z'
  evidence:
  - file: backend/db/ingest/filesystem_source.py
  started: '2026-05-12T00:00:00Z'
  verified_by:
  - T2-008
- id: T2-006
  description: 'Unit tests for FilesystemSource: stream() yields events for a fixture
    sessions dir; ack() advances cursor in ingest_cursors; second stream() with the
    advanced cursor yields zero events (idempotent re-scan). backend/tests/test_filesystem_source.py.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T2-005
  completed: '2026-05-12T01:45:00Z'
  evidence:
  - test: backend/tests/test_filesystem_source.py
  - test: backend/tests/test_filesystem_source.py
  - commit: c52a38c
  started: '2026-05-12T00:00:00Z'
  verified_by:
  - T2-008
- id: T2-007
  description: 'Stub RemoteIngestSource + tests proving the Protocol contract holds
    for a non-filesystem implementation: cursor advances after a simulated upsert;
    crash between yield and ack leaves cursor unchanged (idempotent re-ingest on retry).
    backend/tests/test_ingest_port.py. This satisfies ADR-009 §Hard Gates row 2.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T2-001
  - T2-003
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  evidence:
  - test: backend/tests/test_ingest_port.py::test_cursor_advances_after_upsert_via_repo
  verified_by:
  - T2-008
- id: T2-008
  description: 'Validation gate: run full backend test suite (backend/.venv/bin/python
    -m pytest backend/tests/ -v) and confirm: (a) zero existing tests modified, (b)
    zero new failures in existing tests, (c) new tests from T2-003/T2-006/T2-007 pass.
    Append evidence to this progress file.'
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  dependencies:
  - T2-003
  - T2-004
  - T2-005
  - T2-006
  - T2-007
  evidence:
  - test: 65/65 passed (ingest_port + migrations_v28 + ingest_cursor_repository +
      sessions_source_ref + filesystem_source + sync_engine_jsonl_persistence_regressions
      + sync_light_mode)
  - log: /tmp/ccdash-phase2-importlib.log
  - note: --import-mode=importlib required to bypass pre-existing env segfault in
      default assertion-rewrite mode; verified on parent commit 29633f7
  started: '2026-05-12T00:00:00Z'
  completed: '2026-05-12T01:45:00Z'
  verified_by:
  - T2-008
parallelization:
  batch_1:
  - T2-001
  - T2-002
  batch_2:
  - T2-003
  - T2-004
  batch_3:
  - T2-005
  - T2-007
  batch_4:
  - T2-006
  batch_5:
  - T2-008
blockers: []
success_criteria:
- SessionIngestSource Protocol committed in backend/application/ports/ingest.py
- ingest_cursors table present in SQLite + Postgres migrations; backfilled source_ref
  column on sessions
- IngestCursorRepository (Protocol + SQLite + Postgres impls) shipped with unit tests
- FilesystemSource implements SessionIngestSource end-to-end; cursor advancement verified
- Stub RemoteIngestSource proves port contract works for non-filesystem implementations
- Zero existing backend tests modified or failing (ADR-009 hard gate)
- Cursor advance is idempotent under retry (ADR-009 §Hard Gates row 5)
notes: 'Phase 2 scope is intentionally tighter than ADR-009''s full vision. The 6K-line
  SyncEngine internal consumer-refactor (engine consumes list[SessionIngestSource])
  is deferred to Phase 3 when a real second source (RemoteIngestSource via the daemon)
  lands. Phase 2 ships the port, the cursor table, and a working FilesystemSource
  implementation so Phase 3 has a concrete second-source implementation to plug in.

  workspace_id is a literal "default" string until Phase 4 introduces ADR-008 workspace-scoped
  auth. The wider unique key (project_id, workspace_id, source_ref) is also deferred
  to Phase 4 to avoid forcing two schema breaks in v1.

  '
progress: 100
---

# remote-ccdash-streaming — Phase 2: Sync Engine Port Abstraction

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

Update task status via CLI:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/remote-ccdash-streaming/phase-2-progress.md \
  -t T2-001 -s in_progress
```

---

## Objective

Land the `SessionIngestSource` Protocol, `ingest_cursors` watermark table, and a
`FilesystemSource` wrapper so Phase 3 (daemon) and Phase 5 (Entire) have a stable
contract to implement against. Hard gate: zero existing test changes.

---

## Batch Plan

| Batch | Tasks | Owner agents | Parallel? |
|-------|-------|--------------|-----------|
| 1 | T2-001, T2-002 | python-backend-engineer, data-layer-expert | yes (different files) |
| 2 | T2-003, T2-004 | data-layer-expert, python-backend-engineer | yes (different files) |
| 3 | T2-005, T2-007 | python-backend-engineer | yes (different files) |
| 4 | T2-006 | python-backend-engineer | sequential after T2-005 |
| 5 | T2-008 | task-completion-validator | gate |

Each batch ends with a commit. Sequential commits, not a single monolithic commit,
to keep migration + port + source changes independently revertible.
