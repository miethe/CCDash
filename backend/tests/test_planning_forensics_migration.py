"""Compatibility tests for the planning→evidence-summary migration (P2-001, P2-002).

Verifies that migrating ``get_feature_planning_context`` and
``get_feature_sessions_v1`` from ``FeatureForensicsQueryService`` to
``FeatureEvidenceSummaryService`` did not change response shapes.

Coverage:
- Planning context returns ``total_tokens`` (int) and ``token_usage_by_model`` with
  canonical fields (opus, sonnet, haiku, other, total — all int).
- Partial evidence propagates correctly into the planning context status.
- Zero-session evidence produces zero-valued token fields.
- ``get_feature_sessions_v1`` response includes a ``feature_slug`` field derived
  from the evidence summary.
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.models import (
    FeatureEvidenceSummary,
    TokenUsageByModel,
)
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.models import Feature, FeaturePhase


# ── Shared fixtures ──────────────────────────────────────────────────────────


def _phase(
    *,
    number: str = "1",
    status: str = "in-progress",
    total: int = 2,
    completed: int = 0,
) -> FeaturePhase:
    return FeaturePhase(
        id=f"feat:phase-{number}",
        phase=number,
        title=f"Phase {number}",
        status=status,
        progress=0,
        totalTasks=total,
        completedTasks=completed,
        deferredTasks=0,
        tasks=[],
        phaseBatches=[],
    )


def _feature_row(
    fid: str = "feat-migration",
    name: str = "Migration Feature",
    status: str = "in-progress",
    phases: list | None = None,
) -> dict:
    feature = Feature(
        id=fid,
        name=name,
        status=status,
        totalTasks=0,
        completedTasks=0,
        category="enhancement",
        tags=[],
        updatedAt="2026-05-01T10:00:00+00:00",
        linkedDocs=[],
        phases=phases or [],
        relatedFeatures=[],
    )
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
                "linkedDocs": [],
                "linkedFeatures": [],
            }
        ),
    }


def _evidence_summary(
    *,
    feature_id: str = "feat-migration",
    feature_slug: str = "feat-migration",
    status: str = "ok",
    total_tokens: int = 500,
    opus: int = 200,
    sonnet: int = 200,
    haiku: int = 50,
    other: int = 50,
    session_count: int = 3,
) -> FeatureEvidenceSummary:
    total = opus + sonnet + haiku + other
    return FeatureEvidenceSummary(
        status=status,
        feature_id=feature_id,
        feature_slug=feature_slug,
        feature_status="in-progress",
        name="Migration Feature",
        session_count=session_count,
        total_tokens=total_tokens,
        total_cost=0.05,
        token_usage_by_model=TokenUsageByModel(
            opus=opus,
            sonnet=sonnet,
            haiku=haiku,
            other=other,
            total=total,
        ),
    )


# ── Infrastructure stubs (mirrors test_planning_query_service.py) ────────────


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


_PATCH_LOAD_DOCS = patch(
    "backend.application.services.agent_queries.planning.load_execution_documents",
    new=AsyncMock(return_value=[]),
)

_PATCH_EVIDENCE = (
    "backend.application.services.agent_queries.feature_evidence_summary"
    ".FeatureEvidenceSummaryService.get_summary"
)


# ── Planning contract tests ──────────────────────────────────────────────────


class PlanningContextTokenContractTests(unittest.IsolatedAsyncioTestCase):
    """get_feature_planning_context token-field contract after P2-001 migration."""

    def setUp(self):
        clear_cache()

    async def test_total_tokens_is_int(self) -> None:
        """total_tokens on the FeaturePlanningContextDTO must be an int."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)
        evidence = _evidence_summary(total_tokens=1234)

        with _PATCH_LOAD_DOCS:
            with patch(_PATCH_EVIDENCE, new=AsyncMock(return_value=evidence)):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        self.assertIsInstance(result.total_tokens, int)
        self.assertEqual(result.total_tokens, 1234)

    async def test_token_usage_by_model_canonical_fields(self) -> None:
        """token_usage_by_model must expose opus, sonnet, haiku, other, total — all int."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)
        evidence = _evidence_summary(
            total_tokens=600, opus=300, sonnet=200, haiku=60, other=40
        )

        with _PATCH_LOAD_DOCS:
            with patch(_PATCH_EVIDENCE, new=AsyncMock(return_value=evidence)):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        tum = result.token_usage_by_model
        # All five fields must be present.
        for field in ("opus", "sonnet", "haiku", "other", "total"):
            self.assertTrue(
                hasattr(tum, field),
                f"token_usage_by_model missing field: {field}",
            )
            self.assertIsInstance(
                getattr(tum, field),
                int,
                f"token_usage_by_model.{field} should be int",
            )

        self.assertEqual(tum.opus, 300)
        self.assertEqual(tum.sonnet, 200)
        self.assertEqual(tum.haiku, 60)
        self.assertEqual(tum.other, 40)
        self.assertEqual(tum.total, 600)

    async def test_partial_evidence_marks_context_partial(self) -> None:
        """When evidence summary returns status='partial', planning context is also partial."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)
        evidence = _evidence_summary(status="partial", total_tokens=100)

        with _PATCH_LOAD_DOCS:
            with patch(_PATCH_EVIDENCE, new=AsyncMock(return_value=evidence)):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        # Partial evidence must propagate upward; status may be "ok" if feature
        # itself resolved cleanly but partial evidence triggers at minimum "partial".
        self.assertIn(result.status, {"ok", "partial"})
        # The token fields are still populated from the partial evidence.
        self.assertEqual(result.total_tokens, 100)

    async def test_partial_evidence_status_propagates_to_partial(self) -> None:
        """Evidence status='partial' must produce context status='partial', not 'ok'."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        # Use a clean docs_repo to avoid other partial sources
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)
        evidence = _evidence_summary(status="partial", total_tokens=100)

        with _PATCH_LOAD_DOCS:
            with patch(_PATCH_EVIDENCE, new=AsyncMock(return_value=evidence)):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        self.assertEqual(result.status, "partial")

    async def test_zero_sessions_evidence_produces_zero_token_fields(self) -> None:
        """When evidence summary has zero sessions, token fields default to zero."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)
        evidence = _evidence_summary(
            total_tokens=0,
            opus=0,
            sonnet=0,
            haiku=0,
            other=0,
            session_count=0,
        )

        with _PATCH_LOAD_DOCS:
            with patch(_PATCH_EVIDENCE, new=AsyncMock(return_value=evidence)):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        self.assertEqual(result.total_tokens, 0)
        tum = result.token_usage_by_model
        self.assertEqual(tum.opus, 0)
        self.assertEqual(tum.sonnet, 0)
        self.assertEqual(tum.haiku, 0)
        self.assertEqual(tum.other, 0)
        self.assertEqual(tum.total, 0)

    async def test_evidence_exception_falls_back_to_zero_and_partial(self) -> None:
        """If evidence summary raises, token fields are zero and status is partial."""
        row = _feature_row()
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            with patch(
                _PATCH_EVIDENCE,
                new=AsyncMock(side_effect=RuntimeError("evidence unavailable")),
            ):
                result = await PlanningQueryService().get_feature_planning_context(
                    _context(), ports, feature_id="feat-migration"
                )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.total_tokens, 0)
        tum = result.token_usage_by_model
        self.assertEqual(tum.total, 0)


# ── CLI v1 feature sessions contract tests ───────────────────────────────────


class FeatureSessionsV1ContractTests(unittest.IsolatedAsyncioTestCase):
    """get_feature_sessions_v1 shape contract after P2-002 migration."""

    def setUp(self):
        clear_cache()

    def _build_ports_and_modal_mock(self, feature_id: str, feature_row: dict) -> tuple:
        """Return (ports, feature_row) with session modal service pre-patched."""
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[feature_row]),
            get_by_id=AsyncMock(return_value=feature_row),
        )
        ports = _ports(features_repo=features_repo)
        return ports

    async def test_sessions_response_includes_feature_slug_field(self) -> None:
        """FeatureSessionsDTO must have a feature_slug field."""
        from backend.routers._client_v1_features import get_feature_sessions_v1
        from backend.application.services import resolve_application_request

        row = _feature_row(fid="feat-slug-test", name="Slug Test Feature")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        # Stub the modal detail service's get_sessions to return empty sessions.
        mock_section = MagicMock()
        mock_section.status = "ok"
        mock_section.data = {"rows": [], "total": 0, "has_more": False}

        evidence = _evidence_summary(
            feature_id="feat-slug-test",
            feature_slug="feat-slug-test",
        )

        with patch(
            "backend.application.services.feature_surface.modal_service"
            ".FeatureModalDetailService.get_sessions",
            new=AsyncMock(return_value=mock_section),
        ):
            with patch(
                "backend.routers._client_v1_features._get_evidence_summary_service",
                return_value=MagicMock(
                    get_summary=AsyncMock(return_value=evidence)
                ),
            ):
                with patch(
                    "backend.routers._client_v1_features._resolve_app_request",
                ) as mock_resolve:
                    # Build a minimal app_request stub
                    app_req = types.SimpleNamespace(
                        context=_context(),
                        ports=ports,
                    )
                    mock_resolve.return_value = app_req

                    envelope = await get_feature_sessions_v1(
                        "feat-slug-test",
                        limit=10,
                        offset=0,
                        request_context=_context(),
                        core_ports=ports,
                    )

        dto = envelope.data
        self.assertTrue(
            hasattr(dto, "feature_slug"),
            "FeatureSessionsDTO must have a feature_slug field",
        )
        self.assertIsInstance(dto.feature_slug, str)

    async def test_sessions_slug_derived_from_evidence_summary(self) -> None:
        """feature_slug in sessions response is derived from evidence summary."""
        from backend.routers._client_v1_features import get_feature_sessions_v1

        row = _feature_row(fid="feat-abc", name="ABC Feature")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        mock_section = MagicMock()
        mock_section.status = "ok"
        mock_section.data = {"rows": [], "total": 0, "has_more": False}

        evidence = _evidence_summary(
            feature_id="feat-abc",
            feature_slug="feat-abc-canonical",  # slug enriched by evidence service
        )

        with patch(
            "backend.application.services.feature_surface.modal_service"
            ".FeatureModalDetailService.get_sessions",
            new=AsyncMock(return_value=mock_section),
        ):
            with patch(
                "backend.routers._client_v1_features._get_evidence_summary_service",
                return_value=MagicMock(
                    get_summary=AsyncMock(return_value=evidence)
                ),
            ):
                with patch(
                    "backend.routers._client_v1_features._resolve_app_request",
                ) as mock_resolve:
                    app_req = types.SimpleNamespace(
                        context=_context(),
                        ports=ports,
                    )
                    mock_resolve.return_value = app_req

                    envelope = await get_feature_sessions_v1(
                        "feat-abc",
                        limit=10,
                        offset=0,
                        request_context=_context(),
                        core_ports=ports,
                    )

        dto = envelope.data
        self.assertEqual(dto.feature_slug, "feat-abc-canonical")

    async def test_sessions_slug_falls_back_to_feature_id_on_evidence_error(self) -> None:
        """feature_slug falls back to the raw feature_id when evidence summary raises."""
        from backend.routers._client_v1_features import get_feature_sessions_v1

        row = _feature_row(fid="feat-fallback", name="Fallback Feature")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        mock_section = MagicMock()
        mock_section.status = "ok"
        mock_section.data = {"rows": [], "total": 0, "has_more": False}

        with patch(
            "backend.application.services.feature_surface.modal_service"
            ".FeatureModalDetailService.get_sessions",
            new=AsyncMock(return_value=mock_section),
        ):
            with patch(
                "backend.routers._client_v1_features._get_evidence_summary_service",
                return_value=MagicMock(
                    get_summary=AsyncMock(side_effect=Exception("service down"))
                ),
            ):
                with patch(
                    "backend.routers._client_v1_features._resolve_app_request",
                ) as mock_resolve:
                    app_req = types.SimpleNamespace(
                        context=_context(),
                        ports=ports,
                    )
                    mock_resolve.return_value = app_req

                    envelope = await get_feature_sessions_v1(
                        "feat-fallback",
                        limit=10,
                        offset=0,
                        request_context=_context(),
                        core_ports=ports,
                    )

        dto = envelope.data
        # Slug falls back to the feature_id when evidence is unavailable.
        self.assertEqual(dto.feature_slug, "feat-fallback")

    async def test_sessions_response_shape(self) -> None:
        """FeatureSessionsDTO must include feature_id, feature_slug, sessions, total."""
        from backend.routers._client_v1_features import get_feature_sessions_v1

        row = _feature_row(fid="feat-shape", name="Shape Feature")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        mock_section = MagicMock()
        mock_section.status = "ok"
        mock_section.data = {"rows": [], "total": 0, "has_more": False}

        evidence = _evidence_summary(feature_id="feat-shape", feature_slug="feat-shape")

        with patch(
            "backend.application.services.feature_surface.modal_service"
            ".FeatureModalDetailService.get_sessions",
            new=AsyncMock(return_value=mock_section),
        ):
            with patch(
                "backend.routers._client_v1_features._get_evidence_summary_service",
                return_value=MagicMock(
                    get_summary=AsyncMock(return_value=evidence)
                ),
            ):
                with patch(
                    "backend.routers._client_v1_features._resolve_app_request",
                ) as mock_resolve:
                    app_req = types.SimpleNamespace(
                        context=_context(),
                        ports=ports,
                    )
                    mock_resolve.return_value = app_req

                    envelope = await get_feature_sessions_v1(
                        "feat-shape",
                        limit=10,
                        offset=0,
                        request_context=_context(),
                        core_ports=ports,
                    )

        dto = envelope.data
        for field in ("feature_id", "feature_slug", "sessions", "total"):
            self.assertTrue(
                hasattr(dto, field),
                f"FeatureSessionsDTO missing required field: {field}",
            )
        self.assertIsInstance(dto.sessions, list)
        self.assertIsInstance(dto.total, int)


# ── Token model shape unit test ──────────────────────────────────────────────


class TokenUsageByModelShapeTests(unittest.TestCase):
    """Direct unit tests for TokenUsageByModel field shapes (no service calls)."""

    def test_all_canonical_fields_present(self) -> None:
        """TokenUsageByModel exposes opus, sonnet, haiku, other, total."""
        tum = TokenUsageByModel(opus=10, sonnet=20, haiku=5, other=5, total=40)
        for field in ("opus", "sonnet", "haiku", "other", "total"):
            self.assertTrue(hasattr(tum, field), f"Missing field: {field}")
            self.assertIsInstance(getattr(tum, field), int)

    def test_default_values_are_zero_int(self) -> None:
        """All fields default to 0 (int) when not supplied."""
        tum = TokenUsageByModel()
        for field in ("opus", "sonnet", "haiku", "other", "total"):
            self.assertEqual(getattr(tum, field), 0)
            self.assertIsInstance(getattr(tum, field), int)

    def test_total_can_be_independent_of_component_sum(self) -> None:
        """total is a separate field that the caller sets explicitly."""
        # The model itself doesn't auto-compute total from components.
        tum = TokenUsageByModel(opus=100, sonnet=200, haiku=0, other=0, total=300)
        self.assertEqual(tum.total, 300)

    def test_feature_evidence_summary_carries_token_usage_by_model(self) -> None:
        """FeatureEvidenceSummary.token_usage_by_model is a TokenUsageByModel instance."""
        evidence = FeatureEvidenceSummary(
            status="ok",
            feature_id="test",
            token_usage_by_model=TokenUsageByModel(
                opus=50, sonnet=100, haiku=10, other=5, total=165
            ),
        )
        self.assertIsInstance(evidence.token_usage_by_model, TokenUsageByModel)
        self.assertEqual(evidence.token_usage_by_model.sonnet, 100)


if __name__ == "__main__":
    unittest.main()
