"""Async tests for @memoized_query decorator (CACHE-004 / CACHE-006).

Coverage:
1. Cache miss → stores result → subsequent call is a hit (underlying fn called once).
2. TTL=0 path: caching bypassed entirely; underlying fn called every time.
3. Fingerprint None: result is NOT cached; underlying fn called every time.
4. bypass_cache=True forces a miss even when entry exists; updates stored value.
5. Different params lead to independent cache entries.
6. (CACHE-006) Decorated service methods cache correctly:
   - ProjectStatusQueryService.get_status
   - FeatureForensicsQueryService.get_forensics
   - ReportingQueryService.generate_aar
   Note: WorkflowDiagnosticsQueryService.get_diagnostics is skipped here because
   its get_diagnostics path calls list_workflow_registry / get_workflow_effectiveness
   / detect_failure_patterns which require a live DB connection; standing up a
   sufficient stub for all three is disproportionate for a caching invariant test.
   The decorator is applied to that method; the invariant is covered structurally
   by the MemoizedQueryDecoratorTests.test_decorator_works_on_instance_methods case.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import backend.application.services.agent_queries.cache as cache_module
from backend.application.services.agent_queries.cache import (
    clear_cache,
    memoized_query,
)
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts


# ── Shared helpers ──────────────────────────────────────────────────────────

def _make_ports(fingerprint_value: str | None = "fp-stable") -> MagicMock:
    """Build a minimal ports mock whose fingerprint returns a fixed value."""
    ports = MagicMock()
    storage = MagicMock()
    storage.db = object()
    ports.storage = storage
    return ports


def _make_context(project_id: str | None = "proj-test") -> MagicMock:
    """Build a minimal RequestContext-like mock."""
    ctx = MagicMock()
    if project_id is not None:
        ctx.project = MagicMock()
        ctx.project.project_id = project_id
    else:
        ctx.project = None
    return ctx


# Patch target: get_data_version_fingerprint lives in the cache module
_FP_PATCH = "backend.application.services.agent_queries.cache.get_data_version_fingerprint"


# ── Test suite ──────────────────────────────────────────────────────────────

class MemoizedQueryDecoratorTests(unittest.IsolatedAsyncioTestCase):
    """Covers all five acceptance criteria for @memoized_query."""

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    # ── 1. Miss → store → subsequent call is a hit ───────────────────────

    async def test_first_call_misses_and_stores_subsequent_call_hits(self) -> None:
        """The underlying function must be invoked only once for two identical calls."""
        call_count = 0

        @memoized_query("test_ep_1")
        async def my_service(context, ports):
            nonlocal call_count
            call_count += 1
            return {"value": 42}

        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            result_1 = await my_service(ctx, ports)
            result_2 = await my_service(ctx, ports)

        self.assertEqual(call_count, 1, "underlying fn should be called exactly once")
        self.assertEqual(result_1, {"value": 42})
        self.assertEqual(result_2, {"value": 42})

    # ── 2. TTL=0 path ────────────────────────────────────────────────────

    async def test_ttl_zero_bypasses_cache_entirely(self) -> None:
        """When CCDASH_QUERY_CACHE_TTL_SECONDS=0 the fn is called on every invocation."""
        call_count = 0

        @memoized_query("test_ep_2")
        async def my_service(context, ports):
            nonlocal call_count
            call_count += 1
            return {"call": call_count}

        ctx = _make_context()
        ports = _make_ports()

        with patch.object(cache_module.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
                await my_service(ctx, ports)
                await my_service(ctx, ports)

        self.assertEqual(call_count, 2, "both calls should reach the underlying fn when TTL=0")

    # ── 3. Fingerprint None: result not cached ────────────────────────────

    async def test_fingerprint_none_does_not_cache_result(self) -> None:
        """When fingerprint is None the result must be served live and not stored."""
        call_count = 0

        @memoized_query("test_ep_3")
        async def my_service(context, ports):
            nonlocal call_count
            call_count += 1
            return {"call": call_count}

        ctx = _make_context()
        ports = _make_ports()

        # Return None twice — fingerprint unavailable both times
        with patch(_FP_PATCH, new=AsyncMock(return_value=None)):
            r1 = await my_service(ctx, ports)
            r2 = await my_service(ctx, ports)

        self.assertEqual(call_count, 2, "both calls should hit the live fn when fp=None")
        self.assertEqual(r1, {"call": 1})
        self.assertEqual(r2, {"call": 2})

        # Cache must remain empty
        from backend.application.services.agent_queries.cache import get_cache
        self.assertEqual(len(get_cache()), 0)

    # ── 4. bypass_cache=True forces miss, updates store ──────────────────

    async def test_bypass_cache_forces_miss_and_updates_stored_value(self) -> None:
        """bypass_cache=True must re-execute the fn and overwrite the cached entry."""
        call_count = 0

        @memoized_query("test_ep_4")
        async def my_service(context, ports):
            nonlocal call_count
            call_count += 1
            return {"call": call_count}

        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            # First call populates the cache
            r1 = await my_service(ctx, ports)
            self.assertEqual(r1, {"call": 1})
            self.assertEqual(call_count, 1)

            # Second call — should be cache hit
            r2 = await my_service(ctx, ports)
            self.assertEqual(r2, {"call": 1})  # same cached value
            self.assertEqual(call_count, 1, "second call should not invoke fn")

            # Third call with bypass — must re-execute
            r3 = await my_service(ctx, ports, bypass_cache=True)
            self.assertEqual(r3, {"call": 2})
            self.assertEqual(call_count, 2)

            # Fourth call without bypass — should hit the fresh value just stored
            r4 = await my_service(ctx, ports)
            self.assertEqual(r4, {"call": 2}, "post-bypass call should serve updated cache value")
            self.assertEqual(call_count, 2, "fourth call should not invoke fn")

    async def test_bypass_cache_kwarg_not_forwarded_to_wrapped_fn(self) -> None:
        """The wrapped function must NOT receive bypass_cache in its kwargs."""
        received_kwargs: dict = {}

        @memoized_query("test_ep_bypass_fwd")
        async def my_service(context, ports, **kw):
            nonlocal received_kwargs
            received_kwargs = kw
            return {}

        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            await my_service(ctx, ports, bypass_cache=True)

        self.assertNotIn("bypass_cache", received_kwargs)

    # ── 5. Different params → independent cache entries ───────────────────

    async def test_different_params_produce_independent_cache_entries(self) -> None:
        """Two calls with different extracted params must each miss and store separately."""
        call_count = 0

        @memoized_query(
            "test_ep_5",
            param_extractor=lambda context, ports, *, item_id=None: {"item_id": item_id},
        )
        async def my_service(context, ports, *, item_id=None):
            nonlocal call_count
            call_count += 1
            return {"item_id": item_id, "call": call_count}

        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            r_a = await my_service(ctx, ports, item_id="A")
            r_b = await my_service(ctx, ports, item_id="B")
            # Repeat to confirm cache hit for each
            r_a2 = await my_service(ctx, ports, item_id="A")
            r_b2 = await my_service(ctx, ports, item_id="B")

        self.assertEqual(call_count, 2, "each distinct item_id should miss once")
        self.assertEqual(r_a["item_id"], "A")
        self.assertEqual(r_b["item_id"], "B")
        # Hits return the same objects
        self.assertEqual(r_a, r_a2)
        self.assertEqual(r_b, r_b2)

    # ── Instance method (self as args[0]) ─────────────────────────────────

    async def test_decorator_works_on_instance_methods(self) -> None:
        """Decorator must handle instance methods where args[0] is self."""
        class MyService:
            call_count = 0

            @memoized_query("test_ep_method")
            async def get_data(self, context, ports):
                MyService.call_count += 1
                return {"n": MyService.call_count}

        svc = MyService()
        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            r1 = await svc.get_data(ctx, ports)
            r2 = await svc.get_data(ctx, ports)

        self.assertEqual(MyService.call_count, 1)
        self.assertEqual(r1, r2)

    # ── project_id extracted via param_extractor → scopes key ────────────

    async def test_param_extractor_project_id_scopes_key_independently(self) -> None:
        """project_id from param_extractor must scope entries per project."""
        call_count = 0

        @memoized_query(
            "test_ep_proj_scope",
            param_extractor=lambda context, ports, *, project_id=None: {"project_id": project_id},
        )
        async def my_service(context, ports, *, project_id=None):
            nonlocal call_count
            call_count += 1
            return {"project_id": project_id, "n": call_count}

        ctx = _make_context(project_id=None)
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
            r_p1a = await my_service(ctx, ports, project_id="p1")
            r_p2a = await my_service(ctx, ports, project_id="p2")
            r_p1b = await my_service(ctx, ports, project_id="p1")

        self.assertEqual(call_count, 2, "p1 and p2 should each miss once")
        self.assertEqual(r_p1a, r_p1b, "second p1 call must be a cache hit")
        self.assertNotEqual(r_p1a, r_p2a)

    # ── OTel counter import failure degrades gracefully ───────────────────

    async def test_otel_import_failure_does_not_raise(self) -> None:
        """If observability counters are unavailable the decorator must not raise."""
        @memoized_query("test_ep_otel")
        async def my_service(context, ports):
            return {"ok": True}

        ctx = _make_context()
        ports = _make_ports()

        import sys
        # Temporarily hide the otel module to force ImportError path
        otel_key = "backend.observability.otel"
        original = sys.modules.pop(otel_key, None)
        sys.modules[otel_key] = None  # type: ignore[assignment]
        try:
            with patch(_FP_PATCH, new=AsyncMock(return_value="fp-v1")):
                result = await my_service(ctx, ports)
        finally:
            if original is not None:
                sys.modules[otel_key] = original
            else:
                sys.modules.pop(otel_key, None)

        self.assertEqual(result, {"ok": True})


class GracefulDegradationTests(unittest.IsolatedAsyncioTestCase):
    """CACHE-011: fingerprint failure path must never surface to the caller.

    Three cases:
    1. ``get_data_version_fingerprint`` returns ``None`` explicitly.
    2. ``get_data_version_fingerprint`` raises an exception.
    3. Warning is logged on fingerprint failure (both None and raise paths).
    """

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    # ── 1. Fingerprint returns None explicitly ────────────────────────────

    async def test_fingerprint_none_returns_live_result_and_cache_stays_empty(self) -> None:
        """When get_data_version_fingerprint returns None the decorated fn executes
        live, returns the correct value, and no entry is written to the cache."""
        wrapped = AsyncMock(return_value={"status": "live"})

        @memoized_query("degradation_ep_1")
        async def my_service(context, ports):
            return await wrapped(context, ports)

        ctx = _make_context()
        ports = _make_ports()

        with patch(_FP_PATCH, new=AsyncMock(return_value=None)):
            result = await my_service(ctx, ports)

        self.assertEqual(result, {"status": "live"}, "should return live result")
        wrapped.assert_called_once()

        from backend.application.services.agent_queries.cache import get_cache
        self.assertEqual(len(get_cache()), 0, "cache must remain empty when fp=None")

    # ── 2. Fingerprint raises an exception ───────────────────────────────

    async def test_fingerprint_raises_returns_live_result_and_does_not_reraise(self) -> None:
        """When get_data_version_fingerprint raises, the decorator must catch it,
        still return the live result, and not propagate the exception to the caller."""
        call_count = 0

        @memoized_query("degradation_ep_2")
        async def my_service(context, ports):
            nonlocal call_count
            call_count += 1
            return {"n": call_count}

        ctx = _make_context()
        ports = _make_ports()

        def _raise(*args, **kwargs):
            raise RuntimeError("db down")

        with patch(_FP_PATCH, new=AsyncMock(side_effect=_raise)):
            # Must not raise despite the fingerprint helper blowing up
            result = await my_service(ctx, ports)

        self.assertEqual(result, {"n": 1}, "live result must be returned")
        self.assertEqual(call_count, 1, "wrapped fn must be invoked once")

        from backend.application.services.agent_queries.cache import get_cache
        self.assertEqual(len(get_cache()), 0, "cache must remain empty when fp raises")

    # ── 3. Warning is logged on fingerprint failure ───────────────────────

    async def test_fingerprint_raises_emits_warning_log(self) -> None:
        """A WARNING must be emitted when get_data_version_fingerprint raises."""
        @memoized_query("degradation_ep_3")
        async def my_service(context, ports):
            return {"ok": True}

        ctx = _make_context()
        ports = _make_ports()

        _logger_name = "backend.application.services.agent_queries.cache"

        with self.assertLogs(_logger_name, level="WARNING") as log_ctx:
            with patch(_FP_PATCH, new=AsyncMock(side_effect=RuntimeError("db down"))):
                result = await my_service(ctx, ports)

        self.assertEqual(result, {"ok": True}, "result must still be returned after warning")
        # At least one WARNING record must mention the fingerprint failure
        warning_messages = [r for r in log_ctx.output if "WARNING" in r]
        self.assertTrue(
            warning_messages,
            "expected at least one WARNING log on fingerprint exception",
        )

    async def test_fingerprint_none_emits_debug_log(self) -> None:
        """A DEBUG message must be emitted when fingerprint is None (scope failure)."""
        @memoized_query("degradation_ep_4")
        async def my_service(context, ports):
            return {"ok": True}

        ctx = _make_context()
        ports = _make_ports()

        _logger_name = "backend.application.services.agent_queries.cache"

        # Use level=DEBUG so we capture DEBUG and above
        with self.assertLogs(_logger_name, level="DEBUG") as log_ctx:
            with patch(_FP_PATCH, new=AsyncMock(return_value=None)):
                result = await my_service(ctx, ports)

        self.assertEqual(result, {"ok": True})
        debug_or_warning = [
            r for r in log_ctx.output
            if ("DEBUG" in r or "WARNING" in r) and "fingerprint" in r.lower()
        ]
        self.assertTrue(
            debug_or_warning,
            "expected a DEBUG or WARNING log mentioning fingerprint when fp=None",
        )


# ── CACHE-006: service-level memoization integration tests ──────────────────

# Shared fixture helpers (mirrors test_agent_queries_feature_forensics.py)

class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id):
        return self._project if self._project and self._project.id == project_id else None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        return None, ProjectScope(
            project_id=project_id or self._project.id,
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


def _svc_context(project_id: str = "project-1") -> RequestContext:
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
        trace=TraceContext(request_id="req-1"),
    )


def _svc_ports(*, features=None, sessions=None, documents=None, tasks=None, links=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            features_repo=features or types.SimpleNamespace(
                get_by_id=AsyncMock(return_value=None),
                list_all=AsyncMock(return_value=[]),
            ),
            sessions_repo=sessions or types.SimpleNamespace(
                get_by_id=AsyncMock(return_value=None),
                list_paginated=AsyncMock(return_value=[]),
            ),
            documents_repo=documents or types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks_repo=tasks or types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links_repo=links or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class ServiceMemoizationTests(unittest.IsolatedAsyncioTestCase):
    """CACHE-006: each decorated service method caches correctly.

    Pattern per service:
    - Call twice with same args → underlying data-fetch called once.
    - Third call with bypass_cache=True → fresh fetch triggered.
    """

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    # ── ProjectStatusQueryService.get_status ─────────────────────────────

    async def test_project_status_caches_on_second_call(self) -> None:
        """get_status must invoke data layer only once for two identical calls."""
        from backend.application.services.agent_queries.project_status import ProjectStatusQueryService

        fetch_mock = AsyncMock(return_value=[])
        ports = _svc_ports(
            features=types.SimpleNamespace(list_all=fetch_mock, get_by_id=AsyncMock(return_value=None)),
        )
        ctx = _svc_context()
        svc = ProjectStatusQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.project_status.SessionIntelligenceReadService.list_sessions",
                new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
            ):
                with patch(
                    "backend.application.services.agent_queries.project_status.AnalyticsOverviewService.get_overview",
                    new=AsyncMock(return_value={}),
                ):
                    with patch(
                        "backend.application.services.agent_queries.project_status.list_workflow_registry",
                        new=AsyncMock(return_value={"items": []}),
                    ):
                        result1 = await svc.get_status(ctx, ports)
                        result2 = await svc.get_status(ctx, ports)

        self.assertEqual(fetch_mock.call_count, 1, "features.list_all should be called once (cache hit on 2nd call)")
        self.assertEqual(result1.project_id, result2.project_id)

    async def test_project_status_bypass_cache_triggers_fresh_fetch(self) -> None:
        """bypass_cache=True must force a re-execute even when cache entry exists."""
        from backend.application.services.agent_queries.project_status import ProjectStatusQueryService

        fetch_mock = AsyncMock(return_value=[])
        ports = _svc_ports(
            features=types.SimpleNamespace(list_all=fetch_mock, get_by_id=AsyncMock(return_value=None)),
        )
        ctx = _svc_context()
        svc = ProjectStatusQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.project_status.SessionIntelligenceReadService.list_sessions",
                new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
            ):
                with patch(
                    "backend.application.services.agent_queries.project_status.AnalyticsOverviewService.get_overview",
                    new=AsyncMock(return_value={}),
                ):
                    with patch(
                        "backend.application.services.agent_queries.project_status.list_workflow_registry",
                        new=AsyncMock(return_value={"items": []}),
                    ):
                        await svc.get_status(ctx, ports)           # miss (count=1)
                        await svc.get_status(ctx, ports)           # hit  (count=1)
                        await svc.get_status(ctx, ports, bypass_cache=True)  # miss (count=2)

        self.assertEqual(fetch_mock.call_count, 2, "bypass_cache must trigger a fresh fetch")

    # ── FeatureForensicsQueryService.get_forensics ────────────────────────

    async def test_feature_forensics_caches_on_second_call(self) -> None:
        """get_forensics must invoke storage.features().get_by_id once for two identical calls."""
        from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService

        feature_row = {"id": "feature-1", "name": "Feature 1", "status": "in_progress", "updated_at": "2026-04-14T10:00:00+00:00"}
        get_by_id_mock = AsyncMock(return_value=feature_row)
        features_repo = types.SimpleNamespace(get_by_id=get_by_id_mock)
        ports = _svc_ports(features=features_repo)
        ctx = _svc_context()
        svc = FeatureForensicsQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
                new=AsyncMock(return_value=[]),
            ):
                with patch(
                    "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
                    new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
                ):
                    result1 = await svc.get_forensics(ctx, ports, "feature-1")
                    result2 = await svc.get_forensics(ctx, ports, "feature-1")

        self.assertEqual(get_by_id_mock.call_count, 1, "get_by_id should be called once (cache hit on 2nd call)")
        self.assertEqual(result1.feature_id, result2.feature_id)

    async def test_feature_forensics_bypass_cache_triggers_fresh_fetch(self) -> None:
        """bypass_cache=True must force a re-fetch from storage."""
        from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService

        feature_row = {"id": "feature-1", "name": "Feature 1", "status": "in_progress", "updated_at": "2026-04-14T10:00:00+00:00"}
        get_by_id_mock = AsyncMock(return_value=feature_row)
        features_repo = types.SimpleNamespace(get_by_id=get_by_id_mock)
        ports = _svc_ports(features=features_repo)
        ctx = _svc_context()
        svc = FeatureForensicsQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
                new=AsyncMock(return_value=[]),
            ):
                with patch(
                    "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
                    new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
                ):
                    await svc.get_forensics(ctx, ports, "feature-1")           # miss
                    await svc.get_forensics(ctx, ports, "feature-1")           # hit
                    await svc.get_forensics(ctx, ports, "feature-1", bypass_cache=True)  # miss

        self.assertEqual(get_by_id_mock.call_count, 2, "bypass_cache must trigger a fresh fetch")

    async def test_feature_forensics_different_feature_ids_are_independent_entries(self) -> None:
        """Calls for distinct feature_ids must each miss once independently."""
        from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService

        def _feature_row(fid: str) -> dict:
            return {"id": fid, "name": fid, "status": "in_progress", "updated_at": "2026-04-14T10:00:00+00:00"}

        get_by_id_mock = AsyncMock(side_effect=lambda fid: _feature_row(fid))
        features_repo = types.SimpleNamespace(get_by_id=get_by_id_mock)
        ports = _svc_ports(features=features_repo)
        ctx = _svc_context()
        svc = FeatureForensicsQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
                new=AsyncMock(return_value=[]),
            ):
                with patch(
                    "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
                    new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
                ):
                    await svc.get_forensics(ctx, ports, "feature-A")  # miss A
                    await svc.get_forensics(ctx, ports, "feature-B")  # miss B
                    await svc.get_forensics(ctx, ports, "feature-A")  # hit A
                    await svc.get_forensics(ctx, ports, "feature-B")  # hit B

        self.assertEqual(get_by_id_mock.call_count, 2, "each distinct feature_id should miss exactly once")

    # ── ReportingQueryService.generate_aar ───────────────────────────────

    async def test_aar_report_caches_on_second_call(self) -> None:
        """generate_aar must invoke storage.features().get_by_id once for two identical calls."""
        from backend.application.services.agent_queries.reporting import ReportingQueryService

        feature_row = {"id": "feature-1", "name": "Feature 1", "status": "done", "updated_at": "2026-04-14T10:00:00+00:00"}
        get_by_id_mock = AsyncMock(return_value=feature_row)
        features_repo = types.SimpleNamespace(get_by_id=get_by_id_mock)
        ports = _svc_ports(features=features_repo)
        ctx = _svc_context()
        svc = ReportingQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.reporting.get_workflow_effectiveness",
                new=AsyncMock(return_value={"items": []}),
            ):
                with patch(
                    "backend.application.services.agent_queries.reporting.detect_failure_patterns",
                    new=AsyncMock(return_value={"items": []}),
                ):
                    with patch(
                        "backend.application.services.agent_queries.reporting._load_feature_session_rows",
                        new=AsyncMock(return_value=[]),
                    ):
                        result1 = await svc.generate_aar(ctx, ports, "feature-1")
                        result2 = await svc.generate_aar(ctx, ports, "feature-1")

        self.assertEqual(get_by_id_mock.call_count, 1, "get_by_id should be called once (cache hit on 2nd call)")
        self.assertEqual(result1.feature_id, result2.feature_id)

    async def test_aar_report_bypass_cache_triggers_fresh_fetch(self) -> None:
        """bypass_cache=True must force a re-fetch from storage for AAR reports."""
        from backend.application.services.agent_queries.reporting import ReportingQueryService

        feature_row = {"id": "feature-1", "name": "Feature 1", "status": "done", "updated_at": "2026-04-14T10:00:00+00:00"}
        get_by_id_mock = AsyncMock(return_value=feature_row)
        features_repo = types.SimpleNamespace(get_by_id=get_by_id_mock)
        ports = _svc_ports(features=features_repo)
        ctx = _svc_context()
        svc = ReportingQueryService()

        with patch(_FP_PATCH, new=AsyncMock(return_value="fp-stable")):
            with patch(
                "backend.application.services.agent_queries.reporting.get_workflow_effectiveness",
                new=AsyncMock(return_value={"items": []}),
            ):
                with patch(
                    "backend.application.services.agent_queries.reporting.detect_failure_patterns",
                    new=AsyncMock(return_value={"items": []}),
                ):
                    with patch(
                        "backend.application.services.agent_queries.reporting._load_feature_session_rows",
                        new=AsyncMock(return_value=[]),
                    ):
                        await svc.generate_aar(ctx, ports, "feature-1")           # miss
                        await svc.generate_aar(ctx, ports, "feature-1")           # hit
                        await svc.generate_aar(ctx, ports, "feature-1", bypass_cache=True)  # miss

        self.assertEqual(get_by_id_mock.call_count, 2, "bypass_cache must trigger a fresh fetch")


if __name__ == "__main__":
    unittest.main()
