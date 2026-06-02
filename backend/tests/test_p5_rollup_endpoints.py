"""Tests for P5 Wave-2 ROLLUPS lane endpoints.

Covers:
- P5-002: tokenTelemetry.source == "backend" when tokens are present
- P5-003a: GET /api/agent/planning/portfolio/rollup response shape
- P5-003b: GET /api/agent/system/token-rollup response shape
- P5-004: GET /api/agent/planning/next-work response shape + cursor pagination
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.services.agent_queries.planning import (
    _build_token_telemetry,
    _bulk_fetch_feature_token_usage,
)
from backend.models import (
    Feature,
    NextWorkResponse,
    PortfolioRollupResponse,
    SystemTokenRollupResponse,
    TokenUsageByModel,
)
from backend.application.services.agent_queries.models import (
    PlanningTokenTelemetry,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _feature(fid: str = "f1", opus: int = 0, sonnet: int = 0) -> Feature:
    f = Feature(id=fid, name=fid)
    f.tokenUsageByModel = TokenUsageByModel(opus=opus, sonnet=sonnet, total=opus + sonnet)
    return f


# ── P5-002: _build_token_telemetry ───────────────────────────────────────────

class TokenTelemetrySourceTests(unittest.TestCase):
    """AC-5: source=="backend" when any feature has tokens > 0."""

    def test_source_unavailable_when_all_zero(self) -> None:
        features = [_feature("f1"), _feature("f2")]
        result = _build_token_telemetry(features)
        self.assertEqual(result.source, "unavailable")
        self.assertIsNone(result.total_tokens)

    def test_source_backend_when_any_nonzero(self) -> None:
        features = [_feature("f1", opus=1000), _feature("f2")]
        result = _build_token_telemetry(features)
        self.assertEqual(result.source, "backend")
        self.assertEqual(result.total_tokens, 1000)

    def test_source_backend_aggregates_all_families(self) -> None:
        features = [_feature("f1", opus=100, sonnet=200), _feature("f2", opus=50)]
        result = _build_token_telemetry(features)
        self.assertEqual(result.source, "backend")
        self.assertEqual(result.total_tokens, 350)
        families = {e.model_family: e.total_tokens for e in result.by_model_family}
        self.assertEqual(families["opus"], 150)
        self.assertEqual(families["sonnet"], 200)

    def test_empty_features_list_is_unavailable(self) -> None:
        result = _build_token_telemetry([])
        self.assertEqual(result.source, "unavailable")


# ── P5-002: _bulk_fetch_feature_token_usage ──────────────────────────────────

class BulkFetchTokenUsageTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the SQL-backed bulk token fetch helper."""

    async def test_empty_feature_ids_returns_empty(self) -> None:
        db = MagicMock()
        result = await _bulk_fetch_feature_token_usage(db, "proj-1", [])
        self.assertEqual(result, {})

    async def test_sql_error_returns_empty(self) -> None:
        import aiosqlite

        # Simulate a DB error by making execute raise.
        db = MagicMock(spec=aiosqlite.Connection)
        db.execute.side_effect = RuntimeError("db error")
        result = await _bulk_fetch_feature_token_usage(db, "proj-1", ["f1"])
        self.assertEqual(result, {})

    async def test_rows_aggregated_per_feature(self) -> None:
        import aiosqlite

        # Simulate two rows: feature f1 with opus model, feature f2 with sonnet model.
        rows = [
            ("f1", "claude-opus-4-5", 1000),
            ("f2", "claude-sonnet-4-5", 500),
        ]

        class _FakeCursor:
            async def fetchall(self):
                return rows

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        db = MagicMock(spec=aiosqlite.Connection)
        db.execute.return_value = _FakeCursor()

        with patch(
            "backend.application.services.agent_queries.planning.derive_model_identity",
            side_effect=lambda m: {"modelFamily": "opus" if "opus" in m else "sonnet"},
        ):
            result = await _bulk_fetch_feature_token_usage(db, "proj-1", ["f1", "f2"])

        self.assertIn("f1", result)
        self.assertEqual(result["f1"].opus, 1000)
        self.assertIn("f2", result)
        self.assertEqual(result["f2"].sonnet, 500)


# ── P5-003a: Portfolio rollup response shape ──────────────────────────────────

class PortfolioRollupResponseTests(unittest.TestCase):
    """Contract tests for PortfolioRollupResponse model."""

    def test_default_fields(self) -> None:
        r = PortfolioRollupResponse()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.projects, [])
        self.assertIsNotNone(r.attention)
        self.assertIsNone(r.generated_at)

    def test_serialises_without_error(self) -> None:
        import json
        r = PortfolioRollupResponse(
            status="ok",
            generated_at=datetime.now(timezone.utc),
        )
        dumped = r.model_dump(mode="json")
        # Must be JSON-serialisable.
        json.dumps(dumped)
        self.assertIn("projects", dumped)
        self.assertIn("attention", dumped)
        self.assertIn("generated_at", dumped)


# ── P5-003b: System token rollup response shape ───────────────────────────────

class SystemTokenRollupResponseTests(unittest.TestCase):
    """Contract tests for SystemTokenRollupResponse model."""

    def test_default_fields(self) -> None:
        r = SystemTokenRollupResponse()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.period, "daily")
        self.assertEqual(r.totals.tokens_in, 0)
        self.assertEqual(r.by_project, [])
        self.assertEqual(r.by_model_family, [])

    def test_serialises_without_error(self) -> None:
        import json
        r = SystemTokenRollupResponse(
            status="ok",
            period="daily",
            generated_at=datetime.now(timezone.utc),
        )
        dumped = r.model_dump(mode="json")
        json.dumps(dumped)
        self.assertIn("totals", dumped)
        self.assertIn("by_project", dumped)
        self.assertIn("by_model_family", dumped)


# ── P5-004: NextWorkResponse + cursor helpers ─────────────────────────────────

class NextWorkResponseTests(unittest.TestCase):
    """Contract tests for NextWorkResponse model."""

    def test_default_fields(self) -> None:
        r = NextWorkResponse()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.items, [])
        self.assertIsNone(r.next_cursor)

    def test_next_cursor_round_trip(self) -> None:
        from backend.application.services.agent_queries.planning_next_work import (
            _encode_cursor,
            _decode_cursor,
        )
        cursor = _encode_cursor("2026-01-01T00:00:00+00:00", "feat-abc")
        decoded = _decode_cursor(cursor)
        self.assertIsNotNone(decoded)
        ts, fid = decoded  # type: ignore[misc]
        self.assertEqual(ts, "2026-01-01T00:00:00+00:00")
        self.assertEqual(fid, "feat-abc")

    def test_invalid_cursor_returns_none(self) -> None:
        from backend.application.services.agent_queries.planning_next_work import _decode_cursor
        self.assertIsNone(_decode_cursor("!!!not-base64!!!"))

    def test_serialises_without_error(self) -> None:
        import json
        r = NextWorkResponse(status="ok", next_cursor="abc", generated_at=datetime.now(timezone.utc))
        json.dumps(r.model_dump(mode="json"))


# ── Route registration smoke tests ───────────────────────────────────────────

class RouteRegistrationTests(unittest.TestCase):
    """Verify the three new routes are registered in agent_router."""

    def _get_route_paths(self) -> set[str]:
        from backend.routers.agent import agent_router
        return {r.path for r in agent_router.routes}  # type: ignore[attr-defined]

    def test_portfolio_rollup_route_registered(self) -> None:
        paths = self._get_route_paths()
        self.assertIn("/api/agent/planning/portfolio/rollup", paths)

    def test_system_token_rollup_route_registered(self) -> None:
        paths = self._get_route_paths()
        self.assertIn("/api/agent/system/token-rollup", paths)

    def test_next_work_route_registered(self) -> None:
        paths = self._get_route_paths()
        self.assertIn("/api/agent/planning/next-work", paths)


if __name__ == "__main__":
    unittest.main()
