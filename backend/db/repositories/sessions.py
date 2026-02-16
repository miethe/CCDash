"""SQLite implementation of SessionRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


class SqliteSessionRepository:
    """SQLite-backed session storage with normalized detail tables."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, session_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO sessions (
                id, project_id, task_id, status, model,
                duration_seconds, tokens_in, tokens_out, total_cost,
                quality_rating, friction_rating,
                git_commit_hash, git_author, git_branch,
                session_type, parent_session_id,
                started_at, ended_at, created_at, updated_at, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                task_id=excluded.task_id, status=excluded.status, model=excluded.model,
                duration_seconds=excluded.duration_seconds,
                tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out,
                total_cost=excluded.total_cost,
                quality_rating=excluded.quality_rating, friction_rating=excluded.friction_rating,
                git_commit_hash=excluded.git_commit_hash, git_author=excluded.git_author,
                git_branch=excluded.git_branch,
                session_type=excluded.session_type,
                parent_session_id=excluded.parent_session_id,
                started_at=excluded.started_at, ended_at=excluded.ended_at,
                updated_at=excluded.updated_at, source_file=excluded.source_file
            """,
            (
                session_data["id"], project_id,
                session_data.get("taskId", ""),
                session_data.get("status", "completed"),
                session_data.get("model", ""),
                session_data.get("durationSeconds", 0),
                session_data.get("tokensIn", 0),
                session_data.get("tokensOut", 0),
                session_data.get("totalCost", 0.0),
                session_data.get("qualityRating", 0),
                session_data.get("frictionRating", 0),
                session_data.get("gitCommitHash"),
                session_data.get("gitAuthor"),
                session_data.get("gitBranch"),
                session_data.get("sessionType", ""),
                session_data.get("parentSessionId"),
                session_data.get("startedAt", ""),
                session_data.get("endedAt", ""),
                now, now,
                session_data.get("sourceFile", ""),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, session_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None,
        sort_by: str = "started_at", sort_order: str = "desc",
    ) -> list[dict]:
        # Whitelist sortable columns
        allowed_sort = {"started_at", "total_cost", "duration_seconds", "tokens_in", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "started_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        if project_id:
            query = f"SELECT * FROM sessions WHERE project_id = ? ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
            params = (project_id, limit, offset)
        else:
            query = f"SELECT * FROM sessions ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
            params = (limit, offset)

        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [self._row_to_dict(r) for r in rows]

    async def count(self, project_id: str | None = None) -> int:
        if project_id:
            async with self.db.execute(
                "SELECT COUNT(*) FROM sessions WHERE project_id = ?", (project_id,)
            ) as cur:
                row = await cur.fetchone()
        else:
            async with self.db.execute("SELECT COUNT(*) FROM sessions") as cur:
                row = await cur.fetchone()
        return row[0] if row else 0

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM sessions WHERE source_file = ?", (source_file,))
        await self.db.commit()

    # ── Detail tables ───────────────────────────────────────────────

    async def upsert_logs(self, session_id: str, logs: list[dict]) -> None:
        await self.db.execute("DELETE FROM session_logs WHERE session_id = ?", (session_id,))
        for i, log in enumerate(logs):
            tool_name = None
            tool_args = None
            tool_output = None
            tool_status = "success"
            tc = log.get("toolCall")
            if tc and isinstance(tc, dict):
                tool_name = tc.get("name")
                tool_args = tc.get("args")
                tool_output = tc.get("output")
                tool_status = tc.get("status", "success")

            await self.db.execute(
                """INSERT INTO session_logs
                    (session_id, log_index, timestamp, speaker, type, content,
                     agent_name, tool_name, tool_args, tool_output, tool_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, i,
                    log.get("timestamp", ""),
                    log.get("speaker", ""),
                    log.get("type", ""),
                    log.get("content", ""),
                    log.get("agentName"),
                    tool_name, tool_args, tool_output, tool_status,
                ),
            )
        await self.db.commit()

    async def upsert_tool_usage(self, session_id: str, tools: list[dict]) -> None:
        await self.db.execute("DELETE FROM session_tool_usage WHERE session_id = ?", (session_id,))
        for t in tools:
            await self.db.execute(
                """INSERT INTO session_tool_usage (session_id, tool_name, call_count, success_count)
                   VALUES (?, ?, ?, ?)""",
                (session_id, t.get("name", ""), t.get("count", 0),
                 int(t.get("count", 0) * t.get("successRate", 1.0))),
            )
        await self.db.commit()

    async def upsert_file_updates(self, session_id: str, updates: list[dict]) -> None:
        await self.db.execute("DELETE FROM session_file_updates WHERE session_id = ?", (session_id,))
        for u in updates:
            await self.db.execute(
                """INSERT INTO session_file_updates (session_id, file_path, additions, deletions, agent_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, u.get("filePath", ""), u.get("additions", 0),
                 u.get("deletions", 0), u.get("agentName", "")),
            )
        await self.db.commit()

    async def upsert_artifacts(self, session_id: str, artifacts: list[dict]) -> None:
        await self.db.execute("DELETE FROM session_artifacts WHERE session_id = ?", (session_id,))
        for a in artifacts:
            await self.db.execute(
                """INSERT INTO session_artifacts (id, session_id, title, type, description, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (a.get("id", ""), session_id, a.get("title", ""),
                 a.get("type", "document"), a.get("description", ""), a.get("source", "")),
            )
        await self.db.commit()

    async def get_logs(self, session_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM session_logs WHERE session_id = ? ORDER BY log_index",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_tool_usage(self, session_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM session_tool_usage WHERE session_id = ?",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_file_updates(self, session_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM session_file_updates WHERE session_id = ?",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_artifacts(self, session_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM session_artifacts WHERE session_id = ?", (session_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_project_stats(self, project_id: str) -> dict:
        """Get aggregated session statistics for a project."""
        query = """
            SELECT
                COUNT(*) as count,
                SUM(total_cost) as cost,
                SUM(tokens_in + tokens_out) as tokens,
                AVG(duration_seconds) as duration
            FROM sessions
            WHERE project_id = ?
        """
        async with self.db.execute(query, (project_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "count": row[0] or 0,
                    "cost": row[1] or 0.0,
                    "tokens": row[2] or 0,
                    "duration": row[3] or 0.0,
                }
            return {"count": 0, "cost": 0.0, "tokens": 0, "duration": 0.0}

    async def get_tool_stats(self, project_id: str) -> dict:
        """Get aggregated tool usage statistics for a project."""
        query = """
            SELECT
                SUM(call_count),
                AVG(CAST(success_count AS REAL) / NULLIF(call_count, 0) * 100)
            FROM session_tool_usage stu
            JOIN sessions s ON s.id = stu.session_id
            WHERE s.project_id = ?
        """
        async with self.db.execute(query, (project_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "calls": row[0] or 0,
                    "success_rate": row[1] if row[1] is not None else 0.0,
                }
            return {"calls": 0, "success_rate": 0.0}

    def _row_to_dict(self, row) -> dict:
        return dict(row)
