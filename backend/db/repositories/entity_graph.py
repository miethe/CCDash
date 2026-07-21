"""Observed-entity graph repositories for links and tags."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import aiosqlite


from backend.db.repositories.base import DEFAULT_WORKSPACE_ID, retry_on_locked

# ── Research Foundry run<->session correlation (T2-006, FR-9, D2) ──────────
#
# D2 is a hard boundary: run<->session correlation lives entirely in
# ``entity_links`` rows, never in ``backend/services/aos_correlation.py``
# (zero changes to that file). The correlation is a *heuristic* time-window +
# ``project_id`` overlap between a ``research_runs`` row's event window
# (``first_event_at``/``last_event_at``) and a session's active window
# (``started_at``/``ended_at``) -- it NEVER joins on RF's own ``run_id``
# string, ``intent_id``, or ``task_node_id``. Those three values ride along on
# the link row purely as opaque, display-only ``metadata_json`` attributes
# (for operator legibility / future IntentTree cross-reference), exactly per
# the risk-spike's recommended strategy
# (docs/project_plans/exploration/research-foundry-run-telemetry/spikes/risk-spike.md §1).
#
# The link's identity (upsert key) is always the CCDash-minted, genuine-UUID
# ``research_runs.run_id`` -- RF's non-UUID semantic slugs never become a
# join/identity key anywhere in this module.
RESEARCH_RUN_LINK_SOURCE_TYPE = "research_run"
RESEARCH_RUN_LINK_TARGET_TYPE = "session"
RESEARCH_RUN_LINK_TYPE = "research_run"

# Default symmetric padding applied to a run's event window before comparing
# it against a session's active window. RF runs are typically kicked off from
# inside a coding-agent session (the two overlap in wall-clock time, but not
# necessarily exactly -- a run may start slightly before/after the session's
# recorded first/last transcript timestamp), so a small tolerance avoids
# false negatives without being so wide it starts matching unrelated sessions.
RESEARCH_RUN_CORRELATION_DEFAULT_TOLERANCE_SECONDS = 900  # 15 minutes


def _parse_iso_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string into an aware UTC ``datetime``.

    Returns ``None`` for empty/unparseable input rather than raising --
    ``sessions.started_at``/``ended_at`` and ``research_runs.first_event_at``/
    ``last_event_at`` are best-effort strings from independent producers (the
    local session parser vs. RF's event ingest pipeline), so a malformed or
    missing value must degrade to "no time-window signal for this row", never
    a crash.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sessions_overlapping_window(
    session_rows: list[dict],
    window_start: datetime,
    window_end: datetime,
    tolerance_seconds: int,
) -> list[str]:
    """Return the ``id`` of every session row whose active window overlaps.

    ``session_rows`` are plain dicts with ``id``/``started_at``/``ended_at``
    keys (project_id filtering already applied by the caller's SQL). A session
    with no parseable ``started_at`` carries no time-window signal and is
    skipped -- it is not a match, but it is also not an error. A session with
    no ``ended_at`` yet (still in-flight) is treated as open-ended and can
    still overlap a run window that starts after it began.
    """
    tolerance = timedelta(seconds=max(tolerance_seconds, 0))
    padded_start = window_start - tolerance
    padded_end = window_end + tolerance

    matches: list[str] = []
    for row in session_rows:
        session_start = _parse_iso_ts(row.get("started_at"))
        if session_start is None:
            continue
        session_end = _parse_iso_ts(row.get("ended_at"))
        effective_end = session_end if session_end is not None else padded_end
        if session_start <= padded_end and effective_end >= padded_start:
            matches.append(row["id"])
    return matches


def _research_run_display_attrs(run: dict) -> dict:
    """Build the display-only ``metadata_json`` attribute dict for a run link.

    Only RF's own opaque correlation strings -- never used as join keys
    anywhere in this module or in ``aos_correlation.py``.
    """
    return {
        key: run.get(key)
        for key in ("rf_run_id", "intent_id", "task_node_id", "rf_project")
        if run.get(key) is not None
    }


class SqliteEntityLinkRepository:
    """Entity links with tree queries and bidirectional lookups."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def _commit(self) -> None:
        """Commit with locked-retry, re-raising on exhaustion (fail-loud, ADR-007)."""
        await retry_on_locked(self.db.commit, repo="entity_links")

    async def upsert(self, link_data: dict, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.execute(
            """INSERT INTO entity_links (
                workspace_id, source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin=excluded.origin, confidence=excluded.confidence,
                depth=excluded.depth, sort_order=excluded.sort_order,
                metadata_json=excluded.metadata_json
            """,
            (
                workspace_id,
                link_data["source_type"], link_data["source_id"],
                link_data["target_type"], link_data["target_id"],
                link_data.get("link_type", "related"),
                link_data.get("origin", "auto"),
                link_data.get("confidence", 1.0),
                link_data.get("depth", 0),
                link_data.get("sort_order", 0),
                link_data.get("metadata_json"),
                now,
            ),
        ) as cur:
            await self._commit()
            return cur.lastrowid or 0

    # ── Research Foundry run<->session correlation (T2-006, FR-9, D2) ──────

    async def find_candidate_sessions_for_run(
        self,
        run: dict,
        *,
        tolerance_seconds: int = RESEARCH_RUN_CORRELATION_DEFAULT_TOLERANCE_SECONDS,
    ) -> list[str]:
        """Discover session ids whose active window overlaps a run's event window.

        Heuristic-only ``project_id`` + time-window overlap (module docstring
        above). ``run`` is a ``research_runs`` row dict (e.g. from
        ``SqliteResearchRunsRepository.get_by_run_id``). A run with no
        ``project_id`` or no parseable ``first_event_at`` has no time-window
        signal at all and yields ``[]`` rather than guessing.
        """
        project_id = run.get("project_id")
        window_start = _parse_iso_ts(run.get("first_event_at"))
        window_end = _parse_iso_ts(run.get("last_event_at")) or window_start
        if not project_id or window_start is None or window_end is None:
            return []

        async with self.db.execute(
            "SELECT id, started_at, ended_at FROM sessions WHERE project_id = ?",
            (project_id,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        return _sessions_overlapping_window(rows, window_start, window_end, tolerance_seconds)

    async def link_research_run_sessions(
        self,
        run: dict,
        session_ids: list[str],
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> int:
        """Upsert entity-link rows correlating a research run to sessions (FR-9, D2).

        ``source_type='research_run'``/``source_id=run['run_id']`` (CCDash's
        genuine UUID, never RF's raw slug) links to ``target_type='session'``,
        ``link_type='research_run'``. RF's ``rf_run_id``/``intent_id``/
        ``task_node_id``/``rf_project`` ride along as display-only
        ``metadata_json`` attributes -- never part of the link's identity/join
        key. This method never touches ``aos_correlation.py``.

        Returns the number of link rows upserted.
        """
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
        """Discover + link a research run's correlated sessions in one call.

        Returns ``{"run_id", "linked_session_ids", "correlated"}``. Callers
        (e.g. ``run_intelligence.py``, T2-003) MUST treat an empty
        ``linked_session_ids`` as the explicit "no linked session" resilience
        state (AC-3) -- never coalesce it to a default/zero value upstream.
        """
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

    async def get_linked_session_ids_for_run(
        self, run_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
    ) -> list[str]:
        """Return session ids linked to a research run via the ``research_run`` link kind."""
        links = await self.get_links_for(
            RESEARCH_RUN_LINK_SOURCE_TYPE,
            run_id,
            link_type=RESEARCH_RUN_LINK_TYPE,
            workspace_id=workspace_id,
        )
        return [
            link["target_id"]
            for link in links
            if link.get("target_type") == RESEARCH_RUN_LINK_TARGET_TYPE
        ]

    async def get_session_workload_for_runs(
        self, run_ids: list[str], *, workspace_id: str = DEFAULT_WORKSPACE_ID
    ) -> dict:
        """Roll up a combined session-token workload figure across N linked runs.

        D-001-shape dedup discipline (Option A, ``docs/project_plans/
        design-specs/f-w6-001-correlation-overcounting.md``): when more than
        one id in *run_ids* is linked to the SAME session (a session
        correlated to more than one research run), that session's token
        counts MUST contribute to the returned total exactly once -- never
        once per linked run. This is enforced at the SQL level via a
        ``SELECT DISTINCT`` subquery over the joined session rows that runs
        strictly BEFORE the ``SUM`` aggregate -- never a plain
        join-then-sum, which would double (or N-multiply) count any session
        linked to more than one of *run_ids*. This is the exact F-W6-001/
        D-001 over-count shape (deferred at the session<->feature
        correlation layer), reproduced and fixed here one layer down at the
        run<->session correlation layer (T2-007, AC-3).

        Returns ``{"total_tokens", "session_count", "session_ids"}``. An
        empty *run_ids*, or a set of runs with zero linked sessions, yields
        the explicit AC-3 "no linked session" resilience state
        (``session_count=0``, ``session_ids=[]``, ``total_tokens=0`` -- a
        genuine zero-workload total, not a null-coalesced default masking a
        lookup failure).
        """
        if not run_ids:
            return {"total_tokens": 0, "session_count": 0, "session_ids": []}

        placeholders = ",".join("?" for _ in run_ids)
        params = tuple(
            [
                workspace_id,
                RESEARCH_RUN_LINK_SOURCE_TYPE,
                RESEARCH_RUN_LINK_TYPE,
                RESEARCH_RUN_LINK_TARGET_TYPE,
            ]
            + list(run_ids)
        )

        # Dedup-before-sum (D-001 Option A): the inner SELECT DISTINCT
        # collapses every research_run -> session link row down to one row
        # per distinct session BEFORE any aggregate function ever sees a
        # token column, so a session linked to two (or N) of *run_ids* is
        # counted once, not N times.
        totals_query = f"""
            SELECT
                COALESCE(SUM(tokens_in), 0) + COALESCE(SUM(tokens_out), 0) AS total_tokens,
                COUNT(*) AS session_count
            FROM (
                SELECT DISTINCT s.id AS id, s.tokens_in AS tokens_in, s.tokens_out AS tokens_out
                FROM entity_links el
                JOIN sessions s ON s.id = el.target_id
                WHERE el.workspace_id = ?
                  AND el.source_type = ?
                  AND el.link_type = ?
                  AND el.target_type = ?
                  AND el.source_id IN ({placeholders})
            ) AS distinct_sessions
        """  # noqa: S608
        async with self.db.execute(totals_query, params) as cur:
            totals_row = await cur.fetchone()
        totals = dict(totals_row) if totals_row else {}

        session_ids_query = f"""
            SELECT DISTINCT el.target_id AS session_id
            FROM entity_links el
            WHERE el.workspace_id = ?
              AND el.source_type = ?
              AND el.link_type = ?
              AND el.target_type = ?
              AND el.source_id IN ({placeholders})
        """  # noqa: S608
        async with self.db.execute(session_ids_query, params) as cur:
            session_rows = [dict(r) for r in await cur.fetchall()]

        return {
            "total_tokens": int(totals.get("total_tokens") or 0),
            "session_count": int(totals.get("session_count") or 0),
            "session_ids": [str(r["session_id"]) for r in session_rows],
        }

    async def bulk_upsert(self, links: list[dict], project_id: str | None = None) -> int:
        """Insert or update a batch of entity links in a single transaction.

        Builds one param-tuple list and issues a single ``executemany`` followed
        by a single ``commit``.  Reduces ~25K individual transactions during a
        full link rebuild to exactly one.

        The optional ``project_id`` argument populates the ``project_id`` column
        when it is present in the schema (added by T1-019).  If the column does
        not yet exist the value is silently dropped — callers must NOT rely on it
        being persisted until after T1-019 has run.

        Returns the number of links processed (not necessarily inserted — some
        may resolve to ON CONFLICT DO UPDATE).
        """
        if not links:
            return 0

        now = datetime.now(timezone.utc).isoformat()

        # Probe whether the project_id column exists so we degrade gracefully
        # when running against a schema that predates T1-019.
        has_project_id_col = False
        try:
            async with self.db.execute(
                "SELECT project_id FROM entity_links LIMIT 0"
            ):
                has_project_id_col = True
        except Exception:
            has_project_id_col = False

        if has_project_id_col:
            sql = """INSERT INTO entity_links (
                source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin=excluded.origin, confidence=excluded.confidence,
                depth=excluded.depth, sort_order=excluded.sort_order,
                metadata_json=excluded.metadata_json,
                project_id=COALESCE(excluded.project_id, entity_links.project_id)"""
            params = [
                (
                    lnk["source_type"], lnk["source_id"],
                    lnk["target_type"], lnk["target_id"],
                    lnk.get("link_type", "related"),
                    lnk.get("origin", "auto"),
                    lnk.get("confidence", 1.0),
                    lnk.get("depth", 0),
                    lnk.get("sort_order", 0),
                    lnk.get("metadata_json"),
                    now,
                    lnk.get("project_id") or project_id,
                )
                for lnk in links
            ]
        else:
            sql = """INSERT INTO entity_links (
                source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin=excluded.origin, confidence=excluded.confidence,
                depth=excluded.depth, sort_order=excluded.sort_order,
                metadata_json=excluded.metadata_json"""
            params = [
                (
                    lnk["source_type"], lnk["source_id"],
                    lnk["target_type"], lnk["target_id"],
                    lnk.get("link_type", "related"),
                    lnk.get("origin", "auto"),
                    lnk.get("confidence", 1.0),
                    lnk.get("depth", 0),
                    lnk.get("sort_order", 0),
                    lnk.get("metadata_json"),
                    now,
                )
                for lnk in links
            ]

        await self.db.executemany(sql, params)
        await self.db.commit()
        return len(links)

    async def get_links_for(
        self, entity_type: str, entity_id: str, link_type: str | None = None, *, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> list[dict]:
        if link_type:
            query = """SELECT * FROM entity_links
                       WHERE workspace_id = ?
                         AND ((source_type = ? AND source_id = ?)
                           OR (target_type = ? AND target_id = ?))
                         AND link_type = ?"""
            params = (workspace_id, entity_type, entity_id, entity_type, entity_id, link_type)
        else:
            query = """SELECT * FROM entity_links
                       WHERE workspace_id = ?
                         AND ((source_type = ? AND source_id = ?)
                           OR (target_type = ? AND target_id = ?))"""
            params = (workspace_id, entity_type, entity_id, entity_type, entity_id)

        async with self.db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_links_for_many(
        self, entity_type: str, entity_ids: list[str], *, workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict[str, list[dict]]:
        """Fetch entity links for many entity ids in a single query.

        Returns a dict keyed by entity_id.  Entities with no links map to [].
        """
        if not entity_ids:
            return {}
        placeholders = ",".join("?" for _ in entity_ids)
        query = (
            f"SELECT * FROM entity_links"
            f" WHERE workspace_id = ?"
            f"   AND ((source_type = ? AND source_id IN ({placeholders}))"
            f"     OR (target_type = ? AND target_id IN ({placeholders})))"
        )
        params = tuple([workspace_id, entity_type] + list(entity_ids) + [entity_type] + list(entity_ids))
        async with self.db.execute(query, params) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        result: dict[str, list[dict]] = {eid: [] for eid in entity_ids}
        for row in rows:
            if row.get("source_type") == entity_type and row.get("source_id") in result:
                result[row["source_id"]].append(row)
            if row.get("target_type") == entity_type and row.get("target_id") in result:
                # Avoid double-appending if source and target are the same entity
                if row.get("source_type") != entity_type or row.get("source_id") != row.get("target_id"):
                    result[row["target_id"]].append(row)
        return result

    async def get_tree(self, entity_type: str, entity_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> dict:
        """Get full tree: parents, children, siblings."""
        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE workspace_id = ? AND source_type = ? AND source_id = ? AND link_type = 'child'
               ORDER BY depth, sort_order""",
            (workspace_id, entity_type, entity_id),
        ) as cur:
            children = [dict(r) for r in await cur.fetchall()]

        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE workspace_id = ? AND target_type = ? AND target_id = ? AND link_type = 'child'""",
            (workspace_id, entity_type, entity_id),
        ) as cur:
            parents = [dict(r) for r in await cur.fetchall()]

        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE workspace_id = ?
                 AND ((source_type = ? AND source_id = ?)
                   OR (target_type = ? AND target_id = ?))
                 AND link_type = 'related'""",
            (workspace_id, entity_type, entity_id, entity_type, entity_id),
        ) as cur:
            related = [dict(r) for r in await cur.fetchall()]

        return {"children": children, "parents": parents, "related": related}

    async def delete_auto_links(self, source_type: str, source_id: str) -> None:
        # WORKSPACE-AUDIT-EXEMPT: delete_auto_links is called by the sync engine
        # during a full resync. The sync engine scopes its own source_id to a project;
        # cross-workspace delete is safe because source_id is globally unique by design.
        await self.db.execute(
            "DELETE FROM entity_links WHERE source_type = ? AND source_id = ? AND origin = 'auto'",
            (source_type, source_id),
        )
        await self.db.commit()

    async def delete_link(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        link_type: str = "related",
    ) -> None:
        # WORKSPACE-AUDIT-EXEMPT: single-record delete by full PK; workspace isolation
        # is guaranteed by the caller verifying ownership before calling this method.
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE source_type = ? AND source_id = ?
                 AND target_type = ? AND target_id = ?
                 AND link_type = ?""",
            (source_type, source_id, target_type, target_id, link_type),
        )
        await self.db.commit()

    async def delete_all_for(self, entity_type: str, entity_id: str) -> None:
        # WORKSPACE-AUDIT-EXEMPT: cascade delete of all links for an entity.
        # entity_id is globally unique (UUID), so cross-workspace impact is impossible.
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE (source_type = ? AND source_id = ?)
                  OR (target_type = ? AND target_id = ?)""",
            (entity_type, entity_id, entity_type, entity_id),
        )
        await self.db.commit()

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
            async with self.db.execute(
                """DELETE FROM entity_links
                   WHERE ((source_type = ? AND source_id = ?)
                       OR (target_type = ? AND target_id = ?))
                     AND origin = 'auto'""",
                (entity_type, entity_id, entity_type, entity_id),
            ) as cur:
                deleted += cur.rowcount or 0
            await self.db.commit()

        return {"entities_processed": len(ids), "auto_links_rebuilt": 0}


class SqliteTagRepository:
    """Cross-entity tag management."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_or_create(self, name: str, color: str = "") -> int:
        async with self.db.execute("SELECT id FROM tags WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]

        async with self.db.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color)
        ) as cur:
            await self.db.commit()
            return cur.lastrowid or 0

    async def tag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO entity_tags (entity_type, entity_id, tag_id) VALUES (?, ?, ?)",
            (entity_type, entity_id, tag_id),
        )
        await self.db.commit()

    async def untag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "DELETE FROM entity_tags WHERE entity_type = ? AND entity_id = ? AND tag_id = ?",
            (entity_type, entity_id, tag_id),
        )
        await self.db.commit()

    async def get_tags_for(self, entity_type: str, entity_id: str) -> list[dict]:
        async with self.db.execute(
            """SELECT t.id, t.name, t.color FROM tags t
               JOIN entity_tags et ON t.id = et.tag_id
               WHERE et.entity_type = ? AND et.entity_id = ?""",
            (entity_type, entity_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_entities_for_tag(self, tag_id: int) -> list[dict]:
        async with self.db.execute(
            "SELECT entity_type, entity_id FROM entity_tags WHERE tag_id = ?",
            (tag_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_all(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM tags ORDER BY name") as cur:
            return [dict(r) for r in await cur.fetchall()]
