"""Integration tests for DB-persisted OQ resolution (P3-002).

Tests verify:
1. resolve_open_question persists to DB.
2. After clearing the in-memory overlay (simulating restart), the resolution
   still reads back from DB.
3. Resolving project-A's OQ does NOT evict project-B's @memoized_query cache.

Uses a real in-memory aiosqlite database so that DB upsert/read is genuine.
Fixture style mirrors test_agent_query_cache_invalidation.py.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries import cache as cache_mod
from backend.application.services.agent_queries.cache import (
    aclear_project_cache,
    clear_cache,
)
from backend.db.repositories.oq_resolutions import OQResolutionsRepository

# ---------------------------------------------------------------------------
# DB schema helpers
# ---------------------------------------------------------------------------

_CREATE_OQ_RESOLUTIONS = """
    CREATE TABLE IF NOT EXISTS oq_resolutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        feature_id TEXT NOT NULL,
        oq_id TEXT NOT NULL,
        question TEXT DEFAULT '',
        answer_text TEXT DEFAULT '',
        severity TEXT DEFAULT 'medium',
        resolved INTEGER DEFAULT 0,
        pending_sync INTEGER DEFAULT 0,
        source_document_id TEXT DEFAULT '',
        source_document_path TEXT DEFAULT '',
        resolved_by TEXT DEFAULT '',
        created_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        UNIQUE(project_id, feature_id, oq_id)
    )
"""

_CREATE_SESSIONS = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        status TEXT,
        updated_at TEXT
    )
"""

_CREATE_FEATURES = """
    CREATE TABLE IF NOT EXISTS features (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        name TEXT,
        feature_slug TEXT,
        status TEXT,
        data_json TEXT DEFAULT '{}',
        updated_at TEXT
    )
"""

_CREATE_FEATURE_PHASES = """
    CREATE TABLE IF NOT EXISTS feature_phases (
        id TEXT PRIMARY KEY,
        feature_id TEXT NOT NULL,
        phase TEXT NOT NULL,
        title TEXT DEFAULT '',
        status TEXT DEFAULT 'backlog',
        progress INTEGER DEFAULT 0,
        total_tasks INTEGER DEFAULT 0,
        completed_tasks INTEGER DEFAULT 0
    )
"""

_CREATE_DOCUMENTS = """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        doc_type TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        last_modified TEXT DEFAULT ''
    )
"""

_CREATE_ENTITY_LINKS = """
    CREATE TABLE IF NOT EXISTS entity_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        link_type TEXT DEFAULT 'related',
        created_at TEXT NOT NULL,
        project_id TEXT DEFAULT ''
    )
"""

_CREATE_PLANNING_WORKTREE_CONTEXTS = """
    CREATE TABLE IF NOT EXISTS planning_worktree_contexts (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        feature_id TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

_CREATE_QUERY_CACHE = """
    CREATE TABLE IF NOT EXISTS query_cache (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        project_id TEXT DEFAULT '',
        expires_at TEXT NOT NULL
    )
"""


async def _setup_schema(db: aiosqlite.Connection) -> None:
    for ddl in (
        _CREATE_OQ_RESOLUTIONS,
        _CREATE_SESSIONS,
        _CREATE_FEATURES,
        _CREATE_FEATURE_PHASES,
        _CREATE_DOCUMENTS,
        _CREATE_ENTITY_LINKS,
        _CREATE_PLANNING_WORKTREE_CONTEXTS,
        _CREATE_QUERY_CACHE,
    ):
        await db.execute(ddl)
    await db.commit()


# ---------------------------------------------------------------------------
# Ports / context helpers
# ---------------------------------------------------------------------------


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    """Storage shim backed by a real aiosqlite connection."""

    def __init__(self, *, db: aiosqlite.Connection, features_data: dict) -> None:
        self.db = db
        self._features_data = features_data
        self._doc_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[]),
            list_all=AsyncMock(return_value=[]),
        )
        self._task_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))

    def features(self):
        features_data = self._features_data

        async def get_by_id(feature_id):
            return features_data.get(feature_id)

        async def get_many_by_ids(ids):
            return {fid: features_data[fid] for fid in ids if fid in features_data}

        async def list_all(project_id=None):
            return list(features_data.values())

        return types.SimpleNamespace(
            get_by_id=get_by_id,
            get_many_by_ids=get_many_by_ids,
            list_all=list_all,
        )

    def documents(self):
        return self._doc_repo

    def tasks(self):
        return self._task_repo

    def sessions(self):
        return types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=None),
            get_many_by_ids=AsyncMock(return_value={}),
        )

    def entity_links(self):
        return types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))

    def session_messages(self):
        return types.SimpleNamespace(list_by_session=AsyncMock(return_value=[]))


def _context(project_id: str = "project-oq-test") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="OQ Test Project",
            root_path=Path("/tmp/oq-project"),
            sessions_dir=Path("/tmp/oq-project/sessions"),
            docs_dir=Path("/tmp/oq-project/docs"),
            progress_dir=Path("/tmp/oq-project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-oq-test"),
    )


def _ports(
    *,
    db: aiosqlite.Connection,
    features_data: dict,
    project_id: str = "project-oq-test",
) -> CorePorts:
    project = types.SimpleNamespace(id=project_id, name="OQ Test Project")
    storage = _Storage(db=db, features_data=features_data)
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=storage,
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Feature data helpers
# ---------------------------------------------------------------------------

_FEATURE_WITH_OQ = {
    "id": "feat-oq-1",
    "name": "OQ Feature",
    "feature_slug": "feat-oq-1",
    "status": "in_progress",
    "updated_at": "2026-06-01T08:00:00+00:00",
    "data_json": '{"openQuestions": [{"oq_id": "oq-1", "question": "How to scale?", "severity": "high"}]}',
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class OQResolutionRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for OQResolutionsRepository upsert/read."""

    async def asyncSetUp(self) -> None:
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)
        self._repo = OQResolutionsRepository(self._db)

    async def asyncTearDown(self) -> None:
        await self._db.close()

    async def test_upsert_and_read_back(self) -> None:
        """upsert stores a row; list_for_feature returns it."""
        await self._repo.upsert(
            {
                "project_id": "proj-a",
                "feature_id": "feat-1",
                "oq_id": "oq-1",
                "question": "How to scale?",
                "answer_text": "Use sharding.",
                "severity": "high",
                "resolved": True,
                "pending_sync": True,
                "source_document_id": "doc-1",
                "source_document_path": "/path/doc.md",
                "resolved_by": "agent",
                "created_at": "2026-06-01T10:00:00+00:00",
                "updated_at": "2026-06-01T10:00:00+00:00",
            }
        )
        rows = await self._repo.list_for_feature("proj-a", "feat-1")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["oq_id"], "oq-1")
        self.assertEqual(row["answer_text"], "Use sharding.")
        self.assertTrue(bool(row["resolved"]))

    async def test_upsert_updates_existing(self) -> None:
        """Second upsert with same key updates answer_text."""
        base = {
            "project_id": "proj-a",
            "feature_id": "feat-1",
            "oq_id": "oq-1",
            "question": "Q?",
            "answer_text": "First answer",
            "severity": "medium",
            "resolved": False,
            "pending_sync": False,
            "source_document_id": "",
            "source_document_path": "",
            "resolved_by": "",
            "created_at": "2026-06-01T10:00:00+00:00",
            "updated_at": "2026-06-01T10:00:00+00:00",
        }
        await self._repo.upsert(base)
        await self._repo.upsert({**base, "answer_text": "Updated answer", "resolved": True})
        row = await self._repo.get_one("proj-a", "feat-1", "oq-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["answer_text"], "Updated answer")  # type: ignore[index]
        self.assertTrue(bool(row["resolved"]))  # type: ignore[index]

    async def test_list_scoped_to_feature(self) -> None:
        """list_for_feature only returns rows for the given (project, feature) pair."""
        for fid in ("feat-1", "feat-2"):
            await self._repo.upsert(
                {
                    "project_id": "proj-a",
                    "feature_id": fid,
                    "oq_id": "oq-1",
                    "question": "Q?",
                    "answer_text": "A",
                    "severity": "low",
                    "resolved": True,
                    "pending_sync": False,
                    "source_document_id": "",
                    "source_document_path": "",
                    "resolved_by": "",
                    "created_at": "2026-06-01T10:00:00+00:00",
                    "updated_at": "2026-06-01T10:00:00+00:00",
                }
            )
        rows = await self._repo.list_for_feature("proj-a", "feat-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature_id"], "feat-1")

    async def test_missing_key_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            await self._repo.upsert({"project_id": "p", "feature_id": "", "oq_id": "oq-1"})


class OQResolutionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end: resolve_open_question persists to DB; survives in-memory clear."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)
        self._project_id = "project-oq-test"
        self._feature_id = "feat-oq-1"
        self._features_data = {self._feature_id: _FEATURE_WITH_OQ}
        self._ctx = _context(self._project_id)
        self._ports = _ports(
            db=self._db,
            features_data=self._features_data,
            project_id=self._project_id,
        )

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()
        # Reset in-memory overlay between tests.
        from backend.application.services.agent_queries import planning as planning_mod  # noqa: PLC0415
        planning_mod._OQ_OVERLAY.clear()

    async def test_resolve_persists_to_db(self) -> None:
        """resolve_open_question writes the answer to oq_resolutions table."""
        from backend.application.services.agent_queries.planning import PlanningQueryService  # noqa: PLC0415

        svc = PlanningQueryService()
        result = await svc.resolve_open_question(
            self._ctx,
            self._ports,
            feature_id=self._feature_id,
            oq_id="oq-1",
            answer_text="Use sharding for scale.",
        )
        self.assertTrue(result.oq.resolved)
        self.assertEqual(result.oq.answer_text, "Use sharding for scale.")

        # Verify DB row exists.
        repo = OQResolutionsRepository(self._db)
        row = await repo.get_one(self._project_id, self._feature_id, "oq-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["answer_text"], "Use sharding for scale.")  # type: ignore[index]
        self.assertTrue(bool(row["resolved"]))  # type: ignore[index]

    async def test_resolve_survives_memory_clear(self) -> None:
        """After clearing in-memory overlay, the resolution reads back from DB.

        This simulates a process restart where _OQ_OVERLAY is empty but the DB
        retains the persisted resolution.
        """
        from backend.application.services.agent_queries.planning import (  # noqa: PLC0415
            PlanningQueryService,
            _open_question_overlays_for_feature,
            _OQ_OVERLAY,
        )

        svc = PlanningQueryService()
        await svc.resolve_open_question(
            self._ctx,
            self._ports,
            feature_id=self._feature_id,
            oq_id="oq-1",
            answer_text="Sharding answer.",
        )

        # Simulate restart: wipe in-memory overlay completely.
        _OQ_OVERLAY.clear()

        # Read back from DB (no in-memory cache).
        overlays = await _open_question_overlays_for_feature(
            self._feature_id,
            db=self._db,
            project_id=self._project_id,
        )
        resolved = [o for o in overlays if o.resolved]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].answer_text, "Sharding answer.")

    async def test_read_after_memory_clear_rewarms_cache(self) -> None:
        """After resolving and then clearing in-memory cache, a subsequent read
        from DB re-warms the in-memory overlay for that feature."""
        from backend.application.services.agent_queries.planning import (  # noqa: PLC0415
            PlanningQueryService,
            _OQ_OVERLAY,
            _feature_key,
            _open_question_overlays_for_feature,
        )

        svc = PlanningQueryService()
        await svc.resolve_open_question(
            self._ctx,
            self._ports,
            feature_id=self._feature_id,
            oq_id="oq-1",
            answer_text="Cached answer.",
        )
        # After resolve, aclear_project_cache evicts the overlay.
        _OQ_OVERLAY.clear()

        # A fresh read from DB should re-warm the in-memory overlay.
        overlays = await _open_question_overlays_for_feature(
            self._feature_id, db=self._db, project_id=self._project_id
        )
        self.assertTrue(any(o.resolved for o in overlays))

        # And the in-memory cache is now populated.
        key = _feature_key(self._feature_id)
        self.assertIn(key, _OQ_OVERLAY)
        slot = _OQ_OVERLAY[key]
        self.assertTrue(any(v.resolved for v in slot.values()))


class OQResolutionProjectIsolationTests(unittest.IsolatedAsyncioTestCase):
    """Resolving project-A's OQ must not evict project-B's @memoized_query cache."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)

        self._proj_a = "project-a"
        self._proj_b = "project-b"
        self._feature_id = "feat-oq-1"

        self._features_a = {self._feature_id: _FEATURE_WITH_OQ}
        self._features_b = {
            "feat-b-1": {
                "id": "feat-b-1",
                "name": "B Feature",
                "feature_slug": "feat-b-1",
                "status": "in_progress",
                "updated_at": "2026-06-01T09:00:00+00:00",
                "data_json": "{}",
            }
        }

        self._ctx_a = _context(self._proj_a)
        self._ctx_b = _context(self._proj_b)
        self._ports_a = _ports(db=self._db, features_data=self._features_a, project_id=self._proj_a)
        self._ports_b = _ports(db=self._db, features_data=self._features_b, project_id=self._proj_b)

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()
        from backend.application.services.agent_queries import planning as planning_mod  # noqa: PLC0415
        planning_mod._OQ_OVERLAY.clear()

    async def test_proj_a_oq_does_not_evict_proj_b_cache(self) -> None:
        """Cache keys for project-B survive a resolve_open_question on project-A.

        We inject a synthetic cache entry for project-B before resolving project-A's OQ,
        then assert the entry is still present afterwards.
        """
        from backend.application.services.agent_queries.cache import (  # noqa: PLC0415
            _in_process_set,
            compute_cache_key,
        )
        from backend.application.services.agent_queries.planning import (  # noqa: PLC0415
            PlanningQueryService,
        )

        # Inject a synthetic project-B cache entry.
        b_key = compute_cache_key("project_status", self._proj_b, {}, "fp-b-stub")
        _in_process_set(b_key, {"status": "ok", "project_id": self._proj_b}, ttl=300)

        # Resolve project-A's OQ.
        svc = PlanningQueryService()
        await svc.resolve_open_question(
            self._ctx_a,
            self._ports_a,
            feature_id=self._feature_id,
            oq_id="oq-1",
            answer_text="Scale with sharding.",
        )

        # project-B's cache entry must still be present.
        from backend.application.services.agent_queries.cache import _in_process_get  # noqa: PLC0415
        cached = _in_process_get(b_key)
        self.assertIsNotNone(
            cached,
            "project-B cache entry was evicted when resolving project-A's OQ",
        )
        self.assertEqual(cached["project_id"], self._proj_b)

    async def test_proj_a_oq_evicts_proj_a_cache(self) -> None:
        """After resolving project-A's OQ, project-A cache entries are gone."""
        from backend.application.services.agent_queries.cache import (  # noqa: PLC0415
            _in_process_set,
            compute_cache_key,
            _in_process_get,
        )
        from backend.application.services.agent_queries.planning import (  # noqa: PLC0415
            PlanningQueryService,
        )

        a_key = compute_cache_key("planning_feature_context", self._proj_a, {}, "fp-a-stub")
        _in_process_set(a_key, {"status": "ok", "project_id": self._proj_a}, ttl=300)

        svc = PlanningQueryService()
        await svc.resolve_open_question(
            self._ctx_a,
            self._ports_a,
            feature_id=self._feature_id,
            oq_id="oq-1",
            answer_text="Scale with sharding.",
        )

        cached = _in_process_get(a_key)
        self.assertIsNone(cached, "project-A cache entry should have been evicted after OQ resolve")
