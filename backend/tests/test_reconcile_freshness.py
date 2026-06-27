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


if __name__ == "__main__":
    unittest.main()
