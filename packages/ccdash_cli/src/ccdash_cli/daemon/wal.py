"""On-disk write-ahead log (WAL) for the CCDash ingest daemon.

The WAL guarantees at-least-once delivery: events are persisted to disk
(append-then-fsync) before any network attempt.  Successful delivery removes
the segment (``ack_segment``).  Partial delivery rewrites the segment keeping
only the un-accepted events (``partial_ack``).

Segment naming: ``segment-<UNIX-ms>-<seq>-<uuid4>.ndjson``
  - UNIX-ms is zero-padded to 16 digits for lexicographic sort.
  - seq is a zero-padded 8-digit monotonic counter that breaks ties when
    two segments are created within the same millisecond.
  - Sorting by filename produces strict chronological order.

All public methods are synchronous.  The daemon calls them via
``asyncio.to_thread`` so the event loop is never blocked.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

_LOG = logging.getLogger(__name__)

_DEFAULT_MAX_SEGMENT_LINES = 500
_DEFAULT_MAX_SEGMENT_BYTES = 5 * 1024 * 1024  # 5 MB

# Process-local monotonic sequence counter so same-millisecond segments sort in
# creation order.  Not thread-safe; the daemon is async/single-threaded.
_SEGMENT_SEQ: int = 0


class WalBuffer:
    """Append-only, rotate-on-limit WAL backed by NDJSON segment files.

    Args:
        root:                 Directory that holds segment files.
        max_segment_lines:    Rotate to a new segment after this many lines
                              (default 500).
        max_segment_bytes:    Rotate to a new segment when the current segment
                              reaches this size in bytes (default 5 MB).
    """

    def __init__(
        self,
        root: Path,
        max_segment_lines: int = _DEFAULT_MAX_SEGMENT_LINES,
        max_segment_bytes: int = _DEFAULT_MAX_SEGMENT_BYTES,
    ) -> None:
        self._root = root
        self._max_lines = max_segment_lines
        self._max_bytes = max_segment_bytes
        self._current_path: Path | None = None
        self._current_lines: int = 0
        self._current_bytes: int = 0

        root.mkdir(parents=True, exist_ok=True)
        self._recover_current()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _new_segment_path(self) -> Path:
        global _SEGMENT_SEQ  # noqa: PLW0603
        ts_ms = int(time.time() * 1000)
        _SEGMENT_SEQ += 1
        uid = uuid.uuid4().hex
        # Include a zero-padded sequence number after the timestamp so that
        # same-millisecond segments sort in strict creation order.
        return self._root / f"segment-{ts_ms:016d}-{_SEGMENT_SEQ:08d}-{uid}.ndjson"

    def _recover_current(self) -> None:
        """On init, resume writing to the most-recent open segment if it exists."""
        segments = self.pending_segments()
        if segments:
            last = segments[-1]
            try:
                lines = last.read_text(encoding="utf-8").splitlines()
                n = len(lines)
                b = last.stat().st_size
                if n < self._max_lines and b < self._max_bytes:
                    self._current_path = last
                    self._current_lines = n
                    self._current_bytes = b
                    return
            except OSError:
                pass
        # Start a fresh segment on next append
        self._current_path = None
        self._current_lines = 0
        self._current_bytes = 0

    def _ensure_segment(self) -> Path:
        """Return the current writable segment path, creating one if needed."""
        if (
            self._current_path is None
            or self._current_lines >= self._max_lines
            or self._current_bytes >= self._max_bytes
        ):
            self._current_path = self._new_segment_path()
            self._current_lines = 0
            self._current_bytes = 0
        return self._current_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, event_dict: dict) -> None:
        """Serialise *event_dict* as a JSON line and fsync to the current segment.

        Rotates to a new segment when the line or byte limit is reached.

        Args:
            event_dict: Arbitrary JSON-serialisable dict representing one event.
        """
        line = json.dumps(event_dict, separators=(",", ":")) + "\n"
        line_bytes = line.encode("utf-8")

        path = self._ensure_segment()

        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)

        self._current_lines += 1
        self._current_bytes += len(line_bytes)

        # Check rotation threshold after write
        if self._current_lines >= self._max_lines or self._current_bytes >= self._max_bytes:
            # Force new segment on next append
            self._current_path = None
            self._current_lines = 0
            self._current_bytes = 0

    def pending_segments(self) -> list[Path]:
        """Return segment paths sorted ascending by filename (chronological).

        Returns:
            Sorted list of ``*.ndjson`` segment paths.
        """
        try:
            paths = sorted(self._root.glob("segment-*.ndjson"))
        except OSError:
            paths = []
        return paths

    def peek_segment(self, path: Path) -> list[dict]:
        """Parse a segment file and return its events without deleting it.

        Args:
            path: Path to a segment file (typically from :meth:`pending_segments`).

        Returns:
            List of parsed event dicts (empty list if the file is empty or missing).
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []

        events: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _LOG.warning("WAL segment %s has malformed line: %s", path, exc)
        return events

    def ack_segment(self, path: Path) -> None:
        """Delete a successfully delivered segment (fsync parent dir first).

        Args:
            path: Path to the segment to remove.
        """
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            _LOG.warning("Could not delete WAL segment %s: %s", path, exc)
            return

        # Fsync the parent directory so the unlink survives a crash.
        try:
            dir_fd = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

        # If we just acked our current segment, reset the pointer.
        if path == self._current_path:
            self._current_path = None
            self._current_lines = 0
            self._current_bytes = 0

    def partial_ack(self, path: Path, accepted_event_ids: set[str]) -> None:
        """Rewrite a segment keeping only events NOT in *accepted_event_ids*.

        This implements partial-failure recovery: events whose ``event_id`` was
        accepted by the server are removed; the rest remain for the next flush.

        Args:
            path:               Segment path to rewrite.
            accepted_event_ids: Set of ``event_id`` strings that were accepted.
        """
        events = self.peek_segment(path)
        remaining = [e for e in events if e.get("event_id") not in accepted_event_ids]

        if not remaining:
            self.ack_segment(path)
            return

        # Write to a temp file then atomically rename.
        tmp_path = path.with_suffix(".tmp")
        try:
            content = "\n".join(
                json.dumps(e, separators=(",", ":")) for e in remaining
            ) + "\n"
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, content.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            tmp_path.rename(path)
        except OSError as exc:
            _LOG.error("partial_ack rewrite failed for %s: %s", path, exc)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

        # Reset current segment pointer if the rewritten file is our current one.
        if path == self._current_path:
            try:
                b = path.stat().st_size
                n = len(remaining)
                self._current_lines = n
                self._current_bytes = b
            except OSError:
                self._current_path = None

    def depth(self) -> int:
        """Count total pending event lines across all segments.

        Returns:
            Total number of buffered events (sum of line counts across segments).
        """
        total = 0
        for seg in self.pending_segments():
            try:
                lines = seg.read_text(encoding="utf-8").splitlines()
                total += sum(1 for ln in lines if ln.strip())
            except OSError:
                pass
        return total
