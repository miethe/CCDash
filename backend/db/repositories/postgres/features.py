"""PostgreSQL implementation of FeatureRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import asyncpg

class PostgresFeatureRepository:
    """PostgreSQL-backed feature storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, feature_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = feature_data.get("createdAt", "") or now
        updated_at = feature_data.get("updatedAt", "") or now
        completed_at = feature_data.get("completedAt", "")
        data_json = json.dumps(feature_data)

        query = """
            INSERT INTO features (
                id, project_id, name, status, category,
                total_tasks, completed_tasks, parent_feature_id,
                created_at, updated_at, completed_at, data_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT(id) DO UPDATE SET
                name=EXCLUDED.name, status=EXCLUDED.status,
                category=EXCLUDED.category,
                total_tasks=EXCLUDED.total_tasks,
                completed_tasks=EXCLUDED.completed_tasks,
                parent_feature_id=EXCLUDED.parent_feature_id,
                updated_at=EXCLUDED.updated_at,
                completed_at=EXCLUDED.completed_at,
                data_json=EXCLUDED.data_json
        """
        await self.db.execute(
            query,
            feature_data["id"], project_id,
            feature_data.get("name", ""),
            feature_data.get("status", "backlog"),
            feature_data.get("category", ""),
            feature_data.get("totalTasks", 0),
            feature_data.get("completedTasks", 0),
            feature_data.get("parentFeatureId"),
            created_at,
            updated_at,
            completed_at,
            data_json,
        )

    async def get_by_id(self, feature_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM features WHERE id = $1", feature_id)
        return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM features WHERE project_id = $1 ORDER BY name",
                project_id,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM features ORDER BY name")
        return [dict(r) for r in rows]

    async def upsert_phases(self, feature_id: str, phases: list[dict]) -> None:
        await self.db.execute("DELETE FROM feature_phases WHERE feature_id = $1", feature_id)

        if not phases:
            return

        records = []
        for idx, p in enumerate(phases):
            phase_id = p.get("id")
            if not phase_id:
                phase_id = f"{feature_id}:phase-{str(p.get('phase', '0'))}-{idx}"
            records.append((
                phase_id, feature_id,
                str(p.get("phase", "")),
                p.get("title", ""),
                p.get("status", "backlog"),
                p.get("progress", 0),
                p.get("totalTasks", 0),
                p.get("completedTasks", 0),
            ))

        await self.db.executemany(
            """INSERT INTO feature_phases
                (id, feature_id, phase, title, status, progress, total_tasks, completed_tasks)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT(id) DO UPDATE SET
                   feature_id=EXCLUDED.feature_id,
                   phase=EXCLUDED.phase,
                   title=EXCLUDED.title,
                   status=EXCLUDED.status,
                   progress=EXCLUDED.progress,
                   total_tasks=EXCLUDED.total_tasks,
                   completed_tasks=EXCLUDED.completed_tasks
            """,
            records
        )

    async def get_phases(self, feature_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM feature_phases WHERE feature_id = $1 ORDER BY phase",
            feature_id,
        )
        return [dict(r) for r in rows]

    async def delete(self, feature_id: str) -> None:
        await self.db.execute("DELETE FROM features WHERE id = $1", feature_id)

    async def get_project_stats(self, project_id: str) -> dict:
        query = """
            SELECT AVG(
                CASE WHEN total_tasks > 0
                     THEN CAST(completed_tasks AS DOUBLE PRECISION) / total_tasks * 100
                     ELSE 0
                END
            ) FROM features WHERE project_id = $1
        """
        val = await self.db.fetchval(query, project_id)
        return {"avg_progress": val or 0.0}
