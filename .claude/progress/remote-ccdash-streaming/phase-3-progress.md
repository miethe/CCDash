---
schema_version: 2
doc_type: progress
type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 3
phase_title: Ingest Endpoint + Local Daemon
status: completed
created: '2026-05-19'
updated: '2026-05-19'
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
adr_refs:
- docs/project_plans/adrs/adr-006-remote-session-ingest-transport-ndjson-http.md
- docs/project_plans/adrs/adr-007-local-daemon-packaging-as-ccdash-cli-subcommand.md
- docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
spike_ref: docs/project_plans/spikes/remote-ccdash-streaming.md
commit_refs: []
pr_refs: []
owners:
- python-backend-engineer
- backend-architect
contributors: []
execution_model: batch-parallel
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
runtime_smoke: skipped
runtime_smoke_reason: Backend-only phase; no frontend changes. Smoke gate satisfied
  via FastAPI TestClient contract tests in T3-006.
tasks:
- id: T3-001
  description: Define Pydantic request/response models for the ingest endpoint in
    backend/application/models/ingest.py. IngestSessionEvent (event_id UUID, batch_id
    UUID, schema_version str, occurred_at ISO, source_ref optional, payload dict),
    IngestBatchResponse (accepted int, rejected list[RejectedEvent], dead_lettered
    list[RejectedEvent], cursor_advanced_to str | None), RejectedEvent (event_id,
    reason, code). model_config extra="allow" on IngestSessionEvent for forward-compat
    (warn-and-strip unknown fields per ADR-006 F-6). Add to __init__.py exports.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies: []
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - file: backend/application/models/ingest.py
  verified_by:
  - T3-007
- id: T3-002
  description: 'Implement ingest service in backend/application/services/ingest/session_ingest.py
    that processes a single IngestSessionEvent: (1) build source_ref via compute_source_ref(source_id="remote_ingest",
    event_id=event.event_id); (2) check dedup against an in-memory LRU (size 8192,
    keyed by (workspace_id, event_id)) before any DB read; (3) on LRU miss, query
    sessions where source_ref=? to confirm the dedup decision; (4) upsert via SqliteSessionRepository.upsert(payload,
    project_id, source_ref=source_ref); (5) advance the ingest_cursors row via IngestCursorRepository.advance(source_id="remote_ingest",
    project_id=project_id, workspace_id=workspace_id, cursor_value=event_id, occurred_at=event.occurred_at).
    Service is async, single-event scope; the router batches calls. Constants for
    batch limits and LRU size live next to the service.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T3-001
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - file: backend/application/services/ingest/session_ingest.py
  verified_by:
  - T3-007
- id: T3-003
  description: 'Implement POST /api/v1/ingest/sessions in a new backend/routers/ingest.py
    using FastAPI Request.stream() for chunked NDJSON parse. Apply existing bearer
    auth via the standard request-scoped dependency (mirror backend/routers/client_v1.py).
    Resolve project_id from x-ccdash-project-id header (workspace_id defaults to "default"
    per Phase 2). Stream lines (rstrip("\n"), skip blanks), parse each as IngestSessionEvent;
    on validation error append RejectedEvent(reason="validation_error", code="invalid_event")
    and continue. Enforce max-events-per-batch=500: count lines as they arrive and
    if exceeded, abort with 413 and IngestBatchResponse {accepted: counter_at_limit,
    rejected:[], dead_lettered:[{reason:"batch_limit_exceeded"}]}. For each parsed
    event, call session_ingest.process(event); aggregate accepted/rejected. Schema_version
    forward-compat: any unknown top-level fields on the event are stripped silently
    (extra="allow" on the Pydantic model already does this). Response: 200 when no
    rejections, 207-equivalent 200 with non-empty rejected when partial, 413 when
    batch_limit_exceeded, 401 when auth fails. Wire into backend/runtime/bootstrap.py
    via app.include_router(ingest_router).'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T3-001
  - T3-002
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - file: backend/routers/ingest.py
  - test: backend/tests/test_ingest_endpoint.py
  verified_by:
  - T3-007
- id: T3-004
  description: Add ccdash daemon Typer subcommand to packages/ccdash_cli. Create packages/ccdash_cli/src/ccdash_cli/commands/daemon.py
    exposing daemon_app with sub-commands start, status, install, uninstall. start
    runs the daemon loop in foreground (the user/supervisor backgrounds it). install/uninstall
    print a config + supervisor unit template to stdout for v1 (do NOT auto-write
    system files — keep operationally honest; ADR-007 full supervisor wiring is Phase
    7 hardening). status prints local buffer depth + last_batch_at + last_error from
    the daemon state file. Register daemon_app on the root Typer app in main.py. Add
    CLI integration tests under packages/ccdash_cli/tests/test_daemon_command.py using
    CliRunner for status/install help text.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies: []
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - file: packages/ccdash_cli/src/ccdash_cli/commands/daemon.py
  - test: packages/ccdash_cli/tests/test_daemon_command.py
  verified_by:
  - T3-007
- id: T3-005
  description: 'Implement daemon core in packages/ccdash_cli/src/ccdash_cli/daemon/runner.py
    (and submodules): (1) Config loader from ~/.config/ccdash/daemon.toml with env
    var overrides CCDASH_DAEMON_SERVER_URL, CCDASH_DAEMON_TOKEN, CCDASH_DAEMON_PROJECT_ID,
    CCDASH_DAEMON_SESSIONS_DIR. (2) WAL buffer in ~/.local/state/ccdash/buffer/ using
    append-only NDJSON files (rotate at 500 lines or 5MB) with append-then-fsync semantics
    before any POST; ack-on-success deletes the segment. (3) Tail loop using watchfiles
    on sessions_dir if available, falling back to a 1s mtime poll when watchfiles
    import fails. (4) Event builder: for each new/changed JSONL file, parse with backend.parsers.sessions.parse_session_file
    (yes, imported from the backend package — daemon ships alongside ccdash_cli but
    relies on the same parser; record this dependency in the daemon README), generate
    UUID7 event_id, build IngestSessionEvent payload. (5) Batcher: collect up to 100
    events or 5s of accumulation, whichever comes first; serialize NDJSON; POST via
    httpx.AsyncClient with Bearer token + x-ccdash-project-id header. (6) Retry/backoff:
    exponential 100ms→200ms→400ms→…→max 60s, capped at 10 attempts per batch (mirrors
    SAMTelemetryClient pattern). On 429 honor Retry-After; on 5xx keep the WAL segment
    and back off; on 207-partial advance only the accepted events; rejected events
    move to ~/.local/state/ccdash/deadletter/. (7) Status file at ~/.local/state/ccdash/daemon.status
    written every batch (JSON: last_batch_at, accepted_total, rejected_total, buffer_depth,
    last_error). Daemon entrypoint async run() consumed by commands/daemon.py start.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T3-001
  - T3-004
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - file: packages/ccdash_cli/src/ccdash_cli/daemon/runner.py
  - test: packages/ccdash_cli/tests/test_daemon_retry.py
  verified_by:
  - T3-007
- id: T3-006
  description: 'Backend tests in backend/tests/test_ingest_endpoint.py using TestClient
    pattern from backend/tests/test_client_v1_contract.py (tempfile SQLite + build_runtime_app("test")):
    (a) happy path — 3-event NDJSON batch → 200 with accepted=3; (b) dedup — same
    event_id replayed → second call returns accepted=1, with the second event not
    creating a duplicate session row (assert via direct SQL count); (c) partial failure
    — mix valid + invalid event → 200 envelope with accepted + rejected populated;
    (d) batch limit — 501 events → 413 with reason "batch_limit_exceeded"; (e) schema_version
    forward-compat — event carries unknown_top_level_field, endpoint still accepts
    (extra="allow"); (f) auth — missing/invalid Bearer → 401; (g) cursor — verify
    ingest_cursors row advances to last accepted event_id. Daemon tests in packages/ccdash_cli/tests/test_daemon_wal.py
    + test_daemon_retry.py: WAL durability (write, kill, re-read), retry on 503 (use
    httpx MockTransport), UUID7 monotonicity, dead-letter pathway on 4xx. Aim for
    pure-unit isolation — no real HTTP server.'
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - T3-002
  - T3-003
  - T3-005
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - test: 65 backend + 164 cli passing
  - test: backend/tests/test_ingest_endpoint.py
  - test: packages/ccdash_cli/tests/test_daemon_wal.py
  verified_by:
  - T3-007
- id: T3-007
  description: 'Validation gate: run backend/.venv/bin/python -m pytest backend/tests/test_ingest_endpoint.py
    backend/tests/test_ingest_port.py backend/tests/test_filesystem_source.py backend/tests/test_ingest_cursor_repository.py
    -v plus python -m pytest packages/ccdash_cli/tests/ -v. Confirm: (a) all new tests
    pass; (b) zero pre-existing tests modified or broken; (c) no Pydantic model warnings
    from extra="allow". Update this progress file with task evidence and the final
    commit SHA. Author a concise §Phase Notes section at the end documenting deferred
    items (supervisor unit auto-install, /api/v1/ingest/cursor/{workspace} GET for
    daemon status, /api/health.ingest_sources block — all owned by Phase 6/7).'
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  dependencies:
  - T3-006
  started: '2026-05-19T20:30:00Z'
  completed: '2026-05-19T21:45:00Z'
  evidence:
  - log: backend 65/65, cli 164/164
  - note: --import-mode=importlib required per Phase 2 convention
  verified_by:
  - T3-007
parallelization:
  batch_1:
  - T3-001
  - T3-004
  batch_2:
  - T3-002
  - T3-005
  batch_3:
  - T3-003
  batch_4:
  - T3-006
  batch_5:
  - T3-007
blockers: []
success_criteria:
- POST /api/v1/ingest/sessions accepts chunked NDJSON, dedupes by (workspace_id, event_id),
  returns 200/207-style envelope on partial failure, 413 over batch cap, 401 on auth
  failure
- Sessions upserted from remote ingest carry source_ref="remote:<event_id>"; ingest_cursors
  advances per workspace
- ccdash daemon start tails JSONL, batches NDJSON, POSTs with retry/backoff (mirrors
  SAMTelemetryClient 10-retry pattern), buffers to on-disk WAL, generates UUID7 event_ids,
  honors 429 Retry-After, dead-letters 4xx events
- Backend and daemon tests cover happy path, dedup idempotency, partial failure, batch
  cap, schema_version forward-compat, auth, WAL durability, retry on 503, dead-letter
  on 4xx
- Zero pre-existing tests modified; ADR-009 hard gate preserved
deferred_items:
- 'OS-native supervisor auto-install (launchd plist / systemd --user unit / Task Scheduler
  task): print templates only in v1; auto-install moves to Phase 7 hardening.'
- 'GET /api/v1/ingest/cursor/{workspace} for daemon status query: deferred; status
  reads local daemon.status file only in v1.'
- '/api/health.ingest_sources block + frontend daemon health badge: Phase 6/7.'
- 'Cross-process dedup persistence (Redis or DB-backed LRU): in-memory LRU is sufficient
  for single-worker v1; revisit when horizontal scaling lands.'
notes: 'Phase 3 scope is intentionally narrower than ADR-006/007 max vision. We ship
  the endpoint and a working daemon that operators can launch from a terminal or hand-rolled
  supervisor unit; auto-install of OS supervisors is Phase 7. workspace_id is the
  literal "default" string until Phase 4 introduces ADR-008 workspace-scoped auth.
  RemoteIngestSource as a Phase-2-style port implementation is intentionally NOT shipped
  here — the ingest router talks to sessions + ingest_cursors repositories directly,
  matching the actual production data path. The Phase-2 stub RemoteIngestSource (test_ingest_port.py)
  already proves the Protocol contract works for a non-filesystem implementation.

  The SyncEngine refactor to consume list[SessionIngestSource] referenced in Phase
  2 notes remains deferred — the daemon writes through the endpoint, the endpoint
  writes through the sessions repository, no SyncEngine fan-in is needed until Phase
  5 brings the Entire source online and we want a single engine loop driving multiple
  sources.

  '
progress: 100
---

# remote-ccdash-streaming — Phase 3: Ingest Endpoint + Local Daemon

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

Update task status via CLI:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/remote-ccdash-streaming/phase-3-progress.md \
  -t T3-001 -s in_progress
```

---

## Objective

Land the inbound NDJSON ingest endpoint (`POST /api/v1/ingest/sessions`) plus a
working local daemon (`ccdash daemon`) so a remote CCDash deployment can accept
session events from developer workstations. Idempotency is enforced via
`(workspace_id, event_id)` dedup; the daemon survives restarts via on-disk WAL.

---

## Batch Plan

| Batch | Tasks | Owner agents | Parallel? |
|-------|-------|--------------|-----------|
| 1 | T3-001, T3-004 | python-backend-engineer | yes (different packages) |
| 2 | T3-002, T3-005 | python-backend-engineer | yes (different packages) |
| 3 | T3-003 | python-backend-engineer | sequential (depends on T3-001+T3-002) |
| 4 | T3-006 | python-backend-engineer | sequential after T3-005 |
| 5 | T3-007 | task-completion-validator | gate |

A single commit lands at the end of the phase (per user instruction).

---

## Phase Notes (evidence + deferrals)

### Validation evidence

Backend ingest + Phase 2 regression suite (`--import-mode=importlib`):

```
backend/tests/test_ingest_endpoint.py            ........... 10 passed
backend/tests/test_ingest_port.py                ........... 16 passed
backend/tests/test_filesystem_source.py          ........... 6 passed
backend/tests/test_ingest_cursor_repository.py   ........... 17 passed
backend/tests/test_sessions_source_ref.py        ........... 9 passed
backend/tests/test_migrations_v28.py             ........... 7 passed
Total: 65 passed in 4.17s
```

Standalone CLI suite (with `PYTHONPATH=packages/ccdash_cli/src`):

```
packages/ccdash_cli/tests/                       ........... 164 passed in 1.25s
  ├── test_daemon_command.py                    ............ 16 new
  ├── test_daemon_wal.py                        ............ 13 new
  ├── test_daemon_retry.py                      ............  6 new
  └── test_daemon_uuid7.py                      ............  5 new
```

ADR-009 hard gate preserved: zero pre-existing tests modified or broken.

### Shipped surface

- `POST /api/v1/ingest/sessions` — chunked NDJSON; in-memory LRU dedup
  (`(workspace_id, event_id)`) backed by DB `source_ref` check; partial-failure
  envelope; 413 over 500-event batch cap; 415 on wrong Content-Type;
  `extra="allow"` on `IngestSessionEvent` for ADR-006 F-6 forward-compat.
- `ccdash daemon {start,status,install,uninstall}` — WAL-backed tail+batch+POST
  loop; UUID7 event ids with per-process monotonic sequence; exponential
  backoff matching SAMTelemetryClient (up to 10 retries); 429 Retry-After
  honoring; 413 batch-splitting; rejected events sidelined to disk
  dead-letter; status file written atomically each flush.
- `RemoteSessionIngestService` (in `backend/application/services/ingest/`) is
  the production data path. The Phase-2 stub `RemoteIngestSource` in
  `backend/tests/test_ingest_port.py` continues to assert Protocol conformance
  without being wired into the runtime — exactly as planned.

### Deferred to later phases

- OS-native supervisor auto-install (launchd plist / systemd `--user` unit /
  Task Scheduler entry). Phase 3 prints templates only; Phase 7 hardening owns
  auto-install.
- `GET /api/v1/ingest/cursor/{workspace}` lookup for `ccdash daemon status`
  remote query; v1 status is local-only.
- `/api/health.ingest_sources` block + frontend daemon health badge — Phase
  6/7 deliverable.
- Cross-process dedup persistence (Redis or DB-backed LRU). In-memory LRU is
  correct for single-worker v1; horizontal scaling re-opens the choice.
- SyncEngine refactor to consume `list[SessionIngestSource]` fan-in. Daemon
  → endpoint → sessions repository is the direct path; the engine-level
  fan-in is unnecessary until Phase 5 brings `EntireCheckpointSource` online.

