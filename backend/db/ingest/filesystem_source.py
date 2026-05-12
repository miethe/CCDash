"""FilesystemSource — SessionIngestSource implementation backed by local JSONL files.

Wraps the existing session parsers (backend.parsers.sessions) behind the
transport-neutral SessionIngestSource Protocol defined in
backend.application.ports.ingest.  The SyncEngine refactor (Phase 3) will
wire this as the default source for `local` and `worker` runtime profiles.

Design: one IngestEvent per JSONL file.  The existing parse_session_file()
helper returns a single AgentSession per file; the JSONL granularity matches
the filesystem identity model (one session log → one session row).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from backend.application.ports.ingest import IngestCursor, IngestEvent, SessionIngestSource
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.repositories.sessions import compute_source_ref
from backend.parsers.sessions import parse_session_file

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1.0"
_SOURCE_ID = "filesystem"


def _mtime_iso(path: Path) -> str:
    """Return the mtime of *path* as a UTC ISO-8601 string."""
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _cursor_threshold(last_cursor: str | None) -> float:
    """Convert an opaque cursor value (ISO-8601 string or None) to a POSIX timestamp.

    Returns 0.0 when the cursor is None (ingest everything from the beginning).
    """
    if last_cursor is None:
        return 0.0
    try:
        return datetime.fromisoformat(last_cursor).timestamp()
    except ValueError:
        logger.warning(
            "FilesystemSource: unparseable last_cursor %r — treating as epoch 0",
            last_cursor,
        )
        return 0.0


class FilesystemSource:
    """SessionIngestSource backed by a directory of JSONL session log files.

    Cursors are mtime-based ISO-8601 strings, advancing monotonically.
    One IngestEvent is emitted per JSONL file (mirroring the one-session-per-file
    contract of the existing parsers).

    Parameters
    ----------
    sessions_dir:
        Root directory that is recursively scanned for ``*.jsonl`` files.
    project_id:
        CCDash project identifier propagated into every IngestEvent.
    cursor_repo:
        Repository used by ``ack()`` to advance the watermark.
    workspace_id:
        Workspace identifier (per ADR-008).  Defaults to ``"default"``.
    """

    source_id: str = _SOURCE_ID

    def __init__(
        self,
        *,
        sessions_dir: Path,
        project_id: str,
        cursor_repo: SqliteIngestCursorRepository,
        workspace_id: str = "default",
    ) -> None:
        self._sessions_dir = sessions_dir
        self._project_id = project_id
        self._cursor_repo = cursor_repo
        self._workspace_id = workspace_id

    async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:
        """Yield one IngestEvent per JSONL file whose mtime is newer than *since*.

        Files are yielded in ascending mtime order so the cursor advances
        monotonically.  Parse failures are logged and skipped — they do not
        interrupt the stream.
        """
        threshold = _cursor_threshold(since.last_cursor)

        if not self._sessions_dir.exists():
            logger.debug(
                "FilesystemSource: sessions_dir %s does not exist — yielding nothing",
                self._sessions_dir,
            )
            return

        # Collect candidate files in ascending mtime order.
        candidates: list[tuple[float, Path]] = []
        for path in self._sessions_dir.rglob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError as exc:
                logger.warning("FilesystemSource: cannot stat %s — %s", path, exc)
                continue
            if mtime > threshold:
                candidates.append((mtime, path))

        candidates.sort(key=lambda t: t[0])

        for mtime, path in candidates:
            try:
                session = parse_session_file(path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "FilesystemSource: failed to parse %s — %s", path, exc
                )
                continue

            if session is None:
                logger.debug("FilesystemSource: no session parsed from %s — skipping", path)
                continue

            try:
                rel_path = path.relative_to(self._sessions_dir)
            except ValueError:
                # path is not under sessions_dir (e.g., symlink resolution edge case)
                rel_path = Path(path.name)

            rel_path_str = rel_path.as_posix()
            source_ref = compute_source_ref(_SOURCE_ID, source_file=rel_path_str)
            cursor_value = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            # Build payload from AgentSession.  session.__dict__ or model_dump()
            # depending on whether AgentSession is a Pydantic model or dataclass.
            try:
                payload: dict = session.model_dump()
            except AttributeError:
                payload = session.__dict__.copy()

            yield IngestEvent(
                source_ref=source_ref,
                project_id=self._project_id,
                workspace_id=self._workspace_id,
                payload=payload,
                schema_version=_SCHEMA_VERSION,
                cursor_value=cursor_value,
                occurred_at=cursor_value,
            )

    async def ack(self, event: IngestEvent) -> None:
        """Advance the ingest_cursors watermark after a successful upsert."""
        await self._cursor_repo.advance(
            source_id=self.source_id,
            project_id=event.project_id,
            workspace_id=event.workspace_id,
            cursor_value=event.cursor_value,
            occurred_at=event.occurred_at,
        )


# Runtime-checkable Protocol conformance assertion (caught at import time in tests).
def _assert_protocol() -> None:  # pragma: no cover
    assert isinstance(FilesystemSource.__new__(FilesystemSource), SessionIngestSource), (
        "FilesystemSource does not satisfy SessionIngestSource protocol"
    )


__all__ = ["FilesystemSource"]
