import types
import unittest
from pathlib import Path

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.session_intelligence import SessionIntelligenceQueryService
from backend.db.repositories.session_embeddings import SqliteSessionEmbeddingRepository


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


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


class _FakeSessionRepo:
    def __init__(self) -> None:
        self.rows = [
            {
                "id": "session-1",
                "project_id": "project-1",
                "task_id": "feature-1",
                "root_session_id": "session-1",
                "started_at": "2026-04-03T10:00:00Z",
                "ended_at": "2026-04-03T10:30:00Z",
                "conversation_family_id": "family-1",
            },
            {
                "id": "session-2",
                "project_id": "project-1",
                "task_id": "feature-2",
                "root_session_id": "session-2",
                "started_at": "2026-04-03T11:00:00Z",
                "ended_at": "2026-04-03T11:45:00Z",
                "conversation_family_id": "family-2",
            },
        ]

    async def list_paginated(self, offset, limit, project_id, sort_by, sort_order, filters):
        _ = sort_by, sort_order
        rows = [row for row in self.rows if row["project_id"] == project_id]
        if filters.get("conversation_family_id"):
            rows = [row for row in rows if row["conversation_family_id"] == filters["conversation_family_id"]]
        if filters.get("root_session_id"):
            rows = [row for row in rows if row["root_session_id"] == filters["root_session_id"]]
        return rows[offset : offset + limit]

    async def get_by_id(self, session_id):
        for row in self.rows:
            if row["id"] == session_id:
                return dict(row)
        return None


class _FakeSessionMessageRepo:
    async def search_messages(self, project_id, query, **kwargs):
        _ = project_id, kwargs
        if "auth0" not in query.lower():
            return []
        return [
            {
                "session_id": "session-1",
                "feature_id": "feature-1",
                "root_session_id": "session-1",
                "thread_session_id": "session-1",
                "message_index": 3,
                "message_id": "msg-1",
                "source_log_id": "log-1",
                "message_type": "message",
                "event_timestamp": "2026-04-03T10:05:00Z",
                "content": "Resolved Auth0 JWT validation errors by normalizing the audience claim.",
            }
        ]


class _FakeSessionIntelligenceRepo:
    async def list_session_sentiment_facts(self, session_id):
        if session_id == "session-1":
            return [
                {
                    "session_id": session_id,
                    "feature_id": "feature-1",
                    "root_session_id": session_id,
                    "thread_session_id": session_id,
                    "source_message_id": "msg-1",
                    "source_log_id": "log-1",
                    "message_index": 1,
                    "sentiment_label": "negative",
                    "sentiment_score": -0.8,
                    "confidence": 0.9,
                    "heuristic_version": "v1",
                    "evidence_json": {"cue": "blocked"},
                }
            ]
        return []

    async def list_session_code_churn_facts(self, session_id):
        if session_id == "session-1":
            return [
                {
                    "session_id": session_id,
                    "feature_id": "feature-1",
                    "root_session_id": session_id,
                    "thread_session_id": session_id,
                    "file_path": "backend/service.py",
                    "first_source_log_id": "log-1",
                    "last_source_log_id": "log-2",
                    "first_message_index": 1,
                    "last_message_index": 3,
                    "touch_count": 3,
                    "distinct_edit_turn_count": 2,
                    "repeat_touch_count": 2,
                    "rewrite_pass_count": 1,
                    "additions_total": 10,
                    "deletions_total": 8,
                    "net_diff_total": 2,
                    "churn_score": 0.72,
                    "progress_score": 0.4,
                    "low_progress_loop": True,
                    "confidence": 0.85,
                    "heuristic_version": "v1",
                    "evidence_json": {"updates": 3},
                }
            ]
        return []

    async def list_session_scope_drift_facts(self, session_id):
        if session_id == "session-1":
            return [
                {
                    "session_id": session_id,
                    "feature_id": "feature-1",
                    "root_session_id": session_id,
                    "thread_session_id": session_id,
                    "planned_path_count": 2,
                    "actual_path_count": 4,
                    "matched_path_count": 2,
                    "out_of_scope_path_count": 2,
                    "drift_ratio": 0.5,
                    "adherence_score": 0.5,
                    "confidence": 0.8,
                    "heuristic_version": "v1",
                    "evidence_json": {"outOfScopePaths": ["docs/extra.md"]},
                }
            ]
        return []


class _FakeEmbeddingRepo:
    def describe_capability(self):
        return types.SimpleNamespace(
            supported=True,
            authoritative=True,
            storage_profile="enterprise",
            notes="Enterprise transcript search uses canonical transcript rows until vector ranking is wired.",
        )


class _FakeStorage:
    def __init__(self, *, session_repo, session_messages_repo, session_intelligence_repo, session_embeddings_repo) -> None:
        self.db = object()
        self._session_repo = session_repo
        self._session_messages_repo = session_messages_repo
        self._session_intelligence_repo = session_intelligence_repo
        self._session_embeddings_repo = session_embeddings_repo

    def sessions(self):
        return self._session_repo

    def session_messages(self):
        return self._session_messages_repo

    def session_intelligence(self):
        return self._session_intelligence_repo

    def session_embeddings(self):
        return self._session_embeddings_repo


def _request_context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Test Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/sessions"),
            docs_dir=Path("/tmp/docs"),
            progress_dir=Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _core_ports(*, session_embeddings_repo) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(project),
        storage=_FakeStorage(
            session_repo=_FakeSessionRepo(),
            session_messages_repo=_FakeSessionMessageRepo(),
            session_intelligence_repo=_FakeSessionIntelligenceRepo(),
            session_embeddings_repo=session_embeddings_repo,
        ),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class SessionIntelligenceQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_semantic_transcripts_returns_capability_aware_results(self) -> None:
        service = SessionIntelligenceQueryService()

        payload = await service.search_semantic_transcripts(
            _request_context(),
            _core_ports(session_embeddings_repo=_FakeEmbeddingRepo()),
            query="Auth0 JWT validation",
        )

        self.assertTrue(payload.capability.supported)
        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.items[0].matchedTerms, ["auth0", "jwt", "validation"])

    async def test_search_semantic_transcripts_uses_local_canonical_fallback(self) -> None:
        service = SessionIntelligenceQueryService()

        payload = await service.search_semantic_transcripts(
            _request_context(),
            _core_ports(session_embeddings_repo=SqliteSessionEmbeddingRepository(object())),
            query="Auth0 JWT validation",
        )

        self.assertTrue(payload.capability.supported)
        self.assertEqual(payload.capability.searchMode, "canonical_lexical")
        self.assertEqual(payload.total, 1)

    async def test_list_session_intelligence_builds_rollups(self) -> None:
        service = SessionIntelligenceQueryService()

        payload = await service.list_session_intelligence(
            _request_context(),
            _core_ports(session_embeddings_repo=_FakeEmbeddingRepo()),
        )

        self.assertEqual(payload.total, 2)
        self.assertEqual(payload.items[0].featureId, "feature-1")
        self.assertEqual(payload.items[0].sentiment.label, "negative")
        self.assertEqual(payload.items[0].churn.label, "high_churn")
        self.assertEqual(payload.items[0].scopeDrift.label, "drifting")

    async def test_get_session_intelligence_detail_returns_typed_fact_payloads(self) -> None:
        service = SessionIntelligenceQueryService()

        payload = await service.get_session_intelligence_detail(
            _request_context(),
            _core_ports(session_embeddings_repo=_FakeEmbeddingRepo()),
            session_id="session-1",
        )

        self.assertEqual(payload.summary.sessionId, "session-1")
        self.assertEqual(payload.sentimentFacts[0].evidence["cue"], "blocked")
        self.assertTrue(payload.churnFacts[0].lowProgressLoop)
        self.assertEqual(payload.scopeDriftFacts[0].outOfScopePathCount, 2)

    async def test_get_session_intelligence_drilldown_flattens_concern_specific_items(self) -> None:
        service = SessionIntelligenceQueryService()

        payload = await service.get_session_intelligence_drilldown(
            _request_context(),
            _core_ports(session_embeddings_repo=_FakeEmbeddingRepo()),
            concern="churn",
        )

        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.items[0].filePath, "backend/service.py")
        self.assertEqual(payload.items[0].label, "low_progress_loop")


if __name__ == "__main__":
    unittest.main()
