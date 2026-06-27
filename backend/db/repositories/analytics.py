"""SQLite implementation of AnalyticsRepository."""
from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from backend.db.repositories.base import AnalyticsRepository

logger = logging.getLogger("ccdash.db.analytics")


class SqliteAnalyticsRepository(AnalyticsRepository):
    """SQLite implementation of analytics storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def insert_entry(self, entry: dict) -> int:
        """Insert a new analytics data point.

        For period='point' rows, upserts on the partial unique index
        idx_analytics_point_daily (project_id, metric_type, scope_id, date(captured_at))
        so that only the latest same-day value per scope is kept.  scope='project' /
        scope_id='' is the project-level row; scope='feature' / scope_id=<feature_id>
        yields a distinct per-feature row on the same day.
        Non-point rows use a plain INSERT.
        """
        import json
        metadata = entry.get("metadata_json")
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        period = entry.get("period", "point")
        scope = entry.get("scope", "project")
        scope_id = entry.get("scope_id", "")

        if period == "point":
            query = """
                INSERT INTO analytics_entries (
                    project_id, metric_type, value, captured_at, period, metadata_json,
                    scope, scope_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, metric_type, scope_id, date(captured_at)) WHERE period='point'
                DO UPDATE SET
                    value=excluded.value,
                    captured_at=excluded.captured_at,
                    metadata_json=excluded.metadata_json,
                    scope=excluded.scope
                RETURNING id
            """
        else:
            query = """
                INSERT INTO analytics_entries (
                    project_id, metric_type, value, captured_at, period, metadata_json,
                    scope, scope_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """

        async with self.db.execute(
            query,
            (
                entry["project_id"],
                entry["metric_type"],
                entry["value"],
                entry["captured_at"],
                period,
                metadata,
                scope,
                scope_id,
            ),
        ) as cursor:
            row = await cursor.fetchone()
            await self.db.commit()
            return int(row[0]) if row else 0

    async def link_to_entity(self, analytics_id: int, entity_type: str, entity_id: str) -> None:
        """Link an analytics entry to a specific entity."""
        query = """
            INSERT OR IGNORE INTO analytics_entity_links (
                analytics_id, entity_type, entity_id
            ) VALUES (?, ?, ?)
        """
        await self.db.execute(query, (analytics_id, entity_type, entity_id))
        await self.db.commit()

    async def prune_entries_older_than_days(
        self,
        days: int = 90,
        batch_size: int = 1000,
    ) -> int:
        """Batch-DELETE analytics_entries older than `days` days and prune
        orphaned analytics_entity_links rows.

        Deletes in chunks of `batch_size` to avoid holding a long write-lock
        against SQLite's busy_timeout.  Loops until no rows remain.

        The retention window is controlled by the caller (sync_engine owner);
        wire CCDASH_ANALYTICS_RETENTION_DAYS (default 90) from config.py and
        pass it as `days`.  Do NOT call this at import/init time.

        Returns the total number of analytics_entries rows deleted.
        """
        total_deleted = 0
        while True:
            async with self.db.execute(
                """
                DELETE FROM analytics_entries
                WHERE id IN (
                    SELECT id FROM analytics_entries
                    WHERE captured_at < datetime('now', ? || ' days')
                    LIMIT ?
                )
                """,
                (f"-{days}", batch_size),
            ) as cursor:
                deleted = cursor.rowcount
            await self.db.commit()
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
        await self.db.commit()

        return total_deleted

    async def prune_telemetry_older_than_days(
        self,
        days: int = 90,
        batch_size: int = 1000,
    ) -> int:
        """Batch-DELETE telemetry_events older than `days` days.

        Mirrors prune_entries_older_than_days: loops in chunks to respect
        SQLite busy_timeout; commits after each batch.

        The retention window is controlled by the caller (sync_engine owner);
        wire CCDASH_TELEMETRY_RETENTION_DAYS (default 90) from config.py and
        pass it as `days`.  Do NOT call this at import/init time.

        telemetry_events access is co-located in this repository (record_execution_event,
        list_artifact_analytics_rows, get_prometheus_telemetry_rows), so this prune
        lives here rather than in a separate file.

        Returns the total number of telemetry_events rows deleted.
        """
        total_deleted = 0
        while True:
            async with self.db.execute(
                """
                DELETE FROM telemetry_events
                WHERE id IN (
                    SELECT id FROM telemetry_events
                    WHERE occurred_at < datetime('now', ? || ' days')
                    LIMIT ?
                )
                """,
                (f"-{days}", batch_size),
            ) as cursor:
                deleted = cursor.rowcount
            await self.db.commit()
            if deleted == 0:
                break
            total_deleted += deleted

        return total_deleted

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
        """Get time-series data for a metric.

        Defaults to scope='project' to preserve existing dashboard behaviour.
        Pass scope='feature' and scope_id=<feature_id> for per-feature trends.
        """
        query = """
            SELECT captured_at, value, metadata_json
            FROM analytics_entries
            WHERE project_id = ?
              AND metric_type = ?
              AND period = ?
              AND scope = ?
        """
        params: list[Any] = [project_id, metric_type, period, scope]

        if scope_id is not None:
            query += " AND scope_id = ?"
            params.append(scope_id)
        if start:
            query += " AND captured_at >= ?"
            params.append(start)
        if end:
            query += " AND captured_at <= ?"
            params.append(end)

        query += " ORDER BY captured_at ASC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "captured_at": row[0],
                    "value": row[1],
                    "metadata": row[2],  # Client can parse JSON
                }
                for row in rows
            ]

    async def get_metric_types(self) -> list[dict]:
        """List all available metric definitions."""
        query = "SELECT id, display_name, unit, value_type, aggregation, description FROM metric_types"
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_latest_entries(
        self,
        project_id: str,
        metric_types: list[str],
        *,
        scope: str = "project",
        scope_id: str | None = None,
    ) -> dict[str, float]:
        """Get the most recent value for a list of metrics (helper for dashboards).

        Defaults to scope='project' to preserve existing dashboard behaviour.
        Pass scope='feature' and scope_id=<feature_id> for per-feature KPIs.

        Uses a window function (ROW_NUMBER OVER PARTITION BY metric_type ORDER BY
        captured_at DESC) instead of GROUP BY/HAVING MAX to correctly select the
        single latest row per metric type.  The partial index idx_analytics_point
        on (project_id, metric_type, captured_at DESC) WHERE period='point'
        covers this query.
        """
        if not metric_types:
            return {}

        placeholders = ",".join(["?"] * len(metric_types))
        scope_filter = "AND scope = ?"
        scope_params: list[Any] = [scope]
        if scope_id is not None:
            scope_filter += " AND scope_id = ?"
            scope_params.append(scope_id)

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
                WHERE project_id = ?
                  AND metric_type IN ({placeholders})
                  AND period = 'point'
                  {scope_filter}
            ) ranked
            WHERE rn = 1
        """
        params: list[Any] = [project_id] + metric_types + scope_params
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
            ),
        )
        await self.db.commit()

    async def list_artifact_analytics_rows(
        self,
        *,
        project_id: str,
        start: str | None = None,
        end: str | None = None,
        artifact_type: str | None = None,
        tool: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        artifact_filters = ["project_id = ?", "event_type = 'artifact.linked'"]
        artifact_params: list[Any] = [project_id]
        if start:
            artifact_filters.append("occurred_at >= ?")
            artifact_params.append(start)
        if end:
            artifact_filters.append("occurred_at <= ?")
            artifact_params.append(end)
        if artifact_type:
            artifact_filters.append("LOWER(COALESCE(json_extract(payload_json, '$.type'), status, 'unknown')) = ?")
            artifact_params.append(str(artifact_type).strip().lower())
        if tool:
            artifact_filters.append("LOWER(COALESCE(tool_name, 'unknown')) = ?")
            artifact_params.append(str(tool).strip().lower())

        lifecycle_filters = ["project_id = ?", "event_type = 'session.lifecycle'"]
        lifecycle_params: list[Any] = [project_id]
        if start:
            lifecycle_filters.append("occurred_at >= ?")
            lifecycle_params.append(start)
        if end:
            lifecycle_filters.append("occurred_at <= ?")
            lifecycle_params.append(end)

        event_filters = ["project_id = ?"]
        event_params: list[Any] = [project_id]
        if start:
            event_filters.append("occurred_at >= ?")
            event_params.append(start)
        if end:
            event_filters.append("occurred_at <= ?")
            event_params.append(end)

        async with self.db.execute(
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
            tuple(artifact_params),
        ) as cur:
            artifact_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
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
            tuple(lifecycle_params),
        ) as cur:
            lifecycle_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
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
                AND f.project_id = ?
            """,
            (project_id,),
        ) as cur:
            feature_link_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
            "SELECT id, name FROM features WHERE project_id = ?",
            (project_id,),
        ) as cur:
            feature_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
            f"""
            SELECT session_id, model, occurred_at, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters)} AND event_type = 'log.command'
            ORDER BY occurred_at DESC
            """,
            tuple(event_params),
        ) as cur:
            command_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
            f"""
            SELECT session_id, model, agent, occurred_at, event_type, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters)} AND event_type LIKE 'log.%'
            ORDER BY occurred_at DESC
            """,
            tuple(event_params),
        ) as cur:
            agent_rows = [dict(row) for row in await cur.fetchall()]

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

        async with self.db.execute(
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
                AND f.project_id = ?
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                link_stats = {
                    "avg_confidence": float(row[0] or 0.0),
                    "low_confidence": int(row[1] or 0),
                    "total_links": int(row[2] or 0),
                }

        async with self.db.execute(
            """
            SELECT
                AVG(child_count) AS avg_fanout,
                MAX(child_count) AS max_fanout
            FROM (
                SELECT COUNT(*) AS child_count
                FROM sessions
                WHERE project_id = ?
                GROUP BY root_session_id
            )
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                thread_stats = {
                    "avg_fanout": float(row[0] or 0.0),
                    "max_fanout": int(row[1] or 0),
                }

        return {
            "link_stats": link_stats,
            "thread_stats": thread_stats,
        }

    async def get_prometheus_telemetry_rows(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        async with self.db.execute(
            """
            SELECT
                tool_name,
                status,
                SUM(CAST(COALESCE(json_extract(payload_json, '$.callCount'), 0) AS INTEGER)) AS calls,
                AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
            FROM telemetry_events
            WHERE project_id = ? AND event_type = 'tool.aggregate'
            GROUP BY tool_name, status
            ORDER BY calls DESC
            """,
            (project_id,),
        ) as cur:
            tool_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
            """
            SELECT
                model,
                SUM(COALESCE(token_input, 0)) AS input_tokens,
                SUM(COALESCE(token_output, 0)) AS output_tokens,
                SUM(COALESCE(cost_usd, 0)) AS total_cost
            FROM telemetry_events
            WHERE project_id = ? AND event_type = 'session.lifecycle'
            GROUP BY model
            ORDER BY (input_tokens + output_tokens) DESC
            """,
            (project_id,),
        ) as cur:
            model_rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(
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
            WHERE project_id = ?
            GROUP BY event_type, status, tool_name, model, agent, skill, phase, source
            ORDER BY event_count DESC
            """,
            (project_id,),
        ) as cur:
            event_rows = [dict(row) for row in await cur.fetchall()]

        return {
            "tool_rows": tool_rows,
            "model_rows": model_rows,
            "event_rows": event_rows,
        }
