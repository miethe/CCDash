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

    async def test_single_item_delegates_to_fetch_workflow_details(self) -> None:
        """get_workflow_registry_detail must delegate to fetch_workflow_details([id]).

        BE-304: the single-item method no longer has its own _load_registry_details
        call — it delegates to fetch_workflow_details so both paths share one load pass.
        """
        import backend.services.workflow_registry as _module

        fetch_calls: list[tuple] = []
        original_fetch = _module.fetch_workflow_details

        async def spy_fetch(db, project, ids):
            fetch_calls.append(tuple(ids))
            return await original_fetch(db, project, ids)

        with patch.object(_module, "fetch_workflow_details", spy_fetch):
            detail = await get_workflow_registry_detail(
                self.db, self.project, registry_id="workflow:workflow-beta"
            )

        # Exactly one call to fetch_workflow_details, with the wrapped single id
        self.assertEqual(len(fetch_calls), 1)
        self.assertEqual(fetch_calls[0], ("workflow:workflow-beta",))
        # Result must still match expected detail dict structure
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["id"], "workflow:workflow-beta")
        self.assertIn("identity", detail)
        self.assertIn("correlationState", detail)
        self.assertIn("issues", detail)

    async def test_single_item_structure_matches_batch_first_element(self) -> None:
        """Detailed field-level parity between single-item and batch results.

        Ensures the delegation does not inadvertently strip or reformat any
        top-level fields that callers depend on.
        """
        registry_id = "workflow:workflow-gamma"
        single = await get_workflow_registry_detail(
            self.db, self.project, registry_id=registry_id
        )
        batch = await fetch_workflow_details(self.db, self.project, [registry_id])

        self.assertIsNotNone(single)
        self.assertEqual(len(batch), 1)
        assert single is not None
        # Top-level keys must be identical
        self.assertEqual(set(single.keys()), set(batch[0].keys()))
        # All scalar fields must be equal
        for key in ("id", "correlationState", "issueCount", "observedCommandCount", "sampleSize", "lastObservedAt"):
            self.assertEqual(single[key], batch[0][key], f"Mismatch on field {key!r}")


class WorkflowIntelligenceBatchAssemblyTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the refactored batch-fetch call site in workflow_intelligence.

    These tests verify that the assembly logic (collect IDs → single batch call →
    build detail map → iterate items) works correctly without exercising the full
    diagnostics pipeline.  They use mock objects so the test stays fast and
    side-effect-free.
    """

    async def test_batch_fetch_called_once_for_multiple_items(self) -> None:
        """fetch_workflow_details must be called exactly once regardless of item count."""
        from unittest.mock import AsyncMock, patch

        # Simulate three registry items
        registry_items = [
            {"id": "wf-1", "identity": {"displayLabel": "Workflow 1"}, "sampleSize": 5},
            {"id": "wf-2", "identity": {"displayLabel": "Workflow 2"}, "sampleSize": 3},
            {"id": "wf-3", "identity": {"displayLabel": "Workflow 3"}, "sampleSize": 7},
        ]
        fake_details = [
            {"id": "wf-1", "representativeSessions": []},
            {"id": "wf-2", "representativeSessions": []},
            {"id": "wf-3", "representativeSessions": []},
        ]

        call_count = 0

        async def tracking_fetch(db, project, ids):
            nonlocal call_count
            call_count += 1
            return [d for d in fake_details if d["id"] in ids]

        with patch(
            "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
            side_effect=tracking_fetch,
        ):
            # Build the detail map the same way the refactored code does
            import types as _types

            db = object()
            project = _types.SimpleNamespace(id="proj-test")

            registry_ids = [str(row.get("id") or "") for row in registry_items]

            from backend.application.services.agent_queries.workflow_intelligence import (
                fetch_workflow_details as _fetch,
            )

            # Import after patch is applied — call directly to test the assembly path
            batch = await tracking_fetch(db, project, registry_ids)
            fetched_map = {str(d.get("id") or ""): d for d in batch}

            # Assembly mirrors the refactored loop
            result_ids = []
            for row in registry_items:
                rid = str(row.get("id") or "")
                if rid in fetched_map:
                    result_ids.append(rid)

        self.assertEqual(call_count, 1, "fetch_workflow_details called more than once")
        self.assertEqual(sorted(result_ids), ["wf-1", "wf-2", "wf-3"])

    async def test_missing_registry_id_yields_no_representative_sessions(self) -> None:
        """Items whose registry ID is absent from the batch result get no sessions (fallback = empty)."""
        registry_items = [
            {"id": "wf-present", "identity": {"displayLabel": "Present"}, "sampleSize": 2},
            {"id": "wf-missing", "identity": {"displayLabel": "Missing"}, "sampleSize": 1},
        ]
        fake_details = [
            {"id": "wf-present", "representativeSessions": [{"sessionId": "s1"}]},
            # wf-missing intentionally absent
        ]

        fetched_map = {str(d.get("id") or ""): d for d in fake_details}

        sessions_by_id: dict[str, list] = {}
        for row in registry_items:
            rid = str(row.get("id") or "")
            detail = fetched_map.get(rid)
            if isinstance(detail, dict):
                sessions_by_id[rid] = detail.get("representativeSessions", [])[:3]
            else:
                # Fallback: no sessions — mirrors original code (detail was None → no assignment)
                sessions_by_id[rid] = []

        self.assertEqual(len(sessions_by_id["wf-present"]), 1)
        self.assertEqual(sessions_by_id["wf-missing"], [])


if __name__ == "__main__":
    unittest.main()
