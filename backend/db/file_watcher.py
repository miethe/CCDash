"""File watcher service using watchfiles.

Monitors project directories for real-time changes and triggers
incremental re-sync on modified/added/deleted files.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from watchfiles import awatch, Change

logger = logging.getLogger("ccdash.watcher")


class FileWatcher:
    """Background file watcher that triggers sync on change.

    Uses `watchfiles` (Rust-accelerated) for efficient watching.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(
        self,
        sync_engine,
        project_id: str,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
    ) -> None:
        """Start watching project directories in a background task."""
        if self._running:
            logger.warning("File watcher already running")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._watch_loop(sync_engine, project_id, sessions_dir, docs_dir, progress_dir)
        )
        logger.info(f"File watcher started for project {project_id}")

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
        logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _watch_loop(
        self,
        sync_engine,
        project_id: str,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
    ) -> None:
        """Main watching loop. Watches all project dirs for changes."""
        watch_paths = [p for p in [sessions_dir, docs_dir, progress_dir] if p.exists()]

        if not watch_paths:
            logger.warning("No watch paths exist, watcher has nothing to monitor")
            self._running = False
            return

        logger.info(f"Watching {len(watch_paths)} directories: {[str(p) for p in watch_paths]}")

        try:
            async for changes in awatch(*watch_paths, stop_event=asyncio.Event() if not self._running else None):
                if not self._running:
                    break

                classified = self._classify_changes(changes, sessions_dir, docs_dir, progress_dir)
                if classified:
                    logger.info(f"Detected {len(classified)} file changes, syncing...")
                    try:
                        await sync_engine.sync_changed_files(
                            project_id, classified,
                            sessions_dir, docs_dir, progress_dir,
                        )
                    except Exception as e:
                        logger.error(f"Error syncing changed files: {e}")
        except asyncio.CancelledError:
            logger.info("File watcher task cancelled")
        except Exception as e:
            logger.error(f"File watcher error: {e}")
        finally:
            self._running = False

    def _classify_changes(
        self,
        changes: set[tuple[Change, str]],
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
    ) -> list[tuple[str, Path]]:
        """Classify raw watchfiles changes into (change_type, path) pairs.

        Only returns relevant file types (.jsonl, .md).
        """
        result = []
        for change_type, path_str in changes:
            path = Path(path_str)

            # Only care about session JSONL files and markdown docs
            if path.suffix not in (".jsonl", ".md"):
                continue

            if change_type == Change.deleted:
                result.append(("deleted", path))
            elif change_type in (Change.modified, Change.added):
                result.append(("modified", path))

        return result


# Singleton instance
file_watcher = FileWatcher()
