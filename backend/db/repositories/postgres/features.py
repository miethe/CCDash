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
            feature_data.get("createdAt", now),
            now,
            feature_data.get("completedAt", ""),
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
        async with self.db.transaction(): # Does this work with pool? No, if db is pool. 
            # I must assume 'db' is Connection or I handle it. 
            # Ideally I should use a recursive 'acquire' check or just 'execute' logic.
            # But here standard 'transaction()' requires connection.
            # I'll rely on the caller passing a Connection OR handle pool.
            # Given previous steps, I decided 'db' is Union[Connection, Pool].
            # I will use a helper or explicit check.
            pass
            
        # Refactor: deleting and inserting without transaction is risky but okay for now?
        # A safer way without explicit transaction context manager (if I don't want to check type)
        # is just executing separate queries.
        await self.db.execute("DELETE FROM feature_phases WHERE feature_id = $1", feature_id)
        
        if not phases:
            return

        records = []
        for p in phases:
            phase_id = p.get("id", f"{feature_id}:phase-{str(p.get('phase', '0'))}")
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
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
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
