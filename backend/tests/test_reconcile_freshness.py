"""Phase 8 — Cross-Project Freshness Hardening (T8-005).

Covers AC 8.1–8.5:
  (a) a plan/doc added to a NON-ACTIVE project is reconciled within one
      reconcile interval (sync_project dispatched, no restart);
  (b) a crashed/dead watcher self-heals (re-bound) within one interval;
  (c) a project/dir added AFTER boot is picked up without restart;
  (d) REGRESSION (permanent fixture): non-active project writeback stays OFF.
Plus guard coverage: reconcile routes through the Phase 7 coalescing guard
(trigger="reconcile") and a malformed/empty project row never stalls the sweep.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_reconcile_freshness.py -v
"""
from __future__ import annotations

import asyncio
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_project(project_id: str, name: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=name or project_id)


def _make_path_bundle(root_path: Path) -> MagicMock:
    bundle = MagicMock()
    bundle.root = types.SimpleNamespace(path=root_path)
    bundle.as_tuple.return_value = (
        root_path / "sessions",
        root_path / "docs",
        root_path / "progress",
    )
    return bundle


def _make_binding(project_id: str, root: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        project=_make_project(project_id),
        paths=_make_path_bundle(root),
        source="explicit",
    )


def _make_sync_engine() -> MagicMock:
    engine = MagicMock()
    engine.sync_project = AsyncMock(return_value={"features_synced": 1})
    engine.sync_changed_files = AsyncMock()
    return engine


def _make_scheduler_capturing() -> tuple[MagicMock, list]:
    captured: list = []

    def _schedule_side_effect(coro, *, name=""):
        captured.append((name, coro))
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        fut.set_result(None)
        return fut

    sched = MagicMock()
    sched.schedule = MagicMock(side_effect=_schedule_side_effect)
    sched.__class__.__name__ = "InMemoryJobScheduler"
    return sched, captured


def _make_profile(sync: bool = True, watch: bool = True, jobs: bool = True) -> MagicMock:
    profile = MagicMock()
    profile.name = "local"
    profile.capabilities = types.SimpleNamespace(
        sync=sync, watch=watch, jobs=jobs, integrations=False
    )
    return profile


def _make_ports(workspace_registry: MagicMock, scheduler: MagicMock) -> MagicMock:
    ports = MagicMock()
    ports.workspace_registry = workspace_registry
    ports.job_scheduler = scheduler
    return ports


def _sleep_for_ticks(n_ticks: int):
    """Return an async fake for asyncio.sleep that allows *n_ticks* loop bodies
    to run, then raises CancelledError to exit the `while True` reconcile loop.
    """
    state = {"n": 0}

    async def _fake_sleep(_secs):
        state["n"] += 1
        if state["n"] > n_ticks:
            raise asyncio.CancelledError()
        return None

    return _fake_sleep


async def _drive_reconcile(adapter, captured, *, n_ticks: int = 1) -> None:
    coros = [c for n, c in captured if "reconcile" in n]
    assert coros, "expected a reconcile job to be scheduled"
    with patch("asyncio.sleep", new=_sleep_for_ticks(n_ticks)):
        for coro in coros:
            try:
                await coro
            except asyncio.CancelledError:
                pass


def _build_adapter(workspace_registry, sync_engine, *, active_id="proj-a", active_root="/tmp/proj_a"):
    from backend.adapters.jobs.runtime import RuntimeJobAdapter

    sched, captured = _make_scheduler_capturing()
    ports = _make_ports(workspace_registry, sched)
    adapter = RuntimeJobAdapter(
        profile=_make_profile(),
        ports=ports,
        sync_engine=sync_engine,
        project_binding=_make_binding(active_id, Path(active_root)),
    )
    return adapter, captured


def _writeback_for(sync_engine, project_id: str):
    """Return the allow_writeback kwarg used for *project_id* (None if not called)."""
    for c in sync_engine.sync_project.await_args_list:
        pid = str(c.args[0].id if hasattr(c.args[0], "id") else c.args[0])
        if pid == project_id:
            return c.kwargs.get("allow_writeback")
    return None


# ─────────────────────────────────────────────────────────────────────────────


class TestReconcileFreshness(unittest.IsolatedAsyncioTestCase):
    def _registry_two_projects(self):
        proj_a = _make_project("proj-a")
        proj_b = _make_project("proj-b")
        binding_a = _make_binding("proj-a", Path("/tmp/proj_a"))
        binding_b = _make_binding("proj-b", Path("/tmp/proj_b"))
        reg = MagicMock()
        reg.list_projects.return_value = [proj_a, proj_b]
        reg.reload_projects = MagicMock()

        def _resolve(pid=None, *, allow_active_fallback=True, refresh=False):
            return {"proj-a": binding_a, "proj-b": binding_b}.get(pid)

        reg.resolve_project_binding.side_effect = _resolve
        return reg

    async def test_non_active_project_reconciled_within_interval(self):
        """AC 8.2: a non-active project is freshness-swept within one interval."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            mock_reg.dead_project_ids.return_value = []
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=1)

        synced_ids = {
            str(c.args[0].id) for c in sync_engine.sync_project.await_args_list
        }
        self.assertIn("proj-b", synced_ids)  # non-active appeared
        self.assertIn("proj-a", synced_ids)  # active also reconciled
        # Phase 7 guard routing: every dispatch carries trigger="reconcile"
        for c in sync_engine.sync_project.await_args_list:
            self.assertEqual(c.kwargs.get("trigger"), "reconcile")

    async def test_non_active_writeback_stays_off_regression(self):
        """AC 8.5 (permanent regression fixture): non-active writeback is OFF,
        active stays ON."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            mock_reg.dead_project_ids.return_value = []
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=1)

        self.assertIs(_writeback_for(sync_engine, "proj-b"), False)  # NON-ACTIVE OFF
        self.assertIs(_writeback_for(sync_engine, "proj-a"), True)   # active ON

    async def test_malformed_project_row_skipped_sweep_continues(self):
        """AC 8.1: an empty/malformed project row is skipped; the sweep continues."""
        proj_a = _make_project("proj-a")
        proj_bad = _make_project("")  # empty id — malformed
        proj_b = _make_project("proj-b")
        binding_a = _make_binding("proj-a", Path("/tmp/proj_a"))
        binding_b = _make_binding("proj-b", Path("/tmp/proj_b"))
        reg = MagicMock()
        reg.list_projects.return_value = [proj_a, proj_bad, proj_b]
        reg.reload_projects = MagicMock()
        reg.resolve_project_binding.side_effect = lambda pid=None, **kw: {
            "proj-a": binding_a,
            "proj-b": binding_b,
        }.get(pid)

        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            mock_reg.dead_project_ids.return_value = []
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=1)

        synced_ids = {
            str(c.args[0].id) for c in sync_engine.sync_project.await_args_list
        }
        self.assertEqual(synced_ids, {"proj-a", "proj-b"})  # bad row skipped, others synced

    async def test_crashed_watcher_self_heals_within_interval(self):
        """AC 8.3: a dead watcher is re-bound within one reconcile interval."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            mock_reg.dead_project_ids.return_value = ["proj-b"]  # proj-b watcher crashed
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=1)

        healed_ids = {str(c.args[1]) for c in mock_reg.register.await_args_list}
        self.assertIn("proj-b", healed_ids)  # re-bound

    async def test_self_heal_disabled_skips_rebind(self):
        """Resilience: WATCHER_HEAL_ENABLED=False skips self-heal (no register)."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = False
            mock_reg.dead_project_ids.return_value = ["proj-b"]
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=1)

        mock_reg.register.assert_not_awaited()

    async def test_post_boot_project_picked_up_without_restart(self):
        """AC 8.4: a project added AFTER boot is picked up on the next tick via
        reload_projects() — no restart."""
        proj_a = _make_project("proj-a")
        proj_b = _make_project("proj-b")
        binding_a = _make_binding("proj-a", Path("/tmp/proj_a"))
        binding_b = _make_binding("proj-b", Path("/tmp/proj_b"))
        reg = MagicMock()
        # Tick 1: only proj-a exists. Tick 2 (after reload): proj-b added.
        reg.list_projects.side_effect = [[proj_a], [proj_a, proj_b]]
        reg.reload_projects = MagicMock()
        reg.resolve_project_binding.side_effect = lambda pid=None, **kw: {
            "proj-a": binding_a,
            "proj-b": binding_b,
        }.get(pid)

        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            mock_reg.dead_project_ids.return_value = []
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=2)

        # reload_projects invalidated the snapshot each tick (post-boot pickup)
        self.assertGreaterEqual(reg.reload_projects.call_count, 1)
        synced_ids = {
            str(c.args[0].id) for c in sync_engine.sync_project.await_args_list
        }
        self.assertIn("proj-b", synced_ids)  # post-boot project reconciled

    async def test_reconcile_disabled_when_interval_zero(self):
        """Resilience: RECONCILE_INTERVAL_SECONDS <= 0 disables the job."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, _ = _build_adapter(reg, sync_engine)

        with patch("backend.adapters.jobs.runtime.config") as cfg:
            cfg.RECONCILE_INTERVAL_SECONDS = 0
            cfg.WATCHER_HEAL_ENABLED = True
            self.assertIsNone(adapter._start_reconcile_task())


class TestDeadProjectIdsPredicate(unittest.IsolatedAsyncioTestCase):
    """AC 8.3 unit: the liveness predicate detects crashed + missing watchers."""

    def test_dead_project_ids_detects_crashed_and_missing(self):
        from backend.db.file_watcher import FileWatcherRegistry, _WatcherEntry

        reg = FileWatcherRegistry()
        # Simulate a crashed watcher: entry present but watcher.is_running False.
        crashed = types.SimpleNamespace(is_running=False)
        alive = types.SimpleNamespace(is_running=True)
        reg._entries["crashed"] = _WatcherEntry(
            watcher=crashed,
            sessions_dir=Path("/tmp/s"),
            docs_dir=Path("/tmp/d"),
            progress_dir=Path("/tmp/p"),
        )
        reg._entries["alive"] = _WatcherEntry(
            watcher=alive,
            sessions_dir=Path("/tmp/s"),
            docs_dir=Path("/tmp/d"),
            progress_dir=Path("/tmp/p"),
        )

        dead = reg.dead_project_ids(["crashed", "alive", "never-registered", ""])
        self.assertIn("crashed", dead)            # crashed watcher detected
        self.assertIn("never-registered", dead)   # expected-but-absent detected
        self.assertNotIn("alive", dead)            # running watcher not flagged
        self.assertNotIn("", dead)                 # empty id ignored


class TestWatcherProgressAwareLiveness(unittest.TestCase):
    """AC4: activity-without-progress is UNHEALTHY; legitimate idle is HEALTHY.

    Incident: the 2026-08-13..17 macOS relay watcher stayed ``_running=True``
    (is_running()-only liveness never flagged it) for ~44h while ticking with
    zero successful dispatches. ``watcher_is_inert`` is the pure predicate
    that closes that gap; ``dead_project_ids`` wires it into the existing
    self-heal path.
    """

    @staticmethod
    def _iso(moment: datetime) -> str:
        return moment.isoformat().replace("+00:00", "Z")

    def setUp(self) -> None:
        self.now = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)

    # -- pure predicate: watcher_is_inert -----------------------------------

    def test_watcher_is_inert_true_for_ticking_but_never_dispatching(self):
        """(a) REQUIRED: inert-but-alive IS flagged."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,  # never dispatched successfully
            "consecutiveTicksWithoutDispatch": 50,
        }
        self.assertTrue(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_true_when_last_dispatch_older_than_window(self):
        """(a) REQUIRED: same, but with a stale (not None) last dispatch."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=2000)),
            "consecutiveTicksWithoutDispatch": 12,
        }
        self.assertTrue(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_for_legitimately_idle_quiet_project(self):
        """(b) REQUIRED: no recent ticks at all -> never flagged."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": None,
            "lastChangeSyncAt": None,
            "consecutiveTicksWithoutDispatch": 0,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_when_tick_itself_is_stale(self):
        """A watcher with no RECENT ticks is not 'alive right now' either."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=3600)),
            "lastChangeSyncAt": None,
            "consecutiveTicksWithoutDispatch": 999,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_when_dispatching_successfully(self):
        """A watcher dispatching within the window is never flagged."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=10)),
            "consecutiveTicksWithoutDispatch": 0,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_for_freshly_registered_watcher(self):
        """A freshly-registered watcher with no lastTickAt yet is never flagged."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {"lastTickAt": None, "lastChangeSyncAt": None, "consecutiveTicksWithoutDispatch": 0}
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_below_min_inert_ticks(self):
        """Ticking + no dispatch, but below the configured tick-count floor."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,
            "consecutiveTicksWithoutDispatch": 3,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_never_raises_on_malformed_timestamp(self):
        """A malformed/absent timestamp reads as 'no progress signal', never
        as unhealthy, and never raises."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": "not-a-timestamp",
            "lastChangeSyncAt": "also-garbage",
            "consecutiveTicksWithoutDispatch": 999,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )
        self.assertFalse(
            watcher_is_inert(None, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    # -- integration: FileWatcherRegistry.dead_project_ids ------------------

    def test_dead_project_ids_flags_inert_alive_watcher_and_logs_warning(self):
        """(a) REQUIRED, wired end-to-end: dead_project_ids flags an
        inert-but-alive watcher and logs at WARNING naming the project."""
        from backend.db.file_watcher import FileWatcherRegistry, _WatcherEntry

        reg = FileWatcherRegistry()
        inert_snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,
            "consecutiveTicksWithoutDispatch": 50,
        }
        inert_watcher = types.SimpleNamespace(is_running=True, snapshot=lambda: inert_snapshot)
        reg._entries["inert-proj"] = _WatcherEntry(
            watcher=inert_watcher,
            sessions_dir=Path("/tmp/s"),
            docs_dir=Path("/tmp/d"),
            progress_dir=Path("/tmp/p"),
        )

        with self.assertLogs("ccdash.watcher", level="WARNING") as cm:
            dead = reg.dead_project_ids(["inert-proj"], now=self.now)

        self.assertIn("inert-proj", dead)
        self.assertTrue(any("inert-proj" in line and "INERT" in line for line in cm.output))

    def test_dead_project_ids_does_not_flag_legitimately_idle_watcher(self):
        """(b) REQUIRED, wired end-to-end: a running-but-quiet watcher (no
        ticks at all) must NOT be returned as dead."""
        from backend.db.file_watcher import FileWatcherRegistry, _WatcherEntry

        reg = FileWatcherRegistry()
        idle_snapshot = {
            "lastTickAt": None,
            "lastChangeSyncAt": None,
            "consecutiveTicksWithoutDispatch": 0,
        }
        idle_watcher = types.SimpleNamespace(is_running=True, snapshot=lambda: idle_snapshot)
        reg._entries["idle-proj"] = _WatcherEntry(
            watcher=idle_watcher,
            sessions_dir=Path("/tmp/s"),
            docs_dir=Path("/tmp/d"),
            progress_dir=Path("/tmp/p"),
        )

        dead = reg.dead_project_ids(["idle-proj"], now=self.now)
        self.assertNotIn("idle-proj", dead)

    def test_dead_project_ids_does_not_flag_watcher_missing_snapshot_method(self):
        """Defensive: a watcher stub with no ``snapshot`` callable (as used by
        the pre-existing crashed/missing test) must never raise and must not
        be flagged inert."""
        from backend.db.file_watcher import FileWatcherRegistry, _WatcherEntry

        reg = FileWatcherRegistry()
        bare_alive = types.SimpleNamespace(is_running=True)
        reg._entries["bare-alive"] = _WatcherEntry(
            watcher=bare_alive,
            sessions_dir=Path("/tmp/s"),
            docs_dir=Path("/tmp/d"),
            progress_dir=Path("/tmp/p"),
        )
        dead = reg.dead_project_ids(["bare-alive"], now=self.now)
        self.assertNotIn("bare-alive", dead)


if __name__ == "__main__":
    unittest.main()
