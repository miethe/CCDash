"""Paginated linked-session queries for the feature surface (SQLite).

Placed as a standalone module (not on SqliteEntityLinkRepository) for the
same reasons as feature_rollup.py:
  - This is a multi-table read aggregation (entity_links JOIN sessions) with
    pagination semantics that do not belong on the entity-graph write path.
  - The Postgres variant can subclass cleanly and override only the handful of
    SQL fragments that differ (parameter placeholders, ORDER BY tiebreaker,
    COUNT strategy).

Strategy — SQLite: two separate queries (list + count).
  Rationale: SQLite's window-function support is available since 3.25 (2018)
  but `COUNT(*) OVER ()` on a large unindexed union scan can be slower than a
  separate lightweight COUNT query because SQLite must materialise all rows for
  the window before yielding them.  Two queries allow the planner to short-
  circuit the list scan at LIMIT rows while the count scan touches only the
  primary key / index.  We accept the 2-RTT cost (both queries run on the same
  in-process connection with no network overhead).

Strategy — Postgres (subclass): single query with COUNT(*) OVER () window.
  Rationale: asyncpg uses a real network socket so round-trips are
  non-trivial.  PostgreSQL's parallel-query planner handles the window
  function more efficiently than SQLite, and the combined query avoids the
  second planner invocation entirely.  The Postgres subclass overrides
  list_feature_session_refs to extract total from the first row's
  window-column, falling back to 0 if the page is empty.

Phase 1 only implements offset-based pagination.  Cursor-based migration
(performance-budgets.md §3.2) is a Phase 2 concern.
"""
from __future__ import annotations

from typing import Any

import aiosqlite

from backend.db.repositories.feature_queries import (
    LinkedSessionPage,
    LinkedSessionQuery,
    ThreadExpansionMode,
)

_FAMILY_ROOT_CAP = 50  # max root IDs for list_session_family_refs


# ---------------------------------------------------------------------------
# Row projection
# ---------------------------------------------------------------------------

# Columns returned from every linked-session list query.  The set matches
# what the current features router endpoint exposes via FeatureSessionLink so
# that callers can build the same response shape.
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
# SQL helpers
# ---------------------------------------------------------------------------

def _order_clause(query: LinkedSessionQuery) -> str:
    col = "s.started_at" if query.sort_by == "started_at" else "s.updated_at"
    direction = query.sort_direction.value.upper()
    return f"ORDER BY {col} {direction}, s.id ASC"


def _direct_refs_predicate(
    project_id: str,
    feature_id: str,
    root_session_id: str | None,
) -> tuple[str, list[Any]]:
    """WHERE clause + params for direct entity_link refs to the feature.

    Bind order: feature_id, project_id [, root_session_id, root_session_id].
    """
    params: list[Any] = [feature_id, project_id]
    sql = (
        "el.source_type = 'feature' AND el.source_id = ? "
        "AND el.target_type = 'session' AND el.link_type = 'related' "
        "AND s.project_id = ?"
    )
    if root_session_id:
        sql += " AND (s.root_session_id = ? OR s.id = ?)"
        params.extend([root_session_id, root_session_id])
    return sql, params


def _direct_refs_subquery(feature_id: str, root_session_id: str | None) -> tuple[str, list[Any]]:
    """Subquery that returns session_ids directly linked to a feature.

    When root_session_id is provided, narrows to sessions in that root's family
    by joining sessions on the inner result and applying the root filter there.
    """
    params: list[Any] = [feature_id]
    if root_session_id is None:
        sql = (
            "SELECT el.target_id FROM entity_links el "
            "WHERE el.source_type = 'feature' AND el.source_id = ? "
            "AND el.target_type = 'session' AND el.link_type = 'related'"
        )
    else:
        sql = (
            "SELECT el.target_id FROM entity_links el "
            "JOIN sessions s ON s.id = el.target_id "
            "WHERE el.source_type = 'feature' AND el.source_id = ? "
            "AND el.target_type = 'session' AND el.link_type = 'related' "
            "AND (s.root_session_id = ? OR s.id = ?)"
        )
        params.extend([root_session_id, root_session_id])
    return sql, params


class SqliteFeatureSessionRepository:
    """Paginated linked-session queries for a single project."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_feature_session_refs(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> LinkedSessionPage:
        """Return a paginated page of sessions linked to ``query.feature_id``.

        ``thread_expansion=NONE`` (default) returns only direct session refs
        (entity_link.source_type='feature', target_type='session').

        ``thread_expansion=INHERITED_THREADS`` unions direct refs with every
        session whose root_session_id matches any root session directly linked
        to the feature.

        Filters are applied in SQL; no Python-side row filtering is performed
        after fetch.
        """
        rows = await self._list_refs(project_id, query)
        total = await self._count_refs(project_id, query)
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
        """Return the total count matching ``query`` predicates (no pagination)."""
        return await self._count_refs(project_id, query)

    async def list_session_family_refs(
        self,
        project_id: str,
        root_session_ids: list[str],
        query: LinkedSessionQuery,
    ) -> LinkedSessionPage:
        """Return a paginated page of sessions in the given root families.

        Matches sessions where ``root_session_id IN root_session_ids``
        OR ``id IN root_session_ids`` (i.e. the roots themselves plus their
        descendants).

        ``root_session_ids`` is capped at 50 IDs; raises ValueError if exceeded.
        ``query.root_session_id`` is ignored for this method (the caller
        provides the root list explicitly).
        """
        if len(root_session_ids) > _FAMILY_ROOT_CAP:
            raise ValueError(
                f"root_session_ids exceeds the cap of {_FAMILY_ROOT_CAP}. "
                f"Received {len(root_session_ids)} IDs."
            )
        if not root_session_ids:
            return LinkedSessionPage(rows=[], total=0, offset=query.offset, limit=query.limit)

        rows, total = await self._list_family(project_id, root_session_ids, query)
        return LinkedSessionPage(
            rows=rows,
            total=total,
            offset=query.offset,
            limit=query.limit,
            has_more=(query.offset + len(rows)) < total,
        )

    # ------------------------------------------------------------------
    # Private helpers — list_feature_session_refs
    # ------------------------------------------------------------------

    async def _list_refs(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> list[dict]:
        order = _order_clause(query)
        feature_id = query.feature_id
        root_id = query.root_session_id

        if query.thread_expansion == ThreadExpansionMode.NONE:
            pred, pred_params = _direct_refs_predicate(project_id, feature_id, root_id)
            sql = f"""
            SELECT {_SELECT_COLS}
            FROM entity_links el
            JOIN sessions s ON s.id = el.target_id
            WHERE {pred}
            {order}
            LIMIT ? OFFSET ?
            """
            params = pred_params + [query.limit, query.offset]
        else:
            # INHERITED_THREADS: direct refs UNION descendants of linked roots.
            # A session is included when:
            #   (a) it is directly linked to the feature via entity_links, OR
            #   (b) its root_session_id is itself a directly-linked session.
            direct_sub, direct_params = _direct_refs_subquery(feature_id, root_id)
            inherit_root_filter = (
                "AND (s.root_session_id = ? OR s.id = ?)" if root_id else ""
            )

            sql = f"""
            SELECT {_SELECT_COLS}
            FROM sessions s
            WHERE s.project_id = ?
              AND (
                s.id IN ({direct_sub})
                OR s.root_session_id IN (
                    SELECT el2.target_id
                    FROM entity_links el2
                    WHERE el2.source_type = 'feature' AND el2.source_id = ?
                      AND el2.target_type = 'session' AND el2.link_type = 'related'
                )
              )
              {inherit_root_filter}
            {order}
            LIMIT ? OFFSET ?
            """
            params = self._build_inherited_list_params(
                project_id, feature_id, root_id, query.limit, query.offset, direct_params,
            )

        async with self.db.execute(sql, params) as cur:
            return [dict(row) for row in await cur.fetchall()]

    def _build_inherited_list_params(
        self,
        project_id: str,
        feature_id: str,
        root_session_id: str | None,
        limit: int,
        offset: int,
        direct_params: list[Any],
    ) -> list[Any]:
        """Assemble the parameter list for the INHERITED_THREADS list query."""
        # Outer WHERE s.project_id = ?
        p: list[Any] = [project_id]
        # subquery for s.id IN (direct_sub) — direct_params are the inner ?s
        p.extend(direct_params)
        # subquery for s.root_session_id IN (linked roots) needs feature_id
        p.append(feature_id)
        # optional root_session_id narrowing
        if root_session_id:
            p.extend([root_session_id, root_session_id])
        p.extend([limit, offset])
        return p

    def _build_inherited_count_params(
        self,
        project_id: str,
        feature_id: str,
        root_session_id: str | None,
        direct_params: list[Any],
    ) -> list[Any]:
        p: list[Any] = [project_id]
        p.extend(direct_params)
        p.append(feature_id)
        if root_session_id:
            p.extend([root_session_id, root_session_id])
        return p

    async def _count_refs(
        self,
        project_id: str,
        query: LinkedSessionQuery,
    ) -> int:
        feature_id = query.feature_id
        root_id = query.root_session_id

        if query.thread_expansion == ThreadExpansionMode.NONE:
            pred, pred_params = _direct_refs_predicate(project_id, feature_id, root_id)
            sql = f"""
            SELECT COUNT(*) FROM entity_links el
            JOIN sessions s ON s.id = el.target_id
            WHERE {pred}
            """
            params = pred_params
        else:
            direct_sub, direct_params = _direct_refs_subquery(feature_id, root_id)
            inherit_root_filter = (
                "AND (s.root_session_id = ? OR s.id = ?)" if root_id else ""
            )

            sql = f"""
            SELECT COUNT(*) FROM sessions s
            WHERE s.project_id = ?
              AND (
                s.id IN ({direct_sub})
                OR s.root_session_id IN (
                    SELECT el2.target_id
                    FROM entity_links el2
                    WHERE el2.source_type = 'feature' AND el2.source_id = ?
                      AND el2.target_type = 'session' AND el2.link_type = 'related'
                )
              )
              {inherit_root_filter}
            """
            params = self._build_inherited_count_params(project_id, feature_id, root_id, direct_params)

        async with self.db.execute(sql, params) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Private helpers — list_session_family_refs
    # ------------------------------------------------------------------

    async def _list_family(
        self,
        project_id: str,
        root_session_ids: list[str],
        query: LinkedSessionQuery,
    ) -> tuple[list[dict], int]:
        placeholders = ",".join("?" * len(root_session_ids))
        order = _order_clause(query)

        list_sql = f"""
        SELECT {_SELECT_COLS}
        FROM sessions s
        WHERE s.project_id = ?
          AND (s.root_session_id IN ({placeholders}) OR s.id IN ({placeholders}))
        {order}
        LIMIT ? OFFSET ?
        """
        list_params = [project_id, *root_session_ids, *root_session_ids, query.limit, query.offset]

        count_sql = f"""
        SELECT COUNT(*) FROM sessions s
        WHERE s.project_id = ?
          AND (s.root_session_id IN ({placeholders}) OR s.id IN ({placeholders}))
        """
        count_params = [project_id, *root_session_ids, *root_session_ids]

        async with self.db.execute(list_sql, list_params) as cur:
            rows = [dict(row) for row in await cur.fetchall()]

        async with self.db.execute(count_sql, count_params) as cur:
            row = await cur.fetchone()
            total = int(row[0]) if row else 0

        return rows, total
