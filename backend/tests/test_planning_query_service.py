"""Tests for PlanningQueryService (PCP-201).

Covers all four transport-neutral query methods with fixture features
representing a range of planning states (active, blocked, reversed/stale).
Cache memoization is also verified.
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.application.services.agent_queries.cache import clear_cache
from backend.models import Feature, FeaturePhase, LinkedDocument, PlanningPhaseBatch


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _phase(
    *,
    number: str = "1",
    status: str = "backlog",
    total: int = 3,
    completed: int = 0,
    deferred: int = 0,
    batches: list | None = None,
) -> FeaturePhase:
    return FeaturePhase(
        id=f"feat:phase-{number}",
        phase=number,
        title=f"Phase {number}",
        status=status,
        progress=0,
        totalTasks=total,
        completedTasks=completed,
        deferredTasks=deferred,
        tasks=[],
        phaseBatches=batches or [],
    )


def _feature(
    *,
    fid: str = "feat-1",
    name: str = "Feature One",
    status: str = "backlog",
    phases: list | None = None,
    linked_docs: list | None = None,
) -> Feature:
    return Feature(
        id=fid,
        name=name,
        status=status,
        totalTasks=0,
        completedTasks=0,
        category="enhancement",
        tags=[],
        updatedAt="2026-04-11T10:00:00+00:00",
        linkedDocs=linked_docs or [],
        phases=phases or [],
        relatedFeatures=[],
    )


def _feature_row(feature: Feature) -> dict:
    """Serialise a Feature back to the DB-row shape feature_execution expects.

    NOTE: call this *after* mutating ``feature.linkedFeatures`` so the
    dependency refs land inside ``data_json`` where _feature_from_row reads them.
    """
    linked_features_raw = []
    for ref in (feature.linkedFeatures or []):
        if hasattr(ref, "model_dump"):
            linked_features_raw.append(ref.model_dump())
        elif isinstance(ref, dict):
            linked_features_raw.append(ref)

    return {
        "id": feature.id,
        "name": feature.name,
        "status": feature.status,
        "total_tasks": feature.totalTasks,
        "completed_tasks": feature.completedTasks,
        "deferred_tasks": feature.deferredTasks,
        "category": feature.category,
        "updated_at": feature.updatedAt,
        "data_json": json.dumps(
            {
                "id": feature.id,
                "name": feature.name,
                "status": feature.status,
                "phases": [p.model_dump() for p in feature.phases],
                "linkedDocs": [d.model_dump() for d in feature.linkedDocs],
                "linkedFeatures": linked_features_raw,
            }
        ),
    }


def _doc_row(
    *,
    did: str = "doc-1",
    title: str = "Plan",
    doc_type: str = "implementation_plan",
    file_path: str = "docs/plan.md",
    feature_slug: str = "feat-1",
) -> dict:
    return {
        "id": did,
        "title": title,
        "doc_type": doc_type,
        "file_path": file_path,
        "feature_slug_canonical": feature_slug,
        "feature_slug_hint": feature_slug,
        "updated_at": "2026-04-11T10:00:00+00:00",
        "status": "in-progress",
        "metadata_json": "{}",
        "frontmatter_json": "{}",
    }


# ── Infrastructure stubs ──────────────────────────────────────────────────────


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
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    """Minimal storage stub wiring repos used by PlanningQueryService."""

    def __init__(self, *, features_repo, docs_repo=None, db=None):
        self.db = db or object()
        self._features_repo = features_repo
        self._docs_repo = docs_repo or types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )

    def features(self):
        return self._features_repo

    def documents(self):
        return self._docs_repo

    # Other repos return empty stubs so _filters helpers don't break.
    def sessions(self):
        return types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))

    def sync_state(self):
        return types.SimpleNamespace(list_all=AsyncMock(return_value=[]))

    def entity_links(self):
        return types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))


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


def _ports(
    *,
    project=None,
    features_repo=None,
    docs_repo=None,
    db=None,
) -> CorePorts:
    resolved_project = project or types.SimpleNamespace(
        id="project-1", name="Project 1"
    )
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(resolved_project),
        storage=_Storage(
            features_repo=features_repo
            or types.SimpleNamespace(
                list_all=AsyncMock(return_value=[]),
                get_by_id=AsyncMock(return_value=None),
            ),
            docs_repo=docs_repo,
            db=db,
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ── Helper: patch load_execution_documents to return empty list ───────────────

_PATCH_LOAD_DOCS = patch(
    "backend.application.services.agent_queries.planning.load_execution_documents",
    new=AsyncMock(return_value=[]),
)


# ── Tests ─────────────────────────────────────────────────────────────────────


class ProjectPlanningSummaryTests(unittest.IsolatedAsyncioTestCase):
    """get_project_planning_summary returns correct aggregate counts."""

    def setUp(self):
        clear_cache()

    async def test_mixed_status_features_produce_correct_counts(self) -> None:
        # Three features:
        # - active: in-progress, no phases
        # - done (aligned): raw=done, phase status=done (terminal)
        # - reversed: raw=done but phases are still in-progress (non-terminal status)
        #   The reversal detection fires because feature raw is terminal while phase
        #   rollup effective status is non-terminal (in-progress).
        features = [
            _feature(fid="feat-active", name="Active Feature", status="in-progress"),
            _feature(
                fid="feat-done",
                name="Done Feature",
                status="done",
                phases=[_phase(number="1", status="done", total=2, completed=2)],
            ),
            _feature(
                fid="feat-reversed",
                name="Reversed Feature",
                # raw=done but phase is in-progress (not terminal) so rollup != final
                # and there is no doc completion evidence -> triggers reversed path.
                status="done",
                phases=[_phase(number="1", status="in-progress", total=4, completed=1)],
            ),
        ]
        rows = [_feature_row(f) for f in features]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertEqual(result.project_id, "project-1")
        self.assertEqual(result.total_feature_count, 3)
        self.assertGreaterEqual(result.active_feature_count, 1)
        # The reversed feature should appear in reversal_feature_ids.
        self.assertIn("feat-reversed", result.reversal_feature_ids)
        # Status should be ok or partial (all data loads succeeded).
        self.assertIn(result.status, {"ok", "partial"})
        self.assertIn("project-1", result.source_refs)

    async def test_empty_project_returns_ok(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertEqual(result.total_feature_count, 0)
        self.assertEqual(result.blocked_feature_ids, [])

    async def test_blocked_feature_captured(self) -> None:
        # A feature with a linkedFeature blocked_by dependency that isn't done.
        from backend.models import LinkedFeatureRef
        blocker = _feature(fid="blocker-feat", name="Blocker", status="in-progress")
        blocked = _feature(fid="blocked-feat", name="Blocked", status="backlog")
        blocked.linkedFeatures = [
            LinkedFeatureRef(feature="blocker-feat", type="blocked_by", source="blocked_by")
        ]
        rows = [_feature_row(blocker), _feature_row(blocked)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertIn("blocked-feat", result.blocked_feature_ids)


class ProjectPlanningGraphTests(unittest.IsolatedAsyncioTestCase):
    """get_project_planning_graph returns nodes + edges."""

    def setUp(self):
        clear_cache()

    async def test_returns_nodes_and_edges_for_feature_with_docs(self) -> None:
        feat = _feature(
            fid="feat-graph",
            name="Graph Feature",
            status="in-progress",
            linked_docs=[
                LinkedDocument(
                    id="doc-prd",
                    title="PRD",
                    filePath="docs/prd.md",
                    docType="prd",
                ).model_dump()
            ],
        )
        rows = [_feature_row(feat)]
        doc_rows = [
            _doc_row(
                did="doc-plan",
                title="Plan",
                doc_type="implementation_plan",
                file_path="docs/plan.md",
                feature_slug="feat-graph",
            )
        ]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_project_planning_graph(
                _context(), ports
            )

        self.assertEqual(result.project_id, "project-1")
        # The PRD node from linkedDocs should appear.
        self.assertGreater(result.node_count, 0)
        self.assertEqual(result.node_count, len(result.nodes))
        self.assertEqual(result.edge_count, len(result.edges))
        self.assertIn(result.status, {"ok", "partial"})

    async def test_feature_scoped_graph_filters_to_seed(self) -> None:
        feat_a = _feature(fid="feat-a", name="A", status="in-progress")
        feat_b = _feature(fid="feat-b", name="B", status="backlog")
        rows = [_feature_row(feat_a), _feature_row(feat_b)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_graph(
            _context(), ports, feature_id="feat-a"
        )

        # feature_id should be echoed in the DTO.
        self.assertEqual(result.feature_id, "feat-a")
        self.assertIn(result.status, {"ok", "partial"})

    async def test_unknown_feature_id_returns_error(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_graph(
            _context(), ports, feature_id="does-not-exist"
        )

        self.assertEqual(result.status, "error")


class FeaturePlanningContextTests(unittest.IsolatedAsyncioTestCase):
    """get_feature_planning_context returns effective status, provenance, phases."""

    def setUp(self):
        clear_cache()

    async def test_aligned_feature_returns_ok_with_matching_statuses(self) -> None:
        feat = _feature(
            fid="feat-ctx",
            name="Context Feature",
            status="in-progress",
            phases=[
                _phase(number="1", status="in-progress", total=3, completed=1)
            ],
        )
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="feat-ctx"
            )

        self.assertEqual(result.feature_id, "feat-ctx")
        self.assertEqual(result.raw_status, "in-progress")
        self.assertEqual(result.effective_status, "in-progress")
        self.assertEqual(result.mismatch_state, "aligned")
        # planning_status must carry provenance detail.
        self.assertIn("rawStatus", result.planning_status)
        self.assertIn("provenance", result.planning_status)
        self.assertEqual(len(result.phases), 1)
        self.assertIn(result.status, {"ok", "partial"})

    async def test_reversed_feature_exposes_mismatch(self) -> None:
        """Raw=done but phase status is in-progress (non-terminal) -> reversed mismatch.

        NOTE: The Phase 1 derivation logic considers a phase completion-equivalent when
        its *status* is terminal (done/deferred/completed), regardless of task counts.
        So a reversal requires the phase status itself to be non-terminal while the
        feature raw status is terminal.
        """
        feat = _feature(
            fid="feat-rev",
            name="Reversed",
            status="done",
            phases=[_phase(number="1", status="in-progress", total=5, completed=1)],
        )
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="feat-rev"
            )

        self.assertEqual(result.raw_status, "done")
        # Effective status diverges from raw due to reversal.
        self.assertNotEqual(result.effective_status, "done")
        self.assertIn(result.mismatch_state, {"reversed", "mismatched", "derived"})
        self.assertTrue(result.planning_status.get("mismatchState", {}).get("isMismatch", False))

    async def test_phase_batch_readiness_populated(self) -> None:
        from backend.models import PlanningPhaseBatch, PlanningPhaseBatchReadiness

        batch = PlanningPhaseBatch(
            featureSlug="feat-batched",
            phase="1",
            batchId="batch_1",
            taskIds=["task-a", "task-b"],
            readinessState="ready",
            readiness=PlanningPhaseBatchReadiness(state="ready", isReady=True),
        )
        feat = _feature(
            fid="feat-batched",
            name="Batched Feature",
            status="in-progress",
            phases=[
                FeaturePhase(
                    id="feat-batched:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="in-progress",
                    progress=30,
                    totalTasks=2,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                    phaseBatches=[batch],
                )
            ],
        )
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="feat-batched"
            )

        self.assertEqual(len(result.phases), 1)
        phase_ctx = result.phases[0]
        self.assertEqual(len(phase_ctx.batches), 1)
        self.assertEqual(phase_ctx.batches[0]["batchId"], "batch_1")

    async def test_missing_feature_returns_error(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_feature_planning_context(
            _context(), ports, feature_id="ghost-feature"
        )

        self.assertEqual(result.status, "error")


class PhaseOperationsTests(unittest.IsolatedAsyncioTestCase):
    """get_phase_operations returns batches, tasks, and dependency resolution."""

    def setUp(self):
        clear_cache()

    async def test_returns_batches_with_parallelization_semantics(self) -> None:
        from backend.models import PlanningPhaseBatch

        batch_1 = PlanningPhaseBatch(
            featureSlug="feat-ops",
            phase="2",
            batchId="batch_1",
            taskIds=["task-1", "task-2"],
            readinessState="ready",
        )
        batch_2 = PlanningPhaseBatch(
            featureSlug="feat-ops",
            phase="2",
            batchId="batch_2",
            taskIds=["task-3"],
            readinessState="waiting",
        )
        feat = _feature(
            fid="feat-ops",
            name="Ops Feature",
            status="in-progress",
            phases=[
                _phase(number="1", status="done", total=2, completed=2),
                FeaturePhase(
                    id="feat-ops:phase-2",
                    phase="2",
                    title="Phase 2",
                    status="in-progress",
                    progress=20,
                    totalTasks=3,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                    phaseBatches=[batch_1, batch_2],
                ),
            ],
        )
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_phase_operations(
            _context(), ports, feature_id="feat-ops", phase_number=2
        )

        self.assertEqual(result.feature_id, "feat-ops")
        self.assertEqual(result.phase_number, 2)
        self.assertEqual(result.phase_token, "2")
        # Both batches must appear and preserve their batchId / readinessState.
        self.assertEqual(len(result.phase_batches), 2)
        batch_ids = {b["batchId"] for b in result.phase_batches}
        self.assertIn("batch_1", batch_ids)
        self.assertIn("batch_2", batch_ids)
        self.assertIn(result.status, {"ok", "partial"})

    async def test_unknown_phase_number_returns_error(self) -> None:
        feat = _feature(
            fid="feat-single",
            name="Single Phase",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress", total=3)],
        )
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_phase_operations(
            _context(), ports, feature_id="feat-single", phase_number=99
        )

        self.assertEqual(result.status, "error")

    async def test_dependency_resolution_populated(self) -> None:
        """Dependency info should appear in the phase_ops DTO when the feature
        has linkedFeature blocked_by references."""
        from backend.models import LinkedFeatureRef

        blocker = _feature(fid="dep-feat", name="Dep", status="in-progress")
        feat = _feature(
            fid="main-feat",
            name="Main",
            status="backlog",
            phases=[_phase(number="1", status="backlog", total=2)],
        )
        feat.linkedFeatures = [
            LinkedFeatureRef(feature="dep-feat", type="blocked_by", source="blocked_by")
        ]
        rows = [_feature_row(blocker), _feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=_feature_row(feat)),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_phase_operations(
            _context(), ports, feature_id="main-feat", phase_number=1
        )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertIn("state", result.dependency_resolution)
        self.assertIn(result.dependency_resolution["state"], {"blocked", "blocked_unknown", "unblocked"})


class CacheMemoizationTests(unittest.IsolatedAsyncioTestCase):
    """Memoization: second identical call should short-circuit derivation."""

    def setUp(self):
        clear_cache()

    async def test_second_call_returns_cached_result(self) -> None:
        feat = _feature(fid="feat-cache", name="Cache Test", status="backlog")
        row = _feature_row(feat)

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )

        # _FakeDB satisfies the aiosqlite-style ``async with db.execute(sql) as cur``
        # pattern used by _query_max_updated_at.  Note: ``execute`` must return an
        # *async context manager directly* (not a coroutine), because the cache module
        # does ``async with db.execute(...) as cur`` — the result of db.execute() is
        # used as the async CM, not awaited first.
        class _FakeCur:
            async def fetchone(self):  # noqa: N805
                return ("2026-04-11T10:00:00",)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class _FakeDB:
            """Minimal DB stub that satisfies _query_max_updated_at (aiosqlite path)."""

            def execute(self, sql, params=()):  # sync — returns async CM directly
                return _FakeCur()

        fake_db = _FakeDB()
        # Patch aiosqlite.Connection isinstance check so our stub is treated as SQLite.
        with patch(
            "backend.application.services.agent_queries.cache.aiosqlite.Connection",
            new=type(fake_db),
        ):
            ports = _ports(features_repo=features_repo, docs_repo=docs_repo, db=fake_db)
            svc = PlanningQueryService()

            result_1 = await svc.get_project_planning_summary(_context(), ports)
            # list_all should have been called once during the first (cache-miss) call.
            call_count_after_first = features_repo.list_all.call_count

            result_2 = await svc.get_project_planning_summary(_context(), ports)
            call_count_after_second = features_repo.list_all.call_count

        # The second call should use the cache: list_all should NOT be called again.
        self.assertEqual(call_count_after_first, call_count_after_second)
        self.assertEqual(result_1.project_id, result_2.project_id)
        self.assertEqual(result_1.total_feature_count, result_2.total_feature_count)


class PlanningQueryServiceImportTests(unittest.TestCase):
    """Verify the public __init__ exports are wired correctly."""

    def test_planning_service_importable_from_package(self) -> None:
        from backend.application.services.agent_queries import PlanningQueryService  # noqa: F401

    def test_planning_dtos_importable_from_package(self) -> None:
        from backend.application.services.agent_queries import (  # noqa: F401
            FeaturePlanningContextDTO,
            FeatureSummaryItem,
            PhaseContextItem,
            PhaseOperationsDTO,
            PhaseTaskItem,
            PlanningNodeCountsByType,
            ProjectPlanningSummaryDTO,
            ProjectPlanningGraphDTO,
        )


if __name__ == "__main__":
    unittest.main()
