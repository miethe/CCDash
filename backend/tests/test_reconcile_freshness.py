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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {}
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {}
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {}
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {"proj-b": "not_running"}  # proj-b watcher crashed
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {"proj-b": "not_running"}
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {}
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

    def test_watcher_is_inert_true_for_ticking_with_repeated_failed_dispatches(self):
        """(a) REQUIRED: inert-but-alive IS flagged. NOTE: this fabricates 50
        FAILED dispatch attempts (consecutiveFailedDispatches=50) — that is
        "ticking and repeatedly failing to dispatch", NOT "never dispatching"
        (a dispatch was genuinely attempted every one of those 50 ticks; see
        ``test_watcher_is_inert_false_for_churn_only_never_dispatched_at_all``
        below for the actual never-attempted-a-dispatch shape, which must
        stay HEALTHY)."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,  # never dispatched successfully
            "consecutiveFailedDispatches": 50,
        }
        self.assertTrue(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_for_churn_only_never_dispatched_at_all(self):
        """The genuinely-never-dispatched (churn-only) shape at the pure
        predicate level: recent ticks, no successful dispatch ever, and
        ``consecutiveFailedDispatches == 0`` because no dispatch was ever
        even ATTEMPTED (every tick classified nothing). This must read
        HEALTHY — restarting a watcher whose classifier has nothing to
        classify would not fix anything. (Covered end-to-end via the real
        ``_watch_loop`` in
        ``TestWatcherExceptionPathIncrementsInertCounter.test_churn_only_ticks_never_trip_inert_no_matter_how_many_accumulate``;
        this is the direct plain-dict unit-test counterpart at the predicate
        level.)"""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,
            "lastSuccessfulDispatchAt": None,
            "consecutiveFailedDispatches": 0,
            "consecutiveTicksWithoutDispatch": 500,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_true_when_last_dispatch_older_than_window(self):
        """(a) REQUIRED: same, but with a stale (not None) last dispatch."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=2000)),
            "consecutiveFailedDispatches": 12,
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
            "consecutiveFailedDispatches": 0,
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
            "consecutiveFailedDispatches": 999,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_when_dispatching_successfully(self):
        """A watcher with a FRESH successful dispatch is never flagged — even
        with a failure counter ABOVE min_inert_ticks. The counter is set
        above threshold deliberately: this test must only be able to pass
        via the ``has_recent_successful_dispatch`` short-circuit inside
        ``watcher_is_inert``, not because the counter happens to be 0 (the
        prior version of this test was vacuous — it never actually supplied
        a successful-dispatch timestamp, so it passed via the below-threshold
        branch instead of the success short-circuit it is named for)."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=10)),
            "lastSuccessfulDispatchAt": self._iso(self.now - timedelta(seconds=10)),
            "consecutiveFailedDispatches": 50,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_for_freshly_registered_watcher(self):
        """A freshly-registered watcher with no lastTickAt yet is never flagged."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {"lastTickAt": None, "lastChangeSyncAt": None, "consecutiveFailedDispatches": 0}
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_below_min_inert_ticks(self):
        """Ticking + no dispatch, but below the configured tick-count floor."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": None,
            "consecutiveFailedDispatches": 3,
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
            "consecutiveFailedDispatches": 999,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )
        self.assertFalse(
            watcher_is_inert(None, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    # -- DEFECT 1 regression: attempted-at (lastChangeSyncAt) must never be
    #    mistaken for succeeded-at. -----------------------------------------

    def test_watcher_is_inert_true_when_every_recent_dispatch_is_failing(self):
        """REGRESSION for the independently-confirmed DEFECT 1: a watcher that
        is ticking, classifying changes, and dispatching — but EVERY recent
        dispatch FAILS/times out — must still be judged INERT. The OLD logic
        (reading ``lastChangeSyncAt`` alone as "dispatched inside the window
        -> progressing") would have rescued this snapshot even though nothing
        ever actually synced; this is exactly the 2026-08-13 storm shape (128
        continuously-failing dispatches, refreshed every <=120s, all inside
        the 900s window)."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            # Recent attempted-at — written on the FAILURE branch too. A
            # recent value here must NOT count as progress.
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=10)),
            "lastSyncStatus": "failed",
            "lastSuccessfulDispatchAt": None,
            "consecutiveFailedDispatches": 12,
        }
        self.assertTrue(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_with_recent_successful_dispatch_at(self):
        """A recent ``lastSuccessfulDispatchAt`` IS real progress -> not inert,
        even if ``lastSyncStatus``/``lastChangeSyncAt`` look mixed (e.g. a
        later failed tick after an earlier success within the window)."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=5)),
            "lastSyncStatus": "failed",
            "lastSuccessfulDispatchAt": self._iso(self.now - timedelta(seconds=30)),
            "consecutiveFailedDispatches": 1,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
        )

    def test_watcher_is_inert_false_legacy_snapshot_fallback_on_succeeded_status(self):
        """Backward-compat fallback: a snapshot from BEFORE
        ``lastSuccessfulDispatchAt`` existed (no such key at all) with a
        recent ``lastChangeSyncAt`` AND ``lastSyncStatus == "succeeded"`` must
        still read as progressing — the fallback path is legitimate only when
        status is genuinely "succeeded"."""
        from backend.db.file_watcher import watcher_is_inert

        snapshot = {
            "lastTickAt": self._iso(self.now - timedelta(seconds=5)),
            "lastChangeSyncAt": self._iso(self.now - timedelta(seconds=10)),
            "lastSyncStatus": "succeeded",
            # No "lastSuccessfulDispatchAt" key at all — legacy snapshot shape.
            "consecutiveFailedDispatches": 0,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=self.now, stale_seconds=900, min_inert_ticks=10)
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
            "consecutiveFailedDispatches": 50,
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
            "consecutiveFailedDispatches": 0,
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


class TestWatcherExceptionPathIncrementsInertCounter(unittest.IsolatedAsyncioTestCase):
    """Closes the gap left after DEFECT 1: a dispatch that RAISES (not just
    times out) must also count toward ``consecutive_failed_dispatches``, or
    ``watcher_is_inert`` stays blind to a watcher that is failing every single
    tick.

    This drives the real ``FileWatcher._watch_loop`` end to end (scripted
    ``awatch`` + a ``sync_changed_files`` that raises on every tick) rather
    than a hand-built snapshot dict, so it proves the counter is actually
    wired to the exception branch — not merely that ``watcher_is_inert``'s
    predicate logic is correct in isolation (that is already covered by
    ``test_watcher_is_inert_true_when_every_recent_dispatch_is_failing``
    above, using a snapshot nothing in the loop produced).

    Incident shape: the 2026-08-13 storm logged 128 "File watcher change sync
    failed" lines — i.e. EXCEPTIONS from a broken connection pool, not
    timeouts. Before this fix, ``consecutive_failed_dispatches`` never moved
    off 0 on that path, so ``watcher_is_inert`` never tripped despite every
    dispatch failing for hours.

    Note the FAILURE-driven counter is the one this test asserts on
    (``consecutiveFailedDispatches``), NOT ``consecutiveTicksWithoutDispatch``
    — every tick here has classified changes and a genuinely attempted
    dispatch, so the weak "nothing to classify" counter must stay at 0
    throughout; see the churn-vs-failure split documented on
    ``FileWatcherSnapshot``.
    """

    async def asyncSetUp(self) -> None:
        import tempfile

        from watchfiles import Change

        from backend.db import file_watcher as file_watcher_module
        from backend.db.file_watcher import FileWatcher
        from backend.tests.test_file_watcher import _ScriptedAwatch

        self._Change = Change
        self._file_watcher_module = file_watcher_module
        self._FileWatcher = FileWatcher
        self._ScriptedAwatch = _ScriptedAwatch

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.sessions_dir = root / "sessions"
        self.docs_dir = root / "docs"
        self.progress_dir = root / "progress"
        for directory in (self.sessions_dir, self.docs_dir, self.progress_dir):
            directory.mkdir()

        self._orig_awatch = file_watcher_module.awatch

    async def asyncTearDown(self) -> None:
        self._file_watcher_module.awatch = self._orig_awatch
        self._tmp.cleanup()

    async def test_dispatch_exception_on_every_tick_increments_counter_and_trips_inert(self) -> None:
        from backend.db.file_watcher import watcher_is_inert

        n_ticks = 4
        ticks = [
            {(self._Change.modified, str(self.sessions_dir / f"change-{i}.jsonl"))}
            for i in range(n_ticks)
        ]
        scripted = self._ScriptedAwatch(ticks)
        self._file_watcher_module.awatch = scripted

        async def _always_raises(project_id, classified, *args, **kwargs):
            raise RuntimeError("connection pool exhausted")

        sync_engine = types.SimpleNamespace(sync_changed_files=_always_raises)

        watcher = self._FileWatcher()
        watcher._running = True
        with self.assertLogs("ccdash.watcher", level="ERROR"):
            await watcher._watch_loop(
                sync_engine,
                "proj-exception-storm",
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
                [self.sessions_dir],
            )

        snapshot = watcher.snapshot()

        # Every tick produced classified changes (the dispatch was genuinely
        # attempted) and every dispatch raised, so BEFORE this fix the
        # counter would have stayed 0 the whole time.
        self.assertEqual(snapshot["lastTickClassifiedChangeCount"], 1)
        self.assertEqual(snapshot["lastSyncStatus"], "failed")
        self.assertIsNone(snapshot["lastSuccessfulDispatchAt"])
        self.assertEqual(snapshot["consecutiveFailedDispatches"], n_ticks)
        # The weak "nothing classified" counter must stay untouched — every
        # tick here HAD classified work; it just failed to dispatch.
        self.assertEqual(snapshot["consecutiveTicksWithoutDispatch"], 0)

        # And the watchdog can now actually see it: age lastSuccessfulDispatchAt
        # (here, absent entirely) past the freshness window and confirm
        # watcher_is_inert trips on this exact snapshot shape.
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        aged_snapshot = dict(snapshot)
        aged_snapshot["lastTickAt"] = (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
        self.assertTrue(
            watcher_is_inert(aged_snapshot, now=now, stale_seconds=900, min_inert_ticks=3)
        )

    async def test_churn_only_ticks_never_trip_inert_no_matter_how_many_accumulate(self) -> None:
        """Regression guard for this whole change: a project whose watched
        dirs churn ONLY in files ``_classify_changes`` drops (editor swap
        files, ``.DS_Store``, ``__pycache__/*.pyc``, rotating ``.log``/
        ``.tmp``) ticks forever, classifies nothing, and — before this split
        — tripped the inert verdict via ``consecutive_ticks_without_dispatch``
        despite the watcher being perfectly healthy. That counter is still
        allowed to advance (it is health-visible-only, and
        ``test_empty_classification_tick_advances_progress_fields_only`` in
        test_file_watcher.py legitimately asserts it does); the load-bearing
        assertion here is that ``watcher_is_inert`` never trips on it, even
        run well past ``min_inert_ticks``.
        """
        from backend.db.file_watcher import watcher_is_inert

        n_ticks = 20
        junk_names = [".DS_Store", "foo.pyc", "scratch.session.jsonl.swp", "note.tmp"]
        ticks = [
            {(self._Change.modified, str(self.sessions_dir / junk_names[i % len(junk_names)]))}
            for i in range(n_ticks)
        ]
        scripted = self._ScriptedAwatch(ticks)
        self._file_watcher_module.awatch = scripted

        dispatch_calls: list[object] = []

        async def _record(project_id, classified, *args, **kwargs):
            dispatch_calls.append(classified)

        sync_engine = types.SimpleNamespace(sync_changed_files=_record)

        watcher = self._FileWatcher()
        watcher._running = True
        await watcher._watch_loop(
            sync_engine,
            "proj-churn-only",
            self.sessions_dir,
            self.docs_dir,
            self.progress_dir,
            [self.sessions_dir],
        )

        snapshot = watcher.snapshot()

        self.assertEqual(dispatch_calls, [], "junk-only ticks must never dispatch")
        self.assertEqual(snapshot["consecutiveTicksWithoutDispatch"], n_ticks)
        self.assertEqual(snapshot["consecutiveFailedDispatches"], 0)

        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        aged_snapshot = dict(snapshot)
        aged_snapshot["lastTickAt"] = (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
        # Well past min_inert_ticks (n_ticks=20 >> 3) on the OLD counter —
        # if the predicate still read consecutiveTicksWithoutDispatch this
        # would incorrectly trip.
        self.assertFalse(
            watcher_is_inert(aged_snapshot, now=now, stale_seconds=900, min_inert_ticks=3)
        )


class TestWatcherIsInertFailSafeOnMissingFailureCounter(unittest.TestCase):
    """``watcher_is_inert`` must fail SAFE (never inert) on a snapshot that
    cannot distinguish churn from failure — i.e. one lacking
    ``consecutiveFailedDispatches`` entirely (an older/partial snapshot
    shape). Falling back to ``consecutiveTicksWithoutDispatch`` here would
    resurrect the exact false-positive-on-churn defect this split exists to
    close, so the fallback must NOT exist.
    """

    def test_missing_failure_counter_is_never_treated_as_inert(self) -> None:
        from backend.db.file_watcher import watcher_is_inert

        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        snapshot = {
            "lastTickAt": (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
            "lastChangeSyncAt": None,
            "lastSuccessfulDispatchAt": None,
            # No "consecutiveFailedDispatches" key at all.
            "consecutiveTicksWithoutDispatch": 999,
        }
        self.assertFalse(
            watcher_is_inert(snapshot, now=now, stale_seconds=900, min_inert_ticks=1)
        )


def _sleep_and_monotonic_for_ticks(n_ticks: int, times: list[float]):
    """Like ``_sleep_for_ticks``, but pairs it with a ``time.monotonic`` fake
    that returns a FIXED value per tick (regardless of how many times
    ``time.monotonic()`` is called within that tick's body — e.g. once for
    ``_mark_job_started``/``_mark_job_completed`` bookkeeping, once for the
    self-heal cooldown check). ``times[i]`` is the wall-clock value used
    during tick ``i + 1``. State is shared between the two fakes so they
    always agree on "which tick are we in".
    """
    state = {"n": 0}

    async def _fake_sleep(_secs):
        state["n"] += 1
        if state["n"] > n_ticks:
            raise asyncio.CancelledError()
        return None

    def _fake_monotonic() -> float:
        idx = max(0, state["n"] - 1)
        return times[idx] if idx < len(times) else times[-1]

    return _fake_sleep, _fake_monotonic


class TestWatcherSelfHealCooldown(unittest.IsolatedAsyncioTestCase):
    """DEFECT 2 regression: the restart-thrash cooldown applies ONLY to the
    "inert" self-heal reason, never to "not_running" (crashed/missing)."""

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

    async def test_inert_watcher_restart_cooldown_suppresses_immediate_reregister(self):
        """(4) REQUIRED: an INERT project restarted once is NOT re-registered
        on the immediately following tick (cooldown active), and IS eligible
        again once the cooldown has elapsed — no sleeps, time is injected."""
        reg = self._registry_two_projects()
        sync_engine = _make_sync_engine()
        adapter, captured = _build_adapter(reg, sync_engine)

        # tick1 @ t=1000 (restart) -> tick2 @ t=1010 (10s later, within the
        # 900s cooldown -> suppressed) -> tick3 @ t=1950 (950s later, past
        # the cooldown -> eligible again).
        times = [1_000.0, 1_010.0, 1_950.0]
        fake_sleep, fake_monotonic = _sleep_and_monotonic_for_ticks(3, times)

        with (
            patch("backend.adapters.jobs.runtime.config") as cfg,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
            patch("asyncio.sleep", new=fake_sleep),
            patch("time.monotonic", new=fake_monotonic),
        ):
            cfg.RECONCILE_INTERVAL_SECONDS = 300
            cfg.WATCHER_HEAL_ENABLED = True
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {"proj-b": "inert"}
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()

            coros = [c for n, c in captured if "reconcile" in n]
            assert coros, "expected a reconcile job to be scheduled"
            with self.assertLogs("ccdash.runtime.jobs", level="INFO") as cm:
                for coro in coros:
                    try:
                        await coro
                    except asyncio.CancelledError:
                        pass

        # tick1 restarts (count=1), tick2 suppressed (still count=1), tick3
        # restarts again once the cooldown has elapsed (count=2).
        self.assertEqual(mock_reg.register.await_count, 2)
        suppressed_lines = [
            line for line in cm.output if "proj-b" in line and "cooldown" in line.lower()
        ]
        self.assertTrue(
            suppressed_lines,
            "expected an INFO log naming project 'proj-b' and the cooldown suppression",
        )

    async def test_cooldown_does_not_apply_to_crashed_or_missing_watcher(self):
        """(5) REQUIRED: cooldown must NOT apply to reason="not_running" — a
        genuinely crashed/missing watcher is re-registered on every tick,
        exactly as before this cooldown existed (pre-existing behaviour)."""
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
            cfg.WATCHER_SELF_HEAL_COOLDOWN_SECONDS = 900
            mock_reg.dead_project_ids.return_value = {"proj-b": "not_running"}
            mock_reg.register = AsyncMock()
            adapter._start_reconcile_task()
            await _drive_reconcile(adapter, captured, n_ticks=3)

        # Every one of the 3 ticks re-registers — no cooldown suppression.
        self.assertEqual(mock_reg.register.await_count, 3)


if __name__ == "__main__":
    unittest.main()
