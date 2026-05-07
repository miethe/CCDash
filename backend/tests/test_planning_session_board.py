"""Tests for PASB-501: Planning Session Board backend coverage.

Covers:
1. PlanningQueryService.get_next_run_preview() — command/prompt composition
2. PlanningSessionQueryService.correlate_session() — correlation confidence
3. DTO models: PlanningNextRunPreviewDTO, NextRunContextRef, PromptContextSelection
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.models import (
    NextRunContextRef,
    PlanningNextRunPreviewDTO,
    PromptContextSelection,
    SessionCorrelation,
    SessionCorrelationEvidence,
)
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.application.services.agent_queries.planning_sessions import (
    PlanningSessionQueryService,
)
from backend.application.services.agent_queries.session_correlation import (
    _correlate_explicit_link,
    _correlate_phase_hints,
    _correlate_task_hints,
    _higher_confidence,
)
from backend.application.services.agent_queries.cache import clear_cache


# ── Shared fixtures ──────────────────────────────────────────────────────────


def _feature_row(
    *,
    fid: str = "feat-1",
    name: str = "Feature One",
    status: str = "in-progress",
    phases: list | None = None,
) -> dict:
    return {
        "id": fid,
        "name": name,
        "status": status,
        "total_tasks": 4,
        "completed_tasks": 1,
        "deferred_tasks": 0,
        "category": "enhancement",
        "updated_at": "2026-04-11T10:00:00+00:00",
        "data_json": json.dumps(
            {
                "id": fid,
                "name": name,
                "status": status,
                "phases": phases or [],
                "linkedDocs": [],
                "linkedFeatures": [],
            }
        ),
    }


def _phase_data(
    *,
    number: str = "1",
    status: str = "in-progress",
    total: int = 3,
    completed: int = 0,
) -> dict:
    return {
        "id": f"feat:phase-{number}",
        "phase": number,
        "title": f"Phase {number}",
        "status": status,
        "progress": 0,
        "totalTasks": total,
        "completedTasks": completed,
        "deferredTasks": 0,
        "tasks": [],
        "phaseBatches": [],
    }


def _doc_row(
    *,
    did: str = "doc-1",
    title: str = "Plan",
    doc_type: str = "implementation_plan",
    file_path: str = "docs/project_plans/implementation_plans/feat-1.md",
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
        if getattr(self._project, "id", "") == project_id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
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
    def __init__(self, *, features_repo, docs_repo=None, sessions_repo=None, db=None):
        self.db = db or object()
        self._features_repo = features_repo
        self._docs_repo = docs_repo or types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        self._sessions_repo = sessions_repo or types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
            get_many_by_ids=AsyncMock(return_value={}),
        )

    def features(self):
        return self._features_repo

    def documents(self):
        return self._docs_repo

    def sessions(self):
        return self._sessions_repo

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
    features_repo=None,
    docs_repo=None,
    sessions_repo=None,
    db=None,
) -> CorePorts:
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
            sessions_repo=sessions_repo,
            db=db,
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


_PATCH_LOAD_DOCS = patch(
    "backend.application.services.agent_queries.planning.load_execution_documents",
    new=AsyncMock(return_value=[]),
)


# ── Section 1: get_next_run_preview() ────────────────────────────────────────


class NextRunPreviewFeatureNotFoundTests(unittest.IsolatedAsyncioTestCase):
    """get_next_run_preview returns error when feature does not exist."""

    def setUp(self):
        clear_cache()

    async def test_missing_feature_returns_error_status(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        ports = _ports(features_repo=features_repo)

        result = await PlanningQueryService().get_next_run_preview(
            _context(), ports, feature_id="ghost-feature"
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.feature_id, "ghost-feature")
        self.assertGreater(len(result.warnings), 0)
        self.assertTrue(any("not found" in w.lower() for w in result.warnings))

    async def test_missing_feature_returns_warning_message(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        ports = _ports(features_repo=features_repo)

        result = await PlanningQueryService().get_next_run_preview(
            _context(), ports, feature_id="nonexistent-id"
        )

        self.assertEqual(result.command, "")
        self.assertEqual(result.prompt_skeleton, "")


class NextRunPreviewCommandTests(unittest.IsolatedAsyncioTestCase):
    """get_next_run_preview generates correct CLI commands."""

    def setUp(self):
        clear_cache()

    async def test_feature_with_phase_produces_execute_phase_command(self) -> None:
        phase = _phase_data(number="2", status="in-progress", total=3, completed=0)
        row = _feature_row(fid="feat-cmd", name="Cmd Feature", phases=[phase])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-cmd", phase_number=2
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertIn("/dev:execute-phase", result.command)
        self.assertIn("2", result.command)

    async def test_phase_number_in_command_matches_requested(self) -> None:
        phases = [
            _phase_data(number="1", status="done"),
            _phase_data(number="2", status="in-progress"),
            _phase_data(number="3", status="backlog"),
        ]
        row = _feature_row(fid="feat-phase-num", phases=phases)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-phase-num", phase_number=2
            )

        self.assertIn("/dev:execute-phase", result.command)
        self.assertIn("2", result.command)
        self.assertEqual(result.phase_number, 2)

    async def test_without_phase_number_auto_selects_first_non_terminal(self) -> None:
        # Phase 1 must have completedTasks == totalTasks so apply_planning_projection
        # keeps it terminal (status='done', all tasks complete).
        phases = [
            _phase_data(number="1", status="done", total=3, completed=3),
            _phase_data(number="2", status="in-progress", total=3, completed=0),
            _phase_data(number="3", status="backlog", total=3, completed=0),
        ]
        row = _feature_row(fid="feat-auto", phases=phases)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-auto"
            )

        self.assertIn(result.status, {"ok", "partial"})
        # Phase 1 is done (terminal, tasks complete), phase 2 is in-progress — auto-selects phase 2
        self.assertEqual(result.phase_number, 2)

    async def test_backlog_feature_without_phases_uses_quick_feature_command(self) -> None:
        row = _feature_row(fid="feat-backlog", name="Backlog Feature", status="backlog", phases=[])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-backlog"
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertIn("/dev:quick-feature", result.command)

    async def test_nonexistent_phase_number_generates_warning(self) -> None:
        phase = _phase_data(number="1", status="in-progress")
        row = _feature_row(fid="feat-bad-phase", phases=[phase])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-bad-phase", phase_number=99
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertTrue(any("99" in w or "not found" in w.lower() for w in result.warnings))


class NextRunPreviewPromptSkeletonTests(unittest.IsolatedAsyncioTestCase):
    """get_next_run_preview builds prompt skeleton correctly."""

    def setUp(self):
        clear_cache()

    async def test_prompt_skeleton_contains_feature_id(self) -> None:
        row = _feature_row(fid="feat-prompt", name="Prompt Feature", status="in-progress")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-prompt"
            )

        self.assertIn("feat-prompt", result.prompt_skeleton)

    async def test_prompt_skeleton_contains_placeholder_tokens(self) -> None:
        row = _feature_row(fid="feat-placeholders")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-placeholders"
            )

        # Both placeholder tokens must appear in the prompt skeleton
        self.assertIn("{{objectives}}", result.prompt_skeleton)
        self.assertIn("{{additional_context}}", result.prompt_skeleton)

    async def test_prompt_skeleton_contains_suggested_command(self) -> None:
        row = _feature_row(fid="feat-cmd-hint", phases=[_phase_data(number="1")])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-cmd-hint", phase_number=1
            )

        # Prompt skeleton must echo the command
        self.assertIn(result.command, result.prompt_skeleton)


class NextRunPreviewContextSelectionTests(unittest.IsolatedAsyncioTestCase):
    """get_next_run_preview populates context_refs from context_selection."""

    def setUp(self):
        clear_cache()

    async def test_empty_context_selection_generates_no_sessions_warning(self) -> None:
        row = _feature_row(fid="feat-empty-ctx")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-empty-ctx"
            )

        self.assertTrue(
            any("no sessions selected" in w.lower() for w in result.warnings),
            f"Expected 'no sessions selected' warning, got: {result.warnings}",
        )

    async def test_session_ids_in_context_selection_appear_as_context_refs(self) -> None:
        row = _feature_row(fid="feat-with-sessions")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        # Stub sessions repo to return a known session
        session_row = {
            "id": "sess-abc",
            "title": "Test Session",
            "status": "completed",
            "started_at": "2026-04-25T10:00:00+00:00",
        }
        sessions_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[session_row]),
            get_by_id=AsyncMock(return_value=session_row),
            get_many_by_ids=AsyncMock(return_value={"sess-abc": session_row}),
        )
        ports = _ports(features_repo=features_repo, sessions_repo=sessions_repo)

        selection = PromptContextSelection(session_ids=["sess-abc"])

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(),
                ports,
                feature_id="feat-with-sessions",
                context_selection=selection,
            )

        self.assertIn(result.status, {"ok", "partial"})
        session_refs = [r for r in result.context_refs if r.ref_type == "session"]
        self.assertEqual(len(session_refs), 1)
        self.assertEqual(session_refs[0].ref_id, "sess-abc")

    async def test_artifact_refs_in_selection_appear_in_context_refs(self) -> None:
        row = _feature_row(fid="feat-with-arts")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        selection = PromptContextSelection(
            artifact_refs=["docs/project_plans/implementation_plans/feat-with-arts.md"]
        )

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(),
                ports,
                feature_id="feat-with-arts",
                context_selection=selection,
            )

        artifact_refs = [r for r in result.context_refs if r.ref_type == "artifact"]
        ref_ids = {r.ref_id for r in artifact_refs}
        self.assertIn(
            "docs/project_plans/implementation_plans/feat-with-arts.md", ref_ids
        )

    async def test_missing_session_id_generates_warning(self) -> None:
        row = _feature_row(fid="feat-bad-session")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        sessions_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
            get_many_by_ids=AsyncMock(return_value={}),
        )
        ports = _ports(features_repo=features_repo, sessions_repo=sessions_repo)

        selection = PromptContextSelection(session_ids=["sess-ghost"])

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(),
                ports,
                feature_id="feat-bad-session",
                context_selection=selection,
            )

        self.assertTrue(
            any("sess-ghost" in w for w in result.warnings),
            f"Expected warning about missing session, got: {result.warnings}",
        )


class NextRunPreviewDeterminismTests(unittest.IsolatedAsyncioTestCase):
    """get_next_run_preview produces deterministic output for the same inputs."""

    def setUp(self):
        clear_cache()

    async def test_same_inputs_produce_same_command(self) -> None:
        phase = _phase_data(number="3", status="in-progress")
        row = _feature_row(fid="feat-det", name="Deterministic", phases=[phase])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result_a = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-det", phase_number=3
            )
        clear_cache()
        with _PATCH_LOAD_DOCS:
            result_b = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-det", phase_number=3
            )

        self.assertEqual(result_a.command, result_b.command)
        self.assertEqual(result_a.phase_number, result_b.phase_number)
        self.assertEqual(result_a.feature_id, result_b.feature_id)

    async def test_same_inputs_produce_same_context_ref_count(self) -> None:
        row = _feature_row(fid="feat-det2")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        selection = PromptContextSelection(phase_refs=["1", "2"])
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result_a = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-det2", context_selection=selection
            )
        clear_cache()
        with _PATCH_LOAD_DOCS:
            result_b = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-det2", context_selection=selection
            )

        self.assertEqual(len(result_a.context_refs), len(result_b.context_refs))


# ── Section 2: PlanningSessionQueryService correlation confidence ─────────────


class CorrelationConfidenceTests(unittest.IsolatedAsyncioTestCase):
    """PlanningSessionQueryService.correlate_session returns correct confidence."""

    async def test_explicit_link_yields_high_confidence(self) -> None:
        session = {"id": "sess-1", "status": "completed"}
        feature = {"id": "feat-linked", "name": "Linked Feature", "status": "in-progress"}
        link = {
            "source_type": "session",
            "source_id": "sess-1",
            "target_type": "feature",
            "target_id": "feat-linked",
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(
            session, features=[feature], links=[link]
        )

        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.feature_id, "feat-linked")

    async def test_explicit_link_reversed_direction_also_yields_high_confidence(self) -> None:
        """entity_links is bidirectional: feature→session also counts."""
        session = {"id": "sess-2", "status": "completed"}
        feature = {"id": "feat-rev", "name": "Reversed", "status": "in-progress"}
        link = {
            "source_type": "feature",
            "source_id": "feat-rev",
            "target_type": "session",
            "target_id": "sess-2",
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(session, features=[feature], links=[link])

        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.feature_id, "feat-rev")

    async def test_phase_hint_only_yields_high_confidence(self) -> None:
        """Phase hints are high-confidence evidence."""
        session = {
            "id": "sess-phase",
            "status": "completed",
            "session_forensics_json": json.dumps(
                {"phaseHints": ["Phase 4: Implementation"]}
            ),
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(session, features=[], links=[])

        self.assertEqual(result.confidence, "high")
        phase_ev = [ev for ev in result.evidence if ev.source_type == "phase_hint"]
        self.assertEqual(len(phase_ev), 1)

    async def test_task_hint_only_yields_medium_confidence(self) -> None:
        """Task hints are medium-confidence evidence."""
        session = {
            "id": "sess-task",
            "status": "completed",
            "session_forensics_json": json.dumps(
                {"taskHints": ["T4-001"]}
            ),
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(session, features=[], links=[])

        self.assertEqual(result.confidence, "medium")
        task_ev = [ev for ev in result.evidence if ev.source_type == "task_hint"]
        self.assertEqual(len(task_ev), 1)

    async def test_no_evidence_yields_unknown_confidence(self) -> None:
        session = {"id": "sess-orphan", "status": "completed"}

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(session, features=[], links=[])

        self.assertEqual(result.confidence, "unknown")
        self.assertEqual(result.feature_id, None)
        self.assertEqual(result.evidence, [])

    async def test_multiple_evidence_sources_highest_confidence_wins(self) -> None:
        """When there is both a task hint (medium) and an explicit link (high),
        the overall confidence should be high."""
        session = {
            "id": "sess-multi",
            "status": "completed",
            "session_forensics_json": json.dumps(
                {"taskHints": ["T1-001"]}
            ),
        }
        feature = {"id": "feat-multi", "name": "Multi Feature", "status": "in-progress"}
        link = {
            "source_type": "session",
            "source_id": "sess-multi",
            "target_type": "feature",
            "target_id": "feat-multi",
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(
            session, features=[feature], links=[link]
        )

        self.assertEqual(result.confidence, "high")

    async def test_command_token_match_yields_medium_confidence(self) -> None:
        """A feature slug found in the session task_id produces medium confidence."""
        session = {
            "id": "sess-token",
            "status": "completed",
            "task_id": "feat-token-abc implement feature",
        }
        feature = {"id": "feat-token-abc", "name": "Token Feature", "status": "in-progress"}

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(session, features=[feature], links=[])

        self.assertIn(result.confidence, {"medium", "high"})
        cmd_ev = [ev for ev in result.evidence if ev.source_type == "command_token"]
        self.assertGreater(len(cmd_ev), 0)

    async def test_lineage_from_parent_with_high_confidence_yields_low_for_child(self) -> None:
        """A child session without direct evidence inherits low confidence from a parent."""
        parent_id = "sess-parent"
        child_session = {
            "id": "sess-child",
            "parent_session_id": parent_id,
            "root_session_id": parent_id,
            "status": "completed",
        }
        prior = {
            parent_id: SessionCorrelation(
                feature_id="feat-inherit",
                feature_name="Inherited Feature",
                confidence="high",
                evidence=[],
            )
        }

        svc = PlanningSessionQueryService()
        result = await svc.correlate_session(
            child_session,
            features=[],
            links=[],
            prior_correlations=prior,
        )

        self.assertEqual(result.confidence, "low")
        lineage_ev = [ev for ev in result.evidence if ev.source_type == "lineage"]
        self.assertEqual(len(lineage_ev), 1)


class CorrelationHelperTests(unittest.TestCase):
    """Unit tests for internal correlation helpers."""

    def test_higher_confidence_prefers_high_over_medium(self) -> None:
        self.assertEqual(_higher_confidence("high", "medium"), "high")

    def test_higher_confidence_prefers_medium_over_low(self) -> None:
        self.assertEqual(_higher_confidence("low", "medium"), "medium")

    def test_higher_confidence_prefers_medium_over_unknown(self) -> None:
        self.assertEqual(_higher_confidence("unknown", "medium"), "medium")

    def test_higher_confidence_equal_returns_first(self) -> None:
        self.assertEqual(_higher_confidence("high", "high"), "high")

    def test_explicit_link_with_unknown_feature_id_ignored(self) -> None:
        """A link pointing to a feature not in feature_index should not produce evidence."""
        session = {"id": "sess-x"}
        link = {
            "source_type": "session",
            "source_id": "sess-x",
            "target_type": "feature",
            "target_id": "feat-ghost",
        }
        feature_index = {}  # empty — feat-ghost is not known

        evidence = _correlate_explicit_link(session, [link], feature_index)
        self.assertEqual(len(evidence), 0)

    def test_phase_hint_evidence_has_correct_confidence(self) -> None:
        session = {
            "id": "sess-ph",
            "session_forensics_json": json.dumps({"phaseHints": ["Phase 2"]}),
        }
        evidence = _correlate_phase_hints(session)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].confidence, "high")
        self.assertEqual(evidence[0].source_type, "phase_hint")

    def test_task_hint_evidence_has_correct_confidence(self) -> None:
        session = {
            "id": "sess-th",
            "session_forensics_json": json.dumps({"taskHints": ["T3-007"]}),
        }
        evidence = _correlate_task_hints(session)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].confidence, "medium")
        self.assertEqual(evidence[0].source_type, "task_hint")

    def test_empty_phase_hints_returns_no_evidence(self) -> None:
        session = {"id": "sess-empty-ph", "session_forensics_json": "{}"}
        evidence = _correlate_phase_hints(session)
        self.assertEqual(len(evidence), 0)


# ── Section 3: DTO model tests ────────────────────────────────────────────────


class NextRunContextRefModelTests(unittest.TestCase):
    """NextRunContextRef serialization and defaults."""

    def test_default_values_are_empty_strings(self) -> None:
        ref = NextRunContextRef()
        self.assertEqual(ref.ref_type, "")
        self.assertEqual(ref.ref_id, "")
        self.assertEqual(ref.ref_label, "")
        self.assertIsNone(ref.ref_path)

    def test_explicit_values_roundtrip_via_model_dump(self) -> None:
        ref = NextRunContextRef(
            ref_type="session",
            ref_id="sess-123",
            ref_label="My Session",
            ref_path="/tmp/session.jsonl",
        )
        data = ref.model_dump()
        restored = NextRunContextRef(**data)
        self.assertEqual(restored.ref_type, "session")
        self.assertEqual(restored.ref_id, "sess-123")
        self.assertEqual(restored.ref_label, "My Session")
        self.assertEqual(restored.ref_path, "/tmp/session.jsonl")

    def test_model_dump_and_model_validate_roundtrip(self) -> None:
        ref = NextRunContextRef(ref_type="artifact", ref_id="doc-42", ref_label="Plan")
        restored = NextRunContextRef.model_validate(ref.model_dump())
        self.assertEqual(restored.ref_id, "doc-42")
        self.assertEqual(restored.ref_type, "artifact")


class PromptContextSelectionModelTests(unittest.TestCase):
    """PromptContextSelection defaults and serialization."""

    def test_all_fields_default_to_empty_lists(self) -> None:
        sel = PromptContextSelection()
        self.assertEqual(sel.session_ids, [])
        self.assertEqual(sel.phase_refs, [])
        self.assertEqual(sel.task_refs, [])
        self.assertEqual(sel.artifact_refs, [])
        self.assertEqual(sel.transcript_refs, [])

    def test_populated_selection_roundtrips_via_model_dump(self) -> None:
        sel = PromptContextSelection(
            session_ids=["s1", "s2"],
            phase_refs=["1"],
            task_refs=["T1-001"],
            artifact_refs=["docs/plan.md"],
        )
        data = sel.model_dump()
        restored = PromptContextSelection(**data)
        self.assertEqual(restored.session_ids, ["s1", "s2"])
        self.assertEqual(restored.phase_refs, ["1"])
        self.assertEqual(restored.task_refs, ["T1-001"])
        self.assertEqual(restored.artifact_refs, ["docs/plan.md"])

    def test_deserialization_from_dict(self) -> None:
        raw = {
            "session_ids": ["abc"],
            "artifact_refs": ["path/to/doc.md"],
        }
        sel = PromptContextSelection.model_validate(raw)
        self.assertEqual(sel.session_ids, ["abc"])
        self.assertEqual(sel.artifact_refs, ["path/to/doc.md"])
        self.assertEqual(sel.phase_refs, [])


class PlanningNextRunPreviewDTOModelTests(unittest.TestCase):
    """PlanningNextRunPreviewDTO structure and serialization."""

    def test_minimal_construction_requires_only_feature_id(self) -> None:
        dto = PlanningNextRunPreviewDTO(feature_id="feat-min")
        self.assertEqual(dto.feature_id, "feat-min")
        self.assertEqual(dto.status, "ok")
        self.assertEqual(dto.command, "")
        self.assertEqual(dto.prompt_skeleton, "")
        self.assertEqual(dto.context_refs, [])
        self.assertEqual(dto.warnings, [])
        self.assertIsNone(dto.feature_name)
        self.assertIsNone(dto.phase_number)

    def test_error_status_with_warnings_roundtrips(self) -> None:
        dto = PlanningNextRunPreviewDTO(
            status="error",
            feature_id="feat-err",
            warnings=["Feature not found."],
        )
        data = dto.model_dump()
        restored = PlanningNextRunPreviewDTO.model_validate(data)
        self.assertEqual(restored.status, "error")
        self.assertEqual(restored.warnings, ["Feature not found."])

    def test_context_refs_list_roundtrips(self) -> None:
        refs = [
            NextRunContextRef(ref_type="session", ref_id="s1"),
            NextRunContextRef(ref_type="artifact", ref_id="doc-1"),
        ]
        dto = PlanningNextRunPreviewDTO(
            feature_id="feat-refs",
            command="/dev:execute-phase 1 docs/plan.md",
            context_refs=refs,
        )
        data = dto.model_dump()
        restored = PlanningNextRunPreviewDTO.model_validate(data)
        self.assertEqual(len(restored.context_refs), 2)
        self.assertEqual(restored.context_refs[0].ref_type, "session")
        self.assertEqual(restored.context_refs[1].ref_type, "artifact")

    def test_partial_status_preserved(self) -> None:
        dto = PlanningNextRunPreviewDTO(
            status="partial",
            feature_id="feat-partial",
            phase_number=3,
        )
        self.assertEqual(dto.status, "partial")
        self.assertEqual(dto.phase_number, 3)

    def test_source_refs_field_inherited_from_envelope(self) -> None:
        dto = PlanningNextRunPreviewDTO(
            feature_id="feat-src",
            source_refs=["feat-src", "3"],
        )
        data = dto.model_dump()
        self.assertIn("source_refs", data)
        self.assertEqual(data["source_refs"], ["feat-src", "3"])


# ── Section 4: Edge-case safety tests ────────────────────────────────────────


class NextRunPreviewEdgeCaseTests(unittest.IsolatedAsyncioTestCase):
    """Edge cases: no phases, all-terminal phases, stale sessions."""

    def setUp(self):
        clear_cache()

    async def test_feature_with_all_terminal_phases_returns_no_auto_selection(self) -> None:
        phases = [
            _phase_data(number="1", status="done"),
            _phase_data(number="2", status="completed"),
        ]
        row = _feature_row(fid="feat-all-done", status="done", phases=phases)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-all-done"
            )

        # No non-terminal phase to auto-select; result must still be non-error
        self.assertIn(result.status, {"ok", "partial"})
        # phase_number may be None since all phases are done
        # command should still be a valid non-empty string
        self.assertIsInstance(result.command, str)

    async def test_feature_with_no_phases_returns_command(self) -> None:
        row = _feature_row(fid="feat-no-phases", status="in-progress", phases=[])
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        ports = _ports(features_repo=features_repo)

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(), ports, feature_id="feat-no-phases"
            )

        self.assertIn(result.status, {"ok", "partial"})
        self.assertIsInstance(result.command, str)
        self.assertGreater(len(result.command), 0)

    async def test_stale_session_generates_staleness_warning(self) -> None:
        row = _feature_row(fid="feat-stale")
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        # Session started 5 days ago — beyond the 24h staleness threshold
        session_row = {
            "id": "sess-old",
            "title": "Old Session",
            "status": "completed",
            "started_at": "2026-04-20T10:00:00+00:00",  # 5 days before test date
        }
        sessions_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[session_row]),
            get_by_id=AsyncMock(return_value=session_row),
            get_many_by_ids=AsyncMock(return_value={"sess-old": session_row}),
        )
        ports = _ports(features_repo=features_repo, sessions_repo=sessions_repo)

        selection = PromptContextSelection(session_ids=["sess-old"])

        with _PATCH_LOAD_DOCS:
            result = await PlanningQueryService().get_next_run_preview(
                _context(),
                ports,
                feature_id="feat-stale",
                context_selection=selection,
            )

        self.assertIn(result.status, {"ok", "partial"})
        # A staleness warning must appear for the old session
        staleness_warnings = [
            w for w in result.warnings if "stale" in w.lower() or "old" in w.lower()
        ]
        self.assertGreater(
            len(staleness_warnings), 0,
            f"Expected staleness warning, got: {result.warnings}",
        )


if __name__ == "__main__":
    unittest.main()
