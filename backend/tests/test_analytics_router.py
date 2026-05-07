import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.models import ArtifactRecommendation
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

    async def get_prometheus_telemetry_rows(self, *args, **kwargs):
        return {
            "tool_rows": [],
            "model_rows": [],
            "event_rows": [],
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


class _FakeArtifactRankingRepo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def list_rankings(self, **kwargs):
        self.calls.append(kwargs)
        rows = list(self.rows)
        for key in (
            "project_id",
            "period",
            "collection_id",
            "user_scope",
            "artifact_uuid",
            "artifact_id",
            "version_id",
            "workflow_id",
            "artifact_type",
        ):
            value = kwargs.get(key)
            if value is not None:
                rows = [row for row in rows if row.get(key) == value]
        recommendation_type = kwargs.get("recommendation_type")
        if recommendation_type:
            rows = [row for row in rows if recommendation_type in row.get("recommendation_types", [])]
        return {
            "rows": rows[: kwargs.get("limit", 50)],
            "total": len(rows),
            "limit": kwargs.get("limit", 50),
            "offset": kwargs.get("offset", 0),
            "next_cursor": None,
        }


def _artifact_ranking_row(**overrides):
    row = {
        "project_id": "project-1",
        "collection_id": "collection-a",
        "user_scope": "user-a",
        "artifact_type": "skill",
        "artifact_id": "expensive-skill",
        "artifact_uuid": "uuid-expensive",
        "version_id": "v1",
        "workflow_id": "workflow-a",
        "period": "30d",
        "exclusive_tokens": 100000,
        "supporting_tokens": 0,
        "cost_usd": 2.5,
        "session_count": 8,
        "workflow_count": 1,
        "last_observed_at": "2026-05-07T10:00:00Z",
        "avg_confidence": 0.85,
        "confidence": 0.85,
        "success_score": 0.7,
        "efficiency_score": 0.2,
        "quality_score": 0.7,
        "risk_score": 0.7,
        "context_pressure": 0.5,
        "sample_size": 8,
        "identity_confidence": 1.0,
        "snapshot_fetched_at": "2026-05-07T09:00:00Z",
        "recommendation_types": ["optimization_target"],
        "evidence": {
            "projectSessionCount": 8,
            "snapshot": {"defaultLoadMode": "on_demand", "status": "active"},
        },
        "computed_at": "2026-05-07T10:05:00Z",
    }
    row.update(overrides)
    return row


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeAuthorizationPolicy:
    def __init__(self, denied_action: str | None = None) -> None:
        self.denied_action = denied_action
        self.calls: list[dict[str, str | None]] = []

    async def authorize(self, context, *, action, resource=None):
        _ = context
        self.calls.append({"action": action, "resource": resource})
        if action == self.denied_action:
            return AuthorizationDecision(
                allowed=False,
                code="permission_not_granted",
                reason=f"{action} denied in test",
            )
        return AuthorizationDecision(allowed=True)


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
        _ = integration, operation, payload
        return {}


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if self.project and str(getattr(self.project, "id", "")) == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _FakeStorage:
    def __init__(
        self,
        *,
        db=None,
        analytics_repo=None,
        session_repo=None,
        task_repo=None,
        link_repo=None,
        feature_repo=None,
        alert_repo=None,
    ) -> None:
        self.db = db if db is not None else object()
        self._analytics_repo = analytics_repo
        self._session_repo = session_repo
        self._task_repo = task_repo
        self._link_repo = link_repo
        self._feature_repo = feature_repo
        self._alert_repo = alert_repo

    def analytics(self):
        return self._analytics_repo

    def sessions(self):
        return self._session_repo

    def tasks(self):
        return self._task_repo

    def entity_links(self):
        return self._link_repo

    def features(self):
        return self._feature_repo

    def alert_configs(self):
        return self._alert_repo


def _request_context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Test Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/sessions"),
            docs_dir=Path("/tmp/docs"),
            progress_dir=Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _core_ports(
    *,
    project=None,
    db=None,
    analytics_repo=None,
    session_repo=None,
    task_repo=None,
    link_repo=None,
    feature_repo=None,
    alert_repo=None,
    authorization_policy=None,
) -> CorePorts:
    resolved_project = project or types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=authorization_policy or _FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(resolved_project),
        storage=_FakeStorage(
            db=db,
            analytics_repo=analytics_repo,
            session_repo=session_repo,
            task_repo=task_repo,
            link_repo=link_repo,
            feature_repo=feature_repo,
            alert_repo=alert_repo,
        ),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class AnalyticsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_alert_denies_without_alert_create_permission(self) -> None:
        policy = _FakeAuthorizationPolicy(denied_action="analytics.alert:create")
        ports = _core_ports(alert_repo=_FakeAlertRepo(), authorization_policy=policy)

        with self.assertRaises(HTTPException) as ctx:
            await analytics_router.create_alert(
                analytics_router.AlertConfigCreate(
                    name="Denied",
                    metric="session_cost",
                    operator=">",
                    threshold=1.0,
                ),
                request_context=_request_context(),
                core_ports=ports,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["action"], "analytics.alert:create")
        self.assertEqual(ctx.exception.detail["resource"], "project:project-1")
        self.assertEqual(
            policy.calls,
            [{"action": "analytics.alert:create", "resource": "project:project-1"}],
        )

    async def test_session_intelligence_search_endpoint_returns_typed_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        with patch.object(
            analytics_router.transcript_search_service,
            "search",
            return_value=analytics_router.SessionSemanticSearchResponse(
                query="semantic search",
                total=1,
                offset=0,
                limit=25,
                capability=analytics_router.SessionIntelligenceCapability(
                    supported=True,
                    authoritative=False,
                    storageProfile="local",
                    searchMode="canonical_lexical",
                    detail="fallback",
                ),
                items=[
                    analytics_router.SessionSemanticSearchMatch(
                        sessionId="S-1",
                        featureId="feature-a",
                        rootSessionId="S-root",
                        threadSessionId="S-1",
                        blockKind="message",
                        blockIndex=1,
                        eventTimestamp="2026-04-03T00:00:00Z",
                        score=2.0,
                        matchedTerms=["semantic"],
                        messageIds=["msg-1"],
                        sourceLogIds=["log-1"],
                        content="semantic search",
                        snippet="semantic search",
                    )
                ],
            ),
        ) as search_mock:
            payload = await analytics_router.search_session_intelligence(
                query="semantic search",
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project),
            )

        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.items[0].sessionId, "S-1")
        search_mock.assert_awaited_once()

    async def test_session_intelligence_drilldown_endpoint_404s_when_missing(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        with patch.object(
            analytics_router.session_intelligence_read_service,
            "drilldown",
            return_value=None,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await analytics_router.get_session_intelligence_drilldown(
                    concern="scope_drift",
                    request_context=_request_context(project.id),
                    core_ports=_core_ports(project=project),
                )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Session intelligence drilldown not found")

    async def test_series_session_tokens_uses_log_usage_metadata(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = await analytics_router.get_series(
            metric="session_tokens",
            period="point",
            session_id="S-1",
            request_context=_request_context(project.id),
            core_ports=_core_ports(
                project=project,
                analytics_repo=_FakeAnalyticsRepo(),
                session_repo=_FakeSessionRepo(),
            ),
        )

        self.assertEqual(payload["total"], 2)

    async def test_artifact_rankings_endpoint_applies_phase_filters(self) -> None:
        repo = _FakeArtifactRankingRepo([_artifact_ranking_row()])
        project = types.SimpleNamespace(id="project-1")

        with patch.object(analytics_router, "get_artifact_ranking_repository", return_value=repo):
            payload = await analytics_router.get_artifact_rankings(
                project="project-1",
                collection="collection-a",
                user="user-a",
                period="30d",
                artifact="uuid-expensive",
                version="v1",
                workflow="workflow-a",
                artifact_type="skill",
                recommendation_type="optimization_target",
                refresh=False,
                offset=0,
                limit=50,
                cursor=None,
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project),
            )

        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.rows[0].artifact_id, "expensive-skill")
        self.assertEqual(repo.calls[0]["collection_id"], "collection-a")
        self.assertEqual(repo.calls[0]["user_scope"], "user-a")
        self.assertEqual(repo.calls[0]["artifact_uuid"], "uuid-expensive")
        self.assertEqual(repo.calls[0]["version_id"], "v1")
        self.assertEqual(repo.calls[0]["workflow_id"], "workflow-a")
        self.assertEqual(repo.calls[0]["artifact_type"], "skill")
        self.assertEqual(repo.calls[0]["recommendation_type"], "optimization_target")

    async def test_artifact_recommendations_endpoint_generates_advisory_payloads(self) -> None:
        repo = _FakeArtifactRankingRepo([_artifact_ranking_row(workflow_id="")])
        project = types.SimpleNamespace(id="project-1")

        with patch.object(analytics_router, "get_artifact_ranking_repository", return_value=repo):
            payload = await analytics_router.get_artifact_recommendations(
                project="project-1",
                recommendation_type="optimization_target",
                min_confidence=0.7,
                period="30d",
                collection="collection-a",
                user="user-a",
                workflow=None,
                limit=100,
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project),
            )

        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.recommendations[0].recommendation_type, "optimization_target")
        self.assertNotIn("auto_apply", ArtifactRecommendation.model_fields)

    async def test_artifact_intelligence_endpoints_reject_invalid_filters(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await analytics_router.get_artifact_rankings(
                project="project-1",
                period="forever",
                request_context=_request_context("project-1"),
                core_ports=_core_ports(),
            )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_alert_crud_roundtrip(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        repo = _FakeAlertRepo()
        core_ports = _core_ports(project=project, alert_repo=repo)
        created = await analytics_router.create_alert(
            analytics_router.AlertConfigCreate(
                id="alert-new",
                name="New",
                metric="session_cost",
                operator=">",
                threshold=10.5,
                isActive=True,
                scope="session",
            ),
            request_context=_request_context(project.id),
            core_ports=core_ports,
        )
        self.assertEqual(created.id, "alert-new")

        updated = await analytics_router.update_alert(
            "alert-new",
            analytics_router.AlertConfigPatch(threshold=42.0, isActive=False),
            request_context=_request_context(project.id),
            core_ports=core_ports,
        )
        self.assertEqual(updated.threshold, 42.0)
        self.assertFalse(updated.isActive)

        deleted = await analytics_router.delete_alert(
            "alert-new",
            request_context=_request_context(project.id),
            core_ports=core_ports,
        )
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

        with patch.object(analytics_router, "_load_artifact_analytics_payload", return_value=payload):
            response = await analytics_router.get_artifacts(
                start="2026-02-01",
                end="2026-02-22",
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

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
                        "current_context_tokens": 200,
                        "context_utilization_pct": 0.1,
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
                        "current_context_tokens": 0,
                        "context_utilization_pct": 0.0,
                        "started_at": "2026-03-03T09:01:00Z",
                    },
                ]

        response = await analytics_router.get_overview(
            request_context=_request_context(project.id),
            core_ports=_core_ports(
                project=project,
                analytics_repo=_FakeAnalyticsRepo(),
                task_repo=_TaskRepo(),
                session_repo=_SessionRepo(),
            ),
        )

        self.assertEqual(response["kpis"]["sessionTokens"], 9876)
        self.assertEqual(response["kpis"]["modelIOTokens"], 350)
        self.assertEqual(response["kpis"]["cacheInputTokens"], 90)
        self.assertEqual(response["kpis"]["observedTokens"], 440)
        self.assertEqual(response["kpis"]["toolReportedTokens"], 500)
        self.assertEqual(response["kpis"]["contextSessionCount"], 1)
        self.assertEqual(response["kpis"]["avgContextUtilizationPct"], 0.1)

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

        with patch.object(analytics_router, "get_workflow_effectiveness", return_value=payload):
            response = await analytics_router.workflow_effectiveness(
                limit=20,
                offset=0,
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.items[0].scopeType, "workflow")
        self.assertEqual(response.items[0].successScore, 0.8)

    async def test_workflow_registry_endpoint_wraps_service_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "projectId": "project-1",
            "items": [
                {
                    "id": "workflow:phase-execution",
                    "identity": {
                        "registryId": "workflow:phase-execution",
                        "observedWorkflowFamilyRef": "/dev:execute-phase",
                        "observedAliases": ["/dev:execute-phase"],
                        "displayLabel": "Phase Execution",
                        "resolvedWorkflowId": "phase-execution",
                        "resolvedWorkflowLabel": "Phase Execution",
                        "resolvedWorkflowSourceUrl": "https://example.com/workflows/phase-execution",
                        "resolvedCommandArtifactId": "",
                        "resolvedCommandArtifactLabel": "",
                        "resolvedCommandArtifactSourceUrl": "",
                        "resolutionKind": "workflow_definition",
                        "correlationState": "strong",
                    },
                    "correlationState": "strong",
                    "issueCount": 0,
                    "issues": [],
                    "effectiveness": {
                        "scopeType": "workflow",
                        "scopeId": "phase-execution",
                        "scopeLabel": "Phase Execution",
                        "sampleSize": 4,
                        "successScore": 0.75,
                        "efficiencyScore": 0.7,
                        "qualityScore": 0.8,
                        "riskScore": 0.2,
                        "attributionCoverage": 0.9,
                        "averageAttributionConfidence": 0.88,
                        "evidenceSummary": {"featureIds": ["feature-1"]},
                    },
                    "observedCommandCount": 3,
                    "representativeCommands": ["/dev:execute-phase"],
                    "sampleSize": 4,
                    "lastObservedAt": "2026-03-14T00:00:00+00:00",
                }
            ],
            "correlationCounts": {
                "strong": 1,
                "hybrid": 0,
                "weak": 0,
                "unresolved": 0,
            },
            "total": 1,
            "offset": 0,
            "limit": 20,
            "generatedAt": "2026-03-14T00:00:00+00:00",
        }

        with patch.object(analytics_router, "list_workflow_registry", return_value=payload):
            response = await analytics_router.workflow_registry(
                limit=20,
                offset=0,
                search="phase",
                correlation_state="strong",
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.items[0].id, "workflow:phase-execution")
        self.assertEqual(response.items[0].identity.displayLabel, "Phase Execution")
        self.assertEqual(response.items[0].correlationState, "strong")
        self.assertEqual(response.correlationCounts["strong"], 1)

    async def test_workflow_registry_detail_endpoint_wraps_service_payload(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        detail = {
            "id": "workflow:phase-execution",
            "identity": {
                "registryId": "workflow:phase-execution",
                "observedWorkflowFamilyRef": "/dev:execute-phase",
                "observedAliases": ["/dev:execute-phase"],
                "displayLabel": "Phase Execution",
                "resolvedWorkflowId": "phase-execution",
                "resolvedWorkflowLabel": "Phase Execution",
                "resolvedWorkflowSourceUrl": "https://example.com/workflows/phase-execution",
                "resolvedCommandArtifactId": "",
                "resolvedCommandArtifactLabel": "",
                "resolvedCommandArtifactSourceUrl": "",
                "resolutionKind": "workflow_definition",
                "correlationState": "strong",
            },
            "correlationState": "strong",
            "issueCount": 1,
            "issues": [
                {
                    "code": "stale_cache",
                    "severity": "warning",
                    "title": "Stale cache",
                    "message": "The cached workflow definition is older than the latest observation.",
                    "metadata": {},
                }
            ],
            "effectiveness": {
                "scopeType": "workflow",
                "scopeId": "phase-execution",
                "scopeLabel": "Phase Execution",
                "sampleSize": 4,
                "successScore": 0.75,
                "efficiencyScore": 0.7,
                "qualityScore": 0.8,
                "riskScore": 0.2,
                "attributionCoverage": 0.9,
                "averageAttributionConfidence": 0.88,
                "evidenceSummary": {"featureIds": ["feature-1"]},
            },
            "observedCommandCount": 3,
            "representativeCommands": ["/dev:execute-phase"],
            "sampleSize": 4,
            "lastObservedAt": "2026-03-14T00:00:00+00:00",
            "composition": {
                "artifactRefs": ["workflow:phase-execution"],
                "contextRefs": ["context:planning"],
                "resolvedContextModules": [],
                "planSummary": {"stages": 3},
                "stageOrder": ["plan", "execute", "validate"],
                "gateCount": 2,
                "fanOutCount": 1,
                "bundleAlignment": None,
            },
            "representativeSessions": [
                {
                    "sessionId": "session-1",
                    "featureId": "feature-1",
                    "title": "Workflow Session",
                    "status": "completed",
                    "workflowRef": "/dev:execute-phase",
                    "startedAt": "2026-03-14T00:00:00+00:00",
                    "endedAt": "2026-03-14T00:10:00+00:00",
                    "href": "/sessions/session-1",
                }
            ],
            "recentExecutions": [],
            "actions": [
                {
                    "id": "open-workflow",
                    "label": "Open workflow",
                    "target": "external",
                    "href": "https://example.com/workflows/phase-execution",
                    "disabled": False,
                    "reason": "",
                    "metadata": {},
                }
            ],
        }

        with patch.object(analytics_router, "get_workflow_registry_detail", return_value=detail):
            response = await analytics_router.workflow_registry_detail(
                registry_id="workflow:phase-execution",
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.item.id, "workflow:phase-execution")
        self.assertEqual(response.item.composition.stageOrder, ["plan", "execute", "validate"])
        self.assertEqual(response.item.actions[0].id, "open-workflow")

    async def test_workflow_registry_detail_endpoint_returns_404_when_missing(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        with patch.object(analytics_router, "get_workflow_registry_detail", return_value=None):
            with self.assertRaises(analytics_router.HTTPException) as ctx:
                await analytics_router.workflow_registry_detail(
                    registry_id="workflow:missing",
                    request_context=_request_context(project.id),
                    core_ports=_core_ports(project=project, db=object()),
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("workflow:missing", str(ctx.exception.detail))

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

        with patch.object(analytics_router, "detect_failure_patterns", return_value=payload):
            response = await analytics_router.failure_patterns(
                limit=20,
                offset=0,
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.projectId, "project-1")
        self.assertEqual(response.items[0].patternType, "queue_waste")
        self.assertEqual(response.items[0].scopeId, "debug-loop")

    def test_scope_validation_patterns_include_effective_workflow_and_bundle(self) -> None:
        workflow_route = next(
            route
            for route in analytics_router.analytics_router.routes
            if getattr(route, "path", "") == "/api/analytics/workflow-effectiveness"
        )
        registry_route = next(
            route
            for route in analytics_router.analytics_router.routes
            if getattr(route, "path", "") == "/api/analytics/workflow-registry"
        )
        registry_detail_route = next(
            route
            for route in analytics_router.analytics_router.routes
            if getattr(route, "path", "") == "/api/analytics/workflow-registry/detail"
        )
        failure_route = next(
            route
            for route in analytics_router.analytics_router.routes
            if getattr(route, "path", "") == "/api/analytics/failure-patterns"
        )

        workflow_scope_param = next(param for param in workflow_route.dependant.query_params if param.alias == "scopeType")
        registry_state_param = next(param for param in registry_route.dependant.query_params if param.alias == "correlationState")
        registry_detail_param = next(param for param in registry_detail_route.dependant.query_params if param.alias == "registryId")
        failure_scope_param = next(param for param in failure_route.dependant.query_params if param.alias == "scopeType")

        workflow_pattern = workflow_scope_param.field_info.metadata[0].pattern
        registry_pattern = registry_state_param.field_info.metadata[0].pattern
        failure_pattern = failure_scope_param.field_info.metadata[0].pattern

        self.assertIn("effective_workflow", workflow_pattern)
        self.assertIn("bundle", workflow_pattern)
        self.assertIn("strong", registry_pattern)
        self.assertIn("unresolved", registry_pattern)
        self.assertEqual(registry_detail_param.alias, "registryId")
        self.assertIn("effective_workflow", failure_pattern)
        self.assertIn("bundle", failure_pattern)

    async def test_workflow_registry_endpoint_returns_503_when_disabled(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        with patch.object(
            analytics_router,
            "require_workflow_analytics_enabled",
            side_effect=analytics_router.HTTPException(status_code=503, detail="disabled"),
        ):
            with self.assertRaises(analytics_router.HTTPException) as ctx:
                await analytics_router.workflow_registry(
                    limit=10,
                    offset=0,
                    request_context=_request_context(project.id),
                    core_ports=_core_ports(project=project, db=object()),
                )

        self.assertEqual(ctx.exception.status_code, 503)

    async def test_workflow_effectiveness_endpoint_returns_503_when_disabled(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        with patch.object(
            analytics_router,
            "require_workflow_analytics_enabled",
            side_effect=analytics_router.HTTPException(status_code=503, detail="disabled"),
        ):
            with self.assertRaises(analytics_router.HTTPException) as ctx:
                await analytics_router.workflow_effectiveness(
                    limit=20,
                    offset=0,
                    request_context=_request_context(project.id),
                    core_ports=_core_ports(project=project, db=object()),
                )

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

        with patch.object(analytics_router, "_load_artifact_analytics_payload", return_value=artifact_payload):
            response = await analytics_router.export_prometheus(
                request_context=_request_context(project.id),
                core_ports=_core_ports(
                    project=project,
                    db=object(),
                    analytics_repo=_FakeAnalyticsRepo(),
                ),
            )

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
        notifications = await analytics_router.get_notifications(
            request,
            request_context=_request_context(project.id),
            core_ports=_core_ports(project=project, session_repo=_SessionRepo()),
        )

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
                        "current_context_tokens": 120,
                        "context_window_size": 200000,
                        "context_utilization_pct": 0.06,
                        "context_measurement_source": "hook_context_window",
                        "context_measured_at": "2026-03-03T09:04:00Z",
                        "reported_cost_usd": 1.5,
                        "recalculated_cost_usd": 1.35,
                        "display_cost_usd": 1.5,
                        "cost_provenance": "reported",
                        "cost_confidence": 0.98,
                        "cost_mismatch_pct": 0.1,
                        "pricing_model_source": "claude-opus-4-5",
                        "platform_version": "2.1.52",
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
                        "current_context_tokens": 0,
                        "context_window_size": 0,
                        "context_utilization_pct": 0.0,
                        "context_measurement_source": "",
                        "context_measured_at": "",
                        "reported_cost_usd": None,
                        "recalculated_cost_usd": None,
                        "display_cost_usd": 0.2,
                        "cost_provenance": "estimated",
                        "cost_confidence": 0.45,
                        "cost_mismatch_pct": None,
                        "pricing_model_source": "",
                        "platform_version": "1.0.0",
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

        payload = await analytics_router.get_correlation(
            request_context=_request_context(project.id),
            core_ports=_core_ports(
                project=project,
                session_repo=_SessionRepo(),
                link_repo=_LinkRepo(),
                feature_repo=_FeatureRepo(),
            ),
        )

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
        self.assertEqual(linked_row["currentContextTokens"], 120)
        self.assertEqual(linked_row["contextWindowSize"], 200000)
        self.assertEqual(linked_row["contextUtilizationPct"], 0.06)
        self.assertEqual(linked_row["costProvenance"], "reported")
        self.assertEqual(linked_row["reportedCostUsd"], 1.5)
        self.assertEqual(linked_row["recalculatedCostUsd"], 1.35)
        self.assertEqual(linked_row["displayCostUsd"], 1.5)
        self.assertEqual(linked_row["costMismatchPct"], 0.1)
        self.assertEqual(linked_row["pricingModelSource"], "claude-opus-4-5")
        self.assertEqual(linked_row["platformVersion"], "2.1.52")
        self.assertEqual(linked_row["durationSeconds"], 300)
        self.assertFalse(linked_row["isSubagent"])

        self.assertEqual(unlinked_row["featureId"], "")
        self.assertEqual(unlinked_row["linkedFeatureCount"], 0)
        self.assertEqual(unlinked_row["sessionType"], "subagent")
        self.assertEqual(unlinked_row["rootSessionId"], "S-1")
        self.assertEqual(unlinked_row["parentSessionId"], "S-1")
        self.assertEqual(unlinked_row["observedTokens"], 90)
        self.assertEqual(unlinked_row["costProvenance"], "estimated")
        self.assertTrue(unlinked_row["isSubagent"])

    async def test_session_cost_calibration_aggregates_comparable_sessions(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        class _SessionRepo:
            async def list_paginated(self, *args, **kwargs):
                return [
                    {
                        "id": "S-1",
                        "model": "claude-sonnet-4-5-20260101",
                        "platform_version": "2.1.52",
                        "display_cost_usd": 1.2,
                        "reported_cost_usd": 1.2,
                        "recalculated_cost_usd": 1.1,
                        "cost_provenance": "reported",
                        "cost_confidence": 0.98,
                        "cost_mismatch_pct": 0.0833,
                    },
                    {
                        "id": "S-2",
                        "model": "claude-sonnet-4-5-20260101",
                        "platform_version": "2.1.52",
                        "display_cost_usd": 0.5,
                        "reported_cost_usd": None,
                        "recalculated_cost_usd": 0.5,
                        "cost_provenance": "recalculated",
                        "cost_confidence": 0.9,
                        "cost_mismatch_pct": None,
                    },
                    {
                        "id": "S-3",
                        "model": "gpt-5",
                        "platform_version": "1.0.0",
                        "display_cost_usd": 0.25,
                        "reported_cost_usd": None,
                        "recalculated_cost_usd": None,
                        "cost_provenance": "estimated",
                        "cost_confidence": 0.45,
                        "cost_mismatch_pct": None,
                    },
                ]

        payload = await analytics_router.get_session_cost_calibration(
            request_context=_request_context(project.id),
            core_ports=_core_ports(project=project, session_repo=_SessionRepo()),
        )

        self.assertEqual(payload.sessionCount, 3)
        self.assertEqual(payload.comparableSessionCount, 1)
        self.assertEqual(payload.reportedSessionCount, 1)
        self.assertEqual(payload.recalculatedSessionCount, 2)
        self.assertAlmostEqual(payload.avgMismatchPct, 0.0833)
        self.assertEqual(payload.byModel[0].label, "claude-sonnet-4-5")
        self.assertEqual(payload.byPlatformVersion[0].label, "2.1.52")

    async def test_usage_attribution_endpoint_wraps_rollup_service(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "generatedAt": "2026-03-10T00:00:00+00:00",
            "total": 1,
            "offset": 0,
            "limit": 50,
            "rows": [
                {
                    "entityType": "skill",
                    "entityId": "symbols",
                    "entityLabel": "symbols",
                    "exclusiveTokens": 80,
                    "supportingTokens": 0,
                    "exclusiveModelIOTokens": 60,
                    "exclusiveCacheInputTokens": 20,
                    "supportingModelIOTokens": 0,
                    "supportingCacheInputTokens": 0,
                    "exclusiveCostUsdModelIO": 0.6,
                    "supportingCostUsdModelIO": 0.0,
                    "eventCount": 2,
                    "primaryEventCount": 2,
                    "supportingEventCount": 0,
                    "sessionCount": 1,
                    "averageConfidence": 0.82,
                    "methods": [],
                }
            ],
            "summary": {
                "entityCount": 1,
                "sessionCount": 1,
                "eventCount": 2,
                "totalExclusiveTokens": 80,
                "totalSupportingTokens": 0,
                "totalExclusiveModelIOTokens": 60,
                "totalExclusiveCacheInputTokens": 20,
                "totalExclusiveCostUsdModelIO": 0.6,
                "averageConfidence": 0.82,
            },
        }

        with patch.object(analytics_router, "get_usage_attribution_rollup", return_value=payload):
            response = await analytics_router.get_usage_attribution(
                limit=50,
                offset=0,
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.rows[0].entityType, "skill")
        self.assertEqual(response.summary.totalExclusiveTokens, 80)

    async def test_usage_attribution_drilldown_endpoint_wraps_service(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "generatedAt": "2026-03-10T00:00:00+00:00",
            "total": 1,
            "offset": 0,
            "limit": 100,
            "items": [
                {
                    "eventId": "evt-1",
                    "sessionId": "S-1",
                    "rootSessionId": "S-1",
                    "linkedSessionId": "",
                    "sessionType": "session",
                    "parentSessionId": "",
                    "sourceLogId": "log-1",
                    "capturedAt": "2026-03-10T10:00:00Z",
                    "eventKind": "message",
                    "tokenFamily": "model_input",
                    "deltaTokens": 60,
                    "costUsdModelIO": 0.6,
                    "model": "claude-opus-4-6",
                    "toolName": "",
                    "agentName": "planner",
                    "entityType": "skill",
                    "entityId": "symbols",
                    "entityLabel": "symbols",
                    "attributionRole": "primary",
                    "weight": 1.0,
                    "method": "explicit_skill_invocation",
                    "confidence": 1.0,
                    "metadata": {},
                }
            ],
            "summary": {
                "entityCount": 1,
                "sessionCount": 1,
                "eventCount": 1,
                "totalExclusiveTokens": 60,
                "totalSupportingTokens": 0,
                "totalExclusiveModelIOTokens": 60,
                "totalExclusiveCacheInputTokens": 0,
                "totalExclusiveCostUsdModelIO": 0.6,
                "averageConfidence": 1.0,
            },
        }

        with patch.object(analytics_router, "get_usage_attribution_drilldown", return_value=payload):
            response = await analytics_router.get_usage_attribution_drilldown_view(
                entity_type="skill",
                entity_id="symbols",
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.items[0].entityId, "symbols")
        self.assertEqual(response.summary.totalExclusiveModelIOTokens, 60)

    async def test_usage_attribution_calibration_endpoint_wraps_service(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        payload = {
            "projectId": "project-1",
            "sessionCount": 1,
            "eventCount": 3,
            "attributedEventCount": 3,
            "primaryAttributedEventCount": 3,
            "ambiguousEventCount": 0,
            "unattributedEventCount": 0,
            "primaryCoverage": 1.0,
            "supportingCoverage": 1.0,
            "sessionModelIOTokens": 100,
            "exclusiveModelIOTokens": 100,
            "modelIOGap": 0,
            "sessionCacheInputTokens": 20,
            "exclusiveCacheInputTokens": 20,
            "cacheGap": 0,
            "averageConfidence": 0.84,
            "confidenceBands": [{"band": "high", "count": 2}],
            "methodMix": [{"method": "explicit_skill_invocation", "tokens": 60, "eventCount": 1, "averageConfidence": 1.0}],
            "generatedAt": "2026-03-10T00:00:00+00:00",
        }

        with patch.object(analytics_router, "get_usage_attribution_calibration", return_value=payload):
            response = await analytics_router.get_usage_attribution_calibration_view(
                request_context=_request_context(project.id),
                core_ports=_core_ports(project=project, db=object()),
            )

        self.assertEqual(response.eventCount, 3)
        self.assertEqual(response.modelIOGap, 0)

    async def test_usage_attribution_endpoint_returns_503_when_disabled(self) -> None:
        project = types.SimpleNamespace(id="project-1")

        with patch.object(
            analytics_router,
            "require_usage_attribution_enabled",
            side_effect=analytics_router.HTTPException(status_code=503, detail="disabled"),
        ):
            with self.assertRaises(analytics_router.HTTPException) as ctx:
                await analytics_router.get_usage_attribution(
                    limit=10,
                    offset=0,
                    request_context=_request_context(project.id),
                    core_ports=_core_ports(project=project, db=object()),
                )

        self.assertEqual(ctx.exception.status_code, 503)

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
