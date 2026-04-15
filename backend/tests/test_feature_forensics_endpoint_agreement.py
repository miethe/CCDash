"""Regression test: GET /v1/features/{id} and GET /v1/features/{id}/sessions must agree.

Both endpoints call ``_get_forensics()`` in ``backend.routers._client_v1_features``
and therefore source their session list from the same ``FeatureForensicsDTO``.
This test locks in that invariant at the handler level so any future divergence
(inline computation, alternate repo path, etc.) breaks CI immediately.

Fixture style mirrors ``test_agent_queries_feature_forensics.py`` — same
``_context()`` / ``_ports()`` / ``_Storage`` pattern, calling handlers
directly with real ``RequestContext`` + ``CorePorts`` objects.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.routers._client_v1_features import get_feature_detail_v1, get_feature_sessions_v1


# ---------------------------------------------------------------------------
# Shared test infrastructure (mirrors test_agent_queries_feature_forensics.py)
# ---------------------------------------------------------------------------


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, features_repo, sessions_repo, documents_repo, tasks_repo, links_repo):
        self.db = object()
        self._features_repo = features_repo
        self._sessions_repo = sessions_repo
        self._documents_repo = documents_repo
        self._tasks_repo = tasks_repo
        self._links_repo = links_repo
        self._session_messages_repo = types.SimpleNamespace(list_by_session=AsyncMock(return_value=[]))

    def features(self):
        return self._features_repo

    def sessions(self):
        return self._sessions_repo

    def documents(self):
        return self._documents_repo

    def tasks(self):
        return self._tasks_repo

    def entity_links(self):
        return self._links_repo

    def session_messages(self):
        return self._session_messages_repo


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


def _ports(*, features=None, sessions=None, documents=None, tasks=None, links=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            features_repo=features or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            sessions_repo=sessions or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            documents_repo=documents or types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks_repo=tasks or types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links_repo=links or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Fixture data: one feature, three linked sessions
# ---------------------------------------------------------------------------

_FEATURE_ID = "feat-agreement-1"

_FEATURE_ROW = {
    "id": _FEATURE_ID,
    "name": "Agreement Feature",
    "feature_slug": "agreement-feature",
    "status": "in_progress",
    "updated_at": "2026-04-14T10:00:00+00:00",
}

_SESSION_ROWS = {
    "session-a": {
        "id": "session-a",
        "status": "completed",
        "started_at": "2026-04-14T08:00:00+00:00",
        "ended_at": "2026-04-14T08:30:00+00:00",
        "total_cost": 1.0,
        "observed_tokens": 100,
        "model": "claude",
        "duration_seconds": 1800,
    },
    "session-b": {
        "id": "session-b",
        "status": "completed",
        "started_at": "2026-04-14T09:00:00+00:00",
        "ended_at": "2026-04-14T09:45:00+00:00",
        "total_cost": 2.5,
        "observed_tokens": 300,
        "model": "claude",
        "duration_seconds": 2700,
    },
    "session-c": {
        "id": "session-c",
        "status": "completed",
        "started_at": "2026-04-14T10:00:00+00:00",
        "ended_at": "2026-04-14T10:15:00+00:00",
        "total_cost": 0.75,
        "observed_tokens": 50,
        "model": "claude",
        "duration_seconds": 900,
    },
}

# entity_links rows as produced by sync_engine._build_feature_session_links:
# link_type = 'related', with feature as source and session as target.
_LINK_ROWS = [
    {
        "source_type": "feature",
        "source_id": _FEATURE_ID,
        "target_type": "session",
        "target_id": "session-a",
        "link_type": "related",
        "confidence": 0.9,
        "metadata_json": "{}",
    },
    {
        "source_type": "feature",
        "source_id": _FEATURE_ID,
        "target_type": "session",
        "target_id": "session-b",
        "link_type": "related",
        "confidence": 0.85,
        "metadata_json": "{}",
    },
    {
        "source_type": "feature",
        "source_id": _FEATURE_ID,
        "target_type": "session",
        "target_id": "session-c",
        "link_type": "related",
        "confidence": 0.7,
        "metadata_json": "{}",
    },
]

_EXPECTED_SESSION_IDS = {"session-a", "session-b", "session-c"}


def _make_sessions_repo():
    async def get_by_id(session_id):
        return _SESSION_ROWS.get(session_id)

    return types.SimpleNamespace(get_by_id=get_by_id)


def _make_links_repo():
    async def get_links_for(source_type, source_id, link_type=None):
        return [
            row for row in _LINK_ROWS
            if row["source_type"] == source_type and row["source_id"] == source_id
        ]

    return types.SimpleNamespace(get_links_for=get_links_for)


def _make_features_repo():
    async def get_by_id(feature_id):
        if feature_id == _FEATURE_ID:
            return _FEATURE_ROW
        return None

    return types.SimpleNamespace(get_by_id=get_by_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class FeatureForensicsEndpointAgreementTests(unittest.IsolatedAsyncioTestCase):
    """Verify that the detail and sessions endpoints always agree on linked sessions.

    Both handlers call ``_get_forensics()`` which calls
    ``FeatureForensicsQueryService.get_forensics()``.  Because the paginated
    ``/sessions`` endpoint slices ``forensics.linked_sessions`` in-process, the
    two endpoints are structurally incapable of disagreeing — but this test
    makes that invariant explicit and will catch any future refactor that
    introduces a second code path.
    """

    async def asyncSetUp(self) -> None:
        self._ctx = _context()
        self._ports = _ports(
            features=_make_features_repo(),
            sessions=_make_sessions_repo(),
            documents=types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks=types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links=_make_links_repo(),
        )

    async def _call_detail(self):
        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            return await get_feature_detail_v1(_FEATURE_ID, self._ctx, self._ports)

    async def _call_sessions(self, limit: int = 100, offset: int = 0):
        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            return await get_feature_sessions_v1(_FEATURE_ID, limit, offset, self._ctx, self._ports)

    async def test_detail_linked_sessions_length_equals_sessions_total(self) -> None:
        """detail.data.linked_sessions count must equal sessions_envelope.data.total."""
        detail_envelope = await self._call_detail()
        sessions_envelope = await self._call_sessions(limit=100, offset=0)

        self.assertEqual(
            len(detail_envelope.data.linked_sessions),
            sessions_envelope.data.total,
            "len(detail.linked_sessions) must equal sessions.total",
        )

    async def test_detail_linked_sessions_ids_match_sessions_page_ids(self) -> None:
        """Session IDs in detail and full-page sessions must be identical (order-insensitive)."""
        detail_envelope = await self._call_detail()
        sessions_envelope = await self._call_sessions(limit=100, offset=0)

        detail_ids = {ref.session_id for ref in detail_envelope.data.linked_sessions}
        sessions_ids = {ref.session_id for ref in sessions_envelope.data.sessions}

        self.assertEqual(
            detail_ids,
            sessions_ids,
            "Session IDs from detail and sessions endpoints must be identical",
        )

    async def test_detail_session_list_equals_full_page_of_paginated_endpoint(self) -> None:
        """With limit >= total, the paginated sessions list equals the detail list (order-insensitive)."""
        detail_envelope = await self._call_detail()
        sessions_envelope = await self._call_sessions(limit=100, offset=0)

        detail_ids = {ref.session_id for ref in detail_envelope.data.linked_sessions}
        page_ids = {ref.session_id for ref in sessions_envelope.data.sessions}

        # Both must contain exactly the expected fixture sessions.
        self.assertEqual(detail_ids, _EXPECTED_SESSION_IDS)
        self.assertEqual(page_ids, _EXPECTED_SESSION_IDS)

        # The two endpoints must agree with each other.
        self.assertEqual(detail_ids, page_ids)

    async def test_sessions_total_reflects_all_linked_sessions_not_just_page(self) -> None:
        """sessions.data.total reflects the full linked count, even when page < total."""
        detail_envelope = await self._call_detail()
        # Request only 1 session per page.
        sessions_envelope = await self._call_sessions(limit=1, offset=0)

        total_from_detail = len(detail_envelope.data.linked_sessions)
        total_from_sessions = sessions_envelope.data.total

        self.assertEqual(
            total_from_detail,
            total_from_sessions,
            "sessions.data.total must equal len(detail.linked_sessions) regardless of page size",
        )
        # Confirm the page itself is smaller than the total.
        self.assertEqual(len(sessions_envelope.data.sessions), 1)
        self.assertGreater(total_from_sessions, 1)

    async def test_paginated_reconstruction_matches_detail(self) -> None:
        """Collect all pages with page_size=1 and verify the union equals detail.linked_sessions."""
        detail_envelope = await self._call_detail()
        total = len(detail_envelope.data.linked_sessions)

        # Gather all pages one session at a time.
        collected_ids: set[str] = set()
        for offset in range(total):
            page_envelope = await self._call_sessions(limit=1, offset=offset)
            for ref in page_envelope.data.sessions:
                collected_ids.add(ref.session_id)

        detail_ids = {ref.session_id for ref in detail_envelope.data.linked_sessions}

        self.assertEqual(
            collected_ids,
            detail_ids,
            "Reconstructed session IDs across all pages must equal detail.linked_sessions IDs",
        )


if __name__ == "__main__":
    unittest.main()
