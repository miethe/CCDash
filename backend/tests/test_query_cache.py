"""Tests for P2-001, P2-003, P2-004, P2-005, P2-006, P2-015 cache-core tasks.

Coverage:
- InProcessCacheBackend: get/set/delete/clear/clear_project
- PostgresCacheBackend: async get/set/clear_project (via aiosqlite as stand-in)
- Backend selection via CCDASH_QUERY_CACHE_BACKEND env var
- Fingerprint caching (P2-003): short-TTL in-process cache; project-scoped entity_links
- feature_phases MAX+COUNT marker (P2-004): does not include full row data
- Per-metric TTL overrides (P2-005): live_active_count and system_metrics use short TTLs
- clear_project_cache (P2-006): evicts project-scoped keys only
- InProcessCacheBackend maxsize 2048 (P2-015)
- clear_project_cache importable from package __init__
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from pydantic import BaseModel


class TestInProcessCacheBackend(unittest.TestCase):
    """P2-001 / P2-015: InProcessCacheBackend behaviour."""

    def _make(self, maxsize: int = 2048, ttl: int = 60):
        from backend.application.services.agent_queries.cache import InProcessCacheBackend
        return InProcessCacheBackend(maxsize=maxsize, ttl=ttl)

    def test_default_maxsize_is_2048(self):
        """P2-015: maxsize raised to 2048."""
        backend = self._make()
        self.assertEqual(backend._cache.maxsize, 2048)

    def test_set_and_get(self):
        backend = self._make(ttl=60)
        backend.set("k1", {"foo": "bar"}, ttl=60, project_id="proj-1")
        result = backend.get("k1")
        self.assertEqual(result, {"foo": "bar"})

    def test_get_missing_returns_none(self):
        backend = self._make()
        self.assertIsNone(backend.get("nonexistent"))

    def test_expired_entry_returns_none(self):
        backend = self._make(ttl=60)
        # Set with a TTL that has already expired
        backend.set("k1", "value", ttl=-1, project_id=None)
        result = backend.get("k1")
        self.assertIsNone(result)

    def test_delete(self):
        backend = self._make()
        backend.set("k1", "v1", ttl=60)
        backend.delete("k1")
        self.assertIsNone(backend.get("k1"))

    def test_delete_missing_is_noop(self):
        backend = self._make()
        backend.delete("no_such_key")  # should not raise

    def test_clear_removes_all(self):
        backend = self._make()
        backend.set("k1", "v1", ttl=60)
        backend.set("k2", "v2", ttl=60)
        backend.clear()
        self.assertIsNone(backend.get("k1"))
        self.assertIsNone(backend.get("k2"))

    def test_clear_project_removes_scoped_keys(self):
        """P2-006: clear_project evicts only keys whose scope matches."""
        backend = self._make()
        # Simulate key format: endpoint:scope:param_hash:fingerprint
        backend.set("ep1:proj-A:abc123:fp1", "result-A", ttl=60, project_id="proj-A")
        backend.set("ep1:proj-B:def456:fp2", "result-B", ttl=60, project_id="proj-B")
        backend.set("ep2:proj-A:ghi789:fp3", "result-A2", ttl=60, project_id="proj-A")

        backend.clear_project("proj-A")

        self.assertIsNone(backend.get("ep1:proj-A:abc123:fp1"))
        self.assertIsNone(backend.get("ep2:proj-A:ghi789:fp3"))
        self.assertEqual(backend.get("ep1:proj-B:def456:fp2"), "result-B")

    def test_clear_project_noop_for_unknown_project(self):
        backend = self._make()
        backend.set("ep1:proj-X:abc:fp", "val", ttl=60)
        backend.clear_project("proj-NONEXISTENT")  # should not raise
        self.assertEqual(backend.get("ep1:proj-X:abc:fp"), "val")


class TestKeyMatchesProject(unittest.TestCase):
    """Unit tests for _key_matches_project helper."""

    def test_matches(self):
        from backend.application.services.agent_queries.cache import _key_matches_project
        self.assertTrue(_key_matches_project("ep:proj-1:abc:fp", "proj-1"))

    def test_no_match(self):
        from backend.application.services.agent_queries.cache import _key_matches_project
        self.assertFalse(_key_matches_project("ep:proj-2:abc:fp", "proj-1"))

    def test_global_scope(self):
        from backend.application.services.agent_queries.cache import _key_matches_project
        self.assertFalse(_key_matches_project("ep:global:abc:fp", "proj-1"))

    def test_short_key(self):
        from backend.application.services.agent_queries.cache import _key_matches_project
        self.assertFalse(_key_matches_project("ep", "proj-1"))


class TestPostgresCacheBackendSqlite(unittest.IsolatedAsyncioTestCase):
    """P2-001: PostgresCacheBackend using aiosqlite as stand-in for asyncpg."""

    async def asyncSetUp(self):
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                expires_at TEXT NOT NULL
            )
        """)
        await self._db.commit()

    async def asyncTearDown(self):
        await self._db.close()

    def _make_backend(self):
        from backend.application.services.agent_queries.cache import PostgresCacheBackend
        return PostgresCacheBackend(db=self._db)

    async def test_aset_and_aget(self):
        backend = self._make_backend()
        await backend.aset("key1", {"data": 42}, ttl=3600, project_id="proj-1")
        result = await backend.aget("key1")
        self.assertEqual(result, {"data": 42})

    async def test_aget_missing_returns_none(self):
        backend = self._make_backend()
        result = await backend.aget("nonexistent")
        self.assertIsNone(result)

    async def test_aget_expired_returns_none(self):
        backend = self._make_backend()
        # Insert with already-expired timestamp
        import datetime
        expired = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)).isoformat()
        await self._db.execute(
            "INSERT INTO query_cache (key, value, project_id, expires_at) VALUES (?, ?, ?, ?)",
            ("expired_key", '"val"', "proj-1", expired),
        )
        await self._db.commit()
        result = await backend.aget("expired_key")
        self.assertIsNone(result)

    async def test_aset_upsert_updates_existing(self):
        backend = self._make_backend()
        await backend.aset("key1", "v1", ttl=3600)
        await backend.aset("key1", "v2", ttl=3600)
        result = await backend.aget("key1")
        self.assertEqual(result, "v2")

    async def test_adelete(self):
        backend = self._make_backend()
        await backend.aset("key1", "v1", ttl=3600)
        await backend.adelete("key1")
        self.assertIsNone(await backend.aget("key1"))

    async def test_aclear(self):
        backend = self._make_backend()
        await backend.aset("k1", "v1", ttl=3600, project_id="p1")
        await backend.aset("k2", "v2", ttl=3600, project_id="p2")
        await backend.aclear()
        self.assertIsNone(await backend.aget("k1"))
        self.assertIsNone(await backend.aget("k2"))

    async def test_aclear_project_scoped(self):
        """P2-006: aclear_project evicts only matching project_id rows."""
        backend = self._make_backend()
        await backend.aset("k1", "v1", ttl=3600, project_id="proj-A")
        await backend.aset("k2", "v2", ttl=3600, project_id="proj-B")
        await backend.aclear_project("proj-A")
        self.assertIsNone(await backend.aget("k1"))
        self.assertEqual(await backend.aget("k2"), "v2")

    # ------------------------------------------------------------------
    # Regression: aar-review-response-serialization-fix
    #
    # ``aset`` previously called ``json.dumps(value, default=str)`` with the
    # RAW cached value. When that value was a pydantic BaseModel (as every
    # memoized_query-decorated service method's result is), json.dumps has
    # no native encoder for it and falls back to ``default=str`` at the TOP
    # LEVEL -- stringifying the entire model into its repr, then encoding
    # THAT string as the "cached value". A later cache hit then handed a
    # plain string back in place of the model, which failed FastAPI's
    # response-model validation with a ResponseValidationError (500) at
    # the ClientV1Envelope[T] boundary. See GET /api/v1/project/aar-review.
    # ------------------------------------------------------------------

    async def test_aset_of_a_pydantic_model_does_not_corrupt_into_a_repr_string(self):
        from pydantic import BaseModel

        class _Nested(BaseModel):
            flag_id: str
            triggered: bool = False

        class _Sample(BaseModel):
            project_id: str = ""
            total: int = 0
            reviews: list[_Nested] = []

        backend = self._make_backend()
        model = _Sample(project_id="p1", total=1, reviews=[_Nested(flag_id="f1", triggered=True)])
        await backend.aset("k1", model, ttl=3600, project_id="p1")

        cached = await backend.aget("k1")

        # The historical defect: cached becomes a single opaque repr string
        # (e.g. "project_id='p1' total=1 reviews=[_Nested(...)]") instead of
        # a plain JSON-decodable dict mirroring the model's shape.
        self.assertIsInstance(
            cached, dict, f"expected a JSON dict, got corrupted value: {cached!r}"
        )
        self.assertEqual(cached["project_id"], "p1")
        self.assertEqual(cached["total"], 1)
        self.assertEqual(cached["reviews"], [{"flag_id": "f1", "triggered": True}])


class TestBackendSelection(unittest.TestCase):
    """P2-001: backend selection via CCDASH_QUERY_CACHE_BACKEND."""

    def test_default_is_in_process(self):
        """Default backend is in-process (memory)."""
        from backend.application.services.agent_queries import cache
        self.assertIsInstance(
            cache._active_backend,
            cache.InProcessCacheBackend,
        )

    def test_init_postgres_noop_when_memory_configured(self):
        """init_postgres_cache_backend is a no-op when backend=memory."""
        from backend.application.services.agent_queries.cache import (
            InProcessCacheBackend,
            _active_backend,
            init_postgres_cache_backend,
        )
        init_postgres_cache_backend(db=MagicMock())
        # Should remain InProcessCacheBackend (memory is the default)
        from backend.application.services.agent_queries import cache as _c
        self.assertIsInstance(_c._active_backend, InProcessCacheBackend)

    def test_get_cache_returns_ttl_cache(self):
        from backend.application.services.agent_queries.cache import get_cache
        from cachetools import TTLCache
        cache_obj = get_cache()
        self.assertIsInstance(cache_obj, TTLCache)


class TestFingerprintCache(unittest.IsolatedAsyncioTestCase):
    """P2-003: in-process fingerprint short-TTL cache."""

    def setUp(self):
        # Clear fingerprint cache before each test
        from backend.application.services.agent_queries import cache as c
        c._fingerprint_cache.clear()

    def tearDown(self):
        from backend.application.services.agent_queries import cache as c
        c._fingerprint_cache.clear()

    def test_set_and_get_fingerprint(self):
        from backend.application.services.agent_queries.cache import (
            _get_cached_fingerprint,
            _set_cached_fingerprint,
        )
        _set_cached_fingerprint("proj-1", "fp_abc123")
        result = _get_cached_fingerprint("proj-1")
        self.assertEqual(result, "fp_abc123")

    def test_fingerprint_cache_miss_returns_none(self):
        from backend.application.services.agent_queries.cache import _get_cached_fingerprint
        self.assertIsNone(_get_cached_fingerprint("proj-unknown"))

    def test_fingerprint_cache_expiry(self):
        """Expired fingerprint returns None."""
        from backend.application.services.agent_queries import cache as c
        # Manually insert an already-expired entry
        c._fingerprint_cache["proj-exp"] = ("fp_old", time.monotonic() - 1)
        result = c._get_cached_fingerprint("proj-exp")
        self.assertIsNone(result)
        # Should be removed from cache
        self.assertNotIn("proj-exp", c._fingerprint_cache)

    def test_fingerprint_cache_global_scope(self):
        """None project_id uses __global__ key."""
        from backend.application.services.agent_queries.cache import (
            _get_cached_fingerprint,
            _set_cached_fingerprint,
        )
        _set_cached_fingerprint(None, "fp_global")
        result = _get_cached_fingerprint(None)
        self.assertEqual(result, "fp_global")

    def test_clear_fingerprint_cache_for_project(self):
        from backend.application.services.agent_queries.cache import (
            _clear_fingerprint_cache_for_project,
            _get_cached_fingerprint,
            _set_cached_fingerprint,
        )
        _set_cached_fingerprint("proj-1", "fp1")
        _set_cached_fingerprint("proj-2", "fp2")
        _clear_fingerprint_cache_for_project("proj-1")
        self.assertIsNone(_get_cached_fingerprint("proj-1"))
        self.assertEqual(_get_cached_fingerprint("proj-2"), "fp2")


class TestFeaturePhasesMarker(unittest.IsolatedAsyncioTestCase):
    """P2-004: MAX+COUNT fingerprint for feature_phases."""

    async def asyncSetUp(self):
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        await self._db.execute("""
            CREATE TABLE feature_phases (
                id TEXT PRIMARY KEY,
                feature_id TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT '',
                status TEXT DEFAULT 'backlog',
                progress INTEGER DEFAULT 0,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        await self._db.commit()

    async def asyncTearDown(self):
        await self._db.close()

    async def test_empty_table_returns_zero_count(self):
        from backend.application.services.agent_queries.cache import _query_feature_phases_marker
        result = await _query_feature_phases_marker(self._db, "proj-1")
        self.assertTrue(result.startswith("0:"))

    async def test_returns_count_and_max_ts(self):
        """P2-004: marker is COUNT:MAX(updated_at), not GROUP_CONCAT."""
        from backend.application.services.agent_queries.cache import _query_feature_phases_marker

        await self._db.execute(
            "INSERT INTO features (id, project_id, updated_at) VALUES (?, ?, ?)",
            ("f1", "proj-1", "2026-01-01T00:00:00"),
        )
        await self._db.execute(
            "INSERT INTO feature_phases (id, feature_id, phase, updated_at) VALUES (?, ?, ?, ?)",
            ("fp1", "f1", "phase-1", "2026-01-15T12:00:00"),
        )
        await self._db.execute(
            "INSERT INTO feature_phases (id, feature_id, phase, updated_at) VALUES (?, ?, ?, ?)",
            ("fp2", "f1", "phase-2", "2026-02-01T00:00:00"),
        )
        await self._db.commit()

        result = await _query_feature_phases_marker(self._db, "proj-1")
        # Should be "2:2026-02-01T00:00:00" (count:max_ts)
        parts = result.split(":", 1)
        self.assertEqual(parts[0], "2")
        self.assertIn("2026-02-01", parts[1])

    async def test_project_scoped(self):
        """Only phases for the given project_id are counted."""
        from backend.application.services.agent_queries.cache import _query_feature_phases_marker

        await self._db.execute(
            "INSERT INTO features (id, project_id, updated_at) VALUES (?, ?, ?)",
            ("f1", "proj-1", "2026-01-01"),
        )
        await self._db.execute(
            "INSERT INTO features (id, project_id, updated_at) VALUES (?, ?, ?)",
            ("f2", "proj-2", "2026-01-01"),
        )
        await self._db.execute(
            "INSERT INTO feature_phases (id, feature_id, phase, updated_at) VALUES (?, ?, ?, ?)",
            ("fp1", "f1", "p1", "2026-01-01"),
        )
        await self._db.execute(
            "INSERT INTO feature_phases (id, feature_id, phase, updated_at) VALUES (?, ?, ?, ?)",
            ("fp2", "f2", "p1", "2026-01-01"),
        )
        await self._db.commit()

        r1 = await _query_feature_phases_marker(self._db, "proj-1")
        r2 = await _query_feature_phases_marker(self._db, "proj-2")
        self.assertTrue(r1.startswith("1:"))
        self.assertTrue(r2.startswith("1:"))

    async def test_unscoped_returns_all(self):
        from backend.application.services.agent_queries.cache import _query_feature_phases_marker

        await self._db.execute(
            "INSERT INTO features (id, project_id, updated_at) VALUES (?, ?, ?)",
            ("f1", "proj-1", "2026-01-01"),
        )
        await self._db.execute(
            "INSERT INTO features (id, project_id, updated_at) VALUES (?, ?, ?)",
            ("f2", "proj-2", "2026-01-01"),
        )
        for fid, pid in [("fp1", "f1"), ("fp2", "f1"), ("fp3", "f2")]:
            await self._db.execute(
                "INSERT INTO feature_phases (id, feature_id, phase, updated_at) VALUES (?, ?, ?, ?)",
                (fid, pid, "p1", "2026-01-01"),
            )
        await self._db.commit()

        result = await _query_feature_phases_marker(self._db, None)
        self.assertTrue(result.startswith("3:"))


class TestEntityLinksMarkerProjectScoped(unittest.IsolatedAsyncioTestCase):
    """P2-003: entity_links fingerprint scoped to project_id."""

    async def asyncSetUp(self):
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE entity_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT,
                source_id TEXT,
                target_type TEXT,
                target_id TEXT,
                link_type TEXT,
                created_at TEXT,
                project_id TEXT
            )
        """)
        await self._db.commit()

    async def asyncTearDown(self):
        await self._db.close()

    async def _insert_link(self, project_id: str, source_id: str) -> None:
        await self._db.execute(
            """INSERT INTO entity_links
               (source_type, source_id, target_type, target_id, link_type, created_at, project_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("session", source_id, "feature", "f1", "related", "2026-01-01", project_id),
        )
        await self._db.commit()

    async def test_different_projects_produce_different_fingerprints(self):
        from backend.application.services.agent_queries.cache import _query_entity_links_marker

        await self._insert_link("proj-A", "s1")
        await self._insert_link("proj-B", "s2")
        await self._insert_link("proj-B", "s3")

        fp_a = await _query_entity_links_marker(self._db, "proj-A")
        fp_b = await _query_entity_links_marker(self._db, "proj-B")
        self.assertNotEqual(fp_a, fp_b)

    async def test_proj_scoped_not_affected_by_other_project_change(self):
        """Adding a link to proj-B should not change proj-A's fingerprint."""
        from backend.application.services.agent_queries.cache import _query_entity_links_marker

        await self._insert_link("proj-A", "s1")
        fp_before = await _query_entity_links_marker(self._db, "proj-A")
        await self._insert_link("proj-B", "s2")
        fp_after = await _query_entity_links_marker(self._db, "proj-A")
        self.assertEqual(fp_before, fp_after)

    async def test_global_scope_includes_all(self):
        from backend.application.services.agent_queries.cache import _query_entity_links_marker

        await self._insert_link("proj-A", "s1")
        await self._insert_link("proj-B", "s2")
        result = await _query_entity_links_marker(self._db, None)
        count = int(result.split(":")[0])
        self.assertEqual(count, 2)


class TestPerMetricTTL(unittest.TestCase):
    """P2-005: per-metric TTL overrides respected by _resolve_ttl."""

    def test_live_active_count_uses_short_ttl(self):
        from backend.application.services.agent_queries.cache import _resolve_ttl
        with patch.dict(os.environ, {"CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS": "10"}):
            # Reload config binding
            import importlib
            from backend import config as cfg
            importlib.reload(cfg)
            # Directly check the config value
            from backend.application.services.agent_queries import cache as c
            # Re-bind the lambda to the fresh config
            c._PER_ENDPOINT_TTL["live_active_count"] = lambda: cfg.CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS
            result = c._resolve_ttl("live_active_count", None)
            self.assertEqual(result, cfg.CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS)

    def test_system_metrics_uses_short_ttl(self):
        from backend.application.services.agent_queries import cache as c
        from backend import config as cfg
        c._PER_ENDPOINT_TTL["system_metrics"] = lambda: cfg.CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS
        result = c._resolve_ttl("system_metrics", None)
        self.assertEqual(result, cfg.CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS)

    def test_explicit_ttl_overrides_per_endpoint_map(self):
        from backend.application.services.agent_queries.cache import _resolve_ttl
        result = _resolve_ttl("live_active_count", 999)
        self.assertEqual(result, 999)

    def test_unknown_endpoint_uses_global_ttl(self):
        from backend.application.services.agent_queries.cache import _resolve_ttl
        from backend import config as cfg
        result = _resolve_ttl("some_other_endpoint", None)
        self.assertEqual(result, cfg.CCDASH_QUERY_CACHE_TTL_SECONDS)

    def test_live_count_ttl_differs_from_global(self):
        """Ensure live_count TTL is distinct from (shorter than) global TTL."""
        from backend import config as cfg
        self.assertLess(cfg.CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS, cfg.CCDASH_QUERY_CACHE_TTL_SECONDS)

    def test_system_metrics_ttl_differs_from_global(self):
        from backend import config as cfg
        self.assertLess(cfg.CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS, cfg.CCDASH_QUERY_CACHE_TTL_SECONDS)


class TestClearProjectCache(unittest.TestCase):
    """P2-006: module-level clear_project_cache helper."""

    def setUp(self):
        from backend.application.services.agent_queries.cache import clear_cache
        clear_cache()

    def tearDown(self):
        from backend.application.services.agent_queries.cache import clear_cache
        clear_cache()

    def test_clear_project_cache_importable_from_package(self):
        """Wave 2 invalidation agent must be able to import this."""
        from backend.application.services.agent_queries import clear_project_cache
        self.assertTrue(callable(clear_project_cache))

    def test_clear_project_cache_evicts_correct_keys(self):
        from backend.application.services.agent_queries.cache import (
            _in_process_backend,
            clear_project_cache,
        )
        _in_process_backend.set("ep:proj-X:abc:fp", "val_x", ttl=60, project_id="proj-X")
        _in_process_backend.set("ep:proj-Y:def:fp", "val_y", ttl=60, project_id="proj-Y")

        clear_project_cache("proj-X")

        self.assertIsNone(_in_process_backend.get("ep:proj-X:abc:fp"))
        self.assertEqual(_in_process_backend.get("ep:proj-Y:def:fp"), "val_y")

    def test_clear_project_cache_global_clear_still_works(self):
        """clear_cache() still clears everything (backward compat)."""
        from backend.application.services.agent_queries.cache import (
            _in_process_backend,
            clear_cache,
        )
        _in_process_backend.set("ep:proj-Z:abc:fp", "val_z", ttl=60)
        clear_cache()
        self.assertIsNone(_in_process_backend.get("ep:proj-Z:abc:fp"))


class TestMemoizedQueryTTL(unittest.IsolatedAsyncioTestCase):
    """P2-005: memoized_query decorator honours per-endpoint TTL overrides."""

    async def test_explicit_ttl_stored_in_backend(self):
        """Decorator with explicit ttl=5 stores the entry (not testing actual expiry here)."""
        from backend.application.services.agent_queries.cache import (
            InProcessCacheBackend,
            memoized_query,
        )
        import backend.application.services.agent_queries.cache as c

        call_count = 0

        # Patch active backend to in-process
        original_backend = c._active_backend
        test_backend = InProcessCacheBackend(maxsize=128, ttl=60)
        c._active_backend = test_backend

        try:
            class FakeService:
                @memoized_query("test_endpoint", ttl=5)
                async def get_data(self, context, ports, *, project_id=None):
                    nonlocal call_count
                    call_count += 1
                    return {"count": call_count}

            ctx = MagicMock()
            ctx.project.project_id = "proj-T"
            ports = MagicMock()
            ports.storage.db = MagicMock()

            svc = FakeService()

            # Patch get_data_version_fingerprint to return a known value
            with patch.object(c, "get_data_version_fingerprint", new=AsyncMock(return_value="fp_test")):
                result1 = await svc.get_data(ctx, ports, project_id="proj-T")
                result2 = await svc.get_data(ctx, ports, project_id="proj-T")

            # Second call should hit cache
            self.assertEqual(call_count, 1)
            self.assertEqual(result1, result2)
        finally:
            c._active_backend = original_backend


class _RoundTripRow(BaseModel):
    """Sub-model standing in for one element of a DTO's list field."""

    flag_id: str
    triggered: bool = False


class _RoundTripDTO(BaseModel):
    """Module-level so ``typing.get_type_hints`` can resolve the annotation.

    ``memoized_query`` resolves the wrapped function's return type ONCE at
    decoration time via ``typing.get_type_hints(func)``.  Because this module
    uses ``from __future__ import annotations`` the raw annotation is a string,
    so the referenced type must live in the function's module globals -- a
    class defined inside a test method body would not resolve and the
    reconstruction path would silently degrade to "return raw JSON".  Mirrors
    the real ``AARReviewListDTO`` shape (scalar fields + a list of sub-models)
    without coupling these tests to the AAR domain.
    """

    project_id: str = ""
    total: int = 0
    reviews: list[_RoundTripRow] = []


class TestMemoizedQueryCacheHitReconstruction(unittest.IsolatedAsyncioTestCase):
    """Regression: aar-review-response-serialization-fix (cache-HIT half).

    ``test_aset_of_a_pydantic_model_does_not_corrupt_into_a_repr_string``
    (above) covers ``_json_safe`` on the WRITE side only -- it calls
    ``PostgresCacheBackend.aset``/``aget`` directly and therefore never
    reaches ``memoized_query``'s cache-HIT branch.  These tests drive the FULL
    decorator round trip over a JSON-serialising backend so that
    ``_reconstruct_from_cache`` (and the decoration-time return-type
    resolution it depends on) is genuinely exercised: without it a HIT hands
    the caller a bare ``dict`` where the ``response_model`` expects the
    declared pydantic model, producing the ``ResponseValidationError`` (500)
    seen on ``GET /api/v1/project/aar-review`` with the Postgres cache
    backend active.
    """

    async def asyncSetUp(self):
        from backend.application.services.agent_queries import cache as c
        from backend.application.services.agent_queries.cache import PostgresCacheBackend

        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                expires_at TEXT NOT NULL
            )
        """)
        await self._db.commit()

        # Activate the serialising backend: an in-process backend can never
        # reproduce this bug class because it stores the live Python object.
        self._cache_mod = c
        self._original_backend = c._active_backend
        c._active_backend = PostgresCacheBackend(db=self._db)

    async def asyncTearDown(self):
        self._cache_mod._active_backend = self._original_backend
        await self._db.close()

    async def _stored_rows(self) -> list[dict]:
        async with self._db.execute("SELECT key, value FROM query_cache") as cur:
            rows = await cur.fetchall()
        return [{"key": r[0], "value": r[1]} for r in rows]

    async def test_cache_hit_returns_the_declared_model_not_a_dict_or_str(self):
        """A HIT through the serialising backend must rehydrate into the model."""
        from backend.application.services.agent_queries import cache as c
        from backend.application.services.agent_queries.cache import memoized_query

        call_count = 0

        class FakeService:
            @memoized_query("rt_flat_endpoint")
            async def get_dto(self, context, ports, *, project_id=None) -> _RoundTripDTO:
                nonlocal call_count
                call_count += 1
                return _RoundTripDTO(project_id="proj-RT", total=call_count)

        ctx = MagicMock()
        ctx.project.project_id = "proj-RT"
        ports = MagicMock()
        ports.storage.db = MagicMock()
        svc = FakeService()

        with patch.object(c, "get_data_version_fingerprint", new=AsyncMock(return_value="fp_rt")):
            first = await svc.get_dto(ctx, ports, project_id="proj-RT")   # MISS -> stores
            second = await svc.get_dto(ctx, ports, project_id="proj-RT")  # HIT  -> rehydrates

        # The second call must not have re-entered the wrapped function.
        self.assertEqual(call_count, 1, "second call should have been served from cache")

        self.assertIsInstance(first, _RoundTripDTO)
        self.assertNotIsInstance(
            second, str,
            f"cache HIT degraded into an opaque string: {second!r}",
        )
        self.assertIsInstance(
            second, _RoundTripDTO,
            f"cache HIT returned {type(second).__name__} instead of _RoundTripDTO "
            f"-- FastAPI response_model validation would reject this: {second!r}",
        )
        self.assertEqual(second.project_id, "proj-RT")
        self.assertEqual(second.total, 1)

    async def test_cache_hit_preserves_nested_sub_model_list_integrity(self):
        """Nested list-of-models survives the JSON round trip as real sub-models."""
        from backend.application.services.agent_queries import cache as c
        from backend.application.services.agent_queries.cache import memoized_query

        call_count = 0

        class FakeService:
            @memoized_query("rt_nested_endpoint")
            async def get_dto(self, context, ports, *, project_id=None) -> _RoundTripDTO:
                nonlocal call_count
                call_count += 1
                return _RoundTripDTO(
                    project_id="proj-RT2",
                    total=2,
                    reviews=[
                        _RoundTripRow(flag_id="f1", triggered=True),
                        _RoundTripRow(flag_id="f2", triggered=False),
                    ],
                )

        ctx = MagicMock()
        ctx.project.project_id = "proj-RT2"
        ports = MagicMock()
        ports.storage.db = MagicMock()
        svc = FakeService()

        with patch.object(c, "get_data_version_fingerprint", new=AsyncMock(return_value="fp_rt2")):
            await svc.get_dto(ctx, ports, project_id="proj-RT2")          # MISS
            hit = await svc.get_dto(ctx, ports, project_id="proj-RT2")    # HIT

        self.assertEqual(call_count, 1)
        self.assertIsInstance(
            hit, _RoundTripDTO,
            f"cache HIT returned {type(hit).__name__}: {hit!r}",
        )
        self.assertEqual(len(hit.reviews), 2)
        for row in hit.reviews:
            self.assertIsInstance(
                row, _RoundTripRow,
                f"nested element did not rehydrate into _RoundTripRow: {row!r}",
            )
        self.assertEqual([r.flag_id for r in hit.reviews], ["f1", "f2"])
        self.assertEqual([r.triggered for r in hit.reviews], [True, False])

    async def test_stored_backend_value_is_json_native_not_a_repr_string(self):
        """Negative control: the WRITE half stores JSON, so the HIT half can rehydrate.

        Proves the two halves of the fix compose -- ``_json_safe`` puts a plain
        dict/list tree on the wire, and ``_reconstruct_from_cache`` turns that
        back into the declared model.  If the stored payload were the historical
        opaque repr string, no reconstruction would be possible at all.
        """
        from backend.application.services.agent_queries import cache as c
        from backend.application.services.agent_queries.cache import memoized_query

        class FakeService:
            @memoized_query("rt_negctl_endpoint")
            async def get_dto(self, context, ports, *, project_id=None) -> _RoundTripDTO:
                return _RoundTripDTO(
                    project_id="proj-RT3",
                    total=1,
                    reviews=[_RoundTripRow(flag_id="f9", triggered=True)],
                )

        ctx = MagicMock()
        ctx.project.project_id = "proj-RT3"
        ports = MagicMock()
        ports.storage.db = MagicMock()
        svc = FakeService()

        with patch.object(c, "get_data_version_fingerprint", new=AsyncMock(return_value="fp_rt3")):
            await svc.get_dto(ctx, ports, project_id="proj-RT3")

        rows = await self._stored_rows()
        self.assertEqual(len(rows), 1, f"expected exactly one cached row, got {rows!r}")
        decoded = json.loads(rows[0]["value"])
        self.assertIsInstance(
            decoded, dict,
            f"stored cache payload is not JSON-native: {rows[0]['value']!r}",
        )
        self.assertEqual(decoded["project_id"], "proj-RT3")
        self.assertEqual(decoded["reviews"], [{"flag_id": "f9", "triggered": True}])


class TestConfigNewVars(unittest.TestCase):
    """Verify new config variables are present with expected defaults."""

    def test_query_cache_backend_default(self):
        from backend import config
        self.assertEqual(config.CCDASH_QUERY_CACHE_BACKEND, "memory")

    def test_fingerprint_cache_ttl_default(self):
        from backend import config
        self.assertEqual(config.CCDASH_FINGERPRINT_CACHE_TTL_SECONDS, 5)


if __name__ == "__main__":
    unittest.main()
