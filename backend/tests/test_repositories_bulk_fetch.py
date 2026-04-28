"""Tests for bulk-fetch repository methods added in the N+1 remediation pass.

Covers:
- SqliteSessionRepository.get_many_by_ids
- SqliteFeatureRepository.get_many_by_ids
- SqliteDocumentRepository.get_many_by_ids
- SqliteEntityLinkRepository.get_links_for_many
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Minimal DDL for entity_links (run_migrations covers the rest)
# ---------------------------------------------------------------------------

_ENTITY_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS entity_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type   TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    link_type     TEXT DEFAULT 'related',
    origin        TEXT DEFAULT 'auto',
    confidence    REAL DEFAULT 1.0,
    depth         INTEGER DEFAULT 0,
    sort_order    INTEGER DEFAULT 0,
    metadata_json TEXT,
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert
    ON entity_links(source_type, source_id, target_type, target_id, link_type);
"""

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_SESSION_BASE: dict = {
    "taskId": "",
    "status": "completed",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "platformVersion": "1.0",
    "platformVersions": [],
    "platformVersionTransitions": [],
    "durationSeconds": 1,
    "tokensIn": 1,
    "tokensOut": 1,
    "modelIOTokens": 2,
    "cacheCreationInputTokens": 0,
    "cacheReadInputTokens": 0,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.0,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": None,
    "startedAt": "2026-01-01T00:00:00Z",
    "endedAt": "2026-01-01T00:00:01Z",
    "sourceFile": "",
}


# ===========================================================================
# Session repository
# ===========================================================================

class TestSessionGetManyByIds(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)
        for sid in ("s1", "s2", "s3"):
            await self.repo.upsert({**_SESSION_BASE, "id": sid}, "proj-1")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_empty_input_returns_empty_dict(self) -> None:
        result = await self.repo.get_many_by_ids([])
        self.assertEqual(result, {})

    async def test_single_id_returns_single_row(self) -> None:
        result = await self.repo.get_many_by_ids(["s1"])
        self.assertIn("s1", result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result["s1"]["id"], "s1")

    async def test_multi_id_returns_all_matched(self) -> None:
        result = await self.repo.get_many_by_ids(["s1", "s2", "s3"])
        self.assertEqual(set(result.keys()), {"s1", "s2", "s3"})

    async def test_nonexistent_id_not_in_result(self) -> None:
        result = await self.repo.get_many_by_ids(["s1", "missing"])
        self.assertIn("s1", result)
        self.assertNotIn("missing", result)

    async def test_all_nonexistent_returns_empty(self) -> None:
        result = await self.repo.get_many_by_ids(["x", "y"])
        self.assertEqual(result, {})


# ===========================================================================
# Feature repository
# ===========================================================================

_FEATURE_BASE: dict = {
    "name": "Feature",
    "status": "active",
    "category": "test",
    "totalTasks": 0,
    "completedTasks": 0,
    "parentFeatureId": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
    "completedAt": "",
}


class TestFeatureGetManyByIds(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteFeatureRepository(self.db)
        for fid in ("f1", "f2", "f3"):
            await self.repo.upsert({**_FEATURE_BASE, "id": fid}, "proj-1")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_empty_input_returns_empty_dict(self) -> None:
        result = await self.repo.get_many_by_ids([])
        self.assertEqual(result, {})

    async def test_single_id_returns_single_row(self) -> None:
        result = await self.repo.get_many_by_ids(["f1"])
        self.assertIn("f1", result)
        self.assertEqual(len(result), 1)

    async def test_multi_id_returns_all_matched(self) -> None:
        result = await self.repo.get_many_by_ids(["f1", "f2", "f3"])
        self.assertEqual(set(result.keys()), {"f1", "f2", "f3"})

    async def test_nonexistent_id_not_in_result(self) -> None:
        result = await self.repo.get_many_by_ids(["f1", "missing"])
        self.assertIn("f1", result)
        self.assertNotIn("missing", result)

    async def test_all_nonexistent_returns_empty(self) -> None:
        result = await self.repo.get_many_by_ids(["x"])
        self.assertEqual(result, {})


# ===========================================================================
# Document repository
# ===========================================================================

_DOC_BASE: dict = {
    "title": "Doc",
    "filePath": "docs/doc.md",
    "rootKind": "project_plans",
    "docSubtype": "",
    "hasFrontmatter": False,
    "frontmatterType": "",
    "status": "active",
    "statusNormalized": "active",
    "author": "",
    "docType": "",
    "category": "",
    "featureSlugHint": "",
    "featureSlugCanonical": "",
    "prdRef": "",
    "phaseToken": "",
    "totalTasks": 0,
    "completedTasks": 0,
    "inProgressTasks": 0,
    "blockedTasks": 0,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
    "lastModified": "",
    "sourceFile": "docs/doc.md",
}


class TestDocumentGetManyByIds(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteDocumentRepository(self.db)
        for did in ("d1", "d2", "d3"):
            await self.repo.upsert({**_DOC_BASE, "id": did, "filePath": f"docs/{did}.md"}, "proj-1")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_empty_input_returns_empty_dict(self) -> None:
        result = await self.repo.get_many_by_ids([])
        self.assertEqual(result, {})

    async def test_single_id_returns_single_row(self) -> None:
        result = await self.repo.get_many_by_ids(["d1"])
        self.assertIn("d1", result)
        self.assertEqual(len(result), 1)

    async def test_multi_id_returns_all_matched(self) -> None:
        result = await self.repo.get_many_by_ids(["d1", "d2", "d3"])
        self.assertEqual(set(result.keys()), {"d1", "d2", "d3"})

    async def test_nonexistent_id_not_in_result(self) -> None:
        result = await self.repo.get_many_by_ids(["d1", "missing"])
        self.assertIn("d1", result)
        self.assertNotIn("missing", result)

    async def test_all_nonexistent_returns_empty(self) -> None:
        result = await self.repo.get_many_by_ids(["x"])
        self.assertEqual(result, {})


# ===========================================================================
# EntityLink repository
# ===========================================================================

class TestEntityLinkGetLinksForMany(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(_ENTITY_LINKS_DDL)
        self.repo = SqliteEntityLinkRepository(self.db)

        # f1 → session-a
        await self.repo.upsert({
            "source_type": "feature", "source_id": "f1",
            "target_type": "session", "target_id": "session-a",
            "link_type": "related",
        })
        # f1 → session-b
        await self.repo.upsert({
            "source_type": "feature", "source_id": "f1",
            "target_type": "session", "target_id": "session-b",
            "link_type": "related",
        })
        # f2 → session-c
        await self.repo.upsert({
            "source_type": "feature", "source_id": "f2",
            "target_type": "session", "target_id": "session-c",
            "link_type": "related",
        })
        # f3 has no links

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_empty_input_returns_empty_dict(self) -> None:
        result = await self.repo.get_links_for_many("feature", [])
        self.assertEqual(result, {})

    async def test_single_id_with_links(self) -> None:
        result = await self.repo.get_links_for_many("feature", ["f1"])
        self.assertIn("f1", result)
        self.assertEqual(len(result["f1"]), 2)

    async def test_multi_id_returns_grouped_links(self) -> None:
        result = await self.repo.get_links_for_many("feature", ["f1", "f2"])
        self.assertIn("f1", result)
        self.assertIn("f2", result)
        self.assertEqual(len(result["f1"]), 2)
        self.assertEqual(len(result["f2"]), 1)

    async def test_id_with_no_links_maps_to_empty_list(self) -> None:
        result = await self.repo.get_links_for_many("feature", ["f1", "f3"])
        self.assertIn("f3", result)
        self.assertEqual(result["f3"], [])

    async def test_nonexistent_id_maps_to_empty_list(self) -> None:
        result = await self.repo.get_links_for_many("feature", ["missing"])
        self.assertIn("missing", result)
        self.assertEqual(result["missing"], [])

    async def test_all_ids_present_in_result_keys(self) -> None:
        ids = ["f1", "f2", "f3"]
        result = await self.repo.get_links_for_many("feature", ids)
        for fid in ids:
            self.assertIn(fid, result)


# ===========================================================================
# Callsite regression — ensure get_many_by_ids is called, not get_by_id
# ===========================================================================

class TestFeatureForensicsBulkCallsite(unittest.IsolatedAsyncioTestCase):
    """Verify that _load_feature_session_rows uses get_many_by_ids, not get_by_id."""

    async def test_bulk_fetch_called_not_per_id(self) -> None:
        import types
        from unittest.mock import AsyncMock
        from backend.application.services.agent_queries.feature_forensics import (
            _load_feature_session_rows,
        )
        from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
        from pathlib import Path

        get_by_id_call_count = 0
        get_many_by_ids_call_count = 0

        async def _get_by_id(sid: str) -> dict | None:
            nonlocal get_by_id_call_count
            get_by_id_call_count += 1
            return {"id": sid, "status": "completed", "started_at": "", "ended_at": "", "total_cost": 0.0, "observed_tokens": 0}

        async def _get_many_by_ids(ids: list[str]) -> dict[str, dict]:
            nonlocal get_many_by_ids_call_count
            get_many_by_ids_call_count += 1
            return {sid: {"id": sid, "status": "completed", "started_at": "", "ended_at": "", "total_cost": 0.0, "observed_tokens": 0} for sid in ids}

        sessions_repo = types.SimpleNamespace(
            get_by_id=_get_by_id,
            get_many_by_ids=_get_many_by_ids,
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        ports = types.SimpleNamespace(storage=storage)
        context = RequestContext(
            principal=Principal(subject="t", display_name="T", auth_mode="t"),
            workspace=None,
            project=ProjectScope(
                project_id="p1",
                project_name="P1",
                root_path=Path("/tmp"),
                sessions_dir=Path("/tmp"),
                docs_dir=Path("/tmp"),
                progress_dir=Path("/tmp"),
            ),
            runtime_profile="test",
            trace=TraceContext(request_id="r1"),
        )

        result = await _load_feature_session_rows(context, ports, "feature-1", ["s1", "s2", "s3"])

        self.assertEqual(get_by_id_call_count, 0, "get_by_id must NOT be called")
        self.assertEqual(get_many_by_ids_call_count, 1, "get_many_by_ids must be called exactly once")
        self.assertEqual(len(result), 3)
