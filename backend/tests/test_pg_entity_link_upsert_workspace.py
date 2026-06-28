"""Unit tests for PostgresEntityLinkRepository.upsert workspace_id parity.

Covers the ADR-008 parity gap where the Postgres entity-link upsert was
missing the ``workspace_id`` keyword argument, crashing the incremental
link-rebuild hot path (~14x/min on the streaming worker).

No live Postgres required — uses a lightweight mock connection that records
the SQL and bind args issued by ``upsert``.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_pg_entity_link_upsert_workspace.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.db.repositories.base import DEFAULT_WORKSPACE_ID
from backend.db.repositories.postgres.entity_graph import PostgresEntityLinkRepository


def _make_mock_db(fetchval_return: int = 42) -> MagicMock:
    """Return a mock asyncpg connection that records ``fetchval`` calls."""
    db = MagicMock()
    db.fetchval = AsyncMock(return_value=fetchval_return)
    return db


_SAMPLE_LINK = {
    "source_type": "session",
    "source_id": "sess-abc",
    "target_type": "feature",
    "target_id": "feat-xyz",
    "link_type": "related",
    "origin": "auto",
    "confidence": 0.9,
    "depth": 0,
    "sort_order": 0,
    "metadata_json": None,
}


class TestPostgresEntityLinkUpsertSignature(unittest.IsolatedAsyncioTestCase):
    """upsert accepts workspace_id as a keyword argument (was TypeError before fix)."""

    async def test_upsert_accepts_workspace_id_kwarg(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        # Must not raise TypeError
        result = await repo.upsert(_SAMPLE_LINK, workspace_id="default-local")
        self.assertEqual(result, 42)

    async def test_upsert_uses_default_workspace_id_when_omitted(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        result = await repo.upsert(_SAMPLE_LINK)
        self.assertEqual(result, 42)
        db.fetchval.assert_called_once()

    async def test_upsert_forwards_custom_workspace_id(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="ws-remote-123")
        # First positional arg after SQL is workspace_id
        call_args = db.fetchval.call_args
        # call_args[0] = (sql, *bind_args); bind_args start at index 1
        bind_args = call_args[0][1:]
        self.assertEqual(bind_args[0], "ws-remote-123")


class TestPostgresEntityLinkUpsertSQL(unittest.IsolatedAsyncioTestCase):
    """Generated SQL includes workspace_id as the first inserted column."""

    async def test_sql_contains_workspace_id_column(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="default-local")
        sql = db.fetchval.call_args[0][0]
        self.assertIn("workspace_id", sql)

    async def test_workspace_id_is_first_inserted_column(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="default-local")
        sql: str = db.fetchval.call_args[0][0]
        # workspace_id must appear before source_type in the column list
        self.assertLess(
            sql.index("workspace_id"),
            sql.index("source_type"),
            "workspace_id must be the first column in the INSERT column list",
        )

    async def test_workspace_id_is_first_bind_value(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="default-local")
        bind_args = db.fetchval.call_args[0][1:]
        self.assertEqual(
            bind_args[0],
            "default-local",
            "workspace_id must be the first bind value ($1)",
        )

    async def test_placeholder_count_matches_column_count(self) -> None:
        """12 columns → VALUES ($1 .. $12)."""
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="default-local")
        # 12 bind args: workspace_id + 11 original columns
        bind_args = db.fetchval.call_args[0][1:]
        self.assertEqual(len(bind_args), 12)

    async def test_default_workspace_id_constant(self) -> None:
        """DEFAULT_WORKSPACE_ID sentinel matches the expected value."""
        self.assertEqual(DEFAULT_WORKSPACE_ID, "default-local")


class TestPostgresEntityLinkUpsertBindValues(unittest.IsolatedAsyncioTestCase):
    """Bind values are assembled in the correct order after workspace_id."""

    async def test_source_type_is_second_bind_value(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        link = dict(_SAMPLE_LINK)
        await repo.upsert(link, workspace_id="ws-test")
        bind_args = db.fetchval.call_args[0][1:]
        self.assertEqual(bind_args[1], "session")  # source_type

    async def test_source_id_is_third_bind_value(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="ws-test")
        bind_args = db.fetchval.call_args[0][1:]
        self.assertEqual(bind_args[2], "sess-abc")  # source_id

    async def test_target_type_and_id(self) -> None:
        db = _make_mock_db()
        repo = PostgresEntityLinkRepository(db)
        await repo.upsert(_SAMPLE_LINK, workspace_id="ws-test")
        bind_args = db.fetchval.call_args[0][1:]
        self.assertEqual(bind_args[3], "feature")  # target_type
        self.assertEqual(bind_args[4], "feat-xyz")  # target_id


if __name__ == "__main__":
    unittest.main()
