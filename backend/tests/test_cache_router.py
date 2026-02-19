import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from backend.routers import cache as cache_router


class _FakeSyncEngine:
    def __init__(self) -> None:
        self.started_ops: list[dict] = []
        self.sync_calls: list[dict] = []
        self.rebuild_calls: list[dict] = []
        self.path_sync_calls: list[dict] = []

    async def get_observability_snapshot(self):
        return {"activeOperationCount": 1, "activeOperations": [{"id": "OP-1"}], "recentOperations": [], "trackedOperationCount": 1}

    async def list_operations(self, limit=20):
        return [{"id": "OP-1", "status": "running"}][:limit]

    async def get_operation(self, operation_id):
        if operation_id == "OP-404":
            return None
        return {"id": operation_id, "status": "completed"}

    async def start_operation(self, kind, project_id, trigger="api", metadata=None):
        payload = {"kind": kind, "project_id": project_id, "trigger": trigger, "metadata": metadata or {}}
        self.started_ops.append(payload)
        return "OP-STARTED"

    async def sync_project(self, project, sessions_dir, docs_dir, progress_dir, force=False, operation_id=None, trigger="api"):
        self.sync_calls.append({
            "project_id": project.id,
            "force": force,
            "operation_id": operation_id,
            "trigger": trigger,
            "sessions_dir": str(sessions_dir),
            "docs_dir": str(docs_dir),
            "progress_dir": str(progress_dir),
        })
        return {"operation_id": operation_id or "OP-FOREGROUND", "sessions_synced": 1}

    async def rebuild_links(self, project_id, docs_dir=None, progress_dir=None, operation_id=None, trigger="api", capture_analytics=False):
        self.rebuild_calls.append({
            "project_id": project_id,
            "operation_id": operation_id,
            "trigger": trigger,
            "capture_analytics": capture_analytics,
        })
        return {"operation_id": operation_id or "OP-LINKS", "created": 10}

    async def sync_changed_files(self, project_id, changed_files, sessions_dir, docs_dir, progress_dir, operation_id=None, trigger="api"):
        self.path_sync_calls.append({
            "project_id": project_id,
            "changed_files": changed_files,
            "operation_id": operation_id,
            "trigger": trigger,
        })
        return {"sessions": 0, "documents": len(changed_files), "tasks": 0, "features": 0}

    async def run_link_audit(self, project_id, feature_id="", primary_floor=0.55, fanout_floor=10, limit=50):
        return {
            "project_id": project_id,
            "feature_filter": feature_id or None,
            "row_count": 2,
            "suspect_count": 1,
            "primary_floor": primary_floor,
            "fanout_floor": fanout_floor,
            "suspects": [{"feature_id": "f1", "session_id": "s1"}],
        }


class CacheRouterTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, engine: _FakeSyncEngine):
        return types.SimpleNamespace(
            app=types.SimpleNamespace(
                state=types.SimpleNamespace(sync_engine=engine)
            )
        )

    async def test_status_includes_observability(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        project = types.SimpleNamespace(id="project-1", name="Project One", path="/tmp/project")
        paths = (Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=paths):
            payload = await cache_router.get_cache_status(request)

        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["projectId"], "project-1")
        self.assertEqual(payload["projectName"], "Project One")
        self.assertEqual(payload["activePaths"]["docsDir"], "/tmp/project/docs")
        self.assertIn("operations", payload)

    async def test_sync_background_returns_operation_id(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")
        paths = (Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=paths):
            payload = await cache_router.trigger_sync(
                request,
                background,
                cache_router.SyncRequest(force=True, background=True, trigger="api"),
            )

        self.assertEqual(payload["operationId"], "OP-STARTED")
        self.assertEqual(len(background.tasks), 1)
        self.assertEqual(engine.started_ops[0]["kind"], "full_sync")

    async def test_sync_foreground_returns_stats(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")
        paths = (Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=paths):
            payload = await cache_router.trigger_sync(
                request,
                background,
                cache_router.SyncRequest(force=False, background=False, trigger="manual"),
            )

        self.assertEqual(payload["mode"], "foreground")
        self.assertEqual(payload["stats"]["sessions_synced"], 1)
        self.assertEqual(engine.sync_calls[0]["trigger"], "manual")

    async def test_sync_paths_rejects_outside_project(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")
        paths = (Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=paths):
            with self.assertRaises(HTTPException) as ctx:
                await cache_router.trigger_sync_paths(
                    request,
                    background,
                    cache_router.SyncPathsRequest(
                        paths=[cache_router.ChangedPathSpec(path="../outside.md", changeType="modified")],
                        background=False,
                    ),
                )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_sync_paths_foreground_calls_sync_engine(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")
        paths = (Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=paths):
            payload = await cache_router.trigger_sync_paths(
                request,
                background,
                cache_router.SyncPathsRequest(
                    paths=[cache_router.ChangedPathSpec(path="docs/example.md", changeType="modified")],
                    background=False,
                    trigger="api",
                ),
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(engine.path_sync_calls), 1)
        change_type, resolved_path = engine.path_sync_calls[0]["changed_files"][0]
        self.assertEqual(change_type, "modified")
        self.assertTrue(str(resolved_path).endswith("/tmp/project/docs/example.md"))

    async def test_links_audit_endpoint(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")

        with patch.object(cache_router.project_manager, "get_active_project", return_value=project), patch.object(cache_router.project_manager, "get_active_paths", return_value=(Path("/tmp/sessions"), Path("/tmp/project/docs"), Path("/tmp/project/progress"))):
            payload = await cache_router.get_links_audit(request, feature_id="feature-x", primary_floor=0.6, fanout_floor=8, limit=10)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["feature_filter"], "feature-x")
        self.assertEqual(payload["suspect_count"], 1)


if __name__ == "__main__":
    unittest.main()
