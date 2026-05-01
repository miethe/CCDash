import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations


class SessionRepositoryFilterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

        base = {
            "taskId": "",
            "status": "completed",
            "model": "claude-sonnet",
            "platformType": "Claude Code",
            "platformVersion": "2.1.52",
            "platformVersions": ["2.1.52"],
            "platformVersionTransitions": [],
            "durationSeconds": 1,
            "tokensIn": 1,
            "tokensOut": 1,
            "modelIOTokens": 2,
            "cacheCreationInputTokens": 3,
            "cacheReadInputTokens": 5,
            "cacheInputTokens": 8,
            "observedTokens": 10,
            "toolReportedTokens": 13,
            "toolResultInputTokens": 21,
            "toolResultOutputTokens": 34,
            "toolResultCacheCreationInputTokens": 55,
            "toolResultCacheReadInputTokens": 89,
            "totalCost": 0.0,
            "qualityRating": 0,
            "frictionRating": 0,
            "gitCommitHash": None,
            "gitAuthor": None,
            "gitBranch": None,
            "startedAt": "2026-02-16T00:00:00Z",
            "endedAt": "2026-02-16T00:00:01Z",
            "sourceFile": "",
        }

        await self.repo.upsert(
            {
                **base,
                "id": "S-main",
                "sessionType": "session",
                "parentSessionId": None,
                "rootSessionId": "S-main",
                "agentId": None,
                "threadKind": "root",
                "conversationFamilyId": "S-main",
                "contextInheritance": "fresh",
            },
            "project-1",
        )
        await self.repo.upsert(
            {
                **base,
                "id": "S-agent-a1",
                "sessionType": "subagent",
                "parentSessionId": "S-main",
                "rootSessionId": "S-main",
                "agentId": "a1",
                "threadKind": "subagent",
                "conversationFamilyId": "S-main",
                "contextInheritance": "fresh",
            },
            "project-1",
        )
        await self.repo.upsert(
            {
                **base,
                "id": "S-fork-a",
                "sessionType": "fork",
                "parentSessionId": None,
                "rootSessionId": "S-fork-a",
                "agentId": None,
                "threadKind": "fork",
                "conversationFamilyId": "S-main",
                "contextInheritance": "full",
                "forkParentSessionId": "S-main",
                "forkPointLogId": "log-4",
                "forkPointEntryUuid": "entry-fork-a",
                "forkPointParentEntryUuid": "entry-parent",
                "forkDepth": 1,
                "forkCount": 0,
            },
            "project-1",
        )
        await self.repo.upsert(
            {
                **base,
                "id": "S-opus-45",
                "model": "claude-opus-4-5-20251101",
                "platformVersions": ["2.1.51", "2.1.52"],
                "platformVersionTransitions": [
                    {
                        "timestamp": "2026-02-16T00:00:00Z",
                        "fromVersion": "2.1.51",
                        "toVersion": "2.1.52",
                    }
                ],
                "sessionType": "session",
                "parentSessionId": None,
                "rootSessionId": "S-opus-45",
                "agentId": None,
                "threadKind": "root",
                "conversationFamilyId": "S-opus-45",
                "contextInheritance": "fresh",
            },
            "project-1",
        )
        await self.repo.upsert(
            {
                **base,
                "id": "S-opus-41",
                "model": "claude-opus-4-1-20251001",
                "sessionType": "session",
                "parentSessionId": None,
                "rootSessionId": "S-opus-41",
                "agentId": None,
                "threadKind": "root",
                "conversationFamilyId": "S-opus-41",
                "contextInheritance": "fresh",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_default_excludes_subagents(self) -> None:
        rows = await self.repo.list_paginated(0, 50, "project-1", "started_at", "desc", {})
        row_ids = {r["id"] for r in rows}
        self.assertNotIn("S-agent-a1", row_ids)
        self.assertEqual(row_ids, {"S-main", "S-fork-a", "S-opus-45", "S-opus-41"})

    async def test_include_subagents_true_returns_both(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"include_subagents": True},
        )
        self.assertEqual({r["id"] for r in rows}, {"S-main", "S-agent-a1", "S-fork-a", "S-opus-45", "S-opus-41"})

    async def test_root_session_filter_with_subagents(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"include_subagents": True, "root_session_id": "S-main"},
        )
        self.assertEqual({r["id"] for r in rows}, {"S-main", "S-agent-a1"})

        count = await self.repo.count(
            "project-1",
            {"include_subagents": True, "root_session_id": "S-main"},
        )
        self.assertEqual(count, 2)

    async def test_thread_kind_filter_returns_only_forks(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"thread_kind": "fork", "include_subagents": True},
        )
        self.assertEqual([row["id"] for row in rows], ["S-fork-a"])

    async def test_conversation_family_filter_returns_family_members(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"conversation_family_id": "S-main", "include_subagents": True},
        )
        self.assertEqual({row["id"] for row in rows}, {"S-main", "S-agent-a1", "S-fork-a"})
        count = await self.repo.count(
            "project-1",
            {"conversation_family_id": "S-main", "include_subagents": True},
        )
        self.assertEqual(count, 3)

    async def test_model_identity_filters_match_provider_family_and_version(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {
                "model_provider": "Claude",
                "model_family": "Opus",
                "model_version": "Opus 4.5",
            },
        )
        self.assertEqual([r["id"] for r in rows], ["S-opus-45"])

    async def test_platform_filters_match_type_and_any_seen_version(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {
                "platform_type": "Claude Code",
                "platform_version": "2.1.51",
            },
        )
        self.assertEqual([r["id"] for r in rows], ["S-opus-45"])

    async def test_usage_contract_fields_round_trip_through_repository(self) -> None:
        row = await self.repo.get_by_id("S-main")
        assert row is not None

        self.assertEqual(row["model_io_tokens"], 2)
        self.assertEqual(row["cache_creation_input_tokens"], 3)
        self.assertEqual(row["cache_read_input_tokens"], 5)
        self.assertEqual(row["cache_input_tokens"], 8)
        self.assertEqual(row["observed_tokens"], 10)
        self.assertEqual(row["tool_reported_tokens"], 13)
        self.assertEqual(row["tool_result_input_tokens"], 21)
        self.assertEqual(row["tool_result_output_tokens"], 34)
        self.assertEqual(row["tool_result_cache_creation_input_tokens"], 55)
        self.assertEqual(row["tool_result_cache_read_input_tokens"], 89)

    async def test_session_detail_logs_are_limited_and_offsettable(self) -> None:
        await self.repo.upsert_logs(
            "S-main",
            [
                {
                    "id": f"log-{i}",
                    "timestamp": f"2026-02-16T00:00:{i % 60:02d}Z",
                    "speaker": "assistant",
                    "type": "message",
                    "content": f"message {i}",
                }
                for i in range(6000)
            ],
        )

        first_page = await self.repo.get_logs("S-main")
        second_page = await self.repo.get_logs("S-main", limit=10, offset=5000)

        self.assertEqual(len(first_page), 5000)
        self.assertEqual(first_page[0]["source_log_id"], "log-0")
        self.assertEqual(first_page[-1]["source_log_id"], "log-4999")
        self.assertEqual([row["source_log_id"] for row in second_page[:2]], ["log-5000", "log-5001"])

    async def test_relationship_upsert_and_lookup(self) -> None:
        await self.repo.delete_relationships_for_source("project-1", "sessions/main.jsonl")
        await self.repo.upsert_relationships(
            "project-1",
            "sessions/main.jsonl",
            [
                {
                    "id": "REL-fork-main-a",
                    "parentSessionId": "S-main",
                    "childSessionId": "S-fork-a",
                    "relationshipType": "fork",
                    "contextInheritance": "full",
                    "sourcePlatform": "claude_code",
                    "parentEntryUuid": "entry-parent",
                    "childEntryUuid": "entry-fork-a",
                    "sourceLogId": "log-4",
                    "metadata": {"label": "Fork A"},
                }
            ],
        )
        await self.repo.upsert_relationships(
            "project-1",
            "sessions/main.jsonl",
            [
                {
                    "id": "REL-fork-main-a",
                    "parentSessionId": "S-main",
                    "childSessionId": "S-fork-a",
                    "relationshipType": "fork",
                    "contextInheritance": "full",
                    "sourcePlatform": "claude_code",
                    "parentEntryUuid": "entry-parent",
                    "childEntryUuid": "entry-fork-a",
                    "sourceLogId": "log-4",
                    "metadata": {"label": "Fork A Updated"},
                }
            ],
        )

        rows = await self.repo.list_relationships("project-1", "S-main")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["relationship_type"], "fork")
        self.assertEqual(rows[0]["child_session_id"], "S-fork-a")
        self.assertIn("Fork A Updated", str(rows[0]["metadata_json"]))


if __name__ == "__main__":
    unittest.main()
