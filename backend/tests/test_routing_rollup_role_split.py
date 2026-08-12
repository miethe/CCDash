"""Unit tests for DI-1 node 1: the ``routing_rollup`` role-aware ``task_class``
mapping.

``dev-execution`` is DUAL-ROLE -- the orchestrator loads it
(``/dev:execute-phase``, ``/dev:execute-plan``) and so do the implementer legs
it dispatches. Keying ``task_class`` on ``sessions.skill_name`` alone therefore
folded MUST-stay orchestration spend into the demotable ``implementation``
class (measured 2026-08-11: 164 orchestrator-role Opus sessions, 8.4% of them,
carried 62.4% of all Opus ``dev-execution`` cost). This file covers the fix:

  - The aggregation grain gains an internal ``source_role`` dimension --
    ``orchestrator`` iff the session is referenced as some other session's
    ``subagent_parent_id``, ``implementer`` otherwise -- for role-split skills
    ONLY. Every other skill still yields ``source_role IS NULL`` and exactly one
    group per ``(project_id, skill_name, model)``: the pre-split grain,
    byte-identical.
  - An orchestrator-role row resolves to ``orchestration`` (protected), so its
    cost and sample_count never reach the ``implementation`` row for the same
    ``(project, skill, model)``. Implementer-role rows still resolve to
    ``implementation``. Since schema v54 added ``task_class`` to the persisted
    natural key, both rows PERSIST side by side (they are no longer UPSERT
    duplicates), so per-role telemetry is durable -- the AC1 guarantee comes
    from the role GROUPING, not from suppressing the orchestrator row.
  - The ``session_parents`` LEFT JOIN never fans out (``DISTINCT`` on
    ``(project_id, parent_id)``) -- a parent with N subagents is still counted
    exactly once.
  - ``_resolve_task_class`` falls back to the role-blind ``by_skill`` lookup
    whenever the role is ``None`` or the rule does not declare that role token.
    The role lane is strictly additive; it can never unclassify a skill that
    previously resolved.
  - A load-time contract guard rejects a mapping rule whose ``roles`` declare
    more than one NON-protected target, because the persisted natural key
    (``(project_id, source_skill_name, model, task_class)`` since schema v54)
    does not carry ``source_role`` -- two roles resolving to the SAME
    non-protected ``task_class`` would still collide.
  - ``source_role`` is an internal pipeline dimension only: it is absent from
    the persisted column tuple and from the emitted DTO/envelope.
  - The zero-N+1 invariant holds: still exactly ONE SQL statement.

Reuses ``test_routing_rollup_effort_dimension.py``'s fixture conventions; the
``sessions`` table comes from the real ``run_migrations``, so
``subagent_parent_id`` exists and defaults to NULL when not inserted.

Run as a named module (full collection can hang -- see the repo-wide
pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_role_split.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.adapters.jobs.routing_rollup_sweep_job import _build_routing_rollup_row
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries import routing_feedback_contract
from backend.application.services.agent_queries.routing_rollup import (
    PROTECTED_TASK_CLASSES,
    ROLE_IMPLEMENTER,
    ROLE_ORCHESTRATOR,
    UNCLASSIFIED_TASK_CLASS,
    MappedRollupRow,
    RoutingRollupQueryService,
    _load_skill_to_task_class_mapping,
    _resolve_task_class,
)
from backend.db.repositories.routing_rollup import (
    ROUTING_ROLLUP_COLUMNS,
    SqliteRoutingRollupRepository,
)
from backend.db.sqlite_migrations import run_migrations
from backend.runtime_ports import build_core_ports

#: The one role-split skill in the pinned v1 mapping.
ROLE_SPLIT_SKILL = "dev-execution"
#: A non-role-split skill, used as the "grain unchanged" regression control.
CONTROL_SKILL = "ccdash"
CONTROL_TASK_CLASS = "mechanical"
#: A NON-role-split PROTECTED skill -- the blast-radius control. It must keep
#: emitting its coverage-only row under the default flag; the role-split gate
#: exception must not touch it.
PROTECTED_CONTROL_SKILL = "release"
PROTECTED_CONTROL_TASK_CLASS = "mode_d"

ORCHESTRATOR_TASK_CLASS = "orchestration"
IMPLEMENTER_TASK_CLASS = "implementation"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _context(project_id: str = "proj-1") -> RequestContext:
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


class _DbBase(unittest.IsolatedAsyncioTestCase):
    """DB-backed base: real migrations, real single-statement aggregation."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry())
        self.service = RoutingRollupQueryService()
        self.now = _now_utc()
        self.ts = _iso(self.now)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _insert_session(
        self,
        *,
        session_id: str,
        skill_name: str = ROLE_SPLIT_SKILL,
        project_id: str = "proj-1",
        model: str = "claude-opus-5",
        subagent_parent_id: str | None = None,
        total_cost: float = 0.0,
        updated_at: str | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO sessions
                (id, project_id, skill_name, model, status, updated_at, created_at,
                 source_file, subagent_parent_id, total_cost)
            VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                project_id,
                skill_name,
                model,
                updated_at or self.ts,
                updated_at or self.ts,
                f"{session_id}.jsonl",
                subagent_parent_id,
                total_cost,
            ),
        )
        await self.db.commit()

    async def _raw_rows_by_role(self) -> dict[tuple[str, str | None], Any]:
        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        return {(row.source_skill_name, row.source_role): row for row in rows}


# ---------------------------------------------------------------------------
# Role classification: the discriminator predicate itself.
# ---------------------------------------------------------------------------


class TestRoleClassification(_DbBase):
    async def test_session_that_parents_a_subagent_is_orchestrator(self) -> None:
        await self._insert_session(session_id="parent")
        await self._insert_session(session_id="child", subagent_parent_id="parent")

        by_role = await self._raw_rows_by_role()

        self.assertIn((ROLE_SPLIT_SKILL, ROLE_ORCHESTRATOR), by_role)
        self.assertEqual(by_role[(ROLE_SPLIT_SKILL, ROLE_ORCHESTRATOR)].session_count, 1)

    async def test_session_that_is_itself_a_child_is_implementer(self) -> None:
        """Being a child is NOT the discriminator -- parenting one is. A child
        that parents nobody reads ``implementer``, which is the whole point:
        the implementer legs are exactly the sessions we still want feeding
        ``implementation``.
        """
        await self._insert_session(session_id="parent")
        await self._insert_session(session_id="child", subagent_parent_id="parent")

        by_role = await self._raw_rows_by_role()

        implementer = by_role[(ROLE_SPLIT_SKILL, ROLE_IMPLEMENTER)]
        self.assertEqual(implementer.session_count, 1, "only the child is an implementer")

    async def test_session_that_neither_parents_nor_is_parented_is_implementer(self) -> None:
        """``role_discriminator.default_role`` -- coverage is TOTAL, so a
        standalone session is never left roleless.
        """
        await self._insert_session(session_id="solo")

        by_role = await self._raw_rows_by_role()

        self.assertEqual(list(by_role), [(ROLE_SPLIT_SKILL, ROLE_IMPLEMENTER)])
        self.assertEqual(by_role[(ROLE_SPLIT_SKILL, ROLE_IMPLEMENTER)].session_count, 1)

    async def test_orchestrator_with_many_subagents_is_counted_once(self) -> None:
        """The ``session_parents`` CTE's ``DISTINCT`` is load-bearing: without
        it the LEFT JOIN fans out one row per child and multiplies both
        ``session_count`` and ``cost_sum``.
        """
        await self._insert_session(session_id="parent", total_cost=100.0)
        for index in range(4):
            await self._insert_session(
                session_id=f"child-{index}", subagent_parent_id="parent", total_cost=1.0
            )

        by_role = await self._raw_rows_by_role()

        orchestrator = by_role[(ROLE_SPLIT_SKILL, ROLE_ORCHESTRATOR)]
        self.assertEqual(orchestrator.session_count, 1)
        self.assertEqual(orchestrator.cost_sum, 100.0)
        self.assertEqual(orchestrator.cost_covered_count, 1)

    async def test_parent_in_another_project_does_not_promote_to_orchestrator(self) -> None:
        """``sessions``' PK is the composite ``(project_id, id)``, so the join
        must be scoped by BOTH -- a same-id parent reference in a different
        project must not leak across.
        """
        await self._insert_session(session_id="shared-id", project_id="proj-1")
        await self._insert_session(
            session_id="child", project_id="proj-2", subagent_parent_id="shared-id"
        )

        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        by_project = {(row.project_id, row.source_role): row for row in rows}

        self.assertEqual(by_project[("proj-1", ROLE_IMPLEMENTER)].session_count, 1)
        self.assertNotIn(("proj-1", ROLE_ORCHESTRATOR), by_project)


# ---------------------------------------------------------------------------
# AC1: orchestrator-role spend never reaches the surviving `implementation` row.
# ---------------------------------------------------------------------------


class TestOrchestratorSpendExcludedFromImplementation(_DbBase):
    async def _mixed_fixture(self) -> None:
        """One expensive orchestrator + three cheap implementer legs, all one
        ``(project_id, skill_name, model)`` key -- the shape the measurement
        found in production.
        """
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        await self._insert_session(
            session_id="leg-1", subagent_parent_id="orchestrator", total_cost=9.0
        )
        await self._insert_session(
            session_id="leg-2", subagent_parent_id="orchestrator", total_cost=11.0
        )
        await self._insert_session(session_id="leg-3", total_cost=13.0)

    async def test_implementation_row_excludes_orchestrator_cost_and_samples(self) -> None:
        await self._mixed_fixture()
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=False)

        self.assertEqual(len(mapped), 1, "only the implementer-role row survives")
        surviving = mapped[0]
        self.assertEqual(surviving.task_class, IMPLEMENTER_TASK_CLASS)
        self.assertEqual(surviving.source_role, ROLE_IMPLEMENTER)
        self.assertEqual(surviving.session_count, 3)
        self.assertEqual(surviving.cost_sum, 33.0)
        self.assertNotIn(178.0, (surviving.cost_sum,))

    async def test_orchestrator_row_is_dropped_as_protected(self) -> None:
        await self._mixed_fixture()
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=False)

        self.assertNotIn(ORCHESTRATOR_TASK_CLASS, {row.task_class for row in mapped})
        self.assertIn(
            ORCHESTRATOR_TASK_CLASS,
            PROTECTED_TASK_CLASSES,
            "the drop must come from the EXISTING protected-class gate, not a role special case",
        )

    async def test_both_role_rows_are_emitted_when_protected_rows_included(self) -> None:
        """Under ``include_protected_rows=True`` BOTH role rows survive.

        ``include_protected_rows`` defaults to ``True``, and since schema v54
        widened the persisted natural key to
        ``(project_id, source_skill_name, model, task_class)`` the orchestrator
        row is no longer an UPSERT duplicate of its implementer sibling -- so
        the protected-class gate is the ONLY gate, and a role-split skill now
        persists per-role telemetry: ``implementation`` (routable) alongside
        ``orchestration`` (coverage-only). AC1 is unaffected: the split is what
        keeps the orchestrator's cost and samples out of the implementation row,
        and that is asserted here on the same numbers as before.
        """
        await self._mixed_fixture()
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=True)

        by_class = {row.task_class: row for row in mapped}
        self.assertEqual(
            set(by_class), {IMPLEMENTER_TASK_CLASS, ORCHESTRATOR_TASK_CLASS}
        )
        self.assertEqual(len(mapped), 2, f"one row per role, got {mapped}")

        implementation = by_class[IMPLEMENTER_TASK_CLASS]
        self.assertEqual(implementation.cost_sum, 33.0)
        self.assertEqual(implementation.session_count, 3)
        self.assertFalse(implementation.is_coverage_only)
        self.assertEqual(implementation.source_role, ROLE_IMPLEMENTER)

        orchestration = by_class[ORCHESTRATOR_TASK_CLASS]
        self.assertEqual(orchestration.cost_sum, 178.0, "orchestrator spend, kept separate")
        self.assertEqual(orchestration.session_count, 1)
        self.assertTrue(orchestration.is_coverage_only, "protected class is coverage-only")
        self.assertEqual(orchestration.source_role, ROLE_ORCHESTRATOR)

    async def test_both_role_rows_are_emitted_under_shipped_default_config(self) -> None:
        """Same assertion via the no-kwarg call the sweep job actually makes,
        so the contract cannot be satisfied by a test-only flag override.
        """
        await self._mixed_fixture()
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw)

        by_class = {row.task_class: row for row in mapped}
        self.assertEqual(
            set(by_class), {IMPLEMENTER_TASK_CLASS, ORCHESTRATOR_TASK_CLASS}
        )
        self.assertEqual(by_class[IMPLEMENTER_TASK_CLASS].cost_sum, 33.0)
        self.assertEqual(by_class[ORCHESTRATOR_TASK_CLASS].cost_sum, 178.0)

    async def test_implementer_rows_still_resolve_to_implementation(self) -> None:
        """No orchestrator anywhere in the fixture: the skill behaves exactly
        as it did before the split.
        """
        await self._insert_session(session_id="solo-1", total_cost=4.0)
        await self._insert_session(session_id="solo-2", total_cost=6.0)
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=False)

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].task_class, IMPLEMENTER_TASK_CLASS)
        self.assertFalse(mapped[0].is_coverage_only)
        self.assertEqual(mapped[0].session_count, 2)
        self.assertEqual(mapped[0].cost_sum, 10.0)

    async def test_source_role_survives_apply_provider(self) -> None:
        await self._mixed_fixture()
        raw = await self.service.fetch_raw_rows(_context(), self.ports)
        mapped = self.service.apply_mapping(raw)

        provider_rows = self.service.apply_provider(mapped)

        self.assertEqual(
            {row.task_class: row.source_role for row in provider_rows},
            {
                IMPLEMENTER_TASK_CLASS: ROLE_IMPLEMENTER,
                ORCHESTRATOR_TASK_CLASS: ROLE_ORCHESTRATOR,
            },
        )

    def test_apply_provider_passes_any_source_role_through(self) -> None:
        """The pass-through itself, exercised on a hand-built row so it holds
        even for a row shape the pipeline does not currently produce.
        """
        now = _now_utc()
        rows = [
            MappedRollupRow(
                project_id="proj-1",
                source_skill_name=ROLE_SPLIT_SKILL,
                model="claude-opus-5",
                session_count=1,
                window_start=now,
                window_end=now,
                task_class=ORCHESTRATOR_TASK_CLASS,
                is_coverage_only=True,
                source_role=ROLE_ORCHESTRATOR,
            )
        ]

        provider_rows = self.service.apply_provider(rows)

        self.assertEqual([row.source_role for row in provider_rows], [ROLE_ORCHESTRATOR])


# ---------------------------------------------------------------------------
# Regression: a non-role-split skill's grain and values are unchanged.
# ---------------------------------------------------------------------------


class TestNonRoleSplitSkillGrainUnchanged(_DbBase):
    async def test_control_skill_yields_null_role_and_one_group(self) -> None:
        """``ccdash`` -> ``mechanical`` has no ``roles`` object, so it must
        collapse to ONE group with ``source_role is None`` even when the
        fixture contains a parent/child pair that WOULD split a role-split
        skill.
        """
        await self._insert_session(
            session_id="ctl-parent", skill_name=CONTROL_SKILL, total_cost=2.0
        )
        await self._insert_session(
            session_id="ctl-child",
            skill_name=CONTROL_SKILL,
            subagent_parent_id="ctl-parent",
            total_cost=3.0,
        )
        await self._insert_session(
            session_id="ctl-solo", skill_name=CONTROL_SKILL, total_cost=5.0
        )

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 1, "grain must be identical to the pre-split grain")
        self.assertIsNone(rows[0].source_role)
        self.assertEqual(rows[0].session_count, 3)
        self.assertEqual(rows[0].cost_sum, 10.0)
        self.assertEqual(rows[0].cost_covered_count, 3)

    async def test_control_skill_task_class_unaffected(self) -> None:
        await self._insert_session(session_id="ctl", skill_name=CONTROL_SKILL)
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=False)

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].task_class, CONTROL_TASK_CLASS)
        self.assertIsNone(mapped[0].source_role)
        self.assertFalse(mapped[0].is_coverage_only)

    async def test_control_and_role_split_skills_coexist(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=50.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=5.0
        )
        await self._insert_session(
            session_id="ctl", skill_name=CONTROL_SKILL, total_cost=1.0
        )

        by_role = await self._raw_rows_by_role()

        self.assertEqual(
            set(by_role),
            {
                (ROLE_SPLIT_SKILL, ROLE_ORCHESTRATOR),
                (ROLE_SPLIT_SKILL, ROLE_IMPLEMENTER),
                (CONTROL_SKILL, None),
            },
        )

    async def test_null_skill_name_is_never_promoted_to_orchestrator(self) -> None:
        """A session with no ``skill_name`` at all must stay ``source_role
        IS NULL`` even when it parents a subagent -- the ``IN``-list test is
        the OUTER condition of the CASE precisely so this cannot happen.
        """
        await self.db.execute(
            """
            INSERT INTO sessions
                (id, project_id, skill_name, model, status, updated_at, created_at, source_file)
            VALUES ('anon', 'proj-1', NULL, 'claude-opus-5', 'completed', ?, ?, 'anon.jsonl')
            """,
            (self.ts, self.ts),
        )
        await self._insert_session(session_id="anon-child", subagent_parent_id="anon")

        rows = await self.service.fetch_raw_rows(_context(), self.ports)
        anon = [row for row in rows if row.source_skill_name == ""]

        self.assertEqual(len(anon), 1)
        self.assertIsNone(anon[0].source_role)


# ---------------------------------------------------------------------------
# `source_role` is internal: never persisted, never emitted.
# ---------------------------------------------------------------------------


class TestSourceRoleNotExposed(_DbBase):
    def test_source_role_absent_from_persisted_columns(self) -> None:
        self.assertNotIn("source_role", ROUTING_ROLLUP_COLUMNS)

    async def test_source_role_absent_from_emitted_dtos(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=20.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=2.0
        )
        raw = await self.service.fetch_raw_rows(_context(), self.ports)
        provider_rows = self.service.apply_provider(
            self.service.apply_mapping(raw, include_protected_rows=True)
        )

        dtos = self.service.compute_metrics(provider_rows)

        self.assertTrue(dtos)
        for dto in dtos:
            self.assertNotIn("source_role", dto.model_dump())


# ---------------------------------------------------------------------------
# Zero-N+1: the role dimension must not add a round-trip.
# ---------------------------------------------------------------------------


class TestSingleStatementInvariant(_DbBase):
    async def test_role_split_still_issues_exactly_one_statement(self) -> None:
        await self._insert_session(session_id="orchestrator")
        await self._insert_session(session_id="leg", subagent_parent_id="orchestrator")
        await self._insert_session(session_id="ctl", skill_name=CONTROL_SKILL)

        executed: list[str] = []
        original = self.db.execute

        def _spy(sql: str, *args: Any, **kwargs: Any) -> Any:
            executed.append(sql)
            return original(sql, *args, **kwargs)

        self.db.execute = _spy  # type: ignore[method-assign]
        try:
            rows = await self.service.fetch_raw_rows(_context(), self.ports)
        finally:
            self.db.execute = original  # type: ignore[method-assign]

        self.assertEqual(
            len(executed), 1, f"expected exactly one statement, got {len(executed)}"
        )
        self.assertEqual(len(rows), 3)


# ---------------------------------------------------------------------------
# `_resolve_task_class` unit semantics.
# ---------------------------------------------------------------------------


class TestResolveTaskClass(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = _load_skill_to_task_class_mapping()

    def test_role_none_falls_back_to_flat_lookup(self) -> None:
        """The pre-split behaviour, verbatim: the rule's own ``task_class``."""
        self.assertEqual(
            _resolve_task_class(ROLE_SPLIT_SKILL, self.mapping),
            IMPLEMENTER_TASK_CLASS,
        )
        self.assertEqual(
            _resolve_task_class(ROLE_SPLIT_SKILL, self.mapping, role=None),
            IMPLEMENTER_TASK_CLASS,
        )

    def test_orchestrator_role_resolves_to_orchestration(self) -> None:
        self.assertEqual(
            _resolve_task_class(ROLE_SPLIT_SKILL, self.mapping, role=ROLE_ORCHESTRATOR),
            ORCHESTRATOR_TASK_CLASS,
        )

    def test_implementer_role_resolves_to_implementation(self) -> None:
        self.assertEqual(
            _resolve_task_class(ROLE_SPLIT_SKILL, self.mapping, role=ROLE_IMPLEMENTER),
            IMPLEMENTER_TASK_CLASS,
        )

    def test_unknown_role_token_falls_back_to_flat_lookup(self) -> None:
        """Resilience-by-default: an unrecognised role must degrade to the
        role-blind class, never to ``_unclassified``.
        """
        self.assertEqual(
            _resolve_task_class(ROLE_SPLIT_SKILL, self.mapping, role="reviewer"),
            IMPLEMENTER_TASK_CLASS,
        )

    def test_role_on_non_role_split_skill_falls_back_to_flat_lookup(self) -> None:
        self.assertEqual(
            _resolve_task_class(CONTROL_SKILL, self.mapping, role=ROLE_ORCHESTRATOR),
            CONTROL_TASK_CLASS,
        )

    def test_unmapped_skill_is_unclassified_with_and_without_role(self) -> None:
        for role in (None, ROLE_ORCHESTRATOR, ROLE_IMPLEMENTER):
            with self.subTest(role=role):
                self.assertEqual(
                    _resolve_task_class("totally-unmapped-skill-zzz", self.mapping, role=role),
                    UNCLASSIFIED_TASK_CLASS,
                )

    def test_role_split_skills_set_matches_role_keys(self) -> None:
        self.assertEqual(
            self.mapping.role_split_skills,
            {skill for skill, _role in self.mapping.by_skill_role},
        )
        self.assertIn(ROLE_SPLIT_SKILL, self.mapping.role_split_skills)
        self.assertNotIn(CONTROL_SKILL, self.mapping.role_split_skills)


# ---------------------------------------------------------------------------
# Load-time contract guard on `roles`.
# ---------------------------------------------------------------------------


class TestRoleTargetGuard(unittest.TestCase):
    """The guard that keeps the persisted natural key resolvable.

    ``(project_id, source_skill_name, model)`` does not carry ``source_role``,
    so at most one of a role-split key's rows may be a non-protected
    (i.e. emittable-as-a-routing-key) class.
    """

    def setUp(self) -> None:
        self._original_path = routing_feedback_contract.MAPPING_JSON_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        _load_skill_to_task_class_mapping.cache_clear()

    def tearDown(self) -> None:
        routing_feedback_contract.MAPPING_JSON_PATH = self._original_path
        self._tmpdir.cleanup()
        # Never leave a test-authored mapping in the process-wide cache.
        _load_skill_to_task_class_mapping.cache_clear()

    def _load_with_roles(self, roles: dict[str, str]) -> Any:
        payload = {
            "rules": [
                {
                    "source_skill_name": "fixture-skill",
                    "task_class": "implementation",
                    "roles": roles,
                }
            ]
        }
        path = Path(self._tmpdir.name) / "mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        routing_feedback_contract.MAPPING_JSON_PATH = path
        _load_skill_to_task_class_mapping.cache_clear()
        return _load_skill_to_task_class_mapping()

    def test_two_non_protected_role_targets_raises_naming_the_rule(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._load_with_roles(
                {"orchestrator": "implementation", "implementer": "mechanical"}
            )

        message = str(caught.exception)
        self.assertIn("fixture-skill", message)
        self.assertIn("implementation", message)
        self.assertIn("mechanical", message)

    def test_one_non_protected_plus_one_protected_is_accepted(self) -> None:
        mapping = self._load_with_roles(
            {"orchestrator": "orchestration", "implementer": "implementation"}
        )

        self.assertEqual(
            mapping.by_skill_role,
            {
                ("fixture-skill", "orchestrator"): "orchestration",
                ("fixture-skill", "implementer"): "implementation",
            },
        )

    def test_all_protected_role_targets_is_accepted(self) -> None:
        mapping = self._load_with_roles(
            {"orchestrator": "orchestration", "implementer": "mode_d"}
        )

        self.assertEqual(mapping.role_split_skills, frozenset({"fixture-skill"}))

    def test_duplicate_non_protected_target_across_roles_is_accepted(self) -> None:
        """Two roles pointing at the SAME non-protected class is one distinct
        target, so it cannot collide -- the guard counts distinct classes, not
        role entries.
        """
        mapping = self._load_with_roles(
            {"orchestrator": "implementation", "implementer": "implementation"}
        )

        self.assertEqual(len(mapping.by_skill_role), 2)

    def test_rule_without_roles_is_not_role_split(self) -> None:
        payload = {
            "rules": [{"source_skill_name": "plain-skill", "task_class": "mechanical"}]
        }
        path = Path(self._tmpdir.name) / "plain.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        routing_feedback_contract.MAPPING_JSON_PATH = path
        _load_skill_to_task_class_mapping.cache_clear()

        mapping = _load_skill_to_task_class_mapping()

        self.assertEqual(mapping.by_skill, {"plain-skill": "mechanical"})
        self.assertEqual(mapping.by_skill_role, {})
        self.assertEqual(mapping.role_split_skills, frozenset())


# ---------------------------------------------------------------------------
# Empty role-split set: no invalid `IN ()`, grain identical to pre-split.
# ---------------------------------------------------------------------------


class TestNoRoleSplitRulesFallback(_DbBase):
    """When NO rule declares ``roles`` the SQL must omit the ``session_parents``
    CTE entirely rather than emit ``IN ()``, and every row's ``source_role``
    must be ``None``.
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._original_path = routing_feedback_contract.MAPPING_JSON_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        payload = {
            "rules": [
                {"source_skill_name": ROLE_SPLIT_SKILL, "task_class": IMPLEMENTER_TASK_CLASS},
                {"source_skill_name": CONTROL_SKILL, "task_class": CONTROL_TASK_CLASS},
            ]
        }
        path = Path(self._tmpdir.name) / "no-roles.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        routing_feedback_contract.MAPPING_JSON_PATH = path
        _load_skill_to_task_class_mapping.cache_clear()

    async def asyncTearDown(self) -> None:
        routing_feedback_contract.MAPPING_JSON_PATH = self._original_path
        self._tmpdir.cleanup()
        _load_skill_to_task_class_mapping.cache_clear()
        await super().asyncTearDown()

    async def test_grain_collapses_to_pre_split_shape(self) -> None:
        await self._insert_session(session_id="parent", total_cost=100.0)
        await self._insert_session(
            session_id="child", subagent_parent_id="parent", total_cost=10.0
        )

        rows = await self.service.fetch_raw_rows(_context(), self.ports)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].source_role)
        self.assertEqual(rows[0].session_count, 2)
        self.assertEqual(rows[0].cost_sum, 110.0)

    async def test_project_filter_placeholders_still_bind_correctly(self) -> None:
        """The empty-role path shifts every downstream placeholder index; this
        is the guard that the project filter still binds.
        """
        await self._insert_session(session_id="a", project_id="proj-1")
        await self._insert_session(session_id="b", project_id="proj-2")

        rows = await self.service.fetch_raw_rows(
            _context(), self.ports, project_ids=["proj-1"]
        )

        self.assertEqual([row.project_id for row in rows], ["proj-1"])


class TestRoleSplitProjectFilterBinding(_DbBase):
    """With the REAL mapping (one role-split rule) the role placeholders come
    first, so the window and project-filter indices are all shifted. Same guard,
    other branch.
    """

    async def test_project_filter_and_window_still_bind_with_role_params(self) -> None:
        stale = _iso(self.now - timedelta(days=3650))
        await self._insert_session(session_id="orchestrator", project_id="proj-1")
        await self._insert_session(
            session_id="leg", project_id="proj-1", subagent_parent_id="orchestrator"
        )
        await self._insert_session(session_id="other", project_id="proj-2")
        await self._insert_session(session_id="ancient", project_id="proj-1", updated_at=stale)

        rows = await self.service.fetch_raw_rows(
            _context(), self.ports, project_ids=["proj-1"]
        )

        self.assertEqual({row.project_id for row in rows}, {"proj-1"})
        self.assertEqual(
            {row.source_role for row in rows}, {ROLE_ORCHESTRATOR, ROLE_IMPLEMENTER}
        )
        self.assertEqual(sum(row.session_count for row in rows), 2, "stale row excluded")


# ---------------------------------------------------------------------------
# Natural-key uniqueness: the invariant the role split rests on.
# ---------------------------------------------------------------------------


class TestNaturalKeyUniquenessIncludesTaskClass(_DbBase):
    """No two emitted rows may share ``_NATURAL_KEY_COLUMNS``, which since
    schema v54 is ``(project_id, source_skill_name, model, task_class)``.

    ``routing_rollup``'s writer is an UPSERT on that key and ``fetch_raw_rows``
    has no ``ORDER BY``, so two rows sharing it would non-deterministically
    overwrite one another. ``task_class`` joined the key precisely so a
    role-split skill's two rows -- which DO share the first three columns --
    are distinct keys rather than duplicates. Both halves are asserted here:
    the three-column prefix collides (that is the new, correct shape) while the
    full four-column key does not.

    Asserted through the no-kwarg ``apply_mapping(raw_rows)`` call the sweep job
    actually makes, so a regression cannot hide behind a test-only flag value.
    """

    async def test_uniqueness_holds_at_the_four_column_grain(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=9.0
        )
        await self._insert_session(session_id="ctl", skill_name=CONTROL_SKILL)
        await self._insert_session(session_id="protected", skill_name=PROTECTED_CONTROL_SKILL)
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        # Exactly how RoutingRollupSweepJob._run_for_project calls it.
        mapped = self.service.apply_mapping(raw)

        natural_keys = [
            (row.project_id, row.source_skill_name, row.model, row.task_class)
            for row in mapped
        ]
        self.assertEqual(
            len(set(natural_keys)),
            len(natural_keys),
            f"rows collide on the persisted natural key: {natural_keys}",
        )

        # The role split is exactly what makes the 3-column prefix insufficient:
        # the role-split skill contributes two rows that share it.
        prefixes = [key[:3] for key in natural_keys]
        role_split_prefixes = [
            prefix for prefix in prefixes if prefix[1] == ROLE_SPLIT_SKILL
        ]
        self.assertEqual(
            len(role_split_prefixes),
            2,
            "the role-split skill must emit two rows on one (project, skill, model)",
        )
        self.assertEqual(len(set(role_split_prefixes)), 1)


# ---------------------------------------------------------------------------
# Blast radius: a NON-role-split protected skill is completely unaffected.
# ---------------------------------------------------------------------------


class TestNonRoleSplitProtectedSkillUnaffected(_DbBase):
    """A role-split skill adds a second row of its own; it must not perturb any
    other skill. Every other protected skill keeps emitting exactly one
    coverage-only row, gated only by ``include_protected_rows``, exactly as
    before the role split existed.
    """

    async def test_protected_control_skill_still_emitted_under_default_flag(self) -> None:
        await self._insert_session(
            session_id="prot", skill_name=PROTECTED_CONTROL_SKILL, total_cost=42.0
        )
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw)

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].task_class, PROTECTED_CONTROL_TASK_CLASS)
        self.assertIn(PROTECTED_CONTROL_TASK_CLASS, PROTECTED_TASK_CLASSES)
        self.assertTrue(mapped[0].is_coverage_only)
        self.assertIsNone(mapped[0].source_role, "control skill must carry no role")
        self.assertEqual(mapped[0].cost_sum, 42.0)

    async def test_protected_control_skill_still_gated_off_when_flag_false(self) -> None:
        """The pre-existing flag semantics are untouched for non-role-split
        skills -- the exception ADDs a drop condition, it never forces emission.
        """
        await self._insert_session(session_id="prot", skill_name=PROTECTED_CONTROL_SKILL)
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw, include_protected_rows=False)

        self.assertEqual(mapped, [])

    async def test_protected_control_skill_survives_alongside_role_split_skill(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=100.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=5.0
        )
        await self._insert_session(
            session_id="prot", skill_name=PROTECTED_CONTROL_SKILL, total_cost=7.0
        )
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        mapped = self.service.apply_mapping(raw)

        by_key = {(row.source_skill_name, row.task_class): row for row in mapped}
        self.assertEqual(
            set(by_key),
            {
                (ROLE_SPLIT_SKILL, IMPLEMENTER_TASK_CLASS),
                (ROLE_SPLIT_SKILL, ORCHESTRATOR_TASK_CLASS),
                (PROTECTED_CONTROL_SKILL, PROTECTED_CONTROL_TASK_CLASS),
            },
        )
        # Role-split skill: implementer row carries only the leg's cost.
        self.assertEqual(by_key[(ROLE_SPLIT_SKILL, IMPLEMENTER_TASK_CLASS)].cost_sum, 5.0)
        self.assertEqual(
            by_key[(ROLE_SPLIT_SKILL, ORCHESTRATOR_TASK_CLASS)].cost_sum, 100.0
        )
        # Non-role-split protected skill: coverage row untouched.
        protected = by_key[(PROTECTED_CONTROL_SKILL, PROTECTED_CONTROL_TASK_CLASS)]
        self.assertTrue(protected.is_coverage_only)
        self.assertIsNone(protected.source_role, "control skill must carry no role")

    async def test_unclassified_rows_still_always_emitted(self) -> None:
        """``_unclassified`` bypasses the protected gate entirely (FR-7) and is
        not protected, so the role exception can never reach it.
        """
        await self._insert_session(session_id="unk", skill_name="totally-unmapped-skill-zzz")
        raw = await self.service.fetch_raw_rows(_context(), self.ports)

        for flag in (True, False):
            with self.subTest(include_protected_rows=flag):
                mapped = self.service.apply_mapping(raw, include_protected_rows=flag)
                self.assertEqual(len(mapped), 1)
                self.assertEqual(mapped[0].task_class, UNCLASSIFIED_TASK_CLASS)


# ---------------------------------------------------------------------------
# End-to-end: real repository + real sweep-job row builder.
# ---------------------------------------------------------------------------


class TestPersistedRowEndToEnd(_DbBase):
    """AC1 all the way to the DB, through the code the worker actually runs:
    ``fetch_raw_rows -> apply_mapping -> apply_provider -> compute_metrics ->
    _build_routing_rollup_row -> repo.upsert``, with no flag overrides.
    """

    async def _sweep(self) -> list[dict[str, Any]]:
        raw = await self.service.fetch_raw_rows(_context(), self.ports, project_ids=["proj-1"])
        mapped = self.service.apply_mapping(raw)
        provider_rows = self.service.apply_provider(mapped)
        key_dtos = self.service.compute_metrics(provider_rows)

        repo = SqliteRoutingRollupRepository(self.db)
        for provider_row, key_dto in zip(provider_rows, key_dtos, strict=True):
            await repo.upsert(_build_routing_rollup_row(provider_row, key_dto))

        async with self.db.execute(
            "SELECT project_id, source_skill_name, model, task_class, sample_count "
            "FROM routing_rollup ORDER BY source_skill_name, model, task_class"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def test_persisted_role_split_rows_are_split_by_task_class(self) -> None:
        """Both role rows reach the table (schema v54's 4-column key), and the
        ``implementation`` row still counts only the implementer legs.
        """
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        for index in range(6):
            await self._insert_session(
                session_id=f"leg-{index}", subagent_parent_id="orchestrator", total_cost=10.0
            )

        persisted = await self._sweep()

        self.assertEqual(len(persisted), 2, f"expected one row per role, got {persisted}")
        self.assertEqual({row["source_skill_name"] for row in persisted}, {ROLE_SPLIT_SKILL})
        by_class = {row["task_class"]: row for row in persisted}
        self.assertEqual(
            set(by_class), {IMPLEMENTER_TASK_CLASS, ORCHESTRATOR_TASK_CLASS}
        )
        self.assertEqual(
            by_class[IMPLEMENTER_TASK_CLASS]["sample_count"], 6, "only the implementer legs"
        )
        self.assertEqual(
            by_class[ORCHESTRATOR_TASK_CLASS]["sample_count"], 1, "only the orchestrator"
        )

    async def test_persisted_row_cost_index_excludes_orchestrator_cost(self) -> None:
        """The orchestrator's $178 must not reach the persisted key. Asserted on
        ``cost_index``, which is the only cost surface the row carries: it is a
        ratio against the ``task_class`` baseline, and with a single key in the
        class the implementer-only mean makes it exactly 1.0. Were the
        orchestrator's cost folded in, the mean would shift and the DTO's
        ``sample_count`` above would not be 6 either.

        Since schema v54 the orchestrator's cost is not merely absent from the
        implementation row -- it is PERSISTED SEPARATELY on the ``orchestration``
        row, which is the per-role telemetry this change unlocked. Both halves
        are asserted.
        """
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        for index in range(6):
            await self._insert_session(
                session_id=f"leg-{index}", subagent_parent_id="orchestrator", total_cost=10.0
            )
        raw = await self.service.fetch_raw_rows(_context(), self.ports, project_ids=["proj-1"])
        provider_rows = self.service.apply_provider(self.service.apply_mapping(raw))

        by_class = {row.task_class: row for row in provider_rows}
        self.assertEqual(
            set(by_class), {IMPLEMENTER_TASK_CLASS, ORCHESTRATOR_TASK_CLASS}
        )

        implementation = by_class[IMPLEMENTER_TASK_CLASS]
        self.assertEqual(implementation.cost_sum, 60.0, "6 legs x $10, no orchestrator")
        self.assertEqual(implementation.cost_covered_count, 6)
        self.assertNotEqual(implementation.cost_sum, 238.0, "orchestrator cost folded in")

        orchestration = by_class[ORCHESTRATOR_TASK_CLASS]
        self.assertEqual(
            orchestration.cost_sum, 178.0, "orchestrator spend now has its own row"
        )
        self.assertEqual(orchestration.cost_covered_count, 1)

        # Each class has exactly one key, so both cost_index values are 1.0
        # against their OWN baseline -- the two means never mix.
        dtos = {dto.task_class: dto for dto in self.service.compute_metrics(provider_rows)}
        self.assertEqual(dtos[IMPLEMENTER_TASK_CLASS].cost_index, 1.0)
        self.assertEqual(dtos[ORCHESTRATOR_TASK_CLASS].cost_index, 1.0)

    async def test_sweep_keeps_non_role_split_protected_coverage_row(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=10.0
        )
        await self._insert_session(
            session_id="prot", skill_name=PROTECTED_CONTROL_SKILL, total_cost=3.0
        )

        persisted = await self._sweep()

        by_key = {(row["source_skill_name"], row["task_class"]): row for row in persisted}
        self.assertEqual(
            set(by_key),
            {
                (ROLE_SPLIT_SKILL, IMPLEMENTER_TASK_CLASS),
                (ROLE_SPLIT_SKILL, ORCHESTRATOR_TASK_CLASS),
                (PROTECTED_CONTROL_SKILL, PROTECTED_CONTROL_TASK_CLASS),
            },
        )
        self.assertEqual(by_key[(ROLE_SPLIT_SKILL, IMPLEMENTER_TASK_CLASS)]["sample_count"], 1)

    async def test_repeat_sweep_is_idempotent_on_the_role_split_key(self) -> None:
        await self._insert_session(session_id="orchestrator", total_cost=178.0)
        await self._insert_session(
            session_id="leg", subagent_parent_id="orchestrator", total_cost=10.0
        )

        first = await self._sweep()
        second = await self._sweep()

        self.assertEqual(first, second)
        self.assertEqual(len(second), 2, "one row per role, upserted in place")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
