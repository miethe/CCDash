"""Contract + regression tests for GET /api/v1/sessions/{id}/family.

Verifies:
  - HTTP 404 for an unknown session_id.
  - Envelope shape (status/data/meta) and SessionFamilyDTO field presence.
  - Regression: subagent children of the anchor's root session MUST appear
    in the family response (session_count > 1). Prior to the fix,
    ``list_paginated`` was called without ``include_subagents``, which
    defaults to False and silently excludes every ``session_type ==
    'subagent'`` row via the WHERE clause in
    ``backend/db/repositories/sessions.py``.
  - ``workflow_refs``/``source_ref`` are populated from row columns when
    present on the underlying session row.

Test runtime: build_runtime_app("test") with a throwaway SQLite DB, same
pattern as test_client_v1_session_detail.py. No real filesystem is touched.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.runtime.bootstrap import build_runtime_app

# ---------------------------------------------------------------------------
# Fixture rows
# ---------------------------------------------------------------------------

_ROOT_ID = "sess-family-root-001"

_ANCHOR_ROW: dict = {
    "id": _ROOT_ID,
    "project_id": "",  # empty → unscoped lookup path accepted
    "task_id": "",
    "title": "Root session",
    "status": "completed",
    "model": "claude-3-5-sonnet-20241022",
    "root_session_id": _ROOT_ID,
    "started_at": "2024-06-01T10:00:00Z",
    "ended_at": "2024-06-01T11:00:00Z",
    "tokens_in": 1000,
    "tokens_out": 500,
    "total_cost": 0.0075,
    "duration_seconds": 3600.0,
    "workflow_id": "wf-alpha",
    "source_ref": "claude-code://sess-family-root-001",
}

_SUBAGENT_ROWS: list[dict] = [
    {
        "id": f"sess-family-sub-{i:03d}",
        "project_id": "",
        "task_id": "",
        "title": f"Subagent {i}",
        "status": "completed",
        "model": "claude-3-5-sonnet-20241022",
        "root_session_id": _ROOT_ID,
        "started_at": "2024-06-01T10:0{}:00Z".format(i),
        "ended_at": "2024-06-01T10:1{}:00Z".format(i),
        "tokens_in": 100,
        "tokens_out": 50,
        "total_cost": 0.001,
        "duration_seconds": 120.0,
        "session_type": "subagent",
        "workflow_id": None,
        "source_ref": "",
    }
    for i in range(8)
]

_FAMILY_ROWS: list[dict] = [_ANCHOR_ROW] + _SUBAGENT_ROWS


class TestSessionFamilyV1Endpoint(unittest.TestCase):
    """Contract + regression tests for the /family endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        cls._env_patcher.start()

        cls._app = build_runtime_app("test")

        cls._patches = [
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
                "backend.runtime_ports.db_project_manager.get_active_project",
                return_value=None,
            ),
        ]
        for p in cls._patches:
            p.start()

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    def _family_mock_context(self, list_paginated_return: list[dict]):
        """Mock the anchor lookup + the family list_paginated call."""
        return (
            patch(
                "backend.db.repositories.sessions.SqliteSessionRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=_ANCHOR_ROW,
            ),
            patch(
                "backend.db.repositories.sessions.SqliteSessionRepository.list_paginated",
                new_callable=AsyncMock,
                return_value=list_paginated_return,
            ),
        )

    # ------------------------------------------------------------------
    # 404 for unknown session_id
    # ------------------------------------------------------------------

    def test_family_unknown_session_returns_404(self) -> None:
        with patch(
            "backend.db.repositories.sessions.SqliteSessionRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = self.client.get(
                "/api/v1/sessions/NONEXISTENT-SESSION-ZZZZZ/family"
            )
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Envelope shape
    # ------------------------------------------------------------------

    def test_family_returns_200_with_mocked_session(self) -> None:
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list:
            resp = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_family_envelope_has_required_top_level_fields(self) -> None:
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list:
            body = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family").json()
        for field in ("status", "data", "meta"):
            self.assertIn(field, body)
        self.assertEqual(body["status"], "ok")

    # ------------------------------------------------------------------
    # Regression: subagent children must be included
    # ------------------------------------------------------------------

    def test_family_includes_subagent_children(self) -> None:
        """The core regression: session_count must exceed 1 when subagent
        children of the root exist. Prior to the fix, list_paginated was
        called without include_subagents, which the repository defaults to
        False — excluding every subagent row from the family response.
        """
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list:
            body = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family").json()
        data = body["data"]
        self.assertGreater(
            data["session_count"],
            1,
            "family response must include subagent children, not just the root",
        )
        self.assertEqual(data["session_count"], len(_FAMILY_ROWS))
        member_ids = {m["session_id"] for m in data["members"]}
        for sub_row in _SUBAGENT_ROWS:
            self.assertIn(sub_row["id"], member_ids)

    def test_family_list_paginated_requests_include_subagents(self) -> None:
        """Assert the actual mechanism: the filters dict passed to
        list_paginated must set include_subagents=True.
        """
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list as mocked_list_paginated:
            resp = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family")
        self.assertEqual(resp.status_code, 200, resp.text)
        mocked_list_paginated.assert_awaited_once()
        _, kwargs = mocked_list_paginated.call_args
        filters = kwargs.get("filters") or {}
        self.assertTrue(
            filters.get("include_subagents"),
            f"list_paginated must be called with filters.include_subagents=True, got: {filters}",
        )

    # ------------------------------------------------------------------
    # Field population from row columns
    # ------------------------------------------------------------------

    def test_family_root_member_has_workflow_refs_and_source_ref(self) -> None:
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list:
            body = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family").json()
        members = {m["session_id"]: m for m in body["data"]["members"]}
        root_member = members[_ROOT_ID]
        self.assertEqual(root_member["workflow_refs"], ["wf-alpha"])
        self.assertEqual(root_member["source_ref"], "claude-code://sess-family-root-001")

    def test_family_subagent_member_has_empty_workflow_refs(self) -> None:
        """Subagent rows in the fixture have workflow_id=None; the DTO must
        degrade to an empty list, not error or fabricate a value."""
        mock_get, mock_list = self._family_mock_context(_FAMILY_ROWS)
        with mock_get, mock_list:
            body = self.client.get(f"/api/v1/sessions/{_ROOT_ID}/family").json()
        members = {m["session_id"]: m for m in body["data"]["members"]}
        sub_member = members[_SUBAGENT_ROWS[0]["id"]]
        self.assertEqual(sub_member["workflow_refs"], [])


if __name__ == "__main__":
    unittest.main()
