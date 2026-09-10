"""ADR-007 direct-count assertion for the task write path touched by A1.

progress.py now emits `dependencies`/`assignees` list fields on ProjectTask
(previously truncated into `tags` / collapsed to a single `owner`). This test
asserts the SqliteTaskRepository write path lands exactly N rows for N tasks
and that upsert stays idempotent, per ADR-007 §4.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import aiosqlite

from backend.db.repositories.tasks import SqliteTaskRepository
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.progress import parse_progress_file


def _task_row(task_id: str, **overrides: object) -> dict:
    row = {
        "id": task_id,
        "title": f"Task {task_id}",
        "description": "",
        "status": "backlog",
        "owner": "alice",
        "assignees": ["alice", "bob"],
        "dependencies": ["dep-1", "dep-2"],
        "lastAgent": "Claude 3 Opus",
        "cost": 0.0,
        "sourceFile": "progress/feature-a/phase-1-progress.md",
    }
    row.update(overrides)
    return row


class SqliteTaskDirectCountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteTaskRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _direct_count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM tasks")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_direct_count_matches_writes(self) -> None:
        n = 5
        for i in range(n):
            await self.repo.upsert(_task_row(f"task-{i}"), project_id="project-1")

        self.assertEqual(await self._direct_count(), n)

    async def test_upsert_idempotency_keeps_count_stable_and_updates_row(self) -> None:
        await self.repo.upsert(_task_row("task-x", status="backlog"), project_id="project-1")
        self.assertEqual(await self._direct_count(), 1)

        await self.repo.upsert(_task_row("task-x", status="done"), project_id="project-1")

        self.assertEqual(await self._direct_count(), 1, "re-upsert of the same id must not duplicate")
        stored = await self.repo.get_by_id("task-x")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["status"], "done")

    async def test_dependencies_and_assignees_round_trip_through_data_json(self) -> None:
        """Parser output retains the full lists through the task repository write."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            progress_dir = root / ".claude" / "progress" / "feature-a"
            progress_dir.mkdir(parents=True)
            path = progress_dir / "phase-1-progress.md"
            path.write_text(
                """---
tasks:
  - id: task-fanout
    name: Shared task
    assigned_to: [alice, bob]
    dependencies: [dep-1, dep-2, dep-3, dep-4]
---
""",
                encoding="utf-8",
            )
            tasks = parse_progress_file(path, root / ".claude" / "progress")

        self.assertEqual(len(tasks), 1)
        await self.repo.upsert(tasks[0].model_dump(), project_id="project-1")
        self.assertEqual(await self._direct_count(), 1)

        stored = await self.repo.get_by_id("task-fanout")
        self.assertIsNotNone(stored)
        assert stored is not None

        import json

        payload = json.loads(stored["data_json"])
        self.assertEqual(payload["dependencies"], ["dep-1", "dep-2", "dep-3", "dep-4"])
        self.assertEqual(payload["assignees"], ["alice", "bob"])


if __name__ == "__main__":
    unittest.main()
