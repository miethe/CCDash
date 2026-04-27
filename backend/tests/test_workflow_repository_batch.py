"""Tests for fetch_workflow_details — the batch-fetch helper in workflow_registry.

Covers BE-302: adds a single-load-pass method that eliminates the N+1 loop in
workflow_intelligence.py without touching the call site (BE-303) or removing
the original get_workflow_registry_detail (BE-304).
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations
from backend.services.workflow_registry import fetch_workflow_details, get_workflow_registry_detail


class FetchWorkflowDetailsBatchTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for fetch_workflow_details."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = get_session_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)
        self.project = types.SimpleNamespace(
            id="project-batch",
            skillMeat=types.SimpleNamespace(
                webBaseUrl="http://skillmeat-web.local:3000",
                projectId="project-batch",
                collectionId="default",
            ),
        )
        await self._seed()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed(self) -> None:
        source = await self.intelligence_repo.upsert_definition_source(
            {
                "project_id": "project-batch",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
            }
        )
        for external_id, display_name in [
            ("workflow-alpha", "Workflow Alpha"),
            ("workflow-beta", "Workflow Beta"),
            ("workflow-gamma", "Workflow Gamma"),
        ]:
            await self.intelligence_repo.upsert_external_definition(
                {
                    "project_id": "project-batch",
                    "source_id": source["id"],
                    "definition_type": "workflow",
                    "external_id": external_id,
                    "display_name": display_name,
                    "source_url": f"http://skillmeat.local/workflows/{external_id}",
                    "fetched_at": "2026-04-01T00:00:00+00:00",
                    "resolution_metadata": {
                        "isEffective": True,
                        "workflowScope": "project",
                        "aliases": [f"/{external_id}"],
                    },
                }
            )

    # ------------------------------------------------------------------
    # empty input → empty result, no DB call
    # ------------------------------------------------------------------

    async def test_empty_ids_returns_empty_list(self) -> None:
        result = await fetch_workflow_details(self.db, self.project, [])
        self.assertEqual(result, [])

    async def test_empty_ids_makes_no_db_call(self) -> None:
        """_load_registry_details must not be called when ids is empty."""
        with patch(
            "backend.services.workflow_registry._load_registry_details",
            new_callable=AsyncMock,
        ) as mock_load:
            result = await fetch_workflow_details(self.db, self.project, [])
        mock_load.assert_not_called()
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # single id → single result
    # ------------------------------------------------------------------

    async def test_single_id_returns_single_result(self) -> None:
        result = await fetch_workflow_details(
            self.db, self.project, ["workflow:workflow-alpha"]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "workflow:workflow-alpha")

    async def test_single_id_result_matches_get_detail(self) -> None:
        """Batch result for one ID must equal the output of get_workflow_registry_detail."""
        single = await get_workflow_registry_detail(
            self.db, self.project, registry_id="workflow:workflow-beta"
        )
        batch = await fetch_workflow_details(
            self.db, self.project, ["workflow:workflow-beta"]
        )
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["id"], single["id"])  # type: ignore[index]

    # ------------------------------------------------------------------
    # multiple ids → all results
    # ------------------------------------------------------------------

    async def test_multiple_ids_returns_all_results(self) -> None:
        ids = [
            "workflow:workflow-alpha",
            "workflow:workflow-beta",
            "workflow:workflow-gamma",
        ]
        result = await fetch_workflow_details(self.db, self.project, ids)
        self.assertEqual(len(result), 3)
        returned_ids = {item["id"] for item in result}
        self.assertEqual(returned_ids, set(ids))

    async def test_multiple_ids_preserves_input_order(self) -> None:
        ids = [
            "workflow:workflow-gamma",
            "workflow:workflow-alpha",
            "workflow:workflow-beta",
        ]
        result = await fetch_workflow_details(self.db, self.project, ids)
        self.assertEqual([item["id"] for item in result], ids)

    async def test_multiple_ids_issues_single_load(self) -> None:
        """_load_registry_details must be called exactly once regardless of how many IDs are requested."""
        ids = [
            "workflow:workflow-alpha",
            "workflow:workflow-beta",
            "workflow:workflow-gamma",
        ]
        # Wrap _load_registry_details so we can count calls while still
        # executing real logic.
        import backend.services.workflow_registry as _module

        original = _module._load_registry_details
        call_count = 0

        async def counting_wrapper(db, project):
            nonlocal call_count
            call_count += 1
            return await original(db, project)

        with patch.object(_module, "_load_registry_details", counting_wrapper):
            result = await fetch_workflow_details(self.db, self.project, ids)

        self.assertEqual(call_count, 1, "Expected exactly one _load_registry_details call for a batch of 3 IDs")
        self.assertEqual(len(result), 3)

    # ------------------------------------------------------------------
    # mix of existing + missing ids → only existing returned
    # ------------------------------------------------------------------

    async def test_missing_ids_omitted_from_result(self) -> None:
        ids = [
            "workflow:workflow-alpha",
            "workflow:does-not-exist",
            "workflow:workflow-gamma",
            "workflow:totally-made-up",
        ]
        result = await fetch_workflow_details(self.db, self.project, ids)
        # Only the two real ones come back
        self.assertEqual(len(result), 2)
        returned_ids = {item["id"] for item in result}
        self.assertIn("workflow:workflow-alpha", returned_ids)
        self.assertIn("workflow:workflow-gamma", returned_ids)
        self.assertNotIn("workflow:does-not-exist", returned_ids)
        self.assertNotIn("workflow:totally-made-up", returned_ids)

    async def test_missing_ids_length_check_detects_gap(self) -> None:
        """Callers can detect missing IDs by comparing len(result) with len(ids)."""
        ids = ["workflow:workflow-beta", "workflow:ghost-workflow"]
        result = await fetch_workflow_details(self.db, self.project, ids)
        # One of two IDs was missing — caller detects via length
        self.assertLess(len(result), len(ids))
        self.assertEqual(len(result), 1)

    async def test_all_missing_ids_returns_empty_list(self) -> None:
        result = await fetch_workflow_details(
            self.db,
            self.project,
            ["workflow:ghost-1", "workflow:ghost-2"],
        )
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # original get_workflow_registry_detail remains intact (BE-304)
    # ------------------------------------------------------------------

    async def test_original_single_lookup_still_works(self) -> None:
        detail = await get_workflow_registry_detail(
            self.db, self.project, registry_id="workflow:workflow-alpha"
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["id"], "workflow:workflow-alpha")

    async def test_original_single_lookup_returns_none_for_missing(self) -> None:
        detail = await get_workflow_registry_detail(
            self.db, self.project, registry_id="workflow:nonexistent"
        )
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
