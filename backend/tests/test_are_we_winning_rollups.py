"""Tests for the are-we-winning dashboard weekly rollups + drill-through (M2 part A).

Covers the milestone's four explicit AC (see the M2-part-A task description):

  1. ISO-week bucket boundary — a Sunday-23:59 / Monday-00:00 pair lands in
     different ISO weeks; a year-boundary (week 1 / week 52-53) case too.
  2. Drill-through returns the exact underlying node rows for a rendered
     week bucket.
  3. Zero render-path egress — an outbound HTTP client patched to raise on
     call proves the warm-cache read path makes no external call.
  4. Absent-not-zero — the unimplemented ``reopened``/self-caught-ratio
     fields serialize as ``None``, never ``0``.

Structure mirrors ``test_intenttree_events_ingest.py``'s in-memory-SQLite
harness and ``test_system_metrics_cache_regression.py``'s ``CorePorts``
fixture construction (``build_core_ports``).

Run as a named module (full collection can hang in this repo):
    python3 -m pytest backend/tests/test_are_we_winning_rollups.py -v
"""
from __future__ import annotations

import json
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite

from backend import config
from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.are_we_winning import (
    AreWeWinningQueryService,
    _iso_week_bucket,
    _parse_occurred_at,
)
from backend.application.services.agent_queries.cache import clear_cache
from backend.db.repositories.intent_tree_events import SqliteIntentTreeEventsRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import AreWeWinningDrillThroughPageDTO, AreWeWinningSummaryDTO
from backend.runtime_ports import build_core_ports


# ── Shared fixture helpers (mirrors test_system_metrics_cache_regression.py) ─


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
        trace=TraceContext(request_id="req-1"),
    )


class _WorkspaceRegistry:
    def __init__(self, projects: list[Any]) -> None:
        self._projects = projects
        self._active = projects[0] if projects else None

    def list_projects(self) -> list[Any]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Any | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Any | None:
        return self._active

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, Any]:
        _ = project_id
        return None, None


def _make_project(project_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=project_id)


class _RaisingIntegrationClient:
    """Stand-in "outbound HTTP client" that raises on any call (AC3)."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "are_we_winning render path must never make an external call — "
            f"invoke() was called with args={args!r} kwargs={kwargs!r}"
        )


def _make_ports(db: Any, projects: list[Any] | None = None) -> CorePorts:
    real_ports = build_core_ports(
        db,
        workspace_registry=_WorkspaceRegistry(projects or [_make_project("project-1")]),
    )
    # Swap in a client that raises on any call, proving the warm-cache read
    # path below never reaches for it (AC3: zero render-path egress).
    return CorePorts(
        identity_provider=real_ports.identity_provider,
        authorization_policy=real_ports.authorization_policy,
        workspace_registry=real_ports.workspace_registry,
        storage=real_ports.storage,
        job_scheduler=real_ports.job_scheduler,
        integration_client=_RaisingIntegrationClient(),
    )


async def _insert_event(
    repo: SqliteIntentTreeEventsRepository,
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    node_id: str = "node-1",
    title: str | None = None,
) -> None:
    payload_json = json.dumps({"title": title}) if title is not None else None
    await repo.insert_if_not_exists(
        {
            "id": event_id,
            "workspace_id": "ws-test",
            "tree_id": "tree-test",
            "node_id": node_id,
            "event_type": event_type,
            "actor_type": "system",
            "actor_id": None,
            "occurred_at": occurred_at,
            "payload_json": payload_json,
        }
    )


class _AsyncSqliteHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteIntentTreeEventsRepository(self.db)
        self.ports = _make_ports(self.db)
        self.service = AreWeWinningQueryService()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()


# ── AC1: ISO-week bucket boundary ───────────────────────────────────────────


class IsoWeekBoundaryTests(unittest.TestCase):
    def test_sunday_2359_and_following_monday_0000_land_in_different_iso_weeks(self) -> None:
        monday = date.fromisocalendar(2026, 34, 1)
        sunday_before = monday - timedelta(days=1)

        sunday_dt = _parse_occurred_at(f"{sunday_before.isoformat()}T23:59:00.000000Z")
        monday_dt = _parse_occurred_at(f"{monday.isoformat()}T00:00:00.000000Z")
        assert sunday_dt is not None and monday_dt is not None

        sunday_bucket = _iso_week_bucket(sunday_dt)
        monday_bucket = _iso_week_bucket(monday_dt)

        self.assertNotEqual(
            (sunday_bucket[0], sunday_bucket[1]),
            (monday_bucket[0], monday_bucket[1]),
            "a Sunday 23:59 event and the following Monday 00:00 event must "
            "bucket into different ISO weeks",
        )
        self.assertEqual(sunday_bucket[:2], sunday_before.isocalendar()[:2])
        self.assertEqual(monday_bucket[:2], monday.isocalendar()[:2])

    def test_year_boundary_case_iso_week_1_vs_week_52_53(self) -> None:
        # 2026-12-31 and 2027-01-01 straddle the ISO year boundary. Whichever
        # side of week 1 / week 52-53 each date lands on is derived from the
        # stdlib isocalendar(), not hardcoded here -- this asserts our
        # bucketing function agrees with it, and that the two dates differ.
        dec_31 = date(2026, 12, 31)
        jan_1 = date(2027, 1, 1)

        dec_31_dt = _parse_occurred_at("2026-12-31T12:00:00.000000Z")
        jan_1_dt = _parse_occurred_at("2027-01-01T12:00:00.000000Z")
        assert dec_31_dt is not None and jan_1_dt is not None

        dec_31_bucket = _iso_week_bucket(dec_31_dt)
        jan_1_bucket = _iso_week_bucket(jan_1_dt)

        # The bucketing function must delegate to isocalendar(), not derive
        # iso_year from dt.year -- 2026 has 53 ISO weeks, so 2027-01-01 (a
        # Friday) belongs to ISO week 53 of ISO *year* 2026, not week 1 of
        # 2027. A naive "iso_year = dt.year" implementation would get this
        # wrong. Assert both the exact match against the stdlib and the
        # calendar-year/ISO-year divergence itself.
        self.assertEqual(dec_31_bucket[:2], dec_31.isocalendar()[:2])
        self.assertEqual(jan_1_bucket[:2], jan_1.isocalendar()[:2])
        self.assertEqual(jan_1_bucket[0], 2026, "2027-01-01 must fall in ISO year 2026")
        self.assertEqual(jan_1_bucket[1], 53, "2027-01-01 must fall in ISO week 52/53, not week 1")
        self.assertNotEqual(
            jan_1_bucket[0],
            jan_1.year,
            "2027-01-01's ISO year must diverge from its calendar year "
            "(the year-boundary case this AC requires)",
        )
        # Same bucket as the day before it -- both fall in the trailing ISO
        # week of 2026, not a fresh "week 1".
        self.assertEqual((dec_31_bucket[0], dec_31_bucket[1]), (jan_1_bucket[0], jan_1_bucket[1]))


# ── AC2: drill-through returns real rows ────────────────────────────────────


class DrillThroughTests(_AsyncSqliteHarness):
    async def test_drill_through_returns_exactly_the_rows_behind_a_week_bucket(self) -> None:
        monday = date.fromisocalendar(2026, 34, 1)
        in_week_a = f"{monday.isoformat()}T09:00:00.000000Z"
        in_week_a_2 = f"{(monday.replace(day=monday.day + 2)).isoformat()}T09:00:00.000000Z"
        next_monday = monday.replace(day=monday.day + 7)
        in_week_b = f"{next_monday.isoformat()}T09:00:00.000000Z"

        await _insert_event(
            self.repo,
            event_id="evt-a1",
            event_type="node.created",
            occurred_at=in_week_a,
            node_id="node-a1",
            title="Node A1",
        )
        await _insert_event(
            self.repo,
            event_id="evt-a2",
            event_type="node.created",
            occurred_at=in_week_a_2,
            node_id="node-a2",
            title="Node A2",
        )
        await _insert_event(
            self.repo,
            event_id="evt-b1",
            event_type="node.created",
            occurred_at=in_week_b,
            node_id="node-b1",
            title="Node B1",
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            page = await self.service.get_drill_through(
                _context(),
                self.ports,
                event_type="node.created",
                iso_year=2026,
                iso_week=34,
            )

        self.assertIsInstance(page, AreWeWinningDrillThroughPageDTO)
        self.assertEqual(page.total, 2)
        node_ids = sorted(item.node_id for item in page.items)
        self.assertEqual(node_ids, ["node-a1", "node-a2"])
        titles = sorted(item.title for item in page.items)
        self.assertEqual(titles, ["Node A1", "Node A2"])
        for item in page.items:
            self.assertEqual(item.event_type, "node.created")

    async def test_drill_through_row_count_matches_the_trendline_count_for_the_same_bucket(
        self,
    ) -> None:
        monday = date.fromisocalendar(2026, 20, 1)
        occurred_at = f"{monday.isoformat()}T00:00:00.000000Z"
        for i in range(3):
            await _insert_event(
                self.repo,
                event_id=f"evt-completed-{i}",
                event_type="node.completed",
                occurred_at=occurred_at,
                node_id=f"node-{i}",
            )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)
            page = await self.service.get_drill_through(
                _context(),
                self.ports,
                event_type="node.completed",
                iso_year=2026,
                iso_week=20,
            )

        completed_point = next(
            p for p in summary.completed.points if (p.iso_year, p.iso_week) == (2026, 20)
        )
        self.assertEqual(completed_point.count, 3)
        self.assertEqual(page.total, 3)
        self.assertEqual(len(page.items), 3)


# ── AC3: zero render-path egress ────────────────────────────────────────────


class ZeroRenderPathEgressTests(_AsyncSqliteHarness):
    async def test_get_summary_never_touches_the_raising_integration_client(self) -> None:
        await _insert_event(
            self.repo,
            event_id="evt-1",
            event_type="node.created",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )

        # ports.integration_client.invoke() raises unconditionally (see
        # _RaisingIntegrationClient above). If get_summary ever reached for
        # it -- directly or indirectly -- this call would raise instead of
        # returning normally.
        result = await self.service.get_summary(_context(), self.ports)

        self.assertIsInstance(result, AreWeWinningSummaryDTO)

    async def test_get_drill_through_never_touches_the_raising_integration_client(self) -> None:
        await _insert_event(
            self.repo,
            event_id="evt-1",
            event_type="node.completed",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )
        monday = date(2026, 8, 10).isocalendar()

        result = await self.service.get_drill_through(
            _context(),
            self.ports,
            event_type="node.completed",
            iso_year=monday[0],
            iso_week=monday[1],
        )
        self.assertIsInstance(result, AreWeWinningDrillThroughPageDTO)


# ── AC4: absent-not-zero for the unimplemented part-B fields ────────────────


class AbsentNotZeroTests(_AsyncSqliteHarness):
    async def test_reopened_and_self_caught_ratio_serialize_as_null_never_zero(self) -> None:
        await _insert_event(
            self.repo,
            event_id="evt-1",
            event_type="node.created",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)

        self.assertIsNone(summary.reopened)
        self.assertIsNone(summary.self_caught_ratio)

        dumped = summary.model_dump(mode="json")
        self.assertIn("reopened", dumped)
        self.assertIsNone(dumped["reopened"])
        self.assertIn("self_caught_ratio", dumped)
        self.assertIsNone(dumped["self_caught_ratio"])
        # The never-a-fabricated-0 requirement, made explicit: neither field
        # is allowed to be the integer/float 0 or an empty-but-present shape.
        self.assertNotEqual(dumped["reopened"], 0)
        self.assertNotEqual(dumped["self_caught_ratio"], 0)


if __name__ == "__main__":
    unittest.main()
