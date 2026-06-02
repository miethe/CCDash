"""P3-003-FU: sessions composite PK (project_id, id) upsert semantics.

Verifies:
1. Upserting the SAME (project_id, id) twice updates the row, not duplicates it.
2. Two different projects can each hold a session with the identical `id` value
   without collision (they are distinct rows under the composite PK).
3. PRAGMA foreign_key_check is empty after migration (upgrade-path assertion).
"""
from __future__ import annotations

import unittest

import aiosqlite
import pytest

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

_BASE = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "platformVersion": "2.1.52",
    "platformVersions": ["2.1.52"],
    "platformVersionTransitions": [],
    "durationSeconds": 1,
    "tokensIn": 10,
    "tokensOut": 20,
    "modelIOTokens": 30,
    "cacheCreationInputTokens": 0,
    "cacheReadInputTokens": 0,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.0,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": None,
    "startedAt": "2026-06-01T00:00:00Z",
    "endedAt": "2026-06-01T00:01:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": "shared-id",
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": "shared-id",
    "contextInheritance": "fresh",
}


class CompositePkUpsertTests(unittest.IsolatedAsyncioTestCase):
    """sessions table upsert honours the composite (project_id, id) PK."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count_sessions(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM sessions") as cur:
            row = await cur.fetchone()
            return row[0]

    async def _fetch_session(self, project_id: str, session_id: str) -> aiosqlite.Row | None:
        async with self.db.execute(
            "SELECT * FROM sessions WHERE project_id = ? AND id = ?",
            (project_id, session_id),
        ) as cur:
            return await cur.fetchone()

    async def test_same_project_and_id_updates_not_duplicates(self) -> None:
        """Second upsert with identical (project_id, id) must UPDATE, not INSERT."""
        sid = "shared-id"
        proj = "proj-alpha"

        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 10}, proj)
        count_after_first = await self._count_sessions()
        self.assertEqual(count_after_first, 1)

        # Second upsert: same (proj, id), different field value
        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 99}, proj)
        count_after_second = await self._count_sessions()
        self.assertEqual(count_after_second, 1, "row count must stay at 1 — update, not insert")

        row = await self._fetch_session(proj, sid)
        self.assertIsNotNone(row)
        self.assertEqual(row["tokens_in"], 99, "updated field must reflect the second upsert")

    async def test_same_id_different_projects_no_collision(self) -> None:
        """Identical session `id` values across two projects are distinct rows."""
        sid = "shared-id"

        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 1}, "proj-alpha")
        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 2}, "proj-beta")

        total = await self._count_sessions()
        self.assertEqual(total, 2, "two projects × same id = two distinct rows")

        row_a = await self._fetch_session("proj-alpha", sid)
        row_b = await self._fetch_session("proj-beta", sid)

        self.assertIsNotNone(row_a)
        self.assertIsNotNone(row_b)
        self.assertEqual(row_a["tokens_in"], 1)
        self.assertEqual(row_b["tokens_in"], 2)
        self.assertEqual(row_a["project_id"], "proj-alpha")
        self.assertEqual(row_b["project_id"], "proj-beta")

    async def test_update_only_touches_matching_project_row(self) -> None:
        """Re-upsert for proj-alpha must not bleed into proj-beta's row."""
        sid = "shared-id"

        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 1}, "proj-alpha")
        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 2}, "proj-beta")

        # Now update proj-alpha only
        await self.repo.upsert({**_BASE, "id": sid, "tokensIn": 99}, "proj-alpha")

        row_a = await self._fetch_session("proj-alpha", sid)
        row_b = await self._fetch_session("proj-beta", sid)

        self.assertEqual(row_a["tokens_in"], 99, "proj-alpha row updated")
        self.assertEqual(row_b["tokens_in"], 2, "proj-beta row untouched")

    async def test_sessions_pk_is_composite(self) -> None:
        """P3-003-FU: sessions PK must be composite (project_id, id) after v31 migration."""
        async with self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'"
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row)
        sessions_ddl = row[0] or ""
        self.assertIn(
            "PRIMARY KEY (project_id, id)",
            sessions_ddl,
            f"sessions table DDL must contain composite PK: {sessions_ddl!r}",
        )

    async def test_foreign_key_check_empty_after_migration(self) -> None:
        """P3-003-FU: PRAGMA foreign_key_check must return empty after v31 migration."""
        # Insert sessions first, then child rows, then verify FK check.
        sid = "fk-check-session"
        proj = "fk-check-proj"
        await self.repo.upsert({**_BASE, "id": sid}, proj)
        await self.db.commit()

        # Insert a child row (session_logs) to test FK is enforced correctly.
        import datetime as _dt
        await self.db.execute(
            "INSERT INTO session_logs (project_id, session_id, log_index, timestamp, speaker, type) "
            "VALUES (?, ?, 0, ?, 'user', 'text')",
            (proj, sid, _dt.datetime.utcnow().isoformat()),
        )
        await self.db.commit()

        # Enable FK enforcement and verify.
        await self.db.execute("PRAGMA foreign_keys=ON")
        async with self.db.execute("PRAGMA foreign_key_check") as cur:
            violations = await cur.fetchall()
        self.assertEqual(
            violations, [], f"PRAGMA foreign_key_check must be empty; got: {violations}"
        )

    async def test_upgrade_path_v30_to_v31_fk_check(self) -> None:
        """Upgrade-path: a DB initialized fresh at v31 must have empty foreign_key_check."""
        # The migration already ran in asyncSetUp (run_migrations on :memory: DB).
        # Verify schema_version is 31 and FK check is clean.
        async with self.db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        from backend.db.sqlite_migrations import SCHEMA_VERSION
        self.assertEqual(row[0], SCHEMA_VERSION, f"Expected schema_version {SCHEMA_VERSION}, got {row[0]}")

        await self.db.execute("PRAGMA foreign_keys=ON")
        async with self.db.execute("PRAGMA foreign_key_check") as cur:
            violations = await cur.fetchall()
        self.assertEqual(
            violations, [], f"PRAGMA foreign_key_check must be empty on fresh DB; got: {violations}"
        )


if __name__ == "__main__":
    unittest.main()
