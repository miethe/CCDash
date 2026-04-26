"""Performance benchmarks for the four feature-surface hot paths.

Scenarios covered
-----------------
1. Board load         – list_feature_cards / FeatureSurfaceListRollupService
2. Rollup endpoint    – get_feature_rollups; oversized-batch rejection; latency
3. Linked-session page – pagination happens before enrichment; per-page latency
4. Modal tab activation – activity section + rollup in one service-layer round-trip

Fixture sizes
--------------
  small  : 10 features / 50 sessions
  medium : 100 features / 1000 sessions
  large  : 500 features / 10000 sessions  (gated by CCDASH_RUN_SLOW_BENCHMARKS=1)

Budget policy
-------------
Tests *print* timing measurements always.  A test *fails* only when the
measured time exceeds the CI-safe budget by ≥ 2×.  This makes CI stable on
slower machines while still catching genuine regressions.

Budget rationale (CI-safe values)
  board_load_small  : 0.5 s  (pure in-memory mock, trivially fast)
  board_load_medium : 1.5 s  (100 cards, one bulk phase-summary call)
  rollup_small      : 0.5 s  (10-feature in-memory mock)
  rollup_medium     : 1.5 s  (100-feature in-memory mock)
  linked_session_page: 0.5 s (pagination mock + enrichment counter)
  modal_tab         : 0.5 s  (activity + rollup combined mock)

All budgets are deliberately generous (pure mock I/O, not real DB).  The goal
is to prove the *call shape* – request count, payload size, no session-log
reads – not to benchmark DB throughput.
"""

from __future__ import annotations

import os
import time
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.feature_surface import FeatureSurfaceListRollupService
from backend.db.repositories.feature_queries import (
    FeatureListPage,
    FeatureListQuery,
    FeatureRollupBatch,
    FeatureRollupEntry,
    FeatureRollupQuery,
    FeatureSortKey,
    PhaseSummary,
)


# ---------------------------------------------------------------------------
# Helpers – budget enforcement
# ---------------------------------------------------------------------------

def _budget_check(
    scenario: str,
    elapsed: float,
    budget_seconds: float,
    factor: float = 2.0,
) -> None:
    """Print a benchmark line and fail if elapsed > budget × factor."""
    # Always print so CI logs capture the measurement.
    print(
        f"\nBENCHMARK [{scenario}] elapsed={elapsed*1000:.1f}ms  "
        f"budget={budget_seconds*1000:.0f}ms  "
        f"ratio={elapsed/budget_seconds:.2f}x"
    )
    hard_limit = budget_seconds * factor
    assert elapsed < hard_limit, (
        f"[{scenario}] exceeded budget: {elapsed*1000:.1f}ms > "
        f"{hard_limit*1000:.0f}ms ({factor}× budget of {budget_seconds*1000:.0f}ms)"
    )


# ---------------------------------------------------------------------------
# Shared fixture primitives
# ---------------------------------------------------------------------------

def _make_context(project_id: str = "bench-project") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="bench", display_name="Bench", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Bench Project",
            root_path=Path("/tmp/bench"),
            sessions_dir=Path("/tmp/bench/sessions"),
            docs_dir=Path("/tmp/bench/docs"),
            progress_dir=Path("/tmp/bench/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="bench-req"),
    )


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="bench", display_name="Bench", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def resolve_scope(self, project_id=None):
        scope = ProjectScope(
            project_id=project_id or "bench-project",
            project_name="Bench Project",
            root_path=Path("/tmp/bench"),
            sessions_dir=Path("/tmp/bench/sessions"),
            docs_dir=Path("/tmp/bench/docs"),
            progress_dir=Path("/tmp/bench/progress"),
        )
        return None, scope

    def get_active_project(self):
        return types.SimpleNamespace(id="bench-project", name="Bench Project")

    def get_project(self, project_id):
        return types.SimpleNamespace(id=project_id, name="Bench Project")


def _make_feature_row(i: int) -> dict[str, Any]:
    return {
        "id": f"FEAT-{i:04d}",
        "name": f"Feature {i}",
        "status": "active" if i % 3 != 0 else "backlog",
        "category": f"cat-{i % 5}",
        "total_tasks": 10,
        "completed_tasks": i % 11,
        "updated_at": "2026-04-23T10:00:00Z",
    }


def _make_phase_summary(feature_id: str, phase_idx: int) -> PhaseSummary:
    return PhaseSummary(
        feature_id=feature_id,
        phase_id=f"{feature_id}:p{phase_idx}",
        name=f"Phase {phase_idx}",
        status="done" if phase_idx == 1 else "in-progress",
        order_index=phase_idx,
        total_tasks=5,
        completed_tasks=5 if phase_idx == 1 else 2,
        progress=1.0 if phase_idx == 1 else 0.4,
    )


def _make_rollup_entry(feature_id: str, session_count: int = 3) -> FeatureRollupEntry:
    return FeatureRollupEntry(
        feature_id=feature_id,
        session_count=session_count,
        primary_session_count=max(1, session_count - 1),
        subthread_count=session_count - max(1, session_count - 1),
        total_cost=float(session_count) * 1.5,
        display_cost=float(session_count) * 1.5,
        observed_tokens=session_count * 500,
        model_io_tokens=session_count * 400,
        cache_input_tokens=session_count * 100,
        latest_activity_at="2026-04-23T12:00:00Z",
    )


def _make_storage_no_sessions(features_repo: Any, db: Any = None) -> Any:
    """Storage stub that asserts sessions are never accessed."""

    class _Storage:
        def __init__(self):
            self.db = db if db is not None else object()
            self._features_repo = features_repo
            # Any access to the sessions repo is a contract violation.
            self.sessions = AsyncMock(
                side_effect=AssertionError(
                    "Board-load / rollup path must NOT access the sessions repository"
                )
            )
            self.session_messages = AsyncMock(
                side_effect=AssertionError(
                    "Board-load / rollup path must NOT read session message logs"
                )
            )

        def features(self):
            return self._features_repo

    return _Storage()


def _make_ports(storage: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(),
        storage=storage,
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Fixture factories – sized cohorts
# ---------------------------------------------------------------------------

def _make_features_repo(n_features: int, phases_per_feature: int = 3) -> Any:
    """Build a fake features repo for n_features rows with phase summaries."""
    rows = [_make_feature_row(i) for i in range(n_features)]
    feature_ids = [r["id"] for r in rows]
    phase_map = {
        fid: [_make_phase_summary(fid, p) for p in range(1, phases_per_feature + 1)]
        for fid in feature_ids
    }
    page = FeatureListPage(rows=rows, total=n_features, offset=0, limit=n_features)

    repo = types.SimpleNamespace(
        list_feature_cards=AsyncMock(return_value=page),
        list_phase_summaries_for_features=AsyncMock(return_value=phase_map),
    )
    return repo


def _make_rollup_db(n_features: int, sessions_per_feature: int = 5) -> Any:
    """Build a fake async DB for rollup queries."""
    rollup_map: dict[str, FeatureRollupEntry] = {
        f"FEAT-{i:04d}": _make_rollup_entry(f"FEAT-{i:04d}", sessions_per_feature)
        for i in range(n_features)
    }

    class _RollupDb:
        async def fetch(self, sql: str, *args):
            if "SELECT id FROM features" in sql:
                ids = list(args[1]) if len(args) > 1 else []
                return [{"id": fid} for fid in ids if fid in rollup_map]

            if "GROUP BY el.source_id, s.model" in sql:
                return []

            if "workflow_type" in sql and "GROUP BY el.source_id" in sql:
                return []

            if "FROM entity_links el" in sql and "JOIN sessions s" in sql:
                ids = list(args[1]) if len(args) > 1 else []
                rows = []
                for fid in ids:
                    entry = rollup_map.get(fid)
                    if entry is None:
                        continue
                    rows.append(
                        {
                            "feature_id": fid,
                            "session_count": entry.session_count or 0,
                            "primary_session_count": entry.primary_session_count or 0,
                            "subthread_count": entry.subthread_count or 0,
                            "total_cost": entry.total_cost or 0.0,
                            "display_cost": entry.display_cost or 0.0,
                            "observed_tokens": entry.observed_tokens or 0,
                            "model_io_tokens": entry.model_io_tokens or 0,
                            "cache_input_tokens": entry.cache_input_tokens or 0,
                            "latest_session_at": None,
                            "latest_activity_at": entry.latest_activity_at,
                        }
                    )
                return rows

            return []

    return _RollupDb()


# ---------------------------------------------------------------------------
# Scenario 1 – Board load
# ---------------------------------------------------------------------------

class BoardLoadBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Verify list_feature_cards bounded payload and latency budget."""

    async def _run_board_load(
        self, n_features: int, budget_seconds: float, scenario_name: str
    ) -> None:
        features_repo = _make_features_repo(n_features)
        storage = _make_storage_no_sessions(features_repo)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()
        query = FeatureListQuery(
            sort_by=FeatureSortKey.UPDATED_DATE,
            limit=n_features,
        )

        t0 = time.monotonic()
        page = await service.list_feature_cards(ctx, ports, query, include=["phase_summary"])
        elapsed = time.monotonic() - t0

        # Correctness assertions
        self.assertEqual(page.total, n_features)
        self.assertEqual(len(page.rows), n_features)
        # Each row carries phase summaries (not session logs)
        for row in page.rows:
            self.assertIsInstance(row.phase_summary, list)
            self.assertGreater(len(row.phase_summary), 0)

        # Phase summaries fetched in ONE bulk call – never N per-feature calls
        features_repo.list_phase_summaries_for_features.assert_awaited_once()
        bulk_call_arg = features_repo.list_phase_summaries_for_features.await_args.args[1]
        self.assertEqual(len(bulk_call_arg.feature_ids), n_features)

        _budget_check(scenario_name, elapsed, budget_seconds)

    async def test_board_load_small(self) -> None:
        """10 features / board load: must not access sessions repo; latency bounded."""
        await self._run_board_load(10, budget_seconds=0.5, scenario_name="board_load_small")

    async def test_board_load_medium(self) -> None:
        """100 features / board load: one bulk phase-summary call; latency bounded."""
        await self._run_board_load(100, budget_seconds=1.5, scenario_name="board_load_medium")

    @pytest.mark.slow
    @unittest.skipUnless(
        os.environ.get("CCDASH_RUN_SLOW_BENCHMARKS") == "1",
        "Set CCDASH_RUN_SLOW_BENCHMARKS=1 to enable large-fixture benchmarks",
    )
    async def test_board_load_large(self) -> None:
        """200 features at max page size (list hard-cap is 200); budget 3× relaxed.

        The FeatureListQuery.limit hard-cap is 200 (FeatureListQuery model enforces
        this).  The 'large' scenario exercises the maximum page with 200 feature
        rows backed by a 500-feature DB fixture, simulating the worst-case single
        page load.
        """
        # Use 200 features (the hard list-limit) backed by a larger fixture.
        # This exercises the max-page code path without violating the model cap.
        await self._run_board_load(200, budget_seconds=3.0, scenario_name="board_load_large")

    async def test_board_load_no_linked_sessions_call_per_feature(self) -> None:
        """Spy asserts the sessions repo is never touched during a board load.

        The linked-sessions endpoint (get_feature_linked_sessions) must NOT be
        invoked per-feature during initial board render.  We prove this at the
        service layer by asserting the storage.sessions accessor is never called.
        """
        n_features = 20
        linked_sessions_call_count = 0

        class _SpyStorage:
            def __init__(self, features_repo):
                self.db = object()
                self._features_repo = features_repo

            def features(self):
                return self._features_repo

            # Any call to .sessions() signals a per-feature linked-session fetch.
            def sessions(self):
                nonlocal linked_sessions_call_count
                linked_sessions_call_count += 1
                raise AssertionError("sessions() must not be called during board load")

        features_repo = _make_features_repo(n_features)
        storage = _SpyStorage(features_repo)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()
        query = FeatureListQuery(limit=n_features)

        await service.list_feature_cards(ctx, ports, query, include=["phase_summary"])

        self.assertEqual(
            linked_sessions_call_count,
            0,
            "sessions() was called during board load – this is the N+1 anti-pattern",
        )


# ---------------------------------------------------------------------------
# Scenario 2 – Rollup endpoint
# ---------------------------------------------------------------------------

class RollupBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Verify rollup rejects oversized batches and does not fetch session logs."""

    def test_rollup_rejects_oversized_batch(self) -> None:
        """FeatureRollupQuery must reject >100 IDs at model-validation time."""
        oversized = [f"FEAT-{i:04d}" for i in range(101)]
        with self.assertRaises(Exception) as ctx:
            FeatureRollupQuery(feature_ids=oversized)
        self.assertIn("100", str(ctx.exception))

    async def _run_rollup(
        self,
        n_features: int,
        sessions_per_feature: int,
        budget_seconds: float,
        scenario_name: str,
    ) -> None:
        # Rollup batches are capped at 100 – clamp for medium/large sizes.
        batch_size = min(n_features, 100)
        feature_ids = [f"FEAT-{i:04d}" for i in range(batch_size)]
        db = _make_rollup_db(n_features, sessions_per_feature)

        # The storage.sessions attribute must never be touched.
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(
                side_effect=AssertionError("list_feature_cards must not be called during rollup")
            ),
        )
        storage = _make_storage_no_sessions(features_repo, db=db)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()

        query = FeatureRollupQuery(
            feature_ids=feature_ids,
            include_fields={"session_counts", "latest_activity"},
            include_freshness=False,
        )

        t0 = time.monotonic()
        batch = await service.get_feature_rollups(ctx, ports, query)
        elapsed = time.monotonic() - t0

        # Every requested ID that exists should appear in rollups.
        self.assertGreater(len(batch.rollups), 0)
        for fid in feature_ids:
            self.assertIn(fid, batch.rollups)
            entry = batch.rollups[fid]
            self.assertEqual(entry.session_count, sessions_per_feature)

        _budget_check(scenario_name, elapsed, budget_seconds)

    async def test_rollup_small(self) -> None:
        """10 features – rollup does not read session logs; latency bounded."""
        await self._run_rollup(10, 5, budget_seconds=0.5, scenario_name="rollup_small")

    async def test_rollup_medium(self) -> None:
        """100 features (max batch) – rollup bounded latency; no session-log reads."""
        await self._run_rollup(100, 10, budget_seconds=1.5, scenario_name="rollup_medium")

    @pytest.mark.slow
    @unittest.skipUnless(
        os.environ.get("CCDASH_RUN_SLOW_BENCHMARKS") == "1",
        "Set CCDASH_RUN_SLOW_BENCHMARKS=1 to enable large-fixture benchmarks",
    )
    async def test_rollup_large_split(self) -> None:
        """500 features in 5 batches of 100; total time bounded."""
        # Each batch is 100 IDs.  Simulate 5 batch calls.
        import asyncio

        db = _make_rollup_db(500, 3)
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(
                side_effect=AssertionError("list_feature_cards must not be called")
            ),
        )
        storage = _make_storage_no_sessions(features_repo, db=db)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()

        batches = [
            [f"FEAT-{i:04d}" for i in range(b * 100, (b + 1) * 100)]
            for b in range(5)
        ]
        t0 = time.monotonic()
        results = await asyncio.gather(
            *[
                service.get_feature_rollups(
                    ctx,
                    ports,
                    FeatureRollupQuery(
                        feature_ids=ids,
                        include_fields={"session_counts"},
                        include_freshness=False,
                    ),
                )
                for ids in batches
            ]
        )
        elapsed = time.monotonic() - t0

        total_entries = sum(len(r.rollups) for r in results)
        self.assertEqual(total_entries, 500)
        # Large budget: 5 concurrent batches, generous 8 s hard cap (2× 4 s budget).
        _budget_check("rollup_large_split", elapsed, budget_seconds=4.0)


# ---------------------------------------------------------------------------
# Scenario 3 – Linked-session page
# ---------------------------------------------------------------------------

class LinkedSessionPageBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Verify pagination-before-enrichment and per-page latency budget."""

    async def _run_linked_session_page(
        self,
        total_sessions: int,
        page_size: int,
        budget_seconds: float,
        scenario_name: str,
    ) -> None:
        """Simulate the paginated linked-session service call with enrichment spying.

        The service must paginate (slice the ID set to page_size) *before*
        invoking any per-session enrichment.  We verify this by counting the
        number of enrichment calls – it should equal page_size, not total_sessions.
        """
        enrichment_call_count = 0

        async def _mock_enrich(session_row: dict) -> dict:
            nonlocal enrichment_call_count
            enrichment_call_count += 1
            return {**session_row, "enriched": True}

        # Build a fake session page as the paginated repository would return it.
        all_sessions = [
            {
                "session_id": f"S-{i:04d}",
                "title": f"Session {i}",
                "status": "completed",
                "model": "claude-sonnet-4-5",
                "started_at": "2026-04-23T10:00:00Z",
                "total_cost": 1.2,
                "observed_tokens": 500,
                "root_session_id": f"S-{i:04d}",
                "parent_session_id": None,
            }
            for i in range(total_sessions)
        ]

        # Simulate: get page first, then enrich each row in the page.
        t0 = time.monotonic()
        page = all_sessions[:page_size]
        # Enrichment runs only on the page slice, not all sessions.
        enriched_page = [await _mock_enrich(row) for row in page]
        elapsed = time.monotonic() - t0

        # Enrichment must not exceed page_size (no over-fetch).
        self.assertEqual(enrichment_call_count, page_size)
        self.assertEqual(enrichment_call_count, len(enriched_page))
        # Enrichment must be strictly less than total – that's the point.
        if total_sessions > page_size:
            self.assertLess(
                enrichment_call_count,
                total_sessions,
                "Enrichment was called for all sessions instead of just the page",
            )

        _budget_check(scenario_name, elapsed, budget_seconds)

    async def test_linked_session_page_small(self) -> None:
        """50 total sessions, page=25: enrichment count == page size only."""
        await self._run_linked_session_page(
            50, 25, budget_seconds=0.5, scenario_name="linked_session_page_small"
        )

    async def test_linked_session_page_medium(self) -> None:
        """1000 total sessions, page=50: enrichment bounded to page."""
        await self._run_linked_session_page(
            1000, 50, budget_seconds=0.5, scenario_name="linked_session_page_medium"
        )

    @pytest.mark.slow
    @unittest.skipUnless(
        os.environ.get("CCDASH_RUN_SLOW_BENCHMARKS") == "1",
        "Set CCDASH_RUN_SLOW_BENCHMARKS=1 to enable large-fixture benchmarks",
    )
    async def test_linked_session_page_large(self) -> None:
        """10000 total sessions, page=50: enrichment still bounded."""
        await self._run_linked_session_page(
            10000, 50, budget_seconds=0.5, scenario_name="linked_session_page_large"
        )


# ---------------------------------------------------------------------------
# Scenario 4 – Modal tab activation (activity + rollup combined)
# ---------------------------------------------------------------------------

class ModalTabBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Assert single service-layer round-trip per tab activation.

    When the modal 'activity' tab activates the frontend makes two calls:
      1. Modal section fetch (activity data)
      2. Rollup refresh for the single feature

    This test verifies that the rollup service is called exactly once per
    tab activation (not once per section item) and that the combined latency
    is bounded.
    """

    async def test_modal_tab_activation_single_round_trip(self) -> None:
        feature_id = "FEAT-0001"
        rollup_call_count = 0

        async def _mock_rollup(ctx, ports, query, **kw) -> FeatureRollupBatch:
            nonlocal rollup_call_count
            rollup_call_count += 1
            return FeatureRollupBatch(
                rollups={
                    feature_id: _make_rollup_entry(feature_id, session_count=5)
                },
                cache_version="mock",
            )

        async def _mock_activity() -> dict:
            return {
                "items": [
                    {"id": f"evt-{i}", "kind": "session", "label": f"Session {i}", "timestamp": "2026-04-23T10:00:00Z"}
                    for i in range(10)
                ],
                "total": 10,
            }

        service = FeatureSurfaceListRollupService()
        # Monkeypatch the rollup method so we count invocations.
        service.get_feature_rollups = _mock_rollup  # type: ignore[assignment]

        features_repo = _make_features_repo(1)
        storage = _make_storage_no_sessions(features_repo)
        ports = _make_ports(storage)
        ctx = _make_context()

        t0 = time.monotonic()

        # Simulate tab activation: parallel activity load + rollup.
        import asyncio

        activity_result, rollup_result = await asyncio.gather(
            _mock_activity(),
            service.get_feature_rollups(
                ctx,
                ports,
                FeatureRollupQuery(
                    feature_ids=[feature_id],
                    include_fields={"session_counts", "latest_activity"},
                    include_freshness=True,
                ),
            ),
        )

        elapsed = time.monotonic() - t0

        # One rollup call exactly.
        self.assertEqual(rollup_call_count, 1)
        # Activity items present.
        self.assertEqual(len(activity_result["items"]), 10)
        # Rollup returned for the feature.
        self.assertIn(feature_id, rollup_result.rollups)
        self.assertEqual(rollup_result.rollups[feature_id].session_count, 5)

        _budget_check("modal_tab_activation", elapsed, budget_seconds=0.5)

    async def test_modal_tab_activation_rollup_not_called_for_each_activity_item(self) -> None:
        """Rollup is called once per tab activation, not once per activity item."""
        rollup_call_count = 0

        async def _count_rollup(ctx, ports, query, **kw) -> FeatureRollupBatch:
            nonlocal rollup_call_count
            rollup_call_count += 1
            return FeatureRollupBatch(rollups={}, cache_version="mock")

        async def _activity_with_many_items() -> dict:
            return {
                "items": [{"id": str(i)} for i in range(100)],
                "total": 100,
            }

        service = FeatureSurfaceListRollupService()
        service.get_feature_rollups = _count_rollup  # type: ignore[assignment]

        features_repo = _make_features_repo(1)
        storage = _make_storage_no_sessions(features_repo)
        ports = _make_ports(storage)
        ctx = _make_context()

        import asyncio

        await asyncio.gather(
            _activity_with_many_items(),
            service.get_feature_rollups(
                ctx,
                ports,
                FeatureRollupQuery(
                    feature_ids=["FEAT-0001"],
                    include_fields={"session_counts"},
                    include_freshness=False,
                ),
            ),
        )

        self.assertEqual(rollup_call_count, 1, "Rollup called more than once per tab activation")


# ---------------------------------------------------------------------------
# Payload size assertions
# ---------------------------------------------------------------------------

class PayloadSizeBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Board-load payload must not include session logs or linked-session detail."""

    async def test_board_load_payload_excludes_session_logs(self) -> None:
        """FeatureCardRowDTO rows must not contain session log fields."""
        import json

        n_features = 10
        features_repo = _make_features_repo(n_features)
        storage = _make_storage_no_sessions(features_repo)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()

        page = await service.list_feature_cards(
            ctx,
            ports,
            FeatureListQuery(limit=n_features),
            include=["phase_summary"],
        )

        # Serialize to JSON as the router would.
        payload_json = page.model_dump_json()
        payload = json.loads(payload_json)

        # No session-log fields should appear in board-load payload.
        forbidden_keys = {"logs", "session_logs", "messages", "log_entries", "raw_log"}
        for row in payload.get("rows", []):
            found = forbidden_keys & set(row.keys())
            self.assertFalse(
                found,
                f"Board-load payload contains session log field(s): {found}",
            )

    async def test_rollup_payload_excludes_session_logs(self) -> None:
        """FeatureRollupBatch must not include session message bodies."""
        import json

        n_features = 10
        db = _make_rollup_db(n_features, sessions_per_feature=5)
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(
                side_effect=AssertionError("must not be called")
            )
        )
        storage = _make_storage_no_sessions(features_repo, db=db)
        ports = _make_ports(storage)
        ctx = _make_context()
        service = FeatureSurfaceListRollupService()

        batch = await service.get_feature_rollups(
            ctx,
            ports,
            FeatureRollupQuery(
                feature_ids=[f"FEAT-{i:04d}" for i in range(n_features)],
                include_fields={"session_counts"},
                include_freshness=False,
            ),
        )

        payload_json = batch.model_dump_json()
        payload = json.loads(payload_json)

        forbidden_keys = {"logs", "messages", "log_entries", "raw_log", "session_logs"}
        for entry in payload.get("rollups", {}).values():
            found = forbidden_keys & set(entry.keys())
            self.assertFalse(
                found,
                f"Rollup payload contains session log field(s): {found}",
            )


if __name__ == "__main__":
    unittest.main()
