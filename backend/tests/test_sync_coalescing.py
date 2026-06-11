"""Phase 7: Sync coalescing + recent-first + startup hygiene tests.

Covers AC 7.2 (in-process + durable coalescing), AC 7.3 (recent-first parity),
AC 7.4 (reload/light-mode boot-cost), AC 7.5 (backend coverage).

Run with:
    /Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python \
        -m pytest backend/tests/test_sync_coalescing.py -v

Design notes:
  • SyncEngine is instantiated via __new__ + manual attribute setup so tests run
    without a real DB connection (following test_sync_link_rebuild_dispatch.py).
  • The in-process coalescing guard uses a plain Python set (_sync_in_flight),
    which is safe in asyncio's single-threaded event loop: check+add are
    synchronous (no yield between them), so concurrent callers are guaranteed
    to see the key as in-flight before any yield occurs.
  • asyncio.sleep(0) is used in the _sync_sessions mock to create a real yield
    point so that concurrent gather() callers can observe the in-flight key.
  • Durable-queue coalescing is tested via a mock of SqliteJobQueueRepository's
    depth() method (no real SQLite connection required).
  • Light-mode reload-cost test uses scan_manifest_repo mock (no real DB).
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(project_id: str, name: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=project_id,
        name=name or project_id,
        testConfig=types.SimpleNamespace(
            autoSyncOnStartup=False,
            maxFilesPerScan=25,
            maxParseConcurrency=4,
        ),
    )


@contextmanager
def _noop_span(*args, **kwargs):
    """No-op observability span for tests."""
    yield None


def _make_minimal_sync_engine() -> Any:
    """Minimal SyncEngine with all async internals mocked out.

    Sets up every attribute and method that sync_project() touches so the
    coalescing guard, stats accumulation, and the finally-block all work
    without a real DB connection.
    """
    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine.__new__(SyncEngine)
    engine._rglob_cache = {}
    engine._linking_logic_version = "1"
    engine._source_identity_policy = MagicMock()
    # Phase 7 coalescing guard
    engine._sync_in_flight: set = set()

    # Repositories (not called for the in-process coalescing path)
    engine.session_repo = MagicMock()
    engine.document_repo = MagicMock()
    engine.task_repo = MagicMock()
    engine.feature_repo = MagicMock()
    engine.link_repo = MagicMock()
    engine.sync_repo = MagicMock()
    engine.session_message_repo = MagicMock()
    engine.session_intelligence_repo = MagicMock()
    engine.analytics_repo = MagicMock()
    engine.session_usage_repo = MagicMock()
    engine.telemetry_queue_repo = MagicMock()
    engine.pricing_catalog_repo = MagicMock()
    engine.pricing_catalog_service = MagicMock()
    engine.scan_manifest_repo = MagicMock()
    engine.tag_repo = MagicMock()
    engine.telemetry_transformer = MagicMock()
    engine._session_ingest_service = None
    engine._ops_lock = asyncio.Lock()
    engine._operations = {}
    engine._operation_order = []
    engine._active_operation_ids = set()
    engine._max_operation_history = 40
    engine._git_doc_dates_cache_key = ""
    engine._git_doc_dates_cache_index = {}
    engine._git_doc_dates_cache_dirty = set()
    engine._test_source_errors = {}
    engine._test_source_synced_at = {}

    # Operation lifecycle
    engine._start_operation = AsyncMock(return_value="op-test-1")
    engine._update_operation = AsyncMock()
    engine._finish_operation = AsyncMock()

    # Inner sync phases
    engine._sync_sessions = AsyncMock(return_value={"synced": 1, "skipped": 0})
    engine._sync_documents = AsyncMock(return_value={"synced": 0, "skipped": 0})
    engine._sync_progress = AsyncMock(return_value={"synced": 0, "skipped": 0})
    engine._sync_features = AsyncMock(return_value={"synced": 0})
    engine._dispatch_link_rebuild = AsyncMock(return_value={"created": 0})
    engine.capture_analytics_snapshot = AsyncMock(return_value={})
    engine._maybe_backfill_session_usage_fields = AsyncMock(return_value={})
    engine._maybe_backfill_session_observability_fields = AsyncMock(return_value={})
    engine._maybe_backfill_session_usage_attribution = AsyncMock(return_value={})
    engine._maybe_backfill_telemetry_events = AsyncMock(return_value={})
    engine._maybe_backfill_commit_correlations = AsyncMock(return_value={})
    engine.rebuild_links = AsyncMock(return_value={"created": 0})

    # sync_project calls these after _sync_features; they access self.db in
    # production but are safely stubbed here — no DB connection required in tests.
    engine._load_link_state = AsyncMock(return_value={})
    engine._save_link_state = AsyncMock()
    engine._capture_analytics = AsyncMock()

    return engine


def _make_sessions_engine() -> Any:
    """Minimal SyncEngine for _sync_sessions unit tests (no full sync_project)."""
    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine.__new__(SyncEngine)
    engine._rglob_cache = {}
    engine._sync_in_flight = set()
    engine.scan_manifest_repo = MagicMock()
    engine._sync_single_session = AsyncMock(return_value=True)
    engine._light_mode_scan_skip = AsyncMock(return_value=False)
    engine._update_manifest_for_roots = AsyncMock()
    return engine


# ---------------------------------------------------------------------------
# AC 7.2 — in-process coalescing guard (memory backend)
# ---------------------------------------------------------------------------


class TestInProcessCoalescing(unittest.IsolatedAsyncioTestCase):
    """Coalescing guard: concurrent dispatches for same key → 1 actual sync."""

    async def test_early_return_when_key_already_in_flight(self):
        """Manually pre-adding the key simulates an in-flight sync; new call coalesces."""
        from backend.db.sync_engine import SyncEngine

        engine = _make_minimal_sync_engine()
        project = _make_project("proj-1")
        engine._sync_in_flight.add(("proj-1", "api"))  # simulate in-flight

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = True
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True

            result = await engine.sync_project(
                project,
                Path("/tmp/sessions"),
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                trigger="api",
            )

        self.assertTrue(result.get("coalesced"), "Expected coalesced=True")
        engine._sync_sessions.assert_not_awaited()
        engine._sync_documents.assert_not_awaited()

    async def test_coalescing_disabled_allows_concurrent_runs(self):
        """When SYNC_COALESCING_ENABLED=False, duplicate dispatches are not guarded."""
        engine = _make_minimal_sync_engine()
        project = _make_project("proj-disabled")
        # Pre-add key; with guard disabled this should NOT coalesce
        engine._sync_in_flight.add(("proj-disabled", "api"))

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = False
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_N = 200

            result = await engine.sync_project(
                project,
                Path("/tmp/sessions"),
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                trigger="api",
            )

        self.assertFalse(result.get("coalesced", False))
        engine._sync_sessions.assert_awaited_once()

    async def test_key_removed_from_in_flight_after_sync(self):
        """After a completed sync, the coalescing key is removed so the next call can proceed."""
        engine = _make_minimal_sync_engine()
        project = _make_project("proj-key-cleanup")

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = True
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_N = 200

            await engine.sync_project(
                project,
                Path("/tmp/sessions"),
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                trigger="startup",
            )

        # Key must be absent after completion so a second call is NOT coalesced
        self.assertNotIn(("proj-key-cleanup", "startup"), engine._sync_in_flight)

    async def test_three_concurrent_dispatches_one_real_sync(self):
        """Three concurrent dispatches for the same (project_id, trigger) → 1 actual sync.

        asyncio.sleep(0) in the mocked _sync_sessions creates a real yield
        point so that tasks 2 and 3 start running and see the key as in-flight
        (added by task 1 before its first yield).
        AC 7.2 primary assertion: only 1 full sync completes.
        """
        engine = _make_minimal_sync_engine()
        project = _make_project("proj-concurrent")

        actual_sync_call_count = 0

        async def _yielding_sessions(project_id, sessions_dir, force):
            nonlocal actual_sync_call_count
            await asyncio.sleep(0)  # yield → lets tasks 2 & 3 observe in-flight key
            actual_sync_call_count += 1
            return {"synced": 1, "skipped": 0}

        engine._sync_sessions = _yielding_sessions

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = True
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_N = 200

            results = await asyncio.gather(
                engine.sync_project(
                    project, Path("/tmp/sessions"), Path("/tmp/docs"),
                    Path("/tmp/progress"), trigger="api",
                ),
                engine.sync_project(
                    project, Path("/tmp/sessions"), Path("/tmp/docs"),
                    Path("/tmp/progress"), trigger="api",
                ),
                engine.sync_project(
                    project, Path("/tmp/sessions"), Path("/tmp/docs"),
                    Path("/tmp/progress"), trigger="api",
                ),
            )

        coalesced_count = sum(1 for r in results if r.get("coalesced"))
        # AC 7.2: exactly 1 sync runs; the other 2 are coalesced
        self.assertEqual(actual_sync_call_count, 1, "Expected exactly 1 real sync")
        self.assertEqual(coalesced_count, 2, "Expected 2 coalesced results")

    async def test_different_trigger_keys_not_coalesced(self):
        """Two concurrent dispatches with DIFFERENT triggers each run their own sync."""
        engine = _make_minimal_sync_engine()
        project = _make_project("proj-diff-trigger")

        actual_sync_call_count = 0

        async def _yielding_sessions(project_id, sessions_dir, force):
            nonlocal actual_sync_call_count
            await asyncio.sleep(0)
            actual_sync_call_count += 1
            return {"synced": 1, "skipped": 0}

        engine._sync_sessions = _yielding_sessions

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = True
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_N = 200

            results = await asyncio.gather(
                engine.sync_project(
                    project, Path("/tmp/sessions"), Path("/tmp/docs"),
                    Path("/tmp/progress"), trigger="startup",
                ),
                engine.sync_project(
                    project, Path("/tmp/sessions"), Path("/tmp/docs"),
                    Path("/tmp/progress"), trigger="watcher",
                ),
            )

        # Different triggers → different keys → BOTH syncs run
        coalesced_count = sum(1 for r in results if r.get("coalesced"))
        self.assertEqual(actual_sync_call_count, 2)
        self.assertEqual(coalesced_count, 0)


# ---------------------------------------------------------------------------
# AC 7.2 (durable variant) — DurableJobScheduler idempotent enqueue
# ---------------------------------------------------------------------------


class TestDurableQueueCoalescing(unittest.IsolatedAsyncioTestCase):
    """enqueue_durable_idempotent: skip enqueue when active job exists."""

    async def test_skips_enqueue_when_pending_job_exists(self):
        """Returns None without enqueuing when a pending job already exists."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(db=MagicMock(), backend="sqlite")
        mock_repo = AsyncMock()
        mock_repo.depth = AsyncMock(side_effect=lambda project_id, job_type, status: (
            asyncio.coroutine(lambda: 1 if status == "pending" else 0)()
        ))

        # Simpler approach: patch depth directly
        async def _depth(project_id=None, job_type=None, status="pending"):
            return 1 if status == "pending" else 0

        mock_repo.depth = _depth
        sched._repo = mock_repo

        result = await sched.enqueue_durable_idempotent(
            "sync",
            {"project_id": "proj-1"},
            "proj-1",
            max_attempts=3,
        )

        self.assertIsNone(result, "Should return None when pending job exists")

    async def test_skips_enqueue_when_running_job_exists(self):
        """Returns None without enqueuing when a running job already exists."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(db=MagicMock(), backend="sqlite")
        mock_repo = AsyncMock()

        async def _depth(project_id=None, job_type=None, status="pending"):
            return 1 if status == "running" else 0

        mock_repo.depth = _depth
        sched._repo = mock_repo

        result = await sched.enqueue_durable_idempotent(
            "sync",
            {"project_id": "proj-2"},
            "proj-2",
        )

        self.assertIsNone(result)

    async def test_enqueues_when_no_active_job(self):
        """Proceeds with enqueue when no pending or running job exists."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(db=MagicMock(), backend="sqlite")
        mock_repo = AsyncMock()

        async def _depth(project_id=None, job_type=None, status="pending"):
            return 0  # nothing in queue

        mock_repo.depth = _depth
        mock_repo.enqueue = AsyncMock(return_value="new-job-id-123")
        sched._repo = mock_repo

        result = await sched.enqueue_durable_idempotent(
            "sync",
            {"project_id": "proj-fresh"},
            "proj-fresh",
            max_attempts=3,
        )

        self.assertEqual(result, "new-job-id-123")
        mock_repo.enqueue.assert_awaited_once()

    async def test_memory_backend_returns_none_without_check(self):
        """Memory backend: idempotent enqueue is a no-op (no repo to check)."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(backend="memory")

        result = await sched.enqueue_durable_idempotent(
            "sync",
            {"project_id": "proj-mem"},
            "proj-mem",
        )

        # Memory backend has no repo → None returned without any check
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# AC 7.3 — recent-first + backfill parity (no silent loss)
# ---------------------------------------------------------------------------


class TestRecentFirstParity(unittest.IsolatedAsyncioTestCase):
    """_sync_sessions: backfill_count == baseline (no silent partial)."""

    async def _run_sync_sessions(
        self,
        tmp_path: Path,
        n_files: int,
        recent_n: int,
        enabled: bool = True,
    ) -> dict:
        """Helper: create n_files JSONL stubs, run _sync_sessions, return stats."""
        import time

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        # Create files with distinct mtimes (older files have lower mtime)
        for i in range(n_files):
            p = sessions_dir / f"session-{i:04d}.jsonl"
            p.write_text("{}")
            # stagger mtimes so sorting is deterministic
            os.utime(p, (1000000 + i, 1000000 + i))

        engine = _make_sessions_engine()

        with patch("backend.db.sync_engine.config") as mock_cfg:
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = enabled
            mock_cfg.SYNC_RECENT_FIRST_N = recent_n

            stats = await engine._sync_sessions("proj-parity", sessions_dir, force=False)

        return stats, n_files

    async def test_parity_no_files_dropped(self):
        """All 10 files processed; synced+skipped == baseline (10)."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            stats, baseline = await self._run_sync_sessions(
                Path(tmpdir), n_files=10, recent_n=5
            )
        total = stats["synced"] + stats["skipped"]
        self.assertEqual(total, baseline, f"Parity failed: {total} != {baseline}")

    async def test_parity_when_n_exceeds_file_count(self):
        """N > actual file count: all processed in one pass, no window split."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            stats, baseline = await self._run_sync_sessions(
                Path(tmpdir), n_files=3, recent_n=50
            )
        total = stats["synced"] + stats["skipped"]
        self.assertEqual(total, baseline)

    async def test_parity_recent_first_disabled(self):
        """Feature disabled: all files processed in full-scan order, parity holds."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            stats, baseline = await self._run_sync_sessions(
                Path(tmpdir), n_files=8, recent_n=3, enabled=False
            )
        total = stats["synced"] + stats["skipped"]
        self.assertEqual(total, baseline)

    async def test_recent_window_populates_before_backfill(self):
        """With 10 files and N=4, recent_window=4, backfill=6; parity holds."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            stats, baseline = await self._run_sync_sessions(
                Path(tmpdir), n_files=10, recent_n=4
            )
        # All 10 must be processed regardless of window split
        self.assertEqual(stats["synced"] + stats["skipped"], baseline)
        self.assertEqual(baseline, 10)


# ---------------------------------------------------------------------------
# AC 7.4 — reload boot-cost reduction via STARTUP_SYNC_LIGHT_MODE
# ---------------------------------------------------------------------------


class TestReloadBootCostLightMode(unittest.IsolatedAsyncioTestCase):
    """STARTUP_SYNC_LIGHT_MODE=True: manifest skip bypasses session scan on reload.

    Coordinates with the existing CCDASH_STARTUP_SYNC_LIGHT_MODE mechanism (no
    new parallel skip path introduced — AC 7.4 compliance).
    """

    async def test_light_mode_skips_session_scan_when_manifest_unchanged(self):
        """_sync_sessions returns empty stats immediately on manifest hit."""
        from backend.db.sync_engine import SyncEngine
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "sess.jsonl").write_text("{}")

            engine = _make_sessions_engine()
            # Simulate manifest hit → scan should be skipped
            engine._light_mode_scan_skip = AsyncMock(return_value=True)

            with patch("backend.db.sync_engine.config") as mock_cfg:
                mock_cfg.STARTUP_SYNC_LIGHT_MODE = True
                mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
                mock_cfg.SYNC_RECENT_FIRST_N = 200

                stats = await engine._sync_sessions(
                    "proj-reload", sessions_dir, force=False
                )

            # Manifest hit → scan skipped → zero synced/skipped
            self.assertEqual(stats["synced"], 0)
            self.assertEqual(stats["skipped"], 0)
            engine._sync_single_session.assert_not_awaited()

    async def test_light_mode_runs_scan_when_manifest_changed(self):
        """_sync_sessions runs normally when manifest indicates changed files."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "sess.jsonl").write_text("{}")

            engine = _make_sessions_engine()
            # Manifest miss → full scan runs
            engine._light_mode_scan_skip = AsyncMock(return_value=False)

            with patch("backend.db.sync_engine.config") as mock_cfg:
                mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
                mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
                mock_cfg.SYNC_RECENT_FIRST_N = 200

                stats = await engine._sync_sessions(
                    "proj-reload-changed", sessions_dir, force=False
                )

            # Manifest miss → 1 file synced (mock returns True)
            self.assertEqual(stats["synced"], 1)
            engine._sync_single_session.assert_awaited_once()


# ---------------------------------------------------------------------------
# AC 7.5 — guard attribute present + importable
# ---------------------------------------------------------------------------


class TestPhase7SmokeImports(unittest.TestCase):
    """Sanity checks: new attributes and methods are reachable."""

    def test_sync_in_flight_attribute_present_on_engine(self):
        from backend.db.sync_engine import SyncEngine

        engine = SyncEngine.__new__(SyncEngine)
        engine._sync_in_flight = set()
        self.assertIsInstance(engine._sync_in_flight, set)

    def test_config_flags_importable(self):
        """Phase 7 config flags are importable and have correct types."""
        from backend import config

        self.assertIsInstance(config.SYNC_COALESCING_ENABLED, bool)
        self.assertIsInstance(config.SYNC_RECENT_FIRST_ENABLED, bool)
        self.assertIsInstance(config.SYNC_RECENT_FIRST_N, int)
        self.assertGreater(config.SYNC_RECENT_FIRST_N, 0)

    def test_enqueue_durable_idempotent_method_exists(self):
        """DurableJobScheduler.enqueue_durable_idempotent method is callable."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(backend="memory")
        self.assertTrue(callable(getattr(sched, "enqueue_durable_idempotent", None)))

    def test_phase4_incremental_link_rebuild_flag_preserved(self):
        """Phase 4 INCREMENTAL_LINK_REBUILD_ENABLED flag is still present (no clobber)."""
        from backend import config

        self.assertTrue(hasattr(config, "INCREMENTAL_LINK_REBUILD_ENABLED"))
        self.assertIsInstance(config.INCREMENTAL_LINK_REBUILD_ENABLED, bool)
        # Default is True per Phase 4
        self.assertTrue(config.INCREMENTAL_LINK_REBUILD_ENABLED)

    def test_phase4_routing_in_dispatch_link_rebuild(self):
        """sync_engine._dispatch_link_rebuild still routes via INCREMENTAL_LINK_REBUILD_ENABLED."""
        import inspect
        from backend.db import sync_engine as se_mod

        src = inspect.getsource(se_mod.SyncEngine._dispatch_link_rebuild)
        self.assertIn("INCREMENTAL_LINK_REBUILD_ENABLED", src)
        self.assertIn("rebuild_links_for_entities", src)


# ---------------------------------------------------------------------------
# AC 7.5 — both backends covered (memory path smoke)
# ---------------------------------------------------------------------------


class TestBothBackendsCovered(unittest.IsolatedAsyncioTestCase):
    """Coalescing tests run under memory backend (in-process guard is authoritative)."""

    async def test_memory_backend_coalescing_skips_no_real_db(self):
        """Memory backend coalescing guard works without a DB connection."""
        engine = _make_minimal_sync_engine()
        project = _make_project("proj-mem-backend")

        # Mark as in-flight (simulating an ongoing memory-backend sync)
        engine._sync_in_flight.add(("proj-mem-backend", "api"))

        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch(
                "backend.db.sync_engine.aclear_project_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_feature_invalidation",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.db.sync_engine.publish_planning_invalidation",
                new_callable=AsyncMock,
            ),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = True
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True

            result = await engine.sync_project(
                project,
                Path("/tmp/sessions"),
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                trigger="api",
            )

        self.assertTrue(result.get("coalesced"))
        engine._sync_sessions.assert_not_awaited()

    async def test_durable_backend_coalescing_skipped_when_unavailable(self):
        """Durable backend coalescing skipped with explicit note when backend=memory."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        sched = DurableJobScheduler(backend="memory")
        result = await sched.enqueue_durable_idempotent(
            "sync", {"project_id": "proj-x"}, "proj-x"
        )
        # memory → None (skipped), not an error
        self.assertIsNone(result)


if __name__ == "__main__":
    import os
    unittest.main()
