"""Postgres coverage for the itt-node-session-cost-join repository additions.

``PostgresEntityLinkRepository.link_intent_node_sessions`` /
``.get_intent_node_session_ids`` and ``PostgresSessionRepository.
list_by_workflow_ids`` were added alongside their SQLite counterparts (see
``test_entity_graph_intent_node_links.py`` and ``test_intent_node_cost_service.py``)
but, until this file, had ZERO Postgres-side coverage — the exact bug class
``test_pg_run_session_workload_dedup_regression.py`` exists to guard against
(read that file's module docstring): a method exists on the SQLite repo,
every SQLite test stays green, and a Postgres caller raises ``AttributeError``
because the sibling method was never added there. The operative deployment
DB for this project is Postgres, so SQLite-only coverage on these three
methods is not equivalent coverage.

Mirrors ``test_pg_run_session_workload_dedup_regression.py``'s two-tier
pattern exactly:

1. ``PostgresIntentNodeLinksStructuralTests`` (always runs, no live DB) — a
   lightweight mock ``asyncpg``-shaped connection proves (a) all three
   methods exist and are callable (the literal AttributeError regression
   guard), (b) ``link_intent_node_sessions``'s emitted SQL's ``ON CONFLICT``
   conflict target is the same five columns as the ``idx_links_upsert``
   unique index (``source_type, source_id, target_type, target_id,
   link_type``), verified by inspecting the actual production SQL string,
   (c) ``list_by_workflow_ids``'s emitted SQL constrains ``project_id`` in
   its WHERE clause -- the cross-project-leak guard for the
   ``expand_family`` widen path, and (d) the empty-input resilience states
   (``session_ids=[]``, ``workflow_ids=[]``) never touch the DB.

2. ``LivePGIntentNodeLinksTests`` (skipped unless ``CCDASH_DATABASE_URL`` is
   set) — the behavioral reproduction of the SQLite scenarios against a real
   Postgres instance: declare bindings then read them back; re-declaring the
   same (node, session) pair does not duplicate (direct ``COUNT(*)``
   assertion, ADR-007 style); ``list_by_workflow_ids`` returns only
   same-project siblings sharing a workflow_id, never a cross-project one.

Run (mock tier only, no PG required):
    backend/.venv/bin/python -m pytest backend/tests/test_pg_intent_node_links.py -v

Run (including the live-PG tier):
    CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash \\
        backend/.venv/bin/python -m pytest backend/tests/test_pg_intent_node_links.py -v
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from backend.db.repositories.postgres.entity_graph import PostgresEntityLinkRepository
from backend.db.repositories.postgres.sessions import PostgresSessionRepository

_PG_URL = os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres itt-node-session-cost-join "
    "test requires a running Postgres instance (e.g. via docker compose up --profile postgres)."
)

_NODE_ID = "itt-node-3f9c2a4e"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# 1. Structural / mock tier — always runs, no live Postgres required.
# ---------------------------------------------------------------------------


class PostgresIntentNodeLinksStructuralTests(unittest.IsolatedAsyncioTestCase):
    """AttributeError regression guard + upsert-target / project-scope SQL structure checks."""

    # -- link_intent_node_sessions -------------------------------------------

    async def test_link_intent_node_sessions_exists_and_is_callable(self) -> None:
        """The literal reviewer-flagged bug class: calling this on the Postgres
        repo must not raise AttributeError because the method doesn't exist."""
        db = MagicMock()
        db.executemany = AsyncMock(return_value=None)
        repo = PostgresEntityLinkRepository(db)

        linked = await repo.link_intent_node_sessions(
            _NODE_ID, ["sess-1"], project_id="proj-1"
        )  # must not raise

        self.assertEqual(linked, 1)
        db.executemany.assert_awaited_once()

    async def test_link_intent_node_sessions_empty_session_ids_short_circuits(self) -> None:
        db = MagicMock()
        db.executemany = AsyncMock()
        repo = PostgresEntityLinkRepository(db)

        linked = await repo.link_intent_node_sessions(_NODE_ID, [], project_id="proj-1")

        self.assertEqual(linked, 0)
        db.executemany.assert_not_called()

    async def test_link_intent_node_sessions_empty_node_id_short_circuits(self) -> None:
        db = MagicMock()
        db.executemany = AsyncMock()
        repo = PostgresEntityLinkRepository(db)

        linked = await repo.link_intent_node_sessions("", ["sess-1"], project_id="proj-1")

        self.assertEqual(linked, 0)
        db.executemany.assert_not_called()

    async def test_link_intent_node_sessions_conflict_target_matches_idx_links_upsert(self) -> None:
        """The emitted ``ON CONFLICT`` target must be the exact same five
        columns as the ``idx_links_upsert`` unique index defined in both
        ``sqlite_migrations.py`` and ``postgres_migrations.py``
        (``source_type, source_id, target_type, target_id, link_type``) --
        verified against the actual production SQL string, not a
        reimplementation of its semantics. A mismatch here means the upsert
        would either fail at the DB (no matching unique constraint) or,
        worse, silently target the wrong constraint.
        """
        db = MagicMock()
        db.executemany = AsyncMock()
        repo = PostgresEntityLinkRepository(db)

        await repo.link_intent_node_sessions(_NODE_ID, ["sess-1"], project_id="proj-1")

        sql: str = db.executemany.call_args[0][0]
        self.assertIn("ON CONFLICT(source_type, source_id, target_type, target_id, link_type)", sql)
        self.assertIn("DO UPDATE SET", sql)

    async def test_link_intent_node_sessions_params_shape(self) -> None:
        """asyncpg's ``executemany`` receives (sql, [param_tuples]) — one
        tuple per de-duplicated session id."""
        db = MagicMock()
        db.executemany = AsyncMock()
        repo = PostgresEntityLinkRepository(db)

        await repo.link_intent_node_sessions(
            _NODE_ID, ["sess-1", "sess-1", "sess-2"], project_id="proj-1"
        )

        _sql, param_rows = db.executemany.call_args[0]
        self.assertEqual(len(param_rows), 2)  # de-duped

    # -- get_intent_node_session_ids -----------------------------------------

    async def test_get_intent_node_session_ids_exists_and_is_callable(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresEntityLinkRepository(db)

        ids = await repo.get_intent_node_session_ids(_NODE_ID)  # must not raise

        self.assertEqual(ids, [])
        db.fetch.assert_awaited_once()

    async def test_get_intent_node_session_ids_accepts_workspace_id_kwarg(self) -> None:
        """Protocol-parity guard (the exact defect a prior review round
        caught): the signature must accept ``workspace_id=`` even though the
        Postgres entity-graph layer does not plumb it through."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresEntityLinkRepository(db)

        ids = await repo.get_intent_node_session_ids(_NODE_ID, workspace_id="ws-1")  # must not raise TypeError

        self.assertEqual(ids, [])

    async def test_get_intent_node_session_ids_filters_target_type(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock(
            return_value=[
                {"source_type": "intent_node", "source_id": _NODE_ID, "target_type": "session", "target_id": "sess-1"},
                {"source_type": "intent_node", "source_id": _NODE_ID, "target_type": "other", "target_id": "not-a-session"},
            ]
        )
        repo = PostgresEntityLinkRepository(db)

        ids = await repo.get_intent_node_session_ids(_NODE_ID)

        self.assertEqual(ids, ["sess-1"])

    # -- PostgresSessionRepository.list_by_workflow_ids -----------------------

    async def test_list_by_workflow_ids_exists_and_is_callable(self) -> None:
        """The literal reviewer-flagged bug class, reproduced on the sibling
        session repository: the ``expand_family`` widen path calls this
        method, and it must exist on Postgres, not just SQLite."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresSessionRepository(db)

        rows = await repo.list_by_workflow_ids(["wf-A"], project_id="proj-1")  # must not raise

        self.assertEqual(rows, [])
        db.fetch.assert_awaited_once()

    async def test_list_by_workflow_ids_empty_workflow_ids_short_circuits(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock()
        repo = PostgresSessionRepository(db)

        rows = await repo.list_by_workflow_ids([], project_id="proj-1")

        self.assertEqual(rows, [])
        db.fetch.assert_not_called()

    async def test_list_by_workflow_ids_constrains_project_id_in_where_clause(self) -> None:
        """Cross-project-leak guard for the ``expand_family`` widen path: a
        node declared in project A must never have its family expansion pull
        in a same-``workflow_id`` session that actually belongs to project B.
        Verified against the actual production SQL text, not a
        reimplementation of its semantics.
        """
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresSessionRepository(db)

        await repo.list_by_workflow_ids(["wf-A"], project_id="proj-1")

        sql, *args = db.fetch.call_args[0]
        self.assertIn("project_id = $1", sql)
        self.assertIn("workflow_id = ANY(", sql)
        self.assertEqual(args[0], "proj-1")

    async def test_list_by_workflow_ids_array_bind_for_workflow_ids(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresSessionRepository(db)

        await repo.list_by_workflow_ids(["wf-A", "wf-B"], project_id="proj-1")

        _sql, *args = db.fetch.call_args[0]
        self.assertIn(["wf-A", "wf-B"], args)


# ---------------------------------------------------------------------------
# 2. Live-Postgres tier — PG-gated, mirrors the SQLite behavioral scenarios.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LivePGIntentNodeLinksTests(unittest.IsolatedAsyncioTestCase):
    """Live Postgres reproduction of test_entity_graph_intent_node_links.py
    and test_intent_node_cost_service.py's expand_family scenario.

    Run against compose PG:
        CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash \\
            backend/.venv/bin/python -m pytest \\
            backend/tests/test_pg_intent_node_links.py \\
            -k LivePGIntentNodeLinksTests -v
    """

    async def asyncSetUp(self) -> None:
        import asyncpg

        from backend.db.postgres_migrations import run_migrations

        self._pool = await asyncpg.create_pool(_PG_URL)
        await run_migrations(self._pool)
        self._suffix = uuid.uuid4().hex[:8]
        self._session_ids: list[str] = []
        self._node_ids: list[str] = []

    async def asyncTearDown(self) -> None:
        async with self._pool.acquire() as conn:
            if self._node_ids:
                await conn.execute(
                    "DELETE FROM entity_links WHERE source_id = ANY($1::text[])",
                    self._node_ids,
                )
            if self._session_ids:
                await conn.execute(
                    "DELETE FROM sessions WHERE id = ANY($1::text[])",
                    self._session_ids,
                )
        await self._pool.close()

    async def _insert_session(
        self,
        session_id: str,
        *,
        project_id: str,
        workflow_id: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        now = _iso(datetime.now(timezone.utc))
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO sessions
                       (id, project_id, workflow_id, started_at, ended_at,
                        tokens_in, tokens_out, created_at, updated_at, source_file)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                session_id,
                project_id,
                workflow_id,
                now,
                now,
                tokens_in,
                tokens_out,
                now,
                now,
                f"{session_id}.jsonl",
            )
        self._session_ids.append(session_id)

    async def test_declare_bindings_then_read_them_back(self) -> None:
        node_id = f"itt-node-pg-{self._suffix}"
        self._node_ids.append(node_id)
        project_id = f"proj-{self._suffix}"
        sess_id = f"sess-pg-{self._suffix}"
        await self._insert_session(sess_id, project_id=project_id, workflow_id="wf-pg-A")

        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)

            linked = await repo.link_intent_node_sessions(node_id, [sess_id], project_id=project_id)
            self.assertEqual(linked, 1)

            ids = await repo.get_intent_node_session_ids(node_id)
            self.assertEqual(ids, [sess_id])

    async def test_redeclare_same_pair_does_not_duplicate(self) -> None:
        """ADR-007 direct-count assertion, live PG: re-declaring the same
        (node, session) pair three times still leaves exactly one row."""
        node_id = f"itt-node-pg-dup-{self._suffix}"
        self._node_ids.append(node_id)
        project_id = f"proj-{self._suffix}"
        sess_id = f"sess-pg-dup-{self._suffix}"
        await self._insert_session(sess_id, project_id=project_id, workflow_id="wf-pg-dup")

        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)
            await repo.link_intent_node_sessions(node_id, [sess_id], project_id=project_id)
            await repo.link_intent_node_sessions(node_id, [sess_id], project_id=project_id)
            await repo.link_intent_node_sessions(node_id, [sess_id], project_id=project_id)

            count = await conn.fetchval(
                "SELECT COUNT(*) FROM entity_links WHERE source_type = 'intent_node' AND source_id = $1",
                node_id,
            )
            self.assertEqual(count, 1)

    async def test_list_by_workflow_ids_returns_only_same_project_siblings(self) -> None:
        """Cross-project-leak guard, live PG: two sessions share a
        workflow_id but belong to different projects -- only the
        same-project one must come back."""
        project_a = f"proj-a-{self._suffix}"
        project_b = f"proj-b-{self._suffix}"
        shared_workflow_id = f"wf-shared-{self._suffix}"
        sess_same_project = f"sess-same-{self._suffix}"
        sess_other_project = f"sess-other-{self._suffix}"
        await self._insert_session(
            sess_same_project, project_id=project_a, workflow_id=shared_workflow_id
        )
        await self._insert_session(
            sess_other_project, project_id=project_b, workflow_id=shared_workflow_id
        )

        async with self._pool.acquire() as conn:
            repo = PostgresSessionRepository(conn)
            rows = await repo.list_by_workflow_ids([shared_workflow_id], project_id=project_a)

        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {sess_same_project})


if __name__ == "__main__":
    unittest.main()
