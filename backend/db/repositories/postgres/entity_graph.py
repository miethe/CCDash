"""Observed-entity graph repositories for Postgres links and tags."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg

from backend.db.repositories.base import DEFAULT_WORKSPACE_ID
from backend.db.repositories.entity_graph import (
    RESEARCH_RUN_CORRELATION_DEFAULT_TOLERANCE_SECONDS,
    RESEARCH_RUN_LINK_SOURCE_TYPE,
    RESEARCH_RUN_LINK_TARGET_TYPE,
    RESEARCH_RUN_LINK_TYPE,
    _parse_iso_ts,
    _research_run_display_attrs,
    _sessions_overlapping_window,
)


class PostgresEntityLinkRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, link_data: dict, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> int:
        now = datetime.now(timezone.utc).isoformat()
        return await self.db.fetchval(
            """
            INSERT INTO entity_links (
                workspace_id, source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin = EXCLUDED.origin,
                confidence = EXCLUDED.confidence,
                depth = EXCLUDED.depth,
                sort_order = EXCLUDED.sort_order,
                metadata_json = EXCLUDED.metadata_json
            RETURNING id
            """,
            workspace_id,
            link_data["source_type"],
            link_data["source_id"],
            link_data["target_type"],
            link_data["target_id"],
            link_data.get("link_type", "related"),
            link_data.get("origin", "auto"),
            link_data.get("confidence", 1.0),
            link_data.get("depth", 0),
            link_data.get("sort_order", 0),
            link_data.get("metadata_json"),
            now,
        )

    # ── Research Foundry run<->session correlation (T2-006, FR-9, D2) ──────
    #
    # Mirrors ``backend.db.repositories.entity_graph.SqliteEntityLinkRepository``
    # exactly; see that module's docstring for the full D2 correlation-strategy
    # rationale (time-window + project_id overlap heuristic only -- never a
    # join on RF's raw run_id/intent_id/task_node_id, zero changes to
    # ``aos_correlation.py``).

    async def find_candidate_sessions_for_run(
        self,
        run: dict,
        *,
        tolerance_seconds: int = RESEARCH_RUN_CORRELATION_DEFAULT_TOLERANCE_SECONDS,
    ) -> list[str]:
        project_id = run.get("project_id")
        window_start = _parse_iso_ts(run.get("first_event_at"))
        window_end = _parse_iso_ts(run.get("last_event_at")) or window_start
        if not project_id or window_start is None or window_end is None:
            return []

        rows = await self.db.fetch(
            "SELECT id, started_at, ended_at FROM sessions WHERE project_id = $1",
            project_id,
        )
        session_rows = [dict(r) for r in rows]
        return _sessions_overlapping_window(session_rows, window_start, window_end, tolerance_seconds)

    async def link_research_run_sessions(
        self,
        run: dict,
        session_ids: list[str],
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> int:
        run_id = run.get("run_id")
        if not run_id or not session_ids:
            return 0

        display_attrs = _research_run_display_attrs(run)
        metadata_json = json.dumps(display_attrs) if display_attrs else None

        linked = 0
        for session_id in dict.fromkeys(session_ids):  # de-dupe, preserve order
            await self.upsert(
                {
                    "source_type": RESEARCH_RUN_LINK_SOURCE_TYPE,
                    "source_id": run_id,
                    "target_type": RESEARCH_RUN_LINK_TARGET_TYPE,
                    "target_id": session_id,
                    "link_type": RESEARCH_RUN_LINK_TYPE,
                    "origin": "auto",
                    "confidence": 1.0,
                    "metadata_json": metadata_json,
                },
                workspace_id=workspace_id,
            )
            linked += 1
        return linked

    async def correlate_research_run(
        self,
        run: dict,
        *,
        tolerance_seconds: int = RESEARCH_RUN_CORRELATION_DEFAULT_TOLERANCE_SECONDS,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict:
        session_ids = await self.find_candidate_sessions_for_run(
            run, tolerance_seconds=tolerance_seconds
        )
        if session_ids:
            await self.link_research_run_sessions(run, session_ids, workspace_id=workspace_id)
        return {
            "run_id": run.get("run_id"),
            "linked_session_ids": session_ids,
            "correlated": bool(session_ids),
        }

    async def get_session_workload_for_runs(
        self, run_ids: list[str], *, workspace_id: str = DEFAULT_WORKSPACE_ID
    ) -> dict:
        """Postgres mirror of ``SqliteEntityLinkRepository.get_session_workload_for_runs``.

        D-001-shape dedup discipline (T2-007, AC-3): identical semantics to the
        SQLite implementation (``backend.db.repositories.entity_graph``) — see
        that method's docstring for the full rationale. A ``SELECT DISTINCT``
        subquery over the joined session rows runs strictly BEFORE the
        ``SUM``/``COUNT`` aggregate, so a session linked to more than one of
        *run_ids* contributes its token counts exactly once, never once per
        linked run.

        Returns ``{"total_tokens", "session_count", "session_ids"}``. An
        empty *run_ids*, or a set of runs with zero linked sessions, yields
        the explicit AC-3 resilience state (``session_count=0``,
        ``session_ids=[]``, ``total_tokens=0``).
        """
        if not run_ids:
            return {"total_tokens": 0, "session_count": 0, "session_ids": []}

        # Dedup-before-sum (D-001 Option A): the inner SELECT DISTINCT
        # collapses every research_run -> session link row down to one row
        # per distinct session BEFORE any aggregate function ever sees a
        # token column -- mirrors the SQLite implementation's query shape
        # exactly, adapted to asyncpg's $n placeholders and ANY(...::text[])
        # array membership test in place of SQLite's IN (...) placeholder
        # expansion.
        totals_row = await self.db.fetchrow(
            """
            SELECT
                COALESCE(SUM(tokens_in), 0) + COALESCE(SUM(tokens_out), 0) AS total_tokens,
                COUNT(*) AS session_count
            FROM (
                SELECT DISTINCT s.id AS id, s.tokens_in AS tokens_in, s.tokens_out AS tokens_out
                FROM entity_links el
                JOIN sessions s ON s.id = el.target_id
                WHERE el.workspace_id = $1
                  AND el.source_type = $2
                  AND el.link_type = $3
                  AND el.target_type = $4
                  AND el.source_id = ANY($5::text[])
            ) AS distinct_sessions
            """,
            workspace_id,
            RESEARCH_RUN_LINK_SOURCE_TYPE,
            RESEARCH_RUN_LINK_TYPE,
            RESEARCH_RUN_LINK_TARGET_TYPE,
            list(run_ids),
        )
        totals = dict(totals_row) if totals_row else {}

        session_id_rows = await self.db.fetch(
            """
            SELECT DISTINCT el.target_id AS session_id
            FROM entity_links el
            WHERE el.workspace_id = $1
              AND el.source_type = $2
              AND el.link_type = $3
              AND el.target_type = $4
              AND el.source_id = ANY($5::text[])
            """,
            workspace_id,
            RESEARCH_RUN_LINK_SOURCE_TYPE,
            RESEARCH_RUN_LINK_TYPE,
            RESEARCH_RUN_LINK_TARGET_TYPE,
            list(run_ids),
        )

        return {
            "total_tokens": int(totals.get("total_tokens") or 0),
            "session_count": int(totals.get("session_count") or 0),
            "session_ids": [str(r["session_id"]) for r in session_id_rows],
        }

    async def get_linked_session_ids_for_run(self, run_id: str) -> list[str]:
        links = await self.get_links_for(
            RESEARCH_RUN_LINK_SOURCE_TYPE, run_id, link_type=RESEARCH_RUN_LINK_TYPE
        )
        return [
            link["target_id"]
            for link in links
            if link.get("target_type") == RESEARCH_RUN_LINK_TARGET_TYPE
        ]

    async def get_links_for(
        self, entity_type: str, entity_id: str, link_type: str | None = None,
    ) -> list[dict]:
        if link_type:
            rows = await self.db.fetch(
                """SELECT * FROM entity_links
                   WHERE ((source_type = $1 AND source_id = $2)
                       OR (target_type = $3 AND target_id = $4))
                     AND link_type = $5""",
                entity_type, entity_id, entity_type, entity_id, link_type
            )
        else:
            rows = await self.db.fetch(
                """SELECT * FROM entity_links
                   WHERE (source_type = $1 AND source_id = $2)
                      OR (target_type = $3 AND target_id = $4)""",
                entity_type, entity_id, entity_type, entity_id
            )
        return [dict(r) for r in rows]

    async def get_links_for_many(
        self, entity_type: str, entity_ids: list[str]
    ) -> dict[str, list[dict]]:
        """Fetch entity links for many entity ids in a single query.

        Returns a dict keyed by entity_id.  Entities with no links map to [].
        """
        if not entity_ids:
            return {}
        rows = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE (source_type = $1 AND source_id = ANY($2::text[]))
                  OR (target_type = $3 AND target_id = ANY($4::text[]))""",
            entity_type, entity_ids, entity_type, entity_ids,
        )

        result: dict[str, list[dict]] = {eid: [] for eid in entity_ids}
        for row in rows:
            r = dict(row)
            if r.get("source_type") == entity_type and r.get("source_id") in result:
                result[r["source_id"]].append(r)
            if r.get("target_type") == entity_type and r.get("target_id") in result:
                # Avoid double-appending if source and target are the same entity
                if r.get("source_type") != entity_type or r.get("source_id") != r.get("target_id"):
                    result[r["target_id"]].append(r)
        return result

    async def get_tree(self, entity_type: str, entity_id: str) -> dict:
        children = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE source_type = $1 AND source_id = $2 AND link_type = 'child'
               ORDER BY depth, sort_order""",
            entity_type, entity_id
        )
        parents = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE target_type = $1 AND target_id = $2 AND link_type = 'child'""",
            entity_type, entity_id
        )
        related = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE ((source_type = $1 AND source_id = $2)
                   OR (target_type = $3 AND target_id = $4))
                 AND link_type = 'related'""",
            entity_type, entity_id, entity_type, entity_id
        )
        return {
            "children": [dict(r) for r in children],
            "parents": [dict(r) for r in parents],
            "related": [dict(r) for r in related],
        }

    async def delete_auto_links(self, source_type: str, source_id: str) -> None:
        await self.db.execute(
            "DELETE FROM entity_links WHERE source_type = $1 AND source_id = $2 AND origin = 'auto'",
            source_type, source_id,
        )

    async def delete_link(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        link_type: str = "related",
    ) -> None:
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE source_type = $1 AND source_id = $2
                 AND target_type = $3 AND target_id = $4
                 AND link_type = $5""",
            source_type, source_id, target_type, target_id, link_type,
        )

    async def delete_all_for(self, entity_type: str, entity_id: str) -> None:
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE (source_type = $1 AND source_id = $2)
                  OR (target_type = $3 AND target_id = $4)""",
            entity_type, entity_id, entity_type, entity_id
        )

    async def rebuild_for_entities(
        self, entity_type: str, ids: list[str]
    ) -> dict:
        """Delete then re-derive auto-links scoped to the supplied entity IDs.

        Covers both outbound links (where the entity is the source) and inbound
        auto-links (where the entity is the target).  Actual link re-derivation
        is delegated back to the caller via the returned stats dict; this method
        is responsible only for the delete phase and counting.  Callers that
        want full re-derivation should call ``SyncEngine.rebuild_links_for_entities``
        which drives re-derivation through the normal sync pipeline.

        Returns:
            {"entities_processed": N, "auto_links_rebuilt": 0}
            (``auto_links_rebuilt`` is populated by the SyncEngine wrapper after
            it re-upserts links for the affected entities.)
        """
        if not ids:
            return {"entities_processed": 0, "auto_links_rebuilt": 0}

        deleted = 0
        for entity_id in ids:
            result = await self.db.execute(
                """DELETE FROM entity_links
                   WHERE ((source_type = $1 AND source_id = $2)
                       OR (target_type = $3 AND target_id = $4))
                     AND origin = 'auto'""",
                entity_type, entity_id, entity_type, entity_id,
            )
            # asyncpg returns "DELETE N" as a string status
            try:
                deleted += int(result.split()[-1])
            except (AttributeError, ValueError, IndexError):
                pass

        return {"entities_processed": len(ids), "auto_links_rebuilt": 0}


class PostgresTagRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def get_or_create(self, name: str, color: str = "") -> int:
        row = await self.db.fetchrow("SELECT id FROM tags WHERE name = $1", name)
        if row:
            return row["id"]

        try:
            return await self.db.fetchval(
                "INSERT INTO tags (name, color) VALUES ($1, $2) RETURNING id",
                name, color
            )
        except asyncpg.UniqueViolationError:
            return await self.db.fetchval("SELECT id FROM tags WHERE name = $1", name)

    async def tag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO entity_tags (entity_type, entity_id, tag_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (entity_type, entity_id, tag_id) DO NOTHING
            """,
            entity_type, entity_id, tag_id,
        )

    async def untag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "DELETE FROM entity_tags WHERE entity_type = $1 AND entity_id = $2 AND tag_id = $3",
            entity_type, entity_id, tag_id
        )

    async def get_tags_for(self, entity_type: str, entity_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT t.id, t.name, t.color FROM tags t
               JOIN entity_tags et ON t.id = et.tag_id
               WHERE et.entity_type = $1 AND et.entity_id = $2""",
            entity_type, entity_id
        )
        return [dict(r) for r in rows]

    async def get_entities_for_tag(self, tag_id: int) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT entity_type, entity_id FROM entity_tags WHERE tag_id = $1",
            tag_id
        )
        return [dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM tags ORDER BY name")
        return [dict(r) for r in rows]
