"""Postgres implementation of feature linked-session pagination.

Strategy: single query with ``COUNT(*) OVER ()`` window function.
  On Postgres, the planner handles the window efficiently within a single
  server round-trip.  We extract ``_total`` from the first row's extra column
  and discard that column from the public row dicts.  When the page is empty
  (offset beyond total), we fall back to a separate COUNT query to populate
  ``total`` correctly.

Parameter placeholders use ``$N`` positional style (asyncpg protocol).

See backend/db/repositories/feature_sessions.py for design rationale and
the SQLite two-query strategy comparison.
"""
from __future__ import annotations

from typing import Any

import asyncpg

from backend.db.repositories.feature_queries import (
    LinkedSessionPage,
    LinkedSessionQuery,
    ThreadExpansionMode,
)

_FAMILY_ROOT_CAP = 50

# Columns projected from the sessions table (same set as SQLite variant).
_SESSION_COLS = (
    "s.id          AS session_id",
    "s.project_id",
    "s.task_id",
    "s.status",
    "s.model",
    "s.platform_type",
    "s.session_type",
    "s.parent_session_id",
    "s.root_session_id",
    "s.agent_id",
    "s.thread_kind",
    "s.started_at",
    "s.ended_at",
    "s.updated_at",
    "s.total_cost",
    "s.observed_tokens",
    "s.tokens_in",
    "s.tokens_out",
    "s.git_branch",
    "s.git_commit_hash",
    "s.source_file",
)
_SELECT_COLS = ",\n        ".join(_SESSION_COLS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order_clause(query: LinkedSessionQuery) -> str:
    col = "s.started_at" if query.sort_by == "started_at" else "s.updated_at"
    direction = query.sort_direction.value.upper()
    return f"ORDER BY {col} {direction}, s.id ASC"


class PostgresFeatureSessionRepository:
    """Paginated linked-session queries for a single project (Postgres)."""

    def __init__(self, db: asyncpg.Connection) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_feature_session_refs(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> LinkedSessionPage:
        """Paginated sessions linked to ``query.feature_id``.

        Uses a single query with ``COUNT(*) OVER ()`` to avoid a second
        round-trip.  When the page is empty, falls back to count_feature_session_refs.
        """
        rows, total = await self._list_refs_with_count(project_id, query)
        return LinkedSessionPage(
            rows=rows,
            total=total,
            offset=query.offset,
            limit=query.limit,
            has_more=(query.offset + len(rows)) < total,
        )

    async def count_feature_session_refs(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> int:
        return await self._count_refs(project_id, query)

    async def list_session_family_refs(
        self,
        project_id: str,
        root_session_ids: list[str],
        query: LinkedSessionQuery,
    ) -> LinkedSessionPage:
        """Paginated sessions in the given root families.

        Matches ``root_session_id IN root_session_ids OR id IN root_session_ids``.
        Capped at 50 root IDs.
        """
        if len(root_session_ids) > _FAMILY_ROOT_CAP:
            raise ValueError(
                f"root_session_ids exceeds the cap of {_FAMILY_ROOT_CAP}. "
                f"Received {len(root_session_ids)} IDs."
            )
        if not root_session_ids:
            return LinkedSessionPage(rows=[], total=0, offset=query.offset, limit=query.limit)

        rows, total = await self._list_family_with_count(project_id, root_session_ids, query)
        return LinkedSessionPage(
            rows=rows,
            total=total,
            offset=query.offset,
            limit=query.limit,
            has_more=(query.offset + len(rows)) < total,
        )

    # ------------------------------------------------------------------
    # Private — list_feature_session_refs
    # ------------------------------------------------------------------

    async def _list_refs_with_count(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> tuple[list[dict], int]:
        feature_id = query.feature_id
        root_id = query.root_session_id
        order = _order_clause(query)

        if query.thread_expansion == ThreadExpansionMode.NONE:
            root_filter, extra_params, param_idx = self._root_filter(root_id, start_idx=4)
            sql = f"""
            SELECT {_SELECT_COLS},
                   COUNT(*) OVER () AS _total
            FROM entity_links el
            JOIN sessions s ON s.id = el.target_id
            WHERE el.source_type = 'feature' AND el.source_id = $1
              AND el.target_type = 'session' AND el.link_type = 'related'
              AND s.project_id = $2
              {root_filter}
            {order}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params: list[Any] = [feature_id, project_id, *extra_params, query.limit, query.offset]
        else:
            # Build subquery for direct session IDs
            direct_sub, direct_sub_params, next_idx = self._direct_refs_subquery(
                feature_id, root_id, start_idx=2
            )
            # Subquery for linked roots (re-uses feature_id already at $1)
            root_filter, root_extra, next_idx2 = self._root_filter(root_id, start_idx=next_idx)
            sql = f"""
            SELECT {_SELECT_COLS},
                   COUNT(*) OVER () AS _total
            FROM sessions s
            WHERE s.project_id = $1
              AND (
                s.id IN ({direct_sub})
                OR s.root_session_id IN (
                    SELECT el2.target_id
                    FROM entity_links el2
                    WHERE el2.source_type = 'feature' AND el2.source_id = $2
                      AND el2.target_type = 'session' AND el2.link_type = 'related'
                )
              )
              {root_filter}
            {order}
            LIMIT ${next_idx2} OFFSET ${next_idx2 + 1}
            """
            params = [project_id, feature_id, *direct_sub_params, *root_extra, query.limit, query.offset]

        db_rows = await self.db.fetch(sql, *params)
        if not db_rows:
            # Empty page — run a separate count to handle offset-past-end correctly
            total = await self._count_refs(project_id, query)
            return [], total

        total = int(db_rows[0]["_total"])
        rows = [{k: v for k, v in dict(r).items() if k != "_total"} for r in db_rows]
        return rows, total

    async def _count_refs(self, project_id: str, query: LinkedSessionQuery) -> int:
        feature_id = query.feature_id
        root_id = query.root_session_id

        if query.thread_expansion == ThreadExpansionMode.NONE:
            root_filter, extra_params, _ = self._root_filter(root_id, start_idx=4)
            sql = f"""
            SELECT COUNT(*) FROM entity_links el
            JOIN sessions s ON s.id = el.target_id
            WHERE el.source_type = 'feature' AND el.source_id = $1
              AND el.target_type = 'session' AND el.link_type = 'related'
              AND s.project_id = $2
              {root_filter}
            """
            params: list[Any] = [feature_id, project_id, *extra_params]
        else:
            direct_sub, direct_sub_params, next_idx = self._direct_refs_subquery(
                feature_id, root_id, start_idx=2
            )
            root_filter, root_extra, _ = self._root_filter(root_id, start_idx=next_idx)
            sql = f"""
            SELECT COUNT(*) FROM sessions s
            WHERE s.project_id = $1
              AND (
                s.id IN ({direct_sub})
                OR s.root_session_id IN (
                    SELECT el2.target_id
                    FROM entity_links el2
                    WHERE el2.source_type = 'feature' AND el2.source_id = $2
                      AND el2.target_type = 'session' AND el2.link_type = 'related'
                )
              )
              {root_filter}
            """
            params = [project_id, feature_id, *direct_sub_params, *root_extra]

        return int(await self.db.fetchval(sql, *params) or 0)

    # ------------------------------------------------------------------
    # Private — list_session_family_refs
    # ------------------------------------------------------------------

    async def _list_family_with_count(
        self,
        project_id: str,
        root_session_ids: list[str],
        query: LinkedSessionQuery,
    ) -> tuple[list[dict], int]:
        n = len(root_session_ids)
        # $1 = project_id, $2..$n+1 = root ids (first set), $n+2..$2n+1 = root ids (second set)
        first_placeholders = ", ".join(f"${i + 2}" for i in range(n))
        second_placeholders = ", ".join(f"${i + n + 2}" for i in range(n))
        limit_idx = 2 * n + 2
        offset_idx = 2 * n + 3
        order = _order_clause(query)

        sql = f"""
        SELECT {_SELECT_COLS},
               COUNT(*) OVER () AS _total
        FROM sessions s
        WHERE s.project_id = $1
          AND (s.root_session_id IN ({first_placeholders}) OR s.id IN ({second_placeholders}))
        {order}
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """
        params: list[Any] = [project_id, *root_session_ids, *root_session_ids, query.limit, query.offset]

        db_rows = await self.db.fetch(sql, *params)
        if not db_rows:
            # Count separately for empty pages
            count_sql = f"""
            SELECT COUNT(*) FROM sessions s
            WHERE s.project_id = $1
              AND (s.root_session_id IN ({first_placeholders}) OR s.id IN ({second_placeholders}))
            """
            total = int(await self.db.fetchval(count_sql, project_id, *root_session_ids, *root_session_ids) or 0)
            return [], total

        total = int(db_rows[0]["_total"])
        rows = [{k: v for k, v in dict(r).items() if k != "_total"} for r in db_rows]
        return rows, total

    # ------------------------------------------------------------------
    # SQL builder helpers
    # ------------------------------------------------------------------

    def _root_filter(
        self, root_session_id: str | None, start_idx: int
    ) -> tuple[str, list[Any], int]:
        """Return (SQL fragment, extra params, next_param_idx).

        Returns an empty fragment when root_session_id is None.
        """
        if not root_session_id:
            return "", [], start_idx
        frag = f"AND (s.root_session_id = ${start_idx} OR s.id = ${start_idx + 1})"
        return frag, [root_session_id, root_session_id], start_idx + 2

    def _direct_refs_subquery(
        self,
        feature_id: str,
        root_session_id: str | None,
        start_idx: int,
    ) -> tuple[str, list[Any], int]:
        """Build a subquery for direct session IDs linked to the feature.

        ``start_idx`` is the first available parameter placeholder index.
        Returns (sql_fragment, extra_params_beyond_feature_id, next_idx).

        Note: feature_id is assumed to already be bound at $2 (per the caller
        convention in _list_refs_with_count).
        """
        if root_session_id is None:
            sql = (
                "SELECT el.target_id FROM entity_links el "
                "WHERE el.source_type = 'feature' AND el.source_id = $2 "
                "AND el.target_type = 'session' AND el.link_type = 'related'"
            )
            return sql, [], start_idx

        # Narrow the direct refs to the root family
        sql = (
            "SELECT el.target_id FROM entity_links el "
            "JOIN sessions s ON s.id = el.target_id "
            "WHERE el.source_type = 'feature' AND el.source_id = $2 "
            "AND el.target_type = 'session' AND el.link_type = 'related' "
            f"AND (s.root_session_id = ${start_idx} OR s.id = ${start_idx})"
        )
        return sql, [root_session_id], start_idx + 1
