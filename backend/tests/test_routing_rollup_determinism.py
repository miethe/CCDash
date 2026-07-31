"""Unit tests for T3-005 (service-layer) and T6-004 (worker-path) determinism
guards for the Proof -> Routing Feedback Loop rollup pipeline.

T3-005 (below, ``RoutingRollupDeterminismTests``/``RoutingRollupDTOShapeTests``)
covers this task's own acceptance criteria (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``,
Task T3-005):

  - Two invocations of the full pipeline (``fetch_raw_rows`` ->
    ``apply_mapping`` -> ``apply_provider`` -> ``compute_coverage_counters``
    -> ``build_response``) over an UNCHANGED fixture window produce
    field-identical ``RoutingRollupResponseDTO``/``RoutingRollupKeyDTO`` rows
    -- asserted against a deterministically SORTED key list (by
    ``(source_skill_name, model)``), since order-independent set comparison
    alone is insufficient to prove determinism.
  - ``RoutingRollupKeyDTO``/``RoutingRollupResponseDTO`` are plain
    ``BaseModel`` subclasses, NOT ``AgentQueryEnvelope`` subclasses -- the
    isinstance/MRO check T3-004's own AC explicitly routes to this module
    (see that task's third acceptance criterion) rather than
    ``test_routing_rollup_metrics.py``.

Wall-clock non-determinism sources are pinned for the duration of each
pipeline run so the ONLY thing under test is the compute logic itself, never
incidental clock drift between the two invocations:

  - ``fetch_raw_rows``'s window boundary (``_filters.resolve_time_window``,
    which calls ``datetime.now(timezone.utc)`` internally whenever ``until``
    is omitted -- ``fetch_raw_rows`` never passes ``until``) is pinned by
    patching ``routing_rollup.resolve_time_window`` (the name bound into
    ``routing_rollup``'s own module namespace via
    ``from ._filters import resolve_time_window``) to return a fixed
    ``(window_start, window_end)`` tuple for both invocations.
  - ``build_response``'s ``freshness_ts`` (``_now_iso()`` by default) is
    pinned via the existing ``freshness_ts`` kwarg override point (T3-004),
    never by patching ``_now_iso`` directly -- both are equally valid per
    that task's own docstring; the kwarg is simply less invasive here.

``test_routing_rollup_no_llm_imports.py`` (this task's sibling file) owns
the AST-walk no-LLM/no-agent-dispatch import-graph guard; this file covers
only the determinism + DTO-shape acceptance criteria.

── T6-004 (below, ``RoutingRollupSweepJobDeterminismTests``): end-to-end
worker-path re-confirmation ────────────────────────────────────────────────

T3-005's tests above prove determinism at the ``RoutingRollupQueryService``
layer only -- a direct, in-memory pipeline call, never touching the
``routing_rollup`` table. T6-004 (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-6-validation-guards-docs.md``)
re-runs the same determinism property end-to-end through the full Phase 4
worker path instead: two full ``RoutingRollupSweepJob.execute()`` runs over
an unchanged fixture session window must PERSIST field-identical
``routing_rollup`` rows via the worker's real upsert path
(``backend.db.repositories.routing_rollup``), not merely compute
field-identical in-memory DTOs. This exercises the worker's upsert path
directly, so an upsert bug that corrupts row identity between runs would be
caught here even if the T3-005 service-level tests above stay green (which
this task leaves completely unmodified).

Reuses this module's own pinned-window fixture constants
(``_FIXED_WINDOW_START``/``_FIXED_WINDOW_END``, ``_insert_session``) --
the same fixture-DB approach as T3-005, driven through
``RoutingRollupSweepJob.execute()`` instead of a direct service call.
``freshness_ts``/``created_at``/``updated_at`` are deliberately EXCLUDED
from the field-identity comparison (per T6-004's own Implementation Notes:
sweep timestamps may legitimately differ between the two runs) -- the
worker never exposes a ``freshness_ts`` override hook the way T3-005's
direct ``build_response`` call does, so pinning it here would require
patching private module internals rather than testing the worker's real,
shipped call shape.

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_determinism.py -v
"""
from __future__ import annotations

import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite
from pydantic import BaseModel

from backend import config
from backend.adapters.jobs.routing_rollup_sweep_job import (
    RoutingRollupSweepJob,
    RoutingRollupSweepRunResult,
)
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries import routing_rollup as routing_rollup_module
from backend.application.services.agent_queries.models import (
    AgentQueryEnvelope,
    RoutingRollupKeyDTO,
    RoutingRollupResponseDTO,
)
from backend.application.services.agent_queries.routing_rollup import RoutingRollupQueryService
from backend.db.repositories.routing_rollup import SqliteRoutingRollupRepository
from backend.db.sqlite_migrations import run_migrations
from backend.runtime_ports import build_core_ports

# Fixed window/freshness values -- pinned so the two pipeline invocations
# below see byte-identical wall-clock inputs. Deliberately NOT "now" at test
# run time: a real determinism proof must not rely on both invocations
# happening to land in the same microsecond.
_FIXED_WINDOW_START = datetime(2026, 6, 29, tzinfo=timezone.utc)
_FIXED_WINDOW_END = datetime(2026, 7, 29, tzinfo=timezone.utc)
_FIXED_FRESHNESS_TS = "2026-07-29T02:00:00+00:00"
_IN_WINDOW_UPDATED_AT = "2026-07-15T00:00:00"


# ---------------------------------------------------------------------------
# Shared fixture helpers (mirrors test_routing_rollup_aggregation.py's own
# conventions, which in turn mirror backend/tests/test_system_metrics.py).
# ---------------------------------------------------------------------------


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
    updated_at: str = _IN_WINDOW_UPDATED_AT,
    status: str = "completed",
) -> None:
    """Insert a minimal sessions row exercising the columns the pipeline
    groups/filters/maps on."""
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, project_id, skill_name, model, status, updated_at, created_at, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, project_id, skill_name, model, status, updated_at, updated_at, f"{session_id}.jsonl"),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# AC: two invocations over an unchanged fixture window produce
# field-identical rows in a stable sort order.
# ---------------------------------------------------------------------------


class RoutingRollupDeterminismTests(unittest.IsolatedAsyncioTestCase):
    """T3-005 -- two invocations over an unchanged fixture window produce
    field-identical rows in a stable sort order."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry())
        self.service = RoutingRollupQueryService()

        # A fixture spanning every T3-002/T3-003 policy branch, so the
        # determinism check exercises the whole pipeline, not just the
        # ordinary-key path:
        #   - ("debugging", "claude-sonnet-5")     -> mapped, ordinary key (task_class=implementation)
        #   - ("planning", "gpt-5.6-terra")         -> protected (task_class=orchestration)
        #   - ("codex", "claude-sonnet-5")          -> unclassified (executor-identity -- HAS an entry)
        #   - ("totally-unmapped-skill", "opus-5")  -> unclassified (NO entry at all)
        await _insert_session(
            self.db, session_id="s1", project_id="proj-1", skill_name="debugging", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db, session_id="s2", project_id="proj-1", skill_name="debugging", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db, session_id="s3", project_id="proj-1", skill_name="planning", model="gpt-5.6-terra"
        )
        await _insert_session(
            self.db, session_id="s4", project_id="proj-1", skill_name="codex", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db, session_id="s5", project_id="proj-2", skill_name="totally-unmapped-skill", model="opus-5"
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _run_pipeline(self) -> RoutingRollupResponseDTO:
        """Run the full T3-001..T3-004 pipeline once, with the two wall-clock
        non-determinism sources (window boundary, freshness_ts) pinned."""
        with patch.object(
            routing_rollup_module,
            "resolve_time_window",
            return_value=(_FIXED_WINDOW_START, _FIXED_WINDOW_END),
        ):
            raw_rows = await self.service.fetch_raw_rows(_context(), self.ports)
        mapped_rows = self.service.apply_mapping(raw_rows)
        provider_rows = self.service.apply_provider(mapped_rows)
        coverage = self.service.compute_coverage_counters(mapped_rows)
        return self.service.build_response(provider_rows, coverage, freshness_ts=_FIXED_FRESHNESS_TS)

    @staticmethod
    def _sorted_keys(response: RoutingRollupResponseDTO) -> list[RoutingRollupKeyDTO]:
        """Deterministic sort order for the ``keys[]`` list -- order-
        independent set comparison alone would not prove determinism, per
        this task's own Description."""
        return sorted(response.keys, key=lambda key: (key.source_skill_name, key.model))

    async def test_two_invocations_produce_field_identical_sorted_key_rows(self) -> None:
        response_1 = await self._run_pipeline()
        response_2 = await self._run_pipeline()

        sorted_1 = self._sorted_keys(response_1)
        sorted_2 = self._sorted_keys(response_2)

        # Sanity: the fixture must actually exercise something -- a
        # trivially-empty result would "prove" determinism over nothing.
        self.assertGreaterEqual(
            len(sorted_1), 4, "fixture must produce at least one key per policy branch"
        )
        self.assertEqual(len(sorted_1), len(sorted_2))

        for row_1, row_2 in zip(sorted_1, sorted_2):
            self.assertEqual(
                row_1.model_dump(),
                row_2.model_dump(),
                f"key ({row_1.source_skill_name!r}, {row_1.model!r}) is not field-identical "
                "across two invocations over an unchanged window",
            )

        # The response-level envelope (contract/taxonomy/mapping identity,
        # coverage counters) must also be field-identical -- not just the
        # per-key rows.
        self.assertEqual(
            response_1.model_dump(exclude={"keys"}),
            response_2.model_dump(exclude={"keys"}),
        )

    async def test_two_invocations_agree_on_key_set_membership(self) -> None:
        """The SET of (source_skill_name, model) keys must be identical
        across invocations too -- not merely the count."""
        response_1 = await self._run_pipeline()
        response_2 = await self._run_pipeline()

        keys_1 = {(k.source_skill_name, k.model) for k in response_1.keys}
        keys_2 = {(k.source_skill_name, k.model) for k in response_2.keys}
        self.assertEqual(keys_1, keys_2)

    async def test_fixture_exercises_every_policy_branch(self) -> None:
        """Sanity check on the fixture itself -- guards against a future
        edit silently narrowing fixture coverage to only the ordinary-key
        path, which would make the determinism proof above trivial."""
        response = await self._run_pipeline()
        task_classes = {k.task_class for k in response.keys}

        self.assertIn("implementation", task_classes)  # debugging -> mapped
        self.assertIn("orchestration", task_classes)  # planning -> protected
        self.assertIn(
            routing_rollup_module.UNCLASSIFIED_TASK_CLASS, task_classes
        )  # codex (executor-identity) AND totally-unmapped-skill (no entry)

        eligible_by_key = {(k.source_skill_name, k.model): k.eligible_for_adjustment for k in response.keys}
        # Coverage-only rows are hardcoded ineligible regardless of sample size (T3-002/T3-004).
        self.assertFalse(eligible_by_key[("planning", "gpt-5.6-terra")])
        self.assertFalse(eligible_by_key[("codex", "claude-sonnet-5")])
        self.assertFalse(eligible_by_key[("totally-unmapped-skill", "opus-5")])


# ---------------------------------------------------------------------------
# AC: RoutingRollupKeyDTO / RoutingRollupResponseDTO are plain BaseModel, not
# AgentQueryEnvelope subclasses -- T3-004's own AC routes this isinstance/MRO
# check here rather than test_routing_rollup_metrics.py.
# ---------------------------------------------------------------------------


class RoutingRollupDTOShapeTests(unittest.TestCase):
    """Mirrors ``AARReviewDTO``'s own documented rationale for opting out of
    ``AgentQueryEnvelope`` (no ``data_freshness`` field; ``generated_at`` is a
    plain ISO-8601 string, never a ``datetime``) -- verified structurally
    here rather than merely asserted in a docstring."""

    def test_key_dto_is_not_an_agent_query_envelope_subclass(self) -> None:
        self.assertNotIn(AgentQueryEnvelope, RoutingRollupKeyDTO.__mro__)

    def test_response_dto_is_not_an_agent_query_envelope_subclass(self) -> None:
        self.assertNotIn(AgentQueryEnvelope, RoutingRollupResponseDTO.__mro__)

    def test_dtos_are_plain_pydantic_basemodels_with_no_intermediate_base(self) -> None:
        self.assertTrue(issubclass(RoutingRollupKeyDTO, BaseModel))
        self.assertTrue(issubclass(RoutingRollupResponseDTO, BaseModel))
        # Direct declared bases are BaseModel itself -- not AgentQueryEnvelope
        # or any other intermediate DTO base.
        self.assertEqual(RoutingRollupKeyDTO.__bases__, (BaseModel,))
        self.assertEqual(RoutingRollupResponseDTO.__bases__, (BaseModel,))


# ---------------------------------------------------------------------------
# T6-004: end-to-end determinism re-confirmation through the persisted
# RoutingRollupSweepJob worker path (AC-3, determinism half). See this
# module's own docstring section for the full rationale; T3-005's tests
# above are left completely unmodified.
# ---------------------------------------------------------------------------


class _SweepIdentityProvider:
    """Minimal identity provider satisfying ``resolve_application_request``'s
    ``ports.identity_provider.get_principal(...)`` call -- mirrors
    ``test_routing_rollup_sweep_job.py::_IdentityProvider`` exactly. This
    test class exercises the SAME ``RoutingRollupSweepJob._execute_inner``
    path that module's own fixtures already prove out for the non-
    determinism ACs (multi-project fan-out, flag-off no-op, AC-7
    reversibility); named with a ``_Sweep`` prefix here purely to avoid
    colliding with this file's own pre-existing, differently-shaped
    ``_WorkspaceRegistry`` (used only by ``RoutingRollupDeterminismTests``
    above, which never resolves a real ``ApplicationRequest``)."""

    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(
            subject="routing-rollup-sweep", display_name="Routing Rollup Sweep", auth_mode="test"
        )


class _SweepAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _SweepWorkspaceRegistry:
    """Single-project workspace registry -- mirrors
    ``test_routing_rollup_sweep_job.py::_WorkspaceRegistry`` exactly,
    including the kwarg-less ``resolve_scope`` signature
    ``_resolve_workspace_scope``'s ``TypeError``-retry path already
    tolerates."""

    def __init__(self, project: Any):
        self.project = project

    def get_project(self, project_id: str) -> Any | None:
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self) -> Any | None:
        return self.project

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, ProjectScope | None]:
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path(f"/tmp/{resolved_id}"),
            sessions_dir=Path(f"/tmp/{resolved_id}/sessions"),
            docs_dir=Path(f"/tmp/{resolved_id}/docs"),
            progress_dir=Path(f"/tmp/{resolved_id}/progress"),
        )


class _SweepStorage:
    """Only ``.db`` is ever read on this path -- mirrors
    ``test_routing_rollup_sweep_job.py::_Storage`` exactly."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db


def _build_sweep_ports(db: aiosqlite.Connection, *, project: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_SweepIdentityProvider(),
        authorization_policy=_SweepAuthorizationPolicy(),
        workspace_registry=_SweepWorkspaceRegistry(project),
        storage=_SweepStorage(db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


_SWEEP_CACHE_CLEAR_TARGET = "backend.application.services.agent_queries.aclear_project_cache"

#: Columns on the PERSISTED ``routing_rollup`` row that are wall-clock-
#: derived rather than aggregation/mapping-derived -- excluded from the
#: field-identity comparison below per T6-004's own Implementation Notes:
#: "Do not assume: fully deterministic sweep timestamps (freshness_ts/
#: generated_at) may legitimately differ between the two runs -- scope the
#: field-identity assertion to the aggregation/mapping fields, not
#: wall-clock-derived ones." ``created_at``/``updated_at`` are the DDL's own
#: ``datetime('now')``-defaulted audit columns (never part of
#: ``ROUTING_ROLLUP_COLUMNS``, the compute-service's own output contract);
#: ``freshness_ts`` is ``ROUTING_ROLLUP_COLUMNS``' own wall-clock field,
#: computed by ``RoutingRollupQueryService.compute_metrics`` via
#: ``_now_iso()`` because the worker (unlike T3-005's direct
#: ``build_response`` call) never passes a ``freshness_ts`` override.
_WALL_CLOCK_COLUMNS = frozenset({"freshness_ts", "created_at", "updated_at"})


class RoutingRollupSweepJobDeterminismTests(unittest.IsolatedAsyncioTestCase):
    """T6-004 -- two full ``RoutingRollupSweepJob.execute()`` runs over an
    UNCHANGED fixture session window must persist field-identical
    ``routing_rollup`` rows through the worker's real upsert path, not
    merely compute field-identical in-memory DTOs the way
    ``RoutingRollupDeterminismTests`` above (T3-005, left unmodified) already
    proves at the service layer alone."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self._flag_patch = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        self._flag_patch.start()

        self.project = types.SimpleNamespace(id="proj-1", name="Project 1")
        # Byte-for-byte the same policy-branch fixture as
        # RoutingRollupDeterminismTests.asyncSetUp above (all in one project
        # here -- this class's own ports/registry are single-project by
        # construction, unlike T3-005's direct service call, which never
        # touches a workspace registry at all):
        #   - ("debugging", "claude-sonnet-5")     -> mapped, ordinary key
        #   - ("planning", "gpt-5.6-terra")         -> protected (orchestration)
        #   - ("codex", "claude-sonnet-5")          -> unclassified (executor-identity)
        #   - ("totally-unmapped-skill", "opus-5")  -> unclassified (no entry)
        await _insert_session(
            self.db, session_id="s1", project_id="proj-1", skill_name="debugging", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db, session_id="s2", project_id="proj-1", skill_name="debugging", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db, session_id="s3", project_id="proj-1", skill_name="planning", model="gpt-5.6-terra"
        )
        await _insert_session(
            self.db, session_id="s4", project_id="proj-1", skill_name="codex", model="claude-sonnet-5"
        )
        await _insert_session(
            self.db,
            session_id="s5",
            project_id="proj-1",
            skill_name="totally-unmapped-skill",
            model="opus-5",
        )

    async def asyncTearDown(self) -> None:
        self._flag_patch.stop()
        await self.db.close()

    async def _run_sweep(self, job: RoutingRollupSweepJob) -> RoutingRollupSweepRunResult:
        """One sweep-job tick with BOTH wall-clock non-determinism sources
        pinned/neutralized for the duration of the call:

          - ``fetch_raw_rows``'s window boundary is pinned via the exact
            same ``routing_rollup_module.resolve_time_window`` patch target
            T3-005's own ``_run_pipeline`` helper uses above, so both ticks
            see byte-identical window boundaries.
          - The real cache-invalidation hook (``aclear_project_cache``) is
            patched out -- this test asserts persisted-row identity only; it
            has no opinion on cache behavior, which
            ``test_routing_rollup_sweep_job.py`` already covers.
        """
        with patch.object(
            routing_rollup_module,
            "resolve_time_window",
            return_value=(_FIXED_WINDOW_START, _FIXED_WINDOW_END),
        ):
            with patch(_SWEEP_CACHE_CLEAR_TARGET, new=AsyncMock()):
                return await job.execute(trigger="scheduled")

    @staticmethod
    def _comparable(row: dict[str, Any]) -> dict[str, Any]:
        """Strip wall-clock-derived columns before comparison -- see
        ``_WALL_CLOCK_COLUMNS``'s module-level docstring."""
        return {key: value for key, value in row.items() if key not in _WALL_CLOCK_COLUMNS}

    async def test_two_sweep_runs_over_unchanged_window_persist_field_identical_rows(self) -> None:
        ports = _build_sweep_ports(self.db, project=self.project)
        job = RoutingRollupSweepJob(ports=ports, project=self.project)
        repo = SqliteRoutingRollupRepository(self.db)

        result_1 = await self._run_sweep(job)
        self.assertEqual(result_1.outcome, "success")
        self.assertTrue(result_1.success)
        # get_by_project orders by (source_skill_name, model) -- a
        # deterministic sort, same rationale as T3-005's own _sorted_keys
        # helper (order-independent set comparison alone would not prove
        # determinism).
        rows_1 = await repo.get_by_project("proj-1")
        # Sanity: a trivially-empty persisted result would "prove"
        # determinism over nothing -- mirrors T3-005's own sanity assertion.
        self.assertGreaterEqual(
            len(rows_1), 4, "fixture must persist at least one row per policy branch"
        )

        result_2 = await self._run_sweep(job)
        self.assertEqual(result_2.outcome, "success")
        self.assertTrue(result_2.success)
        rows_2 = await repo.get_by_project("proj-1")

        # Idempotent upsert: a repeat sweep over an unchanged window never
        # grows the table (routing_rollup_sweep_job.py's own module
        # docstring, point 3).
        self.assertEqual(len(rows_1), len(rows_2))

        for row_1, row_2 in zip(rows_1, rows_2):
            self.assertEqual(
                self._comparable(row_1),
                self._comparable(row_2),
                f"persisted row (source_skill_name={row_1['source_skill_name']!r}, "
                f"model={row_1['model']!r}) is not field-identical across two "
                "RoutingRollupSweepJob runs over an unchanged window",
            )

    async def test_repeat_sweep_upserts_in_place_never_growing_row_count(self) -> None:
        """Explicit row-count-stability check, independent of the field-
        identity assertion above -- proves the upsert path's own idempotency
        contract directly (module docstring: "it never grows the table on a
        repeat tick over an unchanged window"), rather than only inferring
        it from ``len(rows_1) == len(rows_2)`` in the test above."""
        ports = _build_sweep_ports(self.db, project=self.project)
        job = RoutingRollupSweepJob(ports=ports, project=self.project)
        repo = SqliteRoutingRollupRepository(self.db)

        await self._run_sweep(job)
        count_after_first = await repo.count_by_project("proj-1")
        self.assertGreater(count_after_first, 0)

        await self._run_sweep(job)
        count_after_second = await repo.count_by_project("proj-1")

        self.assertEqual(count_after_first, count_after_second)


if __name__ == "__main__":
    unittest.main()
