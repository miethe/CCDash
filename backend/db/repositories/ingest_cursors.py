"""Concrete IngestCursorRepository implementations for SQLite and PostgreSQL.

Tracks the ingest watermark per (source_id, project_id, workspace_id) triplet.
See ADR-009 for the full cursor-model rationale.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.application.ports.ingest import IngestCursor


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_cursor(row: Any) -> IngestCursor:
    return IngestCursor(
        source_id=row["source_id"],
        project_id=row["project_id"],
        workspace_id=row["workspace_id"],
        last_cursor=row["last_cursor"],
        last_ingest_at=row["last_ingest_at"],
        error_count=row["error_count"],
        last_error=row["last_error"],
        last_error_at=row["last_error_at"],
    )


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteIngestCursorRepository:
    """aiosqlite-backed implementation of IngestCursorRepository."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def get_or_create(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str = "default",
    ) -> IngestCursor:
        async with self.db.execute(
            """
            SELECT source_id, project_id, workspace_id,
                   last_cursor, last_ingest_at,
                   error_count, last_error, last_error_at
            FROM ingest_cursors
            WHERE source_id = ? AND project_id = ? AND workspace_id = ?
            """,
            (source_id, project_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()

        if row is not None:
            return _row_to_cursor(row)

        await self.db.execute(
            """
            INSERT OR IGNORE INTO ingest_cursors
                (source_id, project_id, workspace_id,
                 last_cursor, last_ingest_at, error_count,
                 last_error, last_error_at)
            VALUES (?, ?, ?, NULL, NULL, 0, NULL, NULL)
            """,
            (source_id, project_id, workspace_id),
        )
        await self.db.commit()

        async with self.db.execute(
            """
            SELECT source_id, project_id, workspace_id,
                   last_cursor, last_ingest_at,
                   error_count, last_error, last_error_at
            FROM ingest_cursors
            WHERE source_id = ? AND project_id = ? AND workspace_id = ?
            """,
            (source_id, project_id, workspace_id),
        ) as cur:
            row = await cur.fetchone()

        assert row is not None, "ingest_cursors INSERT OR IGNORE failed unexpectedly"
        return _row_to_cursor(row)

    async def advance(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str,
        cursor_value: str,
        occurred_at: str,
    ) -> None:
        await self.db.execute(
            """
            UPDATE ingest_cursors
            SET last_cursor    = ?,
                last_ingest_at = ?,
                error_count    = 0,
                last_error     = NULL,
                last_error_at  = NULL
            WHERE source_id = ? AND project_id = ? AND workspace_id = ?
            """,
            (cursor_value, occurred_at, source_id, project_id, workspace_id),
        )
        await self.db.commit()

    async def record_error(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str,
        error_message: str,
    ) -> None:
        await self.db.execute(
            """
            UPDATE ingest_cursors
            SET error_count   = error_count + 1,
                last_error    = ?,
                last_error_at = ?
            WHERE source_id = ? AND project_id = ? AND workspace_id = ?
            """,
            (error_message, _now_iso(), source_id, project_id, workspace_id),
        )
        await self.db.commit()


# ── PostgreSQL ──────────────────────────────────────────────────────────────


class PostgresIngestCursorRepository:
    """asyncpg-backed implementation of IngestCursorRepository."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def get_or_create(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str = "default",
    ) -> IngestCursor:
        row = await self.db.fetchrow(
            """
            SELECT source_id, project_id, workspace_id,
                   last_cursor, last_ingest_at,
                   error_count, last_error, last_error_at
            FROM ingest_cursors
            WHERE source_id = $1 AND project_id = $2 AND workspace_id = $3
            """,
            source_id,
            project_id,
            workspace_id,
        )
        if row is not None:
            return _row_to_cursor(row)

        await self.db.execute(
            """
            INSERT INTO ingest_cursors
                (source_id, project_id, workspace_id,
                 last_cursor, last_ingest_at, error_count,
                 last_error, last_error_at)
            VALUES ($1, $2, $3, NULL, NULL, 0, NULL, NULL)
            ON CONFLICT (source_id, project_id, workspace_id) DO NOTHING
            """,
            source_id,
            project_id,
            workspace_id,
        )

        row = await self.db.fetchrow(
            """
            SELECT source_id, project_id, workspace_id,
                   last_cursor, last_ingest_at,
                   error_count, last_error, last_error_at
            FROM ingest_cursors
            WHERE source_id = $1 AND project_id = $2 AND workspace_id = $3
            """,
            source_id,
            project_id,
            workspace_id,
        )
        assert row is not None, "ingest_cursors INSERT ON CONFLICT DO NOTHING failed unexpectedly"
        return _row_to_cursor(row)

    async def advance(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str,
        cursor_value: str,
        occurred_at: str,
    ) -> None:
        await self.db.execute(
            """
            UPDATE ingest_cursors
            SET last_cursor    = $1,
                last_ingest_at = $2,
                error_count    = 0,
                last_error     = NULL,
                last_error_at  = NULL
            WHERE source_id = $3 AND project_id = $4 AND workspace_id = $5
            """,
            cursor_value,
            occurred_at,
            source_id,
            project_id,
            workspace_id,
        )

    async def record_error(
        self,
        *,
        source_id: str,
        project_id: str,
        workspace_id: str,
        error_message: str,
    ) -> None:
        await self.db.execute(
            """
            UPDATE ingest_cursors
            SET error_count   = error_count + 1,
                last_error    = $1,
                last_error_at = $2
            WHERE source_id = $3 AND project_id = $4 AND workspace_id = $5
            """,
            error_message,
            _now_iso(),
            source_id,
            project_id,
            workspace_id,
        )  # args: (error_message, now_iso, source_id, project_id, workspace_id)


__all__ = [
    "SqliteIngestCursorRepository",
    "PostgresIngestCursorRepository",
]
