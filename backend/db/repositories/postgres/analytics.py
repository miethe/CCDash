"""PostgreSQL implementation of AnalyticsRepository."""
from __future__ import annotations

import json
from typing import Any
import asyncpg
from backend.db.repositories.base import AnalyticsRepository

class PostgresAnalyticsRepository(AnalyticsRepository):
    """PostgreSQL implementation of analytics storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def insert_entry(self, entry: dict) -> int:
        metadata = entry.get("metadata_json")
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        period = entry.get("period", "point")
        scope = entry.get("scope", "project")
        scope_id = entry.get("scope_id", "")

        if period == "point":
            # Upsert on the scope-aware dedup key so point rows never grow
            # unbounded and match the SQLite behaviour exactly.
            query = """
                INSERT INTO analytics_entries (
                    project_id, metric_type, value, captured_at, period,
                    metadata_json, scope, scope_id
                ) VALUES ($1, $2, $3, $4, 'point', $5, $6, $7)
                ON CONFLICT (project_id, metric_type, scope_id, (left(captured_at, 10)))
                WHERE period = 'point'
                DO UPDATE SET
                    value         = EXCLUDED.value,
                    captured_at   = EXCLUDED.captured_at,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING id
            """
        else:
            query = """
                INSERT INTO analytics_entries (
                    project_id, metric_type, value, captured_at, period,
                    metadata_json, scope, scope_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """

        if period == "point":
            id_val = await self.db.fetchval(
                query,
                entry["project_id"],
                entry["metric_type"],
                entry["value"],
                entry["captured_at"],
                metadata,
                scope,
                scope_id,
            )
        else:
            id_val = await self.db.fetchval(
                query,
                entry["project_id"],
                entry["metric_type"],
                entry["value"],
                entry["captured_at"],
                period,
                metadata,
                scope,
                scope_id,
            )
        return int(id_val) if id_val is not None else 0

    async def link_to_entity(self, analytics_id: int, entity_type: str, entity_id: str) -> None:
        query = """
            INSERT INTO analytics_entity_links (
                analytics_id, entity_type, entity_id
            ) VALUES ($1, $2, $3)
            ON CONFLICT (analytics_id, entity_type, entity_id) DO NOTHING
        """
        await self.db.execute(query, analytics_id, entity_type, entity_id)

    async def get_trends(
        self,
        project_id: str,
        metric_type: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
        *,
        scope: str = "project",
        scope_id: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT captured_at, value, metadata_json
            FROM analytics_entries
            WHERE project_id = $1
              AND metric_type = $2
              AND period = $3
        """
        params: list = [project_id, metric_type, period]

        p_idx = 4
        if start:
            query += f" AND captured_at >= ${p_idx}"
            params.append(start)
            p_idx += 1
        if end:
            query += f" AND captured_at <= ${p_idx}"
            params.append(end)
            p_idx += 1

        query += f" AND scope = ${p_idx}"
        params.append(scope)
        p_idx += 1

        if scope_id is not None:
            query += f" AND scope_id = ${p_idx}"
            params.append(scope_id)

        query += " ORDER BY captured_at ASC"

        rows = await self.db.fetch(query, *params)
        return [
            {
                "captured_at": row["captured_at"],
                "value": row["value"],
                "metadata": row["metadata_json"],
            }
            for row in rows
        ]

    async def get_metric_types(self) -> list[dict]:
        query = "SELECT id, display_name, unit, value_type, aggregation, description FROM metric_types"
        rows = await self.db.fetch(query)
        return [dict(r) for r in rows]

    async def upsert_point_entry(self, entry: dict) -> int:
        """Insert or update a period='point' analytics entry.

        Uses the v34 partial unique index idx_analytics_point_daily on
        (project_id, metric_type, scope_id, (left(captured_at, 10))) WHERE period='point'
        to guarantee at most one value per metric per scope per calendar day.
        On conflict the row is updated in-place so callers always see the
        latest same-day value.

        Signature and return value mirror SqliteAnalyticsRepository.insert_entry
        for period='point' rows so callers are backend-agnostic.
        """
        metadata = entry.get("metadata_json")
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        scope = entry.get("scope", "project")
        scope_id = entry.get("scope_id", "")

        query = """
            INSERT INTO analytics_entries (
                project_id, metric_type, value, captured_at, period,
                metadata_json, scope, scope_id
            ) VALUES ($1, $2, $3, $4, 'point', $5, $6, $7)
            ON CONFLICT (project_id, metric_type, scope_id, (left(captured_at, 10)))
            WHERE period = 'point'
            DO UPDATE SET
                value         = EXCLUDED.value,
                captured_at   = EXCLUDED.captured_at,
                metadata_json = EXCLUDED.metadata_json
            RETURNING id
        """
        id_val = await self.db.fetchval(
            query,
            entry["project_id"],
            entry["metric_type"],
            entry["value"],
            entry["captured_at"],
            metadata,
            scope,
            scope_id,
        )
        return int(id_val) if id_val is not None else 0

    async def prune_entries_older_than_days(
        self,
        days: int = 90,
        batch_size: int = 1000,
    ) -> int:
        """Batch-DELETE analytics_entries older than `days` days and prune
        orphaned analytics_entity_links rows.

        Deletes in chunks of `batch_size` to avoid long-running transactions.
        Loops until no rows remain, then removes orphaned entity links.

        Returns the total number of analytics_entries rows deleted.
        """
        import datetime as _dt

        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        total_deleted = 0

        while True:
            status = await self.db.execute(
                """
                DELETE FROM analytics_entries
                WHERE id IN (
                    SELECT id FROM analytics_entries
                    WHERE captured_at < $1
                    LIMIT $2
                )
                """,
                cutoff,
                batch_size,
            )
            # asyncpg returns a status string like "DELETE 42"
            deleted = int(status.split()[-1])
            if deleted == 0:
                break
            total_deleted += deleted

        # Prune orphaned entity links whose analytics entry no longer exists.
        await self.db.execute(
            """
            DELETE FROM analytics_entity_links
            WHERE analytics_id NOT IN (SELECT id FROM analytics_entries)
            """
        )

        return total_deleted

    async def prune_telemetry_older_than_days(
        self,
        days: int = 90,
        batch_size: int = 1000,
    ) -> int:
        """Batch-DELETE telemetry_events older than `days` days.

        Mirrors prune_entries_older_than_days: loops in chunks to avoid
        long-running transactions; returns the total number of rows deleted.
        """
        import datetime as _dt

        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        total_deleted = 0

        while True:
            status = await self.db.execute(
                """
                DELETE FROM telemetry_events
                WHERE id IN (
                    SELECT id FROM telemetry_events
                    WHERE occurred_at < $1
                    LIMIT $2
                )
                """,
                cutoff,
                batch_size,
            )
            deleted = int(status.split()[-1])
            if deleted == 0:
                break
            total_deleted += deleted

        return total_deleted

    async def get_latest_entries(
        self,
        project_id: str,
        metric_types: list[str],
        *,
        scope: str = "project",
        scope_id: str | None = None,
    ) -> dict[str, float]:
        """Get the most recent value for a list of metrics (helper for dashboards).

        Uses a window function (ROW_NUMBER OVER PARTITION BY metric_type ORDER BY
        captured_at DESC) inside a CTE, filtered to rn=1 AND period='point'.
        Mirrors the SQLite sibling exactly — same dict shape {metric_type: value}.
        The partial index idx_analytics_point on (project_id, metric_type,
        captured_at DESC) WHERE period='point' covers this query.
        """
        if not metric_types:
            return {}

        # Build scope filter clauses; $1=project_id, $2=metric_types array
        # are fixed; scope predicates start at $3.
        scope_clause = "AND scope = $3"
        params: list = [project_id, metric_types, scope]

        if scope_id is not None:
            scope_clause += " AND scope_id = $4"
            params.append(scope_id)

        query = f"""
            SELECT metric_type, value
            FROM (
                SELECT
                    metric_type,
                    value,
                    ROW_NUMBER() OVER (
                        PARTITION BY metric_type
                        ORDER BY captured_at DESC
                    ) AS rn
                FROM analytics_entries
                WHERE project_id = $1
                  AND metric_type = ANY($2::text[])
                  AND period = 'point'
                  {scope_clause}
            ) ranked
            WHERE rn = 1
        """
        rows = await self.db.fetch(query, *params)
        return {row["metric_type"]: row["value"] for row in rows}

    async def record_execution_event(
        self,
        *,
        project_id: str,
        event_type: str,
        feature_id: str,
        occurred_at: str,
        source_key: str,
        payload_json: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20, $21, $22, $23
            )
            """,
            project_id,
            "ui-execution-workbench",
            "ui-execution-workbench",
            feature_id,
            "",
            "",
            "",
            "",
            event_type,
            "",
            "",
            "frontend",
            "",
            "ok",
            0,
            0,
            0,
            0.0,
            occurred_at,
            0,
            "frontend",
            source_key,
            payload_json,
        )

    async def list_artifact_analytics_rows(
        self,
        *,
        project_id: str,
        start: str | None = None,
        end: str | None = None,
        artifact_type: str | None = None,
        tool: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        artifact_filters = ["project_id = $1", "event_type = 'artifact.linked'"]
        artifact_params: list[Any] = [project_id]
        bind_index = 2
        if start:
            artifact_filters.append(f"occurred_at >= ${bind_index}")
            artifact_params.append(start)
            bind_index += 1
        if end:
            artifact_filters.append(f"occurred_at <= ${bind_index}")
            artifact_params.append(end)
            bind_index += 1
        if artifact_type:
            artifact_filters.append(f"LOWER(COALESCE(payload_json::jsonb->>'type', status, 'unknown')) = ${bind_index}")
            artifact_params.append(str(artifact_type).strip().lower())
            bind_index += 1
        if tool:
            artifact_filters.append(f"LOWER(COALESCE(tool_name, 'unknown')) = ${bind_index}")
            artifact_params.append(str(tool).strip().lower())

        lifecycle_filters = ["project_id = $1", "event_type = 'session.lifecycle'"]
        lifecycle_params: list[Any] = [project_id]
        bind_index = 2
        if start:
            lifecycle_filters.append(f"occurred_at >= ${bind_index}")
            lifecycle_params.append(start)
            bind_index += 1
        if end:
            lifecycle_filters.append(f"occurred_at <= ${bind_index}")
            lifecycle_params.append(end)

        event_filters = ["project_id = $1"]
        event_params: list[Any] = [project_id]
        bind_index = 2
        if start:
            event_filters.append(f"occurred_at >= ${bind_index}")
            event_params.append(start)
            bind_index += 1
        if end:
            event_filters.append(f"occurred_at <= ${bind_index}")
            event_params.append(end)

        artifact_rows = [
            dict(row)
            for row in await self.db.fetch(
                f"""
                SELECT
                    session_id,
                    feature_id,
                    model,
                    tool_name,
                    agent,
                    skill,
                    status,
                    occurred_at,
                    payload_json
                FROM telemetry_events
                WHERE {" AND ".join(artifact_filters)}
                ORDER BY occurred_at DESC
                """,
                *artifact_params,
            )
        ]

        lifecycle_rows = [
            dict(row)
            for row in await self.db.fetch(
                f"""
                SELECT
                    session_id,
                    feature_id,
                    model,
                    status,
                    occurred_at,
                    token_input,
                    token_output,
                    cost_usd,
                    payload_json
                FROM telemetry_events
                WHERE {" AND ".join(lifecycle_filters)}
                ORDER BY occurred_at DESC
                """,
                *lifecycle_params,
            )
        ]

        feature_link_rows = [
            dict(row)
            for row in await self.db.fetch(
                """
                SELECT
                    el.target_id AS session_id,
                    el.source_id AS feature_id
                FROM entity_links el
                JOIN features f ON f.id = el.source_id
                WHERE
                    el.source_type = 'feature'
                    AND el.target_type = 'session'
                    AND el.link_type = 'related'
                    AND f.project_id = $1
                """,
                project_id,
            )
        ]

        feature_rows = [
            dict(row)
            for row in await self.db.fetch(
                "SELECT id, name FROM features WHERE project_id = $1",
                project_id,
            )
        ]

        command_rows = [
            dict(row)
            for row in await self.db.fetch(
                f"""
                SELECT session_id, model, occurred_at, payload_json
                FROM telemetry_events
                WHERE {" AND ".join(event_filters)} AND event_type = 'log.command'
                ORDER BY occurred_at DESC
                """,
                *event_params,
            )
        ]

        agent_rows = [
            dict(row)
            for row in await self.db.fetch(
                f"""
                SELECT session_id, model, agent, occurred_at, event_type, payload_json
                FROM telemetry_events
                WHERE {" AND ".join(event_filters)} AND event_type LIKE 'log.%'
                ORDER BY occurred_at DESC
                """,
                *event_params,
            )
        ]

        return {
            "artifact_rows": artifact_rows,
            "lifecycle_rows": lifecycle_rows,
            "feature_link_rows": feature_link_rows,
            "feature_rows": feature_rows,
            "command_rows": command_rows,
            "agent_rows": agent_rows,
        }

    async def get_prometheus_link_and_thread_stats(self, project_id: str) -> dict[str, dict[str, Any]]:
        link_stats = {"avg_confidence": 0.0, "low_confidence": 0, "total_links": 0}
        thread_stats = {"avg_fanout": 0.0, "max_fanout": 0}

        row = await self.db.fetchrow(
            """
            SELECT
                AVG(confidence) AS avg_confidence,
                SUM(CASE WHEN confidence < 0.6 THEN 1 ELSE 0 END) AS low_confidence,
                COUNT(*) AS total_links
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND f.project_id = $1
            """,
            project_id,
        )
        if row:
            link_stats = {
                "avg_confidence": float(row["avg_confidence"] or 0.0),
                "low_confidence": int(row["low_confidence"] or 0),
                "total_links": int(row["total_links"] or 0),
            }

        row = await self.db.fetchrow(
            """
            SELECT
                AVG(child_count) AS avg_fanout,
                MAX(child_count) AS max_fanout
            FROM (
                SELECT COUNT(*) AS child_count
                FROM sessions
                WHERE project_id = $1
                GROUP BY root_session_id
            ) fanout
            """,
            project_id,
        )
        if row:
            thread_stats = {
                "avg_fanout": float(row["avg_fanout"] or 0.0),
                "max_fanout": int(row["max_fanout"] or 0),
            }

        return {
            "link_stats": link_stats,
            "thread_stats": thread_stats,
        }

    async def get_prometheus_telemetry_rows(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        tool_rows = [
            dict(row)
            for row in await self.db.fetch(
                """
                SELECT
                    tool_name,
                    status,
                    SUM(COALESCE((payload_json::jsonb->>'callCount')::INTEGER, 0)) AS calls,
                    AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
                FROM telemetry_events
                WHERE project_id = $1 AND event_type = 'tool.aggregate'
                GROUP BY tool_name, status
                ORDER BY calls DESC
                """,
                project_id,
            )
        ]

        model_rows = [
            dict(row)
            for row in await self.db.fetch(
                """
                SELECT
                    model,
                    SUM(COALESCE(token_input, 0)) AS input_tokens,
                    SUM(COALESCE(token_output, 0)) AS output_tokens,
                    SUM(COALESCE(cost_usd, 0)) AS total_cost
                FROM telemetry_events
                WHERE project_id = $1 AND event_type = 'session.lifecycle'
                GROUP BY model
                ORDER BY (SUM(COALESCE(token_input, 0)) + SUM(COALESCE(token_output, 0))) DESC
                """,
                project_id,
            )
        ]

        event_rows = [
            dict(row)
            for row in await self.db.fetch(
                """
                SELECT
                    event_type,
                    status,
                    tool_name,
                    model,
                    agent,
                    skill,
                    phase,
                    source,
                    COUNT(*) AS event_count
                FROM telemetry_events
                WHERE project_id = $1
                GROUP BY event_type, status, tool_name, model, agent, skill, phase, source
                ORDER BY event_count DESC
                """,
                project_id,
            )
        ]

        return {
            "tool_rows": tool_rows,
            "model_rows": model_rows,
            "event_rows": event_rows,
        }
