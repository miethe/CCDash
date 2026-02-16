"""SQLite implementation of FeatureRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


class SqliteFeatureRepository:
    """SQLite-backed feature storage with phases sub-table."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, feature_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(feature_data)

        await self.db.execute(
            """INSERT INTO features (
                id, project_id, name, status, category,
                total_tasks, completed_tasks, parent_feature_id,
                created_at, updated_at, completed_at, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, status=excluded.status,
                category=excluded.category,
                total_tasks=excluded.total_tasks,
                completed_tasks=excluded.completed_tasks,
                parent_feature_id=excluded.parent_feature_id,
                updated_at=excluded.updated_at,
                completed_at=excluded.completed_at,
                data_json=excluded.data_json
            """,
            (
                feature_data["id"], project_id,
                feature_data.get("name", ""),
                feature_data.get("status", "backlog"),
                feature_data.get("category", ""),
                feature_data.get("totalTasks", 0),
                feature_data.get("completedTasks", 0),
                feature_data.get("parentFeatureId"),
                feature_data.get("createdAt", now),
                now,
                feature_data.get("completedAt", ""),
                data_json,
            ),
        )
        await self.db.commit()

    async def get_by_id(self, feature_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM features WHERE id = ?", (feature_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM features WHERE project_id = ? ORDER BY name",
                (project_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM features ORDER BY name"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def upsert_phases(self, feature_id: str, phases: list[dict]) -> None:
        await self.db.execute("DELETE FROM feature_phases WHERE feature_id = ?", (feature_id,))
        for idx, p in enumerate(phases):
            # Generate ID if missing. Append index to ensure uniqueness since multiple phases
            # might share the same 'phase' value (e.g. 'all').
            phase_id = p.get("id")
            if not phase_id:
                phase_id = f"{feature_id}:phase-{str(p.get('phase', '0'))}-{idx}"

            await self.db.execute(
                """INSERT INTO feature_phases
                    (id, feature_id, phase, title, status, progress, total_tasks, completed_tasks)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    phase_id, feature_id,
                    str(p.get("phase", "")),
                    p.get("title", ""),
                    p.get("status", "backlog"),
                    p.get("progress", 0),
                    p.get("totalTasks", 0),
                    p.get("completedTasks", 0),
                ),
            )
        await self.db.commit()

    async def get_phases(self, feature_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM feature_phases WHERE feature_id = ? ORDER BY phase",
            (feature_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def delete(self, feature_id: str) -> None:
        await self.db.execute("DELETE FROM features WHERE id = ?", (feature_id,))
        await self.db.commit()

    async def get_project_stats(self, project_id: str) -> dict:
        """Get aggregated feature statistics."""
        query = """
            SELECT AVG(
                CASE WHEN total_tasks > 0
                     THEN CAST(completed_tasks AS REAL) / total_tasks * 100
                     ELSE 0
                END
            ) FROM features WHERE project_id = ?
        """
        async with self.db.execute(query, (project_id,)) as cur:
            row = await cur.fetchone()
            avg_progress = row[0] if row and row[0] is not None else 0.0
        return {"avg_progress": avg_progress}
