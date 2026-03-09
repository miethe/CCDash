import types
import unittest
from unittest.mock import patch

from backend.routers import analytics as analytics_router


class _FakeSessionRepo:
    async def get_project_stats(self, project_id: str):
        return {
            "count": 3,
            "cost": 4.5,
            "tokens": 9876,
            "duration": 123.0,
        }

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

    async def test_overview_prefers_observed_session_token_stats(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        class _TaskRepo:
            async def get_project_stats(self, project_id: str):
                return {"completed": 7, "completion_pct": 63.0}

        class _SessionRepo(_FakeSessionRepo):
            async def list_paginated(self, *args, **kwargs):
                return [
                    {
                        "id": "S-1",
                        "model": "claude-opus-4-5",
                        "tokens_in": 120,
                        "tokens_out": 180,
                        "model_io_tokens": 300,
                        "cache_input_tokens": 80,
                        "observed_tokens": 380,
                        "tool_reported_tokens": 500,
                        "started_at": "2026-03-03T09:00:00Z",
                    },
                    {
                        "id": "S-2",
                        "model": "gpt-5",
                        "tokens_in": 20,
                        "tokens_out": 30,
                        "model_io_tokens": 50,
                        "cache_input_tokens": 10,
                        "observed_tokens": 60,
                        "tool_reported_tokens": 0,
                        "started_at": "2026-03-03T09:01:00Z",
                    },
                ]

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_analytics_repository", return_value=_FakeAnalyticsRepo()), patch.object(analytics_router, "get_task_repository", return_value=_TaskRepo()), patch.object(analytics_router, "get_session_repository", return_value=_SessionRepo()):
            response = await analytics_router.get_overview()

        self.assertEqual(response["kpis"]["sessionTokens"], 9876)
        self.assertEqual(response["kpis"]["modelIOTokens"], 350)
        self.assertEqual(response["kpis"]["cacheInputTokens"], 90)
        self.assertEqual(response["kpis"]["observedTokens"], 440)
        self.assertEqual(response["kpis"]["toolReportedTokens"], 500)

    async def test_workflow_effectiveness_endpoint_wraps_service_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "projectId": "project-1",
            "period": "all",
            "metricDefinitions": [
                {
                    "id": "successScore",
                    "label": "Success",
                    "description": "desc",
                    "formula": "formula",
                    "inputs": ["session.status"],
                }
            ],
            "items": [
                {
                    "projectId": "project-1",
                    "scopeType": "workflow",
                    "scopeId": "phase-execution",
                    "scopeLabel": "phase-execution",
                    "period": "all",
                    "sampleSize": 2,
                    "successScore": 0.8,
                    "efficiencyScore": 0.7,
                    "qualityScore": 0.9,
                    "riskScore": 0.2,
                    "evidenceSummary": {"featureIds": ["feature-1"]},
                    "generatedAt": "2026-03-07T00:00:00+00:00",
                }
            ],
            "total": 1,
            "offset": 0,
            "limit": 20,
            "generatedAt": "2026-03-07T00:00:00+00:00",
        }

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_workflow_effectiveness", return_value=payload):
            response = await analytics_router.workflow_effectiveness(limit=20, offset=0)

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.items[0].scopeType, "workflow")
        self.assertEqual(response.items[0].successScore, 0.8)

    async def test_failure_patterns_endpoint_wraps_service_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "projectId": "project-1",
            "items": [
                {
                    "id": "queue_waste:workflow:debug-loop",
                    "patternType": "queue_waste",
                    "title": "Queue waste",
                    "scopeType": "workflow",
                    "scopeId": "debug-loop",
                    "severity": "high",
                    "confidence": 0.9,
                    "occurrenceCount": 2,
                    "averageSuccessScore": 0.4,
                    "averageRiskScore": 0.8,
                    "evidenceSummary": {"representativeSessionIds": ["session-2"]},
                    "sessionIds": ["session-2"],
                }
            ],
            "total": 1,
            "offset": 0,
            "limit": 20,
            "generatedAt": "2026-03-07T00:00:00+00:00",
        }

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "detect_failure_patterns", return_value=payload):
            response = await analytics_router.failure_patterns(limit=20, offset=0)

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.items[0].patternType, "queue_waste")
        self.assertEqual(response.items[0].scopeId, "debug-loop")

    async def test_workflow_effectiveness_endpoint_returns_503_when_disabled(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(analytics_router.project_manager, "get_active_project", return_value=project),
            patch.object(analytics_router, "require_workflow_analytics_enabled", side_effect=analytics_router.HTTPException(status_code=503, detail="disabled")),
        ):
            with self.assertRaises(analytics_router.HTTPException) as ctx:
                await analytics_router.workflow_effectiveness(limit=20, offset=0)

        self.assertEqual(ctx.exception.status_code, 503)

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

    async def test_notifications_include_operation_events(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        class _SessionRepo:
            async def list_paginated(self, *args, **kwargs):
                return [
                    {
                        "id": "S-1",
                        "model": "claude-opus-4-5",
                        "total_cost": 1.2345,
                        "started_at": "2026-03-03T09:00:00Z",
                    }
                ]

        class _SyncEngine:
            async def list_operations(self, limit=50):
                return [
                    {
                        "id": "OP-1",
                        "kind": "test_mapping_backfill",
                        "projectId": "project-1",
                        "status": "completed",
                        "finishedAt": "2026-03-03T09:30:00Z",
                        "stats": {"runs_processed": 12, "mappings_stored": 40},
                    }
                ]

        request = types.SimpleNamespace(
            app=types.SimpleNamespace(state=types.SimpleNamespace(sync_engine=_SyncEngine()))
        )
        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_session_repository", return_value=_SessionRepo()):
            notifications = await analytics_router.get_notifications(request)

        self.assertGreaterEqual(len(notifications), 2)
        self.assertIn("Mapping backfill completed", notifications[0].message)
        self.assertFalse(notifications[0].isRead)

    async def test_correlation_includes_enriched_session_context_fields(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        class _SessionRepo:
            async def list_paginated(self, *args, **kwargs):
                return [
                    {
                        "id": "S-1",
                        "model": "claude-opus-4-5",
                        "status": "completed",
                        "git_commit_hash": "abc123",
                        "started_at": "2026-03-03T09:00:00Z",
                        "ended_at": "2026-03-03T09:05:00Z",
                        "root_session_id": "S-1",
                        "parent_session_id": None,
                        "session_type": "",
                        "duration_seconds": 300,
                        "tokens_in": 120,
                        "tokens_out": 180,
                        "model_io_tokens": 300,
                        "cache_creation_input_tokens": 20,
                        "cache_read_input_tokens": 60,
                        "cache_input_tokens": 80,
                        "observed_tokens": 380,
                        "tool_reported_tokens": 500,
                        "total_cost": 1.5,
                    },
                    {
                        "id": "S-2",
                        "model": "gpt-5",
                        "status": "completed",
                        "git_commit_hash": "",
                        "started_at": "2026-03-03T09:01:00Z",
                        "ended_at": "2026-03-03T09:02:00Z",
                        "root_session_id": "S-1",
                        "parent_session_id": "S-1",
                        "session_type": "subagent",
                        "duration_seconds": 60,
                        "tokens_in": 20,
                        "tokens_out": 30,
                        "model_io_tokens": 50,
                        "cache_creation_input_tokens": 15,
                        "cache_read_input_tokens": 25,
                        "cache_input_tokens": 40,
                        "observed_tokens": 90,
                        "tool_reported_tokens": 140,
                        "total_cost": 0.2,
                    },
                ]

        class _LinkRepo:
            async def get_links_for(self, entity_type: str, entity_id: str, relation: str):
                if entity_type == "session" and entity_id == "S-1" and relation == "related":
                    return [
                        {
                            "source_type": "feature",
                            "source_id": "F-1",
                            "confidence": 0.82,
                            "metadata_json": '{"linkStrategy":"explicit"}',
                        }
                    ]
                return []

        class _FeatureRepo:
            async def get_by_id(self, feature_id: str):
                if feature_id == "F-1":
                    return {"name": "Feature One"}
                return None

        with patch.object(analytics_router.project_manager, "get_active_project", return_value=project), patch.object(analytics_router.connection, "get_connection", return_value=object()), patch.object(analytics_router, "get_session_repository", return_value=_SessionRepo()), patch.object(analytics_router, "get_entity_link_repository", return_value=_LinkRepo()), patch.object(analytics_router, "get_feature_repository", return_value=_FeatureRepo()):
            payload = await analytics_router.get_correlation()

        self.assertEqual(payload["total"], 2)
        linked_row = next(row for row in payload["items"] if row["sessionId"] == "S-1")
        unlinked_row = next(row for row in payload["items"] if row["sessionId"] == "S-2")

        self.assertEqual(linked_row["featureId"], "F-1")
        self.assertEqual(linked_row["linkedFeatureCount"], 1)
        self.assertEqual(linked_row["tokenInput"], 120)
        self.assertEqual(linked_row["tokenOutput"], 180)
        self.assertEqual(linked_row["modelIOTokens"], 300)
        self.assertEqual(linked_row["cacheInputTokens"], 80)
        self.assertEqual(linked_row["observedTokens"], 380)
        self.assertEqual(linked_row["toolReportedTokens"], 500)
        self.assertEqual(linked_row["totalTokens"], 380)
        self.assertEqual(linked_row["durationSeconds"], 300)
        self.assertFalse(linked_row["isSubagent"])

        self.assertEqual(unlinked_row["featureId"], "")
        self.assertEqual(unlinked_row["linkedFeatureCount"], 0)
        self.assertEqual(unlinked_row["sessionType"], "subagent")
        self.assertEqual(unlinked_row["rootSessionId"], "S-1")
        self.assertEqual(unlinked_row["parentSessionId"], "S-1")
        self.assertEqual(unlinked_row["observedTokens"], 90)
        self.assertTrue(unlinked_row["isSubagent"])

    def test_build_artifact_payload_agent_model_falls_back_to_main_agent_speaker(self) -> None:
        payload = analytics_router._build_artifact_analytics_payload(
            artifact_rows=[
                {
                    "session_id": "S-1",
                    "feature_id": "",
                    "model": "claude-opus-4-5",
                    "tool_name": "Read",
                    "agent": "",
                    "skill": "",
                    "status": "skill",
                    "occurred_at": "2026-03-03T09:00:00Z",
                    "payload_json": '{"type":"skill","source":"SkillMeat","title":"X"}',
                }
            ],
            lifecycle_rows=[
                {
                    "session_id": "S-1",
                    "feature_id": "",
                    "model": "claude-opus-4-5",
                    "status": "completed",
                    "occurred_at": "2026-03-03T09:00:00Z",
                    "token_input": 100,
                    "token_output": 200,
                    "cost_usd": 1.5,
                    "payload_json": "{}",
                }
            ],
            feature_link_rows=[],
            feature_rows=[],
            command_rows=[],
            agent_rows=[
                {
                    "session_id": "S-1",
                    "model": "claude-opus-4-5",
                    "agent": "",
                    "event_type": "log.message",
                    "occurred_at": "2026-03-03T09:00:01Z",
                    "payload_json": '{"speaker":"agent","metadata":{}}',
                }
            ],
            detail_limit=120,
            feature_filter=None,
            model_filter=None,
            model_family_filter=None,
        )

        self.assertGreaterEqual(len(payload["agentModel"]), 1)
        row = payload["agentModel"][0]
        self.assertEqual(row["agent"], "Main Session")
        self.assertEqual(row["model"], "claude-opus-4-5")
        self.assertEqual(row["sessions"], 1)

    def test_build_artifact_payload_agent_model_works_without_artifact_rows(self) -> None:
        payload = analytics_router._build_artifact_analytics_payload(
            artifact_rows=[],
            lifecycle_rows=[
                {
                    "session_id": "S-1",
                    "feature_id": "",
                    "model": "claude-opus-4-5",
                    "status": "completed",
                    "occurred_at": "2026-03-03T09:00:00Z",
                    "token_input": 10,
                    "token_output": 20,
                    "cost_usd": 0.3,
                    "payload_json": "{}",
                }
            ],
            feature_link_rows=[],
            feature_rows=[],
            command_rows=[],
            agent_rows=[
                {
                    "session_id": "S-1",
                    "model": "claude-opus-4-5",
                    "agent": "",
                    "event_type": "log.message",
                    "occurred_at": "2026-03-03T09:00:01Z",
                    "payload_json": '{"speaker":"agent","metadata":{}}',
                }
            ],
            detail_limit=120,
            feature_filter=None,
            model_filter=None,
            model_family_filter=None,
        )

        self.assertEqual(payload["totals"]["artifactCount"], 0)
        self.assertGreaterEqual(len(payload["agentModel"]), 1)
        self.assertEqual(payload["agentModel"][0]["agent"], "Main Session")


if __name__ == "__main__":
    unittest.main()
