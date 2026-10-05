"""Watcher reconcile must skip (not raise / not traceback-spam) a project whose root does not resolve.

Incident (2026-10-04 18:20 ET, laptop stream-worker @51307a5): every ~60s
``_watcher_reconcile_tick`` re-tried a project whose ``pathConfig.root`` had no filesystem path
and logged a full ``PathResolutionError('missing_filesystem_path')`` traceback each time, growing
the err log ~9KB/s until the disk filled (node_01M44GE8XNP7ZEA3PM1C2D7YGK).
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models import Project, ProjectPathConfig, ProjectPathReference
from backend.services.project_paths.providers.base import PathResolutionError
from backend.services.project_paths.resolver import ProjectPathResolver

RUNTIME_LOGGER = "ccdash.runtime.jobs"


def _adapter(registry: MagicMock):
    from backend.adapters.jobs.runtime import RuntimeJobAdapter
    from backend.runtime.profiles import get_runtime_profile

    ports = MagicMock()
    ports.workspace_registry = registry
    return RuntimeJobAdapter(
        profile=get_runtime_profile("worker-watch"),
        ports=ports,
        sync_engine=None,
        watcher_fan_out_bindings=[],
    )


def _blank_root_project(pid: str, path: str = "") -> Project:
    blank_root = ProjectPathReference(field="root", sourceKind="filesystem", filesystemPath="")
    return Project(id=pid, name=pid, path=path, pathConfig=ProjectPathConfig(root=blank_root))


def _registry_raising(pids: list[str]) -> MagicMock:
    registry = MagicMock()
    registry.list_projects.return_value = [_blank_root_project(pid) for pid in pids]
    registry.reload_projects = MagicMock()
    registry.registry_snapshot_is_authoritative = MagicMock(return_value=True)
    registry.resolve_project_binding.side_effect = PathResolutionError(
        "missing_filesystem_path", "Field 'root' requires a filesystem path."
    )
    return registry


class ReconcileTickUnresolvableRootTests(unittest.TestCase):
    def test_tick_does_not_raise_and_logs_once_across_ticks(self) -> None:
        registry = _registry_raising(["bad-root"])
        adapter = _adapter(registry)

        with self.assertLogs(RUNTIME_LOGGER, level="DEBUG") as captured:
            for _ in range(5):
                asyncio.run(adapter._watcher_reconcile_tick(None))

        warnings = [r for r in captured.records if "paths do not resolve" in r.getMessage()]
        self.assertEqual(len(warnings), 1, [r.getMessage() for r in captured.records])
        self.assertFalse(warnings[0].exc_info)
        self.assertEqual([r for r in captured.records if r.exc_info], [])
        self.assertNotIn("bad-root", adapter.state.fan_out_watcher_tasks)
        # Still retried each tick (so a repaired row is picked up), just not re-logged.
        self.assertEqual(registry.resolve_project_binding.call_count, 5)

    def test_log_suppression_window_is_per_project_and_expires(self) -> None:
        adapter = _adapter(_registry_raising([]))
        exc = PathResolutionError("missing_filesystem_path", "Field 'root' requires a filesystem path.")
        with patch(
            "backend.adapters.jobs.runtime.config.WATCHER_UNRESOLVABLE_PROJECT_LOG_INTERVAL_SECONDS",
            0,
            create=True,
        ):
            self.assertTrue(adapter._log_unresolvable_project_once("p", exc))
            self.assertTrue(adapter._log_unresolvable_project_once("p", exc))
        self.assertTrue(adapter._log_unresolvable_project_once("q", exc))
        self.assertFalse(adapter._log_unresolvable_project_once("q", exc))


class FilesystemRootFallbackTests(unittest.TestCase):
    def test_blank_root_reference_falls_back_to_project_path(self) -> None:
        project = _blank_root_project("legacy", path="/tmp/legacy-root")
        self.assertEqual(project.path, "/tmp/legacy-root")
        root = ProjectPathResolver().resolve_reference(project, project.pathConfig.root)
        self.assertEqual(root.path, Path("/tmp/legacy-root").resolve(strict=False))

    def test_blank_root_and_blank_path_still_raises(self) -> None:
        project = _blank_root_project("nothing", path="")
        with self.assertRaises(PathResolutionError) as ctx:
            ProjectPathResolver().resolve_reference(project, project.pathConfig.root)
        self.assertEqual(ctx.exception.code, "missing_filesystem_path")


if __name__ == "__main__":
    unittest.main()
