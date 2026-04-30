"""PostgreSQL implementation of FeatureRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from backend.db.repositories.feature_queries import (
    DateRange,
    FeatureListPage,
    FeatureListQuery,
    FeatureSortKey,
    PhaseSummary,
    PhaseSummaryBulkQuery,
)


# ---------------------------------------------------------------------------
# Sort key → SQL column mapping (Postgres path)
# ---------------------------------------------------------------------------

_SORT_COLUMN_PG: dict[FeatureSortKey, str] = {
    FeatureSortKey.UPDATED_DATE: "updated_at",
    FeatureSortKey.COMPLETED_AT: "completed_at",
    FeatureSortKey.CREATED_AT: "created_at",
    FeatureSortKey.NAME: "LOWER(name)",
    FeatureSortKey.PROGRESS: (
        "CASE WHEN total_tasks > 0"
        " THEN CAST(completed_tasks AS DOUBLE PRECISION) / total_tasks"
        " ELSE 0.0 END"
    ),
    FeatureSortKey.TASK_COUNT: "total_tasks",
    FeatureSortKey.LATEST_ACTIVITY: "updated_at",
    FeatureSortKey.SESSION_COUNT: "updated_at",
}


def _build_feature_list_where_clause_pg(
    project_id: str,
    query: FeatureListQuery,
) -> tuple[str, list[Any]]:
    """Build the WHERE clause and parameter list for Postgres feature queries.

    Returns a ``(sql_fragment, params)`` tuple using ``$N`` positional placeholders.
    """
    conditions: list[str] = []
    params: list[Any] = []

    def _p(value: Any) -> str:
        """Append ``value`` to params and return its ``$N`` placeholder."""
        params.append(value)
        return f"${len(params)}"

    conditions.append(f"project_id = {_p(project_id)}")

    # ── text search ─────────────────────────────────────────────────────────
    if query.q:
        pattern = f"%{query.q}%"
        ph = _p(pattern)
        conditions.append(f"(id ILIKE {ph} OR name ILIKE {ph})")

    # ── status IN-list ───────────────────────────────────────────────────────
    if query.status:
        phs = [_p(s) for s in query.status]
        conditions.append(f"status IN ({','.join(phs)})")

    # ── stage: same column as status (board stage is client-derived)
    # TODO P2: if a dedicated board_stage column is added, replace this.
    if query.stage:
        phs = [_p(s) for s in query.stage]
        conditions.append(f"status IN ({','.join(phs)})")

    # ── category (case-insensitive) ──────────────────────────────────────────
    if query.category:
        phs = [_p(c.lower()) for c in query.category]
        conditions.append(f"LOWER(category) IN ({','.join(phs)})")

    # ── tags: promoted column with jsonb containment (@>) ──────────────────
    if query.tags:
        tag_parts: list[str] = []
        for tag in query.tags:
            ph = _p(json.dumps([tag]))
            tag_parts.append(f"COALESCE(tags_json, '[]')::jsonb @> {ph}::jsonb")
        conditions.append(f"({' OR '.join(tag_parts)})")

    # ── has_deferred ─────────────────────────────────────────────────────────
    if query.has_deferred is True:
        conditions.append("COALESCE(deferred_tasks, 0) > 0")
    elif query.has_deferred is False:
        conditions.append("COALESCE(deferred_tasks, 0) = 0")

    # ── completed date range ─────────────────────────────────────────────────
    _add_date_range_pg(conditions, _p, "completed_at", query.completed)

    # ── updated date range ───────────────────────────────────────────────────
    _add_date_range_pg(conditions, _p, "updated_at", query.updated)

    # ── planned date range ──────────────────────────────────────────────────
    if query.planned:
        _add_date_range_pg(conditions, _p, "planned_at", query.planned)

    # ── started date range ──────────────────────────────────────────────────
    if query.started:
        _add_date_range_pg(conditions, _p, "started_at", query.started)

    # ── numeric ranges ───────────────────────────────────────────────────────
    _progress_expr = (
        "CASE WHEN total_tasks > 0"
        " THEN CAST(completed_tasks AS DOUBLE PRECISION) / total_tasks"
        " ELSE 0.0 END"
    )
    if query.progress_min is not None:
        conditions.append(f"{_progress_expr} >= {_p(query.progress_min)}")
    if query.progress_max is not None:
        conditions.append(f"{_progress_expr} <= {_p(query.progress_max)}")
    if query.task_count_min is not None:
        conditions.append(f"COALESCE(total_tasks, 0) >= {_p(query.task_count_min)}")
    if query.task_count_max is not None:
        conditions.append(f"COALESCE(total_tasks, 0) <= {_p(query.task_count_max)}")

    return "WHERE " + " AND ".join(conditions), params


def _add_date_range_pg(
    conditions: list[str],
    _p: Any,
    col: str,
    dr: DateRange | None,
) -> None:
    if dr is None:
        return
    if dr.from_date:
        conditions.append(f"{col} >= {_p(dr.from_date)}")
    if dr.to_date:
        conditions.append(f"{col} <= {_p(dr.to_date)}")


def _build_order_clause_pg(query: FeatureListQuery) -> str:
    col = _SORT_COLUMN_PG.get(query.sort_by, "updated_at")
    direction = query.effective_sort_direction.value.upper()
    return f"ORDER BY {col} {direction}, id ASC"


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
                tags_json, deferred_tasks, planned_at, started_at,
                total_tasks, completed_tasks, parent_feature_id,
                created_at, updated_at, completed_at, data_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT(id) DO UPDATE SET
                name=EXCLUDED.name, status=EXCLUDED.status,
                category=EXCLUDED.category,
                tags_json=EXCLUDED.tags_json,
                deferred_tasks=EXCLUDED.deferred_tasks,
                planned_at=EXCLUDED.planned_at,
                started_at=EXCLUDED.started_at,
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
            json.dumps(feature_data.get("tags", [])),
            int(feature_data.get("deferredTasks", 0) or 0),
            feature_data.get("plannedAt", "") or "",
            feature_data.get("startedAt", "") or "",
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

    async def get_many_by_ids(self, ids: list[str]) -> dict[str, dict]:
        """Fetch multiple features in a single query. Returns a dict keyed by feature id."""
        if not ids:
            return {}
        rows = await self.db.fetch(
            "SELECT * FROM features WHERE id = ANY($1::text[])", ids
        )
        return {row["id"]: dict(row) for row in rows}

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM features WHERE project_id = $1 ORDER BY name LIMIT $2",
                project_id,
                5000,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM features ORDER BY name LIMIT $1", 5000)
        return [dict(r) for r in rows]

    async def list_paginated(
        self,
        project_id: str | None,
        offset: int,
        limit: int,
        *,
        keyword: str | None = None,
    ) -> list[dict]:
        if keyword:
            pattern = f"%{keyword}%"
            if project_id:
                rows = await self.db.fetch(
                    "SELECT * FROM features WHERE project_id = $1"
                    " AND (name ILIKE $2 OR id ILIKE $2)"
                    " ORDER BY name LIMIT $3 OFFSET $4",
                    project_id,
                    pattern,
                    limit,
                    offset,
                )
            else:
                rows = await self.db.fetch(
                    "SELECT * FROM features WHERE name ILIKE $1 OR id ILIKE $1"
                    " ORDER BY name LIMIT $2 OFFSET $3",
                    pattern,
                    limit,
                    offset,
                )
            return [dict(r) for r in rows]

        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM features WHERE project_id = $1 ORDER BY name LIMIT $2 OFFSET $3",
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM features ORDER BY name LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    async def count(self, project_id: str | None = None, *, keyword: str | None = None) -> int:
        if keyword:
            pattern = f"%{keyword}%"
            if project_id:
                value = await self.db.fetchval(
                    "SELECT COUNT(*) FROM features WHERE project_id = $1"
                    " AND (name ILIKE $2 OR id ILIKE $2)",
                    project_id,
                    pattern,
                )
            else:
                value = await self.db.fetchval(
                    "SELECT COUNT(*) FROM features WHERE name ILIKE $1 OR id ILIKE $1",
                    pattern,
                )
            return int(value or 0)

        if project_id:
            value = await self.db.fetchval("SELECT COUNT(*) FROM features WHERE project_id = $1", project_id)
        else:
            value = await self.db.fetchval("SELECT COUNT(*) FROM features")
        return int(value or 0)

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

    async def list_phase_summaries_for_features(
        self,
        project_id: str,
        query: PhaseSummaryBulkQuery,
    ) -> dict[str, list[PhaseSummary]]:
        """Return phase summaries for all requested features in a single query.

        Result is keyed by feature_id.  Features with no phases map to ``[]``.
        Features not belonging to ``project_id`` are excluded and also map to
        ``[]`` (their key is still present in the returned dict).

        Uses asyncpg ``$N`` positional placeholders.  Task counts are read
        directly from the ``total_tasks`` / ``completed_tasks`` columns on the
        ``feature_phases`` table — no extra aggregation join is needed.
        """
        feature_ids = query.feature_ids

        # Defensive cap (belt-and-suspenders; Pydantic validator also enforces this)
        if len(feature_ids) > 500:
            raise ValueError(
                f"feature_ids exceeds the maximum batch size of 500. "
                f"Received {len(feature_ids)} IDs."
            )

        # Pre-populate result dict so missing features get [] rather than absent keys
        result: dict[str, list[PhaseSummary]] = {fid: [] for fid in feature_ids}

        # Build $1..$N placeholders for the IN-list, then $N+1 for project_id
        id_placeholders = ", ".join(f"${i + 1}" for i in range(len(feature_ids)))
        project_ph = f"${len(feature_ids) + 1}"

        sql = (
            "SELECT fp.id, fp.feature_id, fp.title, fp.status, fp.phase,"
            " fp.total_tasks, fp.completed_tasks, fp.progress AS stored_progress"
            " FROM feature_phases fp"
            " JOIN features f ON fp.feature_id = f.id"
            f" WHERE fp.feature_id IN ({id_placeholders})"
            f" AND f.project_id = {project_ph}"
            " ORDER BY fp.feature_id, fp.phase"
        )

        db_rows = await self.db.fetch(sql, *feature_ids, project_id)

        for row in db_rows:
            r = dict(row)
            feature_id = r["feature_id"]

            total = int(r.get("total_tasks") or 0)
            completed = int(r.get("completed_tasks") or 0)

            try:
                order_index: int | None = int(r["phase"])
            except (ValueError, TypeError):
                order_index = None

            progress: float | None = None
            if query.include_progress:
                if query.include_counts and total > 0:
                    progress = round(completed / total, 4)
                elif r.get("stored_progress") is not None:
                    progress = float(r["stored_progress"])

            summary = PhaseSummary(
                feature_id=feature_id,
                phase_id=r["id"],
                name=r.get("title") or "",
                status=r.get("status"),
                order_index=order_index,
                total_tasks=total if query.include_counts else 0,
                completed_tasks=completed if query.include_counts else 0,
                progress=progress,
            )
            result[feature_id].append(summary)

        return result

    async def delete(self, feature_id: str) -> None:
        await self.db.execute("DELETE FROM features WHERE id = $1", feature_id)

    async def list_feature_cards(
        self,
        project_id: str,
        query: FeatureListQuery,
    ) -> FeatureListPage:
        """Return a paginated, fully-filtered list of feature card dicts.

        Uses a single query with ``COUNT(*) OVER ()`` window function to avoid
        a separate count round-trip.
        """
        where_sql, params = _build_feature_list_where_clause_pg(project_id, query)
        order_sql = _build_order_clause_pg(query)

        # Add LIMIT/OFFSET as the next positional params
        params.append(query.limit)
        limit_ph = f"${len(params)}"
        params.append(query.offset)
        offset_ph = f"${len(params)}"

        sql = (
            f"SELECT *, COUNT(*) OVER () AS _total_count"
            f" FROM features {where_sql}"
            f" {order_sql}"
            f" LIMIT {limit_ph} OFFSET {offset_ph}"
        )
        db_rows = await self.db.fetch(sql, *params)
        total = int(db_rows[0]["_total_count"]) if db_rows else 0
        rows = [{k: v for k, v in dict(r).items() if k != "_total_count"} for r in db_rows]
        return FeatureListPage(
            rows=rows,
            total=total,
            offset=query.offset,
            limit=query.limit,
        )

    async def count_feature_cards(
        self,
        project_id: str,
        query: FeatureListQuery,
    ) -> int:
        """Return post-filter, pre-pagination count for ``query``."""
        where_sql, params = _build_feature_list_where_clause_pg(project_id, query)
        value = await self.db.fetchval(
            f"SELECT COUNT(*) FROM features {where_sql}",
            *params,
        )
        return int(value or 0)

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
