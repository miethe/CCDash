"""Unit tests for DI-4c: the ``routing_rollup`` effort dimension.

Covers the three v45 columns end-to-end through the compute pipeline:

  - ``effort_tier`` / ``effort_tier_source`` are **unambiguous-or-null** --
    populated only when every tier-carrying session in the key agrees, ``None``
    when the key mixes values or carries none. Never a mode with a tiebreak
    (which would fabricate a winner, the failure ``cost_index`` already refuses
    per D-a2).
  - ``authoritative_effort_fraction`` is the additive trust companion: the
    fraction of the key's sessions whose ``effort_tier_source`` is in
    ``AUTHORITATIVE_EFFORT_SOURCES``. ``None`` only at zero samples; a genuine
    ``0.0`` means "checked, none authoritative" and is NOT the same state.
  - An unrecognised provenance token counts as non-authoritative rather than
    hard-failing (``effort_provenance.py``'s stated consumer contract).
  - The aggregation still issues exactly ONE SQL statement (the zero-N+1
    invariant DI-4c must not regress).

Reuses ``test_routing_rollup_aggregation.py``'s fixture conventions; the
``sessions`` table comes from the real ``run_migrations``, so ``effort_tier``/
``effort_tier_source`` exist and default to NULL when not inserted.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.routing_rollup import (
    RoutingRollupQueryService,
    _authoritative_effort_fraction,
    _unambiguous_or_none,
)
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.effort_provenance import (
    EFFORT_SOURCE_CLAUDE_SETTINGS,
    EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
    EFFORT_SOURCE_LAUNCH_ENV,
)
from backend.runtime_ports import build_core_ports


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
    project_id: str = "proj-1",
    skill_name: str = "planner",
    model: str = "sonnet-5",
    updated_at: str,
    effort_tier: str | None = None,
    effort_tier_source: str | None = None,
) -> None:
    """Insert a sessions row carrying the two Gap-4 effort columns."""
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, project_id, skill_name, model, status, updated_at, created_at,
             source_file, effort_tier, effort_tier_source)
        VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)
        """,
        (
            session_id, project_id, skill_name, model, updated_at, updated_at,
            f"{session_id}.jsonl", effort_tier, effort_tier_source,
        ),
    )
    await db.commit()


class _Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry())
        self.service = RoutingRollupQueryService()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _single_raw_row(self) -> Any:
        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        self.assertEqual(len(rows), 1, "fixture should produce exactly one key")
        return rows[0]

    async def _single_key_dto(self) -> Any:
        raw = await self.service.fetch_raw_rows(_context(), self.ports)
        mapped = self.service.apply_mapping(raw)
        provider = self.service.apply_provider(mapped)
        dtos = self.service.compute_metrics(provider)
        self.assertEqual(len(dtos), 1, "fixture should produce exactly one DTO")
        return dtos[0]


# ── Pure helper semantics ───────────────────────────────────────────────────


class UnambiguousOrNoneTests(unittest.TestCase):
    def test_single_distinct_value_resolves(self) -> None:
        self.assertEqual(_unambiguous_or_none(1, "high"), "high")

    def test_multiple_distinct_values_resolve_to_none(self) -> None:
        """A mixed key is genuinely ambiguous -- never a tiebroken mode."""
        self.assertIsNone(_unambiguous_or_none(2, "high"))
        self.assertIsNone(_unambiguous_or_none(4, "medium"))

    def test_zero_distinct_values_resolve_to_none(self) -> None:
        self.assertIsNone(_unambiguous_or_none(0, None))

    def test_null_and_blank_candidate_resolve_to_none(self) -> None:
        self.assertIsNone(_unambiguous_or_none(1, None))
        self.assertIsNone(_unambiguous_or_none(1, "   "))

    def test_none_distinct_count_is_treated_as_zero(self) -> None:
        """PostgreSQL/SQLite can both hand back NULL for an empty aggregate."""
        self.assertIsNone(_unambiguous_or_none(None, "high"))


class AuthoritativeEffortFractionTests(unittest.TestCase):
    def test_zero_samples_is_none_not_zero(self) -> None:
        """None == nothing to characterize; 0.0 == checked, none authoritative."""
        self.assertIsNone(_authoritative_effort_fraction(0, 0))

    def test_genuine_zero_is_a_real_float(self) -> None:
        self.assertEqual(_authoritative_effort_fraction(0, 4), 0.0)

    def test_full_and_partial_coverage(self) -> None:
        self.assertEqual(_authoritative_effort_fraction(4, 4), 1.0)
        self.assertEqual(_authoritative_effort_fraction(1, 4), 0.25)


# ── SQL aggregation semantics ───────────────────────────────────────────────


class EffortAggregationTests(_Base):
    async def test_unanimous_key_carries_tier_and_source(self) -> None:
        now = _iso(_now_utc())
        for sid in ("s1", "s2", "s3"):
            await _insert_session(
                self.db, session_id=sid, updated_at=now,
                effort_tier="high", effort_tier_source=EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
            )

        row = await self._single_raw_row()
        self.assertEqual(row.effort_tier, "high")
        self.assertEqual(row.effort_tier_source, EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT)
        self.assertEqual(row.effort_authoritative_count, 3)

    async def test_mixed_tiers_null_the_tier_but_keep_the_fraction(self) -> None:
        """The key is ambiguous, but its provenance quality is still knowable."""
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="s1", updated_at=now,
            effort_tier="high", effort_tier_source=EFFORT_SOURCE_LAUNCH_ENV,
        )
        await _insert_session(
            self.db, session_id="s2", updated_at=now,
            effort_tier="medium", effort_tier_source=EFFORT_SOURCE_LAUNCH_ENV,
        )

        row = await self._single_raw_row()
        self.assertIsNone(row.effort_tier, "mixed tiers must resolve to None")
        self.assertEqual(
            row.effort_tier_source, EFFORT_SOURCE_LAUNCH_ENV,
            "source is unanimous even though the tier is not -- resolved independently",
        )
        self.assertEqual(row.effort_authoritative_count, 2)

    async def test_absent_effort_columns_resolve_to_null_and_zero(self) -> None:
        now = _iso(_now_utc())
        await _insert_session(self.db, session_id="s1", updated_at=now)
        await _insert_session(self.db, session_id="s2", updated_at=now)

        row = await self._single_raw_row()
        self.assertIsNone(row.effort_tier)
        self.assertIsNone(row.effort_tier_source)
        self.assertEqual(row.effort_authoritative_count, 0)

    async def test_null_tiers_are_excluded_not_counted_as_a_distinct_value(self) -> None:
        """COUNT(DISTINCT) ignores NULLs, so one real tier + NULLs stays unambiguous."""
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="s1", updated_at=now,
            effort_tier="xhigh", effort_tier_source=EFFORT_SOURCE_LAUNCH_ENV,
        )
        await _insert_session(self.db, session_id="s2", updated_at=now)

        row = await self._single_raw_row()
        self.assertEqual(row.effort_tier, "xhigh")
        self.assertEqual(row.session_count, 2)
        self.assertEqual(
            row.effort_authoritative_count, 1,
            "only the tier-carrying session is authoritative; the NULL one is not",
        )

    async def test_non_authoritative_source_is_excluded_from_the_count(self) -> None:
        """claude_settings is a stale-able snapshot -- real, but not authoritative."""
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="s1", updated_at=now,
            effort_tier="medium", effort_tier_source=EFFORT_SOURCE_CLAUDE_SETTINGS,
        )

        row = await self._single_raw_row()
        self.assertEqual(row.effort_tier_source, EFFORT_SOURCE_CLAUDE_SETTINGS)
        self.assertEqual(row.effort_authoritative_count, 0)

    async def test_unknown_token_counts_as_non_authoritative_never_raises(self) -> None:
        """effort_provenance.py's contract: unknown == unknown provenance, no hard-fail."""
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="s1", updated_at=now,
            effort_tier="high", effort_tier_source="some_future_lane_v9",
        )

        row = await self._single_raw_row()
        self.assertEqual(row.effort_tier_source, "some_future_lane_v9")
        self.assertEqual(row.effort_authoritative_count, 0)

    async def test_distinct_keys_do_not_bleed_effort_into_each_other(self) -> None:
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="a1", skill_name="planner", updated_at=now,
            effort_tier="high", effort_tier_source=EFFORT_SOURCE_LAUNCH_ENV,
        )
        await _insert_session(
            self.db, session_id="b1", skill_name="debugger", updated_at=now,
            effort_tier="low", effort_tier_source=EFFORT_SOURCE_CLAUDE_SETTINGS,
        )

        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        by_skill = {r.source_skill_name: r for r in rows}
        self.assertEqual(by_skill["planner"].effort_tier, "high")
        self.assertEqual(by_skill["planner"].effort_authoritative_count, 1)
        self.assertEqual(by_skill["debugger"].effort_tier, "low")
        self.assertEqual(by_skill["debugger"].effort_authoritative_count, 0)

    async def test_effort_aggregation_adds_no_extra_query(self) -> None:
        """Zero-N+1 invariant: still exactly one statement for the whole call."""
        now = _iso(_now_utc())
        for sid, skill in (("a1", "planner"), ("b1", "debugger"), ("c1", "reviewer")):
            await _insert_session(
                self.db, session_id=sid, skill_name=skill, updated_at=now,
                effort_tier="high", effort_tier_source=EFFORT_SOURCE_LAUNCH_ENV,
            )

        executed: list[str] = []
        original = self.db.execute

        def _spy(sql: str, *args: Any, **kwargs: Any) -> Any:
            executed.append(sql)
            return original(sql, *args, **kwargs)

        self.db.execute = _spy  # type: ignore[method-assign]
        try:
            await self.service.fetch_raw_rows(_context(), self.ports)
        finally:
            self.db.execute = original  # type: ignore[method-assign]

        self.assertEqual(
            len(executed), 1, f"expected exactly one statement, got {len(executed)}"
        )


# ── Terminal DTO wiring ─────────────────────────────────────────────────────


class EffortDtoTests(_Base):
    async def test_dto_carries_tier_source_and_fraction(self) -> None:
        now = _iso(_now_utc())
        for sid in ("s1", "s2", "s3", "s4"):
            await _insert_session(
                self.db, session_id=sid, updated_at=now,
                effort_tier="high",
                effort_tier_source=(
                    EFFORT_SOURCE_LAUNCH_ENV if sid in ("s1", "s2", "s3")
                    else EFFORT_SOURCE_CLAUDE_SETTINGS
                ),
            )

        dto = await self._single_key_dto()
        self.assertEqual(dto.effort_tier, "high")
        self.assertIsNone(
            dto.effort_tier_source, "two distinct sources -- ambiguous, so None"
        )
        self.assertEqual(dto.authoritative_effort_fraction, 0.75)

    async def test_dto_fraction_is_genuine_zero_when_nothing_authoritative(self) -> None:
        now = _iso(_now_utc())
        await _insert_session(
            self.db, session_id="s1", updated_at=now,
            effort_tier="medium", effort_tier_source=EFFORT_SOURCE_CLAUDE_SETTINGS,
        )

        dto = await self._single_key_dto()
        self.assertEqual(
            dto.authoritative_effort_fraction, 0.0,
            "0.0 means checked-and-none-authoritative, never 'no data'",
        )
        self.assertIsNotNone(dto.authoritative_effort_fraction)

    async def test_dto_nulls_effort_without_suppressing_the_row(self) -> None:
        """Absent effort is a contract state -- the key is still emitted."""
        now = _iso(_now_utc())
        await _insert_session(self.db, session_id="s1", updated_at=now)

        dto = await self._single_key_dto()
        self.assertIsNone(dto.effort_tier)
        self.assertIsNone(dto.effort_tier_source)
        self.assertEqual(dto.authoritative_effort_fraction, 0.0)
        self.assertEqual(dto.sample_count, 1)


if __name__ == "__main__":
    unittest.main()
