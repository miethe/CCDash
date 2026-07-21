"""End-to-end smoke test: POST /api/v1/ingest/rf-events -> GET /api/agent/research-runs.

Phase 2 reviewer fix (research-foundry-run-telemetry-v1, CRITICAL #2): proves
the live ingest path actually derives a queryable ``research_runs`` row and
run<->session correlation, not just the ``rf_events`` raw log — exercised at
the HTTP boundary end-to-end, one level above
``test_rf_events_ingest_derives_research_runs.py`` (which drives the same
scenario at the service layer).

Setup mirrors ``test_rf_events_ingest_endpoint.py`` (tempfile SQLite DB +
``build_runtime_app("test")`` + ``TestClient``) for the ingest POST. The GET
side of the round trip overrides ``get_request_context``/``get_core_ports``
(``backend/request_scope.py``) with a hand-built ``RequestContext`` +
``CorePorts`` whose ``workspace_registry`` is a minimal in-memory stub
returning a synthetic ``Project`` for ``project_id="test-project"`` —
``storage``/``db`` on the overridden ``CorePorts`` is the REAL container's,
so the GET reads the exact same database the POST wrote to. This sidesteps
the project-registry's real ``DbProjectManager``, which reads its DB path
from a module-level constant captured whenever ``backend.project_manager``
was first imported in this test process (often long before this test's
``CCDASH_DB_PATH`` env patch takes effect) — registering the throwaway
project through that path is unreliable across the current pytest-collection
import order, per project memory
(``ccdash-test-ordering-db-path-flake.md``-shaped hazard); the override here
avoids it entirely rather than fighting it.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_ingest_to_research_runs_smoke.py -v
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.ports import CorePorts
from backend.models import Project
from backend.request_scope import get_core_ports, get_request_context
from backend.runtime.bootstrap import build_runtime_app

_PROJECT_ID = "test-project"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _event_id() -> str:
    return str(uuid.uuid4())


def _make_event(run_id: str, event_id: str | None = None, **extra) -> dict:
    base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
    obj = {
        "event_id": event_id or _event_id(),
        "timestamp": _iso(base),
        "project": "research-foundry",
        "run_id": run_id,
        "metrics": {
            "claims_total": 6,
            "claims_supported": 5,
            "cost_estimated_usd": 0.12,
        },
        "governance": {"sensitivity": "public", "policy_passed": True},
    }
    obj.update(extra)
    return obj


class _StubWorkspaceRegistry:
    """Minimal WorkspaceRegistry stub — only ``get_project`` is exercised.

    ``resolve_project_scope`` (``backend/application/services/agent_queries/
    _filters.py``) skips ``resolve_scope`` entirely when the RequestContext's
    ``project`` already matches the resolved project id, which is the case
    here (see ``_build_fake_context``) -- so no other WorkspaceRegistry method
    needs a real implementation for this smoke test.
    """

    def __init__(self, project: Project) -> None:
        self._project = project

    def get_project(self, project_id: str) -> Project | None:
        return self._project if project_id == self._project.id else None

    def get_active_project(self) -> Project | None:
        return self._project

    def list_projects(self) -> list[Project]:
        return [self._project]


class TestRfEventsIngestToResearchRunsSmoke(unittest.TestCase):
    """AC-3 / Phase-2-fix #2: live ingest -> queryable, correlated research run."""

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
        ]
        for p in cls._patches:
            p.start()

        cls._app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(
            project_id=_PROJECT_ID
        )

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

        # Wire the GET-side project scope override (see class docstring) using
        # the REAL container's CorePorts.storage so the GET reads the exact DB
        # the ingest POST wrote to.
        real_ports = cls._app.state.core_ports
        stub_project = Project(id=_PROJECT_ID, name="Test Project", path=cls._tmpdb.name)
        fake_ports = dataclasses.replace(
            real_ports, workspace_registry=_StubWorkspaceRegistry(stub_project)
        )
        fake_context = cls._build_fake_context(stub_project)
        cls._app.dependency_overrides[get_core_ports] = lambda: fake_ports
        cls._app.dependency_overrides[get_request_context] = lambda: fake_context

    @classmethod
    def _build_fake_context(cls, project: Project) -> RequestContext:
        principal = Principal(subject="test-local", display_name="Test Local", auth_mode="local")
        project_scope = ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=None,  # noqa: E501 - not read by run_intelligence.py's query path
            sessions_dir=None,
            docs_dir=None,
            progress_dir=None,
        )
        return RequestContext(
            principal=principal,
            workspace=WorkspaceScope(workspace_id=project.id, root_path=None),
            project=project_scope,
            runtime_profile="test",
            trace=TraceContext(request_id="smoke-test", path="/api/agent/research-runs", method="GET"),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._app.dependency_overrides.clear()
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helper: seed a correlated session directly (raw SQLite, dynamic path
    # resolution -- mirrors test_rf_events_ingest_endpoint.py's _fetch_row).
    # ------------------------------------------------------------------

    def _insert_session(self, session_id: str, *, started_at: datetime, ended_at: datetime) -> None:
        from backend.db.connection import _resolve_db_path

        now = _iso(datetime.now(timezone.utc))
        conn = sqlite3.connect(str(_resolve_db_path()))
        try:
            conn.execute(
                """INSERT INTO sessions (id, project_id, started_at, ended_at, created_at, updated_at, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, _PROJECT_ID, _iso(started_at), _iso(ended_at), now, now, f"{session_id}.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # The end-to-end round trip
    # ------------------------------------------------------------------

    def test_ingest_then_list_returns_derived_and_correlated_run(self) -> None:
        base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
        self._insert_session(
            "sess-smoke-1",
            started_at=base - timedelta(minutes=2),
            ended_at=base + timedelta(minutes=15),
        )

        run_id = f"run-smoke-{uuid.uuid4().hex[:8]}"
        event = _make_event(run_id)

        post_resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers={
                "Content-Type": "application/json",
                "x-ccdash-project-id": _PROJECT_ID,
            },
        )
        self.assertEqual(post_resp.status_code, 200, post_resp.text)
        self.assertEqual(post_resp.json()["accepted"], 1, post_resp.json())

        get_resp = self.client.get(
            "/api/agent/research-runs", params={"project_id": _PROJECT_ID}
        )
        self.assertEqual(get_resp.status_code, 200, get_resp.text)
        body = get_resp.json()
        self.assertEqual(body.get("status"), "ok", body)

        items = body.get("items", [])
        matching = [item for item in items if item.get("rf_run_id") == run_id]
        self.assertEqual(
            len(matching),
            1,
            f"expected exactly one derived research_runs row for rf_run_id={run_id!r}, got items={items!r}",
        )
        run_item = matching[0]
        self.assertEqual(run_item["project_id"], _PROJECT_ID)
        self.assertEqual(run_item["event_count"], 1)
        self.assertEqual(run_item["claims_total"], 6)
        self.assertEqual(
            run_item["linked_session_ids"],
            ["sess-smoke-1"],
            "the live ingest path must also run<->session correlate (T2-006) -- "
            "not just derive the research_runs rollup",
        )


if __name__ == "__main__":
    unittest.main()
