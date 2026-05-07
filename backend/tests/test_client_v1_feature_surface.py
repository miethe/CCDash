"""Contract tests for Phase 2 v1 feature-surface routes.

These tests intentionally stay structural:

* bootstrap the real throwaway runtime used by ``test_client_v1_contract.py``
* seed one minimal feature + linked session into the temporary SQLite DB
* validate envelope/query/JSON shape only

Because Batch 2 route work may land in parallel, each test first checks whether
the relevant route/query mode is advertised by the current OpenAPI schema. When
the new surface is not present yet, that individual test skips instead of
breaking unrelated router work.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.application.context import ProjectScope, WorkspaceScope
from backend.models import Project
from backend.runtime.bootstrap import build_runtime_app


class TestClientV1FeatureSurfaceContract(unittest.TestCase):
    _PROJECT_ID = "project-feature-surface-contract"
    _FEATURE_ID = "FEAT-SURFACE-1"
    _SESSION_ID = "session-surface-1"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        cls._env_patcher.start()

        cls._app = build_runtime_app("test")
        cls._patches = [
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.adapters.jobs.runtime.file_watcher.start", new_callable=lambda: lambda: AsyncMock()),
            patch("backend.adapters.jobs.runtime.file_watcher.stop", new_callable=lambda: lambda: AsyncMock()),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=None),
        ]
        for p in cls._patches:
            p.start()

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

        cls._install_active_project_fixture()
        asyncio.run(cls._seed_feature_surface_fixture())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._restore_workspace_registry()
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    @classmethod
    def _install_active_project_fixture(cls) -> None:
        registry = cls._app.state.core_ports.workspace_registry
        cls._workspace_registry = registry
        cls._workspace_registry_originals = {
            "get_active_project": registry.get_active_project,
            "get_project": registry.get_project,
            "resolve_scope": registry.resolve_scope,
        }

        project_root = Path(tempfile.gettempdir()) / "ccdash-feature-surface-contract"
        project_root.mkdir(parents=True, exist_ok=True)
        sessions_dir = project_root / "sessions"
        docs_dir = project_root / "docs"
        progress_dir = project_root / "progress"
        for path in (sessions_dir, docs_dir, progress_dir):
            path.mkdir(parents=True, exist_ok=True)

        cls._project = Project(
            id=cls._PROJECT_ID,
            name="Feature Surface Contract",
            path=str(project_root),
            sessionsPath=str(sessions_dir),
            planDocsPath="docs",
            progressPath="progress",
        )
        cls._workspace_scope = WorkspaceScope(
            workspace_id=cls._PROJECT_ID,
            root_path=project_root,
        )
        cls._project_scope = ProjectScope(
            project_id=cls._PROJECT_ID,
            project_name=cls._project.name,
            root_path=project_root,
            sessions_dir=sessions_dir,
            docs_dir=docs_dir,
            progress_dir=progress_dir,
        )

        registry.get_active_project = types.MethodType(lambda self: cls._project, registry)
        registry.get_project = types.MethodType(
            lambda self, project_id: cls._project if project_id == cls._PROJECT_ID else None,
            registry,
        )
        registry.resolve_scope = types.MethodType(
            lambda self, project_id=None, **_: (
                (cls._workspace_scope, cls._project_scope)
                if project_id in (None, cls._PROJECT_ID)
                else (None, None)
            ),
            registry,
        )

    @classmethod
    def _restore_workspace_registry(cls) -> None:
        registry = getattr(cls, "_workspace_registry", None)
        originals = getattr(cls, "_workspace_registry_originals", None)
        if registry is None or originals is None:
            return
        registry.get_active_project = originals["get_active_project"]
        registry.get_project = originals["get_project"]
        registry.resolve_scope = originals["resolve_scope"]

    @classmethod
    async def _seed_feature_surface_fixture(cls) -> None:
        storage = cls._app.state.core_ports.storage

        await storage.features().upsert(
            {
                "id": cls._FEATURE_ID,
                "name": "Feature Surface Fixture",
                "status": "in_progress",
                "category": "delivery",
                "totalTasks": 5,
                "completedTasks": 2,
                "createdAt": "2026-04-23T09:00:00Z",
                "updatedAt": "2026-04-23T12:00:00Z",
                "data_json": {},
                "summary": "Contract fixture summary",
                "priority": "high",
                "riskLevel": "medium",
                "complexity": "moderate",
                "executionReadiness": "ready",
                "testImpact": "api contract tests",
                "tags": ["phase-2", "contract"],
                "deferredTasks": 1,
                "phaseCount": 2,
                "plannedAt": "2026-04-21",
                "startedAt": "2026-04-22",
                "documentCoverage": {"present": ["prd"], "missing": ["qa"], "countsByType": {"prd": 1}},
                "qualitySignals": {"blockerCount": 1, "atRiskTaskCount": 1},
                "planningStatus": {"effectiveStatus": "active"},
                "relatedFeatures": ["FEAT-DEP-1"],
                "dependencyState": {"state": "blocked", "blockedByCount": 1},
                "blockingFeatures": [{"feature": "FEAT-DEP-1"}],
                "familySummary": {"featureFamily": "alpha"},
                "familyPosition": {"index": 1},
                "executionGate": {"state": "ready_after_dependencies"},
                "primaryDocuments": [{"documentId": "doc-1", "title": "Plan", "docType": "prd"}],
            },
            cls._PROJECT_ID,
        )
        await storage.features().upsert_phases(
            cls._FEATURE_ID,
            [
                {
                    "id": f"{cls._FEATURE_ID}:phase-1",
                    "phase": "1",
                    "title": "Phase 1",
                    "status": "in_progress",
                    "progress": 0.5,
                    "totalTasks": 2,
                    "completedTasks": 1,
                }
            ],
        )
        await storage.sessions().upsert(
            {
                "id": cls._SESSION_ID,
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "totalCost": 1.25,
                "observedTokens": 320,
                "modelIOTokens": 450,
                "cacheInputTokens": 40,
                "startedAt": "2026-04-23T10:00:00Z",
                "endedAt": "2026-04-23T10:15:00Z",
                "updatedAt": "2026-04-23T10:15:00Z",
                "rootSessionId": cls._SESSION_ID,
                "sourceFile": "sessions/session-surface-1.jsonl",
            },
            cls._PROJECT_ID,
        )
        await storage.entity_links().upsert(
            {
                "source_type": "feature",
                "source_id": cls._FEATURE_ID,
                "target_type": "session",
                "target_id": cls._SESSION_ID,
                "link_type": "related",
                "origin": "test",
                "confidence": 1.0,
            }
        )

    def _openapi_paths(self) -> dict:
        return self._app.openapi()["paths"]

    def _operation(self, path: str, method: str) -> dict | None:
        return self._openapi_paths().get(path, {}).get(method.lower())

    def _query_param_names(self, path: str, method: str = "get") -> set[str]:
        operation = self._operation(path, method) or {}
        names: set[str] = set()
        for param in operation.get("parameters", []):
            if param.get("in") == "query" and isinstance(param.get("name"), str):
                names.add(param["name"])
        return names

    def _assert_base_envelope(self, body: dict) -> None:
        self.assertIn("status", body)
        self.assertIn("data", body)
        self.assertIn("meta", body)
        self.assertEqual(body["status"], "ok")
        for field in ("generated_at", "instance_id", "request_id"):
            self.assertIn(field, body["meta"])

    def _require_query_param(self, path: str, *names: str) -> str:
        available = self._query_param_names(path)
        for name in names:
            if name in available:
                return name
        self.skipTest(f"{path} does not advertise any of query params {names}")

    def _get_first_success(self, path: str, candidates: list[dict[str, str | int]]) -> tuple[dict[str, str | int], object]:
        last_response = None
        for params in candidates:
            response = self.client.get(path, params=params)
            if response.status_code == 200:
                return params, response
            last_response = response
        self.fail(
            f"No candidate query params produced 200 for {path}; "
            f"last status was {getattr(last_response, 'status_code', 'n/a')}"
        )

    def _post_first_success(self, path: str, bodies: list[dict]) -> object:
        last_response = None
        for body in bodies:
            response = self.client.post(path, json=body)
            if response.status_code == 200:
                return response
            last_response = response
        self.fail(
            f"No candidate request body produced 200 for {path}; "
            f"last status was {getattr(last_response, 'status_code', 'n/a')}"
        )

    def test_features_card_mode_returns_page_contract_when_enabled(self) -> None:
        path = "/api/v1/features"
        mode_param = self._require_query_param(path, "include", "view", "mode")

        candidates = [
            {mode_param: "card", "limit": 10, "offset": 0},
            {mode_param: "card,phase_summary", "limit": 10, "offset": 0},
            {mode_param: "cards", "limit": 10, "offset": 0},
        ]
        _, response = self._get_first_success(path, candidates)
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreaterEqual(len(data["items"]), 1)

        first = data["items"][0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("effectiveStatus", first)
        self.assertIn("documentCoverage", first)
        self.assertIn("qualitySignals", first)
        self.assertIn("dependencyState", first)
        self.assertEqual(first.get("priority"), "high")
        self.assertEqual(first.get("riskLevel"), "medium")
        self.assertEqual(first.get("complexity"), "moderate")
        self.assertEqual(first.get("executionReadiness"), "ready")
        self.assertEqual(first.get("testImpact"), "api contract tests")
        self.assertEqual(first.get("planningStatus", {}).get("effectiveStatus"), "active")
        self.assertEqual(first.get("deferredTasks"), 1)
        self.assertEqual(first.get("phaseCount"), 2)
        self.assertEqual(first.get("plannedAt"), "2026-04-21")
        self.assertEqual(first.get("startedAt"), "2026-04-22")
        self.assertEqual(first.get("relatedFeatureCount"), 1)
        self.assertEqual(first.get("documentCoverage", {}).get("countsByType", {}).get("prd"), 1)
        self.assertEqual(first.get("qualitySignals", {}).get("blockerCount"), 1)
        self.assertEqual(first.get("dependencyState", {}).get("blockedByCount"), 1)

        pagination_fields = {"total", "offset", "limit", "hasMore"}
        self.assertTrue(
            pagination_fields.issubset(data.keys()) or {"total", "offset", "limit", "has_more"}.issubset(data.keys()),
            f"card-mode payload missing pagination fields: {sorted(pagination_fields)}",
        )

    def test_feature_rollups_endpoint_returns_rollup_map_contract(self) -> None:
        path = "/api/v1/features/rollups"
        if path not in self._openapi_paths():
            self.skipTest("Feature rollups endpoint is not registered in this checkout")

        response = self._post_first_success(
            path,
            bodies=[
                {
                    "feature_ids": [self._FEATURE_ID],
                    "fields": ["session_counts", "latest_activity"],
                    "include_inherited_threads": True,
                },
                {"featureIds": [self._FEATURE_ID], "fields": ["session_counts", "latest_activity"]},
                {"featureIds": [self._FEATURE_ID], "includeFreshness": True},
            ],
        )
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)
        self.assertIn("rollups", data)
        self.assertIsInstance(data["rollups"], dict)
        self.assertIn(self._FEATURE_ID, data["rollups"])

        rollup = data["rollups"][self._FEATURE_ID]
        self.assertEqual(rollup.get("featureId"), self._FEATURE_ID)
        self.assertIn("precision", rollup)
        self.assertTrue(
            any(key in rollup for key in ("sessionCount", "totalCost", "latestActivityAt")),
            "rollup payload should expose at least one card metric field",
        )

        self.assertIn("missing", data)
        self.assertIsInstance(data["missing"], list)

    def test_feature_sessions_page_returns_linked_session_contract(self) -> None:
        path = f"/api/v1/features/{self._FEATURE_ID}/sessions/page"
        if "/api/v1/features/{feature_id}/sessions/page" not in self._openapi_paths():
            self.skipTest("Feature linked-session page endpoint is not registered in this checkout")

        response = self.client.get(path, params={"limit": 20, "offset": 0})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreaterEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0].get("sessionId"), self._SESSION_ID)
        self.assertIn("total", data)
        self.assertIn("hasMore", data)

    def test_feature_detail_overview_include_returns_lightweight_modal_contract(self) -> None:
        path = f"/api/v1/features/{self._FEATURE_ID}"
        include_param = self._require_query_param("/api/v1/features/{feature_id}", "include", "sections")

        candidates = [
            {include_param: "overview_shell"},
            {include_param: "overview"},
            {include_param: "overview_shell,relations"},
        ]
        _, response = self._get_first_success(path, candidates)
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)

        if "card" in data:
            self.assertIn("featureId", data)
            self.assertIn("card", data)
            self.assertIsInstance(data["card"], dict)
            self.assertIn("id", data["card"])
            self.assertIn("effectiveStatus", data["card"])
            return

        self.assertTrue(
            any(key in data for key in ("featureId", "id")),
            "overview payload should expose a feature identifier",
        )
        self.assertIn("name", data)
        self.assertIn("status", data)
        self.assertTrue(
            any(key in data for key in ("documentCoverage", "qualitySignals", "planningStatus")),
            "overview payload should expose lightweight modal shell fields",
        )
        self.assertNotIn("linkedSessions", data, "overview shell must not eagerly inline linked sessions")

    def test_feature_section_endpoint_returns_section_contract_when_registered(self) -> None:
        section_paths = [
            path
            for path in self._openapi_paths()
            if path.startswith("/api/v1/features/{feature_id}/") and "section" in path
        ]
        if not section_paths:
            self.skipTest("No dedicated feature section endpoint is registered in this checkout")

        path_template = section_paths[0]
        if "{section}" in path_template:
            path = path_template.replace("{feature_id}", self._FEATURE_ID).replace("{section}", "relations")
            response = self.client.get(path)
        else:
            path = path_template.replace("{feature_id}", self._FEATURE_ID)
            param_name = self._require_query_param(path_template, "section", "sections")
            section_value = "relations" if param_name == "section" else "relations"
            response = self.client.get(path, params={param_name: section_value})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)

        if "section" in data:
            self.assertEqual(data["section"], "relations")
            self.assertIn("items", data)
            self.assertIsInstance(data["items"], list)
            return

        if "sections" in data and isinstance(data["sections"], dict):
            self.assertIn("relations", data["sections"])
            self.assertEqual(data["sections"]["relations"].get("section"), "relations")
            return

        self.assertIn("relations", data)
        self.assertEqual(data["relations"].get("section"), "relations")

    def test_feature_sessions_route_uses_paginated_feature_surface_contract_when_enabled(self) -> None:
        path = f"/api/v1/features/{self._FEATURE_ID}/sessions"
        operation = self._operation("/api/v1/features/{feature_id}/sessions", "get")
        self.assertIsNotNone(operation, "feature sessions route must exist")

        response = self.client.get(path, params={"limit": 1, "offset": 0})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self._assert_base_envelope(body)

        data = body["data"]
        self.assertIsInstance(data, dict)
        if "items" not in data:
            params = self._query_param_names("/api/v1/features/{feature_id}/sessions")
            modern_markers = {"include", "sort", "order", "primary_only", "workflow_type", "phase"}
            if params.isdisjoint(modern_markers):
                self.skipTest("Feature sessions route still exposes the legacy compatibility DTO on this checkout")
            self.fail("Feature sessions route advertises the Phase 2 surface but did not return paginated items")

        self.assertIsInstance(data["items"], list)
        self.assertLessEqual(len(data["items"]), 1)
        self.assertGreaterEqual(data.get("total", 0), len(data["items"]))
        self.assertIn("enrichment", data)
        self.assertIsInstance(data["enrichment"], dict)
        self.assertIn("includes", data["enrichment"])

        if data["items"]:
            first = data["items"][0]
            self.assertIn("sessionId", first)
            self.assertIn("status", first)
            self.assertIn("isPrimaryLink", first)


if __name__ == "__main__":
    unittest.main()
