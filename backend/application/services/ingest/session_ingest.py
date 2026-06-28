"""Single-event ingest service for the remote NDJSON session ingest endpoint.

Processes one IngestSessionEvent at a time; the router drives the batch loop.
Deduplication is performed in two stages:
  1. In-memory LRU keyed by (workspace_id, event_id) — zero DB round-trip on
     replay within the same process lifetime.
  2. On LRU miss, a targeted SELECT confirms whether the source_ref is already
     present in the sessions table before issuing an upsert.

Cursor advancement via IngestCursorRepository.advance() happens *after* a
successful upsert so the watermark only moves on confirmed writes (ADR-009).
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from backend.application.models.ingest import IngestSessionEvent
from backend.db.repositories.sessions import SqliteSessionRepository, compute_source_ref
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository

logger = logging.getLogger("ccdash.ingest")

# ── Batch-level limits (enforced by the router; exported for tests) ──────────

MAX_EVENTS_PER_BATCH: int = 500
MAX_BATCH_BYTES: int = 16 * 1024 * 1024  # 16 MiB


# ── Exceptions ───────────────────────────────────────────────────────────────


class IngestProcessingError(Exception):
    """Raised when a single event cannot be upserted.

    The router catches this, appends a RejectedEvent, and continues.
    """

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


# ── Service ───────────────────────────────────────────────────────────────────


class RemoteSessionIngestService:
    """Process a single IngestSessionEvent: dedup → upsert → cursor-advance.

    Instantiate once per application process (process-wide LRU).
    The router creates one instance via the RuntimeContainer singleton so the
    LRU is shared across all requests in the same worker.

    Parameters
    ----------
    session_repo:
        SqliteSessionRepository (or compatible duck-typed variant) with
        ``upsert(payload, project_id, *, source_ref)`` and a ``db`` attribute
        supporting ``db.execute()``.
    cursor_repo:
        SqliteIngestCursorRepository with ``get_or_create``, ``advance``,
        and ``record_error`` methods.
    lru_size:
        Maximum number of (workspace_id, event_id) pairs to keep in the
        in-memory dedup cache before evicting the oldest entry.
    """

    def __init__(
        self,
        session_repo: Any,
        cursor_repo: Any,
        *,
        lru_size: int = 8192,
    ) -> None:
        self._session_repo = session_repo
        self._cursor_repo = cursor_repo
        self._lru: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._lru_size = lru_size

    # ── Public ───────────────────────────────────────────────────────────────

    async def process(
        self,
        event: IngestSessionEvent,
        *,
        project_id: str,
        workspace_id: str,
    ) -> tuple[bool, str | None]:
        """Process one event.

        Returns
        -------
        (was_new_upsert, source_ref)
            ``was_new_upsert`` is False when the event was a duplicate (LRU or
            DB hit); True when an upsert was issued.  ``source_ref`` is always
            set to the canonical value for the event.
        """
        # 1. Compute canonical source_ref.
        source_ref = compute_source_ref(
            source_id="remote_ingest",
            event_id=event.event_id,
        )

        # 2. Ensure the cursor row exists for this (source, project, workspace).
        await self._cursor_repo.get_or_create(
            source_id="remote_ingest",
            project_id=project_id,
            workspace_id=workspace_id,
        )

        lru_key = (workspace_id, event.event_id)

        # 3. LRU dedup check — zero DB round-trip on cache hit.
        if lru_key in self._lru:
            self._lru.move_to_end(lru_key)
            logger.debug("ingest dedup (lru): event_id=%s workspace=%s", event.event_id, workspace_id)
            return False, source_ref

        # 4. DB existence check — covers replays after a process restart.
        exists = await self._source_ref_exists(source_ref)
        if exists:
            self._lru_put(lru_key, source_ref)
            logger.debug("ingest dedup (db): event_id=%s workspace=%s", event.event_id, workspace_id)
            return False, source_ref

        # 5. Upsert + cursor advance.
        try:
            await self._session_repo.upsert(
                event.payload,
                project_id,
                workspace_id=workspace_id,
                source_ref=source_ref,
            )
            await self._cursor_repo.advance(
                source_id="remote_ingest",
                project_id=project_id,
                workspace_id=workspace_id,
                cursor_value=event.event_id,
                occurred_at=event.occurred_at,
            )
        except Exception as exc:
            try:
                await self._cursor_repo.record_error(
                    source_id="remote_ingest",
                    project_id=project_id,
                    workspace_id=workspace_id,
                    error_message=str(exc),
                )
            except Exception:
                logger.warning("ingest: failed to record error for event_id=%s", event.event_id)
            raise IngestProcessingError(
                reason=str(exc),
                code="upsert_failed",
            ) from exc

        # 6. Populate LRU after successful write.
        self._lru_put(lru_key, source_ref)
        return True, source_ref

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _source_ref_exists(self, source_ref: str) -> bool:
        """Return True if a sessions row with this source_ref already exists."""
        db = self._session_repo.db
        async with db.execute(
            "SELECT 1 FROM sessions WHERE source_ref = ? LIMIT 1",
            (source_ref,),
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    def _lru_put(self, key: tuple[str, str], value: str) -> None:
        """Insert/refresh a key in the LRU; evict the oldest entry if full."""
        if key in self._lru:
            self._lru.move_to_end(key)
        else:
            if len(self._lru) >= self._lru_size:
                self._lru.popitem(last=False)  # evict LRU (oldest)
            self._lru[key] = value
