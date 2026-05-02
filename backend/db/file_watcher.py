"""File watcher service using watchfiles.

Monitors project directories for real-time changes and triggers
incremental re-sync on modified/added/deleted files.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
        )
        self._snapshot.configured = True
        self._snapshot.project_id = project_id
        self._snapshot.watch_paths = [str(path) for path in watch_paths]
        self._snapshot.last_change_sync_at = None
        self._snapshot.last_change_count = None
        self._snapshot.last_sync_status = None
        self._snapshot.last_sync_error = None

        if not watch_paths:
            self._running = False
            self._snapshot.running = False
            logger.warning(
                "File watcher configured with no existing paths",
                extra={"project_id": project_id, "watch_path_count": 0, "watch_paths": []},
            )
            return

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
                        )
                    except Exception as e:
                        if _otel is not None:
                            _otel.record_watcher_sync_latency((time.monotonic() - _t0) * 1000.0)
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
    ) -> list[Path]:
        watch_paths = [p for p in [sessions_dir, docs_dir, progress_dir] if p.exists()]
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


# Singleton instance
file_watcher = FileWatcher()
