"""SQLite implementation of CouncilReviewRepository (P5-012 ARC scaffold)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteCouncilReviewRepository:
    """SQLite-backed ARC council review storage.

    All methods are capability-gated at the query-service level; this
    repository performs no flag checks — it simply reads/writes the table.
    """

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
    ) -> list[dict[str, Any]]:
        """Return all council_reviews rows for the given project+feature."""
        async with self.db.execute(
            """
            SELECT id, project_id, feature_id, status, summary, created_at, updated_at
            FROM council_reviews
            WHERE project_id = ? AND feature_id = ?
            ORDER BY created_at ASC
            """,
            (str(project_id or ""), str(feature_id or "")),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a council review record.

        Uses the provided ``id`` if present; otherwise generates a new UUID.
        """
        now = _now_iso()
        row_id = str(data.get("id") or uuid.uuid4().hex)
        project_id = str(data.get("project_id") or "")
        feature_id = str(data.get("feature_id") or "")
        status = str(data.get("status") or "pending")
        summary = str(data.get("summary") or "")
        created_at = str(data.get("created_at") or now)
        updated_at = now

        await self.db.execute(
            """
            INSERT INTO council_reviews (
                id, project_id, feature_id, status, summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                summary = excluded.summary,
                updated_at = excluded.updated_at
            """,
            (row_id, project_id, feature_id, status, summary, created_at, updated_at),
        )
        await self.db.commit()
        return {
            "id": row_id,
            "project_id": project_id,
            "feature_id": feature_id,
            "status": status,
            "summary": summary,
            "created_at": created_at,
            "updated_at": updated_at,
        }
