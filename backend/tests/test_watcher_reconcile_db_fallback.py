"""Watcher reconcile must not read a DB-unavailable fallback snapshot as deregistration.

Incident (2026-09-26 22:36 / 22:47 EDT, Mac direct-Postgres worker): two Postgres connect
timeouts made ``DbProjectManager`` serve its projects.json read-fallback (5 stale projects
instead of 428).  The T3-004 watcher reconcile tick diffed that against 428 live watchers and
stopped 320 of them, then wedged mid-removal and never ticked again.  Every project whose watcher
was removed stopped ingesting live; the next morning's night report showed 31 ingest gaps in
exactly those 14 projects (node_01M3EXGG6DFXGN4GCRCYP8JDST).

These tests drive the real ``RuntimeJobAdapter._watcher_reconcile_tick`` (not a re-implementation
of its diff) and the real ``DbProjectManager`` fallback branch.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.models import Project
from backend.project_manager import DbProjectManager, ProjectManager
from backend.tests.test_project_manager import _make_db_manager


def _project(pid: str) -> Project:
    return Project(id=pid, name=f"Project {pid}", path=f"/tmp/{pid}")


def _registry(projects: list[Project], *, authoritative: bool) -> MagicMock:
    registry = MagicMock()
    registry.list_projects.return_value = list(projects)
    registry.resolve_project_binding.return_value = None  # additions are not under test here
    registry.reload_projects = MagicMock()
    registry.registry_snapshot_is_authoritative = MagicMock(return_value=authoritative)
    return registry


def _adapter(registry: MagicMock, active_ids: list[str]):
    from backend.adapters.jobs.runtime import RuntimeJobAdapter
    from backend.runtime.profiles import get_runtime_profile

    ports = MagicMock()
    ports.workspace_registry = registry
    adapter = RuntimeJobAdapter(
        profile=get_runtime_profile("worker-watch"),
        ports=ports,
        sync_engine=None,
        watcher_fan_out_bindings=[],
    )
    for pid in active_ids:
        task = MagicMock(spec=asyncio.Task)
        task.done.return_value = True
        adapter.state.fan_out_watcher_tasks[pid] = task
        adapter.state.fan_out_watcher_health[pid] = "running"
    return adapter


class _FakeWatcherRegistry:
    def __init__(self, hang: bool = False) -> None:
        self.hang = hang
        self.unregistered: list[str] = []

    async def unregister(self, project_id: str) -> None:
        if self.hang:
            await asyncio.Event().wait()  # never set: a stuck stop
        self.unregistered.append(project_id)


class WatcherReconcileFallbackSnapshotTests(unittest.TestCase):
    def test_fallback_snapshot_does_not_remove_live_watchers(self) -> None:
        live = [f"ccp-{i:03d}" for i in range(428)]
        registry = _registry([_project("default-skillmeat"), _project("test-project-1")], authoritative=False)
        adapter = _adapter(registry, live)
        fake = _FakeWatcherRegistry()

        with patch("backend.adapters.jobs.runtime.file_watcher_registry", fake):
            warning = asyncio.run(adapter._watcher_reconcile_tick(None))

        self.assertEqual(set(adapter.state.fan_out_watcher_tasks), set(live))
        self.assertEqual(fake.unregistered, [])
        self.assertIsNotNone(warning)
        self.assertIn("non-authoritative", warning)
        self.assertIn("skipped 428 watcher removal(s)", warning)

    def test_authoritative_snapshot_still_removes_deregistered_watchers(self) -> None:
        """Negative control: the guard must not disable genuine deregistration."""
        registry = _registry([_project("keep")], authoritative=True)
        adapter = _adapter(registry, ["keep", "gone"])
        fake = _FakeWatcherRegistry()

        with patch("backend.adapters.jobs.runtime.file_watcher_registry", fake):
            warning = asyncio.run(adapter._watcher_reconcile_tick(None))

        self.assertEqual(set(adapter.state.fan_out_watcher_tasks), {"keep"})
        self.assertEqual(fake.unregistered, ["gone"])
        self.assertIsNone(warning)

    def test_registry_without_authority_probe_keeps_legacy_removal_behaviour(self) -> None:
        registry = _registry([], authoritative=True)
        del registry.registry_snapshot_is_authoritative
        adapter = _adapter(registry, ["gone"])
        fake = _FakeWatcherRegistry()

        with patch("backend.adapters.jobs.runtime.file_watcher_registry", fake):
            asyncio.run(adapter._watcher_reconcile_tick(None))

        self.assertEqual(fake.unregistered, ["gone"])

    def test_stuck_unregister_does_not_wedge_the_tick(self) -> None:
        from backend import config

        registry = _registry([], authoritative=True)
        adapter = _adapter(registry, ["a", "b"])
        fake = _FakeWatcherRegistry(hang=True)

        async def _tick_with_ceiling():
            return await asyncio.wait_for(adapter._watcher_reconcile_tick(None), timeout=10)

        with patch("backend.adapters.jobs.runtime.file_watcher_registry", fake), \
             patch.object(config, "WATCHER_RECONCILE_STOP_TIMEOUT_SECONDS", 1):
            started = time.monotonic()
            asyncio.run(_tick_with_ceiling())
            elapsed = time.monotonic() - started

        self.assertEqual(adapter.state.fan_out_watcher_tasks, {})
        self.assertLess(elapsed, 5)

    def test_watcher_task_ignoring_cancel_does_not_wedge_the_tick(self) -> None:
        from backend import config

        registry = _registry([], authoritative=True)
        adapter = _adapter(registry, [])
        fake = _FakeWatcherRegistry()

        async def _scenario():
            release = asyncio.Event()

            async def _stubborn():
                while not release.is_set():
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        continue  # swallows cancel: the shape that hangs an unbounded await

            stubborn = asyncio.create_task(_stubborn())
            await asyncio.sleep(0)
            adapter.state.fan_out_watcher_tasks["stuck"] = stubborn
            await asyncio.wait_for(adapter._watcher_reconcile_tick(None), timeout=10)
            removed = "stuck" not in adapter.state.fan_out_watcher_tasks
            release.set()  # let the stubborn task end so the loop can shut down
            await stubborn
            return removed

        with patch("backend.adapters.jobs.runtime.file_watcher_registry", fake), \
             patch.object(config, "WATCHER_RECONCILE_STOP_TIMEOUT_SECONDS", 1):
            self.assertTrue(asyncio.run(_scenario()))
        self.assertEqual(fake.unregistered, ["stuck"])


class DbProjectManagerSnapshotAuthorityTests(unittest.TestCase):
    def test_db_snapshot_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_db_manager(tmpdir)
            manager.add_project(_project("p1"))
            manager.reload()
            manager.list_projects()
            self.assertTrue(manager.snapshot_is_authoritative())
            self.assertTrue(ProjectManagerWorkspaceRegistry(manager).registry_snapshot_is_authoritative())

    def test_db_unavailable_fallback_is_not_authoritative_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_db_manager(tmpdir)
            manager.add_project(_project("p1"))
            manager.reload()
            with patch.object(manager, "_get_repo", side_effect=OSError("Operation timed out")):
                fallback_ids = {p.id for p in manager.list_projects()}
                self.assertNotIn("p1", fallback_ids)  # the fallback really is a different set
                self.assertFalse(manager.snapshot_is_authoritative())
                self.assertFalse(ProjectManagerWorkspaceRegistry(manager).registry_snapshot_is_authoritative())
            # The probe reports the snapshot just served; it never reloads behind the caller.
            self.assertFalse(manager.snapshot_is_authoritative())
            # The fallback leaves the snapshot unloaded, so the next read retries the DB.
            self.assertIn("p1", {p.id for p in manager.list_projects()})
            self.assertTrue(manager.snapshot_is_authoritative())

    def test_legacy_json_manager_is_authoritative_by_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy = ProjectManager(Path(tmpdir) / "projects.json")
            self.assertTrue(ProjectManagerWorkspaceRegistry(legacy).registry_snapshot_is_authoritative())


if __name__ == "__main__":
    unittest.main()
