"""Regression tests for FC-1: session child-writer project_id threading.

Validates:
  - AC-5: Cross-project isolation — project-A's writer does not delete project-B's rows
          that share the same session_id (upsert_artifacts + replace_session_sentiment_facts)
  - AC-6: FK compliance under foreign_keys=ON — upsert_artifacts,
          replace_session_sentiment_facts, replace_session_code_churn_facts,
          replace_session_scope_drift_facts all write project_id; no NULL child rows
  - Regression: upsert_logs and upsert_file_updates DELETE scoping
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db import sqlite_migrations
from backend.db.repositories.session_intelligence import SqliteSessionIntelligenceRepository
from backend.db.repositories.sessions import SqliteSessionRepository


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await sqlite_migrations.run_migrations(db)
    # Match runtime: composite FK enforcement is always on.
    await db.execute("PRAGMA foreign_keys=ON")
    await db.commit()
    return db


def _session(session_id: str, project_id: str) -> dict:
    return {
        "id": session_id,
        "taskId": "feature-x",
        "status": "completed",
        "model": "claude-opus-4",
        "startedAt": "2026-05-01T10:00:00Z",
        "endedAt": "2026-05-01T10:05:00Z",
        "updatedAt": "2026-05-01T10:05:00Z",
    }


def _artifact(artifact_id: str) -> dict:
    return {
        "id": artifact_id,
        "title": f"Artifact {artifact_id}",
        "type": "document",
        "description": "test",
        "source": "test",
    }


def _sentiment_fact(label: str = "neutral") -> dict:
    return {
        "feature_id": "feature-x",
        "root_session_id": "S-1",
        "thread_session_id": "S-1",
        "source_message_id": "msg-1",
        "source_log_id": "log-1",
        "message_index": 1,
        "sentiment_label": label,
        "sentiment_score": 0.5,
        "confidence": 0.9,
        "heuristic_version": "v1",
        "evidence_json": {},
    }


def _churn_fact() -> dict:
    return {
        "feature_id": "feature-x",
        "root_session_id": "S-1",
        "thread_session_id": "S-1",
        "file_path": "backend/foo.py",
        "first_source_log_id": "log-1",
        "last_source_log_id": "log-2",
        "first_message_index": 1,
        "last_message_index": 2,
        "touch_count": 2,
        "distinct_edit_turn_count": 1,
        "repeat_touch_count": 1,
        "rewrite_pass_count": 0,
        "additions_total": 5,
        "deletions_total": 3,
        "net_diff_total": 2,
        "churn_score": 0.4,
        "progress_score": 0.6,
        "low_progress_loop": False,
        "confidence": 0.8,
        "heuristic_version": "v1",
        "evidence_json": {},
    }


def _scope_drift_fact() -> dict:
    return {
        "feature_id": "feature-x",
        "root_session_id": "S-1",
        "thread_session_id": "S-1",
        "planned_path_count": 2,
        "actual_path_count": 2,
        "matched_path_count": 2,
        "out_of_scope_path_count": 0,
        "drift_ratio": 0.0,
        "adherence_score": 1.0,
        "confidence": 0.95,
        "heuristic_version": "v1",
        "evidence_json": {},
    }


class CrossProjectIsolationTests(unittest.IsolatedAsyncioTestCase):
    """AC-5: project-A's writer must never delete project-B's rows sharing session_id."""

    async def asyncSetUp(self) -> None:
        self.db = await _make_db()
        self.addAsyncCleanup(self.db.close)
        self.sessions = SqliteSessionRepository(self.db)
        self.intel = SqliteSessionIntelligenceRepository(self.db)

        # Insert the SAME session_id "S-1" under two different projects.
        # This replicates the scenario that breaks without project-scoped DELETE.
        await self.sessions.upsert(_session("S-1", "project-A"), "project-A")
        await self.sessions.upsert(_session("S-1", "project-B"), "project-B")

    async def test_upsert_artifacts_does_not_delete_other_project_rows(self) -> None:
        """Writing artifacts for project-A must not delete project-B's artifact rows."""
        # Seed project-B artifact rows first.
        await self.sessions.upsert_artifacts(
            "S-1",
            [_artifact("b-art-1"), _artifact("b-art-2")],
            "project-B",
        )

        # Now write project-A's artifacts (triggering the scoped DELETE + INSERT).
        await self.sessions.upsert_artifacts(
            "S-1",
            [_artifact("a-art-1")],
            "project-A",
        )

        # project-B's rows must still exist.
        async with self.db.execute(
            "SELECT id FROM session_artifacts WHERE session_id = 'S-1' AND project_id = 'project-B'",
        ) as cur:
            b_rows = await cur.fetchall()
        self.assertEqual(len(b_rows), 2, "project-B's artifacts must not be deleted by project-A's writer")

        # project-A's rows are correctly replaced.
        async with self.db.execute(
            "SELECT id FROM session_artifacts WHERE session_id = 'S-1' AND project_id = 'project-A'",
        ) as cur:
            a_rows = await cur.fetchall()
        self.assertEqual(len(a_rows), 1, "project-A's artifacts should have exactly 1 row")
        self.assertEqual(a_rows[0]["id"], "a-art-1")

    async def test_replace_sentiment_facts_does_not_delete_other_project_rows(self) -> None:
        """Writing sentiment facts for project-A must not delete project-B's rows."""
        # Seed project-B sentiment row.
        await self.intel.replace_session_sentiment_facts(
            "S-1",
            [_sentiment_fact("positive")],
            "project-B",
        )

        # Write project-A's sentiment facts.
        await self.intel.replace_session_sentiment_facts(
            "S-1",
            [_sentiment_fact("negative")],
            "project-A",
        )

        async with self.db.execute(
            "SELECT sentiment_label FROM session_sentiment_facts WHERE session_id = 'S-1' AND project_id = 'project-B'",
        ) as cur:
            b_rows = await cur.fetchall()
        self.assertEqual(len(b_rows), 1, "project-B's sentiment facts must not be deleted by project-A's writer")
        self.assertEqual(b_rows[0]["sentiment_label"], "positive")

        async with self.db.execute(
            "SELECT sentiment_label FROM session_sentiment_facts WHERE session_id = 'S-1' AND project_id = 'project-A'",
        ) as cur:
            a_rows = await cur.fetchall()
        self.assertEqual(len(a_rows), 1)
        self.assertEqual(a_rows[0]["sentiment_label"], "negative")

    async def test_replace_code_churn_facts_does_not_delete_other_project_rows(self) -> None:
        """Writing code-churn facts for project-A must not delete project-B's rows."""
        await self.intel.replace_session_code_churn_facts("S-1", [_churn_fact()], "project-B")
        await self.intel.replace_session_code_churn_facts("S-1", [_churn_fact()], "project-A")

        async with self.db.execute(
            "SELECT project_id FROM session_code_churn_facts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        projects = {r["project_id"] for r in rows}
        self.assertIn("project-A", projects)
        self.assertIn("project-B", projects)

    async def test_replace_scope_drift_facts_does_not_delete_other_project_rows(self) -> None:
        """Writing scope-drift facts for project-A must not delete project-B's rows."""
        await self.intel.replace_session_scope_drift_facts("S-1", [_scope_drift_fact()], "project-B")
        await self.intel.replace_session_scope_drift_facts("S-1", [_scope_drift_fact()], "project-A")

        async with self.db.execute(
            "SELECT project_id FROM session_scope_drift_facts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        projects = {r["project_id"] for r in rows}
        self.assertIn("project-A", projects)
        self.assertIn("project-B", projects)


class FKComplianceUnderForeignKeysOnTests(unittest.IsolatedAsyncioTestCase):
    """AC-6: FK must not be violated; no NULL/'' child rows after the fix."""

    async def asyncSetUp(self) -> None:
        self.db = await _make_db()
        self.addAsyncCleanup(self.db.close)
        self.sessions = SqliteSessionRepository(self.db)
        self.intel = SqliteSessionIntelligenceRepository(self.db)
        # Upsert one parent session with a real project_id.
        await self.sessions.upsert(_session("S-1", "project-1"), "project-1")

    async def test_full_child_write_cycle_no_fk_violation(self) -> None:
        """All four child writers succeed without FK violation under foreign_keys=ON."""
        # If any of these raise an IntegrityError the test fails.
        await self.sessions.upsert_artifacts("S-1", [_artifact("art-1")], "project-1")
        await self.intel.replace_session_sentiment_facts("S-1", [_sentiment_fact()], "project-1")
        await self.intel.replace_session_code_churn_facts("S-1", [_churn_fact()], "project-1")
        await self.intel.replace_session_scope_drift_facts("S-1", [_scope_drift_fact()], "project-1")

    async def test_no_null_project_id_in_artifacts(self) -> None:
        await self.sessions.upsert_artifacts("S-1", [_artifact("art-1"), _artifact("art-2")], "project-1")
        async with self.db.execute(
            "SELECT id, project_id FROM session_artifacts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["project_id"], "project-1", f"artifact {row['id']} has NULL/empty project_id")

    async def test_no_null_project_id_in_sentiment_facts(self) -> None:
        await self.intel.replace_session_sentiment_facts("S-1", [_sentiment_fact()], "project-1")
        async with self.db.execute(
            "SELECT project_id FROM session_sentiment_facts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["project_id"], "project-1")

    async def test_no_null_project_id_in_code_churn_facts(self) -> None:
        await self.intel.replace_session_code_churn_facts("S-1", [_churn_fact()], "project-1")
        async with self.db.execute(
            "SELECT project_id FROM session_code_churn_facts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["project_id"], "project-1")

    async def test_no_null_project_id_in_scope_drift_facts(self) -> None:
        await self.intel.replace_session_scope_drift_facts("S-1", [_scope_drift_fact()], "project-1")
        async with self.db.execute(
            "SELECT project_id FROM session_scope_drift_facts WHERE session_id = 'S-1'",
        ) as cur:
            rows = await cur.fetchall()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["project_id"], "project-1")


class UpsertLogsAndFileUpdatesDeleteScopingTests(unittest.IsolatedAsyncioTestCase):
    """Regression tests for upsert_logs and upsert_file_updates DELETE scoping (AC-3)."""

    async def asyncSetUp(self) -> None:
        self.db = await _make_db()
        self.addAsyncCleanup(self.db.close)
        self.sessions = SqliteSessionRepository(self.db)
        await self.sessions.upsert(_session("S-1", "project-A"), "project-A")
        await self.sessions.upsert(_session("S-1", "project-B"), "project-B")

    async def test_upsert_logs_scoped_delete(self) -> None:
        """project-A's upsert_logs must not delete project-B's session_logs rows."""
        log_b = {
            "id": "b-log-1",
            "timestamp": "2026-05-01T10:00:00Z",
            "speaker": "assistant",
            "type": "text",
            "content": "project-B content",
        }
        log_a = {
            "id": "a-log-1",
            "timestamp": "2026-05-01T10:00:00Z",
            "speaker": "user",
            "type": "text",
            "content": "project-A content",
        }
        await self.sessions.upsert_logs("S-1", [log_b], "project-B")
        await self.sessions.upsert_logs("S-1", [log_a], "project-A")

        async with self.db.execute(
            "SELECT source_log_id FROM session_logs WHERE session_id = 'S-1' AND project_id = 'project-B'",
        ) as cur:
            b_rows = await cur.fetchall()
        self.assertEqual(len(b_rows), 1, "project-B's logs must not be deleted by project-A's writer")

    async def test_upsert_file_updates_scoped_delete(self) -> None:
        """project-A's upsert_file_updates must not delete project-B's rows."""
        update_b = {
            "filePath": "src/b.py",
            "action": "edit",
            "fileType": "Python",
            "timestamp": "2026-05-01T10:00:00Z",
            "additions": 1,
            "deletions": 0,
        }
        update_a = {
            "filePath": "src/a.py",
            "action": "edit",
            "fileType": "Python",
            "timestamp": "2026-05-01T10:00:00Z",
            "additions": 2,
            "deletions": 1,
        }
        await self.sessions.upsert_file_updates("S-1", [update_b], "project-B")
        await self.sessions.upsert_file_updates("S-1", [update_a], "project-A")

        async with self.db.execute(
            "SELECT file_path FROM session_file_updates WHERE session_id = 'S-1' AND project_id = 'project-B'",
        ) as cur:
            b_rows = await cur.fetchall()
        self.assertEqual(len(b_rows), 1, "project-B's file_updates must not be deleted by project-A's writer")
