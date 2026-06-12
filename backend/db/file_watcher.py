"""File watcher service using watchfiles.

Monitors project directories for real-time changes and triggers
incremental re-sync on modified/added/deleted files.

P3-005: FileWatcherRegistry — one watcher task per registered project;
        start/stop/snapshot per project; is_running(project_id);
        aggregate snapshot reports per-project watch state.
P3-010: asyncio.Lock wraps register/unregister/rebind so concurrent calls
        are serialised and never produce torn watcher state.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from watchfiles import awatch, Change

from backend.services.test_config import ResolvedTestSource

try:
    from backend.observability import otel as _otel
except ImportError:  # pragma: no cover — observability is optional
    _otel = None  # type: ignore[assignment]

logger = logging.getLogger("ccdash.watcher")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class FileWatcherSnapshot:
    configured: bool = False
    running: bool = False
    project_id: str | None = None
    watch_paths: list[str] = field(default_factory=list)
    last_change_sync_at: str | None = None
    last_change_count: int | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None

    @property
    def watch_path_count(self) -> int:
        return len(self.watch_paths)

    def as_dict(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "running": self.running,
            "projectId": self.project_id,
            "watchPaths": list(self.watch_paths),
            "watchPathCount": self.watch_path_count,
            "lastChangeSyncAt": self.last_change_sync_at,
            "lastChangeCount": self.last_change_count,
            "lastSyncStatus": self.last_sync_status,
            "lastSyncError": self.last_sync_error,
        }


class FileWatcher:
    """Background file watcher that triggers sync on change.

    Uses `watchfiles` (Rust-accelerated) for efficient watching.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._allow_writeback: bool = True
        self._snapshot = FileWatcherSnapshot()

    async def start(
        self,
        sync_engine,
        project_id: str,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        test_results_dir: Path | None = None,
        test_sources: list[ResolvedTestSource] | None = None,
        worknotes_dir: Path | None = None,
        allow_writeback: bool = True,
    ) -> None:
        """Start watching project directories in a background task."""
        if self._running:
            logger.warning(
                "File watcher already running",
                extra={"project_id": self._snapshot.project_id, "watch_path_count": self._snapshot.watch_path_count},
            )
            return

        watch_paths = self._resolve_watch_paths(
            sessions_dir,
            docs_dir,
            progress_dir,
            test_results_dir,
            test_sources,
            worknotes_dir=worknotes_dir,
        )
        self._snapshot.configured = True
        self._snapshot.project_id = project_id
        self._snapshot.watch_paths = [str(path) for path in watch_paths]
        self._snapshot.last_change_sync_at = None
        self._snapshot.last_change_count = None
        self._snapshot.last_sync_status = None
        self._snapshot.last_sync_error = None

        # T12-005: pre-register in the watcher-event-age gauge so the probe
        # emits the sentinel (-1.0) rather than omitting this project until
        # its first change event arrives (AC R12.5).
        if _otel is not None:
            _otel.set_watcher_project_registered(project_id)

        if not watch_paths:
            self._running = False
            self._snapshot.running = False
            logger.warning(
                "File watcher configured with no existing paths",
                extra={"project_id": project_id, "watch_path_count": 0, "watch_paths": []},
            )
            return

        self._allow_writeback = allow_writeback
        self._running = True
        self._snapshot.running = True
        self._task = asyncio.create_task(
            self._watch_loop(
                sync_engine,
                project_id,
                sessions_dir,
                docs_dir,
                progress_dir,
                watch_paths,
                test_results_dir,
                test_sources,
                allow_writeback=allow_writeback,
            )
        )
        logger.info(
            "File watcher started",
            extra={
                "project_id": project_id,
                "watch_path_count": len(watch_paths),
                "watch_paths": [str(path) for path in watch_paths],
            },
        )

    async def stop(self) -> None:
        """Stop the file watcher."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._snapshot.running = False
        logger.info(
            "File watcher stopped",
            extra={"project_id": self._snapshot.project_id, "watch_path_count": self._snapshot.watch_path_count},
        )

    @property
    def is_running(self) -> bool:
        return self._running

    def snapshot(self) -> dict[str, object]:
        self._snapshot.running = self._running
        return self._snapshot.as_dict()

    async def _watch_loop(
        self,
        sync_engine,
        project_id: str,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        watch_paths: list[Path],
        test_results_dir: Path | None = None,
        test_sources: list[ResolvedTestSource] | None = None,
        allow_writeback: bool = True,
    ) -> None:
        """Main watching loop. Watches all project dirs for changes."""
        logger.info(
            "Watching directories",
            extra={
                "project_id": project_id,
                "watch_path_count": len(watch_paths),
                "watch_paths": [str(path) for path in watch_paths],
            },
        )

        try:
            async for changes in awatch(*watch_paths, stop_event=asyncio.Event() if not self._running else None):
                if not self._running:
                    break

                classified = self._classify_changes(
                    changes,
                    test_results_dir,
                    test_sources,
                )
                logger.info(
                    "File watcher classified changes",
                    extra={
                        "project_id": project_id,
                        "raw_change_count": len(changes),
                        "classified_change_count": len(classified),
                        "classified_changes": [
                            {"change_type": change_type, "path": str(path)}
                            for change_type, path in classified
                        ],
                    },
                )
                if classified:
                    _t0 = time.monotonic()
                    try:
                        await sync_engine.sync_changed_files(
                            project_id, classified,
                            sessions_dir, docs_dir, progress_dir,
                            test_results_dir=test_results_dir,
                            test_sources=test_sources,
                            allow_writeback=allow_writeback,
                        )
                    except Exception as e:
                        if _otel is not None:
                            _otel.record_watcher_sync_latency((time.monotonic() - _t0) * 1000.0)
                            # T12-005: record event age even on sync failure — the
                            # watcher DID fire; it's the downstream sync that failed.
                            _otel.record_watcher_event(project_id)
                        self._snapshot.last_change_sync_at = _utc_now_iso()
                        self._snapshot.last_change_count = len(classified)
                        self._snapshot.last_sync_status = "failed"
                        self._snapshot.last_sync_error = str(e) or e.__class__.__name__
                        logger.exception(
                            "File watcher change sync failed",
                            extra={
                                "project_id": project_id,
                                "classified_change_count": len(classified),
                                "error": self._snapshot.last_sync_error,
                            },
                        )
                    else:
                        if _otel is not None:
                            _otel.record_watcher_sync_latency((time.monotonic() - _t0) * 1000.0)
                            # T12-005: record event age on success.
                            _otel.record_watcher_event(project_id)
                        self._snapshot.last_change_sync_at = _utc_now_iso()
                        self._snapshot.last_change_count = len(classified)
                        self._snapshot.last_sync_status = "succeeded"
                        self._snapshot.last_sync_error = None
                        logger.info(
                            "File watcher change sync succeeded",
                            extra={"project_id": project_id, "classified_change_count": len(classified)},
                        )
        except asyncio.CancelledError:
            logger.info("File watcher task cancelled", extra={"project_id": project_id})
        except Exception as e:
            self._snapshot.last_sync_status = "failed"
            self._snapshot.last_sync_error = str(e) or e.__class__.__name__
            logger.exception(
                "File watcher error",
                extra={"project_id": project_id, "error": self._snapshot.last_sync_error},
            )
        finally:
            self._running = False
            self._snapshot.running = False

    def _resolve_watch_paths(
        self,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        test_results_dir: Path | None = None,
        test_sources: list[ResolvedTestSource] | None = None,
        worknotes_dir: Path | None = None,
    ) -> list[Path]:
        watch_paths = [p for p in [sessions_dir, docs_dir, progress_dir] if p.exists()]
        if worknotes_dir is not None and worknotes_dir.exists():
            watch_paths.append(worknotes_dir)
        if test_results_dir and test_results_dir.exists():
            watch_paths.append(test_results_dir)
        for source in test_sources or []:
            if source.watch and source.enabled and source.resolved_dir.exists():
                watch_paths.append(source.resolved_dir)
        return list(dict.fromkeys(watch_paths))

    def _classify_changes(
        self,
        changes: set[tuple[Change, str]],
        test_results_dir: Path | None = None,
        test_sources: list[ResolvedTestSource] | None = None,
    ) -> list[tuple[str, Path]]:
        """Classify raw watchfiles changes into (change_type, path) pairs.

        Returns relevant session/doc/test artifact file types.
        """
        artifact_suffixes = {".xml", ".json", ".csv", ".html", ".txt", ".info"}
        result = []
        for change_type, path_str in changes:
            path = Path(path_str)

            if path.suffix in artifact_suffixes:
                in_legacy_dir = bool(
                    test_results_dir
                    and (path == test_results_dir or test_results_dir in path.parents)
                )
                in_test_source = False
                for source in test_sources or []:
                    if path == source.resolved_dir or source.resolved_dir in path.parents:
                        in_test_source = True
                        break
                if not in_legacy_dir and not in_test_source:
                    continue
            elif path.suffix not in (".jsonl", ".md"):
                continue

            if change_type == Change.deleted:
                result.append(("deleted", path))
            elif change_type in (Change.modified, Change.added):
                result.append(("modified", path))

        return result


# ── P3-005: FileWatcherRegistry ──────────────────────────────────────────────


@dataclass
class _WatcherEntry:
    """Internal registry entry: one FileWatcher + its creation args."""
    watcher: FileWatcher
    # Paths used at start-time (for snapshot display)
    sessions_dir: Path
    docs_dir: Path
    progress_dir: Path


class FileWatcherRegistry:
    """Registry that owns one FileWatcher task per registered project_id.

    Thread-safety / concurrency: all mutating operations (register,
    unregister) acquire ``_lock`` (asyncio.Lock) so concurrent rebind
    calls cannot produce torn watcher state (P3-010).

    Usage::

        registry = FileWatcherRegistry()

        # start a watcher for a project
        await registry.register(project_id, sync_engine, sessions_dir, docs_dir, progress_dir)

        # check running state
        registry.is_running("proj-1")   # True / False

        # per-project snapshot
        registry.snapshot("proj-1")     # dict

        # aggregate snapshot (all projects)
        registry.snapshot_all()         # dict[project_id, dict]

        # tear down one project
        await registry.unregister("proj-1")

        # tear down all
        await registry.stop_all()
    """

    def __init__(self) -> None:
        self._entries: dict[str, _WatcherEntry] = {}
        # P3-010: serialise all mutating calls
        self._lock: asyncio.Lock | None = None  # lazy-init (loop may not exist at import time)

    def _get_lock(self) -> asyncio.Lock:
        """Return (or lazily create) the asyncio.Lock for the running loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def register(
        self,
        sync_engine,
        project_id: str,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        test_results_dir: Path | None = None,
        test_sources: list[ResolvedTestSource] | None = None,
        worknotes_dir: Path | None = None,
        allow_writeback: bool = True,
    ) -> None:
        """Start (or restart) a watcher for *project_id*.

        If a watcher is already running for this project it is stopped first
        so callers can safely call register on rebind without a prior
        unregister call.
        """
        async with self._get_lock():
            # Stop existing watcher for this project if present
            existing = self._entries.get(project_id)
            if existing is not None:
                await existing.watcher.stop()
                del self._entries[project_id]

            watcher = FileWatcher()
            await watcher.start(
                sync_engine,
                project_id,
                sessions_dir,
                docs_dir,
                progress_dir,
                test_results_dir=test_results_dir,
                test_sources=test_sources,
                worknotes_dir=worknotes_dir,
                allow_writeback=allow_writeback,
            )
            self._entries[project_id] = _WatcherEntry(
                watcher=watcher,
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
            )
            logger.info(
                "FileWatcherRegistry: registered project '%s' (total=%d)",
                project_id,
                len(self._entries),
            )

    async def unregister(self, project_id: str) -> None:
        """Stop and remove the watcher for *project_id* (no-op if absent)."""
        async with self._get_lock():
            entry = self._entries.pop(project_id, None)
            if entry is not None:
                await entry.watcher.stop()
                logger.info(
                    "FileWatcherRegistry: unregistered project '%s' (remaining=%d)",
                    project_id,
                    len(self._entries),
                )

    def is_running(self, project_id: str) -> bool:
        """Return True if a running watcher task exists for *project_id*."""
        entry = self._entries.get(project_id)
        return entry is not None and entry.watcher.is_running

    def dead_project_ids(self, expected_ids: Iterable[str]) -> list[str]:
        """Phase 8 (T8-003): liveness predicate for watcher self-heal.

        Returns every id in *expected_ids* whose watcher is NOT currently
        running — covering both the registered-but-crashed case (entry exists
        but ``watcher.is_running`` is False because ``_watch_loop`` set
        ``_running=False`` on exception) and the expected-but-never-registered
        case (post-boot project the reconcile tick should bind).  Pure read; no
        lock required.  The reconcile tick re-registers each returned id from
        the DB-authoritative registry binding.
        """
        dead: list[str] = []
        for pid in expected_ids:
            pid_s = str(pid or "")
            if not pid_s:
                continue
            if not self.is_running(pid_s):
                dead.append(pid_s)
        return dead

    def snapshot(self, project_id: str) -> dict[str, object] | None:
        """Return the snapshot dict for *project_id*, or None if not registered."""
        entry = self._entries.get(project_id)
        if entry is None:
            return None
        return entry.watcher.snapshot()

    def snapshot_all(self) -> dict[str, dict[str, object]]:
        """Return a dict keyed by project_id with each project's snapshot."""
        return {pid: entry.watcher.snapshot() for pid, entry in self._entries.items()}

    @property
    def registered_project_ids(self) -> list[str]:
        """Return the list of currently registered project IDs."""
        return list(self._entries.keys())

    async def stop_all(self) -> None:
        """Stop and unregister all watchers."""
        async with self._get_lock():
            for pid, entry in list(self._entries.items()):
                await entry.watcher.stop()
                logger.info("FileWatcherRegistry: stopped watcher for project '%s'", pid)
            self._entries.clear()


# ── Module-level singletons ──────────────────────────────────────────────────

# Legacy singleton (kept for backward compatibility; registry is the preferred API)
file_watcher = FileWatcher()

# Multi-project registry singleton (P3-005)
file_watcher_registry = FileWatcherRegistry()
