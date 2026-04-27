"""Filesystem scan manifest repository.

Tracks per-file mtime/size snapshots so the sync engine can cheaply detect
which paths have been added, removed, or changed since the last scan without
hashing every file on every startup.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger("ccdash.db.scan_manifest")


class SqliteScanManifestRepository:
    """Concrete SQLite implementation of the scan manifest store."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Writes                                                               #
    # ------------------------------------------------------------------ #

    async def upsert_manifest(self, entries: list[tuple[str, float, int]]) -> None:
        """Insert or replace manifest rows.

        Args:
            entries: Sequence of ``(path, mtime_epoch_seconds, size_bytes)``
                     triples.  ``scanned_at`` is filled with the current UTC
                     ISO timestamp automatically.
        """
        if not entries:
            return
        scanned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.db.executemany(
            """
            INSERT INTO filesystem_scan_manifest (path, mtime, size, scanned_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                mtime      = excluded.mtime,
                size       = excluded.size,
                scanned_at = excluded.scanned_at
            """,
            [(path, mtime, size, scanned_at) for path, mtime, size in entries],
        )
        await self.db.commit()

    # ------------------------------------------------------------------ #
    # Reads                                                                #
    # ------------------------------------------------------------------ #

    async def fetch_manifest(self) -> dict[str, tuple[float, int]]:
        """Return the full manifest as ``{path: (mtime, size)}``.

        An empty dict is returned when the table is empty or does not exist
        yet (defensive for tests that skip migrations).
        """
        try:
            async with self.db.execute(
                "SELECT path, mtime, size FROM filesystem_scan_manifest"
            ) as cur:
                rows = await cur.fetchall()
        except Exception:  # pragma: no cover – table missing in partial setups
            logger.debug("filesystem_scan_manifest not yet available; returning empty manifest")
            return {}
        return {row["path"]: (row["mtime"], row["size"]) for row in rows}

    # ------------------------------------------------------------------ #
    # Diff                                                                 #
    # ------------------------------------------------------------------ #

    async def diff_against(
        self, current: dict[str, tuple[float, int]]
    ) -> dict[str, list[Any]]:
        """Compare *current* filesystem snapshot against the stored manifest.

        Args:
            current: Mapping ``{path: (mtime, size)}`` representing what the
                     filesystem looks like *right now*.

        Returns:
            A dict with three keys:
            - ``added``   – paths present in *current* but not in the manifest.
            - ``removed`` – paths in the manifest that are absent from *current*.
            - ``changed`` – paths in both whose ``(mtime, size)`` differs.

            Each value is a sorted list of path strings.
        """
        stored = await self.fetch_manifest()

        stored_paths = set(stored)
        current_paths = set(current)

        added = sorted(current_paths - stored_paths)
        removed = sorted(stored_paths - current_paths)
        changed = sorted(
            path
            for path in stored_paths & current_paths
            if stored[path] != current[path]
        )

        return {"added": added, "removed": removed, "changed": changed}
