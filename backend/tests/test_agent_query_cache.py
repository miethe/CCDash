"""Unit tests for backend.application.services.agent_queries.cache (CACHE-003).

Coverage:
- compute_cache_key determinism and collision resistance
- get_data_version_fingerprint graceful degradation on DB error
- clear_cache empties the TTLCache singleton
- get_cache returns the module-level instance
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.services.agent_queries.cache import (
    _query_cache,
    clear_cache,
    compute_cache_key,
    get_cache,
    get_data_version_fingerprint,
)


# ── compute_cache_key ───────────────────────────────────────────────────────

class ComputeCacheKeyDeterminismTests(unittest.TestCase):
    """compute_cache_key must be stable and collision-resistant."""

    def _key(
        self,
        endpoint: str = "project_status",
        project_id: str | None = "proj-1",
        params: dict | None = None,
        fingerprint: str | None = "fp-abc",
    ) -> str:
        return compute_cache_key(endpoint, project_id, params or {}, fingerprint)

    # ── determinism ──────────────────────────────────────────────────────

    def test_identical_inputs_produce_identical_key(self) -> None:
        key_a = self._key()
        key_b = self._key()
        self.assertEqual(key_a, key_b)

    def test_key_survives_param_key_ordering_difference(self) -> None:
        """Params dict with different key insertion order must hash identically."""
        key_a = compute_cache_key("ep", "p1", {"z": 1, "a": 2}, "fp")
        key_b = compute_cache_key("ep", "p1", {"a": 2, "z": 1}, "fp")
        self.assertEqual(key_a, key_b)

    # ── collision resistance ──────────────────────────────────────────────

    def test_different_params_produce_different_keys(self) -> None:
        key_a = self._key(params={"limit": 10})
        key_b = self._key(params={"limit": 20})
        self.assertNotEqual(key_a, key_b)

    def test_different_fingerprints_produce_different_keys(self) -> None:
        key_a = self._key(fingerprint="v1")
        key_b = self._key(fingerprint="v2")
        self.assertNotEqual(key_a, key_b)

    def test_different_endpoints_produce_different_keys(self) -> None:
        key_a = self._key(endpoint="project_status")
        key_b = self._key(endpoint="feature_forensics")
        self.assertNotEqual(key_a, key_b)

    def test_different_project_ids_produce_different_keys(self) -> None:
        key_a = self._key(project_id="proj-1")
        key_b = self._key(project_id="proj-2")
        self.assertNotEqual(key_a, key_b)

    # ── None / sentinel encoding ──────────────────────────────────────────

    def test_none_project_id_encodes_as_global(self) -> None:
        key = compute_cache_key("ep", None, {}, "fp")
        self.assertIn(":global:", key)

    def test_none_fingerprint_encodes_as_nofp(self) -> None:
        key = compute_cache_key("ep", "p1", {}, None)
        self.assertTrue(key.endswith(":nofp"), f"unexpected key: {key!r}")

    def test_none_fingerprint_differs_from_non_none(self) -> None:
        key_none = compute_cache_key("ep", "p1", {}, None)
        key_fp = compute_cache_key("ep", "p1", {}, "some-fp")
        self.assertNotEqual(key_none, key_fp)

    # ── format sanity ─────────────────────────────────────────────────────

    def test_key_has_four_colon_separated_segments(self) -> None:
        key = self._key()
        parts = key.split(":")
        self.assertEqual(len(parts), 4, f"expected 4 segments, got {len(parts)}: {key!r}")

    def test_param_hash_segment_is_16_hex_chars(self) -> None:
        key = self._key(params={"x": 1})
        param_hash = key.split(":")[2]
        self.assertEqual(len(param_hash), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in param_hash))


# ── get_data_version_fingerprint ────────────────────────────────────────────

class GetDataVersionFingerprintTests(unittest.IsolatedAsyncioTestCase):
    """get_data_version_fingerprint must degrade gracefully on failures."""

    def _make_ports(self, db: object) -> object:
        """Build a minimal CorePorts-like mock with a controllable db object."""
        storage = MagicMock()
        storage.db = db
        ports = MagicMock()
        ports.storage = storage
        return ports

    # ── happy path ────────────────────────────────────────────────────────

    async def test_returns_pipe_separated_fingerprint_on_success(self) -> None:
        """With a cooperative SQLite-style mock, fingerprint is non-None."""
        import aiosqlite

        # Build a cursor mock that returns a single-row result
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=("2026-04-14T10:00:00",))
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock(spec=aiosqlite.Connection)
        db.execute = MagicMock(return_value=cursor)

        context = MagicMock()
        ports = self._make_ports(db)

        result = await get_data_version_fingerprint(context, ports, project_id="proj-1")

        self.assertIsNotNone(result)
        self.assertIn("|", result)  # type: ignore[arg-type]

    # ── degradation: SQLite execute raises ───────────────────────────────

    async def test_returns_none_when_db_execute_raises(self) -> None:
        """Any exception from the DB layer must be swallowed and None returned."""
        import aiosqlite

        db = MagicMock(spec=aiosqlite.Connection)
        db.execute = MagicMock(side_effect=RuntimeError("disk I/O error"))

        context = MagicMock()
        ports = self._make_ports(db)

        result = await get_data_version_fingerprint(context, ports, project_id="proj-x")

        self.assertIsNone(result)

    # ── degradation: non-SQLite (asyncpg) fetchrow raises ────────────────

    async def test_returns_none_when_asyncpg_fetchrow_raises(self) -> None:
        """Postgres path failure must also degrade to None."""
        # db is not an aiosqlite.Connection instance, so asyncpg path is taken
        db = MagicMock()  # no spec — not aiosqlite.Connection
        db.fetchrow = AsyncMock(side_effect=ConnectionError("pg connection lost"))

        context = MagicMock()
        ports = self._make_ports(db)

        result = await get_data_version_fingerprint(context, ports, project_id=None)

        self.assertIsNone(result)

    # ── degradation: ports.storage.db attribute raises ───────────────────

    async def test_returns_none_when_storage_db_attribute_raises(self) -> None:
        """Attribute access failure on ports must be swallowed."""
        storage = MagicMock()
        type(storage).db = property(lambda self: (_ for _ in ()).throw(AttributeError("no db")))
        ports = MagicMock()
        ports.storage = storage

        context = MagicMock()
        result = await get_data_version_fingerprint(context, ports, project_id="proj-y")

        self.assertIsNone(result)


# ── Cache singleton helpers ─────────────────────────────────────────────────

class CacheModuleHelpersTests(unittest.TestCase):
    """clear_cache and get_cache operate on the shared singleton."""

    def setUp(self) -> None:
        # Ensure a clean state for each test in this class
        clear_cache()

    def test_get_cache_returns_module_singleton(self) -> None:
        self.assertIs(get_cache(), _query_cache)

    def test_clear_cache_empties_ttl_cache(self) -> None:
        _query_cache["sentinel-key"] = "some-value"
        self.assertIn("sentinel-key", _query_cache)
        clear_cache()
        self.assertNotIn("sentinel-key", _query_cache)

    def test_cache_stores_and_retrieves_values(self) -> None:
        key = compute_cache_key("ep", "p1", {"x": 1}, "fp1")
        _query_cache[key] = {"result": 42}
        self.assertEqual(_query_cache[key], {"result": 42})

    def tearDown(self) -> None:
        clear_cache()


if __name__ == "__main__":
    unittest.main()
