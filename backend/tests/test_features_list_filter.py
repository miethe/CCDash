"""Integration tests for feature-list keyword filtering and pagination metadata.

Tests are designed to be self-contained: they seed rows directly into the
throw-away SQLite DB, then call the REST endpoint and assert on the JSON
response shape.

Covers:
  FILTER-003 — ?q= returns case-insensitive substring matches on name/id only
  PAGINATE-004 — default limit is 200, truncated/total fields are accurate,
                 and when total > limit the truncated flag is set
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi.testclient import TestClient

from backend.db import migrations as _migrations
from backend.runtime.bootstrap import build_runtime_app


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_migrations_sync(db_path: str) -> None:
    """Run SQLite migrations synchronously on an isolated DB file."""

    async def _go() -> None:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await _migrations.run_migrations(db)

    asyncio.run(_go())


def _insert_features(db_path: str, features: list[dict]) -> None:
    """Insert feature rows directly into a migrated SQLite DB (synchronous)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        for f in features:
            conn.execute(
                """INSERT OR IGNORE INTO features
                    (id, project_id, name, status, category,
                     total_tasks, completed_tasks, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
                """,
                (
                    f["id"],
                    f.get("project_id", "test-project"),
                    f["name"],
                    f.get("status", "active"),
                    f.get("category", ""),
                    f.get("total_tasks", 0),
                    f.get("completed_tasks", 0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


_SHARED_PATCHES = [
    "backend.runtime.container.initialize_observability",
    "backend.runtime.container.shutdown_observability",
]


def _start_app(tmp_path: str) -> tuple:
    """Migrate the DB, configure connection singleton, build and start the app.

    Returns (app, test_client, list[patcher]) so the caller can stop them
    in tearDownClass.
    """
    import backend.db.connection as _dbc

    # Pre-migrate so the schema exists before the app lifespan opens the conn.
    _run_migrations_sync(tmp_path)

    # Seed connection singleton pointing at our temp DB so get_connection()
    # reuses it (avoiding the module-level DB_PATH being the real cache.db).
    # We also patch DB_PATH so lifespan code that reads it also resolves
    # to our file.
    _dbc._connection = None
    _dbc.DB_PATH = Path(tmp_path)

    env_patch = patch.dict(
        os.environ,
        {
            "CCDASH_DB_PATH": tmp_path,
            "CCDASH_DB_BACKEND": "sqlite",
        },
    )
    env_patch.start()

    app = build_runtime_app("test")

    misc_patches = [
        patch("backend.runtime.container.initialize_observability"),
        patch("backend.runtime.container.shutdown_observability"),
        patch(
            "backend.adapters.jobs.runtime.file_watcher.start",
            new_callable=lambda: lambda: AsyncMock(),
        ),
        patch(
            "backend.adapters.jobs.runtime.file_watcher.stop",
            new_callable=lambda: lambda: AsyncMock(),
        ),
        patch(
            "backend.runtime_ports.project_manager.get_active_project",
            return_value=None,
        ),
    ]
    for p in misc_patches:
        p.start()

    tc = TestClient(app, raise_server_exceptions=False)
    tc.__enter__()

    return app, tc, [env_patch] + misc_patches


def _stop_app(tc: TestClient, patchers: list) -> None:
    tc.__exit__(None, None, None)
    for p in reversed(patchers):
        p.stop()


# ---------------------------------------------------------------------------
# Test: keyword filtering (FILTER-003)
# ---------------------------------------------------------------------------


class TestFeatureKeywordFilter(unittest.TestCase):
    """Verify ?q= keyword filtering at the repository layer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._app, cls._tc, cls._patchers = _start_app(cls._tmpdb.name)
        cls.client = cls._tc

        # Seed after the app has started (DB is migrated and connection is open).
        _insert_features(
            cls._tmpdb.name,
            [
                {"id": "FEAT-repo-01", "name": "Repo Sync Engine", "status": "active"},
                {"id": "FEAT-repo-02", "name": "Repository Analytics", "status": "completed"},
                {"id": "FEAT-auth-01", "name": "Auth System", "status": "active"},
                {"id": "FEAT-dash-01", "name": "Dashboard UI", "status": "active"},
                # id contains REPO (uppercase) but name does not
                {"id": "FEAT-REPO-03", "name": "Legacy Module", "status": "backlog"},
            ],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        _stop_app(cls._tc, cls._patchers)
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Keyword matching tests
    # ------------------------------------------------------------------

    def test_q_returns_only_matching_features(self) -> None:
        resp = self.client.get("/api/v1/features?q=repo")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        ids = {item["id"] for item in body["data"]}
        # "Repo Sync Engine" matches on name; "FEAT-repo-02" matches on id;
        # "Repository Analytics" matches on name; "FEAT-REPO-03" matches on id.
        self.assertIn("FEAT-repo-01", ids)
        self.assertIn("FEAT-repo-02", ids)
        self.assertIn("FEAT-REPO-03", ids)
        # Non-matching features must NOT appear.
        self.assertNotIn("FEAT-auth-01", ids)
        self.assertNotIn("FEAT-dash-01", ids)

    def test_q_is_case_insensitive_uppercase(self) -> None:
        resp_lower = self.client.get("/api/v1/features?q=repo")
        resp_upper = self.client.get("/api/v1/features?q=REPO")
        self.assertEqual(resp_lower.status_code, 200)
        self.assertEqual(resp_upper.status_code, 200)
        ids_lower = {item["id"] for item in resp_lower.json()["data"]}
        ids_upper = {item["id"] for item in resp_upper.json()["data"]}
        self.assertEqual(ids_lower, ids_upper)

    def test_q_mixed_case_matches_same_as_lowercase(self) -> None:
        resp = self.client.get("/api/v1/features?q=RePoSiToRy")
        self.assertEqual(resp.status_code, 200)
        ids = {item["id"] for item in resp.json()["data"]}
        self.assertIn("FEAT-repo-02", ids)  # "Repository Analytics"
        self.assertNotIn("FEAT-auth-01", ids)

    def test_q_no_match_returns_empty_data(self) -> None:
        resp = self.client.get("/api/v1/features?q=XYZNONEXISTENT")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"], [])
        self.assertEqual(body["meta"]["total"], 0)

    def test_q_total_reflects_filtered_count(self) -> None:
        resp = self.client.get("/api/v1/features?q=auth")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Only FEAT-auth-01 matches "auth".
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(len(body["data"]), 1)

    def test_no_q_returns_all_features(self) -> None:
        resp = self.client.get("/api/v1/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["total"], 5)


# ---------------------------------------------------------------------------
# Test: pagination metadata (PAGINATE-004)
# ---------------------------------------------------------------------------


class TestFeaturePaginationMeta(unittest.TestCase):
    """Verify default limit=200, truncated, and total fields."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._app, cls._tc, cls._patchers = _start_app(cls._tmpdb.name)
        cls.client = cls._tc

        # Seed 5 features — all below the default limit of 200.
        _insert_features(
            cls._tmpdb.name,
            [{"id": f"FEAT-PAG-{i:03d}", "name": f"Feature {i}"} for i in range(5)],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        _stop_app(cls._tc, cls._patchers)
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    def test_default_limit_is_200(self) -> None:
        resp = self.client.get("/api/v1/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["limit"], 200)

    def test_truncated_false_when_all_fit(self) -> None:
        resp = self.client.get("/api/v1/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # 5 features, limit 200 — nothing is truncated.
        self.assertFalse(body["meta"]["truncated"])

    def test_total_reflects_full_count(self) -> None:
        resp = self.client.get("/api/v1/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["total"], 5)

    def test_truncated_true_when_more_exist_beyond_limit(self) -> None:
        # Request with limit=2 against 5 features — truncated should be true.
        resp = self.client.get("/api/v1/features?limit=2&offset=0")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["meta"]["truncated"])
        self.assertEqual(body["meta"]["total"], 5)
        self.assertEqual(len(body["data"]), 2)

    def test_has_more_false_when_last_page(self) -> None:
        # Fetch the last 2 of 5 (offset=3, limit=10).
        resp = self.client.get("/api/v1/features?limit=10&offset=3")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["meta"]["has_more"])
        self.assertFalse(body["meta"]["truncated"])

    def test_truncated_field_present_in_meta(self) -> None:
        body = self.client.get("/api/v1/features").json()
        self.assertIn("truncated", body["meta"])


# ---------------------------------------------------------------------------
# Test: CLI truncation hint (PAGINATE-003 unit)
# ---------------------------------------------------------------------------


class TestFeatureCLITruncationHint(unittest.TestCase):
    """Verify the CLI truncation hint renders when meta.truncated is true."""

    def _invoke_with_mock(self, response_body: dict) -> str:
        """Invoke the feature list command with a mocked HTTP response."""
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        from ccdash_cli.main import app
        from ccdash_cli.runtime.config import TargetConfig

        runner = CliRunner()
        client_mock = MagicMock()
        client_mock.get.return_value = response_body
        client_mock.__enter__ = MagicMock(return_value=client_mock)
        client_mock.__exit__ = MagicMock(return_value=False)

        local_target = TargetConfig(
            name="local",
            url="http://localhost:8000",
            token=None,
            is_implicit_local=True,
        )

        with (
            patch("ccdash_cli.commands.feature.resolve_target", return_value=local_target),
            patch("ccdash_cli.commands.feature.build_client", return_value=client_mock),
        ):
            result = runner.invoke(app, ["feature", "list"])

        return result.output

    def test_truncation_hint_shown_when_truncated_true(self) -> None:
        response = {
            "status": "ok",
            "data": [
                {
                    "id": f"FEAT-{i}",
                    "name": f"Feature {i}",
                    "status": "active",
                    "category": "",
                    "priority": "",
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "updated_at": "",
                }
                for i in range(200)
            ],
            "meta": {
                "total": 213,
                "offset": 0,
                "limit": 200,
                "has_more": True,
                "truncated": True,
            },
        }
        output = self._invoke_with_mock(response)
        self.assertIn("213", output)
        # The hint message should include "Use --limit" guidance.
        self.assertIn("--limit", output)

    def test_truncation_hint_not_shown_when_truncated_false(self) -> None:
        response = {
            "status": "ok",
            "data": [
                {
                    "id": "FEAT-1",
                    "name": "Feature 1",
                    "status": "active",
                    "category": "",
                    "priority": "",
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "updated_at": "",
                }
            ],
            "meta": {
                "total": 1,
                "offset": 0,
                "limit": 200,
                "has_more": False,
                "truncated": False,
            },
        }
        output = self._invoke_with_mock(response)
        self.assertNotIn("--limit", output)


if __name__ == "__main__":
    unittest.main()
