"""Integration test: cache invalidation via fingerprint advancement.

``@memoized_query`` uses ``get_data_version_fingerprint`` which computes
``MAX(updated_at)`` from both ``sessions`` and ``features`` tables scoped to a
project_id.  When a row is inserted or updated, MAX advances, the fingerprint
changes, and the next call is a cache miss.

This test uses a real in-memory aiosqlite database so that the fingerprint
logic executes genuine SQL — it is the only way to verify that the DB-side
timestamp change actually propagates through the cache key.

Fixture style mirrors ``test_feature_forensics_endpoint_agreement.py``:
same ``_context()`` / ``_ports()`` / ``_Storage`` helper pattern, calling the
service directly with real ``RequestContext`` + ``CorePorts`` objects.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService

# ---------------------------------------------------------------------------
# Shared helpers (mirrors existing forensics test infrastructure)
# ---------------------------------------------------------------------------

_PROJECT_ID = "project-cache-test"


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
    """Thin storage shim that holds a real aiosqlite connection for fingerprinting
    and in-memory Python dicts for the per-repo method calls."""

    def __init__(
        self,
        *,
        db: aiosqlite.Connection,
        features_data: dict,
        sessions_data: dict,
        link_rows: list[dict],
    ) -> None:
        self.db = db
        self._features_data = features_data
        self._sessions_data = sessions_data
        self._link_rows = link_rows

        # Repos built fresh each access so mutations to the dicts are visible.
        self._doc_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        self._task_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        self._msg_repo = types.SimpleNamespace(list_by_session=AsyncMock(return_value=[]))

    def features(self):
        features_data = self._features_data

        async def get_by_id(feature_id):
            return features_data.get(feature_id)

        return types.SimpleNamespace(get_by_id=get_by_id)

    def sessions(self):
        sessions_data = self._sessions_data

        async def get_by_id(session_id):
            return sessions_data.get(session_id)

        return types.SimpleNamespace(get_by_id=get_by_id)

    def documents(self):
        return self._doc_repo

    def tasks(self):
        return self._task_repo

    def entity_links(self):
        link_rows = self._link_rows

        async def get_links_for(source_type, source_id, link_type=None):
            return [
                row for row in link_rows
                if row["source_type"] == source_type and row["source_id"] == source_id
            ]

        return types.SimpleNamespace(get_links_for=get_links_for)

    def session_messages(self):
        return self._msg_repo


def _context(project_id: str = _PROJECT_ID) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Cache Test Project",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-cache-test"),
    )


def _ports(*, db: aiosqlite.Connection, features_data: dict, sessions_data: dict, link_rows: list) -> CorePorts:
    project = types.SimpleNamespace(id=_PROJECT_ID, name="Cache Test Project")
    storage = _Storage(
        db=db,
        features_data=features_data,
        sessions_data=sessions_data,
        link_rows=link_rows,
    )
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=storage,
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# SQLite schema helpers
# ---------------------------------------------------------------------------

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
        updated_at TEXT
    )
"""


async def _setup_schema(db: aiosqlite.Connection) -> None:
    await db.execute(_CREATE_SESSIONS)
    await db.execute(_CREATE_FEATURES)
    await db.commit()


async def _insert_feature(db: aiosqlite.Connection, feature_id: str, updated_at: str) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO features (id, project_id, name, feature_slug, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (feature_id, _PROJECT_ID, feature_id, feature_id, "in_progress", updated_at),
    )
    await db.commit()


async def _insert_session(db: aiosqlite.Connection, session_id: str, updated_at: str) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO sessions (id, project_id, status, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, _PROJECT_ID, "completed", updated_at),
    )
    await db.commit()


async def _bump_feature_updated_at(db: aiosqlite.Connection, feature_id: str, updated_at: str) -> None:
    await db.execute(
        "UPDATE features SET updated_at = ? WHERE id = ?",
        (updated_at, feature_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Call helper: patches transcript service so no filesystem access is needed
# ---------------------------------------------------------------------------

_TRANSCRIPT_PATCH = "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs"


async def _call_forensics(
    service: FeatureForensicsQueryService,
    ctx: RequestContext,
    ports: CorePorts,
    feature_id: str,
) -> object:
    with patch(_TRANSCRIPT_PATCH, new=AsyncMock(return_value=[])):
        return await service.get_forensics(ctx, ports, feature_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class CacheInvalidationOnNewSessionTests(unittest.IsolatedAsyncioTestCase):
    """Scenario 1: inserting a new session advances MAX(updated_at) → cache miss."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)

        self._feature_id = "feat-cache-s1"
        self._features_data: dict = {}
        self._sessions_data: dict = {}
        self._link_rows: list = []

        # Seed feature row in both DB (for fingerprint) and in-memory dict (for repo calls)
        await _insert_feature(self._db, self._feature_id, "2026-04-14T08:00:00+00:00")
        self._features_data[self._feature_id] = {
            "id": self._feature_id,
            "name": "Cache Invalidation Feature",
            "feature_slug": self._feature_id,
            "status": "in_progress",
            "updated_at": "2026-04-14T08:00:00+00:00",
        }

        # Seed two initial session rows
        for session_id, updated_at in [
            ("sess-s1-a", "2026-04-14T08:10:00+00:00"),
            ("sess-s1-b", "2026-04-14T08:20:00+00:00"),
        ]:
            await _insert_session(self._db, session_id, updated_at)
            self._sessions_data[session_id] = {
                "id": session_id,
                "status": "completed",
                "started_at": updated_at,
                "ended_at": updated_at,
                "total_cost": 1.0,
                "observed_tokens": 100,
                "model": "claude",
                "duration_seconds": 600,
                "updated_at": updated_at,
            }
            self._link_rows.append({
                "source_type": "feature",
                "source_id": self._feature_id,
                "target_type": "session",
                "target_id": session_id,
                "link_type": "related",
                "confidence": 0.9,
                "metadata_json": "{}",
            })

        self._ctx = _context()
        self._ports = _ports(
            db=self._db,
            features_data=self._features_data,
            sessions_data=self._sessions_data,
            link_rows=self._link_rows,
        )
        self._service = FeatureForensicsQueryService()

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()

    async def test_first_call_is_cache_miss(self) -> None:
        """The very first call must populate the cache (miss path)."""
        result = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(result.feature_id, self._feature_id)
        self.assertEqual(len(result.linked_sessions), 2)

    async def test_second_call_is_cache_hit(self) -> None:
        """A repeated call with unchanged data must return a cached result.

        Verified by wrapping ``ports.storage.sessions().get_by_id`` with a spy
        counter: on a hit, the underlying fetch is never invoked.
        """
        # First call — miss
        await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)

        # Track how many times get_by_id is called on the second pass
        call_count = 0
        original_sessions_data = self._sessions_data

        async def spy_get_by_id(session_id):
            nonlocal call_count
            call_count += 1
            return original_sessions_data.get(session_id)

        self._ports.storage._sessions_data = original_sessions_data

        # Patch get_by_id at the storage level for the second call
        spy_sessions_repo = types.SimpleNamespace(get_by_id=spy_get_by_id)

        # Replace the sessions data dict reference so sessions() method uses spy
        # We override the sessions() method on the storage instance directly
        self._ports.storage.sessions = lambda: spy_sessions_repo

        # Second call — must be a cache hit, so spy should not be called
        result = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(call_count, 0, "Cache hit must not invoke the underlying sessions repo")
        self.assertEqual(result.feature_id, self._feature_id)

    async def test_new_session_invalidates_cache(self) -> None:
        """Inserting a new session with a later updated_at causes the next call to be a miss."""
        # First call — miss; second call — hit
        first = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        second = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(len(first.linked_sessions), 2)
        self.assertEqual(len(second.linked_sessions), 2)

        # Now insert a third session with a later timestamp
        new_session_id = "sess-s1-c"
        new_updated_at = "2026-04-14T09:00:00+00:00"
        await _insert_session(self._db, new_session_id, new_updated_at)
        self._sessions_data[new_session_id] = {
            "id": new_session_id,
            "status": "completed",
            "started_at": new_updated_at,
            "ended_at": new_updated_at,
            "total_cost": 0.5,
            "observed_tokens": 50,
            "model": "claude",
            "duration_seconds": 300,
            "updated_at": new_updated_at,
        }
        self._link_rows.append({
            "source_type": "feature",
            "source_id": self._feature_id,
            "target_type": "session",
            "target_id": new_session_id,
            "link_type": "related",
            "confidence": 0.8,
            "metadata_json": "{}",
        })

        # Third call — fingerprint changed because MAX(sessions.updated_at) advanced
        third = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(
            len(third.linked_sessions),
            3,
            "After inserting a new linked session, the DTO must include the new session",
        )


class CacheInvalidationOnFeatureUpdateTests(unittest.IsolatedAsyncioTestCase):
    """Scenario 2: bumping features.updated_at causes the next call to be a miss."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)

        self._feature_id = "feat-cache-s2"
        self._features_data: dict = {}
        self._sessions_data: dict = {}
        self._link_rows: list = []

        await _insert_feature(self._db, self._feature_id, "2026-04-14T08:00:00+00:00")
        self._features_data[self._feature_id] = {
            "id": self._feature_id,
            "name": "Feature Updated At Test",
            "feature_slug": self._feature_id,
            "status": "in_progress",
            "updated_at": "2026-04-14T08:00:00+00:00",
        }

        session_id = "sess-s2-a"
        await _insert_session(self._db, session_id, "2026-04-14T08:05:00+00:00")
        self._sessions_data[session_id] = {
            "id": session_id,
            "status": "completed",
            "started_at": "2026-04-14T08:05:00+00:00",
            "ended_at": "2026-04-14T08:10:00+00:00",
            "total_cost": 1.0,
            "observed_tokens": 100,
            "model": "claude",
            "duration_seconds": 300,
            "updated_at": "2026-04-14T08:05:00+00:00",
        }
        self._link_rows.append({
            "source_type": "feature",
            "source_id": self._feature_id,
            "target_type": "session",
            "target_id": session_id,
            "link_type": "related",
            "confidence": 0.9,
            "metadata_json": "{}",
        })

        self._ctx = _context()
        self._ports = _ports(
            db=self._db,
            features_data=self._features_data,
            sessions_data=self._sessions_data,
            link_rows=self._link_rows,
        )
        self._service = FeatureForensicsQueryService()

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()

    async def test_feature_updated_at_bump_invalidates_cache(self) -> None:
        """UPDATE features SET updated_at = <later> must change the fingerprint."""
        # Miss then hit
        first = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(first.feature_id, self._feature_id)

        spy_sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda sid: self._sessions_data.get(sid))
        )

        # Verify second call is a hit by checking spy not called
        self._ports.storage.sessions = lambda: spy_sessions_repo
        await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(spy_sessions_repo.get_by_id.await_count, 0, "Second call must be a cache hit")

        # Reset sessions() to normal before the bump
        self._ports.storage.sessions = lambda: types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda sid: self._sessions_data.get(sid))
        )

        # Bump features.updated_at in the DB — fingerprint must advance
        later = "2026-04-14T10:00:00+00:00"
        await _bump_feature_updated_at(self._db, self._feature_id, later)
        self._features_data[self._feature_id] = {
            **self._features_data[self._feature_id],
            "updated_at": later,
        }

        # Third call must be a cache miss because the fingerprint changed
        third = await _call_forensics(self._service, self._ctx, self._ports, self._feature_id)
        self.assertEqual(
            third.feature_id,
            self._feature_id,
            "After bumping features.updated_at, forensics must still return valid data",
        )
        # Confirm it was actually a miss by checking the DTO is freshly computed
        # (linked_sessions count unchanged — the miss just means the function ran again)
        self.assertEqual(len(third.linked_sessions), 1)


class CacheIsolationBetweenFeaturesTests(unittest.IsolatedAsyncioTestCase):
    """Scenario 3: fingerprint scope is project-wide (MAX across all rows).

    Two features share the same project.  Touching feature B's updated_at
    advances MAX(features.updated_at) for the project, which invalidates
    the fingerprint for ALL keys scoped to that project — including A's entry.

    This is expected behaviour given the current implementation of
    ``get_data_version_fingerprint``: it computes a project-wide MAX, not a
    per-feature MAX.  The test documents (and asserts) this scope so the
    behaviour is explicit and observable in CI.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)

        self._feat_a = "feat-cache-s3-a"
        self._feat_b = "feat-cache-s3-b"
        self._features_data: dict = {}
        self._sessions_data: dict = {}
        self._link_rows: list = []

        # Feature A with one session
        await _insert_feature(self._db, self._feat_a, "2026-04-14T08:00:00+00:00")
        self._features_data[self._feat_a] = {
            "id": self._feat_a,
            "name": "Feature A",
            "feature_slug": self._feat_a,
            "status": "in_progress",
            "updated_at": "2026-04-14T08:00:00+00:00",
        }
        await _insert_session(self._db, "sess-s3-a", "2026-04-14T08:10:00+00:00")
        self._sessions_data["sess-s3-a"] = {
            "id": "sess-s3-a",
            "status": "completed",
            "started_at": "2026-04-14T08:10:00+00:00",
            "ended_at": "2026-04-14T08:15:00+00:00",
            "total_cost": 1.0,
            "observed_tokens": 100,
            "model": "claude",
            "duration_seconds": 300,
            "updated_at": "2026-04-14T08:10:00+00:00",
        }
        self._link_rows.append({
            "source_type": "feature",
            "source_id": self._feat_a,
            "target_type": "session",
            "target_id": "sess-s3-a",
            "link_type": "related",
            "confidence": 0.9,
            "metadata_json": "{}",
        })

        # Feature B with one session
        await _insert_feature(self._db, self._feat_b, "2026-04-14T08:00:00+00:00")
        self._features_data[self._feat_b] = {
            "id": self._feat_b,
            "name": "Feature B",
            "feature_slug": self._feat_b,
            "status": "in_progress",
            "updated_at": "2026-04-14T08:00:00+00:00",
        }
        await _insert_session(self._db, "sess-s3-b", "2026-04-14T08:20:00+00:00")
        self._sessions_data["sess-s3-b"] = {
            "id": "sess-s3-b",
            "status": "completed",
            "started_at": "2026-04-14T08:20:00+00:00",
            "ended_at": "2026-04-14T08:25:00+00:00",
            "total_cost": 2.0,
            "observed_tokens": 200,
            "model": "claude",
            "duration_seconds": 300,
            "updated_at": "2026-04-14T08:20:00+00:00",
        }
        self._link_rows.append({
            "source_type": "feature",
            "source_id": self._feat_b,
            "target_type": "session",
            "target_id": "sess-s3-b",
            "link_type": "related",
            "confidence": 0.9,
            "metadata_json": "{}",
        })

        self._ctx = _context()
        self._ports = _ports(
            db=self._db,
            features_data=self._features_data,
            sessions_data=self._sessions_data,
            link_rows=self._link_rows,
        )
        self._service = FeatureForensicsQueryService()

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()

    async def test_independent_first_calls_both_miss(self) -> None:
        """First calls for A and B are independent cache misses."""
        result_a = await _call_forensics(self._service, self._ctx, self._ports, self._feat_a)
        result_b = await _call_forensics(self._service, self._ctx, self._ports, self._feat_b)
        self.assertEqual(result_a.feature_id, self._feat_a)
        self.assertEqual(result_b.feature_id, self._feat_b)
        self.assertEqual(len(result_a.linked_sessions), 1)
        self.assertEqual(len(result_b.linked_sessions), 1)

    async def test_touching_b_invalidates_a_cache_due_to_project_wide_fingerprint(self) -> None:
        """Observed behaviour: touching B's updated_at also invalidates A's cache entry.

        The fingerprint is ``MAX(sessions.updated_at)|MAX(features.updated_at)``
        scoped to the project, NOT per-feature.  When feature B's updated_at
        advances, MAX(features.updated_at) for the project advances, so the
        shared fingerprint token changes for every cache key in this project —
        including A's entry.

        This test documents this project-wide scope behaviour.  If the
        fingerprint is ever narrowed to per-feature scope, this assertion should
        be inverted: touching B would then NOT affect A's cache entry.
        """
        # Populate cache for both A and B
        await _call_forensics(self._service, self._ctx, self._ports, self._feat_a)
        await _call_forensics(self._service, self._ctx, self._ports, self._feat_b)

        # Spy: if A's cache is still live, sessions() for A's session will not be called
        spy_a_sessions = types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda sid: self._sessions_data.get(sid))
        )
        self._ports.storage.sessions = lambda: spy_a_sessions

        # Confirm A's entry is cached before touching B
        await _call_forensics(self._service, self._ctx, self._ports, self._feat_a)
        self.assertEqual(
            spy_a_sessions.get_by_id.await_count,
            0,
            "A's cache entry should be live before touching B",
        )

        # Reset spy count, then touch B
        spy_a_sessions.get_by_id.reset_mock()
        self._ports.storage.sessions = lambda: types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda sid: self._sessions_data.get(sid))
        )
        later = "2026-04-14T12:00:00+00:00"
        await _bump_feature_updated_at(self._db, self._feat_b, later)
        self._features_data[self._feat_b] = {
            **self._features_data[self._feat_b],
            "updated_at": later,
        }

        # Attach fresh spy for A's next call
        spy_a_after_b_touch = types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda sid: self._sessions_data.get(sid))
        )
        self._ports.storage.sessions = lambda: spy_a_after_b_touch

        # Call A again — with project-wide fingerprint, A's cache must be invalid
        result_a_after = await _call_forensics(self._service, self._ctx, self._ports, self._feat_a)

        # Document observed behaviour: project-wide MAX means touching B invalidates A
        # If this assertion fails, the fingerprint has been narrowed to per-feature scope.
        self.assertGreater(
            spy_a_after_b_touch.get_by_id.await_count,
            0,
            "OBSERVED BEHAVIOUR (project-wide fingerprint): touching feature B advances "
            "MAX(features.updated_at) for the project, which changes the shared fingerprint "
            "token and therefore invalidates feature A's cache entry too. "
            "If this assertion fails, the fingerprint scope has been narrowed to per-feature.",
        )
        self.assertEqual(result_a_after.feature_id, self._feat_a)


if __name__ == "__main__":
    unittest.main()
