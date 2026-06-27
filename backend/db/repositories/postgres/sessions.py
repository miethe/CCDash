"""PostgreSQL implementation of SessionRepository."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg
from backend.model_identity import model_filter_tokens
from backend.db.repositories.postgres._transactions import postgres_transaction

logger = logging.getLogger("ccdash.db.postgres.sessions")

class PostgresSessionRepository:
    """PostgreSQL-backed session storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, session_data: dict, project_id: str, _pg_conn: Any = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = session_data.get("createdAt", "") or now
        updated_at = session_data.get("updatedAt", "") or now
        # Postgres ON CONFLICT syntax is similar to SQLite
        query = """
            INSERT INTO sessions (
                id, project_id, task_id, status, model,
                platform_type, platform_version, platform_versions_json, platform_version_transitions_json,
                duration_seconds, tokens_in, tokens_out, model_io_tokens,
                cache_creation_input_tokens, cache_read_input_tokens, cache_input_tokens, observed_tokens,
                tool_reported_tokens, tool_result_input_tokens, tool_result_output_tokens,
                tool_result_cache_creation_input_tokens, tool_result_cache_read_input_tokens, total_cost,
                quality_rating, friction_rating,
                git_commit_hash, git_commit_hashes_json, git_author, git_branch,
                session_type, parent_session_id, root_session_id, agent_id,
                thread_kind, conversation_family_id, context_inheritance,
                fork_parent_session_id, fork_point_log_id, fork_point_entry_uuid, fork_point_parent_entry_uuid, fork_depth, fork_count,
                started_at, ended_at, created_at, updated_at, source_file,
                dates_json, timeline_json, impact_history_json,
                thinking_level, session_forensics_json,
                model_slug, workflow_id, subagent_parent_id, skill_name, context_window,
                launcher, profile, effort_tier, model_variant
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41, $42, $43, $44, $45, $46, $47, $48, $49, $50, $51, $52, $53, $54, $55, $56, $57, $58, $59, $60, $61)
            ON CONFLICT(project_id, id) DO UPDATE SET
                task_id=EXCLUDED.task_id, status=EXCLUDED.status, model=EXCLUDED.model,
                platform_type=EXCLUDED.platform_type,
                platform_version=EXCLUDED.platform_version,
                platform_versions_json=EXCLUDED.platform_versions_json,
                platform_version_transitions_json=EXCLUDED.platform_version_transitions_json,
                duration_seconds=EXCLUDED.duration_seconds,
                tokens_in=EXCLUDED.tokens_in, tokens_out=EXCLUDED.tokens_out,
                model_io_tokens=EXCLUDED.model_io_tokens,
                cache_creation_input_tokens=EXCLUDED.cache_creation_input_tokens,
                cache_read_input_tokens=EXCLUDED.cache_read_input_tokens,
                cache_input_tokens=EXCLUDED.cache_input_tokens,
                observed_tokens=EXCLUDED.observed_tokens,
                tool_reported_tokens=EXCLUDED.tool_reported_tokens,
                tool_result_input_tokens=EXCLUDED.tool_result_input_tokens,
                tool_result_output_tokens=EXCLUDED.tool_result_output_tokens,
                tool_result_cache_creation_input_tokens=EXCLUDED.tool_result_cache_creation_input_tokens,
                tool_result_cache_read_input_tokens=EXCLUDED.tool_result_cache_read_input_tokens,
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
                thread_kind=EXCLUDED.thread_kind,
                conversation_family_id=EXCLUDED.conversation_family_id,
                context_inheritance=EXCLUDED.context_inheritance,
                fork_parent_session_id=EXCLUDED.fork_parent_session_id,
                fork_point_log_id=EXCLUDED.fork_point_log_id,
                fork_point_entry_uuid=EXCLUDED.fork_point_entry_uuid,
                fork_point_parent_entry_uuid=EXCLUDED.fork_point_parent_entry_uuid,
                fork_depth=EXCLUDED.fork_depth,
                fork_count=EXCLUDED.fork_count,
                started_at=EXCLUDED.started_at, ended_at=EXCLUDED.ended_at,
                updated_at=EXCLUDED.updated_at, source_file=EXCLUDED.source_file,
                dates_json=EXCLUDED.dates_json,
                timeline_json=EXCLUDED.timeline_json,
                impact_history_json=EXCLUDED.impact_history_json,
                thinking_level=EXCLUDED.thinking_level,
                session_forensics_json=EXCLUDED.session_forensics_json,
                -- Phase 5 detection columns (T5-006).
                model_slug=CASE WHEN EXCLUDED.model_slug != '' THEN EXCLUDED.model_slug ELSE sessions.model_slug END,
                workflow_id=EXCLUDED.workflow_id,
                subagent_parent_id=EXCLUDED.subagent_parent_id,
                skill_name=EXCLUDED.skill_name,
                -- context_window comes from the sidecar join (T5-003); never wipe a
                -- prior attribution when the sidecar is transiently absent.
                context_window=COALESCE(EXCLUDED.context_window, sessions.context_window),
                -- Phase 11 launch-time capture columns (T11-003). All four are
                -- capture-once: a re-ingest with a null value must never clobber a
                -- previously-captured value (idempotency, AC-11.C).
                launcher=COALESCE(EXCLUDED.launcher, sessions.launcher),
                profile=COALESCE(EXCLUDED.profile, sessions.profile),
                effort_tier=COALESCE(EXCLUDED.effort_tier, sessions.effort_tier),
                model_variant=COALESCE(EXCLUDED.model_variant, sessions.model_variant)
        """
        _conn = _pg_conn if _pg_conn is not None else self.db
        await _conn.execute(
            query,
            session_data["id"], project_id,
            session_data.get("taskId", ""),
            session_data.get("status", "completed"),
            session_data.get("model", ""),
            session_data.get("platformType", "Claude Code"),
            session_data.get("platformVersion", ""),
            json.dumps(session_data.get("platformVersions", []) or []),
            json.dumps(session_data.get("platformVersionTransitions", []) or []),
            session_data.get("durationSeconds", 0),
            session_data.get("tokensIn", 0),
            session_data.get("tokensOut", 0),
            session_data.get("modelIOTokens", 0),
            session_data.get("cacheCreationInputTokens", 0),
            session_data.get("cacheReadInputTokens", 0),
            session_data.get("cacheInputTokens", 0),
            session_data.get("observedTokens", 0),
            session_data.get("toolReportedTokens", 0),
            session_data.get("toolResultInputTokens", 0),
            session_data.get("toolResultOutputTokens", 0),
            session_data.get("toolResultCacheCreationInputTokens", 0),
            session_data.get("toolResultCacheReadInputTokens", 0),
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
            str(session_data.get("threadKind", "") or ""),
            str(session_data.get("conversationFamilyId", "") or ""),
            str(session_data.get("contextInheritance", "") or ""),
            session_data.get("forkParentSessionId"),
            session_data.get("forkPointLogId"),
            session_data.get("forkPointEntryUuid"),
            session_data.get("forkPointParentEntryUuid"),
            int(session_data.get("forkDepth", 0) or 0),
            int(session_data.get("forkCount", 0) or 0),
            session_data.get("startedAt", ""),
            session_data.get("endedAt", ""),
            created_at, updated_at,
            session_data.get("sourceFile", ""),
            json.dumps(session_data.get("dates", {}) or {}),
            json.dumps(session_data.get("timeline", []) or []),
            json.dumps(session_data.get("impactHistory", []) or []),
            str(session_data.get("thinkingLevel", "") or ""),
            json.dumps(session_data.get("sessionForensics", {}) or {}),
            # Phase 5 detection columns (T5-006).
            str(session_data.get("modelSlug", "") or ""),
            session_data.get("workflowId"),
            session_data.get("subagentParentId"),
            session_data.get("skillName"),
            session_data.get("contextWindow"),
            # Phase 11 launch-time capture columns (T11-003). All nullable;
            # null == "not captured" (contract state, no default, no backfill).
            session_data.get("launcher"),
            session_data.get("profile"),
            session_data.get("effortTier"),
            session_data.get("modelVariant"),
        )

    async def get_by_id(self, session_id: str, project_id: str | None = None) -> dict | None:
        """Fetch a single session by id.

        Mirrors the SQLite backend (``backend/db/repositories/sessions.py``) with
        identical predicate semantics: a non-empty ``project_id`` adds a strict
        equality predicate alongside ``id`` (composite PK ``(project_id, id)``);
        ``None``/``''`` leaves the read unscoped (active-project hot path unchanged).
        """
        if project_id:
            row = await self.db.fetchrow(
                "SELECT * FROM sessions WHERE project_id = $1 AND id = $2",
                project_id,
                session_id,
            )
        else:
            row = await self.db.fetchrow(
                "SELECT * FROM sessions WHERE id = $1", session_id
            )
        if not row:
            return None
        return dict(row)

    async def get_many_by_ids(
        self, ids: list[str], project_id: str | None = None
    ) -> dict[str, dict]:
        """Fetch multiple sessions in a single query. Returns a dict keyed by session id.

        ``project_id`` follows the same semantics as :meth:`get_by_id` and mirrors
        the SQLite backend predicate exactly (Risk Hotspot: backend drift).
        """
        if not ids:
            return {}
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM sessions WHERE project_id = $1 AND id = ANY($2::text[])",
                project_id,
                ids,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM sessions WHERE id = ANY($1::text[])", ids
            )
        return {row["id"]: dict(row) for row in rows}

    async def list_by_source(self, source_file: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM sessions WHERE source_file = $1",
            source_file,
        )
        return [dict(row) for row in rows]

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
        if filters.get("platform_type"):
            where_parts.append(f"LOWER(COALESCE(NULLIF(TRIM(platform_type), ''), 'Claude Code')) = LOWER(${idx})")
            params.append(str(filters["platform_type"]))
            idx += 1
        if filters.get("platform_version"):
            version = str(filters["platform_version"]).strip()
            if version:
                where_parts.append(f"(platform_version = ${idx} OR platform_versions_json ILIKE ${idx + 1})")
                params.append(version)
                params.append(f'%"{version}"%')
                idx += 2
        if not filters.get("include_subagents", False):
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("thread_kind"):
            where_parts.append(f"LOWER(COALESCE(thread_kind, '')) = LOWER(${idx})")
            params.append(str(filters["thread_kind"]))
            idx += 1
        if filters.get("conversation_family_id"):
            where_parts.append(f"conversation_family_id = ${idx}")
            params.append(str(filters["conversation_family_id"]))
            idx += 1
        if filters.get("task_id"):
            where_parts.append(f"task_id = ${idx}")
            params.append(str(filters["task_id"]))
            idx += 1
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
        if filters.get("platform_type"):
            where_parts.append(f"LOWER(COALESCE(NULLIF(TRIM(platform_type), ''), 'Claude Code')) = LOWER(${idx})")
            params.append(str(filters["platform_type"]))
            idx += 1
        if filters.get("platform_version"):
            version = str(filters["platform_version"]).strip()
            if version:
                where_parts.append(f"(platform_version = ${idx} OR platform_versions_json ILIKE ${idx + 1})")
                params.append(version)
                params.append(f'%"{version}"%')
                idx += 2
        if not filters.get("include_subagents", False):
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("thread_kind"):
            where_parts.append(f"LOWER(COALESCE(thread_kind, '')) = LOWER(${idx})")
            params.append(str(filters["thread_kind"]))
            idx += 1
        if filters.get("conversation_family_id"):
            where_parts.append(f"conversation_family_id = ${idx}")
            params.append(str(filters["conversation_family_id"]))
            idx += 1
        if filters.get("task_id"):
            where_parts.append(f"task_id = ${idx}")
            params.append(str(filters["task_id"]))
            idx += 1
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

    async def count_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        include_subagents: bool = False,
    ) -> int:
        """Count sessions that are currently active for a project.

        See ``SqliteSessionRepository.count_active`` for full docstring including
        the dual role of the freshness clamp and the stale-active defence.

        The default ``window_seconds=600`` matches ``_ACTIVE_SESSION_WINDOW_SECONDS``
        in the parsers but serves a different purpose (read-time filter, not
        parser classification).

        Args:
            project_id: The project to scope the count to.
            window_seconds: Freshness window in seconds (default 600 = 10 min).
            include_subagents: If ``False`` (default), excludes subagent rows.

        Returns:
            Integer count of currently-active sessions within the window.
        """
        from datetime import datetime, timedelta, timezone

        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        where_parts = [
            "project_id = $1",
            "status = $2",
            "updated_at >= $3",
        ]
        params: list[Any] = [project_id, "active", threshold]

        if not include_subagents:
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")

        where = " WHERE " + " AND ".join(where_parts)
        val = await self.db.fetchval(
            f"SELECT COUNT(*) FROM sessions{where}",  # noqa: S608
            *params,
        )
        return int(val or 0)

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit: int | None = None,
        include_subagents: bool = True,
    ) -> list[dict]:
        """List sessions that are currently active for a project.

        Mirrors ``SqliteSessionRepository.list_active`` exactly — same predicate
        semantics (``status = 'active'`` + ``updated_at >= threshold``), same
        ordering (``updated_at DESC``), same ``include_subagents`` behaviour.

        The active predicate and freshness clamp are identical to
        :meth:`count_active`:

        1. ``status = 'active'``
        2. ``updated_at >= now() - window_seconds``

        Args:
            project_id: The project to scope the query to.
            window_seconds: Freshness window in seconds (default 600 = 10 min).
                Sessions with ``updated_at`` older than this are excluded even
                if their stored ``status`` is ``'active'``.
            limit: Optional cap on returned rows.  ``None`` means no cap.
                Callers doing cross-project sweeps should always pass a
                reasonable limit to avoid unbounded result sets.
            include_subagents: If ``True`` (default), rows where
                ``session_type = 'subagent'`` are included.  Pass ``False``
                to exclude subagent sessions.

        Returns:
            List of session row dicts ordered by ``updated_at DESC``.
            Returns an empty list when the project has no active sessions
            within the window.  Each dict has the same shape as rows
            returned by :meth:`get_by_id` (all ``sessions`` columns via
            ``dict(row)``).
        """
        from datetime import datetime, timedelta, timezone

        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        where_parts = [
            "project_id = $1",
            "status = $2",
            "updated_at >= $3",
        ]
        params: list[Any] = [project_id, "active", threshold]

        if not include_subagents:
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")

        where = " WHERE " + " AND ".join(where_parts)
        order_clause = " ORDER BY updated_at DESC"

        limit_clause = ""
        if limit is not None:
            params.append(limit)
            limit_clause = f" LIMIT ${len(params)}"

        rows = await self.db.fetch(
            f"SELECT * FROM sessions{where}{order_clause}{limit_clause}",  # noqa: S608
            *params,
        )
        return [dict(row) for row in rows]

    async def get_model_facets(self, project_id: str | None = None, include_subagents: bool = True) -> list[dict]:
        where_parts: list[str] = ["TRIM(COALESCE(model, '')) != ''"]
        params: list[Any] = []
        idx = 1

        if project_id:
            where_parts.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if not include_subagents:
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")

        where = ""
        if where_parts:
            where = " WHERE " + " AND ".join(where_parts)

        rows = await self.db.fetch(
            f"""
            SELECT model, COUNT(*)::int AS count
            FROM sessions
            {where}
            GROUP BY model
            ORDER BY count DESC, model ASC
            """,
            *params,
        )
        return [dict(row) for row in rows]

    async def get_platform_facets(self, project_id: str | None = None, include_subagents: bool = True) -> list[dict]:
        where_parts: list[str] = []
        params: list[Any] = []
        idx = 1

        if project_id:
            where_parts.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if not include_subagents:
            where_parts.append("(session_type IS NULL OR session_type != 'subagent')")

        where = ""
        if where_parts:
            where = " WHERE " + " AND ".join(where_parts)

        rows = await self.db.fetch(
            f"""
            SELECT platform_type, platform_version, platform_versions_json
            FROM sessions
            {where}
            """,
            *params,
        )

        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            row_dict = dict(row)
            platform_type = str(row_dict.get("platform_type") or "").strip() or "Claude Code"
            versions: set[str] = set()
            primary = str(row_dict.get("platform_version") or "").strip()
            if primary:
                versions.add(primary)
            raw_versions = row_dict.get("platform_versions_json")
            if isinstance(raw_versions, str) and raw_versions.strip():
                try:
                    parsed = json.loads(raw_versions)
                except Exception:
                    parsed = []
                if isinstance(parsed, list):
                    for value in parsed:
                        version = str(value or "").strip()
                        if version:
                            versions.add(version)
            for version in versions:
                key = (platform_type, version)
                counts[key] = counts.get(key, 0) + 1

        items = [
            {"platform_type": key[0], "platform_version": key[1], "count": count}
            for key, count in counts.items()
        ]
        items.sort(key=lambda item: (-item["count"], item["platform_type"].lower(), item["platform_version"].lower()))
        return items

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM sessions WHERE source_file = $1", source_file)

    async def update_session_badges(
        self,
        session_id: str,
        *,
        command_slug: str,
        latest_summary: str,
        subagent_type: str,
        models_used: list,
        agents_used: list,
        skills_used: list,
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
    ) -> None:
        """Persist the 6 materialized badge columns for a single session.

        The WHERE clause includes a NULL/'' project_id tolerance so sessions written
        before project_id threading was added still get updated.
        """
        import json as _json
        await self.db.execute(
            """UPDATE sessions SET
                command_slug = $1,
                latest_summary = $2,
                subagent_type = $3,
                models_used_json = $4,
                agents_used_json = $5,
                skills_used_json = $6
               WHERE (project_id = $7 OR project_id IS NULL OR project_id = '') AND id = $8""",
            str(command_slug or ""),
            str(latest_summary or ""),
            str(subagent_type or ""),
            _json.dumps(models_used if isinstance(models_used, list) else []),
            _json.dumps(agents_used if isinstance(agents_used, list) else []),
            _json.dumps(skills_used if isinstance(skills_used, list) else []),
            project_id,
            session_id,
        )

    async def update_usage_fields(
        self,
        session_id: str,
        usage_fields: dict[str, int],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
    ) -> None:
        await self.db.execute(
            """
            UPDATE sessions
            SET model_io_tokens = $1,
                cache_creation_input_tokens = $2,
                cache_read_input_tokens = $3,
                cache_input_tokens = $4,
                observed_tokens = $5,
                tool_reported_tokens = $6,
                tool_result_input_tokens = $7,
                tool_result_output_tokens = $8,
                tool_result_cache_creation_input_tokens = $9,
                tool_result_cache_read_input_tokens = $10
            WHERE (project_id = $11 OR project_id IS NULL OR project_id = '') AND id = $12
            """,
            int(usage_fields.get("model_io_tokens", 0) or 0),
            int(usage_fields.get("cache_creation_input_tokens", 0) or 0),
            int(usage_fields.get("cache_read_input_tokens", 0) or 0),
            int(usage_fields.get("cache_input_tokens", 0) or 0),
            int(usage_fields.get("observed_tokens", 0) or 0),
            int(usage_fields.get("tool_reported_tokens", 0) or 0),
            int(usage_fields.get("tool_result_input_tokens", 0) or 0),
            int(usage_fields.get("tool_result_output_tokens", 0) or 0),
            int(usage_fields.get("tool_result_cache_creation_input_tokens", 0) or 0),
            int(usage_fields.get("tool_result_cache_read_input_tokens", 0) or 0),
            project_id,
            session_id,
        )

    async def update_observability_fields(
        self,
        session_id: str,
        observability_fields: dict[str, Any],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
        _pg_conn: Any = None,
    ) -> None:
        _conn = _pg_conn if _pg_conn is not None else self.db
        await _conn.execute(
            """
            UPDATE sessions
            SET current_context_tokens = $1,
                context_window_size = $2,
                context_utilization_pct = $3,
                context_measurement_source = $4,
                context_measured_at = $5,
                reported_cost_usd = $6,
                recalculated_cost_usd = $7,
                display_cost_usd = $8,
                cost_provenance = $9,
                cost_confidence = $10,
                cost_mismatch_pct = $11,
                pricing_model_source = $12,
                total_cost = $13
            WHERE (project_id = $14 OR project_id IS NULL OR project_id = '') AND id = $15
            """,
            int(observability_fields.get("current_context_tokens", 0) or 0),
            int(observability_fields.get("context_window_size", 0) or 0),
            float(observability_fields.get("context_utilization_pct", 0.0) or 0.0),
            str(observability_fields.get("context_measurement_source", "") or ""),
            str(observability_fields.get("context_measured_at", "") or ""),
            observability_fields.get("reported_cost_usd"),
            observability_fields.get("recalculated_cost_usd"),
            observability_fields.get("display_cost_usd"),
            str(observability_fields.get("cost_provenance", "unknown") or "unknown"),
            float(observability_fields.get("cost_confidence", 0.0) or 0.0),
            observability_fields.get("cost_mismatch_pct"),
            str(observability_fields.get("pricing_model_source", "") or ""),
            float(observability_fields.get("total_cost", 0.0) or 0.0),
            project_id,
            session_id,
        )

    # ── Detail tables ───────────────────────────────────────────────

    async def upsert_logs(self, session_id: str, logs: list[dict], project_id: str = "", _pg_conn: Any = None) -> None:
        # Deduplicate by source_log_id (non-empty) before building the record list.
        # Duplicates produced by the parser are a known upstream issue (Fix C) — this
        # guard prevents the partial-unique index constraint from firing.
        seen_source_ids: set[str] = set()
        deduped: list[dict] = []
        dropped = 0
        for log in logs:
            src_id = log.get("id", "")
            if src_id:
                if src_id in seen_source_ids:
                    dropped += 1
                    continue
                seen_source_ids.add(src_id)
            deduped.append(log)
        if dropped:
            logger.warning(
                "upsert_logs: dropped %d duplicate source_log_id entries for session_id=%r",
                dropped,
                session_id,
            )

        async def _execute(conn: Any) -> None:
            # Scope DELETE to (project_id, session_id) so project-A's writer never clears
            # project-B's rows sharing the same session_id.  NULL/'' tolerance covers
            # legacy rows written before project_id threading was added.
            await conn.execute(
                "DELETE FROM session_logs "
                "WHERE session_id = $1 AND (project_id = $2 OR project_id IS NULL OR project_id = '')",
                session_id,
                project_id,
            )
            if not deduped:
                return

            records = []
            for i, log in enumerate(deduped):
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
                    log.get("id", f"log-{i}"),
                    log.get("timestamp", ""),
                    log.get("speaker", ""),
                    log.get("type", ""),
                    log.get("content", ""),
                    log.get("agentName"),
                    tool_name, tool_call_id, log.get("relatedToolCallId"),
                    log.get("linkedSessionId"), tool_args, tool_output, tool_status, metadata_json,
                    project_id,
                ))

            await conn.executemany(
                """INSERT INTO session_logs
                    (session_id, log_index, source_log_id, timestamp, speaker, type, content,
                     agent_name, tool_name, tool_call_id, related_tool_call_id,
                     linked_session_id, tool_args, tool_output, tool_status, metadata_json,
                     project_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                   ON CONFLICT ON CONSTRAINT idx_logs_source_log_unique DO NOTHING""",
                records
            )

        if _pg_conn is not None:
            await _execute(_pg_conn)
        else:
            async with postgres_transaction(self.db) as conn:
                await _execute(conn)

    async def upsert_tool_usage(self, session_id: str, tools: list[dict], project_id: str = "", _pg_conn: Any = None) -> None:
        async def _execute(conn: Any) -> None:
            await conn.execute("DELETE FROM session_tool_usage WHERE session_id = $1", session_id)
            if not tools:
                return

            records = []
            for t in tools:
                records.append((
                    session_id, t.get("name", ""), t.get("count", 0),
                    int(t.get("count", 0) * t.get("successRate", 1.0)),
                    max(0, int(t.get("totalMs", 0) or 0)),
                    project_id,
                ))

            await conn.executemany(
                """INSERT INTO session_tool_usage (session_id, tool_name, call_count, success_count, total_ms, project_id)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (session_id, tool_name) DO NOTHING""",
                records
            )

        if _pg_conn is not None:
            await _execute(_pg_conn)
        else:
            async with postgres_transaction(self.db) as conn:
                await _execute(conn)

    async def upsert_file_updates(self, session_id: str, updates: list[dict], project_id: str = "", _pg_conn: Any = None) -> None:
        async def _execute(conn: Any) -> None:
            # Scope DELETE to (project_id, session_id) — see upsert_logs for rationale.
            await conn.execute(
                "DELETE FROM session_file_updates "
                "WHERE session_id = $1 AND (project_id = $2 OR project_id IS NULL OR project_id = '')",
                session_id,
                project_id,
            )
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
                    project_id,
                ))

            await conn.executemany(
                """INSERT INTO session_file_updates (
                    session_id, file_path, action, file_type, action_timestamp,
                    additions, deletions, agent_name, thread_session_id, root_session_id,
                    source_log_id, source_tool_name, project_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
                records
            )

        if _pg_conn is not None:
            await _execute(_pg_conn)
        else:
            async with postgres_transaction(self.db) as conn:
                await _execute(conn)

    async def upsert_artifacts(
        self,
        session_id: str,
        artifacts: list[dict],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
        _pg_conn: Any = None,
    ) -> None:
        async def _execute(conn: Any) -> None:
            # Scope DELETE to (project_id, session_id) — see upsert_logs for rationale.
            await conn.execute(
                "DELETE FROM session_artifacts "
                "WHERE session_id = $1 AND (project_id = $2 OR project_id IS NULL OR project_id = '')",
                session_id,
                project_id,
            )
            if not artifacts:
                return

            records = []
            for a in artifacts:
                records.append((
                   project_id, a.get("id", ""), session_id, a.get("title", ""),
                   a.get("type", "document"), a.get("description", ""), a.get("source", ""),
                   a.get("url"), a.get("sourceLogId"), a.get("sourceToolName"),
                ))

            await conn.executemany(
                """INSERT INTO session_artifacts (
                    project_id, id, session_id, title, type, description, source, url, source_log_id, source_tool_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO NOTHING""",
                records
            )

        if _pg_conn is not None:
            await _execute(_pg_conn)
        else:
            async with postgres_transaction(self.db) as conn:
                await _execute(conn)

    async def delete_relationships_for_source(self, project_id: str, source_file: str) -> None:
        await self.db.execute(
            "DELETE FROM session_relationships WHERE project_id = $1 AND source_file = $2",
            project_id,
            source_file,
        )

    async def upsert_relationships(self, project_id: str, source_file: str, relationships: list[dict], _pg_conn: Any = None) -> None:
        if not relationships:
            return
        records = []
        for relationship in relationships:
            records.append(
                (
                    str(relationship.get("id") or ""),
                    project_id,
                    str(relationship.get("parentSessionId") or ""),
                    str(relationship.get("childSessionId") or ""),
                    str(relationship.get("relationshipType") or ""),
                    str(relationship.get("contextInheritance") or ""),
                    str(relationship.get("sourcePlatform") or ""),
                    str(relationship.get("parentEntryUuid") or ""),
                    str(relationship.get("childEntryUuid") or ""),
                    relationship.get("sourceLogId"),
                    json.dumps(relationship.get("metadata") or {}),
                    source_file,
                )
            )
        _conn = _pg_conn if _pg_conn is not None else self.db
        await _conn.executemany(
            """
            INSERT INTO session_relationships (
                id, project_id, parent_session_id, child_session_id,
                relationship_type, context_inheritance, source_platform,
                parent_entry_uuid, child_entry_uuid, source_log_id, metadata_json, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                parent_session_id = EXCLUDED.parent_session_id,
                child_session_id = EXCLUDED.child_session_id,
                relationship_type = EXCLUDED.relationship_type,
                context_inheritance = EXCLUDED.context_inheritance,
                source_platform = EXCLUDED.source_platform,
                parent_entry_uuid = EXCLUDED.parent_entry_uuid,
                child_entry_uuid = EXCLUDED.child_entry_uuid,
                source_log_id = EXCLUDED.source_log_id,
                metadata_json = EXCLUDED.metadata_json,
                source_file = EXCLUDED.source_file
            """,
            records,
        )

    async def list_relationships(self, project_id: str, session_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM session_relationships
            WHERE project_id = $1
              AND (parent_session_id = $2 OR child_session_id = $2)
            ORDER BY created_at ASC, id ASC
            """,
            project_id,
            session_id,
        )
        return [dict(r) for r in rows]

    async def get_logs(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_logs WHERE session_id = $1 ORDER BY log_index LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(r) for r in rows]

    async def get_tool_usage(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_tool_usage WHERE session_id = $1 LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(r) for r in rows]

    async def get_file_updates(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_file_updates WHERE session_id = $1 LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(r) for r in rows]

    async def get_artifacts(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_artifacts WHERE session_id = $1 LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(r) for r in rows]

    async def get_project_stats(self, project_id: str) -> dict:
        query = """
            SELECT
                COUNT(*) as count,
                SUM(total_cost) as cost,
                SUM(
                    CASE
                        WHEN observed_tokens > 0 THEN observed_tokens
                        ELSE tokens_in + tokens_out
                    END
                ) as tokens,
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
