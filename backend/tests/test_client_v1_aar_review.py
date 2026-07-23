"""Contract tests for GET /api/v1/project/aar-review (T4-002/T4-003).

Verifies:
  - Empty-project resilience: no ``aar_reviews`` rows -> 200 with a
    normalized empty payload, never an error (AC-P4.4).
  - Persisted-row shape: seeding one ``aar_reviews`` row and reading it back
    through the endpoint reproduces the full §7.2 ``AARReviewDTO`` shape --
    nested ``correlation``, 3-value ``triage_verdict``, ``flags[]``,
    ``reasons``, and the deprecated flat aliases.
  - Document-level fan-out dedup: two persisted rows sharing the same
    ``aar_document_id`` (different ``session_id``) collapse to exactly one
    entry in the response.
  - The ``aar-review`` capability string is present in
    ``GET /api/v1/capabilities`` (T4-003).

Setup mirrors ``test_rf_events_ingest_to_research_runs_smoke.py``: a
throwaway SQLite DB + ``build_runtime_app("test")`` + ``TestClient``, with
``get_request_context``/``get_core_ports`` overridden to a hand-built
``RequestContext``/``CorePorts`` whose ``workspace_registry`` is a minimal
stub returning a synthetic ``Project`` for a known ``project_id`` -- the
overridden ``CorePorts.storage`` is the REAL container's, so the seeded rows
(inserted via a raw ``sqlite3`` connection) are read by the exact same
database the endpoint queries.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_client_v1_aar_review.py -v
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import tempfile
import unittest
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

_PROJECT_ID = "test-project-aar-review"


class _StubWorkspaceRegistry:
    """Minimal WorkspaceRegistry stub — only ``get_project`` is exercised.

    ``resolve_project_scope`` skips ``resolve_scope`` entirely when the
    RequestContext's ``project`` already matches the resolved project id
    (the case here — see ``_build_fake_context``), so no other
    WorkspaceRegistry method needs a real implementation.
    """

    def __init__(self, project: Project) -> None:
        self._project = project

    def get_project(self, project_id: str) -> Project | None:
        return self._project if project_id == self._project.id else None

    def get_active_project(self) -> Project | None:
        return self._project

    def list_projects(self) -> list[Project]:
        return [self._project]


class TestClientV1AarReview(unittest.TestCase):
    """AC-P4.4: v1 endpoint returns the persisted, reconciled §7.2 verdict."""

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

        real_ports = cls._app.state.core_ports
        stub_project = Project(id=_PROJECT_ID, name="Test AAR Review Project", path=cls._tmpdb.name)
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
            root_path=None,
            sessions_dir=None,
            docs_dir=None,
            progress_dir=None,
        )
        return RequestContext(
            principal=principal,
            workspace=WorkspaceScope(workspace_id=project.id, root_path=None),
            project=project_scope,
            runtime_profile="test",
            trace=TraceContext(
                request_id="test-aar-review", path="/api/v1/project/aar-review", method="GET"
            ),
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
    # Helper: seed an aar_reviews row directly (raw sqlite3) -- mirrors
    # test_rf_events_ingest_to_research_runs_smoke.py's _insert_session.
    # ------------------------------------------------------------------

    def _insert_aar_review_row(
        self,
        *,
        aar_document_id: str,
        session_id: str,
        triage_verdict: str = "deep_review_recommended",
        session_ids: list[str] | None = None,
        confidence: float | None = 0.82,
        strategy: str = "two_hop_doc_feature_session",
        feature_id: str | None = "FEAT-123",
    ) -> None:
        from backend.db.connection import _resolve_db_path

        correlation = {
            "strategy": strategy,
            "confidence": confidence,
            "session_ids": session_ids if session_ids is not None else [session_id],
            "feature_id": feature_id,
        }
        flags = [
            {
                "flag_id": "long_running_no_checkpoint",
                "triggered": True,
                "severity": "medium",
                "evidence_refs": ["session:" + session_id],
                "rationale": "Session ran 45 minutes with no checkpoint evidence.",
            }
        ]
        reasons = ["Correlated via two-hop document->feature->session strategy."]
        evidence_refs = ["doc:" + aar_document_id, "session:" + session_id]

        conn = sqlite3.connect(str(_resolve_db_path()))
        try:
            conn.execute(
                """INSERT INTO aar_reviews (
                    aar_document_id, session_id, project_id, aar_document_path,
                    correlation, flags, triage_verdict, triage_reasons,
                    evidence_refs, generated_at, provenance_skill_name,
                    provenance_workflow_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    aar_document_id,
                    session_id,
                    _PROJECT_ID,
                    f".claude/worknotes/{aar_document_id}/aar.md",
                    json.dumps(correlation),
                    json.dumps(flags),
                    triage_verdict,
                    json.dumps(reasons),
                    json.dumps(evidence_refs),
                    "2026-07-20T10:00:00Z",
                    None,
                    None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Empty-project resilience (AC-P4.4)
    # ------------------------------------------------------------------

    def test_a_empty_project_returns_200_with_normalized_empty_payload(self) -> None:
        """Runs first alphabetically (prefix ``test_a_``) — no rows seeded yet.

        The other tests in this class share one class-level DB (mirroring
        ``test_rf_events_ingest_to_research_runs_smoke.py``'s pattern) and
        seed rows into it; this test asserts the true "nothing persisted
        yet" contract state before any of them run.
        """
        resp = self.client.get("/api/v1/project/aar-review")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        data = body["data"]
        self.assertEqual(data["reviews"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["project_id"], _PROJECT_ID)

    def test_envelope_has_required_top_level_fields(self) -> None:
        body = self.client.get("/api/v1/project/aar-review").json()
        for field in ("status", "data", "meta"):
            self.assertIn(field, body)

    def test_meta_has_required_fields(self) -> None:
        body = self.client.get("/api/v1/project/aar-review").json()
        for field in ("generated_at", "instance_id", "request_id"):
            self.assertIn(field, body["meta"])

    # ------------------------------------------------------------------
    # Persisted-row shape (§7.2 DTO) — AC-P4.4
    # ------------------------------------------------------------------

    def test_persisted_row_round_trips_the_section_7_2_shape(self) -> None:
        self._insert_aar_review_row(
            aar_document_id="aar-doc-shape-001",
            session_id="sess-shape-001",
        )

        resp = self.client.get(
            "/api/v1/project/aar-review", params={"bypass_cache": "true"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        data = body["data"]
        matching = [r for r in data["reviews"] if r["document_id"] == "aar-doc-shape-001"]
        self.assertEqual(
            len(matching), 1, f"expected exactly one entry for aar-doc-shape-001, got {matching!r}"
        )

        review = matching[0]

        # Top-level §7.2 fields.
        self.assertEqual(review["document_id"], "aar-doc-shape-001")
        self.assertEqual(review["triage_verdict"], "deep_review_recommended")
        self.assertEqual(
            review["reasons"],
            ["Correlated via two-hop document->feature->session strategy."],
        )
        self.assertEqual(
            review["source_refs"],
            ["doc:aar-doc-shape-001", "session:sess-shape-001"],
        )
        self.assertEqual(review["generated_at"], "2026-07-20T10:00:00Z")

        # Nested correlation{}.
        correlation = review["correlation"]
        self.assertEqual(correlation["strategy"], "two_hop_doc_feature_session")
        self.assertEqual(correlation["confidence"], 0.82)
        self.assertEqual(correlation["session_ids"], ["sess-shape-001"])
        self.assertEqual(correlation["feature_id"], "FEAT-123")

        # flags[].
        self.assertEqual(len(review["flags"]), 1)
        flag = review["flags"][0]
        self.assertEqual(flag["flag_id"], "long_running_no_checkpoint")
        self.assertTrue(flag["triggered"])
        self.assertEqual(flag["severity"], "medium")
        self.assertEqual(flag["evidence_refs"], ["session:sess-shape-001"])

        # Deprecated flat aliases auto-synced from the nested shape.
        self.assertEqual(review["session_refs"], ["sess-shape-001"])
        self.assertEqual(review["correlation_confidence"], 0.82)
        self.assertEqual(review["correlation_strategy"], "two_hop_doc_feature_session")
        self.assertEqual(review["verdict"], "deep_review_recommended")

    def test_document_fanout_rows_dedupe_to_one_entry(self) -> None:
        """Two rows sharing aar_document_id (different session_id) -> one entry."""
        self._insert_aar_review_row(
            aar_document_id="aar-doc-fanout-001",
            session_id="sess-fanout-a",
            session_ids=["sess-fanout-a", "sess-fanout-b"],
        )
        self._insert_aar_review_row(
            aar_document_id="aar-doc-fanout-001",
            session_id="sess-fanout-b",
            session_ids=["sess-fanout-a", "sess-fanout-b"],
        )

        resp = self.client.get(
            "/api/v1/project/aar-review", params={"bypass_cache": "true"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        matching = [r for r in data["reviews"] if r["document_id"] == "aar-doc-fanout-001"]
        self.assertEqual(
            len(matching),
            1,
            f"expected exactly one deduped entry for aar-doc-fanout-001, got {matching!r}",
        )
        self.assertEqual(
            sorted(matching[0]["correlation"]["session_ids"]),
            ["sess-fanout-a", "sess-fanout-b"],
        )

    def test_human_triage_required_verdict_round_trips(self) -> None:
        """3-value triage_verdict enum: human_triage_required with null confidence."""
        self._insert_aar_review_row(
            aar_document_id="aar-doc-human-001",
            session_id="sess-human-001",
            triage_verdict="human_triage_required",
            confidence=None,
            feature_id=None,
        )

        resp = self.client.get(
            "/api/v1/project/aar-review", params={"bypass_cache": "true"}
        )
        data = resp.json()["data"]
        matching = [r for r in data["reviews"] if r["document_id"] == "aar-doc-human-001"]
        self.assertEqual(len(matching), 1)
        review = matching[0]
        self.assertEqual(review["triage_verdict"], "human_triage_required")
        self.assertIsNone(review["correlation"]["confidence"])
        self.assertIsNone(review["correlation"]["feature_id"])

    # ------------------------------------------------------------------
    # Capability advertisement (T4-003)
    # ------------------------------------------------------------------

    def test_capabilities_endpoint_advertises_aar_review(self) -> None:
        resp = self.client.get("/api/v1/capabilities")
        self.assertEqual(resp.status_code, 200, resp.text)
        capabilities = resp.json()["data"]["capabilities"]
        self.assertIn("aar-review", capabilities)

    # ------------------------------------------------------------------
    # OpenAPI schema: new path registered
    # ------------------------------------------------------------------

    def test_openapi_schema_exposes_aar_review_path(self) -> None:
        paths = self._app.openapi()["paths"]
        self.assertIn(
            "/api/v1/project/aar-review",
            paths,
            "GET /api/v1/project/aar-review not found in OpenAPI schema",
        )


if __name__ == "__main__":
    unittest.main()
