"""Tests for FeatureEvidenceSummaryService cache integration.

Covers:
- Cache key format: ``feature-evidence-summary:{project_id}:{param_hash}:{fp}``
- Service returns ``ok`` result for a known feature (mocked repos, cache bypassed via TTL=0)
- Service returns ``error`` when feature row is absent
- Cache is populated on a live call when fingerprint is available
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import (
    clear_cache,
    compute_cache_key,
    get_cache,
)
from backend.application.services.agent_queries.feature_evidence_summary import (
    FeatureEvidenceSummaryService,
)


# ---------------------------------------------------------------------------
# Shared test doubles
# ---------------------------------------------------------------------------


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
            root_path=Path("/tmp/test-project"),
            sessions_dir=Path("/tmp/test-project/sessions"),
            docs_dir=Path("/tmp/test-project/docs"),
            progress_dir=Path("/tmp/test-project/progress"),
        )


class _Storage:
    def __init__(
        self,
        *,
        features_repo,
        sessions_repo,
        links_repo,
        db=None,
    ):
        self.db = db or object()
        self._features_repo = features_repo
        self._sessions_repo = sessions_repo
        self._links_repo = links_repo

    def features(self):
        return self._features_repo

    def sessions(self):
        return self._sessions_repo

    def entity_links(self):
        return self._links_repo


def _context(project_id: str = "proj-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Test Project",
            root_path=Path("/tmp/test-project"),
            sessions_dir=Path("/tmp/test-project/sessions"),
            docs_dir=Path("/tmp/test-project/docs"),
            progress_dir=Path("/tmp/test-project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-test"),
    )


def _ports(
    *,
    features=None,
    sessions=None,
    links=None,
    db=None,
) -> CorePorts:
    project = types.SimpleNamespace(id="proj-1", name="Test Project")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            features_repo=features
            or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            sessions_repo=sessions
            or types.SimpleNamespace(get_many_by_ids=AsyncMock(return_value={})),
            links_repo=links
            or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
            db=db,
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Cache key format tests (pure unit — no I/O)
# ---------------------------------------------------------------------------


class TestCacheKeyFormat(unittest.TestCase):
    """Verify the cache key format expected by FeatureEvidenceSummaryService."""

    def test_key_prefix_is_feature_evidence_summary(self) -> None:
        key = compute_cache_key(
            "feature-evidence-summary",
            "proj-1",
            {"feature_id": "FEAT-42"},
            "fp123",
        )
        self.assertTrue(
            key.startswith("feature-evidence-summary:"),
            f"Expected key to start with 'feature-evidence-summary:'; got: {key!r}",
        )

    def test_key_encodes_project_scope(self) -> None:
        key_a = compute_cache_key(
            "feature-evidence-summary",
            "proj-A",
            {"feature_id": "FEAT-1"},
            "fp",
        )
        key_b = compute_cache_key(
            "feature-evidence-summary",
            "proj-B",
            {"feature_id": "FEAT-1"},
            "fp",
        )
        self.assertNotEqual(key_a, key_b)

    def test_key_encodes_feature_id(self) -> None:
        key_a = compute_cache_key(
            "feature-evidence-summary",
            "proj-1",
            {"feature_id": "FEAT-1"},
            "fp",
        )
        key_b = compute_cache_key(
            "feature-evidence-summary",
            "proj-1",
            {"feature_id": "FEAT-2"},
            "fp",
        )
        self.assertNotEqual(key_a, key_b)

    def test_key_encodes_fingerprint(self) -> None:
        key_a = compute_cache_key(
            "feature-evidence-summary", "proj-1", {"feature_id": "FEAT-1"}, "fp-v1"
        )
        key_b = compute_cache_key(
            "feature-evidence-summary", "proj-1", {"feature_id": "FEAT-1"}, "fp-v2"
        )
        self.assertNotEqual(key_a, key_b)

    def test_key_has_four_colon_separated_segments(self) -> None:
        key = compute_cache_key(
            "feature-evidence-summary", "proj-1", {"feature_id": "FEAT-1"}, "fp"
        )
        # Format: endpoint:scope:param_hash:fingerprint  — endpoint may itself
        # contain hyphens but the last three segments are colon-separated.
        parts = key.split(":")
        self.assertGreaterEqual(len(parts), 4)


# ---------------------------------------------------------------------------
# Service behaviour tests (async, cache bypassed via TTL=0 env patch)
# ---------------------------------------------------------------------------


class TestFeatureEvidenceSummaryServiceCacheBypassed(unittest.IsolatedAsyncioTestCase):
    """Call the service with TTL=0 so the cache decorator is a no-op.

    This isolates the service logic from the cache without needing a real DB
    for fingerprinting.
    """

    def setUp(self) -> None:
        clear_cache()

    async def test_returns_ok_for_known_feature(self) -> None:
        feature_row = {
            "id": "FEAT-1",
            "name": "Evidence Feature",
            "status": "in_progress",
            "updated_at": "2026-04-01T10:00:00+00:00",
        }
        session_row = {
            "id": "sess-1",
            "status": "completed",
            "started_at": "2026-04-01T09:00:00+00:00",
            "ended_at": "2026-04-01T09:30:00+00:00",
            "total_cost": 1.5,
            "observed_tokens": 300,
        }
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=feature_row)
        )
        sessions_repo = types.SimpleNamespace(
            get_many_by_ids=AsyncMock(return_value={"sess-1": session_row})
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[
                    {
                        "source_type": "feature",
                        "source_id": "FEAT-1",
                        "target_type": "session",
                        "target_id": "sess-1",
                    }
                ]
            )
        )
        ports = _ports(features=features_repo, sessions=sessions_repo, links=links_repo)

        with patch("backend.application.services.agent_queries.cache.config") as cfg:
            cfg.CCDASH_QUERY_CACHE_TTL_SECONDS = 0
            result = await FeatureEvidenceSummaryService().get_summary(
                _context(), ports, "FEAT-1"
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.feature_id, "FEAT-1")
        self.assertEqual(result.session_count, 1)
        self.assertEqual(result.total_cost, 1.5)

    async def test_returns_error_when_feature_missing(self) -> None:
        with patch("backend.application.services.agent_queries.cache.config") as cfg:
            cfg.CCDASH_QUERY_CACHE_TTL_SECONDS = 0
            result = await FeatureEvidenceSummaryService().get_summary(
                _context(), _ports(), "FEAT-MISSING"
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.feature_id, "FEAT-MISSING")

    async def test_returns_partial_when_links_fail(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={"id": "FEAT-1", "name": "F1", "status": "active"}
            )
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(side_effect=RuntimeError("links unavailable"))
        )
        with patch("backend.application.services.agent_queries.cache.config") as cfg:
            cfg.CCDASH_QUERY_CACHE_TTL_SECONDS = 0
            with patch(
                "backend.application.services.session_intelligence."
                "SessionIntelligenceReadService.list_sessions",
                new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
            ):
                result = await FeatureEvidenceSummaryService().get_summary(
                    _context(), _ports(features=features_repo, links=links_repo), "FEAT-1"
                )

        self.assertEqual(result.status, "partial")

    async def test_no_error_status_cached_when_ttl_zero(self) -> None:
        """With TTL=0 the decorator bypasses the cache entirely — nothing stored."""
        with patch("backend.application.services.agent_queries.cache.config") as cfg:
            cfg.CCDASH_QUERY_CACHE_TTL_SECONDS = 0
            await FeatureEvidenceSummaryService().get_summary(
                _context(), _ports(), "FEAT-MISSING"
            )

        self.assertEqual(len(get_cache()), 0, "Cache must be empty when TTL=0")


# ---------------------------------------------------------------------------
# Cache population test (fingerprint stubbed)
# ---------------------------------------------------------------------------


class TestFeatureEvidenceSummaryServiceCachePopulation(unittest.IsolatedAsyncioTestCase):
    """Verify that a successful call populates the cache when TTL > 0."""

    def setUp(self) -> None:
        clear_cache()

    async def test_result_stored_in_cache_on_first_call(self) -> None:
        feature_row = {
            "id": "FEAT-2",
            "name": "Cached Feature",
            "status": "active",
            "updated_at": "2026-04-02T08:00:00+00:00",
        }
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=feature_row)
        )
        sessions_repo = types.SimpleNamespace(
            get_many_by_ids=AsyncMock(return_value={})
        )
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.cache.get_data_version_fingerprint",
            new=AsyncMock(return_value="fp-stable"),
        ):
            result = await FeatureEvidenceSummaryService().get_summary(
                _context(), ports, "FEAT-2"
            )

        self.assertIn(result.status, {"ok", "partial"})
        # At least one cache entry should have been written
        self.assertGreater(len(get_cache()), 0)

    async def test_second_call_hits_cache(self) -> None:
        feature_row = {
            "id": "FEAT-3",
            "name": "Hit Feature",
            "status": "active",
            "updated_at": "2026-04-02T08:00:00+00:00",
        }
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=feature_row)
        )
        sessions_repo = types.SimpleNamespace(
            get_many_by_ids=AsyncMock(return_value={})
        )
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, links=links_repo)
        svc = FeatureEvidenceSummaryService()

        with patch(
            "backend.application.services.agent_queries.cache.get_data_version_fingerprint",
            new=AsyncMock(return_value="fp-stable"),
        ):
            first = await svc.get_summary(_context(), ports, "FEAT-3")
            # Reset call count to detect whether repos are hit again
            features_repo.get_by_id.reset_mock()
            links_repo.get_links_for.reset_mock()

            second = await svc.get_summary(_context(), ports, "FEAT-3")

        self.assertEqual(first.feature_id, second.feature_id)
        self.assertEqual(first.status, second.status)
        # Repos should NOT have been called again on the cache-hit path
        features_repo.get_by_id.assert_not_called()
        links_repo.get_links_for.assert_not_called()
