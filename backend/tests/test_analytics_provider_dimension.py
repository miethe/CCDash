"""Tests for the T-002 provider dimension wired into /api/analytics/{breakdown,series,artifacts}.

Uses lightweight fakes mirroring backend/tests/test_analytics_router.py's CorePorts wiring
so this file stays self-contained.
"""
import types
import unittest
from pathlib import Path

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.routers import analytics as analytics_router


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
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


_SESSION_ROWS = [
    {
        "id": "S-1",
        "model": "claude-opus-4-5-20251101",
        "platform_type": "Claude Code",
        "launcher": "",
        "model_variant": "",
        "started_at": "2026-03-01T09:00:00Z",
        "session_type": "session",
        "tokens_in": 100,
        "tokens_out": 50,
        "model_io_tokens": 150,
        "cache_input_tokens": 0,
        "observed_tokens": 150,
        "tool_reported_tokens": 150,
        "total_cost": 1.0,
    },
    {
        "id": "S-2",
        "model": "gpt-5.6-terra",
        "platform_type": "Codex",
        "launcher": "",
        "model_variant": "",
        "started_at": "2026-03-01T10:00:00Z",
        "session_type": "session",
        "tokens_in": 0,
        "tokens_out": 0,
        "model_io_tokens": 0,
        "cache_input_tokens": 0,
        "observed_tokens": 0,
        "tool_reported_tokens": 0,
        "total_cost": 0.0,
    },
    {
        "id": "S-3",
        "model": "claude-sonnet-5",
        "platform_type": "Claude Code",
        "launcher": "ica-claude",
        "model_variant": "",
        "started_at": "2026-03-01T11:00:00Z",
        "session_type": "session",
        "tokens_in": 40,
        "tokens_out": 20,
        "model_io_tokens": 60,
        "cache_input_tokens": 0,
        "observed_tokens": 60,
        "tool_reported_tokens": 60,
        "total_cost": 0.2,
    },
]


class _FakeSessionRepo:
    async def list_paginated(self, *args, **kwargs):
        return list(_SESSION_ROWS)

    async def get_many_by_ids(self, ids, project_id=None, *, workspace_id="default-local"):
        return {row["id"]: row for row in _SESSION_ROWS if row["id"] in set(ids)}

    async def get_tool_usage(self, session_id):
        return []


class _FakeEntityLinkRepo:
    async def get_links_for(self, entity_type, entity_id, relation):
        return []


class _FakeAnalyticsRepoForArtifacts:
    async def list_artifact_analytics_rows(self, **kwargs):
        return {
            "artifact_rows": [
                {
                    "session_id": "S-1",
                    "feature_id": "",
                    "model": "claude-opus-4-5-20251101",
                    "tool_name": "Write",
                    "agent": "",
                    "skill": "",
                    "status": "created",
                    "occurred_at": "2026-03-01T09:05:00Z",
                    "payload_json": '{"type": "component"}',
                },
                {
                    "session_id": "S-2",
                    "feature_id": "",
                    "model": "gpt-5.6-terra",
                    "tool_name": "Write",
                    "agent": "",
                    "skill": "",
                    "status": "created",
                    "occurred_at": "2026-03-01T10:05:00Z",
                    "payload_json": '{"type": "component"}',
                },
            ],
            "lifecycle_rows": [
                {
                    "session_id": "S-1",
                    "feature_id": "",
                    "model": "claude-opus-4-5-20251101",
                    "status": "completed",
                    "occurred_at": "2026-03-01T09:10:00Z",
                    "token_input": 100,
                    "token_output": 50,
                    "cost_usd": 1.0,
                    "payload_json": "{}",
                },
                {
                    "session_id": "S-2",
                    "feature_id": "",
                    "model": "gpt-5.6-terra",
                    "status": "completed",
                    "occurred_at": "2026-03-01T10:10:00Z",
                    "token_input": 0,
                    "token_output": 0,
                    "cost_usd": 0.0,
                    "payload_json": "{}",
                },
            ],
            "feature_link_rows": [],
            "feature_rows": [],
            "command_rows": [],
            "agent_rows": [],
        }


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


class _FakeStorage:
    def __init__(self, *, session_repo=None, link_repo=None, analytics_repo=None):
        self.db = object()
        self._session_repo = session_repo
        self._link_repo = link_repo
        self._analytics_repo = analytics_repo

    def sessions(self):
        return self._session_repo

    def entity_links(self):
        return self._link_repo

    def analytics(self):
        return self._analytics_repo


def _core_ports(*, session_repo=None, link_repo=None, analytics_repo=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(project),
        storage=_FakeStorage(session_repo=session_repo, link_repo=link_repo, analytics_repo=analytics_repo),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class BreakdownProviderDimensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_dimension_keys_by_provider_label(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), link_repo=_FakeEntityLinkRepo())
        response = await analytics_router.get_breakdown(
            dimension="provider",
            request_context=_request_context(),
            core_ports=ports,
        )
        names = {item["name"] for item in response["items"]}
        self.assertIn("Anthropic · Claude Code", names)
        self.assertIn("OpenAI · Codex", names)
        self.assertIn("Anthropic · Claude Code · ICA", names)

    async def test_provider_vendor_dimension(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), link_repo=_FakeEntityLinkRepo())
        response = await analytics_router.get_breakdown(
            dimension="provider_vendor",
            request_context=_request_context(),
            core_ports=ports,
        )
        by_name = {item["name"]: item for item in response["items"]}
        self.assertEqual(by_name["Anthropic"]["count"], 2)
        self.assertEqual(by_name["OpenAI"]["count"], 1)
        # Zero-token Codex session must still surface as a real zero-token row, not be hidden.
        self.assertEqual(by_name["OpenAI"]["tokens"], 0)

    async def test_provider_surface_dimension(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), link_repo=_FakeEntityLinkRepo())
        response = await analytics_router.get_breakdown(
            dimension="provider_surface",
            request_context=_request_context(),
            core_ports=ports,
        )
        names = {item["name"] for item in response["items"]}
        self.assertEqual(names, {"Claude Code", "Codex"})

    async def test_provider_channel_dimension(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), link_repo=_FakeEntityLinkRepo())
        response = await analytics_router.get_breakdown(
            dimension="provider_channel",
            request_context=_request_context(),
            core_ports=ports,
        )
        by_name = {item["name"]: item for item in response["items"]}
        self.assertEqual(by_name["unknown"]["count"], 2)
        self.assertEqual(by_name["ica"]["count"], 1)


class SeriesProviderGroupByTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_tokens_series_groups_by_provider_vendor(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo())
        response = await analytics_router.get_series(
            metric="session_tokens",
            period="daily",
            group_by="provider_vendor",
            request_context=_request_context(),
            core_ports=ports,
        )
        groups = {item["metadata"]["provider_vendor"] for item in response["items"]}
        self.assertEqual(groups, {"Anthropic", "OpenAI"})


class ArtifactsByProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_by_provider_row_shape_mirrors_by_model(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), analytics_repo=_FakeAnalyticsRepoForArtifacts())
        response = await analytics_router.get_artifacts(
            artifact_type=None,
            model=None,
            model_family=None,
            tool=None,
            feature_id=None,
            limit=120,
            request_context=_request_context(),
            core_ports=ports,
        )
        by_provider = response["tokenUsage"]["byProvider"]
        self.assertTrue(by_provider, "expected byProvider rows")
        row = next(r for r in by_provider if r["provider"] == "Anthropic · Claude Code")
        self.assertEqual(row["providerVendor"], "Anthropic")
        self.assertEqual(row["providerSurface"], "Claude Code")
        self.assertEqual(row["providerChannel"], "unknown")
        self.assertEqual(row["providerId"], "anthropic:claude-code:unknown")
        self.assertEqual(row["tokenInput"], 100)
        self.assertEqual(row["tokenOutput"], 50)
        self.assertEqual(row["totalTokens"], 150)
        # byModel row shape parity: same numeric/aggregate keys present.
        by_model = response["tokenUsage"]["byModel"]
        model_row = next(r for r in by_model if r["model"] == "claude-opus-4-5")
        for key in ("artifactCount", "sessions", "artifactTypes", "tokenInput", "tokenOutput", "totalTokens", "totalCost"):
            self.assertIn(key, row)
            self.assertIn(key, model_row)

    async def test_by_provider_covers_zero_token_openai_row(self) -> None:
        ports = _core_ports(session_repo=_FakeSessionRepo(), analytics_repo=_FakeAnalyticsRepoForArtifacts())
        response = await analytics_router.get_artifacts(
            artifact_type=None,
            model=None,
            model_family=None,
            tool=None,
            feature_id=None,
            limit=120,
            request_context=_request_context(),
            core_ports=ports,
        )
        by_provider = response["tokenUsage"]["byProvider"]
        row = next(r for r in by_provider if r["providerVendor"] == "OpenAI")
        self.assertEqual(row["tokenInput"], 0)
        self.assertEqual(row["tokenOutput"], 0)
        self.assertEqual(row["totalTokens"], 0)


if __name__ == "__main__":
    unittest.main()
