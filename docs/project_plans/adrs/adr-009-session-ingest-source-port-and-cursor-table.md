---
title: "ADR-009: SessionIngestSource Port + ingest_cursors Watermark Table"
type: "adr"
status: "accepted"
created: "2026-05-10"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
tags: ["adr", "sync-engine", "port-adapter", "cursor", "ingest"]
---

# ADR-009: SessionIngestSource Port + ingest_cursors Watermark Table

## Status

Accepted (SPIKE-resolved 2026-05-10)

## Context

The current `SyncEngine` (`backend/db/sync_engine.py`) is filesystem-coupled at three layers:

1. **Path resolution** — `sync_engine.py:118-121` calls `infer_project_root()` and canonical-path transforms.
2. **Change detection** — `file_watcher.py:30` uses `watchfiles` (inotify/fsevents) and `_file_hash()` for incremental decisions.
3. **Identity** — sessions are keyed by canonical relative `source_file` (`backend/db/repositories/sessions.py:59`).

A remote ingest source has no analogue for any of these. To accept events from the daemon (ADR-014/007) and from Entire.io checkpoints (sister SPIKE) without forking the engine, the sync layer needs a transport-neutral abstraction.

The chosen abstraction must (a) preserve local-mode behavior bit-for-bit (zero existing-test changes — hard gate), (b) make remote ingest a parallel implementation, not a fork, and (c) provide resumable semantics for any source, not just filesystem.

## Decision

Introduce a `SessionIngestSource` Python `Protocol` and a new `ingest_cursors` table that becomes the **single source of sync truth** across all source types.

### The Port

```python
# backend/application/ports/ingest.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass(frozen=True)
class IngestEvent:
    source_ref: str             # 'fs:<rel-path>' | 'remote:<workspace>:<event-id>' | 'entire:<checkpoint-hex>'
    project_id: str
    workspace_id: str           # added per ADR-008
    payload: dict               # parsed session JSON
    schema_version: str         # for forward-compat (ADR-014)
    cursor_value: str           # source-specific opaque cursor; monotonic per (source_id, project_id)
    occurred_at: str            # ISO-8601 from the event itself, not server clock

@dataclass(frozen=True)
class IngestCursor:
    source_id: str              # 'filesystem' | 'remote_ingest' | 'entire'
    project_id: str
    workspace_id: str
    last_cursor: str | None
    last_ingest_at: str | None
    error_count: int

class SessionIngestSource(Protocol):
    source_id: str

    async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]: ...
    async def ack(self, event: IngestEvent) -> None: ...
    # ack updates ingest_cursors.last_cursor; called by SyncEngine after successful upsert.
    # Sources are free to no-op ack if they don't need it (e.g., FilesystemSource keeps using mtime
    # as its internal cursor and only writes to ingest_cursors for observability).
```

The `SyncEngine` is refactored to consume `SessionIngestSource` instead of filesystem paths directly:

```python
# backend/db/sync_engine.py (refactored)
class SyncEngine:
    def __init__(self, sources: list[SessionIngestSource], session_repo: SessionRepository, ...):
        self._sources = sources
        ...

    async def run(self) -> None:
        for source in self._sources:
            cursor = await self._cursor_repo.get_or_create(source.source_id, project_id, workspace_id)
            async for event in source.stream(since=cursor):
                await self._session_repo.upsert(self._materialize(event))
                await source.ack(event)
                await self._cursor_repo.advance(source.source_id, project_id, workspace_id, event.cursor_value)
```

### Implementations

| Implementation | source_id | Cursor semantics | When constructed |
|---|---|---|---|
| `FilesystemSource` | `filesystem` | mtime + content-hash (existing logic, wrapped) | `local` and `worker` runtime profiles when `storage_profile.filesystem_source_of_truth` is true |
| `RemoteIngestSource` | `remote_ingest` | UUID v7 `event_id` from the daemon; cursor advances on successful upsert | `api` and `worker` profiles when `CCDASH_REMOTE_INGEST_ENABLED=true` |
| `EntireCheckpointSource` | `entire` | git commit hash of `entire/checkpoints/v1` branch + checkpoint ID | sister SPIKE; deferred to Phase 5 |

### The `ingest_cursors` Table

```sql
CREATE TABLE ingest_cursors (
    source_id      TEXT NOT NULL,
    project_id     TEXT NOT NULL,
    workspace_id   TEXT NOT NULL,
    last_cursor    TEXT,
    last_ingest_at TEXT,
    error_count    INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    last_error_at  TEXT,
    PRIMARY KEY (source_id, project_id, workspace_id)
);

CREATE INDEX ix_ingest_cursors_workspace ON ingest_cursors (workspace_id);
```

The cursor advances on **successful repository upsert**, not on receipt. This keeps the contract simple: "cursor at value X means every event ≤ X is durably stored."

### Session Identity Unification

A `source_ref` column is added to `sessions`, with a URI scheme:

- `fs:<canonical-rel-path>` for filesystem sessions (backfilled from existing `source_file`)
- `remote:<workspace_id>:<event_id>` for daemon-streamed sessions
- `entire:<checkpoint-hex-id>` for Entire (deferred)

The ON CONFLICT upsert key in `repositories/sessions.py:17-82` becomes `(project_id, workspace_id, source_ref)`. The legacy `source_file` column is preserved for backwards compatibility and continues to be populated for filesystem sessions.

## Decision Drivers

1. **Zero-test-change requirement is the hard gate.** Local mode is the hottest path in production. Any test diff is a regression risk.
2. **Single source of sync truth.** Today the cursor is implicit (mtime in the filesystem). Making it explicit (`ingest_cursors`) for *all* sources — including filesystem — pays a one-time refactor cost and gains operability (cursor lag is now a queryable health signal, see ADR-014).
3. **Source identity is opaque to the engine.** The engine never asks "is this a filesystem path?"; it asks the source to stream events. This forecloses the failure mode where "remote events accidentally invoke filesystem path logic" (a real risk surfaced in the grounding brief).
4. **Forward-compat with Entire.** The Entire integration (sister SPIKE) is a third implementation of the same `Protocol`. The port shape was designed with three implementations in mind, not retrofitted to one.
5. **Cursor model handles backfill.** A daemon that has been offline for a week resumes from the last server-acked cursor automatically; the server has no "what did I last see from this daemon" mystery.

## Alternatives Considered

1. **Parallel ingest path alongside an unchanged `SyncEngine`.** Easier to ship; no refactor. Long-term: divergence between two pipelines, two sets of repository writes, two cursor models. Rejected because the maintenance cost compounds.
2. **Source-as-class-hierarchy** (abstract base class with shared default implementation). More OOP-flavored but the `Protocol` shape here is structural — a `FilesystemSource` need not inherit anything from a remote source. Rejected for being heavier than necessary.
3. **Single global cursor instead of per-(source, project, workspace) cursor.** Simpler. Breaks resumability when one source is healthy and another is failing. Rejected.
4. **Use the existing `source_file` as the upsert key, no `source_ref` column.** Zero schema change. Cannot represent non-filesystem sessions. Rejected.

## Hard Gates (from E4)

| Gate | Target |
|---|---|
| Existing sync-engine tests pass without modification | 100% — zero diff |
| At least one new unit test demonstrates cursor advancement on a stub `RemoteIngestSource` | Required |
| `FilesystemSource` produces identical DB state as the pre-refactor engine on a fixed corpus of session files | Byte-equal `sessions` rows for the test corpus |
| `ingest_cursors` rows match for an idempotent re-run | Same cursor values; row count unchanged |
| Cursor advances atomically with upsert (no advance-without-upsert path) | Verified by transaction-boundary test |

## Consequences

### Positive

- One pipeline serves all sources. No fork.
- Cursor lag is a first-class operational signal (`/api/health` extension in ADR-010 and Phase 7).
- The Entire integration (sister SPIKE) becomes a contained ~300-LOC implementation rather than a parallel sync engine.
- Daemon-offline scenarios are recovered automatically by the cursor model; no operator intervention.

### Negative

- Schema migration touches every existing project's DB. Requires a tested migration path on representative SQLite databases.
- The `source_ref` upsert key is a wider unique constraint than `source_file` alone; index size grows modestly.
- The abstraction adds one indirection per event in the hot path. Negligible cost (per-event work is dominated by JSON parse + DB upsert), validated in E4 micro-benchmark.

### Risks

| Risk | Mitigation |
|---|---|
| Cursor off-by-one silently loses sessions | Cursor advances **after** upsert in the same DB transaction; integration test forces a crash between upsert and advance and asserts re-ingest is idempotent |
| `FilesystemSource` parity regression | Hard gate: zero existing test changes; corpus-equality test added |
| Migration corrupts `source_file` for some edge case (Windows backslash paths, symlinks) | Run migration against a corpus of representative DBs in CI before any release |
| Two sources writing to the same project_id with overlapping events (filesystem + remote, transition period) | Dedup by `source_ref` upsert key; design-spec §4.6 covers dual-source policy explicitly; transition mode is opt-in via `CCDASH_DUAL_SOURCE_INGEST=true` |

## Related

- ADR-014 (transport — produces events for `RemoteIngestSource`)
- ADR-008 (auth — `AuthContext.workspace_id` populates `IngestEvent`)
- ADR-010 (multi-project routing — sources are per-(project, workspace))
- Sync engine today: `backend/db/sync_engine.py`, `backend/db/file_watcher.py`
- Session repo upsert: `backend/db/repositories/sessions.py:17-82`
- Sister SPIKE (Entire): `docs/project_plans/SPIKEs/entire-io-integration-charter.md`
