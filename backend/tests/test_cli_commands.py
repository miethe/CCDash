import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel, Field
from typer.testing import CliRunner

from backend.cli.main import app


class _CliPayload(BaseModel):
    status: str
    project_id: str | None = None
    feature_id: str | None = None
    summary: str | None = None
    generated_at: str = "2026-04-11T10:00:00Z"
    data_freshness: str = "fresh"
    source_refs: list[str] = Field(default_factory=list)


class _WorkflowProblem(BaseModel):
    workflow_id: str
    failure_rate: float
    failure_count: int


class _WorkflowPayload(BaseModel):
    status: str
    project_id: str
    feature_id: str | None = None
    generated_at: str = "2026-04-11T10:00:00Z"
    data_freshness: str = "fresh"
    source_refs: list[str] = Field(default_factory=list)
    problem_workflows: list[_WorkflowProblem] = Field(default_factory=list)


class CliCommandsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_status_project_renders_human_output(self) -> None:
        payload = _CliPayload(
            status="ok",
            project_id="project-1",
            summary="All systems nominal",
            source_refs=["project-1"],
        )

        with patch(
            "backend.cli.commands.status.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["status", "project"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Project Status", result.output)
        self.assertIn("project-1", result.output)

    def test_status_project_errors_when_project_unresolved(self) -> None:
        payload = _CliPayload(status="error")

        with patch(
            "backend.cli.commands.status.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["--project", "missing-project", "status", "project"])

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Project 'missing-project' was not found.", result.output)

    def test_feature_report_renders_json_output(self) -> None:
        payload = _CliPayload(
            status="ok",
            project_id="project-1",
            feature_id="feature-123",
            summary="Feature is stable",
            source_refs=["feature-123"],
        )

        with patch(
            "backend.cli.commands.feature.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", True)),
        ):
            result = self.runner.invoke(app, ["feature", "report", "feature-123", "--json"])

        self.assertEqual(result.exit_code, 0)
        output = json.loads(result.output)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["feature_id"], "feature-123")

    def test_feature_report_errors_when_feature_missing(self) -> None:
        payload = _CliPayload(status="error", feature_id="missing-feature")

        with patch(
            "backend.cli.commands.feature.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", False)),
        ):
            result = self.runner.invoke(app, ["feature", "report", "missing-feature"])

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Feature 'missing-feature' was not found in project 'project-1'.", result.output)

    def test_workflow_failures_renders_markdown_output(self) -> None:
        payload = _WorkflowPayload(
            status="ok",
            project_id="project-1",
            source_refs=["project-1"],
            problem_workflows=[
                _WorkflowProblem(workflow_id="workflow:phase-execution", failure_rate=0.6, failure_count=3)
            ],
        )

        with patch(
            "backend.cli.commands.workflow.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["workflow", "failures", "--md"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("# Workflow Failures", result.output)
        self.assertIn("problem workflows", result.output)
        self.assertIn("workflow:phase-execution", result.output)

    def test_workflow_failures_rejects_conflicting_output_flags(self) -> None:
        payload = _WorkflowPayload(status="ok", project_id="project-1")

        with patch(
            "backend.cli.commands.workflow.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["workflow", "failures", "--json", "--md"])

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Choose only one of --json or --md.", result.output)

    def test_report_aar_renders_human_output(self) -> None:
        payload = _CliPayload(
            status="ok",
            project_id="project-1",
            feature_id="feature-321",
            summary="AAR complete",
            source_refs=["feature-321"],
        )

        with patch(
            "backend.cli.commands.report.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", True)),
        ):
            result = self.runner.invoke(app, ["report", "aar", "--feature", "feature-321"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("AAR Report: feature-321", result.output)
        self.assertIn("AAR complete", result.output)

    def test_report_aar_errors_when_feature_missing(self) -> None:
        payload = _CliPayload(status="error", feature_id="missing-feature")

        with patch(
            "backend.cli.commands.report.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", False)),
        ):
            result = self.runner.invoke(app, ["report", "aar", "--feature", "missing-feature"])

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Feature 'missing-feature' was not found in project 'project-1'.", result.output)
