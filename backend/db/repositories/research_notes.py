"""SQLite implementation of ResearchNoteRepository (P5-013 MeatyWiki scaffold)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteResearchNoteRepository:
    """SQLite-backed MeatyWiki research note storage.

    Capability-gating is handled at the query-service level.  This repository
    reads and writes the ``research_notes`` table without flag checks.
    """

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
    ) -> list[dict[str, Any]]:
        """Return all research_notes rows for the given project+feature."""
        async with self.db.execute(
            """
            SELECT id, project_id, feature_id, title, url, body, source, created_at
            FROM research_notes
            WHERE project_id = ? AND feature_id = ?
            ORDER BY created_at ASC
            """,
            (str(project_id or ""), str(feature_id or "")),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a research note record."""
        now = _now_iso()
        row_id = str(data.get("id") or uuid.uuid4().hex)
        project_id = str(data.get("project_id") or "")
        feature_id = str(data.get("feature_id") or "")
        title = str(data.get("title") or "")
        url = str(data.get("url") or "")
        body = str(data.get("body") or "")
        source = str(data.get("source") or "")
        created_at = str(data.get("created_at") or now)

        await self.db.execute(
            """
            INSERT INTO research_notes (
                id, project_id, feature_id, title, url, body, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                url = excluded.url,
                body = excluded.body,
                source = excluded.source
            """,
            (row_id, project_id, feature_id, title, url, body, source, created_at),
        )
        await self.db.commit()
        return {
            "id": row_id,
            "project_id": project_id,
            "feature_id": feature_id,
            "title": title,
            "url": url,
            "body": body,
            "source": source,
            "created_at": created_at,
        }
