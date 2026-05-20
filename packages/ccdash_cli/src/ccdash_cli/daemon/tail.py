"""File tail / change-detection for the CCDash ingest daemon.

Yields :class:`pathlib.Path` objects for JSONL files in *sessions_dir* whenever
they are created or modified.

Two backends are supported:
  1. **watchfiles** (preferred) — uses inotify/FSEvents for near-instant
     notification with minimal CPU.  Installed as an optional extra:
     ``pip install 'ccdash-cli[daemon]'`` or ``pip install watchfiles``.
  2. **mtime poll** (fallback) — checks file modification times every
     *poll_interval* seconds.  Adequate for the 5–30 s flush cadence but
     slightly higher idle CPU than the inotify-based approach.

The dependency on ``watchfiles`` is intentionally soft — if the package is
absent, the daemon logs once at INFO level and falls back automatically.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

_LOG = logging.getLogger(__name__)

# Whether we have already logged the watchfiles-fallback message.
_WATCHFILES_WARNED = False


async def iter_changed_files(
    sessions_dir: Path,
    poll_interval: float = 1.0,
) -> AsyncIterator[Path]:
    """Yield paths to JSONL files under *sessions_dir* when they change.

    Tries the ``watchfiles`` backend first; falls back to mtime polling if the
    package is not installed.

    Args:
        sessions_dir:   Directory to monitor for ``*.jsonl`` files.
        poll_interval:  Seconds between mtime polls (fallback mode only).

    Yields:
        Absolute :class:`~pathlib.Path` for each created or modified
        ``*.jsonl`` file.
    """
    global _WATCHFILES_WARNED  # noqa: PLW0603

    try:
        from watchfiles import awatch, Change  # type: ignore[import]

        async for changes in awatch(sessions_dir):
            for change_type, raw_path in changes:
                path = Path(raw_path)
                if path.suffix == ".jsonl" and change_type in (
                    Change.added,
                    Change.modified,
                ):
                    yield path
    except ImportError:
        if not _WATCHFILES_WARNED:
            _LOG.info(
                "watchfiles package not installed; falling back to %gs mtime poll. "
                "Install 'watchfiles' for lower CPU usage: pip install watchfiles",
                poll_interval,
            )
            _WATCHFILES_WARNED = True

        async for path in _mtime_poll(sessions_dir, poll_interval):
            yield path


async def _mtime_poll(
    sessions_dir: Path,
    poll_interval: float,
) -> AsyncIterator[Path]:
    """Simple mtime-based poll fallback.

    Yields a path whenever its modification time changes relative to the last
    observed value.  Also yields newly-discovered files on first sight.

    Args:
        sessions_dir:  Directory to scan.
        poll_interval: Seconds between scans.

    Yields:
        Changed or new ``*.jsonl`` paths.
    """
    last_seen: dict[Path, float] = {}

    while True:
        try:
            candidates = list(sessions_dir.glob("*.jsonl"))
        except OSError:
            candidates = []

        for path in candidates:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            prev_mtime = last_seen.get(path)
            if prev_mtime is None or mtime != prev_mtime:
                last_seen[path] = mtime
                yield path

        await asyncio.sleep(poll_interval)
