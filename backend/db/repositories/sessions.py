"""SQLite implementation of SessionRepository."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite
from backend.model_identity import model_filter_tokens
from backend.db.repositories.base import retry_on_locked, DEFAULT_WORKSPACE_ID

logger = logging.getLogger("ccdash.db.sessions")

logger = logging.getLogger("ccdash.db.sessions")

_FS_SOURCE_ID = "filesystem"
_REMOTE_SOURCE_ID = "remote_ingest"
_ENTIRE_SOURCE_ID = "entire"


def compute_source_ref(
    source_id: str,
    *,
    source_file: str | None = None,
    event_id: str | None = None,
    checkpoint_id: str | None = None,
) -> str:
    """Build the canonical source_ref URI for a session row.

    fs:<canonical-rel-path>        — filesystem source
    remote:<event-id>              — daemon remote ingest (workspace prefix added in Phase 4)
    entire:<checkpoint-hex>        — Entire.io checkpoint (Phase 5)

    Raises ValueError for an unknown source_id or a missing required field.
    """
    if source_id == _FS_SOURCE_ID:
        if not source_file:
            raise ValueError(
                "source_file is required when source_id is 'filesystem'"
            )
        return f"fs:{source_file}"
    if source_id == _REMOTE_SOURCE_ID:
        if not event_id:
            raise ValueError(
                "event_id is required when source_id is 'remote_ingest'"
            )
        return f"remote:{event_id}"
    if source_id == _ENTIRE_SOURCE_ID:
        if not checkpoint_id:
            raise ValueError(
                "checkpoint_id is required when source_id is 'entire'"
            )
        return f"entire:{checkpoint_id}"
    raise ValueError(f"Unknown source_id: {source_id!r}")


class SqliteSessionRepository:
    """SQLite-backed session storage with normalized detail tables."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def _commit(self) -> None:
        """Commit with locked-retry, re-raising on exhaustion (fail-loud)."""
        await retry_on_locked(self.db.commit, repo="sessions")

    async def upsert(
        self,
        session_data: dict,
        project_id: str,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        source_ref: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = session_data.get("createdAt", "") or now
        updated_at = session_data.get("updatedAt", "") or now
        await self.db.execute(
            """INSERT INTO sessions (
                id, project_id, workspace_id, task_id, status, model,
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
                command_slug, latest_summary, subagent_type,
                models_used_json, agents_used_json, skills_used_json,
                model_slug, workflow_id, subagent_parent_id, skill_name, context_window,
                launcher, profile, effort_tier, model_variant,
                source_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, id) DO UPDATE SET
                task_id=excluded.task_id, status=excluded.status, model=excluded.model,
                platform_type=excluded.platform_type,
                platform_version=excluded.platform_version,
                platform_versions_json=excluded.platform_versions_json,
                platform_version_transitions_json=excluded.platform_version_transitions_json,
                duration_seconds=excluded.duration_seconds,
                tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out,
                model_io_tokens=excluded.model_io_tokens,
                cache_creation_input_tokens=excluded.cache_creation_input_tokens,
                cache_read_input_tokens=excluded.cache_read_input_tokens,
                cache_input_tokens=excluded.cache_input_tokens,
                observed_tokens=excluded.observed_tokens,
                tool_reported_tokens=excluded.tool_reported_tokens,
                tool_result_input_tokens=excluded.tool_result_input_tokens,
                tool_result_output_tokens=excluded.tool_result_output_tokens,
                tool_result_cache_creation_input_tokens=excluded.tool_result_cache_creation_input_tokens,
                tool_result_cache_read_input_tokens=excluded.tool_result_cache_read_input_tokens,
                total_cost=excluded.total_cost,
                quality_rating=excluded.quality_rating, friction_rating=excluded.friction_rating,
                git_commit_hash=excluded.git_commit_hash,
                git_commit_hashes_json=excluded.git_commit_hashes_json,
                git_author=excluded.git_author,
                git_branch=excluded.git_branch,
                session_type=excluded.session_type,
                parent_session_id=excluded.parent_session_id,
                root_session_id=excluded.root_session_id,
                agent_id=excluded.agent_id,
                thread_kind=excluded.thread_kind,
                conversation_family_id=excluded.conversation_family_id,
                context_inheritance=excluded.context_inheritance,
                fork_parent_session_id=excluded.fork_parent_session_id,
                fork_point_log_id=excluded.fork_point_log_id,
                fork_point_entry_uuid=excluded.fork_point_entry_uuid,
                fork_point_parent_entry_uuid=excluded.fork_point_parent_entry_uuid,
                fork_depth=excluded.fork_depth,
                fork_count=excluded.fork_count,
                started_at=excluded.started_at, ended_at=excluded.ended_at,
                updated_at=excluded.updated_at, source_file=excluded.source_file,
                dates_json=excluded.dates_json,
                timeline_json=excluded.timeline_json,
                impact_history_json=excluded.impact_history_json,
                thinking_level=excluded.thinking_level,
                session_forensics_json=excluded.session_forensics_json,
                command_slug=CASE WHEN excluded.command_slug != '' THEN excluded.command_slug ELSE sessions.command_slug END,
                latest_summary=CASE WHEN excluded.latest_summary != '' THEN excluded.latest_summary ELSE sessions.latest_summary END,
                subagent_type=CASE WHEN excluded.subagent_type != '' THEN excluded.subagent_type ELSE sessions.subagent_type END,
                models_used_json=CASE WHEN excluded.models_used_json != '[]' THEN excluded.models_used_json ELSE sessions.models_used_json END,
                agents_used_json=CASE WHEN excluded.agents_used_json != '[]' THEN excluded.agents_used_json ELSE sessions.agents_used_json END,
                skills_used_json=CASE WHEN excluded.skills_used_json != '[]' THEN excluded.skills_used_json ELSE sessions.skills_used_json END,
                -- Phase 5 detection columns (T5-006).
                model_slug=CASE WHEN excluded.model_slug != '' THEN excluded.model_slug ELSE sessions.model_slug END,
                workflow_id=excluded.workflow_id,
                subagent_parent_id=excluded.subagent_parent_id,
                skill_name=excluded.skill_name,
                -- context_window comes from the sidecar join (T5-003), which may be
                -- transiently absent on re-ingest; never wipe a prior attribution.
                context_window=COALESCE(excluded.context_window, sessions.context_window),
                -- Phase 11 launch-time capture columns (T11-003). All four are
                -- capture-once: a re-ingest with a null value must never clobber a
                -- previously-captured value (idempotency, AC-11.C).
                launcher=COALESCE(excluded.launcher, sessions.launcher),
                profile=COALESCE(excluded.profile, sessions.profile),
                effort_tier=COALESCE(excluded.effort_tier, sessions.effort_tier),
                model_variant=COALESCE(excluded.model_variant, sessions.model_variant),
                source_ref=COALESCE(excluded.source_ref, sessions.source_ref)
            WHERE sessions.workspace_id = excluded.workspace_id
            """,
            (
                session_data["id"], project_id, workspace_id,
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
                # Badge columns — written on initial upsert; also updated via update_session_badges.
                # These default to '' / '[]' so existing rows without badges are not overwritten
                # with empty values on re-ingest (see ON CONFLICT CASE expressions above).
                str(session_data.get("badgeCommandSlug", "") or ""),
                str(session_data.get("badgeLatestSummary", "") or ""),
                str(session_data.get("badgeSubagentType", "") or ""),
                json.dumps(session_data.get("badgeModelsUsed", []) or []),
                json.dumps(session_data.get("badgeAgentsUsed", []) or []),
                json.dumps(session_data.get("badgeSkillsUsed", []) or []),
                # Phase 5 detection columns (T5-006). model_slug defaults to ''
                # (string contract); workflow/skill/context are nullable.
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
                source_ref,
            ),
        )
        await self._commit()

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

        Called by the badge backfill path and from SessionTranscriptService after
        computing badges from logs.  Designed to be idempotent (safe to call
        multiple times).  Does NOT commit — caller may batch commits.

        The WHERE clause includes a NULL/'' project_id tolerance so sessions written
        before project_id threading was added still get updated.
        """
        await self.db.execute(
            """UPDATE sessions SET
                command_slug = ?,
                latest_summary = ?,
                subagent_type = ?,
                models_used_json = ?,
                agents_used_json = ?,
                skills_used_json = ?
               WHERE (project_id = ? OR project_id IS NULL OR project_id = '') AND id = ?""",
            (
                str(command_slug or ""),
                str(latest_summary or ""),
                str(subagent_type or ""),
                json.dumps(models_used if isinstance(models_used, list) else []),
                json.dumps(agents_used if isinstance(agents_used, list) else []),
                json.dumps(skills_used if isinstance(skills_used, list) else []),
                project_id,
                session_id,
            ),
        )
        await self._commit()

    async def get_by_id(self, session_id: str, project_id: str | None = None, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict | None:
        """Fetch a single session by id, optionally scoped to project_id and workspace_id.

        When ``project_id`` is a non-empty string it is added to the WHERE clause
        as a strict-equality predicate alongside ``id`` (the table's composite PK
        is ``(project_id, id)``).  ``workspace_id`` scopes the read to a specific
        workspace (default DEFAULT_WORKSPACE_ID).
        """
        if project_id:
            query = "SELECT * FROM sessions WHERE project_id = ? AND id = ? AND workspace_id = ?"
            params: tuple = (project_id, session_id, workspace_id)
        else:
            query = "SELECT * FROM sessions WHERE id = ? AND workspace_id = ?"
            params = (session_id, workspace_id)
        async with self.db.execute(query, params) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    async def get_many_by_ids(
        self, ids: list[str], project_id: str | None = None, *, workspace_id: str = DEFAULT_WORKSPACE_ID
    ) -> dict[str, dict]:
        """Fetch multiple sessions in a single query. Returns a dict keyed by session id.

        ``project_id`` follows the same semantics as :meth:`get_by_id`: a non-empty
        value scopes the query to that project (strict equality), while ``None``/``''``
        leaves the read unscoped.  ``workspace_id`` scopes to a specific workspace.
        """
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        if project_id:
            query = (
                f"SELECT * FROM sessions WHERE project_id = ? AND id IN ({placeholders}) AND workspace_id = ?"
            )
            params: tuple = (project_id, *ids, workspace_id)
        else:
            query = f"SELECT * FROM sessions WHERE id IN ({placeholders}) AND workspace_id = ?"
            params = tuple(ids) + (workspace_id,)
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return {row["id"]: self._row_to_dict(row) for row in rows}

    async def list_by_source(self, source_file: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[dict]:
        """List sessions by source_file, scoped to workspace_id."""
        async with self.db.execute(
            "SELECT * FROM sessions WHERE source_file = ? AND workspace_id = ?",
            (source_file, workspace_id),
        ) as cur:
            rows = await cur.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def list_paginated(
        self,
        offset: int,
        limit: int,
        project_id: str | None = None,
        sort_by: str = "started_at",
        sort_order: str = "desc",
        filters: dict | None = None,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> list[dict]:
        # Whitelist sortable columns

        allowed_sort = {"started_at", "total_cost", "duration_seconds", "tokens_in", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "started_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        query_parts = ["SELECT * FROM sessions"]
        params: list = []
        where_clauses: list[str] = ["workspace_id = ?"]
        params.append(workspace_id)
        filters = filters or {}

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if filters.get("status"):
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if filters.get("model"):
            where_clauses.append("model LIKE ?")
            params.append(f"%{filters['model']}%")
        if filters.get("model_provider"):
            tokens = model_filter_tokens(str(filters["model_provider"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("model_family"):
            tokens = model_filter_tokens(str(filters["model_family"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("model_version"):
            tokens = model_filter_tokens(str(filters["model_version"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("platform_type"):
            where_clauses.append("LOWER(COALESCE(NULLIF(TRIM(platform_type), ''), 'Claude Code')) = LOWER(?)")
            params.append(str(filters["platform_type"]))
        if filters.get("platform_version"):
            version = str(filters["platform_version"]).strip()
            if version:
                where_clauses.append("(platform_version = ? OR platform_versions_json LIKE ?)")
                params.append(version)
                params.append(f'%"{version}"%')
        if not filters.get("include_subagents", False):
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("thread_kind"):
            where_clauses.append("LOWER(COALESCE(thread_kind, '')) = LOWER(?)")
            params.append(str(filters["thread_kind"]))
        if filters.get("conversation_family_id"):
            where_clauses.append("conversation_family_id = ?")
            params.append(str(filters["conversation_family_id"]))
        if filters.get("task_id"):
            where_clauses.append("task_id = ?")
            params.append(str(filters["task_id"]))
        if filters.get("root_session_id"):
            where_clauses.append("root_session_id = ?")
            params.append(filters["root_session_id"])
        
        # Date range (started_at)
        if filters.get("start_date"):
            where_clauses.append("started_at >= ?")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            where_clauses.append("started_at <= ?")
            params.append(filters["end_date"])
        if filters.get("created_start"):
            where_clauses.append("created_at >= ?")
            params.append(filters["created_start"])
        if filters.get("created_end"):
            where_clauses.append("created_at <= ?")
            params.append(filters["created_end"])
        if filters.get("completed_start"):
            where_clauses.append("ended_at >= ?")
            params.append(filters["completed_start"])
        if filters.get("completed_end"):
            where_clauses.append("ended_at <= ?")
            params.append(filters["completed_end"])
        if filters.get("updated_start"):
            where_clauses.append("updated_at >= ?")
            params.append(filters["updated_start"])
        if filters.get("updated_end"):
            where_clauses.append("updated_at <= ?")
            params.append(filters["updated_end"])

        # Duration range
        if filters.get("min_duration") is not None:
            where_clauses.append("duration_seconds >= ?")
            params.append(filters["min_duration"])
        if filters.get("max_duration") is not None:
            where_clauses.append("duration_seconds <= ?")
            params.append(filters["max_duration"])

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query_parts.append(f"ORDER BY {sort_by} {order}")
        query_parts.append("LIMIT ? OFFSET ?")
        params.append(limit)
        params.append(offset)

        query = " ".join(query_parts)

        async with self.db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            return [self._row_to_dict(r) for r in rows]

    async def count(self, project_id: str | None = None, filters: dict | None = None, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> int:
        query_parts = ["SELECT COUNT(*) FROM sessions"]
        params: list = []
        where_clauses: list[str] = ["workspace_id = ?"]
        params.append(workspace_id)
        filters = filters or {}

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
            
        if filters.get("status"):
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if filters.get("model"):
            where_clauses.append("model LIKE ?")
            params.append(f"%{filters['model']}%")
        if filters.get("model_provider"):
            tokens = model_filter_tokens(str(filters["model_provider"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("model_family"):
            tokens = model_filter_tokens(str(filters["model_family"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("model_version"):
            tokens = model_filter_tokens(str(filters["model_version"]))
            if tokens:
                for token in tokens:
                    where_clauses.append("model LIKE ?")
                    params.append(f"%{token}%")
        if filters.get("platform_type"):
            where_clauses.append("LOWER(COALESCE(NULLIF(TRIM(platform_type), ''), 'Claude Code')) = LOWER(?)")
            params.append(str(filters["platform_type"]))
        if filters.get("platform_version"):
            version = str(filters["platform_version"]).strip()
            if version:
                where_clauses.append("(platform_version = ? OR platform_versions_json LIKE ?)")
                params.append(version)
                params.append(f'%"{version}"%')
        if not filters.get("include_subagents", False):
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")
        if filters.get("thread_kind"):
            where_clauses.append("LOWER(COALESCE(thread_kind, '')) = LOWER(?)")
            params.append(str(filters["thread_kind"]))
        if filters.get("conversation_family_id"):
            where_clauses.append("conversation_family_id = ?")
            params.append(str(filters["conversation_family_id"]))
        if filters.get("task_id"):
            where_clauses.append("task_id = ?")
            params.append(str(filters["task_id"]))
        if filters.get("root_session_id"):
            where_clauses.append("root_session_id = ?")
            params.append(filters["root_session_id"])
        if filters.get("start_date"):
            where_clauses.append("started_at >= ?")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            where_clauses.append("started_at <= ?")
            params.append(filters["end_date"])
        if filters.get("created_start"):
            where_clauses.append("created_at >= ?")
            params.append(filters["created_start"])
        if filters.get("created_end"):
            where_clauses.append("created_at <= ?")
            params.append(filters["created_end"])
        if filters.get("completed_start"):
            where_clauses.append("ended_at >= ?")
            params.append(filters["completed_start"])
        if filters.get("completed_end"):
            where_clauses.append("ended_at <= ?")
            params.append(filters["completed_end"])
        if filters.get("updated_start"):
            where_clauses.append("updated_at >= ?")
            params.append(filters["updated_start"])
        if filters.get("updated_end"):
            where_clauses.append("updated_at <= ?")
            params.append(filters["updated_end"])
        if filters.get("min_duration") is not None:
            where_clauses.append("duration_seconds >= ?")
            params.append(filters["min_duration"])
        if filters.get("max_duration") is not None:
            where_clauses.append("duration_seconds <= ?")
            params.append(filters["max_duration"])

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query = " ".join(query_parts)

        async with self.db.execute(query, tuple(params)) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def count_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        include_subagents: bool = False,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> int:
        """Count sessions that are currently active for a project.

        A session is counted as "active" when BOTH conditions hold:
        1. ``status = 'active'``
        2. ``updated_at >= now() - window_seconds``

        Dual role of the freshness clamp (important — do NOT remove):
        - **Liveness gate**: ensures only recently-seen sessions are reported
          as running.  Without this predicate, sessions that are truly finished
          but whose ``status`` column was never updated (e.g. because the parser
          ran before the JSONL file was fully flushed) would be counted forever.
        - **Stale-active defence**: the spike verification (OQ-3) found sessions
          with ``status='active'`` and ``updated_at`` values 57–93 days in the
          past.  These are phantom rows that appear when a project is switched
          away from before the file watcher can re-parse them.  The
          ``updated_at >= now() - window_seconds`` predicate silently excludes
          those rows and prevents phantom live-agent counts.

        The default ``window_seconds=600`` intentionally matches
        ``_ACTIVE_SESSION_WINDOW_SECONDS`` in:
        - ``backend/parsers/platforms/claude_code/parser.py`` (line ~100)
        - ``backend/parsers/platforms/codex/parser.py`` (line ~22)
        Those constants control *parser classification*; this parameter controls
        *query filtering*.  They are equal by convention, not by coupling.
        Override via ``CCDASH_LIVE_AGENTS_WINDOW_SECONDS`` at query call sites.

        Args:
            project_id: The project to scope the count to.
            window_seconds: Freshness window in seconds (default 600 = 10 min).
                Sessions with ``updated_at`` older than this are excluded even
                if their ``status`` is ``'active'``.
            include_subagents: If ``False`` (default), rows where
                ``session_type = 'subagent'`` are excluded, matching the
                existing ``include_subagents=False`` convention on
                ``list_paginated`` and ``count``.
            workspace_id: Scope the count to a specific workspace.

        Returns:
            Integer count of currently-active sessions.  Returns 0 when the
            project has no sessions or no active sessions within the window.
        """
        from datetime import datetime, timedelta, timezone

        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        where_clauses = [
            "project_id = ?",
            "status = ?",
            "updated_at >= ?",
            "workspace_id = ?",
        ]
        params: list = [project_id, "active", threshold, workspace_id]

        if not include_subagents:
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")

        query = (
            "SELECT COUNT(*) FROM sessions WHERE "
            + " AND ".join(where_clauses)
        )

        async with self.db.execute(query, tuple(params)) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit: int | None = None,
        include_subagents: bool = True,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> list[dict]:
        """List sessions that are currently active for a project.

        Returns session rows ordered by ``updated_at DESC`` (most-recently
        active first).  The active predicate and staleness clamp are
        **identical** to :meth:`count_active`:

        1. ``status = 'active'``
        2. ``updated_at >= now() - window_seconds``

        The WHERE clause is intentionally shaped to match the composite index
        declared in ``sqlite_migrations.py``::

            CREATE INDEX idx_sessions_project_status_updated
                ON sessions(project_id, status, updated_at);

        That index covers all three leading predicate columns, so this query
        never does a full table scan.

        Args:
            project_id: The project to scope the query to.
            window_seconds: Freshness window in seconds (default 600 = 10 min).
                Sessions with ``updated_at`` older than this are excluded even
                if their stored ``status`` is ``'active'``.  Same default and
                same semantics as :meth:`count_active`.
            limit: Optional cap on returned rows.  ``None`` means no cap.
                Callers doing cross-project sweeps should always pass a
                reasonable limit to avoid unbounded result sets.
            include_subagents: If ``True`` (default), rows where
                ``session_type = 'subagent'`` are included.  Pass ``False``
                to exclude worker/subagent sessions, mirroring the
                ``include_subagents=False`` convention on
                :meth:`list_paginated`, :meth:`count`, and
                :meth:`count_active`.
            workspace_id: Scope the list to a specific workspace.

        Returns:
            List of session row dicts ordered by ``updated_at DESC``.
            Returns an empty list when the project has no active sessions
            within the window.  Each dict has the same shape as rows
            returned by :meth:`list_paginated` (all ``sessions`` columns
            via :meth:`_row_to_dict`).
        """
        from datetime import datetime, timedelta, timezone

        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        where_clauses = [
            "project_id = ?",
            "status = ?",
            "updated_at >= ?",
            "workspace_id = ?",
        ]
        params: list = [project_id, "active", threshold, workspace_id]

        if not include_subagents:
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")

        query = (
            "SELECT * FROM sessions WHERE "
            + " AND ".join(where_clauses)
            + " ORDER BY updated_at DESC"
        )

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        async with self.db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_model_facets(self, project_id: str | None = None, include_subagents: bool = True, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[dict]:
        query_parts = [
            "SELECT model, COUNT(*) AS count",
            "FROM sessions",
        ]
        params: list = []
        where_clauses: list[str] = ["workspace_id = ?", "TRIM(COALESCE(model, '')) != ''"]
        params.append(workspace_id)

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if not include_subagents:
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))
        query_parts.append("GROUP BY model")
        query_parts.append("ORDER BY count DESC, model ASC")

        query = " ".join(query_parts)
        async with self.db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            return [{"model": row[0], "count": int(row[1] or 0)} for row in rows]

    async def get_platform_facets(self, project_id: str | None = None, include_subagents: bool = True, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[dict]:
        query_parts = [
            "SELECT platform_type, platform_version, platform_versions_json",
            "FROM sessions",
        ]
        params: list = []
        where_clauses: list[str] = ["workspace_id = ?"]
        params.append(workspace_id)

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if not include_subagents:
            where_clauses.append("(session_type IS NULL OR session_type != 'subagent')")

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query = " ".join(query_parts)
        counts: dict[tuple[str, str], int] = {}
        async with self.db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            for row in rows:
                platform_type = str(row[0] or "").strip() or "Claude Code"
                versions: set[str] = set()
                primary = str(row[1] or "").strip()
                if primary:
                    versions.add(primary)
                raw_versions = row[2]
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
        await self.db.execute("DELETE FROM sessions WHERE source_file = ?", (source_file,))
        await self._commit()

    async def update_usage_fields(
        self,
        session_id: str,
        usage_fields: dict[str, int],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
    ) -> None:
        await self.db.execute(
            """
            UPDATE sessions
            SET model_io_tokens = ?,
                cache_creation_input_tokens = ?,
                cache_read_input_tokens = ?,
                cache_input_tokens = ?,
                observed_tokens = ?,
                tool_reported_tokens = ?,
                tool_result_input_tokens = ?,
                tool_result_output_tokens = ?,
                tool_result_cache_creation_input_tokens = ?,
                tool_result_cache_read_input_tokens = ?
            WHERE (project_id = ? OR project_id IS NULL OR project_id = '') AND id = ?
            """,
            (
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
            ),
        )
        await self._commit()

    async def update_observability_fields(
        self,
        session_id: str,
        observability_fields: dict[str, object],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
    ) -> None:
        await self.db.execute(
            """
            UPDATE sessions
            SET current_context_tokens = ?,
                context_window_size = ?,
                context_utilization_pct = ?,
                context_measurement_source = ?,
                context_measured_at = ?,
                reported_cost_usd = ?,
                recalculated_cost_usd = ?,
                display_cost_usd = ?,
                cost_provenance = ?,
                cost_confidence = ?,
                cost_mismatch_pct = ?,
                pricing_model_source = ?,
                total_cost = ?
            WHERE (project_id = ? OR project_id IS NULL OR project_id = '') AND id = ?
            """,
            (
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
            ),
        )
        await self._commit()

    # ── Detail tables ───────────────────────────────────────────────

    async def upsert_logs(self, session_id: str, logs: list[dict], project_id: str = "") -> None:
        # Deduplicate by (session_id, source_log_id) for non-empty source_log_id values,
        # keeping the first occurrence.  Duplicates produced by the parser are a known
        # upstream issue (Fix C) — this guard prevents the DB constraint from firing.
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

        # Scope DELETE to (project_id, session_id) so project-A's writer never clears
        # project-B's rows sharing the same session_id.  NULL/'' tolerance covers
        # legacy rows written before project_id threading was added.
        await self.db.execute(
            "DELETE FROM session_logs "
            "WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')",
            (session_id, project_id),
        )
        records = []
        for i, log in enumerate(deduped):
            tool_name = None
            tool_call_id = None
            tool_args = None
            tool_output = None
            tool_status = "success"
            metadata_json = None
            tc = log.get("toolCall")
            if tc and isinstance(tc, dict):
                tool_name = tc.get("name")
                tool_call_id = tc.get("id")
                tool_args = tc.get("args")
                tool_output = tc.get("output")
                tool_status = tc.get("status", "success")
            metadata = log.get("metadata")
            if isinstance(metadata, dict) and metadata:
                metadata_json = json.dumps(metadata)
            records.append((
                session_id, i,
                log.get("id", f"log-{i}"),
                log.get("timestamp", ""),
                log.get("speaker", ""),
                log.get("type", ""),
                log.get("content", ""),
                log.get("agentName"),
                tool_name,
                tool_call_id,
                log.get("relatedToolCallId"),
                log.get("linkedSessionId"),
                tool_args,
                tool_output,
                tool_status,
                metadata_json,
                project_id,
            ))
        if records:
            await self.db.executemany(
                """INSERT OR IGNORE INTO session_logs
                    (session_id, log_index, source_log_id, timestamp, speaker, type, content,
                     agent_name, tool_name, tool_call_id, related_tool_call_id,
                     linked_session_id, tool_args, tool_output, tool_status, metadata_json,
                     project_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                records,
            )
        await self._commit()

    async def upsert_tool_usage(self, session_id: str, tools: list[dict], project_id: str = "") -> None:
        await self.db.execute("DELETE FROM session_tool_usage WHERE session_id = ?", (session_id,))
        for t in tools:
            await self.db.execute(
                """INSERT INTO session_tool_usage (session_id, tool_name, call_count, success_count, total_ms, project_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, t.get("name", ""), t.get("count", 0),
                 int(t.get("count", 0) * t.get("successRate", 1.0)),
                 max(0, int(t.get("totalMs", 0) or 0)),
                 project_id),
            )
        await self._commit()

    async def upsert_file_updates(self, session_id: str, updates: list[dict], project_id: str = "") -> None:
        # Scope DELETE to (project_id, session_id) — see upsert_logs for rationale.
        await self.db.execute(
            "DELETE FROM session_file_updates "
            "WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')",
            (session_id, project_id),
        )
        for u in updates:
            await self.db.execute(
                """INSERT INTO session_file_updates (
                    session_id, file_path, action, file_type, action_timestamp,
                    additions, deletions, agent_name, thread_session_id, root_session_id,
                    source_log_id, source_tool_name, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
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
                ),
            )
        await self._commit()

    async def upsert_artifacts(
        self,
        session_id: str,
        artifacts: list[dict],
        project_id: str = "",  # TODO(FC-1): remove default once all callers are confirmed
    ) -> None:
        # Scope DELETE to (project_id, session_id) — see upsert_logs for rationale.
        await self.db.execute(
            "DELETE FROM session_artifacts "
            "WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')",
            (session_id, project_id),
        )
        for a in artifacts:
            await self.db.execute(
                """INSERT INTO session_artifacts (
                    project_id, id, session_id, title, type, description, source, url, source_log_id, source_tool_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (project_id, a.get("id", ""), session_id, a.get("title", ""),
                 a.get("type", "document"), a.get("description", ""), a.get("source", ""),
                 a.get("url"), a.get("sourceLogId"), a.get("sourceToolName")),
            )
        await self._commit()

    async def delete_relationships_for_source(self, project_id: str, source_file: str) -> None:
        await self.db.execute(
            "DELETE FROM session_relationships WHERE project_id = ? AND source_file = ?",
            (project_id, source_file),
        )
        await self._commit()

    async def upsert_relationships(self, project_id: str, source_file: str, relationships: list[dict]) -> None:
        import sqlite3
        for relationship in relationships:
            try:
                await self.db.execute(
                    """
                    INSERT INTO session_relationships (
                        id, project_id, parent_session_id, child_session_id,
                        relationship_type, context_inheritance, source_platform,
                        parent_entry_uuid, child_entry_uuid, source_log_id, metadata_json, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        project_id=excluded.project_id,
                        parent_session_id=excluded.parent_session_id,
                        child_session_id=excluded.child_session_id,
                        relationship_type=excluded.relationship_type,
                        context_inheritance=excluded.context_inheritance,
                        source_platform=excluded.source_platform,
                        parent_entry_uuid=excluded.parent_entry_uuid,
                        child_entry_uuid=excluded.child_entry_uuid,
                        source_log_id=excluded.source_log_id,
                        metadata_json=excluded.metadata_json,
                        source_file=excluded.source_file
                    """,
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
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise sqlite3.IntegrityError(
                    f"FOREIGN KEY failed for session={relationship.get('id')!r}"
                    f" parent={relationship.get('parentSessionId')!r}"
                    f" child={relationship.get('childSessionId')!r}"
                    f" type={relationship.get('relationshipType')!r}"
                ) from exc
        await self._commit()

    async def list_relationships(self, project_id: str, session_id: str) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM session_relationships
            WHERE project_id = ?
              AND (parent_session_id = ? OR child_session_id = ?)
            ORDER BY created_at ASC, id ASC
            """,
            (project_id, session_id, session_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_logs(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        async with self.db.execute(
            "SELECT * FROM session_logs WHERE session_id = ? ORDER BY log_index LIMIT ? OFFSET ?",
            (session_id, safe_limit, safe_offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_tool_usage(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        async with self.db.execute(
            "SELECT * FROM session_tool_usage WHERE session_id = ? LIMIT ? OFFSET ?",
            (session_id, safe_limit, safe_offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_file_updates(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        async with self.db.execute(
            "SELECT * FROM session_file_updates WHERE session_id = ? LIMIT ? OFFSET ?",
            (session_id, safe_limit, safe_offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_artifacts(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        async with self.db.execute(
            "SELECT * FROM session_artifacts WHERE session_id = ? LIMIT ? OFFSET ?",
            (session_id, safe_limit, safe_offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_project_stats(self, project_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict:
        """Get aggregated session statistics for a project."""
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
            WHERE project_id = ? AND workspace_id = ?
        """
        async with self.db.execute(query, (project_id, workspace_id)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "count": row[0] or 0,
                    "cost": row[1] or 0.0,
                    "tokens": row[2] or 0,
                    "duration": row[3] or 0.0,
                }
            return {"count": 0, "cost": 0.0, "tokens": 0, "duration": 0.0}

    async def get_tool_stats(self, project_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict:
        """Get aggregated tool usage statistics for a project."""
        query = """
            SELECT
                SUM(call_count),
                AVG(CAST(success_count AS REAL) / NULLIF(call_count, 0) * 100)
            FROM session_tool_usage stu
            JOIN sessions s ON s.id = stu.session_id
            WHERE s.project_id = ? AND s.workspace_id = ?
        """
        async with self.db.execute(query, (project_id, workspace_id)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "calls": row[0] or 0,
                    "success_rate": row[1] if row[1] is not None else 0.0,
                }
            return {"calls": 0, "success_rate": 0.0}

    def _row_to_dict(self, row) -> dict:
        return dict(row)
