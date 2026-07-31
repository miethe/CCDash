"""Unit tests for T3-001: ``RoutingRollupQueryService.fetch_raw_rows`` skeleton.

Covers this task's own acceptance criteria (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``,
Task T3-001):

  - Correct grouping: exactly one row per distinct
    ``(project_id, source_skill_name, model)`` combination present in a
    hand-built fixture window.
  - Zero N+1: a single SQL statement is issued for the whole aggregation
    call, regardless of the number of distinct keys in the fixture.
  - Window boundary is read from ``config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS``,
    not hardcoded.

T3-005 (not yet built as of this test file) owns the dedicated determinism
(``test_routing_rollup_determinism.py``) and no-LLM-import-guard
(``test_routing_rollup_no_llm_imports.py``) test files -- this file covers
only T3-001's own raw-aggregation contract.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite

from backend import config
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.routing_rollup import (
    RawRollupRow,
    RoutingRollupQueryService,
)
from backend.db.sqlite_migrations import run_migrations
from backend.runtime_ports import build_core_ports


# ---------------------------------------------------------------------------
# Shared helpers (mirrors backend/tests/test_system_metrics.py conventions)
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


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
    """Minimal workspace registry for unit tests (no projects needed --
    ``fetch_raw_rows`` reads directly from ``sessions``, not the registry)."""

    def list_projects(self) -> list[Any]:
        return []

    def get_project(self, project_id: str) -> Any | None:
        return None

    def get_active_project(self) -> Any | None:
        return None

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, Any]:
        return None, None


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    skill_name: str | None,
    model: str,
    updated_at: str,
    status: str = "completed",
) -> None:
    """Insert a minimal sessions row exercising the columns
    ``fetch_raw_rows`` groups/filters on."""
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, project_id, skill_name, model, status, updated_at, created_at, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, project_id, skill_name, model, status, updated_at, updated_at, f"{session_id}.jsonl"),
    )
    await db.commit()


class _RoutingRollupTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry())
        self.service = RoutingRollupQueryService()

    async def asyncTearDown(self) -> None:
        await self.db.close()


# ---------------------------------------------------------------------------
# AC: Correct grouping on a fixture DB
# ---------------------------------------------------------------------------

class TestCorrectGrouping(_RoutingRollupTestBase):
    async def test_one_row_per_distinct_key(self) -> None:
        """Two distinct keys, each with duplicate session rows, collapse to
        exactly one raw row per key with the correct session_count."""
        now = _iso(_now_utc())
        # key A: (proj-1, "planner", "sonnet-5") x3
        await _insert_session(self.db, session_id="a1", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=now)
        await _insert_session(self.db, session_id="a2", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=now)
        await _insert_session(self.db, session_id="a3", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=now)
        # key B: (proj-1, "debugger", "opus-5") x2
        await _insert_session(self.db, session_id="b1", project_id="proj-1", skill_name="debugger", model="opus-5", updated_at=now)
        await _insert_session(self.db, session_id="b2", project_id="proj-1", skill_name="debugger", model="opus-5", updated_at=now)

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 2, "expected exactly one row per distinct key")
        by_key = {(r.project_id, r.source_skill_name, r.model): r for r in rows}
        self.assertIn(("proj-1", "planner", "sonnet-5"), by_key)
        self.assertIn(("proj-1", "debugger", "opus-5"), by_key)
        self.assertEqual(by_key[("proj-1", "planner", "sonnet-5")].session_count, 3)
        self.assertEqual(by_key[("proj-1", "debugger", "opus-5")].session_count, 2)

    async def test_distinct_project_ids_are_separate_keys(self) -> None:
        """Same skill_name+model in two different projects yields two rows —
        project_id is part of the grain, never collapsed across projects."""
        now = _iso(_now_utc())
        await _insert_session(self.db, session_id="p1a", project_id="proj-a", skill_name="planner", model="sonnet-5", updated_at=now)
        await _insert_session(self.db, session_id="p1b", project_id="proj-b", skill_name="planner", model="sonnet-5", updated_at=now)

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 2)
        project_ids = {r.project_id for r in rows}
        self.assertEqual(project_ids, {"proj-a", "proj-b"})

    async def test_project_ids_filter_scopes_result(self) -> None:
        """An explicit project_ids filter excludes non-matching projects
        without collapsing or losing the matching key."""
        now = _iso(_now_utc())
        await _insert_session(self.db, session_id="s1", project_id="proj-keep", skill_name="planner", model="sonnet-5", updated_at=now)
        await _insert_session(self.db, session_id="s2", project_id="proj-drop", skill_name="planner", model="sonnet-5", updated_at=now)

        rows = await self.service.fetch_raw_rows(_context(), self.ports, project_ids=["proj-keep"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].project_id, "proj-keep")

    async def test_rows_outside_window_are_excluded(self) -> None:
        """A session well outside the default 30-day window is excluded from
        the aggregation entirely."""
        now = _now_utc()
        in_window = _iso(now)
        out_of_window = _iso(now - timedelta(days=45))

        await _insert_session(self.db, session_id="fresh", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=in_window)
        await _insert_session(self.db, session_id="stale", project_id="proj-1", skill_name="ancient-skill", model="opus-3", updated_at=out_of_window)

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        skill_names = {r.source_skill_name for r in rows}
        self.assertIn("planner", skill_names)
        self.assertNotIn("ancient-skill", skill_names)


# ---------------------------------------------------------------------------
# AC: Zero N+1 -- exactly one SQL statement regardless of fixture size
# ---------------------------------------------------------------------------

class TestZeroNPlusOne(_RoutingRollupTestBase):
    async def _seed_distinct_keys(self, n: int) -> None:
        now = _iso(_now_utc())
        for i in range(n):
            await _insert_session(
                self.db,
                session_id=f"s-{i}",
                project_id="proj-1",
                skill_name=f"skill-{i}",
                model="sonnet-5",
                updated_at=now,
            )

    async def _count_execute_calls(self) -> int:
        call_count = 0
        original_execute = self.db.execute

        def counting_execute(sql: str, parameters: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            return original_execute(sql, parameters)

        self.db.execute = counting_execute
        try:
            await self.service.fetch_raw_rows(_context(), self.ports)
        finally:
            self.db.execute = original_execute
        return call_count

    async def test_single_query_for_one_key(self) -> None:
        await self._seed_distinct_keys(1)
        self.assertEqual(await self._count_execute_calls(), 1)

    async def test_single_query_for_many_keys(self) -> None:
        await self._seed_distinct_keys(20)
        self.assertEqual(
            await self._count_execute_calls(),
            1,
            "aggregation must issue exactly one SQL statement regardless of key count",
        )

    async def test_query_count_invariant_across_n(self) -> None:
        for n in (1, 5, 15):
            with self.subTest(n=n):
                self.db.execute  # sanity: attribute exists before wrap
                await self._seed_distinct_keys(n)
                count = await self._count_execute_calls()
                self.assertEqual(count, 1, f"expected 1 query for N={n}, got {count}")


# ---------------------------------------------------------------------------
# AC: Window boundary read from config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS
# ---------------------------------------------------------------------------

class TestWindowBoundaryFromConfig(_RoutingRollupTestBase):
    async def test_window_respects_config_default(self) -> None:
        """A row 10 days old is included under the default 30-day window."""
        ten_days_ago = _iso(_now_utc() - timedelta(days=10))
        await _insert_session(self.db, session_id="s1", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=ten_days_ago)

        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        self.assertEqual(len(rows), 1)

    async def test_window_shrinks_when_config_overridden(self) -> None:
        """Shrinking CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS to 1 excludes a
        10-day-old row that the default 30-day window would include --
        proving the boundary is read from config, not hardcoded."""
        ten_days_ago = _iso(_now_utc() - timedelta(days=10))
        await _insert_session(self.db, session_id="s1", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=ten_days_ago)

        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS", 1):
            rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 0, "10-day-old row must be excluded by a 1-day window")

    async def test_window_days_override_param_takes_precedence(self) -> None:
        """The explicit window_days kwarg overrides config for a single call
        (test/worker convenience) without mutating global config."""
        ten_days_ago = _iso(_now_utc() - timedelta(days=10))
        await _insert_session(self.db, session_id="s1", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=ten_days_ago)

        rows = await self.service.fetch_raw_rows(_context(), self.ports, window_days=1)
        self.assertEqual(len(rows), 0)

        # Config itself is untouched.
        self.assertEqual(config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS, 30)


# ---------------------------------------------------------------------------
# Sanity: return type is the frozen RawRollupRow shape, not a dict/DTO.
# ---------------------------------------------------------------------------

class TestRawRowShape(_RoutingRollupTestBase):
    async def test_rows_are_raw_rollup_row_instances(self) -> None:
        now = _iso(_now_utc())
        await _insert_session(self.db, session_id="s1", project_id="proj-1", skill_name="planner", model="sonnet-5", updated_at=now)

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsInstance(row, RawRollupRow)
        # No mapping/provider/metric fields at this skeleton stage.
        for forbidden_field in ("task_class", "provider", "success_rate", "cost_index", "regression_rate", "confidence", "eligible_for_adjustment"):
            self.assertFalse(
                hasattr(row, forbidden_field),
                f"RawRollupRow must not carry '{forbidden_field}' -- that belongs to a later Phase 3 task",
            )


if __name__ == "__main__":
    unittest.main()
