import types
import unittest
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException

from backend.routers import cache as cache_router


@dataclass
class _FakeLiveBrokerStats:
    active_subscribers: int = 2
    buffered_topics: int = 3
    active_topic_subscriptions: int = 4
    published_events: int = 12
    dropped_events: int = 1
    buffer_evictions: int = 0
    replay_gaps: int = 2
    subscription_opens: int = 5
    subscription_closes: int = 3


class _FakeLiveBroker:
    def stats(self):
        return _FakeLiveBrokerStats()


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


@dataclass
class _FakeResolvedPath:
    path: Path
    source_kind: str = "filesystem"
    diagnostic: str = ""


@dataclass
class _FakeResolvedProjectPaths:
    root: _FakeResolvedPath
    sessions: _FakeResolvedPath
    plan_docs: _FakeResolvedPath
    progress: _FakeResolvedPath


class _FakeWorkspaceRegistry:
    def __init__(self, project, bundle: _FakeResolvedProjectPaths) -> None:
        self.project = project
        self.bundle = bundle

    def get_active_project(self):
        return self.project

    def resolve_project_paths(self, project):
        self.project = project
        return self.bundle


class _FakeEntityLinkRepository:
    async def get_links_for(self, entity_type, entity_id, link_type):
        return [
            {
                "id": 1,
                "source_type": entity_type,
                "source_id": entity_id,
                "target_type": "feature",
                "target_id": "feature-1",
                "link_type": link_type or "related",
                "origin": "manual",
                "confidence": 1.0,
                "depth": 0,
                "sort_order": 0,
                "created_at": "2026-03-27T00:00:00Z",
                "metadata_json": "{\"note\":\"ok\"}",
            }
        ]

    async def upsert(self, payload):
        self.last_payload = payload
        return 7

    async def get_tree(self, entity_type, entity_id):
        row = {
            "id": 1,
            "source_type": entity_type,
            "source_id": entity_id,
            "target_type": "feature",
            "target_id": "feature-1",
            "link_type": "child",
            "origin": "manual",
            "confidence": 1.0,
            "depth": 0,
            "sort_order": 0,
            "created_at": "2026-03-27T00:00:00Z",
            "metadata_json": "{}",
        }
        return {"children": [row], "parents": [], "related": []}


class CacheRouterTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, engine: _FakeSyncEngine, live_broker: _FakeLiveBroker | None = None):
        return types.SimpleNamespace(
            app=types.SimpleNamespace(
                state=types.SimpleNamespace(sync_engine=engine, live_event_broker=live_broker)
            )
        )

    def _core_ports(self, project=None, bundle: _FakeResolvedProjectPaths | None = None):
        project = project or types.SimpleNamespace(id="project-1", name="Project One", path="/tmp/project")
        bundle = bundle or _FakeResolvedProjectPaths(
            root=_FakeResolvedPath(Path("/tmp/project")),
            sessions=_FakeResolvedPath(Path("/tmp/sessions")),
            plan_docs=_FakeResolvedPath(Path("/tmp/project/docs")),
            progress=_FakeResolvedPath(Path("/tmp/project/progress")),
        )
        return types.SimpleNamespace(
            workspace_registry=_FakeWorkspaceRegistry(project, bundle),
            storage=types.SimpleNamespace(entity_links=lambda: _FakeEntityLinkRepository()),
        )

    async def test_status_includes_observability(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        project = types.SimpleNamespace(id="project-1", name="Project One", path="/tmp/project")

        payload = await cache_router.get_cache_status(request, self._core_ports(project=project))

        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["projectId"], "project-1")
        self.assertEqual(payload["projectName"], "Project One")
        self.assertEqual(payload["activePaths"]["docsDir"], "/tmp/project/docs")
        self.assertIn("operations", payload)
        self.assertIsNone(payload["liveUpdates"])

    async def test_status_includes_live_update_stats_when_available(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine, _FakeLiveBroker())
        project = types.SimpleNamespace(id="project-1", name="Project One", path="/tmp/project")

        payload = await cache_router.get_cache_status(request, self._core_ports(project=project))

        self.assertEqual(payload["liveUpdates"]["published_events"], 12)
        self.assertEqual(payload["liveUpdates"]["replay_gaps"], 2)

    async def test_sync_background_returns_operation_id(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")

        payload = await cache_router.trigger_sync(
            request,
            background,
            cache_router.SyncRequest(force=True, background=True, trigger="api"),
            self._core_ports(project=project),
        )

        self.assertEqual(payload["operationId"], "OP-STARTED")
        self.assertEqual(len(background.tasks), 1)
        self.assertEqual(engine.started_ops[0]["kind"], "full_sync")

    async def test_sync_foreground_returns_stats(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")

        payload = await cache_router.trigger_sync(
            request,
            background,
            cache_router.SyncRequest(force=False, background=False, trigger="manual"),
            self._core_ports(project=project),
        )

        self.assertEqual(payload["mode"], "foreground")
        self.assertEqual(payload["stats"]["sessions_synced"], 1)
        self.assertEqual(engine.sync_calls[0]["trigger"], "manual")

    async def test_sync_paths_rejects_outside_project(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")

        with self.assertRaises(HTTPException) as ctx:
            await cache_router.trigger_sync_paths(
                request,
                background,
                cache_router.SyncPathsRequest(
                    paths=[cache_router.ChangedPathSpec(path="../outside.md", changeType="modified")],
                    background=False,
                ),
                self._core_ports(project=project),
            )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_sync_paths_foreground_calls_sync_engine(self) -> None:
        engine = _FakeSyncEngine()
        request = self._request(engine)
        background = BackgroundTasks()
        project = types.SimpleNamespace(id="project-1", path="/tmp/project")

        payload = await cache_router.trigger_sync_paths(
            request,
            background,
            cache_router.SyncPathsRequest(
                paths=[cache_router.ChangedPathSpec(path="docs/example.md", changeType="modified")],
                background=False,
                trigger="api",
            ),
            self._core_ports(project=project),
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

        payload = await cache_router.get_links_audit(
            request,
            feature_id="feature-x",
            primary_floor=0.6,
            fanout_floor=8,
            limit=10,
            core_ports=self._core_ports(project=project),
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["feature_filter"], "feature-x")
        self.assertEqual(payload["suspect_count"], 1)

    async def test_link_routes_use_storage_ports(self) -> None:
        core_ports = self._core_ports()

        payload = await cache_router.get_entity_links("session", "s-1", None, core_ports)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["targetType"], "feature")


if __name__ == "__main__":
    unittest.main()
