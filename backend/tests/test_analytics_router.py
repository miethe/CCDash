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
        return {}


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


if __name__ == "__main__":
    unittest.main()
