"""Tests for Phase 5 Wave 2 scaffolds: ARC council (P5-012), MeatyWiki (P5-013),
and live PR status / github_client import (P5-008).

Run with:
    PYTHONPATH=... /path/to/.venv/bin/python -m pytest backend/tests/test_p5_scaffolds.py \
        -p no:cacheprovider --no-header -q
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    # Use asyncio.run for a fresh loop each call — robust under Python 3.12 when a
    # prior test has consumed/closed the thread's event loop (get_event_loop raises).
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# P5-008 — github_client import + fetch_pr_status fail-soft
# ---------------------------------------------------------------------------


class TestGitHubClientImport(unittest.TestCase):
    def test_module_imports(self):
        """github_client must be importable without errors."""
        mod = importlib.import_module(
            "backend.services.repo_workspaces.github_client"
        )
        self.assertTrue(hasattr(mod, "fetch_pr_status"))
        self.assertTrue(hasattr(mod, "GitHubClient"))
        self.assertTrue(hasattr(mod, "mask_token"))

    def test_fetch_pr_status_no_token_returns_empty(self):
        """fetch_pr_status returns {} when no token is configured."""
        from backend.services.repo_workspaces.github_client import fetch_pr_status

        result = _run(fetch_pr_status("owner/repo", 1, token=""))
        self.assertEqual(result, {})

    def test_fetch_pr_status_invalid_slug_returns_empty(self):
        """fetch_pr_status returns {} for invalid / empty inputs."""
        from backend.services.repo_workspaces.github_client import fetch_pr_status

        result = _run(fetch_pr_status("", 0, token="some-token"))
        self.assertEqual(result, {})

    def test_fetch_pr_status_exception_returns_empty(self):
        """fetch_pr_status returns {} on any network exception (fail-soft)."""
        from backend.services.repo_workspaces.github_client import fetch_pr_status

        with patch(
            "backend.services.repo_workspaces.github_client.aiohttp.ClientSession",
            side_effect=RuntimeError("network error"),
        ):
            result = _run(fetch_pr_status("owner/repo", 42, token="tok"))
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# P5-012 — ARC council scaffold: empty-state and live-read
# ---------------------------------------------------------------------------


class TestCouncilReviewQueryService(unittest.TestCase):
    def _make_service(self):
        from backend.application.services.agent_queries.council_review_queries import (
            CouncilReviewQueryService,
        )
        return CouncilReviewQueryService()

    def test_empty_state_when_arc_disabled(self):
        """Returns enabled=False without DB query when ARC_ENABLED=False."""
        with patch("backend.application.services.agent_queries.council_review_queries.config") as mock_cfg:
            mock_cfg.ARC_ENABLED = False
            svc = self._make_service()
            ctx = MagicMock()
            ports = MagicMock()
            result = _run(svc.get_for_feature(ctx, ports, "proj-1", "feat-1"))
        self.assertFalse(result.enabled)
        self.assertEqual(result.items, [])
        # DB must not have been touched
        ports.storage.db.execute.assert_not_called()

    def test_returns_rows_when_arc_enabled(self):
        """Returns rows from repository when ARC_ENABLED=True."""
        with patch("backend.application.services.agent_queries.council_review_queries.config") as mock_cfg:
            mock_cfg.ARC_ENABLED = True
            svc = self._make_service()

            fake_row = {
                "id": "rev-1",
                "project_id": "proj-1",
                "feature_id": "feat-1",
                "status": "approved",
                "summary": "LGTM",
                "created_at": "2026-06-01T00:00:00Z",
                "updated_at": "2026-06-01T00:00:00Z",
            }

            ctx = MagicMock()
            ports = MagicMock()

            with patch(
                "backend.application.services.agent_queries.council_review_queries.SqliteCouncilReviewRepository"
            ) as MockRepo:
                mock_repo_instance = MagicMock()
                mock_repo_instance.list_by_feature = AsyncMock(return_value=[fake_row])
                MockRepo.return_value = mock_repo_instance

                result = _run(svc.get_for_feature(ctx, ports, "proj-1", "feat-1"))

        self.assertTrue(result.enabled)
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.id, "rev-1")
        self.assertEqual(item.status, "approved")
        self.assertEqual(item.summary, "LGTM")


# ---------------------------------------------------------------------------
# P5-013 — MeatyWiki research scaffold: empty-state and live-read
# ---------------------------------------------------------------------------


class TestResearchNoteQueryService(unittest.TestCase):
    def _make_service(self):
        from backend.application.services.agent_queries.research_note_queries import (
            ResearchNoteQueryService,
        )
        return ResearchNoteQueryService()

    def test_empty_state_when_meatywiki_disabled(self):
        """Returns enabled=False without DB query when MEATYWIKI_ENABLED=False."""
        with patch("backend.application.services.agent_queries.research_note_queries.config") as mock_cfg:
            mock_cfg.MEATYWIKI_ENABLED = False
            svc = self._make_service()
            ctx = MagicMock()
            ports = MagicMock()
            result = _run(svc.get_for_feature(ctx, ports, "proj-1", "feat-1"))
        self.assertFalse(result.enabled)
        self.assertEqual(result.items, [])
        ports.storage.db.execute.assert_not_called()

    def test_returns_rows_when_meatywiki_enabled(self):
        """Returns rows from repository when MEATYWIKI_ENABLED=True."""
        with patch("backend.application.services.agent_queries.research_note_queries.config") as mock_cfg:
            mock_cfg.MEATYWIKI_ENABLED = True
            svc = self._make_service()

            fake_row = {
                "id": "note-1",
                "project_id": "proj-1",
                "feature_id": "feat-1",
                "title": "Background Research",
                "url": "https://meatywiki.example.com/notes/1",
                "body": "Detailed findings here.",
                "source": "meatywiki",
                "created_at": "2026-06-01T00:00:00Z",
            }

            ctx = MagicMock()
            ports = MagicMock()

            with patch(
                "backend.application.services.agent_queries.research_note_queries.SqliteResearchNoteRepository"
            ) as MockRepo:
                mock_repo_instance = MagicMock()
                mock_repo_instance.list_by_feature = AsyncMock(return_value=[fake_row])
                MockRepo.return_value = mock_repo_instance

                result = _run(svc.get_for_feature(ctx, ports, "proj-1", "feat-1"))

        self.assertTrue(result.enabled)
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.id, "note-1")
        self.assertEqual(item.title, "Background Research")
        self.assertEqual(item.source, "meatywiki")


# ---------------------------------------------------------------------------
# P5-008 — PR status falls back to "linked" when no token (via planning_command_center)
# ---------------------------------------------------------------------------


class TestPrDtoFallback(unittest.TestCase):
    def test_pr_dto_returns_linked_state_without_token(self):
        """_pr_dto returns state='linked' when no GitHub token is configured."""
        from backend.application.services.agent_queries.planning_command_center import (
            _pr_dto,
        )
        from backend.models import Feature

        feature = MagicMock(spec=Feature)
        feature.prRefs = ["https://github.com/owner/repo/pull/42"]

        with patch(
            "backend.application.services.agent_queries.planning_command_center._github_settings_store"
        ) as mock_store:
            mock_settings = MagicMock()
            mock_settings.token = ""
            mock_store.load.return_value = mock_settings

            dto = _run(_pr_dto(feature))

        self.assertIsNotNone(dto)
        self.assertEqual(dto.state, "linked")
        self.assertEqual(dto.provider, "github")
        self.assertEqual(dto.number, 42)

    def test_pr_dto_returns_none_for_no_refs(self):
        """_pr_dto returns None when feature has no prRefs."""
        from backend.application.services.agent_queries.planning_command_center import (
            _pr_dto,
        )

        feature = MagicMock()
        feature.prRefs = []

        dto = _run(_pr_dto(feature))
        self.assertIsNone(dto)


# ---------------------------------------------------------------------------
# Router / module import checks
# ---------------------------------------------------------------------------


class TestRouterImports(unittest.TestCase):
    def test_council_router_importable(self):
        mod = importlib.import_module("backend.routers.council")
        self.assertTrue(hasattr(mod, "arc_router"))

    def test_meatywiki_router_importable(self):
        mod = importlib.import_module("backend.routers.meatywiki")
        self.assertTrue(hasattr(mod, "meatywiki_router"))

    def test_council_review_queries_importable(self):
        mod = importlib.import_module(
            "backend.application.services.agent_queries.council_review_queries"
        )
        self.assertTrue(hasattr(mod, "CouncilReviewQueryService"))

    def test_research_note_queries_importable(self):
        mod = importlib.import_module(
            "backend.application.services.agent_queries.research_note_queries"
        )
        self.assertTrue(hasattr(mod, "ResearchNoteQueryService"))

    def test_council_repo_importable(self):
        mod = importlib.import_module("backend.db.repositories.council_reviews")
        self.assertTrue(hasattr(mod, "SqliteCouncilReviewRepository"))

    def test_research_repo_importable(self):
        mod = importlib.import_module("backend.db.repositories.research_notes")
        self.assertTrue(hasattr(mod, "SqliteResearchNoteRepository"))

    def test_postgres_council_repo_importable(self):
        mod = importlib.import_module(
            "backend.db.repositories.postgres.council_reviews"
        )
        self.assertTrue(hasattr(mod, "PostgresCouncilReviewRepository"))

    def test_postgres_research_repo_importable(self):
        mod = importlib.import_module(
            "backend.db.repositories.postgres.research_notes"
        )
        self.assertTrue(hasattr(mod, "PostgresResearchNoteRepository"))


if __name__ == "__main__":
    unittest.main()
