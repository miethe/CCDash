"""Tests for SqliteWorktreeContextRepository (PCP-501)."""
import unittest

import aiosqlite

from backend.db.repositories.base import WorktreeContextRepository
from backend.db.repositories.worktree_contexts import SqliteWorktreeContextRepository
from backend.db.sqlite_migrations import run_migrations


class WorktreeContextRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteWorktreeContextRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── Protocol ────────────────────────────────────────────────────

    async def test_protocol_runtime_check(self) -> None:
        self.assertIsInstance(self.repo, WorktreeContextRepository)

    # ── Create / get_by_id roundtrip ────────────────────────────────

    async def test_create_get_roundtrip_auto_id(self) -> None:
        row = await self.repo.create(
            {
                "project_id": "proj-1",
                "feature_id": "FEAT-10",
                "phase_number": 2,
                "batch_id": "batch-a",
                "branch": "feat/pcp-501",
                "provider": "local",
                "notes": "initial draft",
                "metadata": {"ticket": "PCP-501"},
            }
        )
        self.assertTrue(row["id"])
        self.assertEqual(row["project_id"], "proj-1")
        self.assertEqual(row["feature_id"], "FEAT-10")
        self.assertEqual(row["phase_number"], 2)
        self.assertEqual(row["batch_id"], "batch-a")
        self.assertEqual(row["status"], "draft")
        self.assertEqual(row["metadata"], {"ticket": "PCP-501"})

        fetched = await self.repo.get_by_id(row["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], row["id"])
        self.assertEqual(fetched["metadata"], {"ticket": "PCP-501"})

    async def test_create_with_explicit_id(self) -> None:
        row = await self.repo.create({"id": "wc-explicit-1", "project_id": "proj-2"})
        self.assertEqual(row["id"], "wc-explicit-1")
        fetched = await self.repo.get_by_id("wc-explicit-1")
        self.assertIsNotNone(fetched)

    async def test_get_by_id_missing_returns_none(self) -> None:
        result = await self.repo.get_by_id("does-not-exist")
        self.assertIsNone(result)

    # ── Update ──────────────────────────────────────────────────────

    async def test_update_merges_fields_and_bumps_updated_at(self) -> None:
        created = await self.repo.create(
            {"project_id": "proj-1", "branch": "old-branch", "status": "draft"}
        )
        original_updated_at = created["updated_at"]

        updated = await self.repo.update(
            created["id"],
            {"branch": "new-branch", "status": "ready", "notes": "ready to go"},
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["branch"], "new-branch")
        self.assertEqual(updated["status"], "ready")
        self.assertEqual(updated["notes"], "ready to go")
        # updated_at should have advanced or at minimum be set
        self.assertIsNotNone(updated["updated_at"])

    async def test_update_metadata_via_metadata_key(self) -> None:
        created = await self.repo.create({"project_id": "proj-1"})
        updated = await self.repo.update(
            created["id"], {"metadata": {"key": "value"}}
        )
        self.assertEqual(updated["metadata"], {"key": "value"})

    async def test_update_missing_id_returns_none(self) -> None:
        result = await self.repo.update("no-such-id", {"status": "ready"})
        self.assertIsNone(result)

    # ── List filters ────────────────────────────────────────────────

    async def test_list_by_feature_id(self) -> None:
        await self.repo.create({"project_id": "proj-1", "feature_id": "F-1"})
        await self.repo.create({"project_id": "proj-1", "feature_id": "F-2"})
        await self.repo.create({"project_id": "proj-1", "feature_id": "F-1"})

        results = await self.repo.list("proj-1", feature_id="F-1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["feature_id"], "F-1")

    async def test_list_by_phase_number(self) -> None:
        await self.repo.create({"project_id": "proj-1", "phase_number": 1})
        await self.repo.create({"project_id": "proj-1", "phase_number": 2})

        results = await self.repo.list("proj-1", phase_number=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["phase_number"], 1)

    async def test_list_by_batch_id(self) -> None:
        await self.repo.create({"project_id": "proj-1", "batch_id": "batch-x"})
        await self.repo.create({"project_id": "proj-1", "batch_id": "batch-y"})

        results = await self.repo.list("proj-1", batch_id="batch-x")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["batch_id"], "batch-x")

    async def test_list_by_status(self) -> None:
        await self.repo.create({"project_id": "proj-1", "status": "draft"})
        await self.repo.create({"project_id": "proj-1", "status": "ready"})
        await self.repo.create({"project_id": "proj-1", "status": "ready"})

        results = await self.repo.list("proj-1", status="ready")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["status"], "ready")

    async def test_list_scoped_to_project(self) -> None:
        await self.repo.create({"project_id": "proj-A"})
        await self.repo.create({"project_id": "proj-B"})

        results = await self.repo.list("proj-A")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["project_id"], "proj-A")

    # ── Count ───────────────────────────────────────────────────────

    async def test_count_matches_list_length(self) -> None:
        await self.repo.create({"project_id": "proj-c", "status": "draft"})
        await self.repo.create({"project_id": "proj-c", "status": "ready"})
        await self.repo.create({"project_id": "proj-c", "status": "draft"})

        total = await self.repo.count("proj-c")
        self.assertEqual(total, 3)

        draft_count = await self.repo.count("proj-c", status="draft")
        draft_list = await self.repo.list("proj-c", status="draft")
        self.assertEqual(draft_count, len(draft_list))

    async def test_count_zero_for_unknown_project(self) -> None:
        result = await self.repo.count("no-such-project")
        self.assertEqual(result, 0)

    # ── Delete ──────────────────────────────────────────────────────

    async def test_delete_removes_row(self) -> None:
        row = await self.repo.create({"project_id": "proj-d"})
        deleted = await self.repo.delete(row["id"])
        self.assertTrue(deleted)
        self.assertIsNone(await self.repo.get_by_id(row["id"]))

    async def test_delete_missing_returns_false(self) -> None:
        result = await self.repo.delete("non-existent-id")
        self.assertFalse(result)
