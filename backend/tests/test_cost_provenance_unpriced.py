"""Regression tests for costProvenance='unpriced' handling.

Verifies:
  - AgentSession validates with costProvenance='unpriced' (first-class pricing state).
  - AgentSession validates with all five Literal values.
  - An unknown provenance value still raises ValidationError (guard is real).
  - list_sessions skips rows with an invalid costProvenance value and returns 200
    instead of 500-ing the entire page.
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.models import AgentSession
from backend.routers import api as api_router


# ── model validation ─────────────────────────────────────────────────────────


class TestAgentSessionCostProvenanceUnpriced(unittest.TestCase):
    """AgentSession must accept costProvenance='unpriced'."""

    def _minimal(self, **kwargs):
        """Return minimal kwargs that satisfy AgentSession's required fields."""
        return dict(
            id="sess-test",
            title="Test",
            taskId="",
            status="completed",
            model="claude-sonnet",
            durationSeconds=1,
            tokensIn=10,
            tokensOut=10,
            totalCost=0.0,
            startedAt="2026-01-01T00:00:00Z",
            qualityRating=0,
            frictionRating=0,
            **kwargs,
        )

    def test_unpriced_is_valid(self) -> None:
        """costProvenance='unpriced' must not raise ValidationError."""
        session = AgentSession(**self._minimal(costProvenance="unpriced"))
        self.assertEqual(session.costProvenance, "unpriced")

    def test_all_five_literal_values_are_valid(self) -> None:
        """All five Literal values must validate."""
        for value in ("reported", "recalculated", "estimated", "unknown", "unpriced"):
            with self.subTest(value=value):
                session = AgentSession(**self._minimal(costProvenance=value))
                self.assertEqual(session.costProvenance, value)

    def test_unknown_value_still_raises(self) -> None:
        """Values outside the Literal must still raise ValidationError (guard is real)."""
        with self.assertRaises(ValidationError):
            AgentSession(**self._minimal(costProvenance="__not_a_valid_provenance__"))


# ── list_sessions resilience ──────────────────────────────────────────────────


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test", auth_mode="test")


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
        _ = integration, operation, payload
        return {}


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if self.project and str(getattr(self.project, "id", "")) == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _EmptySessionMessageRepo:
    async def list_by_session(self, session_id):
        _ = session_id
        return []


class _FakeStorage:
    def __init__(self, *, session_repo) -> None:
        self.db = object()
        self._session_repo = session_repo

    def sessions(self):
        return self._session_repo

    def session_messages(self):
        return _EmptySessionMessageRepo()

    def entity_links(self):
        return None

    def features(self):
        return None


def _make_row(session_id: str, cost_provenance: str | None = None) -> dict:
    """Build a minimal session row dict.  cost_provenance=None leaves the field absent.

    models_used_json is set to a non-empty value so list_sessions takes the
    materialized fast path and never calls get_logs.
    """
    row = {
        "id": session_id,
        "task_id": "",
        "status": "completed",
        "model": "claude-sonnet",
        "platform_type": "Claude Code",
        "platform_version": "2.1.0",
        "platform_versions_json": "[\"2.1.0\"]",
        "platform_version_transitions_json": "[]",
        "session_type": "session",
        "parent_session_id": None,
        "root_session_id": session_id,
        "agent_id": None,
        "thread_kind": "root",
        "conversation_family_id": session_id,
        "context_inheritance": "fresh",
        "fork_parent_session_id": None,
        "fork_point_log_id": None,
        "fork_point_entry_uuid": None,
        "fork_point_parent_entry_uuid": None,
        "fork_depth": 0,
        "fork_count": 0,
        "duration_seconds": 1,
        "tokens_in": 10,
        "tokens_out": 10,
        "model_io_tokens": 20,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_input_tokens": 0,
        "observed_tokens": 20,
        "tool_reported_tokens": 0,
        "tool_result_input_tokens": 0,
        "tool_result_output_tokens": 0,
        "tool_result_cache_creation_input_tokens": 0,
        "tool_result_cache_read_input_tokens": 0,
        "total_cost": 0.0,
        "started_at": "2026-01-01T00:00:00Z",
        "quality_rating": 0,
        "friction_rating": 0,
        "git_commit_hash": None,
        "git_author": None,
        "git_branch": None,
        "thinking_level": "",
        "session_forensics_json": "{}",
        # Non-empty models_used_json triggers the fast-path badge read and
        # avoids falling through to get_logs in the slow path.
        "models_used_json": '[{"model":"claude-sonnet","count":1}]',
        "agents_used_json": "[]",
        "skills_used_json": "[]",
    }
    if cost_provenance is not None:
        row["cost_provenance"] = cost_provenance
    return row


class _ProvenanceMixedRepo:
    """Returns three rows: valid-unpriced, valid-unknown, invalid-provenance."""

    def __init__(self, rows) -> None:
        self.rows = rows

    async def list_paginated(
        self, offset, limit, project_id, sort_by, sort_order, filters,
        *, workspace_id="default-local"
    ):
        _ = offset, limit, project_id, sort_by, sort_order, filters, workspace_id
        return self.rows

    async def count(self, project_id, filters, *, workspace_id="default-local"):
        _ = project_id, filters, workspace_id
        return len(self.rows)

    async def get_logs(self, session_id, **kwargs):
        _ = session_id, kwargs
        return []

    async def update_session_badges(self, *args, **kwargs):
        _ = args, kwargs


def _request_context(project_id: str = "p-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:op", display_name="Op", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Test Project",
            root_path=api_router.Path("/tmp/proj"),
            sessions_dir=api_router.Path("/tmp/sessions"),
            docs_dir=api_router.Path("/tmp/docs"),
            progress_dir=api_router.Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-test"),
    )


def _core_ports(session_repo) -> CorePorts:
    project = types.SimpleNamespace(id="p-1", name="Test Project")
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(project),
        storage=_FakeStorage(session_repo=session_repo),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class TestListSessionsUnpricedResilience(unittest.IsolatedAsyncioTestCase):
    """list_sessions must skip invalid-provenance rows and serve valid ones."""

    async def test_unpriced_row_is_included(self) -> None:
        """A row with cost_provenance='unpriced' must appear in the response."""
        rows = [_make_row("sess-1", cost_provenance="unpriced")]
        repo = _ProvenanceMixedRepo(rows)
        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.list_sessions(
                request_context=_request_context(),
                core_ports=_core_ports(repo),
            )
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].id, "sess-1")
        self.assertEqual(response.items[0].costProvenance, "unpriced")

    async def test_invalid_provenance_row_is_skipped(self) -> None:
        """A row with an unrecognised cost_provenance must be skipped; 200 is returned."""
        rows = [
            _make_row("sess-good", cost_provenance="unpriced"),
            _make_row("sess-bad", cost_provenance="__invalid_value__"),
        ]
        repo = _ProvenanceMixedRepo(rows)
        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.list_sessions(
                request_context=_request_context(),
                core_ports=_core_ports(repo),
            )
        # sess-good survives; sess-bad is skipped
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].id, "sess-good")
