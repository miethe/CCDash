"""Transport-neutral session ingest port: event, cursor, and source Protocol."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class IngestEvent:
    """A single parsed session event produced by a SessionIngestSource."""

    source_ref: str       # 'fs:<rel-path>' | 'remote:<workspace>:<event-id>' | 'entire:<checkpoint-hex>'
    project_id: str
    workspace_id: str     # per ADR-008
    payload: dict         # parsed session JSON
    schema_version: str   # forward-compat per ADR-006
    cursor_value: str     # opaque, monotonic per (source_id, project_id)
    occurred_at: str      # ISO-8601 from the event, not server clock


@dataclass(frozen=True)
class IngestCursor:
    """Watermark row tracking ingest progress for one (source, project, workspace) triplet."""

    source_id: str
    project_id: str
    workspace_id: str
    last_cursor: str | None
    last_ingest_at: str | None
    error_count: int
    last_error: str | None = None
    last_error_at: str | None = None


@runtime_checkable
class SessionIngestSource(Protocol):
    """Structural protocol for any session ingest source (filesystem, remote, Entire)."""

    source_id: str

    async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:
        """Yield events that arrived after the given cursor position."""
        ...

    async def ack(self, event: IngestEvent) -> None:
        """Acknowledge successful upsert; implementations advance ingest_cursors."""
        ...
