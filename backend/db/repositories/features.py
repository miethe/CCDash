"""SQLite implementation of FeatureRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.db.repositories.feature_queries import (
    DateRange,
    FeatureListPage,
    FeatureListQuery,
    FeatureSortKey,
    PhaseSummary,
    PhaseSummaryBulkQuery,
)


# ---------------------------------------------------------------------------
# Sort key → SQL column mapping (SQLite path)
# ---------------------------------------------------------------------------

_SORT_COLUMN: dict[FeatureSortKey, str] = {
    FeatureSortKey.UPDATED_DATE: "updated_at",
    FeatureSortKey.COMPLETED_AT: "completed_at",
    FeatureSortKey.CREATED_AT: "created_at",
    FeatureSortKey.NAME: "LOWER(name)",
    FeatureSortKey.PROGRESS: (
        "CASE WHEN total_tasks > 0"
        " THEN CAST(completed_tasks AS REAL) / total_tasks"
        " ELSE 0.0 END"
    ),
    FeatureSortKey.TASK_COUNT: "total_tasks",
    # TODO P2: replace fallback with real latest_activity_at column when rollup join lands
    FeatureSortKey.LATEST_ACTIVITY: "updated_at",
    # TODO P2: replace fallback with session_count from rollup join in Phase 2
    FeatureSortKey.SESSION_COUNT: "updated_at",
}


def _build_feature_list_where_clause(
    project_id: str,
    query: FeatureListQuery,
) -> tuple[str, list[Any]]:
    """Build the WHERE clause and parameter list for feature list / count queries.

    Returns a ``(sql_fragment, params)`` tuple.  ``sql_fragment`` always starts
    with ``WHERE`` and always includes the ``project_id`` predicate.  ``params``
    uses positional ``?`` placeholders (SQLite style).
    """
    conditions: list[str] = ["project_id = ?"]
    params: list[Any] = [project_id]

    # ── text search ─────────────────────────────────────────────────────────
    if query.q:
        pattern = f"%{query.q.lower()}%"
        conditions.append("(LOWER(id) LIKE ? OR LOWER(name) LIKE ?)")
        params.extend([pattern, pattern])

    # ── status IN-list ───────────────────────────────────────────────────────
    if query.status:
        placeholders = ",".join("?" for _ in query.status)
        conditions.append(f"status IN ({placeholders})")
        params.extend(query.status)

    # ── stage: mapped from status values — board stage is client-side derived
    # from status; we support it by treating stage values as status aliases here
    # (same column, same IN-list semantics).
    # TODO P2: if a dedicated board_stage column is added, replace this.
    if query.stage:
        placeholders = ",".join("?" for _ in query.stage)
        conditions.append(f"status IN ({placeholders})")
        params.extend(query.stage)

    # ── category (case-insensitive) ──────────────────────────────────────────
    if query.category:
        placeholders = ",".join("?" for _ in query.category)
        lower_cats = [c.lower() for c in query.category]
        conditions.append(f"LOWER(category) IN ({placeholders})")
        params.extend(lower_cats)

    # ── tags: basic JSON extraction via json_extract / LIKE ─────────────────
    # json_extract returns the raw JSON of the tags array; we fall back to a
    # LIKE search against the stringified array.  A missing/null tags value
    # is treated gracefully (COALESCE to '[]').
    if query.tags:
        tag_parts: list[str] = []
        for tag in query.tags:
            # Match the tag value anywhere in the JSON array representation.
            # This is intentionally coarse; Phase 2 will add a GIN / junction table.
            # TODO P2: replace with json_each CTE or feature_tags junction table.
            tag_parts.append("COALESCE(json_extract(data_json, '$.tags'), '[]') LIKE ?")
            params.append(f'%"{tag}"%')
        conditions.append(f"({' OR '.join(tag_parts)})")

    # ── has_deferred ─────────────────────────────────────────────────────────
    # TODO P2: add a `deferred_tasks` indexed column; JSON extraction is
    # expensive at scale.  For now skip when the column does not exist.
    if query.has_deferred is True:
        conditions.append(
            "CAST(COALESCE(json_extract(data_json, '$.deferredTasks'), 0) AS INTEGER) > 0"
        )
    elif query.has_deferred is False:
        conditions.append(
            "CAST(COALESCE(json_extract(data_json, '$.deferredTasks'), 0) AS INTEGER) = 0"
        )

    # ── completed date range (column exists) ────────────────────────────────
    _add_date_range(conditions, params, "completed_at", query.completed)

    # ── updated date range (column exists) ──────────────────────────────────
    _add_date_range(conditions, params, "updated_at", query.updated)

    # ── planned date range — JSON extraction (Phase 2 concern for indexing)
    # TODO P2: add `planned_at` column + index; use json_extract for now.
    if query.planned:
        _add_date_range(
            conditions, params,
            "json_extract(data_json, '$.plannedAt')",
            query.planned,
        )

    # ── started date range — JSON extraction
    # TODO P2: add `started_at` column + index; use json_extract for now.
    if query.started:
        _add_date_range(
            conditions, params,
            "json_extract(data_json, '$.startedAt')",
            query.started,
        )

    # ── numeric ranges ───────────────────────────────────────────────────────
    if query.progress_min is not None:
        conditions.append(
            "CASE WHEN total_tasks > 0"
            " THEN CAST(completed_tasks AS REAL) / total_tasks"
            " ELSE 0.0 END >= ?"
        )
        params.append(query.progress_min)
    if query.progress_max is not None:
        conditions.append(
            "CASE WHEN total_tasks > 0"
            " THEN CAST(completed_tasks AS REAL) / total_tasks"
            " ELSE 0.0 END <= ?"
        )
        params.append(query.progress_max)
    if query.task_count_min is not None:
        conditions.append("COALESCE(total_tasks, 0) >= ?")
        params.append(query.task_count_min)
    if query.task_count_max is not None:
        conditions.append("COALESCE(total_tasks, 0) <= ?")
        params.append(query.task_count_max)

    return "WHERE " + " AND ".join(conditions), params


def _add_date_range(
    conditions: list[str],
    params: list[Any],
    col: str,
    dr: DateRange | None,
) -> None:
    """Append >=/<= date predicates for ``dr`` onto ``conditions``/``params``."""
    if dr is None:
        return
    if dr.from_date:
        conditions.append(f"{col} >= ?")
        params.append(dr.from_date)
    if dr.to_date:
        conditions.append(f"{col} <= ?")
        params.append(dr.to_date)


def _build_order_clause(query: FeatureListQuery) -> str:
    """Return an ORDER BY clause with a stable feature_id tiebreaker."""
    col = _SORT_COLUMN.get(query.sort_by, "updated_at")
    direction = query.effective_sort_direction.value.upper()
    return f"ORDER BY {col} {direction}, id ASC"


class SqliteFeatureRepository:
    """SQLite-backed feature storage with phases sub-table."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, feature_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = feature_data.get("createdAt", "") or now
        updated_at = feature_data.get("updatedAt", "") or now
        completed_at = feature_data.get("completedAt", "")
        data_json = json.dumps(feature_data)

        await self.db.execute(
            """INSERT INTO features (
                id, project_id, name, status, category,
                total_tasks, completed_tasks, parent_feature_id,
                created_at, updated_at, completed_at, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, status=excluded.status,
                category=excluded.category,
                total_tasks=excluded.total_tasks,
                completed_tasks=excluded.completed_tasks,
                parent_feature_id=excluded.parent_feature_id,
                updated_at=excluded.updated_at,
                completed_at=excluded.completed_at,
                data_json=excluded.data_json
            """,
            (
                feature_data["id"], project_id,
                feature_data.get("name", ""),
                feature_data.get("status", "backlog"),
                feature_data.get("category", ""),
                feature_data.get("totalTasks", 0),
                feature_data.get("completedTasks", 0),
                feature_data.get("parentFeatureId"),
                created_at,
                updated_at,
                completed_at,
                data_json,
            ),
        )
        await self.db.commit()

    async def get_by_id(self, feature_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM features WHERE id = ?", (feature_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_many_by_ids(self, ids: list[str]) -> dict[str, dict]:
        """Fetch multiple features in a single query. Returns a dict keyed by feature id."""
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        async with self.db.execute(
            f"SELECT * FROM features WHERE id IN ({placeholders})", tuple(ids)
        ) as cur:
            rows = await cur.fetchall()
        return {row["id"]: dict(row) for row in rows}

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM features WHERE project_id = ? ORDER BY name LIMIT ?",
                (project_id, 5000),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM features ORDER BY name LIMIT ?",
                (5000,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def list_paginated(
        self,
        project_id: str | None,
        offset: int,
        limit: int,
        *,
        keyword: str | None = None,
    ) -> list[dict]:
        # SQLite LIKE is case-insensitive for ASCII by default; LOWER() ensures
        # consistent behaviour across all character sets.
        if keyword:
            pattern = f"%{keyword.lower()}%"
            if project_id:
                async with self.db.execute(
                    "SELECT * FROM features WHERE project_id = ?"
                    " AND (LOWER(name) LIKE ? OR LOWER(id) LIKE ?)"
                    " ORDER BY name LIMIT ? OFFSET ?",
                    (project_id, pattern, pattern, limit, offset),
                ) as cur:
                    return [dict(r) for r in await cur.fetchall()]
            async with self.db.execute(
                "SELECT * FROM features"
                " WHERE LOWER(name) LIKE ? OR LOWER(id) LIKE ?"
                " ORDER BY name LIMIT ? OFFSET ?",
                (pattern, pattern, limit, offset),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

        if project_id:
            async with self.db.execute(
                "SELECT * FROM features WHERE project_id = ? ORDER BY name LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with self.db.execute(
            "SELECT * FROM features ORDER BY name LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def count(self, project_id: str | None = None, *, keyword: str | None = None) -> int:
        if keyword:
            pattern = f"%{keyword.lower()}%"
            if project_id:
                async with self.db.execute(
                    "SELECT COUNT(*) FROM features WHERE project_id = ?"
                    " AND (LOWER(name) LIKE ? OR LOWER(id) LIKE ?)",
                    (project_id, pattern, pattern),
                ) as cur:
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0
            async with self.db.execute(
                "SELECT COUNT(*) FROM features WHERE LOWER(name) LIKE ? OR LOWER(id) LIKE ?",
                (pattern, pattern),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0

        if project_id:
            async with self.db.execute(
                "SELECT COUNT(*) FROM features WHERE project_id = ?",
                (project_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
        async with self.db.execute("SELECT COUNT(*) FROM features") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def upsert_phases(self, feature_id: str, phases: list[dict]) -> None:
        await self.db.execute("DELETE FROM feature_phases WHERE feature_id = ?", (feature_id,))
        for idx, p in enumerate(phases):
            # Generate ID if missing. Append index to ensure uniqueness since multiple phases
            # might share the same 'phase' value (e.g. 'all').
            phase_id = p.get("id")
            if not phase_id:
                phase_id = f"{feature_id}:phase-{str(p.get('phase', '0'))}-{idx}"

            await self.db.execute(
                """INSERT INTO feature_phases
                    (id, feature_id, phase, title, status, progress, total_tasks, completed_tasks)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       feature_id=excluded.feature_id,
                       phase=excluded.phase,
                       title=excluded.title,
                       status=excluded.status,
                       progress=excluded.progress,
                       total_tasks=excluded.total_tasks,
                       completed_tasks=excluded.completed_tasks
                """,
                (
                    phase_id, feature_id,
                    str(p.get("phase", "")),
                    p.get("title", ""),
                    p.get("status", "backlog"),
                    p.get("progress", 0),
                    p.get("totalTasks", 0),
                    p.get("completedTasks", 0),
                ),
            )
        await self.db.commit()

    async def get_phases(self, feature_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM feature_phases WHERE feature_id = ? ORDER BY phase",
            (feature_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_phase_summaries_for_features(
        self,
        project_id: str,
        query: PhaseSummaryBulkQuery,
    ) -> dict[str, list[PhaseSummary]]:
        """Return phase summaries for all requested features in a single query.

        Result is keyed by feature_id.  Features with no phases map to ``[]``.
        Features not belonging to ``project_id`` are excluded and also map to
        ``[]`` (their key is still present in the returned dict).

        SQL strategy
        ------------
        * Base: ``SELECT ... FROM feature_phases fp JOIN features f ON ...``
          filtered to the requested feature_ids and project_id.
        * When ``include_counts=True`` (the default): task counts are read
          directly from the ``total_tasks`` / ``completed_tasks`` columns that
          are already maintained on the ``feature_phases`` table — no extra join
          is needed.
        * When ``include_progress=True``: ``progress`` is derived as
          ``completed_tasks / total_tasks`` with a zero-guard.
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

        placeholders = ",".join("?" for _ in feature_ids)
        sql = (
            "SELECT fp.id, fp.feature_id, fp.title, fp.status, fp.phase,"
            " fp.total_tasks, fp.completed_tasks, fp.progress AS stored_progress"
            " FROM feature_phases fp"
            " JOIN features f ON fp.feature_id = f.id"
            f" WHERE fp.feature_id IN ({placeholders})"
            " AND f.project_id = ?"
            " ORDER BY fp.feature_id, fp.phase"
        )
        params: list[Any] = list(feature_ids) + [project_id]

        async with self.db.execute(sql, params) as cur:
            rows = await cur.fetchall()

        for row in rows:
            r = dict(row)
            feature_id = r["feature_id"]

            total = int(r.get("total_tasks") or 0)
            completed = int(r.get("completed_tasks") or 0)

            # order_index: try to parse the phase string as an int
            try:
                order_index: int | None = int(r["phase"])
            except (ValueError, TypeError):
                order_index = None

            # progress: use stored value when include_progress is True, but
            # recalculate from task counts for consistency with include_counts
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
        await self.db.execute("DELETE FROM features WHERE id = ?", (feature_id,))
        await self.db.commit()

    async def list_feature_cards(
        self,
        project_id: str,
        query: FeatureListQuery,
    ) -> FeatureListPage:
        """Return a paginated, fully-filtered list of feature card dicts.

        All filtering and sorting is performed in SQL.  No in-memory filtering
        is applied after pagination.
        """
        where_sql, params = _build_feature_list_where_clause(project_id, query)
        order_sql = _build_order_clause(query)

        # Run count and data fetch concurrently via two separate queries.
        # SQLite does not guarantee window-function availability across old
        # versions embedded in some Python wheels, so we use two queries.
        import asyncio

        async def _fetch_total() -> int:
            async with self.db.execute(
                f"SELECT COUNT(*) FROM features {where_sql}",
                params,
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0

        async def _fetch_rows() -> list[dict]:
            row_params = list(params) + [query.limit, query.offset]
            async with self.db.execute(
                f"SELECT * FROM features {where_sql}"
                f" {order_sql}"
                " LIMIT ? OFFSET ?",
                row_params,
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

        total, rows = await asyncio.gather(_fetch_total(), _fetch_rows())
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
        where_sql, params = _build_feature_list_where_clause(project_id, query)
        async with self.db.execute(
            f"SELECT COUNT(*) FROM features {where_sql}",
            params,
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def get_project_stats(self, project_id: str) -> dict:
        """Get aggregated feature statistics."""
        query = """
            SELECT AVG(
                CASE WHEN total_tasks > 0
                     THEN CAST(completed_tasks AS REAL) / total_tasks * 100
                     ELSE 0
                END
            ) FROM features WHERE project_id = ?
        """
        async with self.db.execute(query, (project_id,)) as cur:
            row = await cur.fetchone()
            avg_progress = row[0] if row and row[0] is not None else 0.0
        return {"avg_progress": avg_progress}
