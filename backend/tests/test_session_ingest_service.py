from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from backend.ingestion.jsonl_adapter import jsonl_session_to_envelope
from backend.ingestion.models import IngestSource, MergePolicy
from backend.ingestion.session_ingest_service import SessionIngestService


class _SessionRepo:
    def __init__(self) -> None:
        self.sessions: list[tuple[dict, str]] = []
        self.relationships: list[tuple[str, str, list[dict]]] = []

    async def upsert(self, session_data: dict, project_id: str) -> None:
        self.sessions.append((dict(session_data), project_id))

    async def get_logs(self, session_id: str) -> list[dict]:
        return []

    async def upsert_logs(self, session_id: str, logs: list[dict]) -> None:
        return None

    async def upsert_tool_usage(self, session_id: str, tools: list[dict]) -> None:
        return None

    async def upsert_file_updates(self, session_id: str, updates: list[dict]) -> None:
        return None

    async def upsert_artifacts(self, session_id: str, artifacts: list[dict]) -> None:
        return None

    async def update_observability_fields(self, session_id: str, observability_fields: dict) -> None:
        return None

    async def upsert_relationships(self, project_id: str, source_file: str, relationships: list[dict]) -> None:
        self.relationships.append((project_id, source_file, list(relationships)))


class _SessionMessageRepo:
    async def list_by_session(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict]:
        return []

    async def replace_session_messages(self, session_id: str, messages: list[dict]) -> None:
        return None


class SessionIngestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_persist_complete_jsonl_envelope_returns_session_and_relationship_counts(self) -> None:
        session_repo = _SessionRepo()
        message_repo = _SessionMessageRepo()
        service = SessionIngestService(
            session_repo=session_repo,
            session_message_repo=message_repo,
            project_session_messages=lambda session, logs: [{"session_id": session["id"], "content": "hello"}],
            apply_usage_fields=lambda session: {},
            should_write_legacy_session_logs=lambda rows: True,
            derive_session_observability_fields=AsyncMock(return_value={}),
            replace_session_usage_attribution=AsyncMock(return_value={"events": 0, "attributions": 0}),
            replace_session_telemetry_events=AsyncMock(return_value=0),
            replace_session_commit_correlations=AsyncMock(return_value=0),
            replace_session_intelligence_facts=AsyncMock(return_value=0),
            maybe_enqueue_telemetry_export=AsyncMock(return_value=None),
            publish_transcript_appends=AsyncMock(return_value=False),
            publish_session_snapshot=AsyncMock(return_value=None),
        )
        envelope = jsonl_session_to_envelope(
            {
                "id": "S-root",
                "platformType": "Claude Code",
                "logs": [{"id": "log-1", "content": "hello"}],
                "toolsUsed": [],
                "updatedFiles": [],
                "linkedArtifacts": [],
                "sessionRelationships": [
                    {
                        "parentSessionId": "S-root",
                        "childSessionId": "S-child",
                        "relationshipType": "fork",
                    }
                ],
                "derivedSessions": [
                    {
                        "id": "S-child",
                        "logs": [],
                        "toolsUsed": [],
                        "updatedFiles": [],
                        "linkedArtifacts": [],
                    }
                ],
            },
            source_identity="source/session.jsonl",
            source_uri="/tmp/session.jsonl",
        )

        result = await service.persist_envelope("project-1", envelope, observed_source_file="/tmp/session.jsonl")

        self.assertEqual(result.source, IngestSource.JSONL)
        self.assertEqual(result.merge_policy, MergePolicy.UPSERT_COMPLETE)
        self.assertEqual(result.session_ids, ["S-root", "S-child"])
        self.assertEqual(result.message_count, 2)
        self.assertEqual(result.log_count, 1)
        self.assertEqual(result.relationship_count, 1)
        self.assertEqual(session_repo.sessions[0][0]["sourceFile"], "source/session.jsonl")
        self.assertEqual(session_repo.sessions[0][0]["sessionForensics"]["observedSourceFile"], "/tmp/session.jsonl")
        self.assertEqual(session_repo.relationships[0][1], "source/session.jsonl")
        self.assertTrue(session_repo.relationships[0][2][0]["id"].startswith("REL-"))


if __name__ == "__main__":
    unittest.main()
