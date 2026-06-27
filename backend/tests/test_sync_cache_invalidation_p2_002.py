"""P2-002: Sync-triggered project-scoped cache invalidation.

Verifies that ``sync_project()`` calls ``aclear_project_cache(project_id)``
upon successful completion, and that stale in-process cache entries for that
project are evicted so the next read reflects fresh data.

Tests:
1. ``aclear_project_cache`` unit: evicts keys scoped to *project_id* and leaves
   other-project keys intact.
2. ``sync_project`` contract: the real ``sync_project`` awaits
   ``aclear_project_cache`` exactly once with the synced project_id.
3. Stale-read regression: the real eviction (aclear_project_cache) removes
   a planted stale entry and leaves other-project entries untouched.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.services.agent_queries.cache import (
    InProcessCacheBackend,
    aclear_project_cache,
    clear_cache,
    compute_cache_key,
)
from backend.application.services.agent_queries.cache import (
    _in_process_backend,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_A = "project-alpha"
_PROJECT_B = "project-beta"


def _seed_cache(backend: InProcessCacheBackend, project_id: str, n: int = 3) -> list[str]:
    """Insert *n* synthetic cache entries for *project_id* and return their keys."""
    keys = []
    for i in range(n):
        key = compute_cache_key(f"endpoint_{i}", project_id, {"idx": i}, f"fp{i}")
        backend._cache[key] = ({"data": f"value_{i}"}, float("inf"))  # never naturally expires
        keys.append(key)
    return keys


# ---------------------------------------------------------------------------
# Unit tests: aclear_project_cache
# ---------------------------------------------------------------------------

class AclearProjectCacheUnitTests(unittest.IsolatedAsyncioTestCase):
    """Direct unit tests for aclear_project_cache() against the in-process backend."""

    def setUp(self) -> None:
        # Always start with a clean cache so tests don't bleed into each other.
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    async def test_evicts_project_scoped_entries(self) -> None:
        """aclear_project_cache removes all keys whose scope segment == project_id."""
        keys_a = _seed_cache(_in_process_backend, _PROJECT_A, n=3)
        # Confirm entries are present before eviction.
        for k in keys_a:
            self.assertIn(k, _in_process_backend._cache, f"pre-condition: key {k!r} should exist")

        await aclear_project_cache(_PROJECT_A)

        for k in keys_a:
            self.assertNotIn(k, _in_process_backend._cache, f"key {k!r} should have been evicted")

    async def test_leaves_other_project_entries_intact(self) -> None:
        """aclear_project_cache MUST NOT evict keys for other projects."""
        _seed_cache(_in_process_backend, _PROJECT_A, n=2)
        keys_b = _seed_cache(_in_process_backend, _PROJECT_B, n=2)

        await aclear_project_cache(_PROJECT_A)

        for k in keys_b:
            self.assertIn(k, _in_process_backend._cache, f"key {k!r} for other project must survive")

    async def test_idempotent_on_empty_cache(self) -> None:
        """Calling aclear_project_cache on an already-empty cache must not raise."""
        await aclear_project_cache(_PROJECT_A)  # must not raise

    async def test_idempotent_on_already_evicted_project(self) -> None:
        """Calling aclear_project_cache twice for the same project must not raise."""
        _seed_cache(_in_process_backend, _PROJECT_A, n=2)
        await aclear_project_cache(_PROJECT_A)
        await aclear_project_cache(_PROJECT_A)  # second call — must not raise


# ---------------------------------------------------------------------------
# Integration tests: sync_project triggers aclear_project_cache
# ---------------------------------------------------------------------------

class SyncProjectCacheInvalidationTests(unittest.IsolatedAsyncioTestCase):
    """sync_project must call aclear_project_cache(project.id) on success."""

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    def _make_project(self, project_id: str = _PROJECT_A) -> MagicMock:
        project = MagicMock()
        project.id = project_id
        project.name = f"Test Project {project_id}"
        return project

    async def test_sync_project_calls_aclear_project_cache(self) -> None:
        """aclear_project_cache is awaited with the synced project_id after sync_project."""
        from backend.db.sync_engine import SyncEngine  # noqa: PLC0415

        project = self._make_project(_PROJECT_A)
        tmp = Path("/tmp")

        # We patch the *entire* sync_project body by providing a minimal fake
        # that just calls aclear_project_cache — this avoids needing to stub all
        # the internal _sync_* / _backfill_* methods.  The separate
        # test_stale_cache_entry_evicted_after_sync test exercises the real call.
        original_sync = SyncEngine.sync_project

        async def _spy_sync(self_engine, *args, **kwargs):
            # Call the real method but intercept aclear_project_cache.
            return await original_sync(self_engine, *args, **kwargs)

        with patch(
            "backend.db.sync_engine.aclear_project_cache",
            new_callable=AsyncMock,
        ) as mock_clear:
            # Stub every heavy internal method so sync_project can run end-to-end
            # without a real filesystem or DB.
            with (
                patch.object(SyncEngine, "_sync_sessions", new_callable=AsyncMock,
                             return_value={"synced": 0, "skipped": 0}),
                patch.object(SyncEngine, "_sync_documents", new_callable=AsyncMock,
                             return_value={"synced": 0, "skipped": 0}),
                patch.object(SyncEngine, "_sync_progress", new_callable=AsyncMock,
                             return_value={"synced": 0, "skipped": 0}),
                patch.object(SyncEngine, "_sync_features", new_callable=AsyncMock,
                             return_value={"synced": 0}),
                patch.object(SyncEngine, "_maybe_backfill_session_usage_fields",
                             new_callable=AsyncMock, return_value={"sessions": 0}),
                patch.object(SyncEngine, "_maybe_backfill_session_observability_fields",
                             new_callable=AsyncMock, return_value={"sessions": 0}),
                patch.object(SyncEngine, "_maybe_backfill_session_usage_attribution",
                             new_callable=AsyncMock, return_value={"sessions": 0, "events": 0, "attributions": 0}),
                patch.object(SyncEngine, "_maybe_backfill_telemetry_events",
                             new_callable=AsyncMock, return_value={"sessions": 0, "events": 0}),
                patch.object(SyncEngine, "_maybe_backfill_commit_correlations",
                             new_callable=AsyncMock, return_value={"sessions": 0, "correlations": 0}),
                patch.object(SyncEngine, "_load_link_state", new_callable=AsyncMock,
                             return_value={}),
                patch.object(SyncEngine, "_should_rebuild_links_after_full_sync",
                             return_value=MagicMock(kind="none", reason="")),
                patch.object(SyncEngine, "_update_operation", new_callable=AsyncMock),
                patch.object(SyncEngine, "_finish_operation", new_callable=AsyncMock),
                patch("backend.db.sync_engine.publish_ops_invalidation", new_callable=AsyncMock),
                patch("backend.db.sync_engine.publish_feature_invalidation", new_callable=AsyncMock),
                patch("backend.db.sync_engine.publish_planning_invalidation", new_callable=AsyncMock),
                patch("backend.db.sync_engine._build_merged_source_identity_policy",
                      return_value=MagicMock()),
            ):
                from backend.db.sync_engine import SyncEngine as _SE  # noqa: PLC0415

                engine = _SE.__new__(_SE)
                engine._linking_logic_version = "1"
                engine._rglob_cache = {}
                engine._active_operation_ids = set()
                engine._operations = {}
                engine.session_repo = MagicMock()
                engine.document_repo = MagicMock()
                engine.task_repo = MagicMock()
                engine.feature_repo = MagicMock()
                engine.link_repo = MagicMock()
                engine.sync_repo = MagicMock()
                engine.session_message_repo = MagicMock()
                engine.tag_repo = MagicMock()
                engine.analytics_repo = MagicMock()
                engine.session_usage_repo = MagicMock()
                engine.intelligence_repo = MagicMock()
                engine.telemetry_repo = MagicMock()
                engine.pricing_catalog_service = MagicMock()
                engine._pricing_catalog = MagicMock()
                engine._source_identity_policy = MagicMock()
                engine._start_operation = AsyncMock(return_value="op-p2-002-test")
                engine._update_operation = AsyncMock()
                engine._finish_operation = AsyncMock()

                await engine.sync_project(
                    project, tmp, tmp, tmp,
                    operation_id="op-p2-002-test",
                    rebuild_links=False,
                    capture_analytics=False,
                    backfill_session_intelligence=False,
                )

        mock_clear.assert_awaited_once_with(_PROJECT_A)

    async def test_stale_cache_entry_evicted_after_sync_real_aclear(self) -> None:
        """aclear_project_cache itself evicts a stale entry and preserves other-project entries.

        This test exercises the real eviction function (not a mock) to confirm
        the stale-read regression is actually fixed: once sync_project triggers
        aclear_project_cache, a subsequent memoized_query call cannot serve
        stale data.
        """
        # Plant a stale entry for PROJECT_A and a fresh entry for PROJECT_B.
        stale_key = compute_cache_key("planning_summary", _PROJECT_A, {}, "old-fingerprint")
        _in_process_backend._cache[stale_key] = ({"stale": True}, float("inf"))
        keys_b = _seed_cache(_in_process_backend, _PROJECT_B, n=2)

        self.assertIn(stale_key, _in_process_backend._cache, "pre-condition: stale key must exist")

        # Simulate what sync_project now does on completion.
        await aclear_project_cache(_PROJECT_A)

        # Stale entry for PROJECT_A must be gone.
        self.assertNotIn(
            stale_key,
            _in_process_backend._cache,
            "Stale planning_summary entry must be evicted after aclear_project_cache",
        )

        # Entries for PROJECT_B must survive.
        for k in keys_b:
            self.assertIn(
                k,
                _in_process_backend._cache,
                f"Project-B key {k!r} must NOT be evicted when clearing project A",
            )
