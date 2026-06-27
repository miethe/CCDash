"""Tests for P2-016: list_features N+1 elimination and server-side memoization.

Acceptance criteria:
1. ``list_phase_summaries_for_features`` is called exactly ONCE per request
   regardless of the number of returned features — no per-feature ``get_phases``
   calls (N+1 eliminated).
2. A second call with the same parameters returns the cached result without
   re-executing the DB queries (memoization).
"""
from __future__ import annotations

import json
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from backend.db.repositories.feature_queries import PhaseSummary, PhaseSummaryBulkQuery
from backend.routers import features as features_router
from backend.application.services.agent_queries import cache as _cache_module


def _make_feature_row(feature_id: str, project_id: str = "project-1") -> dict:
    """Return a minimal feature row dict matching the shape from the DB."""
    return {
        "id": feature_id,
        "name": feature_id.replace("-", " ").title(),
        "status": "active",
        "category": "enhancement",
        "project_id": project_id,
        "total_tasks": 2,
        "completed_tasks": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "data_json": json.dumps(
            {
                "phases": [{"phase": "1", "deferredTasks": 0}],
                "linkedDocs": [],
                "linkedFeatures": [],
                "primaryDocuments": {},
                "documentCoverage": {},
                "qualitySignals": {},
                "relatedFeatures": [],
            }
        ),
    }


def _make_phase_summaries(feature_id: str) -> list[PhaseSummary]:
    """Return a minimal PhaseSummary list for a feature."""
    return [
        PhaseSummary(
            feature_id=feature_id,
            phase_id=f"{feature_id}:phase-1",
            name="Phase 1",
            status="in-progress",
            order_index=1,
            total_tasks=2,
            completed_tasks=1,
            progress=0.5,
        )
    ]


class TestListFeaturesN1Elimination(unittest.IsolatedAsyncioTestCase):
    """Asserts that list_features uses a single batch query for phases.

    The per-feature ``get_phases`` call (N+1) must not be issued; instead
    ``list_phase_summaries_for_features`` must be called exactly once.
    """

    async def test_phases_loaded_in_single_batch_call_not_per_feature(self) -> None:
        """N+1 eliminated: batch method called once; get_phases never called."""
        feature_ids = ["feat-alpha", "feat-beta", "feat-gamma"]
        rows = [_make_feature_row(fid) for fid in feature_ids]
        project = types.SimpleNamespace(id="project-1")

        # Phase summaries keyed by feature_id
        phases_map = {fid: _make_phase_summaries(fid) for fid in feature_ids}

        repo = MagicMock()
        repo.list_paginated = AsyncMock(return_value=rows)
        repo.count = AsyncMock(return_value=len(rows))
        repo.get_phases = AsyncMock(return_value=[])  # should NOT be called
        repo.list_phase_summaries_for_features = AsyncMock(return_value=phases_map)

        with (
            patch.object(
                features_router.project_manager, "get_active_project", return_value=project
            ),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(
                features_router,
                "load_feature_execution_derived_states",
                return_value={},
            ),
            # Disable cache for this test so we exercise the DB path each call
            patch.dict(
                __import__("os").environ,
                {"CCDASH_QUERY_CACHE_TTL_SECONDS": "0"},
            ),
            patch.object(_cache_module.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0),
        ):
            response = await features_router.list_features(offset=0, limit=200)

        # Batch method called exactly once (not N times)
        repo.list_phase_summaries_for_features.assert_called_once()
        # Per-feature get_phases must NOT have been called
        repo.get_phases.assert_not_called()

        # Response shape preserved
        self.assertEqual(len(response.items), 3)
        # Phases are populated from the batch result (FeaturePhase model instances)
        feature_with_phases = next(f for f in response.items if f.id == "feat-alpha")
        self.assertEqual(len(feature_with_phases.phases), 1)
        self.assertEqual(feature_with_phases.phases[0].title, "Phase 1")

    async def test_batch_query_receives_all_feature_ids(self) -> None:
        """Batch call receives ALL feature IDs from the page, not a subset."""
        feature_ids = ["feat-one", "feat-two"]
        rows = [_make_feature_row(fid) for fid in feature_ids]
        project = types.SimpleNamespace(id="project-1")

        repo = MagicMock()
        repo.list_paginated = AsyncMock(return_value=rows)
        repo.count = AsyncMock(return_value=2)
        repo.get_phases = AsyncMock(return_value=[])
        repo.list_phase_summaries_for_features = AsyncMock(
            return_value={fid: [] for fid in feature_ids}
        )

        with (
            patch.object(
                features_router.project_manager, "get_active_project", return_value=project
            ),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(
                features_router,
                "load_feature_execution_derived_states",
                return_value={},
            ),
            patch.object(_cache_module.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0),
        ):
            await features_router.list_features(offset=0, limit=200)

        # Verify the PhaseSummaryBulkQuery passed contains all feature IDs
        call_args = repo.list_phase_summaries_for_features.call_args
        passed_query: PhaseSummaryBulkQuery = call_args[0][1]  # positional arg 1
        self.assertIn("feat-one", passed_query.feature_ids)
        self.assertIn("feat-two", passed_query.feature_ids)
        self.assertEqual(len(passed_query.feature_ids), 2)


class TestListFeaturesMemoization(unittest.IsolatedAsyncioTestCase):
    """Asserts server-side memoization: second call with same params returns
    the cached result and does not re-issue DB queries."""

    async def asyncSetUp(self) -> None:
        # Clear the in-process cache before each test so state is clean
        _cache_module.clear_cache()

    async def asyncTearDown(self) -> None:
        _cache_module.clear_cache()

    async def test_second_call_returns_cached_result_without_db_queries(self) -> None:
        """Memoization: DB queries issued only on first call; second call is a cache hit."""
        feature_ids = ["feat-memo-1"]
        rows = [_make_feature_row(fid) for fid in feature_ids]
        project = types.SimpleNamespace(id="project-1")
        phases_map = {fid: _make_phase_summaries(fid) for fid in feature_ids}

        repo = MagicMock()
        repo.list_paginated = AsyncMock(return_value=rows)
        repo.count = AsyncMock(return_value=1)
        repo.get_phases = AsyncMock(return_value=[])
        repo.list_phase_summaries_for_features = AsyncMock(return_value=phases_map)

        with (
            patch.object(
                features_router.project_manager, "get_active_project", return_value=project
            ),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(
                features_router,
                "load_feature_execution_derived_states",
                return_value={},
            ),
            # Enable a generous TTL so the cache entry survives both calls
            patch.object(_cache_module.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 300),
        ):
            response_1 = await features_router.list_features(offset=0, limit=200)
            response_2 = await features_router.list_features(offset=0, limit=200)

        # DB queries issued only on first call (1 time each)
        self.assertEqual(repo.list_paginated.call_count, 1)
        self.assertEqual(repo.count.call_count, 1)
        self.assertEqual(repo.list_phase_summaries_for_features.call_count, 1)

        # Both responses contain the same feature
        self.assertEqual(len(response_1.items), 1)
        self.assertEqual(len(response_2.items), 1)
        self.assertEqual(response_1.items[0].id, response_2.items[0].id)

    async def test_different_params_produce_separate_cache_entries(self) -> None:
        """Different query params are not collapsed into the same cache key."""
        rows_offset_0 = [_make_feature_row("feat-a")]
        rows_offset_1 = [_make_feature_row("feat-b")]
        project = types.SimpleNamespace(id="project-1")

        repo = MagicMock()
        # Return different rows depending on offset
        async def _paginated(proj_id: str, offset: int, limit: int) -> list[dict]:
            return rows_offset_0 if offset == 0 else rows_offset_1

        repo.list_paginated = AsyncMock(side_effect=_paginated)
        repo.count = AsyncMock(return_value=2)
        repo.get_phases = AsyncMock(return_value=[])
        repo.list_phase_summaries_for_features = AsyncMock(return_value={})

        with (
            patch.object(
                features_router.project_manager, "get_active_project", return_value=project
            ),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(
                features_router,
                "load_feature_execution_derived_states",
                return_value={},
            ),
            patch.object(_cache_module.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 300),
        ):
            response_0 = await features_router.list_features(offset=0, limit=200)
            response_1 = await features_router.list_features(offset=1, limit=200)

        # Both offset values should have triggered separate DB calls (2 times each)
        self.assertEqual(repo.list_paginated.call_count, 2)
        # The two responses should contain different features
        self.assertNotEqual(
            {f.id for f in response_0.items},
            {f.id for f in response_1.items},
        )


if __name__ == "__main__":
    unittest.main()
