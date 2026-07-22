from __future__ import annotations

import json
import os
import tempfile
import textwrap
import unittest
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _decode_tool_result(result) -> dict:
    text_blocks = [item.text for item in result.content if getattr(item, "text", None)]
    if not text_blocks:
        raise AssertionError("Expected at least one text response block from MCP tool call.")
    return json.loads(text_blocks[0])


def _tool_text(result) -> str:
    text_blocks = [item.text for item in result.content if getattr(item, "text", None)]
    if not text_blocks:
        raise AssertionError("Expected at least one text response block from MCP tool call.")
    return text_blocks[0]


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.venv_bin = cls.repo_root / "backend/.venv/bin"
        cls._tempdir = tempfile.TemporaryDirectory()
        sitecustomize = Path(cls._tempdir.name) / "sitecustomize.py"
        sitecustomize.write_text(
            textwrap.dedent(
                """
                import os

                if os.environ.get("CCDASH_MCP_TEST_MODE") == "1":
                    from backend.application.services.agent_queries import (
                        AARReportDTO,
                        AARReviewDTO,
                        ArtifactRecommendationsDTO,
                        FeatureForensicsDTO,
                        ProjectStatusDTO,
                        WorkflowDiagnosticsDTO,
                    )
                    from backend.application.services.agent_queries.aar_review import (
                        AARReviewQueryService,
                    )
                    from backend.application.services.agent_queries.artifact_intelligence import (
                        ArtifactIntelligenceQueryService,
                    )
                    from backend.application.services.agent_queries.feature_forensics import (
                        FeatureForensicsQueryService,
                    )
                    from backend.application.services.agent_queries.project_status import (
                        ProjectStatusQueryService,
                    )
                    from backend.application.services.agent_queries.reporting import (
                        ReportingQueryService,
                    )
                    from backend.application.services.agent_queries.workflow_intelligence import (
                        WorkflowDiagnosticsQueryService,
                    )

                    async def project_status(self, context, ports, project_id_override=None):
                        project_id = project_id_override or "test-project"
                        return ProjectStatusDTO(
                            project_id=project_id,
                            project_name="Test Project",
                            source_refs=[project_id],
                        )

                    async def feature_forensics(self, context, ports, feature_id):
                        status = "error" if feature_id == "missing-feature" else "ok"
                        return FeatureForensicsDTO(
                            status=status,
                            feature_id=feature_id,
                            feature_slug=feature_id,
                            source_refs=[feature_id],
                        )

                    async def workflow_diagnostics(self, context, ports, feature_id=None):
                        status = "error" if feature_id == "missing-feature" else "ok"
                        return WorkflowDiagnosticsDTO(
                            status=status,
                            project_id="test-project",
                            feature_id=feature_id,
                            source_refs=[feature_id or "test-project"],
                        )

                    async def generate_aar(self, context, ports, feature_id):
                        status = "error" if feature_id == "missing-feature" else "ok"
                        return AARReportDTO(
                            status=status,
                            feature_id=feature_id,
                            feature_slug=feature_id,
                            source_refs=[feature_id],
                        )

                    async def aar_review(self, context, ports, document_id):
                        status = "error" if document_id == "missing-document" else "ok"
                        return AARReviewDTO(
                            status=status,
                            document_id=document_id,
                            source_refs=[document_id],
                        )

                    async def artifact_recommendations(
                        self,
                        context,
                        ports,
                        project_id_override=None,
                        *,
                        period="30d",
                        collection_id=None,
                        user_scope=None,
                        workflow_id=None,
                        recommendation_type=None,
                        min_confidence=None,
                        limit=100,
                        bypass_cache=False,
                    ):
                        project_id = project_id_override or "test-project"
                        return ArtifactRecommendationsDTO(
                            status="ok",
                            project_id=project_id,
                            period=period,
                            total=1,
                            recommendations=[
                                {
                                    "type": "optimization_target",
                                    "confidence": min_confidence or 0.82,
                                    "nextAction": "Review prompt context before the next optimization pass.",
                                    "affectedArtifactIds": ["artifact-alpha"],
                                }
                            ],
                            source_refs=[project_id],
                        )

                    ProjectStatusQueryService.get_status = project_status
                    FeatureForensicsQueryService.get_forensics = feature_forensics
                    WorkflowDiagnosticsQueryService.get_diagnostics = workflow_diagnostics
                    ReportingQueryService.generate_aar = generate_aar
                    AARReviewQueryService.get_review = aar_review
                    ArtifactIntelligenceQueryService.get_recommendations = artifact_recommendations

                    # ── Session tool mocks (Phase 3 / T3-007) ─────────────────────────────
                    # Patch get_session_detail so session tools work without a seeded DB.
                    # The mock returns a minimal SessionDetailBundle with token telemetry.
                    # Missing session_id "missing-session" returns None (not-found path).
                    # The mock bundle intentionally has no secrets — redaction parity is
                    # proven in test_session_parity.py (T3-005) using the real service.

                    import base64 as _b64, json as _json

                    def _enc_cursor(offset):
                        raw = _json.dumps({"o": offset}, separators=(",", ":"))
                        return _b64.urlsafe_b64encode(raw.encode()).decode()

                    class _FakePage:
                        def __init__(self, items, offset, limit):
                            self.items = items
                            self.cursor = _enc_cursor(offset)
                            self.limit = limit
                            self.next_cursor = None
                        def as_dict(self):
                            return {
                                "items": self.items,
                                "cursor": self.cursor,
                                "limit": self.limit,
                                "nextCursor": self.next_cursor,
                            }

                    class _FakeBundle:
                        def __init__(self, session_id, project_id, page):
                            self.session_id = session_id
                            self.project_id = project_id
                            self.session = {
                                "id": session_id,
                                "project_id": project_id,
                                "status": "completed",
                                "model": "claude-3-5-sonnet",
                            }
                            self.transcript = page
                            self.subagents = []
                            self.tokens = {
                                "tokensIn": 100,
                                "tokensOut": 200,
                                "modelIOTokens": 300,
                                "cacheCreationInputTokens": 0,
                                "cacheReadInputTokens": 0,
                                "cacheInputTokens": 0,
                                "observedTokens": 0,
                                "toolReportedTokens": 0,
                                "totalCost": 0.01,
                                "durationSeconds": 60.0,
                            }
                            self.artifacts = []
                            self.links = []
                            self.redacted_field_count = 0

                        def as_dict(self):
                            d = {
                                "sessionId": self.session_id,
                                "projectId": self.project_id,
                                "session": self.session,
                                "subagents": self.subagents,
                                "tokens": self.tokens,
                                "artifacts": self.artifacts,
                                "links": self.links,
                                "redactedFieldCount": self.redacted_field_count,
                            }
                            if self.transcript is not None:
                                d["transcript"] = self.transcript.as_dict()
                            return d

                    async def _mock_get_session_detail(
                        project_id,
                        session_id,
                        ports,
                        *,
                        include=None,
                        cursor=None,
                        limit=None,
                        context=None,
                    ):
                        if session_id == "missing-session" or not session_id:
                            return None
                        eff_limit = min(limit or 50, 200)
                        page_items = [
                            {
                                "id": "mcp-log-0",
                                "content": "mcp test transcript content",
                                "type": "message",
                                "timestamp": "2026-06-01T10:00:00Z",
                            }
                        ]
                        page = _FakePage(page_items, 0, eff_limit)
                        return _FakeBundle(session_id, project_id, page)

                    # Patch the source module and the sessions tool module's local binding
                    import backend.application.services.agent_queries.session_detail as _sd_mod
                    _sd_mod.get_session_detail = _mock_get_session_detail

                    import backend.mcp.tools.sessions as _sessions_tool_mod
                    _sessions_tool_mod.get_session_detail = _mock_get_session_detail

                    # ── Research run tool mocks (Phase 2 / T2-005) ────────────────────────
                    # Patch RunIntelligenceQueryService so research-run tools work without
                    # a seeded rf_events/research_runs DB. "missing-run" and the sentinel
                    # project "no-such-project-001" exercise the not-found / error paths.

                    from backend.application.services.agent_queries.run_intelligence import (
                        ResearchRunDetailDTO,
                        ResearchRunDetailResponseDTO,
                        ResearchRunListResponseDTO,
                        ResearchRunSummaryDTO,
                        RunIntelligenceQueryService,
                    )

                    async def _mock_list_runs(
                        self,
                        context,
                        ports,
                        *,
                        project_id_override=None,
                        cursor=None,
                        limit=50,
                        bypass_cache=False,
                    ):
                        project_id = project_id_override or "test-project"
                        if project_id == "no-such-project-001":
                            return ResearchRunListResponseDTO(
                                status="error",
                                project_id=project_id,
                                cursor=cursor or "",
                                limit=limit,
                            )
                        item = ResearchRunSummaryDTO(
                            run_id="run-uuid-0001",
                            rf_run_id="rf-slug-alpha",
                            project_id=project_id,
                            event_count=3,
                            linked_session_ids=["sess-0001"],
                            linked_session_id="sess-0001",
                        )
                        return ResearchRunListResponseDTO(
                            status="ok",
                            project_id=project_id,
                            items=[item],
                            cursor=cursor or "",
                            limit=limit,
                            next_cursor=None,
                            source_refs=[project_id],
                        )

                    async def _mock_get_run_detail(
                        self,
                        context,
                        ports,
                        run_id,
                        *,
                        project_id_override=None,
                        bypass_cache=False,
                    ):
                        project_id = project_id_override or "test-project"
                        if project_id == "no-such-project-001":
                            return ResearchRunDetailResponseDTO(
                                status="error",
                                project_id=project_id,
                                run_id=run_id,
                                found=False,
                            )
                        if run_id == "missing-run":
                            return ResearchRunDetailResponseDTO(
                                status="ok",
                                project_id=project_id,
                                run_id=run_id,
                                found=False,
                                source_refs=[project_id, run_id],
                            )
                        detail = ResearchRunDetailDTO(
                            run_id=run_id,
                            rf_run_id="rf-slug-alpha",
                            project_id=project_id,
                            event_count=3,
                            linked_session_ids=["sess-0001"],
                            linked_session_id="sess-0001",
                        )
                        return ResearchRunDetailResponseDTO(
                            status="ok",
                            project_id=project_id,
                            run_id=run_id,
                            found=True,
                            run=detail,
                            source_refs=[project_id, run_id, "sess-0001"],
                        )

                    RunIntelligenceQueryService.list_runs = _mock_list_runs
                    RunIntelligenceQueryService.get_run_detail = _mock_get_run_detail
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tempdir.cleanup()
        super().tearDownClass()

    def _server_parameters(self) -> StdioServerParameters:
        env = dict(os.environ)
        env["CCDASH_MCP_TEST_MODE"] = "1"
        env["PATH"] = os.pathsep.join([str(self.venv_bin), env.get("PATH", "")])
        env["PYTHONPATH"] = os.pathsep.join(
            [
                self._tempdir.name,
                str(self.repo_root),
                env.get("PYTHONPATH", ""),
            ]
        )
        return StdioServerParameters(
            command="python",
            args=["-m", "backend.mcp.server"],
            cwd=self.repo_root,
            env=env,
        )

    async def _call_tool(self, name: str, arguments: dict | None = None) -> dict:
        async with stdio_client(self._server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    name,
                    arguments or {},
                    read_timeout_seconds=timedelta(seconds=15),
                )
        return _decode_tool_result(result)

    async def _call_tool_text(self, name: str, arguments: dict | None = None) -> str:
        async with stdio_client(self._server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    name,
                    arguments or {},
                    read_timeout_seconds=timedelta(seconds=15),
                )
        return _tool_text(result)

    async def test_list_tools_exposes_expected_mcp_surface(self) -> None:
        async with stdio_client(self._server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()

        self.assertEqual(
            {tool.name for tool in tools.tools},
            {
                "ccdash_project_status",
                "ccdash_feature_forensics",
                "ccdash_workflow_failure_patterns",
                "ccdash_generate_aar",
                "ccdash_aar_review",
                "artifact_recommendations",
                # live-agents-count-v1
                "ccdash_live_active_count",
                # system-wide-metrics-v1
                "ccdash_system_active_count",
                # session intelligence (Phase 3 / T3-001)
                "ccdash_session_search",
                "ccdash_session_detail",
                "ccdash_session_transcript",
                # research run intelligence (Phase 2 / T2-005)
                "ccdash_research_runs_list",
                "ccdash_research_run_detail",
            },
        )

    async def test_project_status_tool_returns_ok_envelope(self) -> None:
        payload = await self._call_tool("ccdash_project_status")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["project_id"], "test-project")
        self.assertEqual(payload["meta"]["project_id"], "test-project")
        self.assertIn("generated_at", payload["meta"])
        self.assertIn("data_freshness", payload["meta"])
        self.assertEqual(payload["meta"]["source_refs"], ["test-project"])

    async def test_feature_forensics_tool_surfaces_error_envelope(self) -> None:
        payload = await self._call_tool(
            "ccdash_feature_forensics",
            {"feature_id": "missing-feature"},
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["data"]["feature_id"], "missing-feature")
        self.assertEqual(payload["meta"]["feature_id"], "missing-feature")

    async def test_workflow_failure_patterns_tool_is_callable(self) -> None:
        payload = await self._call_tool(
            "ccdash_workflow_failure_patterns",
            {"feature_id": "missing-feature"},
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["data"]["project_id"], "test-project")
        self.assertEqual(payload["data"]["feature_id"], "missing-feature")
        self.assertEqual(payload["meta"]["project_id"], "test-project")

    async def test_generate_aar_tool_is_callable(self) -> None:
        payload = await self._call_tool(
            "ccdash_generate_aar",
            {"feature_id": "missing-feature"},
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["data"]["feature_id"], "missing-feature")
        self.assertEqual(payload["meta"]["feature_id"], "missing-feature")

    async def test_aar_review_tool_surfaces_error_envelope(self) -> None:
        payload = await self._call_tool(
            "ccdash_aar_review",
            {"document_id": "missing-document"},
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["data"]["document_id"], "missing-document")

    async def test_aar_review_tool_is_callable(self) -> None:
        payload = await self._call_tool(
            "ccdash_aar_review",
            {"document_id": "doc-1"},
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["document_id"], "doc-1")

    async def test_artifact_recommendations_tool_returns_markdown_summary(self) -> None:
        payload = await self._call_tool_text(
            "artifact_recommendations",
            {"project_id": "test-project", "min_confidence": 0.7, "limit": 5},
        )

        self.assertIn("Artifact recommendations for test-project", payload)
        self.assertIn("artifact-alpha", payload)
        self.assertIn("optimization_target", payload)


    # ── Session tool tests (Phase 3 / T3-007) ─────────────────────────────────

    async def test_session_detail_missing_project_id_returns_error(self) -> None:
        """ccdash_session_detail without project_id must return status='error'."""
        payload = await self._call_tool(
            "ccdash_session_detail",
            {"session_id": "test-sess-001"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("project_id", payload.get("error", "").lower())

    async def test_session_transcript_missing_project_id_returns_error(self) -> None:
        """ccdash_session_transcript without project_id must return status='error'."""
        payload = await self._call_tool(
            "ccdash_session_transcript",
            {"session_id": "test-sess-001"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("project_id", payload.get("error", "").lower())

    async def test_session_search_missing_project_id_returns_error(self) -> None:
        """ccdash_session_search without project_id must return status='error'."""
        payload = await self._call_tool(
            "ccdash_session_search",
            {"query": "some search term"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("project_id", payload.get("error", "").lower())

    async def test_session_search_missing_query_returns_error(self) -> None:
        """ccdash_session_search with project_id but no query must return status='error'."""
        payload = await self._call_tool(
            "ccdash_session_search",
            {"project_id": "test-project"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("query", payload.get("error", "").lower())

    async def test_session_detail_missing_session_id_returns_error(self) -> None:
        """ccdash_session_detail with project_id but no session_id returns status='error'."""
        payload = await self._call_tool(
            "ccdash_session_detail",
            {"project_id": "non-active-project-001"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("session_id", payload.get("error", "").lower())

    async def test_session_detail_unknown_session_returns_not_found(self) -> None:
        """ccdash_session_detail with unknown session_id returns status='not_found'."""
        payload = await self._call_tool(
            "ccdash_session_detail",
            {"project_id": "non-active-project-001", "session_id": "missing-session"},
        )
        self.assertEqual(payload["status"], "not_found")
        self.assertIn("missing-session", payload.get("error", ""))

    async def test_session_detail_non_active_project_returns_full_detail(self) -> None:
        """ccdash_session_detail with a non-active project_id returns full detail bundle."""
        payload = await self._call_tool(
            "ccdash_session_detail",
            {
                "project_id": "non-active-project-001",
                "session_id": "test-session-parity-001",
            },
        )
        self.assertEqual(payload["status"], "ok")
        data = payload["data"]
        # Core identity fields
        self.assertEqual(data.get("projectId"), "non-active-project-001")
        self.assertEqual(data.get("sessionId"), "test-session-parity-001")
        # Transcript segment present with cursor envelope
        transcript = data.get("transcript")
        self.assertIsNotNone(transcript)
        self.assertIsInstance(transcript.get("items"), list)
        for field in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(field, transcript, f"transcript missing cursor field: {field}")
        # Token telemetry present
        tokens = data.get("tokens")
        self.assertIsNotNone(tokens)
        self.assertIn("tokensIn", tokens)
        self.assertIn("totalCost", tokens)

    async def test_session_detail_meta_carries_project_and_session_id(self) -> None:
        """ccdash_session_detail response meta must carry project_id and session_id."""
        payload = await self._call_tool(
            "ccdash_session_detail",
            {
                "project_id": "non-active-project-001",
                "session_id": "test-session-parity-001",
            },
        )
        self.assertEqual(payload["status"], "ok")
        meta = payload.get("meta", {})
        self.assertEqual(meta.get("project_id"), "non-active-project-001")
        self.assertEqual(meta.get("session_id"), "test-session-parity-001")

    async def test_session_transcript_non_active_project_returns_page(self) -> None:
        """ccdash_session_transcript returns a valid transcript page envelope."""
        payload = await self._call_tool(
            "ccdash_session_transcript",
            {
                "project_id": "non-active-project-001",
                "session_id": "test-session-parity-001",
            },
        )
        self.assertEqual(payload["status"], "ok")
        data = payload["data"]
        self.assertIsInstance(data.get("items"), list)
        for field in ("sessionId", "projectId", "items", "cursor", "limit", "nextCursor"):
            self.assertIn(field, data, f"transcript page missing field: {field}")
        self.assertEqual(data["projectId"], "non-active-project-001")

    async def test_session_transcript_cursor_is_string(self) -> None:
        """ccdash_session_transcript cursor field must be a string (opaque base64)."""
        payload = await self._call_tool(
            "ccdash_session_transcript",
            {
                "project_id": "non-active-project-001",
                "session_id": "test-session-parity-001",
                "limit": 10,
            },
        )
        self.assertEqual(payload["status"], "ok")
        cursor = payload["data"].get("cursor")
        self.assertIsInstance(cursor, str)
        self.assertTrue(cursor, "cursor must be non-empty")

    # ── Research run tool tests (Phase 2 / T2-005) ────────────────────────────

    async def test_research_runs_list_returns_ok_envelope_with_items(self) -> None:
        payload = await self._call_tool(
            "ccdash_research_runs_list",
            {"project_id": "test-project"},
        )
        self.assertEqual(payload["status"], "ok")
        items = payload["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["run_id"], "run-uuid-0001")
        self.assertEqual(items[0]["rf_run_id"], "rf-slug-alpha")
        self.assertEqual(items[0]["linked_session_ids"], ["sess-0001"])
        self.assertEqual(payload["meta"]["project_id"], "test-project")

    async def test_research_runs_list_surfaces_error_envelope(self) -> None:
        payload = await self._call_tool(
            "ccdash_research_runs_list",
            {"project_id": "no-such-project-001"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["meta"]["project_id"], "no-such-project-001")

    async def test_research_run_detail_returns_found_run(self) -> None:
        payload = await self._call_tool(
            "ccdash_research_run_detail",
            {"run_id": "run-uuid-0001", "project_id": "test-project"},
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["data"]["found"])
        self.assertEqual(payload["data"]["run"]["run_id"], "run-uuid-0001")
        self.assertEqual(payload["meta"]["run_id"], "run-uuid-0001")
        self.assertEqual(payload["meta"]["project_id"], "test-project")

    async def test_research_run_detail_unknown_run_returns_ok_not_found(self) -> None:
        """"No such run" is a normal status='ok'/found=False response, never an error."""
        payload = await self._call_tool(
            "ccdash_research_run_detail",
            {"run_id": "missing-run", "project_id": "test-project"},
        )
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["data"]["found"])
        self.assertIsNone(payload["data"].get("run"))

    async def test_research_run_detail_surfaces_error_envelope(self) -> None:
        payload = await self._call_tool(
            "ccdash_research_run_detail",
            {"run_id": "run-uuid-0001", "project_id": "no-such-project-001"},
        )
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["meta"]["project_id"], "no-such-project-001")


if __name__ == "__main__":
    unittest.main()
