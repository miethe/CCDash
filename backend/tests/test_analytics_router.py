import types
import unittest
from unittest.mock import patch

from backend.routers import analytics as analytics_router


class _FakeSessionRepo:
    async def get_logs(self, session_id: str):
        return [
            {"timestamp": "2026-02-16T10:00:00Z", "metadata_json": '{"inputTokens": 10, "outputTokens": 20}'},
            {"timestamp": "2026-02-16T10:00:05Z", "metadata_json": '{"inputTokens": 5, "outputTokens": 15}'},
        ]

    async def list_paginated(self, *args, **kwargs):
        return []


class _FakeAnalyticsRepo:
    async def get_trends(self, *args, **kwargs):
        return []

    async def get_latest_entries(self, *args, **kwargs):
        return {
            "session_count": 12,
            "session_tokens": 3456,
        }


class _FakeAlertRepo:
    def __init__(self) -> None:
        self.items = {
            "alert-1": {
                "id": "alert-1",
                "name": "One",
                "metric": "total_tokens",
                "operator": ">",
                "threshold": 100,
                "is_active": 1,
                "scope": "session",
                "project_id": "project-1",
            }
        }

    async def list_all(self, project_id=None):
        return list(self.items.values())

    async def upsert(self, config_data):
        self.items[config_data["id"]] = {
            "id": config_data["id"],
            "name": config_data["name"],
            "metric": config_data["metric"],
            "operator": config_data["operator"],
            "threshold": config_data["threshold"],
            "is_active": 1 if config_data.get("is_active", True) else 0,
            "scope": config_data["scope"],
            "project_id": config_data.get("project_id"),
        }

    async def delete(self, config_id: str):
        self.items.pop(config_id, None)


class AnalyticsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_series_session_tokens_uses_log_usage_metadata(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_session_repository", return_value=_FakeSessionRepo()), patch.object(analytics_router, "get_analytics_repository", return_value=_FakeAnalyticsRepo()):
            payload = await analytics_router.get_series(metric="session_tokens", period="point", session_id="S-1")

        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["items"][0]["value"], 30)
        self.assertEqual(payload["items"][1]["value"], 50)

    async def test_alert_crud_roundtrip(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        repo = _FakeAlertRepo()
        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_alert_config_repository", return_value=repo):
            created = await analytics_router.create_alert(
                analytics_router.AlertConfigCreate(
                    id="alert-new",
                    name="New",
                    metric="session_cost",
                    operator=">",
                    threshold=10.5,
                    isActive=True,
                    scope="session",
                )
            )
            self.assertEqual(created.id, "alert-new")

            updated = await analytics_router.update_alert(
                "alert-new",
                analytics_router.AlertConfigPatch(threshold=42.0, isActive=False),
            )
            self.assertEqual(updated.threshold, 42.0)
            self.assertFalse(updated.isActive)

            deleted = await analytics_router.delete_alert("alert-new")
            self.assertEqual(deleted["status"], "ok")

    async def test_artifacts_endpoint_returns_artifact_analytics_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "totals": {
                "artifactCount": 5,
                "artifactTypes": 2,
                "sessions": 3,
                "features": 1,
                "models": 1,
                "modelFamilies": 1,
                "tools": 1,
                "sources": 1,
                "agents": 1,
                "skills": 1,
                "commands": 1,
                "kindTotals": {
                    "agents": 1,
                    "skills": 1,
                    "commands": 1,
                    "manifests": 0,
                    "requests": 0,
                },
            },
            "byType": [],
            "bySource": [],
            "byTool": [],
            "bySession": [],
            "byFeature": [],
            "modelArtifact": [],
            "modelFamilies": [],
            "artifactTool": [],
            "modelArtifactTool": [],
            "commandModel": [],
            "agentModel": [],
            "tokenUsage": {
                "byArtifactType": [],
                "byModel": [],
                "byModelArtifact": [],
                "byModelFamily": [],
            },
            "detailLimit": 120,
        }

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "_load_artifact_analytics_payload", return_value=payload):
            response = await analytics_router.get_artifacts(start="2026-02-01", end="2026-02-22")

        self.assertEqual(response["totals"]["artifactCount"], 5)
        self.assertEqual(response["range"]["start"], "2026-02-01")
        self.assertEqual(response["range"]["end"], "2026-02-22")
        self.assertIn("generatedAt", response)

    async def test_prometheus_export_includes_artifact_metrics(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        artifact_payload = {
            "totals": {
                "artifactCount": 10,
                "artifactTypes": 3,
                "sessions": 4,
                "features": 2,
                "models": 2,
                "tools": 3,
                "sources": 2,
                "kindTotals": {
                    "agents": 2,
                    "skills": 3,
                    "commands": 4,
                    "manifests": 1,
                    "requests": 0,
                },
            },
            "byType": [
                {
                    "artifactType": "skill",
                    "count": 5,
                    "sessions": 3,
                    "features": 2,
                    "tokenInput": 100,
                    "tokenOutput": 200,
                    "totalCost": 1.25,
                }
            ],
            "modelArtifact": [
                {
                    "model": "gpt-5",
                    "artifactType": "skill",
                    "count": 5,
                    "tokenInput": 100,
                    "tokenOutput": 200,
                    "totalCost": 1.25,
                }
            ],
            "modelFamilies": [
                {
                    "modelFamily": "Opus",
                    "artifactCount": 5,
                    "tokenInput": 100,
                    "tokenOutput": 200,
                    "totalCost": 1.25,
                }
            ],
            "artifactTool": [
                {
                    "artifactType": "skill",
                    "toolName": "Skill",
                    "count": 5,
                }
            ],
            "modelArtifactTool": [
                {
                    "model": "gpt-5",
                    "artifactType": "skill",
                    "toolName": "Skill",
                    "count": 5,
                    "tokenInput": 100,
                    "tokenOutput": 200,
                    "totalCost": 1.25,
                }
            ],
            "commandModel": [
                {
                    "command": "planning",
                    "model": "claude-opus-4-5",
                    "modelFamily": "Opus",
                    "count": 3,
                    "tokenInput": 50,
                    "tokenOutput": 75,
                    "totalCost": 0.5,
                }
            ],
            "agentModel": [
                {
                    "agent": "explorer",
                    "model": "claude-opus-4-5",
                    "modelFamily": "Opus",
                    "count": 2,
                    "tokenInput": 40,
                    "tokenOutput": 60,
                    "totalCost": 0.4,
                }
            ],
        }

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_analytics_repository", return_value=_FakeAnalyticsRepo()), patch.object(analytics_router, "_load_artifact_analytics_payload", return_value=artifact_payload):
            response = await analytics_router.export_prometheus()

        body = response.body.decode("utf-8")
        self.assertIn("ccdash_artifacts_total", body)
        self.assertIn('kind="commands"', body)
        self.assertIn("ccdash_model_artifact_tool_events_total", body)
        self.assertIn("ccdash_model_family_artifact_events_total", body)
        self.assertIn("ccdash_command_model_events_total", body)
        self.assertIn("ccdash_agent_model_events_total", body)
        self.assertIn("ccdash_session_count", body)


if __name__ == "__main__":
    unittest.main()
