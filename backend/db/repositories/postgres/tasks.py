"""PostgreSQL implementation of TaskRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import asyncpg

class PostgresTaskRepository:
    """PostgreSQL-backed task storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, task_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(task_data)

        query = """
            INSERT INTO tasks (
                id, project_id, title, description, status, priority,
                owner, last_agent, cost,
                task_type, project_type, project_level,
                parent_task_id, feature_id, phase_id,
                session_id, commit_hash,
                created_at, updated_at, completed_at,
                source_file, data_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
            ON CONFLICT(id) DO UPDATE SET
                title=EXCLUDED.title, description=EXCLUDED.description,
                status=EXCLUDED.status, priority=EXCLUDED.priority,
                owner=EXCLUDED.owner, last_agent=EXCLUDED.last_agent,
                cost=EXCLUDED.cost,
                task_type=EXCLUDED.task_type, project_type=EXCLUDED.project_type,
                project_level=EXCLUDED.project_level,
                parent_task_id=EXCLUDED.parent_task_id,
                feature_id=EXCLUDED.feature_id, phase_id=EXCLUDED.phase_id,
                session_id=EXCLUDED.session_id, commit_hash=EXCLUDED.commit_hash,
                updated_at=EXCLUDED.updated_at, completed_at=EXCLUDED.completed_at,
                source_file=EXCLUDED.source_file, data_json=EXCLUDED.data_json
        """
        await self.db.execute(
            query,
            task_data["id"], project_id,
            task_data.get("title", ""),
            task_data.get("description", ""),
            task_data.get("status", "backlog"),
            task_data.get("priority", "medium"),
            task_data.get("owner", ""),
            task_data.get("lastAgent", ""),
            task_data.get("cost", 0.0),
            task_data.get("taskType", ""),
            task_data.get("projectType", ""),
            task_data.get("projectLevel", ""),
            task_data.get("parentTaskId"),
            task_data.get("featureId"),
            task_data.get("phaseId"),
            task_data.get("sessionId", ""),
            task_data.get("commitHash", ""),
            task_data.get("createdAt", now),
            now,
            task_data.get("completedAt", ""),
            task_data.get("sourceFile", ""),
            data_json,
        )

    async def get_by_id(self, task_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM tasks WHERE project_id = $1 ORDER BY updated_at DESC",
                project_id,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM tasks ORDER BY updated_at DESC")
        return [dict(r) for r in rows]

    async def list_by_feature(self, feature_id: str, phase_id: str | None = None) -> list[dict]:
        if phase_id:
            rows = await self.db.fetch(
                "SELECT * FROM tasks WHERE feature_id = $1 AND phase_id = $2 ORDER BY id",
                feature_id, phase_id,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM tasks WHERE feature_id = $1 ORDER BY phase_id, id",
                feature_id,
            )
        return [dict(r) for r in rows]

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM tasks WHERE source_file = $1", source_file)

    async def get_project_stats(self, project_id: str) -> dict:
        completed = await self.db.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE project_id = $1 AND lower(status) IN ('done', 'deferred', 'completed')",
            project_id
        ) or 0

        pct = await self.db.fetchval(
            """
            SELECT
                CAST(SUM(CASE WHEN lower(status) IN ('done', 'deferred', 'completed') THEN 1 ELSE 0 END) AS DOUBLE PRECISION)
                / NULLIF(COUNT(*), 0) * 100
            FROM tasks
            WHERE project_id = $1
            """,
            project_id
        ) or 0.0

        return {"completed": completed, "completion_pct": pct}
