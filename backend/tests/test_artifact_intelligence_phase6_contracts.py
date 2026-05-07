import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.db.repositories.artifact_snapshot_repository import SqliteArtifactSnapshotRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    ArtifactOutcomePayload,
    ArtifactRecommendationType,
    ArtifactUsageRollup,
    SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
)
from backend.routers import analytics as analytics_router
from backend.services.identity_resolver import ArtifactIdentityMapper
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient
from backend.services.integrations.skillmeat_client import SkillMeatClient


_ALL_RECOMMENDATION_TYPES: set[ArtifactRecommendationType] = {
    "disable_candidate",
    "load_on_demand",
    "workflow_specific_swap",
    "optimization_target",
    "version_regression",
    "identity_reconciliation",
    "insufficient_data",
}


def _request_context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Test Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):  # noqa: ANN001
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):  # noqa: ANN001
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:  # noqa: ANN001
        self.project = project

    def get_project(self, project_id):  # noqa: ANN001
        if self.project and str(getattr(self.project, "id", "")) == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _FakeStorage:
    def __init__(self, db=None) -> None:  # noqa: ANN001
        self.db = db if db is not None else object()


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):  # noqa: ANN001
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):  # noqa: ANN001
        _ = integration, operation, payload
        return {}


def _core_ports(project_id: str = "project-1", *, db=None) -> CorePorts:  # noqa: ANN001
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(types.SimpleNamespace(id=project_id, name="Project 1")),
        storage=_FakeStorage(db=db),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


def _snapshot_artifact(name: str, *, uuid: str, suffix: str) -> dict[str, Any]:
    return {
        "definitionType": "skill",
        "externalId": f"skill:{name}",
        "artifactUuid": uuid,
        "displayName": name,
        "versionId": f"version-{name}",
        "contentHash": f"sha256:{suffix * 64}",
        "collectionIds": ["collection-a"],
        "deploymentProfileIds": ["claude-code"],
        "defaultLoadMode": "workflow_scoped",
        "workflowRefs": ["workflow-a"],
        "tags": [name],
        "status": "active",
    }


def _snapshot_payload() -> dict[str, Any]:
    return {
        "schemaVersion": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
        "generatedAt": "2026-05-07T10:00:00Z",
        "projectId": "project-1",
        "collectionId": "collection-a",
        "artifacts": [
            _snapshot_artifact("code-review", uuid="uuid-code-review", suffix="a"),
            _snapshot_artifact("frontend-design", uuid="uuid-frontend-design", suffix="b"),
        ],
        "freshness": {
            "snapshotSource": "skillmeat",
            "sourceGeneratedAt": "2026-05-07T10:00:00Z",
            "fetchedAt": "2026-05-07T10:01:00Z",
            "warnings": [],
        },
    }


def _ranking_row(**overrides: Any) -> dict[str, Any]:
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
        "supporting_tokens": 100,
        "cost_usd": 2.5,
        "session_count": 8,
        "workflow_count": 1,
        "last_observed_at": "2026-05-07T10:00:00Z",
        "avg_confidence": 0.85,
        "confidence": 0.85,
        "success_score": 0.7,
        "efficiency_score": 0.3,
        "quality_score": 0.7,
        "risk_score": 0.65,
        "context_pressure": 0.5,
        "sample_size": 8,
        "identity_confidence": 1.0,
        "snapshot_fetched_at": "2099-05-07T09:00:00Z",
        "recommendation_types": ["optimization_target"],
        "evidence": {"projectSessionCount": 12, "snapshot": {"defaultLoadMode": "on_demand", "status": "active"}},
        "computed_at": "2026-05-07T10:05:00Z",
    }
    row.update(overrides)
    return row


def _recommendation_fixture_rows() -> list[dict[str, Any]]:
    return [
        _ranking_row(
            artifact_id="unused",
            artifact_uuid="unused",
            workflow_id="",
            session_count=0,
            sample_size=0,
            confidence=None,
            recommendation_types=["disable_candidate"],
            evidence={"projectSessionCount": 12, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        ),
        _ranking_row(
            artifact_id="narrow",
            artifact_uuid="narrow",
            workflow_id="",
            workflow_count=1,
            context_pressure=0.85,
            recommendation_types=["load_on_demand"],
            evidence={"projectSessionCount": 12, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        ),
        _ranking_row(
            artifact_id="expensive",
            artifact_uuid="expensive",
            workflow_id="",
            session_count=8,
            sample_size=8,
            efficiency_score=0.25,
            cost_usd=2.0,
            recommendation_types=["optimization_target"],
        ),
        _ranking_row(
            artifact_id="unresolved",
            artifact_uuid="unresolved",
            workflow_id="",
            identity_confidence=None,
            recommendation_types=["identity_reconciliation"],
        ),
        _ranking_row(
            artifact_id="cold",
            artifact_uuid="cold",
            workflow_id="",
            session_count=1,
            sample_size=1,
            confidence=None,
            recommendation_types=["insufficient_data"],
            evidence={"projectSessionCount": 1, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        ),
        _ranking_row(
            artifact_id="versioned",
            artifact_uuid="versioned",
            workflow_id="",
            version_id="v1",
            success_score=0.92,
            recommendation_types=[],
        ),
        _ranking_row(
            artifact_id="versioned",
            artifact_uuid="versioned",
            workflow_id="",
            version_id="v2",
            success_score=0.65,
            recommendation_types=["version_regression"],
        ),
        _ranking_row(
            artifact_id="swap-current",
            artifact_uuid="swap-current",
            workflow_id="workflow-swap",
            success_score=0.55,
            efficiency_score=0.45,
            recommendation_types=["workflow_specific_swap"],
        ),
        _ranking_row(
            artifact_id="swap-alt",
            artifact_uuid="swap-alt",
            workflow_id="workflow-swap",
            success_score=0.86,
            efficiency_score=0.8,
            recommendation_types=[],
        ),
    ]


class _FakeArtifactRankingRepo:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    async def list_rankings(self, **kwargs):  # noqa: ANN001
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
        offset = int(kwargs.get("offset") or 0)
        limit = int(kwargs.get("limit") or 50)
        return {"rows": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset, "next_cursor": None}


class _CapturingSAMTelemetryClient(SAMTelemetryClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.post_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def _post_batch(self, url: str, events: list[dict]) -> tuple[bool, str | None]:
        self.post_calls.append((url, events))
        return True, None


def _rollup() -> ArtifactUsageRollup:
    return ArtifactUsageRollup.model_validate(
        {
            "schemaVersion": "ccdash-artifact-usage-rollup-v1",
            "generatedAt": "2026-05-07T12:00:00Z",
            "projectSlug": "project-1",
            "skillmeatProjectId": "sm-project",
            "collectionId": "collection-a",
            "period": "30d",
            "artifact": {"definitionType": "skill", "externalId": "skill:expensive-skill", "artifactUuid": "uuid-expensive"},
            "usage": {"exclusiveTokens": 100, "supportingTokens": 25, "sessionCount": 2},
        }
    )


def _artifact_outcome() -> ArtifactOutcomePayload:
    return ArtifactOutcomePayload(
        event_id="5b56afba-9ccb-4d2b-b334-f921d4460209",
        definition_type="skill",
        external_id="skill:frontend-design",
        period_label="30d",
        period_start=datetime(2026, 4, 7, tzinfo=timezone.utc),
        period_end=datetime(2026, 5, 7, tzinfo=timezone.utc),
        execution_count=1,
        success_count=1,
        failure_count=0,
        token_input=10,
        token_output=5,
        cost_usd=0.01,
        duration_ms=1000,
        timestamp=datetime(2026, 5, 7, tzinfo=timezone.utc),
    )


class ArtifactIntelligencePhase6ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_fetch_store_query_cycle_contract(self) -> None:
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            await run_migrations(db)
            repo = SqliteArtifactSnapshotRepository(db)
            client = SkillMeatClient(base_url="http://skillmeat.local")

            with (
                patch(
                    "backend.services.integrations.skillmeat_client.agentic_intelligence_flags.artifact_intelligence_enabled",
                    return_value=True,
                ),
                patch.object(SkillMeatClient, "_request_json", return_value=_snapshot_payload()) as request_mock,
            ):
                snapshot = await client.fetch_project_artifact_snapshot("project-1", "collection-a")

            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            request_mock.assert_called_once_with(
                "/api/v1/projects/project-1/artifact-snapshot",
                {"collection_id": "collection-a"},
            )

            await repo.save_snapshot(snapshot)
            latest = await repo.get_latest_snapshot("project-1")
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest.collection_id, "collection-a")
            self.assertEqual([artifact.artifact_uuid for artifact in latest.artifacts], ["uuid-code-review", "uuid-frontend-design"])

            mapper = ArtifactIdentityMapper(repo, fuzzy_threshold=0.85)
            resolutions = await mapper.resolve_many(
                project_id="project-1",
                observed_artifacts=[
                    {"observed_name": "local-code-review", "ccdash_type": "skill", "observed_uuid": "uuid-code-review", "content_hash": None},
                    {"observed_name": "frontend-design", "ccdash_type": "skill", "observed_uuid": None, "content_hash": None},
                    {"observed_name": "missing-skill", "ccdash_type": "skill", "observed_uuid": None, "content_hash": None},
                ],
                snapshot_artifacts=latest.artifacts,
            )
            self.assertEqual([result.match_tier for result in resolutions], ["tier-1", "tier-2", "unresolved"])

            diagnostics = await repo.get_snapshot_diagnostics("project-1")
            self.assertEqual(diagnostics.artifact_count, 2)
            self.assertEqual(diagnostics.resolved_count, 2)
            self.assertEqual(diagnostics.unresolved_count, 1)
        finally:
            await db.close()

    async def test_rollup_export_posts_additive_contract_to_mock_skillmeat_endpoint(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local")
        rollup = _rollup()

        with patch.object(SkillMeatClient, "_request_json", return_value={"accepted": True}) as request_mock:
            response = await client.post_artifact_usage_rollup(rollup)

        self.assertEqual(response, {"accepted": True})
        request_mock.assert_called_once_with(
            "/api/v1/analytics/artifact-usage-rollups",
            None,
            method="POST",
            body=rollup.rollup_dict(),
        )
        posted_body = request_mock.call_args.kwargs["body"]
        self.assertEqual(posted_body["schemaVersion"], "ccdash-artifact-usage-rollup-v1")
        self.assertIn("usage", posted_body)
        self.assertNotIn("raw_prompt", str(posted_body))

    async def test_ranking_api_contract_applies_supported_filter_combinations(self) -> None:
        repo = _FakeArtifactRankingRepo(
            [
                _ranking_row(),
                _ranking_row(
                    artifact_id="observed-expensive",
                    artifact_uuid="uuid-observed",
                    version_id="v2",
                    workflow_id="workflow-b",
                    user_scope="user-b",
                    recommendation_types=[],
                ),
            ]
        )

        cases = [
            ({"collection": "collection-a"}, 2),
            ({"user": "user-a"}, 1),
            ({"artifact": "uuid-expensive"}, 1),
            ({"version": "v1"}, 1),
            ({"workflow": "workflow-a"}, 1),
            ({"artifact_type": "skill"}, 2),
            ({"recommendation_type": "optimization_target"}, 1),
            (
                {
                    "collection": "collection-a",
                    "user": "user-a",
                    "artifact": "uuid-expensive",
                    "version": "v1",
                    "workflow": "workflow-a",
                    "artifact_type": "skill",
                    "recommendation_type": "optimization_target",
                },
                1,
            ),
        ]

        with patch.object(analytics_router, "get_artifact_ranking_repository", return_value=repo):
            for filters, expected_total in cases:
                with self.subTest(filters=filters):
                    payload = await analytics_router.get_artifact_rankings(
                        project="project-1",
                        collection=filters.get("collection"),
                        user=filters.get("user"),
                        period="30d",
                        artifact=filters.get("artifact"),
                        version=filters.get("version"),
                        workflow=filters.get("workflow"),
                        artifact_type=filters.get("artifact_type"),
                        recommendation_type=filters.get("recommendation_type"),
                        refresh=False,
                        offset=0,
                        limit=50,
                        cursor=None,
                        request_context=_request_context(),
                        core_ports=_core_ports(),
                    )
                    self.assertEqual(payload.total, expected_total)
                    call = repo.calls[-1]
                    self.assertEqual(call["period"], "30d")
                    self.assertEqual(call["collection_id"], filters.get("collection"))
                    self.assertEqual(call["user_scope"], filters.get("user"))
                    self.assertEqual(call["artifact_uuid"], filters.get("artifact"))
                    self.assertEqual(call["version_id"], filters.get("version"))
                    self.assertEqual(call["workflow_id"], filters.get("workflow"))
                    self.assertEqual(call["artifact_type"], filters.get("artifact_type"))
                    self.assertEqual(call["recommendation_type"], filters.get("recommendation_type"))

            payload = await analytics_router.get_artifact_rankings(
                project="project-1",
                collection=None,
                user=None,
                period="30d",
                artifact="observed-expensive",
                version=None,
                workflow=None,
                artifact_type=None,
                recommendation_type=None,
                refresh=False,
                offset=0,
                limit=50,
                cursor=None,
                request_context=_request_context(),
                core_ports=_core_ports(),
            )

        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.rows[0].artifact_id, "observed-expensive")
        self.assertEqual(repo.calls[-2]["artifact_uuid"], "observed-expensive")
        self.assertEqual(repo.calls[-1]["artifact_id"], "observed-expensive")

    async def test_recommendation_api_contract_supports_all_seven_advisory_types(self) -> None:
        repo = _FakeArtifactRankingRepo(_recommendation_fixture_rows())

        with patch.object(analytics_router, "get_artifact_ranking_repository", return_value=repo):
            for recommendation_type in sorted(_ALL_RECOMMENDATION_TYPES):
                with self.subTest(recommendation_type=recommendation_type):
                    payload = await analytics_router.get_artifact_recommendations(
                        project="project-1",
                        recommendation_type=recommendation_type,
                        min_confidence=0.65,
                        period="30d",
                        collection="collection-a",
                        user="user-a",
                        workflow=None,
                        limit=100,
                        request_context=_request_context(),
                        core_ports=_core_ports(),
                    )
                    self.assertGreater(payload.total, 0)
                    self.assertEqual({rec.recommendation_type for rec in payload.recommendations}, {recommendation_type})
                    self.assertTrue(all(rec.next_action for rec in payload.recommendations))

    async def test_existing_artifact_outcome_endpoint_contract_remains_backward_compatible(self) -> None:
        client = _CapturingSAMTelemetryClient(
            endpoint_url="https://sam.example.com/api/v1/analytics/execution-outcomes",
            api_key="secret",
        )
        event = _artifact_outcome()
        ok, error = await client.push_artifact_batch([event], "https://sam.example.com")

        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertEqual(len(client.post_calls), 1)
        url, events = client.post_calls[0]
        self.assertEqual(url, "https://sam.example.com/api/v1/analytics/artifact-outcomes")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["definition_type"], "skill")
        self.assertIn("external_id", events[0])
        self.assertNotIn("schemaVersion", events[0])
        self.assertNotIn("schema_version", events[0])


if __name__ == "__main__":
    unittest.main()
