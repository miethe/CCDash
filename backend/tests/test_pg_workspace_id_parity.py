"""Unit tests for Postgres documents/tasks/features upsert workspace_id parity (ADR-008).

Covers the ADR-008 parity gap where the Postgres document, task, and feature
upserts were missing the ``workspace_id`` keyword argument, causing
``TypeError: upsert() got an unexpected keyword argument 'workspace_id'`` on the
sync/link-rebuild hot path.

Also asserts that ``list_all`` on all three repos accepts ``workspace_id=``
(these were already correct but are verified here to prevent future regression).

No live Postgres required — uses lightweight mock connections that record SQL
and bind args issued by each method.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_pg_workspace_id_parity.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, call

from backend.db.repositories.base import DEFAULT_WORKSPACE_ID
from backend.db.repositories.postgres.documents import PostgresDocumentRepository
from backend.db.repositories.postgres.tasks import PostgresTaskRepository
from backend.db.repositories.postgres.features import PostgresFeatureRepository


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_db_execute() -> MagicMock:
    """Mock asyncpg connection whose .execute() is an AsyncMock."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=None)
    db.executemany = AsyncMock(return_value=None)
    return db


def _make_db_fetch() -> MagicMock:
    """Mock asyncpg connection whose .fetch() is an AsyncMock returning []."""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])
    return db


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_DOC = {
    "id": "doc-001",
    "title": "My Doc",
    "filePath": "docs/my-doc.md",
    "rootKind": "project_plans",
    "status": "active",
    "frontmatter": {},
    "metadata": {},
    "sourceFile": "docs/my-doc.md",
}

_SAMPLE_TASK = {
    "id": "task-001",
    "title": "My Task",
    "status": "backlog",
    "sourceFile": "tasks/my-task.md",
}

_SAMPLE_FEATURE = {
    "id": "feat-001",
    "name": "My Feature",
    "status": "backlog",
}


# ---------------------------------------------------------------------------
# DocumentRepository tests
# ---------------------------------------------------------------------------

class TestPostgresDocumentUpsertWorkspaceId(unittest.IsolatedAsyncioTestCase):
    """PostgresDocumentRepository.upsert now accepts workspace_id."""

    async def test_upsert_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_execute()
        repo = PostgresDocumentRepository(db)
        # Must not raise TypeError.  Document upsert calls execute twice
        # (INSERT + DELETE FROM document_refs), so assert_called() not once.
        await repo.upsert(_SAMPLE_DOC, "proj-1", workspace_id="ws-abc")
        db.execute.assert_called()

    async def test_upsert_uses_default_workspace_id_when_omitted(self) -> None:
        db = _make_db_execute()
        repo = PostgresDocumentRepository(db)
        await repo.upsert(_SAMPLE_DOC, "proj-1")
        db.execute.assert_called()
        # workspace_id is the 4th positional arg in the first call
        # (query, id, project_id, workspace_id, title, ...)
        first_call_positional = db.execute.call_args_list[0][0]
        self.assertEqual(first_call_positional[3], DEFAULT_WORKSPACE_ID)

    async def test_upsert_forwards_custom_workspace_id(self) -> None:
        db = _make_db_execute()
        repo = PostgresDocumentRepository(db)
        await repo.upsert(_SAMPLE_DOC, "proj-1", workspace_id="ws-custom")
        first_call_positional = db.execute.call_args_list[0][0]
        # 4th positional arg (index 3) after query string is workspace_id
        self.assertEqual(first_call_positional[3], "ws-custom")

    async def test_list_all_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_fetch()
        repo = PostgresDocumentRepository(db)
        # Must not raise TypeError
        result = await repo.list_all("proj-1", workspace_id="ws-abc")
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# TaskRepository tests
# ---------------------------------------------------------------------------

class TestPostgresTaskUpsertWorkspaceId(unittest.IsolatedAsyncioTestCase):
    """PostgresTaskRepository.upsert now accepts workspace_id."""

    async def test_upsert_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_execute()
        repo = PostgresTaskRepository(db)
        # Must not raise TypeError
        await repo.upsert(_SAMPLE_TASK, "proj-1", workspace_id="ws-abc")
        db.execute.assert_called_once()

    async def test_upsert_uses_default_workspace_id_when_omitted(self) -> None:
        db = _make_db_execute()
        repo = PostgresTaskRepository(db)
        await repo.upsert(_SAMPLE_TASK, "proj-1")
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        positional = call_args[0]  # (query, id, project_id, workspace_id, title, ...)
        self.assertEqual(positional[3], DEFAULT_WORKSPACE_ID)

    async def test_upsert_forwards_custom_workspace_id(self) -> None:
        db = _make_db_execute()
        repo = PostgresTaskRepository(db)
        await repo.upsert(_SAMPLE_TASK, "proj-1", workspace_id="ws-custom")
        call_args = db.execute.call_args
        positional = call_args[0]
        self.assertEqual(positional[3], "ws-custom")

    async def test_list_all_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_fetch()
        repo = PostgresTaskRepository(db)
        result = await repo.list_all("proj-1", workspace_id="ws-abc")
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# FeatureRepository tests
# ---------------------------------------------------------------------------

class TestPostgresFeatureUpsertWorkspaceId(unittest.IsolatedAsyncioTestCase):
    """PostgresFeatureRepository.upsert now accepts workspace_id."""

    async def test_upsert_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_execute()
        repo = PostgresFeatureRepository(db)
        # Must not raise TypeError
        await repo.upsert(_SAMPLE_FEATURE, "proj-1", workspace_id="ws-abc")
        db.execute.assert_called_once()

    async def test_upsert_uses_default_workspace_id_when_omitted(self) -> None:
        db = _make_db_execute()
        repo = PostgresFeatureRepository(db)
        await repo.upsert(_SAMPLE_FEATURE, "proj-1")
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        positional = call_args[0]  # (query, id, project_id, workspace_id, name, ...)
        self.assertEqual(positional[3], DEFAULT_WORKSPACE_ID)

    async def test_upsert_forwards_custom_workspace_id(self) -> None:
        db = _make_db_execute()
        repo = PostgresFeatureRepository(db)
        await repo.upsert(_SAMPLE_FEATURE, "proj-1", workspace_id="ws-custom")
        call_args = db.execute.call_args
        positional = call_args[0]
        self.assertEqual(positional[3], "ws-custom")

    async def test_list_all_accepts_workspace_id_kwarg(self) -> None:
        db = _make_db_fetch()
        repo = PostgresFeatureRepository(db)
        result = await repo.list_all("proj-1", workspace_id="ws-abc")
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
