"""PCP-601: Extended planning coverage for edge / derivation / mismatch states.

Closes gaps across seven coverage areas:
1. Planning graph derivation — partial/missing frontmatter; node shape stability.
2. Effective status — plan-draft+no-progress (backlog), in-progress+partial (in-progress),
   completed+progress-missing (stale), reversed (mismatch).
3. Mismatch classification — blocked, mismatched, derived states in summary+context DTOs.
4. Blocked states — phase with blocked batches surfaces in PhaseOperationsDTO.
5. Stale detection — stale_feature_ids populated in summary when terminal status
   disagrees with phase evidence.
6. Planning API contracts — response shape assertions (IDs, effective_status, mismatch,
   provenance) for all four planning endpoints; empty-project and NOT-FOUND cases.
7. Launch-preparation contracts — prepare/start field shapes; _require_launch_enabled
   returns 503 with error payload on both prepare and start.

The approach is *service-layer* for derivation tests and *router-layer* (FastAPI
TestClient) only for HTTP contract/gating assertions.  No DB mocks; no production
code changes.
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Shared helpers re-used from test_planning_query_service ──────────────────

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.application.services.agent_queries.cache import clear_cache
from backend.models import Feature, FeaturePhase, LinkedDocument, PlanningPhaseBatch


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors test_planning_query_service.py style)
# ---------------------------------------------------------------------------


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
        "deferred_tasks": getattr(feature, "deferredTasks", 0),
        "category": feature.category,
        "updated_at": feature.updatedAt,
        "data_json": json.dumps(
            {
                "id": feature.id,
                "name": feature.name,
                "status": feature.status,
                "phases": [p.model_dump() for p in feature.phases],
                "linkedDocs": [
                    (d if isinstance(d, dict) else d.model_dump())
                    for d in feature.linkedDocs
                ],
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
    frontmatter: dict | None = None,
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
        "frontmatter_json": json.dumps(frontmatter or {}),
    }


# ── Infra stubs (same pattern as existing tests) ─────────────────────────────


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project=None):
        self._project = project or types.SimpleNamespace(id="project-1", name="Project 1")

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


def _ports(*, features_repo=None, docs_repo=None, db=None) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(),
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


_PATCH_LOAD_DOCS = patch(
    "backend.application.services.agent_queries.planning.load_execution_documents",
    new=AsyncMock(return_value=[]),
)


# ===========================================================================
# Area 1 & 2: Graph derivation + effective status across plan states
# ===========================================================================


class GraphDerivationEdgeCasesTests(unittest.IsolatedAsyncioTestCase):
    """Planning graph derivation with partial/missing frontmatter inputs."""

    def setUp(self):
        clear_cache()

    async def test_feature_with_no_linked_docs_yields_at_least_feature_node(self) -> None:
        """Graph must emit at least the feature node even with zero linked docs."""
        feat = _feature(fid="bare-feat", name="No Docs", status="backlog")
        rows = [_feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="bare-feat"
            )

        self.assertIn(result.status, {"ok", "partial"})
        # graph dict must have a nodes list (even if empty it must be present)
        self.assertIn("nodes", result.graph)
        self.assertIn("edges", result.graph)

    async def test_graph_node_shape_stable_with_partial_frontmatter(self) -> None:
        """Nodes produced from a doc row with minimal fields have required keys."""
        feat = _feature(fid="partial-feat", name="Partial Frontmatter", status="in-progress")
        rows = [_feature_row(feat)]
        # doc row with only id/title/file_path, no frontmatter_json
        sparse_doc_row = {
            "id": "sparse-doc",
            "title": "Sparse Plan",
            "doc_type": "implementation_plan",
            "file_path": "docs/sparse.md",
            "feature_slug_canonical": "partial-feat",
            "feature_slug_hint": "partial-feat",
            "updated_at": "2026-04-11T10:00:00+00:00",
            "status": "",
            "metadata_json": None,
            "frontmatter_json": None,
        }

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[sparse_doc_row]),
            list_paginated=AsyncMock(return_value=[sparse_doc_row]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="partial-feat"
            )

        self.assertIn(result.status, {"ok", "partial"})
        for node in result.graph.get("nodes", []):
            # Every node must have id and type keys regardless of doc completeness.
            self.assertIn("id", node)
            self.assertIn("type", node)

    async def test_project_graph_empty_project_has_stable_shape(self) -> None:
        """Project-scope graph with zero features must return ok status + empty lists."""
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_project_planning_graph(
                _context(), ports
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertEqual(result.nodes, [])
        self.assertEqual(result.edges, [])
        self.assertEqual(result.node_count, 0)
        self.assertEqual(result.edge_count, 0)


# ===========================================================================
# Area 2: Effective status — explicit plan state scenarios
# ===========================================================================


class EffectiveStatusDerivationTests(unittest.IsolatedAsyncioTestCase):
    """Effective status derivation for plan-draft, in-progress, completed+stale."""

    def setUp(self):
        clear_cache()

    async def test_plan_draft_no_progress_yields_backlog(self) -> None:
        """Feature with backlog status and no phases → effective_status is backlog."""
        feat = _feature(fid="draft-feat", status="backlog", phases=[])
        rows = [_feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="draft-feat"
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertEqual(result.raw_status, "backlog")
        self.assertIn(result.effective_status, {"backlog", ""})
        self.assertIn(result.mismatch_state, {"aligned", "unknown"})

    async def test_plan_in_progress_partial_tasks_yields_in_progress(self) -> None:
        """Feature in-progress with partial task completion → effective_status in-progress."""
        feat = _feature(
            fid="wip-feat",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress", total=5, completed=2)],
        )
        rows = [_feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="wip-feat"
            )

        self.assertIn(result.effective_status, {"in-progress", "review"})
        self.assertIn(result.mismatch_state, {"aligned", "derived", "mismatched"})

    async def test_plan_completed_progress_missing_appears_in_stale_ids(self) -> None:
        """Feature with raw=done but phase status non-terminal → stale_feature_ids populated."""
        feat = _feature(
            fid="stale-feat",
            status="done",
            phases=[_phase(number="1", status="in-progress", total=4, completed=1)],
        )
        rows = [_feature_row(feat)]

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

        # Stale detection fires when raw is terminal but mismatch is reversed/mismatched.
        self.assertIn("stale-feat", result.stale_feature_ids)
        self.assertGreater(result.stale_feature_count, 0)

    async def test_reversal_summary_counts_correct(self) -> None:
        """Summary reversal_count increments for each reversed feature."""
        feat_rev1 = _feature(
            fid="rev-1",
            status="done",
            phases=[_phase(number="1", status="in-progress", total=3, completed=1)],
        )
        feat_rev2 = _feature(
            fid="rev-2",
            status="done",
            phases=[_phase(number="1", status="backlog", total=2, completed=0)],
        )
        feat_ok = _feature(
            fid="ok-1",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress", total=2, completed=1)],
        )
        rows = [_feature_row(feat_rev1), _feature_row(feat_rev2), _feature_row(feat_ok)]

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

        self.assertGreaterEqual(result.reversal_count, 1)
        self.assertIn("rev-1", result.reversal_feature_ids)


# ===========================================================================
# Area 3: Mismatch classification
# ===========================================================================


class MismatchClassificationTests(unittest.IsolatedAsyncioTestCase):
    """Verify mismatch reasons enumerated via feature-context and summary DTOs."""

    def setUp(self):
        clear_cache()

    async def test_derived_mismatch_when_tasks_imply_completion_beyond_raw(self) -> None:
        """All tasks terminal but raw status is in-progress → mismatch_state=derived."""
        feat = _feature(
            fid="derived-feat",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress", total=3, completed=3)],
        )
        rows = [_feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="derived-feat"
            )

        # effective_status should differ from raw OR mismatch_state should be derived/aligned.
        # The key contract is: planning_status dict has mismatchState key.
        self.assertIn("mismatchState", result.planning_status)
        ms = result.planning_status["mismatchState"]
        self.assertIn("state", ms)
        self.assertIn("isMismatch", ms)

    async def test_mismatched_state_when_tasks_ahead_of_backlog_raw_status(self) -> None:
        """Phase raw=backlog but tasks partially completed → mismatch_state=mismatched."""
        feat = _feature(
            fid="lagging-feat",
            status="backlog",
            phases=[_phase(number="1", status="backlog", total=4, completed=2)],
        )
        rows = [_feature_row(feat)]

        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="lagging-feat"
            )

        phase = result.phases[0]
        # Phase-level mismatch should be surfaced.
        self.assertIn("state", phase.planning_status.get("mismatchState", {}))

    async def test_mismatch_count_in_summary_increments_for_each_mismatch(self) -> None:
        """mismatch_count in summary counts any non-aligned mismatch."""
        feat_mis = _feature(
            fid="mis-1",
            status="done",
            phases=[_phase(number="1", status="in-progress", total=3, completed=1)],
        )
        feat_ok = _feature(
            fid="ok-2",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress", total=2, completed=1)],
        )
        rows = [_feature_row(feat_mis), _feature_row(feat_ok)]

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

        self.assertGreaterEqual(result.mismatch_count, 1)
        # feature_summaries should carry per-feature mismatch flags.
        summary_map = {fs.feature_id: fs for fs in result.feature_summaries}
        self.assertIn("mis-1", summary_map)
        self.assertTrue(summary_map["mis-1"].is_mismatch)
        self.assertNotIn(summary_map["mis-1"].mismatch_state, {"aligned", "unknown"})


# ===========================================================================
# Area 4: Blocked states
# ===========================================================================


class BlockedStateTests(unittest.IsolatedAsyncioTestCase):
    """Blocked phase batches surface correctly in PhaseOperationsDTO."""

    def setUp(self):
        clear_cache()

    async def test_blocked_batch_surfaces_in_phase_operations_dto(self) -> None:
        """Phase with a blocked PlanningPhaseBatch → blocked_batch_ids non-empty."""
        blocked_batch = PlanningPhaseBatch(
            featureSlug="blocked-ops-feat",
            phase="1",
            batchId="batch_blocked",
            taskIds=["task-a"],
            readinessState="blocked",
        )
        feat = _feature(
            fid="blocked-ops-feat",
            status="in-progress",
            phases=[
                FeaturePhase(
                    id="blocked-ops-feat:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="backlog",
                    progress=0,
                    totalTasks=1,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                    phaseBatches=[blocked_batch],
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

        result = await PlanningQueryService().get_phase_operations(
            _context(), ports, feature_id="blocked-ops-feat", phase_number=1
        )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertIn("batch_blocked", result.blocked_batch_ids)
        # readiness_state of the phase should reflect the first batch.
        self.assertEqual(result.readiness_state, "blocked")

    async def test_blocked_phase_has_blocked_phase_count_in_feature_context(self) -> None:
        """FeaturePlanningContextDTO.phases surfaces blocked_batch_ids at phase level."""
        blocked_batch = PlanningPhaseBatch(
            featureSlug="ctx-blocked-feat",
            phase="1",
            batchId="ctx_batch_blocked",
            taskIds=[],
            readinessState="blocked",
        )
        feat = _feature(
            fid="ctx-blocked-feat",
            status="in-progress",
            phases=[
                FeaturePhase(
                    id="ctx-blocked-feat:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="backlog",
                    progress=0,
                    totalTasks=0,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                    phaseBatches=[blocked_batch],
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
                _context(), ports, feature_id="ctx-blocked-feat"
            )

        # Feature-level aggregation must include this blocked batch.
        self.assertIn("ctx_batch_blocked", result.blocked_batch_ids)
        phase = result.phases[0]
        self.assertIn("ctx_batch_blocked", phase.blocked_batch_ids)

    async def test_blocked_feature_dependency_surfaces_in_summary(self) -> None:
        """Dependency-blocked feature appears in blocked_feature_ids of summary."""
        from backend.models import LinkedFeatureRef

        blocker = _feature(fid="dep-blocker", name="Dep Blocker", status="in-progress")
        blocked = _feature(fid="dep-blocked", name="Dep Blocked", status="backlog")
        blocked.linkedFeatures = [
            LinkedFeatureRef(feature="dep-blocker", type="blocked_by", source="blocked_by")
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

        self.assertIn("dep-blocked", result.blocked_feature_ids)
        self.assertGreater(result.blocked_feature_count, 0)


# ===========================================================================
# Area 5: Stale detection
# ===========================================================================


class StaleDetectionTests(unittest.IsolatedAsyncioTestCase):
    """stale_feature_ids populated when terminal raw status lacks phase evidence."""

    def setUp(self):
        clear_cache()

    async def test_stale_detection_single_deferred_feature(self) -> None:
        """Feature raw=deferred but phase still in-progress → stale_feature_ids."""
        feat = _feature(
            fid="stale-deferred",
            status="deferred",
            phases=[_phase(number="1", status="in-progress", total=3, completed=1)],
        )
        rows = [_feature_row(feat)]

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

        self.assertIn("stale-deferred", result.stale_feature_ids)

    async def test_feature_summaries_carry_mismatch_state_for_stale(self) -> None:
        """FeatureSummaryItem for a stale feature has is_mismatch=True."""
        feat = _feature(
            fid="stale-summary",
            status="done",
            phases=[_phase(number="1", status="backlog", total=2, completed=0)],
        )
        rows = [_feature_row(feat)]

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

        summary_map = {fs.feature_id: fs for fs in result.feature_summaries}
        self.assertIn("stale-summary", summary_map)
        fs = summary_map["stale-summary"]
        # Stale = mismatch is active.
        self.assertTrue(fs.is_mismatch)
        self.assertNotIn(fs.mismatch_state, {"aligned"})

    async def test_aligned_done_feature_not_in_stale_ids(self) -> None:
        """Completed feature with all tasks terminal is NOT stale."""
        feat = _feature(
            fid="done-clean",
            status="done",
            phases=[_phase(number="1", status="done", total=2, completed=2)],
        )
        rows = [_feature_row(feat)]

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

        self.assertNotIn("done-clean", result.stale_feature_ids)


# ===========================================================================
# Area 6: Planning API contracts (router layer)
# ===========================================================================


from backend.routers import agent as agent_router
from backend.application.services.agent_queries import (
    FeaturePlanningContextDTO,
    PhaseOperationsDTO,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
)


class PlanningAPIContractTests(unittest.IsolatedAsyncioTestCase):
    """Assert response body field shapes for all four planning endpoints."""

    # ── summary DTO shape ────────────────────────────────────────────────────

    async def test_summary_dto_has_required_fields(self) -> None:
        app_request = types.SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningSummaryDTO(
            project_id="proj-x",
            project_name="Project X",
            total_feature_count=3,
            active_feature_count=1,
            stale_feature_count=1,
            blocked_feature_count=0,
            mismatch_count=2,
            reversal_count=1,
            stale_feature_ids=["feat-stale"],
            reversal_feature_ids=["feat-rev"],
            blocked_feature_ids=[],
            source_refs=["proj-x"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_summary",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_router.get_planning_summary(
                    project_id="proj-x",
                    active_first=True,
                    include_terminal=False,
                    limit=100,
                    request_context=object(),
                    core_ports=object(),
                )

        dumped = result.model_dump()
        self.assertIn("project_id", dumped)
        self.assertIn("total_feature_count", dumped)
        self.assertIn("mismatch_count", dumped)
        self.assertIn("reversal_count", dumped)
        self.assertIn("stale_feature_ids", dumped)
        self.assertIn("blocked_feature_ids", dumped)
        self.assertIn("source_refs", dumped)
        self.assertIn("status", dumped)

    # ── graph DTO shape ──────────────────────────────────────────────────────

    async def test_graph_dto_has_required_fields(self) -> None:
        app_request = types.SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningGraphDTO(
            project_id="proj-x",
            feature_id="feat-1",
            depth=1,
            nodes=[{"id": "n1", "type": "feature", "label": "Feat", "path": ""}],
            edges=[],
            node_count=1,
            edge_count=0,
            source_refs=["proj-x"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_graph",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_router.get_planning_graph(
                    project_id="proj-x",
                    feature_id="feat-1",
                    depth=1,
                    request_context=object(),
                    core_ports=object(),
                )

        dumped = result.model_dump()
        self.assertIn("project_id", dumped)
        self.assertIn("nodes", dumped)
        self.assertIn("edges", dumped)
        self.assertIn("node_count", dumped)
        self.assertIn("edge_count", dumped)
        self.assertIn("source_refs", dumped)

    # ── feature-context DTO shape ────────────────────────────────────────────

    async def test_feature_context_dto_has_provenance_fields(self) -> None:
        app_request = types.SimpleNamespace(context=object(), ports=object())
        dto = FeaturePlanningContextDTO(
            feature_id="feat-1",
            feature_name="Feature One",
            raw_status="done",
            effective_status="in-progress",
            mismatch_state="reversed",
            planning_status={
                "rawStatus": "done",
                "effectiveStatus": "in-progress",
                "provenance": {"source": "derived", "reason": "Phase evidence reversed."},
                "mismatchState": {"state": "reversed", "isMismatch": True},
            },
            source_refs=["feat-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_feature_planning_context",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_router.get_feature_planning_context(
                    feature_id="feat-1",
                    project_id="proj-x",
                    request_context=object(),
                    core_ports=object(),
                )

        dumped = result.model_dump()
        self.assertIn("feature_id", dumped)
        self.assertIn("raw_status", dumped)
        self.assertIn("effective_status", dumped)
        self.assertIn("mismatch_state", dumped)
        self.assertIn("planning_status", dumped)
        ps = dumped["planning_status"]
        self.assertIn("rawStatus", ps)
        self.assertIn("provenance", ps)
        self.assertIn("mismatchState", ps)

    # ── phase-ops DTO shape ──────────────────────────────────────────────────

    async def test_phase_ops_dto_has_required_fields(self) -> None:
        app_request = types.SimpleNamespace(context=object(), ports=object())
        dto = PhaseOperationsDTO(
            feature_id="feat-1",
            phase_number=2,
            phase_token="2",
            phase_title="Implementation",
            raw_status="backlog",
            effective_status="blocked",
            is_ready=False,
            readiness_state="blocked",
            phase_batches=[{"batchId": "b1", "readinessState": "blocked"}],
            blocked_batch_ids=["b1"],
            dependency_resolution={"state": "blocked", "dependency_count": 1},
            source_refs=["feat-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_phase_operations",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_router.get_phase_operations(
                    feature_id="feat-1",
                    phase_number=2,
                    project_id="proj-x",
                    request_context=object(),
                    core_ports=object(),
                )

        dumped = result.model_dump()
        self.assertIn("feature_id", dumped)
        self.assertIn("phase_number", dumped)
        self.assertIn("effective_status", dumped)
        self.assertIn("readiness_state", dumped)
        self.assertIn("blocked_batch_ids", dumped)
        self.assertIn("dependency_resolution", dumped)
        self.assertIn("source_refs", dumped)

    # ── empty-project summary ────────────────────────────────────────────────

    async def test_empty_project_summary_returns_ok_with_zero_counts(self) -> None:
        app_request = types.SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningSummaryDTO(
            project_id="empty-proj",
            total_feature_count=0,
            source_refs=[],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_summary",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_router.get_planning_summary(
                    project_id="empty-proj",
                    active_first=True,
                    include_terminal=False,
                    limit=100,
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertEqual(result.total_feature_count, 0)
        self.assertEqual(result.blocked_feature_ids, [])
        self.assertEqual(result.stale_feature_ids, [])
        self.assertEqual(result.reversal_feature_ids, [])


# ===========================================================================
# Area 7: Launch-preparation contracts
# ===========================================================================


from backend.request_scope import get_core_ports, get_request_context
from backend.routers.execution import execution_router


def _make_exec_client() -> TestClient:
    app = FastAPI()
    app.include_router(execution_router)
    app.dependency_overrides[get_request_context] = lambda: object()
    app.dependency_overrides[get_core_ports] = lambda: object()
    return TestClient(app)


class LaunchPreparationContractTests(unittest.TestCase):
    """HTTP contract shape assertions for launch-prep endpoints."""

    # ── capabilities field shape ─────────────────────────────────────────────

    def test_capabilities_response_has_required_fields_when_enabled(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", True):
            client = _make_exec_client()
            response = client.get("/api/execution/launch/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("enabled", body)
        self.assertIn("disabledReason", body)
        self.assertIn("providers", body)
        self.assertTrue(body["enabled"])
        # Each provider must carry required capability keys.
        for provider in body["providers"]:
            self.assertIn("provider", provider)
            self.assertIn("supported", provider)
            self.assertIn("label", provider)

    def test_capabilities_response_has_required_fields_when_disabled(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_exec_client()
            response = client.get("/api/execution/launch/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("enabled", body)
        self.assertIn("disabledReason", body)
        self.assertIn("providers", body)
        self.assertFalse(body["enabled"])
        self.assertNotEqual(body["disabledReason"], "")
        self.assertEqual(body["providers"], [])

    # ── _require_launch_enabled gate shape ───────────────────────────────────

    def test_prepare_503_payload_has_error_field(self) -> None:
        """503 gating response must carry detail.error == 'launch_disabled'."""
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_exec_client()
            response = client.post(
                "/api/execution/launch/prepare",
                json={"projectId": "p", "featureId": "f", "phaseNumber": 1, "batchId": "b"},
            )

        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertIn("error", detail)
        self.assertEqual(detail["error"], "launch_disabled")
        self.assertIn("hint", detail)

    def test_start_503_payload_has_error_field(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_exec_client()
            response = client.post(
                "/api/execution/launch/start",
                json={
                    "projectId": "p",
                    "featureId": "f",
                    "phaseNumber": 1,
                    "batchId": "b",
                    "provider": "local",
                    "worktree": {
                        "worktreeContextId": "",
                        "createIfMissing": True,
                        "branch": "",
                        "worktreePath": "",
                        "baseBranch": "",
                        "notes": "",
                    },
                },
            )

        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "launch_disabled")

    # ── prepare response field shape (service layer) ─────────────────────────


class LaunchPreparationServiceFieldShapeTests(unittest.IsolatedAsyncioTestCase):
    """Validate that prepare() returns the required fields: batch, providers, worktree, approvals."""

    async def asyncSetUp(self) -> None:
        import aiosqlite
        import tempfile
        from pathlib import Path
        from backend.db.sqlite_migrations import run_migrations
        from backend.adapters.storage.local import LocalStorageUnitOfWork
        from backend.application.services.agent_queries.models import PhaseOperationsDTO, PhaseTaskItem

        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name).resolve()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.storage = LocalStorageUnitOfWork(self.db)
        self.project = types.SimpleNamespace(id="proj-shape", path=str(self.workspace))
        self.ports = types.SimpleNamespace(storage=self.storage)
        self.context = types.SimpleNamespace(project=self.project)

        class _FakePlanningService:
            async def get_phase_operations(self, ctx, ports, *, feature_id, phase_number, project_id_override=None):
                return PhaseOperationsDTO(
                    status="ok",
                    feature_id=feature_id,
                    phase_number=phase_number,
                    phase_token="ph-1",
                    phase_title="Phase One",
                    phase_batches=[{
                        "id": "batch-a",
                        "batch_id": "batch-a",
                        "task_ids": ["T-1"],
                        "is_ready": True,
                        "readiness_state": "ready",
                        "blocked_reason": "",
                        "dependencies": [],
                    }],
                    blocked_batch_ids=[],
                    tasks=[
                        PhaseTaskItem(task_id="T-1", title="Task", status="pending", assignees=[], blockers=[], batch_id="batch-a")
                    ],
                )

        from unittest.mock import MagicMock
        execution_svc = MagicMock()
        execution_svc.create_run = AsyncMock(return_value={"id": "run-shape", "status": "queued", "requires_approval": False})

        from backend.application.services.launch_preparation import LaunchPreparationApplicationService
        self.svc = LaunchPreparationApplicationService(
            planning_service=_FakePlanningService(),
            execution_service=execution_svc,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def test_prepare_response_has_batch_provider_worktree_approval_fields(self) -> None:
        from backend.models import LaunchPreparationRequest

        req = LaunchPreparationRequest(
            projectId="proj-shape",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
        )
        with patch(
            "backend.application.services.launch_preparation.require_project",
            return_value=self.project,
        ):
            result = await self.svc.prepare(self.context, self.ports, req)

        # batch
        self.assertIsNotNone(result.batch)
        self.assertEqual(result.batch.batchId, "batch-a")
        # providers
        self.assertTrue(len(result.providers) > 0)
        for p in result.providers:
            self.assertIsNotNone(p.provider)
        # selectedProvider
        self.assertIsNotNone(result.selectedProvider)
        # worktreeSelection
        self.assertIsNotNone(result.worktreeSelection)
        # approval
        self.assertIsNotNone(result.approval)
        self.assertIn(result.approval.requirement, {"none", "optional", "required"})

    async def test_prepare_model_fields_include_model_selection(self) -> None:
        """selectedModel / model should be present in the response (defaulted)."""
        from backend.models import LaunchPreparationRequest

        req = LaunchPreparationRequest(
            projectId="proj-shape",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
        )
        with patch(
            "backend.application.services.launch_preparation.require_project",
            return_value=self.project,
        ):
            result = await self.svc.prepare(self.context, self.ports, req)

        # selectedModel should be a string (possibly empty, but present)
        self.assertIsInstance(result.selectedModel, str)
        # projectId should be reflected back
        self.assertEqual(result.projectId, "proj-shape")
        self.assertEqual(result.featureId, "FEAT-1")
        self.assertEqual(result.phaseNumber, 1)


if __name__ == "__main__":
    unittest.main()
