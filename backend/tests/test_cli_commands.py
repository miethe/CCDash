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


class _ArtifactRankingsPayload(BaseModel):
    status: str
    project_id: str
    period: str = "7d"
    total: int = 0
    rows: list[dict] = Field(default_factory=list)


class _ArtifactRecommendationsPayload(BaseModel):
    status: str
    project_id: str
    period: str = "30d"
    total: int = 0
    recommendations: list[dict] = Field(default_factory=list)


class CliCommandsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_root_help_lists_artifact_commands(self) -> None:
        result = self.runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("artifact", result.output)

    def test_artifact_help_lists_rankings_and_recommendations(self) -> None:
        result = self.runner.invoke(app, ["artifact", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("rankings", result.output)
        self.assertIn("recommendations", result.output)

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

    def test_artifact_rankings_renders_json_output(self) -> None:
        payload = _ArtifactRankingsPayload(
            status="ok",
            project_id="project-1",
            period="7d",
            total=1,
            rows=[
                {
                    "artifact_id": "planning",
                    "artifact_type": "skill",
                    "exclusive_tokens": 1200,
                    "confidence": 0.88,
                }
            ],
        )

        with patch(
            "backend.cli.commands.artifact.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(
                app,
                ["artifact", "rankings", "--project", "project-1", "--period", "7d", "--json"],
            )

        self.assertEqual(result.exit_code, 0)
        output = json.loads(result.output)
        self.assertEqual(output["project_id"], "project-1")
        self.assertEqual(output["period"], "7d")
        self.assertEqual(output["rows"][0]["artifact_id"], "planning")

    def test_artifact_rankings_handles_empty_rows(self) -> None:
        payload = _ArtifactRankingsPayload(status="ok", project_id="project-1", period="7d")

        with patch(
            "backend.cli.commands.artifact.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["artifact", "rankings", "--project", "project-1"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "\n")

    def test_artifact_recommendations_renders_markdown_summary(self) -> None:
        payload = _ArtifactRecommendationsPayload(
            status="ok",
            project_id="project-1",
            total=1,
            recommendations=[
                {
                    "type": "optimization_target",
                    "confidence": 0.91,
                    "nextAction": "Review before optimizing.",
                    "affectedArtifactIds": ["planning"],
                }
            ],
        )

        with patch(
            "backend.cli.commands.artifact.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(
                app,
                ["artifact", "recommendations", "--project", "project-1", "--min-confidence", "0.7", "--md"],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Artifact recommendations for project-1", result.output)
        self.assertIn("planning", result.output)
        self.assertIn("optimization_target", result.output)

    def test_artifact_recommendations_handles_empty_data(self) -> None:
        payload = _ArtifactRecommendationsPayload(status="ok", project_id="project-1")

        with patch(
            "backend.cli.commands.artifact.runtime.execute_query",
            new=AsyncMock(return_value=payload),
        ):
            result = self.runner.invoke(app, ["artifact", "recommendations", "--project", "project-1"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No recommendations available", result.output)


class _ForensicsPayload(_CliPayload):
    """FeatureForensicsDTO stand-in that carries sessions_note."""

    sessions_note: str = (
        "Session linkage is eventually-consistent (populated by the background sync engine). "
        "For the canonical session list use GET /v1/features/{id}/sessions."
    )


class CliSessionsHintTests(unittest.TestCase):
    """TEST-002.5 criterion 2 — CLI/MCP hint for eventual-consistency invariant.

    ``FeatureForensicsDTO.sessions_note`` must be surfaced in both CLI and MCP
    output so consumers know that ``linked_sessions`` is eventually-consistent
    and ``GET /v1/features/{id}/sessions`` is the canonical view.
    """

    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_feature_report_human_output_includes_sessions_note(self) -> None:
        """Human-mode feature report must emit the sessions_note hint."""
        payload = _ForensicsPayload(
            status="ok",
            project_id="project-1",
            feature_id="feature-hint-1",
            summary="Hint test feature",
            source_refs=["feature-hint-1"],
        )

        with patch(
            "backend.cli.commands.feature.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", True)),
        ):
            result = self.runner.invoke(app, ["feature", "report", "feature-hint-1"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("eventually-consistent", result.output)

    def test_feature_report_json_output_includes_sessions_note(self) -> None:
        """JSON-mode feature report must include sessions_note in the serialised object."""
        payload = _ForensicsPayload(
            status="ok",
            project_id="project-1",
            feature_id="feature-hint-2",
            summary="Hint test feature json",
            source_refs=["feature-hint-2"],
        )

        with patch(
            "backend.cli.commands.feature.runtime.execute_query",
            new=AsyncMock(return_value=(payload, "project-1", True)),
        ):
            result = self.runner.invoke(app, ["feature", "report", "feature-hint-2", "--json"])

        self.assertEqual(result.exit_code, 0)
        output = json.loads(result.output)
        self.assertIn("sessions_note", output)
        self.assertIn("eventually-consistent", output["sessions_note"])
