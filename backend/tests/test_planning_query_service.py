"""Tests for PlanningQueryService (PCP-201).

Covers all four transport-neutral query methods with fixture features
representing a range of planning states (active, blocked, reversed/stale).
Cache memoization is also verified.
"""
from __future__ import annotations

import contextlib
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

    async def test_summary_uses_lightweight_artifact_facets_without_building_graphs(self) -> None:
        feature = _feature(
            fid="feat-light",
            name="Lightweight Feature",
            status="in-progress",
            linked_docs=[
                LinkedDocument(
                    id="linked-prd",
                    title="Linked PRD",
                    filePath="docs/prds/feat-light.md",
                    docType="prd",
                ).model_dump()
            ],
        )
        rows = [_feature_row(feature)]
        doc_rows = [
            _doc_row(
                did="doc-plan",
                title="Plan",
                doc_type="implementation_plan",
                file_path="docs/project_plans/implementation_plans/feat-light.md",
                feature_slug="feat-light",
            ),
            _doc_row(
                did="doc-context",
                title="Context",
                doc_type="context",
                file_path="docs/context/feat-light.md",
                feature_slug="feat-light",
            ),
            _doc_row(
                did="doc-tracker",
                title="Tracker",
                doc_type="tracker",
                file_path=".claude/progress/feat-light/phase-12-progress.md",
                feature_slug="feat-light",
            ),
        ]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with patch(
            "backend.application.services.agent_queries.planning.build_planning_graph",
            new=MagicMock(side_effect=AssertionError("summary should not build graphs")),
        ) as graph_mock:
            result = await PlanningQueryService().get_project_planning_summary(
                _context(), ports
            )

        graph_mock.assert_not_called()
        self.assertEqual(result.total_feature_count, 1)
        self.assertEqual(result.active_feature_count, 1)
        self.assertEqual(len(result.feature_summaries), 1)
        self.assertEqual(result.feature_summaries[0].feature_id, "feat-light")
        self.assertEqual(result.feature_summaries[0].node_count, 4)
        self.assertEqual(result.node_counts_by_type.prd, 1)
        self.assertEqual(result.node_counts_by_type.implementation_plan, 1)
        self.assertEqual(result.node_counts_by_type.context, 1)
        self.assertEqual(result.node_counts_by_type.tracker, 1)

    async def test_summary_defaults_active_first_and_excludes_terminal_items(self) -> None:
        features = [
            _feature(
                fid="feat-done",
                name="Done Feature",
                status="done",
                phases=[_phase(number="1", status="done", total=1, completed=1)],
            ),
            _feature(fid="feat-approved", name="Approved Feature", status="approved"),
            _feature(fid="feat-active", name="Active Feature", status="in-progress"),
            _feature(fid="feat-draft", name="Draft Feature", status="draft"),
        ]
        rows = [_feature_row(feature) for feature in features]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(_context(), ports)

        self.assertEqual(result.total_feature_count, 4)
        self.assertEqual(
            [item.feature_id for item in result.feature_summaries],
            ["feat-active", "feat-draft", "feat-approved"],
        )

    async def test_summary_can_include_terminal_and_limit_results(self) -> None:
        features = [
            _feature(fid="feat-done", name="Done Feature", status="done"),
            _feature(fid="feat-active", name="Active Feature", status="in-progress"),
            _feature(fid="feat-review", name="Review Feature", status="review"),
            _feature(fid="feat-draft", name="Draft Feature", status="draft"),
        ]
        rows = [_feature_row(feature) for feature in features]
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
            _context(),
            ports,
            include_terminal=True,
            limit=2,
        )

        self.assertEqual(
            [item.feature_id for item in result.feature_summaries],
            ["feat-active", "feat-review"],
        )


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

    async def test_design_spec_only_context_returns_document_evidence(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        doc_rows = [
            _doc_row(
                did="doc-design",
                title="Design Spec",
                doc_type="design_spec",
                file_path="docs/project_plans/design-specs/design-only.md",
                feature_slug="design-only",
            )
        ]
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="design-only"
            )

        self.assertEqual(result.feature_id, "design-only")
        self.assertEqual(result.feature_name, "Design Spec")
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.specs), 1)
        self.assertEqual(result.specs[0].file_path, "docs/project_plans/design-specs/design-only.md")
        self.assertIn("docs/project_plans/design-specs/design-only.md", result.linked_artifact_refs)

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

    async def test_feature_context_exposes_planning_payload_contract(self) -> None:
        feat = _feature(
            fid="feat-contract",
            name="Contract Feature",
            status="done",
            phases=[_phase(number="1", status="done", total=2, completed=2)],
            linked_docs=[
                LinkedDocument(id="prd-1", title="PRD", filePath="docs/project_plans/prds/enhancements/feat-contract.md", docType="prd"),
                LinkedDocument(id="plan-1", title="Plan", filePath="docs/project_plans/implementation_plans/enhancements/feat-contract.md", docType="implementation_plan"),
                LinkedDocument(id="report-1", title="Report", filePath="docs/project_plans/reports/feat-contract.md", docType="report"),
            ],
        )
        row = _feature_row(feat)
        data = json.loads(row["data_json"])
        data["spikes"] = [{"id": "SPIKE-1", "title": "Investigate graph layout", "status": "done"}]
        data["openQuestions"] = [{"id": "OQ-1", "question": "Ship now?", "severity": "high"}]
        row["data_json"] = json.dumps(data)
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(
                return_value=[
                    _doc_row(
                        did="spec-1",
                        title="Spec",
                        doc_type="spec",
                        file_path="docs/project_plans/specs/feat-contract.md",
                        feature_slug="feat-contract",
                    ),
                    {
                        "id": "spike-doc-1",
                        "title": "Spike Doc",
                        "doc_type": "document",
                        "doc_subtype": "spike",
                        "file_path": "docs/project_plans/spikes/feat-contract-spike.md",
                        "feature_slug_canonical": "feat-contract",
                        "feature_slug_hint": "feat-contract",
                        "updated_at": "2026-04-11T10:00:00+00:00",
                        "status": "done",
                        "metadata_json": "{}",
                        "frontmatter_json": json.dumps(
                            {
                                "open_questions": [
                                    {"id": "OQ-2", "question": "Document fallback?", "severity": "medium"}
                                ]
                            }
                        ),
                    },
                ]
            ),
            list_paginated=AsyncMock(return_value=[]),
        )
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)
        evidence = types.SimpleNamespace(
            status="ok",
            total_tokens=240,
            token_usage_by_model=types.SimpleNamespace(opus=120, sonnet=120, haiku=0, other=0, total=240),
        )

        with patch(
            "backend.application.services.agent_queries.planning.load_execution_documents",
            new=AsyncMock(return_value=feat.linkedDocs),
        ):
            with patch(
                "backend.application.services.agent_queries.feature_evidence_summary.FeatureEvidenceSummaryService.get_summary",
                new=AsyncMock(return_value=evidence),
            ):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-contract"
                )

        self.assertEqual([item.artifact_id for item in result.prds], ["prd-1"])
        self.assertEqual([item.artifact_id for item in result.plans], ["plan-1"])
        self.assertEqual([item.artifact_id for item in result.reports], ["report-1"])
        self.assertEqual([item.artifact_id for item in result.specs], ["spec-1"])
        self.assertEqual(result.spikes[0].spike_id, "SPIKE-1")
        self.assertEqual({item.oq_id for item in result.open_questions}, {"OQ-1", "OQ-2"})
        self.assertIsInstance(result.ready_to_promote, bool)
        self.assertIsInstance(result.is_stale, bool)
        self.assertEqual(result.total_tokens, 240)
        self.assertEqual(result.token_usage_by_model.total, 240)


class ResolveOpenQuestionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_cache()

    async def test_resolve_open_question_updates_overlay_and_sets_otel_success(self) -> None:
        row = _feature_row(_feature(fid="feat-oq", name="Open Question Feature"))
        data = json.loads(row["data_json"])
        data["openQuestions"] = [{"id": "OQ-1", "question": "Need answer?", "severity": "high"}]
        row["data_json"] = json.dumps(data)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        class _Span:
            def __init__(self) -> None:
                self.attrs: dict[str, object] = {}

            def set_attribute(self, key: str, value: object) -> None:
                self.attrs[key] = value

        span = _Span()

        @contextlib.contextmanager
        def _start_span(name: str, attributes: dict[str, object] | None = None):
            self.assertEqual(name, "planning.oq.resolve")
            self.assertEqual(attributes["feature_id"], "feat-oq")
            self.assertEqual(attributes["oq_id"], "OQ-1")
            self.assertEqual(attributes["answer_length"], len("Resolved"))
            yield span

        with patch(
            "backend.application.services.agent_queries.planning.otel.start_span",
            new=_start_span,
        ):
            result = await PlanningQueryService().resolve_open_question(
                _context(),
                ports,
                feature_id="feat-oq",
                oq_id="OQ-1",
                answer_text="Resolved",
            )

        self.assertEqual(result.feature_id, "feat-oq")
        self.assertEqual(result.oq.oq_id, "OQ-1")
        self.assertTrue(result.oq.resolved)
        self.assertTrue(result.oq.pending_sync)
        self.assertEqual(result.oq.answer_text, "Resolved")
        self.assertEqual(span.attrs["success"], True)

    async def test_resolve_open_question_rejects_empty_answer(self) -> None:
        row = _feature_row(_feature(fid="feat-empty", name="Empty"))
        data = json.loads(row["data_json"])
        data["openQuestions"] = [{"id": "OQ-1", "question": "Need answer?"}]
        row["data_json"] = json.dumps(data)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with self.assertRaises(ValueError):
            await PlanningQueryService().resolve_open_question(
                _context(),
                ports,
                feature_id="feat-empty",
                oq_id="OQ-1",
                answer_text="   ",
            )


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


# ── Orphan doc synthesis tests ────────────────────────────────────────────────


def _orphan_doc_row(
    *,
    did: str = "orphan-1",
    title: str = "Orphan Spec",
    doc_type: str = "design_spec",
    doc_subtype: str = "",
    file_path: str = "docs/specs/my-feature.md",
    feature_slug: str = "my-feature",
    status: str = "draft",
) -> dict:
    """Build a doc row that looks like a design_spec or PRD with no matching feature."""
    import json
    return {
        "id": did,
        "title": title,
        "doc_type": doc_type,
        "doc_subtype": doc_subtype,
        "file_path": file_path,
        "feature_slug_canonical": feature_slug,
        "feature_slug_hint": feature_slug,
        "updated_at": "2026-04-17T10:00:00+00:00",
        "status": status,
        "metadata_json": "{}",
        "frontmatter_json": json.dumps({"status": status}),
    }


class OrphanDocSynthesisTests(unittest.IsolatedAsyncioTestCase):
    """Synthesis of FeatureSummaryItems from design_spec / prd orphan docs."""

    def setUp(self):
        clear_cache()

    async def test_design_spec_without_impl_plan_appears_in_summary(self) -> None:
        """A design_spec doc with no matching feature row appears with source_artifact_kind='design_spec'."""
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        doc_rows = [
            _orphan_doc_row(
                did="spec-1",
                title="My Feature Spec",
                doc_type="design_spec",
                feature_slug="my-feature",
                status="draft",
            )
        ]
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertEqual(result.total_feature_count, 1)
        self.assertEqual(len(result.feature_summaries), 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.source_artifact_kind, "design_spec")
        self.assertEqual(item.effective_status, "draft")
        self.assertEqual(item.feature_name, "My Feature Spec")

    async def test_prd_without_impl_plan_appears_in_summary(self) -> None:
        """A PRD doc with no matching feature row appears with source_artifact_kind='prd'."""
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        doc_rows = [
            _orphan_doc_row(
                did="prd-1",
                title="My Feature PRD",
                doc_type="prd",
                feature_slug="my-feature-prd",
                status="approved",
            )
        ]
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertEqual(result.total_feature_count, 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.source_artifact_kind, "prd")
        self.assertEqual(item.effective_status, "approved")

    async def test_design_spec_matching_existing_feature_not_duplicated(self) -> None:
        """A design_spec whose slug matches an existing feature row is NOT emitted twice."""
        feat = _feature(fid="my-feature", name="My Feature", status="in-progress")
        rows = [_feature_row(feat)]
        doc_rows = [
            _orphan_doc_row(
                did="spec-dup",
                title="My Feature Spec",
                doc_type="design_spec",
                feature_slug="my-feature",
                status="draft",
            )
        ]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        # Only 1 summary item — the real feature, not the orphan spec.
        self.assertEqual(result.total_feature_count, 1)
        self.assertEqual(len(result.feature_summaries), 1)
        self.assertEqual(result.feature_summaries[0].source_artifact_kind, "feature")

    async def test_design_spec_preferred_over_prd_for_same_slug(self) -> None:
        """When both a design_spec and a PRD share a slug, design_spec wins."""
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        doc_rows = [
            _orphan_doc_row(
                did="prd-slug",
                title="PRD Version",
                doc_type="prd",
                feature_slug="shared-slug",
                status="draft",
            ),
            _orphan_doc_row(
                did="spec-slug",
                title="Spec Version",
                doc_type="design_spec",
                feature_slug="shared-slug",
                status="draft",
            ),
        ]
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertEqual(result.total_feature_count, 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.source_artifact_kind, "design_spec")

    async def test_planned_feature_count_reflects_draft_and_approved(self) -> None:
        """planned_feature_count counts real + synthesized items in draft/approved."""
        feat_active = _feature(fid="feat-active", name="Active", status="in-progress")
        feat_draft = _feature(fid="feat-draft", name="Draft Feature", status="draft")
        rows = [_feature_row(feat_active), _feature_row(feat_draft)]

        # One orphan PRD in approved state.
        doc_rows = [
            _orphan_doc_row(
                did="prd-approved",
                title="Approved PRD",
                doc_type="prd",
                feature_slug="orphan-approved",
                status="approved",
            )
        ]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        # total = 3 (2 real + 1 synthesized)
        self.assertEqual(result.total_feature_count, 3)
        # planned = 2: feat-draft (draft) + orphan-approved (approved)
        self.assertEqual(result.planned_feature_count, 2)


class StatusBucketPrecedenceTests(unittest.IsolatedAsyncioTestCase):
    """_derive_status_bucket precedence: blocked > review > active > planned > shaping > completed > deferred > stale_or_mismatched."""

    def setUp(self):
        clear_cache()

    def _make_feature_with_status(self, status: str) -> "Feature":
        from backend.models import Feature
        return Feature(
            id="feat-x",
            name="Test Feature",
            status=status,
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="2026-04-21T10:00:00+00:00",
            linkedDocs=[],
            phases=[],
            relatedFeatures=[],
        )

    async def test_blocked_active_feature_lands_in_blocked(self) -> None:
        """A feature whose effective_status is 'blocked' lands in the blocked bucket regardless of raw status."""
        from backend.application.services.agent_queries.planning import _derive_status_bucket
        from backend.models import Feature, PlanningEffectiveStatus, PlanningMismatchState

        feature = self._make_feature_with_status("active")
        # Inject planning status with effective=blocked
        feature.planningStatus = PlanningEffectiveStatus(
            rawStatus="active",
            effectiveStatus="blocked",
            mismatchState=PlanningMismatchState(state="blocked", isMismatch=True),
        )
        self.assertEqual(_derive_status_bucket(feature), "blocked")

    async def test_active_without_blocked_lands_in_active(self) -> None:
        from backend.application.services.agent_queries.planning import _derive_status_bucket
        feature = self._make_feature_with_status("in-progress")
        self.assertEqual(_derive_status_bucket(feature), "active")

    async def test_planned_status(self) -> None:
        from backend.application.services.agent_queries.planning import _derive_status_bucket
        feature = self._make_feature_with_status("planned")
        self.assertEqual(_derive_status_bucket(feature), "planned")

    async def test_completed_status(self) -> None:
        from backend.application.services.agent_queries.planning import _derive_status_bucket
        feature = self._make_feature_with_status("completed")
        self.assertEqual(_derive_status_bucket(feature), "completed")

    async def test_deferred_status(self) -> None:
        from backend.application.services.agent_queries.planning import _derive_status_bucket
        feature = self._make_feature_with_status("deferred")
        self.assertEqual(_derive_status_bucket(feature), "deferred")

    async def test_status_counts_sum_equals_feature_count(self) -> None:
        """Sum of all status buckets must equal the number of features."""
        from backend.application.services.agent_queries.planning import _build_status_counts
        features = [
            self._make_feature_with_status(s)
            for s in ["active", "in-progress", "blocked", "planned", "draft", "done", "deferred", "backlog"]
        ]
        counts = _build_status_counts(features)
        total = sum([
            counts.shaping, counts.planned, counts.active, counts.blocked,
            counts.review, counts.completed, counts.deferred, counts.stale_or_mismatched,
        ])
        self.assertEqual(total, len(features))


class CtxPerPhaseTests(unittest.TestCase):
    """_build_ctx_per_phase returns unavailable when phase_count == 0."""

    def test_unavailable_when_phase_count_zero(self) -> None:
        from backend.application.services.agent_queries.planning import _build_ctx_per_phase
        result = _build_ctx_per_phase(context_count=5, phase_count=0)
        self.assertEqual(result.source, "unavailable")
        self.assertIsNone(result.ratio)
        self.assertEqual(result.context_count, 5)
        self.assertEqual(result.phase_count, 0)

    def test_ratio_computed_when_phase_count_positive(self) -> None:
        from backend.application.services.agent_queries.planning import _build_ctx_per_phase
        result = _build_ctx_per_phase(context_count=6, phase_count=3)
        self.assertEqual(result.source, "backend")
        self.assertAlmostEqual(result.ratio, 2.0)

    def test_zero_context_with_phases(self) -> None:
        from backend.application.services.agent_queries.planning import _build_ctx_per_phase
        result = _build_ctx_per_phase(context_count=0, phase_count=4)
        self.assertEqual(result.source, "backend")
        self.assertAlmostEqual(result.ratio, 0.0)


class TokenTelemetryTests(unittest.TestCase):
    """_build_token_telemetry returns unavailable when no session roll-up is present."""

    def _bare_feature(self) -> "Feature":
        from backend.models import Feature
        return Feature(
            id="feat-t",
            name="Token Feature",
            status="active",
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="2026-04-21T10:00:00+00:00",
            linkedDocs=[],
            phases=[],
            relatedFeatures=[],
        )

    def test_unavailable_when_no_token_data(self) -> None:
        from backend.application.services.agent_queries.planning import _build_token_telemetry
        features = [self._bare_feature()]
        result = _build_token_telemetry(features)
        self.assertEqual(result.source, "unavailable")
        self.assertIsNone(result.total_tokens)
        self.assertEqual(result.by_model_family, [])

    def test_unavailable_for_empty_list(self) -> None:
        from backend.application.services.agent_queries.planning import _build_token_telemetry
        result = _build_token_telemetry([])
        self.assertEqual(result.source, "unavailable")


class DisplayAgentTypeTests(unittest.TestCase):
    """_derive_display_agent_type returns Orchestrator for root, subagent_type when detected."""

    def test_root_session_returns_orchestrator(self) -> None:
        from backend.routers.api import _derive_display_agent_type
        result = _derive_display_agent_type("", is_root=True)
        self.assertEqual(result, "Orchestrator")

    def test_subagent_type_returned_when_present(self) -> None:
        from backend.routers.api import _derive_display_agent_type
        result = _derive_display_agent_type("Python Backend Engineer", is_root=False)
        self.assertEqual(result, "Python Backend Engineer")

    def test_subagent_type_overrides_root(self) -> None:
        from backend.routers.api import _derive_display_agent_type
        result = _derive_display_agent_type("Frontend Engineer", is_root=True)
        self.assertEqual(result, "Frontend Engineer")

    def test_non_root_no_subagent_returns_none(self) -> None:
        from backend.routers.api import _derive_display_agent_type
        result = _derive_display_agent_type("", is_root=False)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
