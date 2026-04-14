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
                        FeatureForensicsDTO,
                        ProjectStatusDTO,
                        WorkflowDiagnosticsDTO,
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

                    ProjectStatusQueryService.get_status = project_status
                    FeatureForensicsQueryService.get_forensics = feature_forensics
                    WorkflowDiagnosticsQueryService.get_diagnostics = workflow_diagnostics
                    ReportingQueryService.generate_aar = generate_aar
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


if __name__ == "__main__":
    unittest.main()
