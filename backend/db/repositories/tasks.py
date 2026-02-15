"""SQLite implementation of TaskRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


class SqliteTaskRepository:
    """SQLite-backed task storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, task_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(task_data)

        await self.db.execute(
            """INSERT INTO tasks (
                id, project_id, title, description, status, priority,
                owner, last_agent, cost,
                task_type, project_type, project_level,
                parent_task_id, feature_id, phase_id,
                session_id, commit_hash,
                created_at, updated_at, completed_at,
                source_file, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, description=excluded.description,
                status=excluded.status, priority=excluded.priority,
                owner=excluded.owner, last_agent=excluded.last_agent,
                cost=excluded.cost,
                task_type=excluded.task_type, project_type=excluded.project_type,
                project_level=excluded.project_level,
                parent_task_id=excluded.parent_task_id,
                feature_id=excluded.feature_id, phase_id=excluded.phase_id,
                session_id=excluded.session_id, commit_hash=excluded.commit_hash,
                updated_at=excluded.updated_at, completed_at=excluded.completed_at,
                source_file=excluded.source_file, data_json=excluded.data_json
            """,
            (
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
            ),
        )
        await self.db.commit()

    async def get_by_id(self, task_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def list_by_feature(self, feature_id: str, phase_id: str | None = None) -> list[dict]:
        if phase_id:
            async with self.db.execute(
                "SELECT * FROM tasks WHERE feature_id = ? AND phase_id = ? ORDER BY id",
                (feature_id, phase_id),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM tasks WHERE feature_id = ? ORDER BY phase_id, id",
                (feature_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM tasks WHERE source_file = ?", (source_file,))
        await self.db.commit()
