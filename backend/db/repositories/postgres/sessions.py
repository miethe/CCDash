"""PostgreSQL implementation of SessionRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg
from backend.model_identity import model_filter_tokens

class PostgresSessionRepository:
    """PostgreSQL-backed session storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, session_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = session_data.get("createdAt", "") or now
        updated_at = session_data.get("updatedAt", "") or now
        # Postgres ON CONFLICT syntax is similar to SQLite
        query = """
            INSERT INTO sessions (
                id, project_id, task_id, status, model,
                duration_seconds, tokens_in, tokens_out, total_cost,
                quality_rating, friction_rating,
                git_commit_hash, git_commit_hashes_json, git_author, git_branch,
                session_type, parent_session_id, root_session_id, agent_id,
                started_at, ended_at, created_at, updated_at, source_file,
                dates_json, timeline_json, impact_history_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27)
            ON CONFLICT(id) DO UPDATE SET
                task_id=EXCLUDED.task_id, status=EXCLUDED.status, model=EXCLUDED.model,
                duration_seconds=EXCLUDED.duration_seconds,
                tokens_in=EXCLUDED.tokens_in, tokens_out=EXCLUDED.tokens_out,
                total_cost=EXCLUDED.total_cost,
                quality_rating=EXCLUDED.quality_rating, friction_rating=EXCLUDED.friction_rating,
                git_commit_hash=EXCLUDED.git_commit_hash,
                git_commit_hashes_json=EXCLUDED.git_commit_hashes_json,
                git_author=EXCLUDED.git_author,
                git_branch=EXCLUDED.git_branch,
                session_type=EXCLUDED.session_type,
                parent_session_id=EXCLUDED.parent_session_id,
                root_session_id=EXCLUDED.root_session_id,
                agent_id=EXCLUDED.agent_id,
                started_at=EXCLUDED.started_at, ended_at=EXCLUDED.ended_at,
                updated_at=EXCLUDED.updated_at, source_file=EXCLUDED.source_file,
                dates_json=EXCLUDED.dates_json,
                timeline_json=EXCLUDED.timeline_json,
                impact_history_json=EXCLUDED.impact_history_json
        """
        await self.db.execute(
            query,
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
            json.dumps(session_data.get("gitCommitHashes", []) or []),
            session_data.get("gitAuthor"),
            session_data.get("gitBranch"),
            session_data.get("sessionType", ""),
            session_data.get("parentSessionId"),
            session_data.get("rootSessionId", session_data.get("id", "")),
            session_data.get("agentId"),
            session_data.get("startedAt", ""),
            session_data.get("endedAt", ""),
            created_at, updated_at,
            session_data.get("sourceFile", ""),
            json.dumps(session_data.get("dates", {}) or {}),
            json.dumps(session_data.get("timeline", []) or []),
            json.dumps(session_data.get("impactHistory", []) or []),
        )

    async def get_by_id(self, session_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
        if not row:
            return None
        return dict(row)

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None,
        sort_by: str = "started_at", sort_order: str = "desc",
        filters: dict | None = None,
    ) -> list[dict]:
        allowed_sort = {"started_at", "total_cost", "duration_seconds", "tokens_in", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "started_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        where_parts: list[str] = []
        params: list[Any] = []
        idx = 1

        if project_id:
            where_parts.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1

        filters = filters or {}
        if filters.get("status"):
            where_parts.append(f"status = ${idx}")
            params.append(filters["status"])
            idx += 1
        if filters.get("model"):
            where_parts.append(f"model ILIKE ${idx}")
            params.append(f"%{filters['model']}%")
            idx += 1
        if filters.get("model_provider"):
            tokens = model_filter_tokens(str(filters["model_provider"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if filters.get("model_family"):
            tokens = model_filter_tokens(str(filters["model_family"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if filters.get("model_version"):
            tokens = model_filter_tokens(str(filters["model_version"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if not filters.get("include_subagents", False):
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("root_session_id"):
            where_parts.append(f"root_session_id = ${idx}")
            params.append(filters["root_session_id"])
            idx += 1
        if filters.get("start_date"):
            where_parts.append(f"started_at >= ${idx}")
            params.append(filters["start_date"])
            idx += 1
        if filters.get("end_date"):
            where_parts.append(f"started_at <= ${idx}")
            params.append(filters["end_date"])
            idx += 1
        if filters.get("created_start"):
            where_parts.append(f"created_at >= ${idx}")
            params.append(filters["created_start"])
            idx += 1
        if filters.get("created_end"):
            where_parts.append(f"created_at <= ${idx}")
            params.append(filters["created_end"])
            idx += 1
        if filters.get("completed_start"):
            where_parts.append(f"ended_at >= ${idx}")
            params.append(filters["completed_start"])
            idx += 1
        if filters.get("completed_end"):
            where_parts.append(f"ended_at <= ${idx}")
            params.append(filters["completed_end"])
            idx += 1
        if filters.get("updated_start"):
            where_parts.append(f"updated_at >= ${idx}")
            params.append(filters["updated_start"])
            idx += 1
        if filters.get("updated_end"):
            where_parts.append(f"updated_at <= ${idx}")
            params.append(filters["updated_end"])
            idx += 1
        if filters.get("min_duration") is not None:
            where_parts.append(f"duration_seconds >= ${idx}")
            params.append(filters["min_duration"])
            idx += 1
        if filters.get("max_duration") is not None:
            where_parts.append(f"duration_seconds <= ${idx}")
            params.append(filters["max_duration"])
            idx += 1

        where = ""
        if where_parts:
            where = " WHERE " + " AND ".join(where_parts)

        query = f"SELECT * FROM sessions{where} ORDER BY {sort_by} {order} LIMIT ${idx} OFFSET ${idx + 1}"
        params.extend([limit, offset])
        rows = await self.db.fetch(query, *params)
        
        return [dict(r) for r in rows]

    async def count(self, project_id: str | None = None, filters: dict | None = None) -> int:
        where_parts: list[str] = []
        params: list[Any] = []
        idx = 1

        if project_id:
            where_parts.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1

        filters = filters or {}
        if filters.get("status"):
            where_parts.append(f"status = ${idx}")
            params.append(filters["status"])
            idx += 1
        if filters.get("model"):
            where_parts.append(f"model ILIKE ${idx}")
            params.append(f"%{filters['model']}%")
            idx += 1
        if filters.get("model_provider"):
            tokens = model_filter_tokens(str(filters["model_provider"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if filters.get("model_family"):
            tokens = model_filter_tokens(str(filters["model_family"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if filters.get("model_version"):
            tokens = model_filter_tokens(str(filters["model_version"]))
            if tokens:
                for token in tokens:
                    where_parts.append(f"model ILIKE ${idx}")
                    params.append(f"%{token}%")
                    idx += 1
        if not filters.get("include_subagents", False):
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("root_session_id"):
            where_parts.append(f"root_session_id = ${idx}")
            params.append(filters["root_session_id"])
            idx += 1
        if filters.get("start_date"):
            where_parts.append(f"started_at >= ${idx}")
            params.append(filters["start_date"])
            idx += 1
        if filters.get("end_date"):
            where_parts.append(f"started_at <= ${idx}")
            params.append(filters["end_date"])
            idx += 1
        if filters.get("created_start"):
            where_parts.append(f"created_at >= ${idx}")
            params.append(filters["created_start"])
            idx += 1
        if filters.get("created_end"):
            where_parts.append(f"created_at <= ${idx}")
            params.append(filters["created_end"])
            idx += 1
        if filters.get("completed_start"):
            where_parts.append(f"ended_at >= ${idx}")
            params.append(filters["completed_start"])
            idx += 1
        if filters.get("completed_end"):
            where_parts.append(f"ended_at <= ${idx}")
            params.append(filters["completed_end"])
            idx += 1
        if filters.get("updated_start"):
            where_parts.append(f"updated_at >= ${idx}")
            params.append(filters["updated_start"])
            idx += 1
        if filters.get("updated_end"):
            where_parts.append(f"updated_at <= ${idx}")
            params.append(filters["updated_end"])
            idx += 1
        if filters.get("min_duration") is not None:
            where_parts.append(f"duration_seconds >= ${idx}")
            params.append(filters["min_duration"])
            idx += 1
        if filters.get("max_duration") is not None:
            where_parts.append(f"duration_seconds <= ${idx}")
            params.append(filters["max_duration"])
            idx += 1

        where = ""
        if where_parts:
            where = " WHERE " + " AND ".join(where_parts)
        val = await self.db.fetchval(f"SELECT COUNT(*) FROM sessions{where}", *params)
        return val or 0

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM sessions WHERE source_file = $1", source_file)

    # ── Detail tables ───────────────────────────────────────────────

    async def upsert_logs(self, session_id: str, logs: list[dict]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM session_logs WHERE session_id = $1", session_id)
            if not logs:
                return
                
            # Efficient batch insert could be used here (copy_records_to_table), but loop is safer for now
            # Actually asyncpg executemany is good.
            # But let's stick to loop to match logic for now, or use executemany with prepared statement.
            
            records = []
            for i, log in enumerate(logs):
                tc = log.get("toolCall")
                tool_name, tool_call_id, tool_args, tool_output, tool_status = None, None, None, None, "success"
                if tc and isinstance(tc, dict):
                    tool_name = tc.get("name")
                    tool_call_id = tc.get("id")
                    tool_args = tc.get("args")
                    tool_output = tc.get("output")
                    tool_status = tc.get("status", "success")
                metadata_json = None
                if isinstance(log.get("metadata"), dict) and log.get("metadata"):
                    metadata_json = json.dumps(log.get("metadata"))

                records.append((
                    session_id, i,
                    log.get("timestamp", ""),
                    log.get("speaker", ""),
                    log.get("type", ""),
                    log.get("content", ""),
                    log.get("agentName"),
                    tool_name, tool_call_id, log.get("relatedToolCallId"),
                    log.get("linkedSessionId"), tool_args, tool_output, tool_status, metadata_json,
                ))

            await self.db.executemany(
                """INSERT INTO session_logs
                    (session_id, log_index, timestamp, speaker, type, content,
                     agent_name, tool_name, tool_call_id, related_tool_call_id,
                     linked_session_id, tool_args, tool_output, tool_status, metadata_json)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)""",
                records
            )

    async def upsert_tool_usage(self, session_id: str, tools: list[dict]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM session_tool_usage WHERE session_id = $1", session_id)
            if not tools:
                return
            
            records = []
            for t in tools:
                records.append((
                    session_id, t.get("name", ""), t.get("count", 0),
                    int(t.get("count", 0) * t.get("successRate", 1.0)),
                    max(0, int(t.get("totalMs", 0) or 0)),
                ))
                
            await self.db.executemany(
                """INSERT INTO session_tool_usage (session_id, tool_name, call_count, success_count, total_ms)
                   VALUES ($1, $2, $3, $4, $5)""",
                records
            )

    async def upsert_file_updates(self, session_id: str, updates: list[dict]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM session_file_updates WHERE session_id = $1", session_id)
            if not updates:
                return

            records = []
            for u in updates:
                records.append((
                    session_id,
                    u.get("filePath", ""),
                    u.get("action", "update"),
                    u.get("fileType", "Other"),
                    u.get("timestamp", ""),
                    u.get("additions", 0),
                    u.get("deletions", 0),
                    u.get("agentName", ""),
                    u.get("threadSessionId", ""),
                    u.get("rootSessionId", ""),
                    u.get("sourceLogId"),
                    u.get("sourceToolName"),
                ))
            
            await self.db.executemany(
                """INSERT INTO session_file_updates (
                    session_id, file_path, action, file_type, action_timestamp,
                    additions, deletions, agent_name, thread_session_id, root_session_id,
                    source_log_id, source_tool_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                records
            )

    async def upsert_artifacts(self, session_id: str, artifacts: list[dict]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM session_artifacts WHERE session_id = $1", session_id)
            if not artifacts:
                return
                
            records = []
            for a in artifacts:
                records.append((
                   a.get("id", ""), session_id, a.get("title", ""),
                   a.get("type", "document"), a.get("description", ""), a.get("source", ""),
                   a.get("url"), a.get("sourceLogId"), a.get("sourceToolName"),
                ))

            await self.db.executemany(
                """INSERT INTO session_artifacts (
                    id, session_id, title, type, description, source, url, source_log_id, source_tool_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                records
            )

    async def get_logs(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM session_logs WHERE session_id = $1 ORDER BY log_index",
            session_id
        )
        return [dict(r) for r in rows]

    async def get_tool_usage(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM session_tool_usage WHERE session_id = $1",
            session_id
        )
        return [dict(r) for r in rows]

    async def get_file_updates(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM session_file_updates WHERE session_id = $1",
            session_id
        )
        return [dict(r) for r in rows]

    async def get_artifacts(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM session_artifacts WHERE session_id = $1",
            session_id
        )
        return [dict(r) for r in rows]

    async def get_project_stats(self, project_id: str) -> dict:
        query = """
            SELECT
                COUNT(*) as count,
                SUM(total_cost) as cost,
                SUM(tokens_in + tokens_out) as tokens,
                AVG(duration_seconds) as duration
            FROM sessions
            WHERE project_id = $1
        """
        row = await self.db.fetchrow(query, project_id)
        if row:
            return {
                "count": row["count"] or 0,
                "cost": row["cost"] or 0.0,
                "tokens": row["tokens"] or 0,
                "duration": row["duration"] or 0.0,
            }
        return {"count": 0, "cost": 0.0, "tokens": 0, "duration": 0.0}

    async def get_tool_stats(self, project_id: str) -> dict:
        query = """
            SELECT
                SUM(call_count) as calls,
                AVG(CAST(success_count AS DOUBLE PRECISION) / NULLIF(call_count, 0) * 100) as success_rate
            FROM session_tool_usage stu
            JOIN sessions s ON s.id = stu.session_id
            WHERE s.project_id = $1
        """
        row = await self.db.fetchrow(query, project_id)
        if row:
            return {
                "calls": row["calls"] or 0,
                "success_rate": row["success_rate"] if row["success_rate"] is not None else 0.0,
            }
        return {"calls": 0, "success_rate": 0.0}
