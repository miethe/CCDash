"""Main async daemon loop for the CCDash local ingest daemon.

Architecture
------------
Two coroutines run concurrently via :func:`asyncio.gather`:

* **Tail coroutine** — watches *sessions_dir* for changed ``*.jsonl`` files.
  Each changed file is parsed into session events and appended to the
  in-memory queue *and* the on-disk WAL (write-ahead log) for durability.

* **Flush coroutine** — fires every *flush_interval_seconds* OR when the
  in-memory queue reaches *max_batch_events*.  Takes a snapshot of the queue,
  POSTs an NDJSON batch, applies ack/partial-ack/dead-letter, and updates the
  status file.

Cross-package import notice
---------------------------
``backend.parsers.sessions.parse_session_file`` is imported here for session
log parsing.  This is the ONE intentional cross-package dependency: the daemon
ships alongside ``ccdash_cli`` but reuses the canonical parser so the event
payloads are always consistent with what the server stores.  See ADR-007.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from ccdash_cli.daemon.config import DaemonConfig
from ccdash_cli.daemon.tail import iter_changed_files
from ccdash_cli.daemon.uuid7 import uuid7
from ccdash_cli.daemon.wal import WalBuffer

_LOG = logging.getLogger(__name__)

_INGEST_PATH = "/api/v1/ingest/sessions"


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def run_daemon(
    config: DaemonConfig,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Run the ingest daemon until cancelled.

    Sets up the WAL buffer, dead-letter directory, and status file path, then
    launches two coroutines:
    - a tail loop that detects changed JSONL files and enqueues events, and
    - a flush loop that POSTs batches and updates the status file.

    Args:
        config:      Resolved :class:`~ccdash_cli.daemon.config.DaemonConfig`.
        http_client: Optional pre-built :class:`httpx.AsyncClient` for testing.
                     When *None* a client is constructed from *config*.

    Raises:
        asyncio.CancelledError: On graceful shutdown; a final flush is attempted
                                before propagating.
    """
    # Ensure all state directories exist.
    config.buffer_root.mkdir(parents=True, exist_ok=True)
    config.deadletter_root.mkdir(parents=True, exist_ok=True)
    config.status_path.parent.mkdir(parents=True, exist_ok=True)

    wal = WalBuffer(config.buffer_root)
    queue: list[dict] = []
    counters = _Counters()

    # Build HTTP client if not injected.
    _owns_client = http_client is None
    if _owns_client:
        http_client = _build_http_client(config)

    assert http_client is not None

    try:
        # Replay any WAL segments from a previous run before starting the tail.
        await _replay_wal(wal, config, http_client, counters)

        tail_task = asyncio.create_task(
            _tail_coroutine(config, wal, queue),
            name="daemon-tail",
        )
        flush_task = asyncio.create_task(
            _flush_coroutine(config, wal, queue, http_client, counters),
            name="daemon-flush",
        )

        try:
            await asyncio.gather(tail_task, flush_task)
        except asyncio.CancelledError:
            # Graceful shutdown: cancel the two tasks then do a final flush.
            tail_task.cancel()
            flush_task.cancel()
            await asyncio.gather(tail_task, flush_task, return_exceptions=True)

            _LOG.info("Daemon shutting down — flushing remaining events …")
            if queue:
                batch_id = uuid7()
                events = _make_events(queue, batch_id)
                queue.clear()
                seg = wal.pending_segments()
                seg_path = seg[-1] if seg else None
                if seg_path:
                    await _post_batch(
                        events=events,
                        segment_path=seg_path,
                        wal=wal,
                        config=config,
                        http_client=http_client,
                        counters=counters,
                    )
            await _write_status(config, wal, counters, last_error=None)
            raise
    finally:
        if _owns_client:
            await http_client.aclose()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Counters:
    __slots__ = ("accepted_total", "rejected_total", "deadlettered_total", "last_error")

    def __init__(self) -> None:
        self.accepted_total: int = 0
        self.rejected_total: int = 0
        self.deadlettered_total: int = 0
        self.last_error: str | None = None


def _build_http_client(config: DaemonConfig) -> httpx.AsyncClient:
    """Construct an :class:`httpx.AsyncClient` configured for daemon use."""
    return httpx.AsyncClient(
        base_url=config.server_url,
        headers={
            "Authorization": f"Bearer {config.token}",
            "x-ccdash-project-id": config.project_id,
            "Content-Type": "application/x-ndjson",
        },
        timeout=30.0,
        follow_redirects=True,
    )


def _make_events(raw_events: list[dict], batch_id: str) -> list[dict]:
    """Stamp events with the given *batch_id* (event_id already set)."""
    out = []
    for ev in raw_events:
        stamped = dict(ev)
        stamped["batch_id"] = batch_id
        out.append(stamped)
    return out


def _build_event(session: Any, batch_id: str) -> dict:
    """Build an IngestSessionEvent-shaped dict from a parsed session object."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    eid = uuid7()

    # session may be a Pydantic model or a plain dict-like object.
    try:
        payload: dict = session.model_dump()
    except AttributeError:
        try:
            payload = dict(session.__dict__)
        except AttributeError:
            payload = dict(session)

    return {
        "event_id": eid,
        "batch_id": batch_id,
        "schema_version": "1.0",
        "occurred_at": now_iso,
        "payload": payload,
    }


async def _tail_coroutine(
    config: DaemonConfig,
    wal: WalBuffer,
    queue: list[dict],
) -> None:
    """Watch *sessions_dir* and enqueue events for changed JSONL files.

    Cross-package import: ``backend.parsers.sessions.parse_session_file`` is
    imported lazily here — the one intentional cross-package dependency per
    ADR-007.  The import is deferred to avoid failing at package-import time in
    environments where the backend package is not installed (e.g. test
    environments that mock the parser).
    """
    # Lazy cross-package import (backend.parsers.sessions) — see ADR-007.
    try:
        from backend.parsers.sessions import parse_session_file  # type: ignore[import]
    except ImportError as exc:
        _LOG.error(
            "Cannot import backend.parsers.sessions: %s. "
            "Ensure the CCDash backend package is installed alongside ccdash-cli.",
            exc,
        )
        return

    _LOG.info("Tail coroutine started; watching %s", config.sessions_dir)
    batch_id = uuid7()  # shared across the current accumulation window

    async for path in iter_changed_files(config.sessions_dir):
        _LOG.debug("Detected change: %s", path)
        try:
            session = await asyncio.to_thread(parse_session_file, path)
        except Exception as exc:
            _LOG.warning("Failed to parse session file %s: %s", path, exc)
            continue

        if session is None:
            continue

        event = _build_event(session, batch_id)

        # WAL write first (durability before network).
        try:
            await asyncio.to_thread(wal.append, event)
        except Exception as exc:
            _LOG.error("WAL append failed: %s", exc)

        queue.append(event)

        # Rotate the batch_id on every accumulation window boundary.
        if len(queue) >= config.max_batch_events:
            batch_id = uuid7()


async def _flush_coroutine(
    config: DaemonConfig,
    wal: WalBuffer,
    queue: list[dict],
    http_client: httpx.AsyncClient,
    counters: _Counters,
) -> None:
    """Periodically flush the in-memory queue to the server."""
    _LOG.info(
        "Flush coroutine started; interval=%gs max_batch=%d",
        config.flush_interval_seconds,
        config.max_batch_events,
    )
    while True:
        await asyncio.sleep(config.flush_interval_seconds)

        # Take a snapshot and clear the live queue atomically.
        if not queue:
            # No in-memory events — check for leftover WAL segments.
            pending = await asyncio.to_thread(wal.pending_segments)
            for seg in pending:
                events = await asyncio.to_thread(wal.peek_segment, seg)
                if events:
                    await _post_batch(
                        events=events,
                        segment_path=seg,
                        wal=wal,
                        config=config,
                        http_client=http_client,
                        counters=counters,
                    )
            await _write_status(config, wal, counters, last_error=counters.last_error)
            continue

        snapshot = list(queue)
        queue.clear()

        # Split into sub-batches respecting max_batch_events.
        for i in range(0, len(snapshot), config.max_batch_events):
            sub_batch = snapshot[i : i + config.max_batch_events]
            pending = await asyncio.to_thread(wal.pending_segments)
            seg_path = pending[-1] if pending else None
            if seg_path is None:
                # Edge case: events in queue but WAL has no segment.
                # Write them to WAL now.
                for ev in sub_batch:
                    await asyncio.to_thread(wal.append, ev)
                pending = await asyncio.to_thread(wal.pending_segments)
                seg_path = pending[-1] if pending else None

            if seg_path:
                await _post_batch(
                    events=sub_batch,
                    segment_path=seg_path,
                    wal=wal,
                    config=config,
                    http_client=http_client,
                    counters=counters,
                )

        await _write_status(config, wal, counters, last_error=counters.last_error)


async def _replay_wal(
    wal: WalBuffer,
    config: DaemonConfig,
    http_client: httpx.AsyncClient,
    counters: _Counters,
) -> None:
    """Replay any WAL segments left from a prior daemon run."""
    pending = await asyncio.to_thread(wal.pending_segments)
    if not pending:
        return
    _LOG.info("Replaying %d WAL segment(s) from previous run …", len(pending))
    for seg in pending:
        events = await asyncio.to_thread(wal.peek_segment, seg)
        if events:
            await _post_batch(
                events=events,
                segment_path=seg,
                wal=wal,
                config=config,
                http_client=http_client,
                counters=counters,
            )


async def _post_batch(
    *,
    events: list[dict],
    segment_path: Path,
    wal: WalBuffer,
    config: DaemonConfig,
    http_client: httpx.AsyncClient,
    counters: _Counters,
) -> None:
    """POST a batch of events to the ingest endpoint with retry/backoff.

    Handles:
    - 200 success → ack_segment
    - 200 with non-empty ``rejected`` → partial_ack + dead-letter rejected
    - 413 → split in half (recursively) or dead-letter if size == 1
    - 429 → honor ``Retry-After`` header then retry
    - 5xx / connection error → exponential backoff; on exhaustion leave WAL intact
    """
    if not events:
        return

    ndjson_body = "\n".join(json.dumps(ev, separators=(",", ":")) for ev in events) + "\n"

    last_error: str | None = None

    for attempt in range(config.max_retries + 1):
        try:
            response = await http_client.post(
                _INGEST_PATH,
                content=ndjson_body.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            last_error = str(exc)
            _LOG.warning(
                "POST attempt %d/%d failed (connection): %s",
                attempt + 1,
                config.max_retries + 1,
                exc,
            )
            if attempt < config.max_retries:
                backoff = min(60.0, 0.1 * (2 ** attempt))
                await asyncio.sleep(backoff)
            continue

        status = response.status_code

        if status == 200:
            try:
                body = response.json()
            except Exception:
                body = {}

            rejected = body.get("rejected", [])
            if rejected:
                accepted_ids = {
                    ev["event_id"]
                    for ev in events
                    if ev.get("event_id") not in {r.get("event_id") for r in rejected}
                }
                # partial_ack keeps only the un-accepted events
                await asyncio.to_thread(wal.partial_ack, segment_path, accepted_ids)
                _write_deadletter(config.deadletter_root, rejected)
                counters.accepted_total += len(accepted_ids)
                counters.rejected_total += len(rejected)
                _LOG.warning(
                    "Partial success: accepted=%d rejected=%d",
                    len(accepted_ids),
                    len(rejected),
                )
            else:
                n = body.get("accepted", len(events))
                counters.accepted_total += n
                await asyncio.to_thread(wal.ack_segment, segment_path)
                _LOG.debug("Batch accepted: %d events", n)

            counters.last_error = None
            return

        if status == 413:
            _LOG.warning(
                "Batch too large (413); splitting %d events in half …", len(events)
            )
            if len(events) == 1:
                # Cannot split further — dead-letter this event.
                _write_deadletter(config.deadletter_root, events)
                counters.deadlettered_total += 1
                await asyncio.to_thread(wal.ack_segment, segment_path)
                return
            mid = len(events) // 2
            await _post_batch(
                events=events[:mid],
                segment_path=segment_path,
                wal=wal,
                config=config,
                http_client=http_client,
                counters=counters,
            )
            await _post_batch(
                events=events[mid:],
                segment_path=segment_path,
                wal=wal,
                config=config,
                http_client=http_client,
                counters=counters,
            )
            return

        if status == 429:
            retry_after = _parse_retry_after(response)
            _LOG.warning(
                "Rate limited (429); sleeping %gs before retry %d/%d …",
                retry_after,
                attempt + 1,
                config.max_retries,
            )
            await asyncio.sleep(retry_after)
            last_error = f"429 rate limited (Retry-After={retry_after}s)"
            continue

        if status >= 500:
            last_error = f"HTTP {status}"
            _LOG.warning(
                "Server error %d on attempt %d/%d",
                status,
                attempt + 1,
                config.max_retries + 1,
            )
            if attempt < config.max_retries:
                backoff = min(60.0, 0.1 * (2 ** attempt))
                await asyncio.sleep(backoff)
            continue

        # Unexpected 4xx — dead-letter immediately, do not retry.
        _LOG.error("Unexpected HTTP %d — dead-lettering %d events", status, len(events))
        _write_deadletter(config.deadletter_root, events)
        counters.deadlettered_total += len(events)
        await asyncio.to_thread(wal.ack_segment, segment_path)
        counters.last_error = f"HTTP {status} — dead-lettered"
        return

    # Exhausted all retries — leave WAL segment intact for next flush.
    _LOG.error(
        "Exhausted %d retries for batch of %d events; WAL segment retained for retry.",
        config.max_retries,
        len(events),
    )
    counters.last_error = last_error


def _parse_retry_after(response: httpx.Response) -> float:
    """Extract the ``Retry-After`` header value in seconds (default 5s)."""
    header = response.headers.get("Retry-After", "")
    try:
        return float(header)
    except (ValueError, TypeError):
        return 5.0


def _write_deadletter(deadletter_root: Path, events: list[dict]) -> None:
    """Append *events* to a dead-letter file."""
    ts_ms = int(time.time() * 1000)
    dl_path = deadletter_root / f"deadletter-{ts_ms:016d}.ndjson"
    try:
        with dl_path.open("a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev, separators=(",", ":")) + "\n")
        _LOG.warning("Dead-lettered %d event(s) to %s", len(events), dl_path)
    except OSError as exc:
        _LOG.error("Failed to write dead-letter file %s: %s", dl_path, exc)


async def _write_status(
    config: DaemonConfig,
    wal: WalBuffer,
    counters: _Counters,
    last_error: str | None,
) -> None:
    """Atomically write the JSON status file (temp + rename)."""
    depth = await asyncio.to_thread(wal.depth)
    status: dict[str, Any] = {
        "last_batch_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "accepted_total": counters.accepted_total,
        "rejected_total": counters.rejected_total,
        "deadlettered_total": counters.deadlettered_total,
        "buffer_depth": depth,
        "last_error": last_error,
    }
    tmp = config.status_path.with_suffix(".tmp")
    try:
        content = json.dumps(status, indent=2).encode("utf-8")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)
        tmp.rename(config.status_path)
    except OSError as exc:
        _LOG.warning("Failed to write status file %s: %s", config.status_path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
