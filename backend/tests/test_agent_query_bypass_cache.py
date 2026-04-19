"""Handler-level tests for bypass_cache end-to-end wiring (CACHE-007).

Coverage:
1. ``GET /api/agent/feature-forensics/{feature_id}`` handler — cache miss on
   first call, cache hit on second call, forced miss on third call with
   ``bypass_cache=True``.  Uses the same fixture style as
   ``test_feature_forensics_endpoint_agreement.py``.

2. CLI ``--no-cache`` flag — verifies that ``ccdash feature show --no-cache``
   and ``ccdash feature sessions --no-cache`` include ``bypass_cache=true`` in
   the HTTP request params.  Follows the ``test_commands.py`` harness.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.routers.agent import get_feature_forensics


# ---------------------------------------------------------------------------
# Shared test infrastructure (mirrors test_feature_forensics_endpoint_agreement.py)
# ---------------------------------------------------------------------------

_FP_PATCH = "backend.application.services.agent_queries.cache.get_data_version_fingerprint"


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id):
        if self._project and getattr(self._project, "id", "") == project_id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        resolved_id = project_id or self._project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self._project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, features_repo, sessions_repo, documents_repo, tasks_repo, links_repo):
        self.db = object()
        self._features_repo = features_repo
        self._sessions_repo = sessions_repo
        self._documents_repo = documents_repo
        self._tasks_repo = tasks_repo
        self._links_repo = links_repo
        self._session_messages_repo = types.SimpleNamespace(list_by_session=AsyncMock(return_value=[]))

    def features(self):
        return self._features_repo

    def sessions(self):
        return self._sessions_repo

    def documents(self):
        return self._documents_repo

    def tasks(self):
        return self._tasks_repo

    def entity_links(self):
        return self._links_repo

    def session_messages(self):
        return self._session_messages_repo


def _context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
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
        trace=TraceContext(request_id="req-bypass-1"),
    )


def _ports(*, features=None, sessions=None, documents=None, tasks=None, links=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            features_repo=features or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            sessions_repo=sessions or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            documents_repo=documents or types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks_repo=tasks or types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links_repo=links or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_FEATURE_ID = "feat-bypass-007"

_FEATURE_ROW = {
    "id": _FEATURE_ID,
    "name": "Bypass Cache Feature",
    "feature_slug": "bypass-cache-feature",
    "status": "in_progress",
    "updated_at": "2026-04-14T10:00:00+00:00",
}


# ---------------------------------------------------------------------------
# Handler-level bypass_cache tests
# ---------------------------------------------------------------------------


class FeatureForensicsHandlerBypassCacheTests(unittest.IsolatedAsyncioTestCase):
    """Verify that bypass_cache=True on the REST handler forces a fresh fetch.

    Pattern:
    1. Call 1 (bypass_cache=False) — cache miss; underlying get_by_id called once.
    2. Call 2 (bypass_cache=False) — cache hit; get_by_id NOT called again.
    3. Call 3 (bypass_cache=True)  — forced miss; get_by_id called a second time.
    """

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    async def _call_handler(self, *, bypass_cache: bool = False):
        """Invoke the agent router handler directly."""
        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            with patch(
                "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
                new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
            ):
                return await get_feature_forensics(
                    feature_id=_FEATURE_ID,
                    bypass_cache=bypass_cache,
                    request_context=self._ctx,
                    core_ports=self._ports,
                )

    async def asyncSetUp(self) -> None:
        self._get_by_id_mock = AsyncMock(return_value=_FEATURE_ROW)
        features_repo = types.SimpleNamespace(get_by_id=self._get_by_id_mock)
        self._ctx = _context()
        self._ports = _ports(
            features=features_repo,
            sessions=types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            documents=types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks=types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links=types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        )

    async def test_first_call_is_cache_miss(self) -> None:
        """First call with bypass_cache=False must invoke the underlying data fetch."""
        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            result = await self._call_handler(bypass_cache=False)

        self.assertEqual(self._get_by_id_mock.call_count, 1, "first call must be a miss")
        self.assertEqual(result.feature_id, _FEATURE_ID)

    async def test_second_call_is_cache_hit(self) -> None:
        """Second identical call must be served from cache (get_by_id called only once)."""
        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            await self._call_handler(bypass_cache=False)
            await self._call_handler(bypass_cache=False)

        self.assertEqual(
            self._get_by_id_mock.call_count,
            1,
            "second call should be a cache hit — get_by_id must not be called again",
        )

    async def test_third_call_with_bypass_cache_forces_fresh_fetch(self) -> None:
        """bypass_cache=True on the third call must skip cache and call get_by_id again."""
        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            await self._call_handler(bypass_cache=False)  # miss  → count=1
            await self._call_handler(bypass_cache=False)  # hit   → count=1
            result = await self._call_handler(bypass_cache=True)  # miss  → count=2

        self.assertEqual(
            self._get_by_id_mock.call_count,
            2,
            "bypass_cache=True must force a fresh fetch from the data layer",
        )
        self.assertEqual(result.feature_id, _FEATURE_ID)

    async def test_call_after_bypass_serves_updated_cache_value(self) -> None:
        """A normal call immediately after bypass_cache=True must be a cache hit."""
        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            await self._call_handler(bypass_cache=False)  # miss  → count=1
            await self._call_handler(bypass_cache=True)   # miss  → count=2
            await self._call_handler(bypass_cache=False)  # hit   → count=2

        self.assertEqual(
            self._get_by_id_mock.call_count,
            2,
            "call after bypass must hit the refreshed cache entry",
        )


# ---------------------------------------------------------------------------
# CLI --no-cache flag tests
# ---------------------------------------------------------------------------


try:
    import pytest  # noqa: F401
    from typer.testing import CliRunner
    from ccdash_cli.main import app
    from ccdash_cli.runtime.config import TargetConfig

    _CLI_AVAILABLE = True
except ImportError:
    _CLI_AVAILABLE = False


@unittest.skipUnless(_CLI_AVAILABLE, "ccdash_cli package not importable in this environment")
class FeatureShowNoCacheFlagTests(unittest.TestCase):
    """Verify --no-cache flag causes bypass_cache=true to be sent in the HTTP params."""

    def setUp(self) -> None:
        self.runner = CliRunner()
        self.target = TargetConfig(
            name="local",
            url="http://localhost:8000",
            token=None,
            is_implicit_local=True,
        )

    def _make_client(self) -> MagicMock:
        """Build a mock CCDashClient that records calls."""
        client = MagicMock()
        client.get.return_value = {
            "status": "ok",
            "data": {
                "feature_slug": "bypass-feature",
                "id": _FEATURE_ID,
                "name": "Bypass Feature",
                "status": "active",
                "linked_sessions": [],
                "linked_documents": [],
            },
            "meta": {},
        }
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_feature_show_no_cache_sends_bypass_cache_param(self) -> None:
        """ccdash feature show --no-cache must include bypass_cache=true in GET params."""
        client = self._make_client()

        with (
            patch("ccdash_cli.commands.feature.resolve_target", return_value=self.target),
            patch("ccdash_cli.commands.feature.build_client", return_value=client),
        ):
            result = self.runner.invoke(app, ["feature", "show", _FEATURE_ID, "--no-cache"])

        assert result.exit_code == 0, result.output
        client.get.assert_called_once()
        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})
        assert params and params.get("bypass_cache") == "true", (
            f"Expected bypass_cache=true in GET params, got: {params}"
        )

    def test_feature_show_without_no_cache_omits_bypass_param(self) -> None:
        """ccdash feature show without --no-cache must NOT include bypass_cache."""
        client = self._make_client()

        with (
            patch("ccdash_cli.commands.feature.resolve_target", return_value=self.target),
            patch("ccdash_cli.commands.feature.build_client", return_value=client),
        ):
            result = self.runner.invoke(app, ["feature", "show", _FEATURE_ID])

        assert result.exit_code == 0, result.output
        client.get.assert_called_once()
        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or {}
        assert "bypass_cache" not in (params or {}), (
            f"bypass_cache must be absent when --no-cache is not set, got: {params}"
        )

    def test_feature_sessions_no_cache_sends_bypass_cache_param(self) -> None:
        """ccdash feature sessions --no-cache must include bypass_cache=true in GET params."""
        client = MagicMock()
        client.get.return_value = {
            "status": "ok",
            "data": {"sessions": [], "total": 0, "feature_id": _FEATURE_ID, "feature_slug": "bypass-feature"},
            "meta": {},
        }
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with (
            patch("ccdash_cli.commands.feature.resolve_target", return_value=self.target),
            patch("ccdash_cli.commands.feature.build_client", return_value=client),
        ):
            result = self.runner.invoke(app, ["feature", "sessions", _FEATURE_ID, "--no-cache"])

        assert result.exit_code == 0, result.output
        client.get.assert_called_once()
        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or {}
        assert params.get("bypass_cache") == "true", (
            f"Expected bypass_cache=true in GET params, got: {params}"
        )


if __name__ == "__main__":
    unittest.main()
