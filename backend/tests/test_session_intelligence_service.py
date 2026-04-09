import unittest
from pathlib import Path

import aiosqlite

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.session_intelligence import (
    HistoricalSessionIntelligenceBackfillService,
    SessionIntelligenceReadService,
    TranscriptSearchService,
    build_session_embedding_blocks,
)
from backend.db.sqlite_migrations import run_migrations


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
        _ = integration, operation, payload
        return {}


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


def _core_ports(storage, project_id: str = "project-1") -> CorePorts:
    project = type("Project", (), {"id": project_id, "name": "Project 1"})()
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(project),
        storage=storage,
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class SessionIntelligenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.storage = LocalStorageUnitOfWork(self.db)
        self.ports = _core_ports(self.storage)
        self.context = _request_context()
        self.search_service = TranscriptSearchService()
        self.read_service = SessionIntelligenceReadService()

        await self.storage.sessions().upsert(
            {
                "id": "S-1",
                "taskId": "feature-a",
                "status": "completed",
                "model": "gpt-5",
                "startedAt": "2026-04-02T10:00:00Z",
                "endedAt": "2026-04-02T10:05:00Z",
                "updatedAt": "2026-04-02T10:05:00Z",
                "rootSessionId": "S-root",
                "conversationFamilyId": "family-1",
            },
            "project-1",
        )
        await self.storage.session_messages().replace_session_messages(
            "S-1",
            [
                {
                    "messageIndex": 1,
                    "sourceLogId": "log-1",
                    "messageId": "msg-1",
                    "role": "user",
                    "messageType": "message",
                    "content": "The rollout is blocked and the semantic search endpoint is failing.",
                    "timestamp": "2026-04-02T10:00:01Z",
                    "rootSessionId": "S-root",
                    "conversationFamilyId": "family-1",
                    "threadSessionId": "S-1",
                    "sourceProvenance": "sync",
                },
                {
                    "messageIndex": 2,
                    "sourceLogId": "log-2",
                    "messageId": "msg-2",
                    "role": "assistant",
                    "messageType": "message",
                    "content": "I fixed the search ranking and updated the API contract.",
                    "timestamp": "2026-04-02T10:00:03Z",
                    "rootSessionId": "S-root",
                    "conversationFamilyId": "family-1",
                    "threadSessionId": "S-1",
                    "sourceProvenance": "sync",
                },
            ],
        )
        await self.storage.session_intelligence().replace_session_sentiment_facts(
            "S-1",
            [
                {
                    "feature_id": "feature-a",
                    "root_session_id": "S-root",
                    "thread_session_id": "S-1",
                    "source_message_id": "msg-1",
                    "source_log_id": "log-1",
                    "message_index": 1,
                    "sentiment_label": "negative",
                    "sentiment_score": -0.8,
                    "confidence": 0.9,
                    "heuristic_version": "v1",
                    "evidence_json": {"negativeCues": ["blocked", "failing"]},
                }
            ],
        )
        await self.storage.session_intelligence().replace_session_code_churn_facts(
            "S-1",
            [
                {
                    "feature_id": "feature-a",
                    "root_session_id": "S-root",
                    "thread_session_id": "S-1",
                    "file_path": "backend/routers/analytics.py",
                    "first_source_log_id": "log-1",
                    "last_source_log_id": "log-2",
                    "first_message_index": 1,
                    "last_message_index": 2,
                    "touch_count": 3,
                    "distinct_edit_turn_count": 2,
                    "repeat_touch_count": 2,
                    "rewrite_pass_count": 1,
                    "additions_total": 10,
                    "deletions_total": 7,
                    "net_diff_total": 3,
                    "churn_score": 0.71,
                    "progress_score": 0.42,
                    "low_progress_loop": True,
                    "confidence": 0.88,
                    "heuristic_version": "v1",
                    "evidence_json": {"updates": 3},
                }
            ],
        )
        await self.storage.session_intelligence().replace_session_scope_drift_facts(
            "S-1",
            [
                {
                    "feature_id": "feature-a",
                    "root_session_id": "S-root",
                    "thread_session_id": "S-1",
                    "planned_path_count": 2,
                    "actual_path_count": 3,
                    "matched_path_count": 2,
                    "out_of_scope_path_count": 1,
                    "drift_ratio": 0.3333,
                    "adherence_score": 0.6667,
                    "confidence": 0.77,
                    "heuristic_version": "v1",
                    "evidence_json": {"matchingMode": "prefix-aware", "outOfScopePaths": ["docs/extra.md"]},
                }
            ],
        )
        await self.storage.sessions().upsert(
            {
                "id": "S-2",
                "taskId": "feature-b",
                "status": "completed",
                "model": "gpt-5",
                "startedAt": "2026-04-03T10:00:00Z",
                "endedAt": "2026-04-03T10:08:00Z",
                "updatedAt": "2026-04-03T10:08:00Z",
                "rootSessionId": "S-root-2",
                "conversationFamilyId": "family-2",
            },
            "project-1",
        )
        await self.storage.sessions().upsert_logs(
            "S-2",
            [
                {
                    "id": "log-3",
                    "timestamp": "2026-04-03T10:00:01Z",
                    "speaker": "user",
                    "type": "message",
                    "content": "The rollout needs a restart-safe backfill checkpoint.",
                },
                {
                    "id": "log-4",
                    "timestamp": "2026-04-03T10:00:03Z",
                    "speaker": "assistant",
                    "type": "message",
                    "content": "I added the checkpoint and the operator guidance output.",
                },
            ],
        )
        await self.storage.sessions().upsert_file_updates(
            "S-2",
            [
                {
                    "filePath": "backend/scripts/agentic_intelligence_rollout.py",
                    "action": "update",
                    "timestamp": "2026-04-03T10:00:02Z",
                    "additions": 8,
                    "deletions": 2,
                    "sourceLogId": "log-4",
                }
            ],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_transcript_search_returns_ranked_matches(self) -> None:
        response = await self.search_service.search(
            self.context,
            self.ports,
            query="semantic search failing",
            feature_id="feature-a",
            conversation_family_id="family-1",
            limit=5,
        )

        self.assertEqual(response.total, 2)
        self.assertEqual(response.capability.searchMode, "canonical_lexical")
        self.assertEqual(response.items[0].sourceLogIds, ["log-1"])
        self.assertIn("semantic", response.items[0].matchedTerms)

    async def test_list_sessions_builds_rollups(self) -> None:
        response = await self.read_service.list_sessions(
            self.context,
            self.ports,
            feature_id="feature-a",
            conversation_family_id="family-1",
            limit=10,
        )

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.sessionId, "S-1")
        self.assertEqual(item.sentiment.label, "negative")
        self.assertEqual(item.churn.flaggedCount, 1)
        self.assertAlmostEqual(item.scopeDrift.score, 0.3333)

    async def test_detail_and_drilldown_return_fact_payloads(self) -> None:
        detail = await self.read_service.get_session_detail(self.context, self.ports, "S-1")
        assert detail is not None
        self.assertEqual(detail.summary.sessionId, "S-1")
        self.assertEqual(detail.sentimentFacts[0].sentimentLabel, "negative")
        self.assertEqual(detail.churnFacts[0].filePath, "backend/routers/analytics.py")
        self.assertEqual(detail.scopeDriftFacts[0].outOfScopePathCount, 1)

        drilldown = await self.read_service.drilldown(
            self.context,
            self.ports,
            concern="scope_drift",
            session_id="S-1",
        )
        assert drilldown is not None
        self.assertEqual(drilldown.total, 1)
        self.assertEqual(drilldown.items[0].label, "out_of_scope")

    async def test_historical_backfill_is_incremental_and_restart_safe(self) -> None:
        service = HistoricalSessionIntelligenceBackfillService()

        first = await service.backfill(
            self.db,
            project_id="project-1",
            limit=1,
            checkpoint_key="test-backfill",
        )
        self.assertEqual(first["sessionsProcessed"], 1)
        self.assertFalse(first["completed"])
        self.assertEqual(first["checkpoint"]["lastSessionId"], "S-1")

        second = await service.backfill(
            self.db,
            project_id="project-1",
            limit=1,
            checkpoint_key="test-backfill",
        )
        self.assertEqual(second["sessionsProcessed"], 1)
        self.assertTrue(second["completed"])
        self.assertEqual(second["checkpoint"]["lastSessionId"], "S-2")
        self.assertEqual(second["sessionsProcessedTotal"], 2)
        self.assertGreaterEqual(len(second["operatorGuidance"]), 2)

        s2_messages = await self.storage.session_messages().list_by_session("S-2")
        s2_sentiment = await self.storage.session_intelligence().list_session_sentiment_facts("S-2")
        self.assertEqual(len(s2_messages), 2)
        self.assertEqual(len(s2_sentiment), 1)

    def test_embedding_block_builder_creates_message_and_window_blocks(self) -> None:
        blocks = build_session_embedding_blocks(
            [
                {
                    "messageIndex": idx,
                    "messageId": f"msg-{idx}",
                    "role": "user" if idx % 2 == 0 else "assistant",
                    "messageType": "message",
                    "content": f"content-{idx}",
                    "sourceProvenance": "sync",
                }
                for idx in range(5)
            ]
        )
        self.assertEqual(sum(1 for block in blocks if block["block_kind"] == "message"), 5)
        self.assertEqual(sum(1 for block in blocks if block["block_kind"] == "window"), 1)


if __name__ == "__main__":
    unittest.main()
