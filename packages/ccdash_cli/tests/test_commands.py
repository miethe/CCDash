"""Command-level tests for the CCDash standalone CLI.

Covers the feature, session, and report command groups using
typer.testing.CliRunner and unittest.mock to stub out the HTTP layer.

Each command module imports CCDashClient directly, so the patch target is
the module-level name rather than the runtime.client module.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ccdash_cli.main import app
from ccdash_cli.runtime.client import (
    AuthenticationError,
    ConnectionError,
    NotFoundError,
)
from ccdash_cli.runtime.config import ConfigStore, TargetConfig

# ---------------------------------------------------------------------------
# Shared runner
# ---------------------------------------------------------------------------

runner = CliRunner()

# ---------------------------------------------------------------------------
# Canonical mock responses
# ---------------------------------------------------------------------------

FEATURES_LIST_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": [
        {
            "id": "FEAT-1",
            "name": "Auth System",
            "status": "active",
            "category": "security",
            "priority": "high",
            "total_tasks": 5,
            "completed_tasks": 3,
            "updated_at": "2026-04-13",
        },
        {
            "id": "FEAT-2",
            "name": "Dashboard",
            "status": "completed",
            "category": "ui",
            "priority": "medium",
            "total_tasks": 8,
            "completed_tasks": 8,
            "updated_at": "2026-04-12",
        },
    ],
    "meta": {"total": 2, "offset": 0, "limit": 50, "has_more": False},
}

FEATURE_DETAIL_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "feature_slug": "auth-system",
        "id": "FEAT-123",
        "name": "Auth System",
        "status": "active",
        "linked_sessions": [],
        "linked_documents": [],
    },
    "meta": {},
}

FEATURE_SESSIONS_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "sessions": [
            {
                "sessionId": "sess-1",
                "featureId": "FEAT-123",
                "startedAt": "2026-04-13T10:00:00Z",
            }
        ]
    },
    "meta": {"total": 1, "offset": 0, "limit": 50, "has_more": False},
}

FEATURE_DOCUMENTS_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "documents": [
            {
                "id": "doc-1",
                "title": "Auth Design Doc",
                "doc_type": "design",
                "feature_id": "FEAT-123",
            }
        ]
    },
    "meta": {"total": 1},
}

SESSION_LIST_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": [
        {
            "sessionId": "sess-1",
            "featureId": "FEAT-1",
            "startedAt": "2026-04-13T10:00:00Z",
        },
    ],
    "meta": {"total": 1, "offset": 0, "limit": 50, "has_more": False},
}

SESSION_DETAIL_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "sessionId": "sess-1",
        "featureId": "FEAT-1",
        "concerns": {},
        "startedAt": "2026-04-13T10:00:00Z",
    },
    "meta": {},
}

SESSION_SEARCH_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": [
        {
            "sessionId": "sess-1",
            "excerpt": "test query match",
            "score": 0.92,
        }
    ],
    "meta": {"total": 1, "offset": 0, "limit": 25, "has_more": False},
}

SESSION_DRILLDOWN_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "concern": "sentiment",
        "sessionId": "sess-1",
        "analysis": {"score": 0.7, "label": "positive"},
    },
    "meta": {},
}

SESSION_FAMILY_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "root_session_id": "sess-root",
        "session_count": 2,
        "members": [
            {"sessionId": "sess-root", "featureId": "FEAT-1"},
            {"sessionId": "sess-1", "featureId": "FEAT-1"},
        ],
    },
    "meta": {},
}

AAR_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "data": {
        "feature_id": "FEAT-123",
        "summary": "## After-Action Report\n\nFeature completed successfully.",
        "timeline": [],
        "lessons": [],
    },
    "meta": {},
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_LOCAL_TARGET = TargetConfig(
    name="local",
    url="http://localhost:8000",
    token=None,
    is_implicit_local=True,
)


def _mock_client(responses: dict[str, Any]) -> MagicMock:
    """Build a MagicMock CCDashClient that dispatches GET/POST by path fragment.

    Parameters
    ----------
    responses:
        Mapping of path substring -> envelope dict.  The first matching key
        wins.  If nothing matches, a generic ``{"status": "ok", "data": {}, "meta": {}}``
        is returned.
    """
    client = MagicMock()

    def _dispatch(path: str, **_kwargs: Any) -> dict[str, Any]:
        for key, val in responses.items():
            if key in path:
                return val
        return {"status": "ok", "data": {}, "meta": {}}

    client.get.side_effect = _dispatch
    client.post.side_effect = _dispatch
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


def _invoke(*args: str, **kwargs: Any):
    """Invoke the CLI app under both the resolve_target and CCDashClient patches.

    ``_patch_modules`` should be the list of module paths to patch for
    ``CCDashClient`` (e.g. ``["ccdash_cli.commands.feature.CCDashClient"]``).
    ``client`` is the mock to inject.

    Keyword-only:
        client  — MagicMock CCDashClient instance
        modules — list of patch targets for CCDashClient
    """
    client: MagicMock = kwargs.pop("client")
    modules: list[str] = kwargs.pop("modules", [])

    patches = [
        patch("ccdash_cli.commands.feature.resolve_target", return_value=_LOCAL_TARGET),
        patch("ccdash_cli.commands.session.resolve_target", return_value=_LOCAL_TARGET),
        patch("ccdash_cli.commands.report.resolve_target", return_value=_LOCAL_TARGET),
    ]
    client_patches = [patch(m, return_value=client) for m in modules]

    ctx_managers = patches + client_patches
    for p in ctx_managers:
        p.start()
    try:
        result = runner.invoke(app, list(args))
    finally:
        for p in ctx_managers:
            p.stop()
    return result


# ---------------------------------------------------------------------------
# Feature command tests
# ---------------------------------------------------------------------------


class TestRootAndTargetCommands:
    def test_root_version_flag_prints_version(self):
        with patch("ccdash_cli.main._cli_version", return_value="9.9.9"):
            result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == "ccdash-cli 9.9.9"

    def test_version_subcommand_prints_version(self):
        with patch("ccdash_cli.main._cli_version", return_value="9.9.9"):
            result = runner.invoke(app, ["version"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == "ccdash-cli 9.9.9"

    def test_target_show_reports_active_target(self, tmp_path):
        config_path = tmp_path / "config.toml"
        store = ConfigStore(config_path=config_path)
        store.add_target(
            "staging",
            "https://staging.example.com",
            token_ref="target:staging",
            project="proj-a",
        )
        store.set_active_target("staging")

        with (
            patch.object(ConfigStore, "default_config_path", return_value=config_path),
            patch("ccdash_cli.runtime.config._resolve_token", return_value="secret"),
        ):
            result = runner.invoke(app, ["target", "show"])

        assert result.exit_code == 0, result.output
        assert "Name: staging" in result.output
        assert "URL: https://staging.example.com" in result.output
        assert "Project: proj-a" in result.output
        assert "Authentication: token ref 'target:staging' (token loaded)" in result.output
        assert "Source: configured target" in result.output


class TestFeatureCommands:
    """Tests for `ccdash feature <subcommand>`."""

    def test_feature_list_json_returns_parseable_output(self):
        """feature list --json should print JSON containing both features."""
        client = _mock_client({"/api/v1/features": FEATURES_LIST_RESPONSE})
        result = _invoke(
            "feature", "list", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["id"] == "FEAT-1"

    def test_feature_list_status_filter_forwarded(self):
        """feature list --status active should pass status param to GET."""
        client = _mock_client({"/api/v1/features": FEATURES_LIST_RESPONSE})
        result = _invoke(
            "feature", "list", "--status", "active", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0
        # Verify that status was in the params passed to get()
        assert client.get.called
        _, kw = client.get.call_args
        assert "status" in kw.get("params", {})
        assert "active" in kw["params"]["status"]

    def test_feature_list_expands_comma_separated_status_filters(self):
        client = _mock_client({"/api/v1/features": FEATURES_LIST_RESPONSE})
        result = _invoke(
            "feature", "list", "--status", "active,completed", "--status", "planned", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0
        _, kw = client.get.call_args
        assert kw["params"]["status"] == ["active", "completed", "planned"]

    def test_feature_show_json_returns_feature_detail(self):
        """feature show FEAT-123 --json should return feature detail data."""
        client = _mock_client({"/api/v1/features/FEAT-123": FEATURE_DETAIL_RESPONSE})
        result = _invoke(
            "feature", "show", "FEAT-123", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["feature_slug"] == "auth-system"

    def test_feature_show_not_found_exits_code_1(self):
        """feature show NONEXISTENT should exit 1 when server returns NotFoundError."""
        client = MagicMock()
        client.get.side_effect = NotFoundError("Feature not found")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            "feature", "show", "NONEXISTENT",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 1

    def test_feature_sessions_json_returns_sessions(self):
        """feature sessions FEAT-123 --json should return sessions list."""
        client = _mock_client({
            "/api/v1/features/FEAT-123/sessions": FEATURE_SESSIONS_RESPONSE,
        })
        result = _invoke(
            "feature", "sessions", "FEAT-123", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        # sessions key extracted by the command
        assert isinstance(parsed, list)
        assert parsed[0]["sessionId"] == "sess-1"

    def test_feature_documents_json_returns_documents(self):
        """feature documents FEAT-123 --json should return documents list."""
        client = _mock_client({
            "/api/v1/features/FEAT-123/documents": FEATURE_DOCUMENTS_RESPONSE,
        })
        result = _invoke(
            "feature", "documents", "FEAT-123", "--json",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["id"] == "doc-1"


# ---------------------------------------------------------------------------
# Session command tests
# ---------------------------------------------------------------------------


class TestSessionCommands:
    """Tests for `ccdash session <subcommand>`."""

    def test_session_list_json_returns_sessions(self):
        """session list --json should return the sessions array."""
        client = _mock_client({"/api/v1/sessions": SESSION_LIST_RESPONSE})
        result = _invoke(
            "session", "list", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["sessionId"] == "sess-1"

    def test_session_list_feature_filter_forwarded(self):
        """session list --feature FEAT-123 should pass feature_id to GET."""
        client = _mock_client({"/api/v1/sessions": SESSION_LIST_RESPONSE})
        result = _invoke(
            "session", "list", "--feature", "FEAT-123", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0
        assert client.get.called
        _, kw = client.get.call_args
        assert kw.get("params", {}).get("feature_id") == "FEAT-123"

    def test_session_show_json_returns_detail(self):
        """session show sess-1 --json should return session detail."""
        client = _mock_client({"/api/v1/sessions/sess-1": SESSION_DETAIL_RESPONSE})
        result = _invoke(
            "session", "show", "sess-1", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["sessionId"] == "sess-1"

    def test_session_show_not_found_exits_code_1(self):
        """session show NONEXISTENT should exit 1 when NotFoundError raised."""
        client = MagicMock()
        client.get.side_effect = NotFoundError("Session not found")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            "session", "show", "NONEXISTENT",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 1

    def test_session_search_json_returns_results(self):
        """session search 'test query' --json should return search results."""
        client = _mock_client({"/api/v1/sessions/search": SESSION_SEARCH_RESPONSE})
        result = _invoke(
            "session", "search", "test query", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["sessionId"] == "sess-1"

    def test_session_drilldown_json_returns_analysis(self):
        """session drilldown sess-1 --concern sentiment --json should return analysis."""
        client = _mock_client({
            "/api/v1/sessions/sess-1/drilldown": SESSION_DRILLDOWN_RESPONSE
        })
        result = _invoke(
            "session", "drilldown", "sess-1", "--concern", "sentiment", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["concern"] == "sentiment"

    def test_session_family_json_returns_members(self):
        """session family sess-1 --json should return the members list."""
        client = _mock_client({
            "/api/v1/sessions/sess-1/family": SESSION_FAMILY_RESPONSE
        })
        result = _invoke(
            "session", "family", "sess-1", "--json",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["sessionId"] == "sess-root"


# ---------------------------------------------------------------------------
# Report command tests
# ---------------------------------------------------------------------------


class TestReportCommands:
    """Tests for `ccdash report <subcommand>`."""

    def test_report_aar_uses_post(self):
        """report aar --feature FEAT-123 should call client.post."""
        client = _mock_client({"/api/v1/reports/aar": AAR_RESPONSE})
        result = _invoke(
            "report", "aar", "--feature", "FEAT-123",
            client=client,
            modules=["ccdash_cli.commands.report.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        assert client.post.called
        call_path = client.post.call_args[0][0]
        assert "/api/v1/reports/aar" in call_path

    def test_report_aar_default_output_is_markdown(self):
        """report aar without --json should produce markdown-formatted output."""
        client = _mock_client({"/api/v1/reports/aar": AAR_RESPONSE})
        result = _invoke(
            "report", "aar", "--feature", "FEAT-123",
            client=client,
            modules=["ccdash_cli.commands.report.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        # Markdown formatter produces output; JSON output would be parseable as JSON.
        # Verify it is NOT valid JSON (it should be markdown or human text).
        try:
            json.loads(result.output)
            is_json = True
        except json.JSONDecodeError:
            is_json = False
        assert not is_json, "Default report aar output should not be JSON"

    def test_report_feature_uses_get(self):
        """report feature FEAT-123 should call client.get on the features endpoint."""
        client = _mock_client({"/api/v1/features/FEAT-123": FEATURE_DETAIL_RESPONSE})
        result = _invoke(
            "report", "feature", "FEAT-123",
            client=client,
            modules=["ccdash_cli.commands.report.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        assert client.get.called
        call_path = client.get.call_args[0][0]
        assert "FEAT-123" in call_path

    def test_report_feature_default_output_is_markdown(self):
        """report feature FEAT-123 without --json should produce markdown output."""
        client = _mock_client({"/api/v1/features/FEAT-123": FEATURE_DETAIL_RESPONSE})
        result = _invoke(
            "report", "feature", "FEAT-123",
            client=client,
            modules=["ccdash_cli.commands.report.CCDashClient"],
        )
        assert result.exit_code == 0, result.output
        try:
            json.loads(result.output)
            is_json = True
        except json.JSONDecodeError:
            is_json = False
        assert not is_json, "Default report feature output should not be JSON"


# ---------------------------------------------------------------------------
# Cross-cutting error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Shared error handling behaviour across command groups."""

    @pytest.mark.parametrize("cmd_args,module", [
        (["feature", "list"], "ccdash_cli.commands.feature.CCDashClient"),
        (["session", "list"], "ccdash_cli.commands.session.CCDashClient"),
        (["report", "aar", "--feature", "FEAT-1"], "ccdash_cli.commands.report.CCDashClient"),
    ])
    def test_connection_failure_exits_code_4(self, cmd_args, module):
        """Any command should exit 4 when a ConnectionError is raised."""
        client = MagicMock()
        client.get.side_effect = ConnectionError("Connection refused")
        client.post.side_effect = ConnectionError("Connection refused")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            *cmd_args,
            client=client,
            modules=[module],
        )
        assert result.exit_code == 4, (
            f"Expected exit code 4, got {result.exit_code} for {cmd_args!r}. "
            f"Output: {result.output}"
        )

    @pytest.mark.parametrize("cmd_args,module", [
        (["feature", "list"], "ccdash_cli.commands.feature.CCDashClient"),
        (["session", "list"], "ccdash_cli.commands.session.CCDashClient"),
        (["report", "aar", "--feature", "FEAT-1"], "ccdash_cli.commands.report.CCDashClient"),
    ])
    def test_auth_failure_exits_code_2(self, cmd_args, module):
        """Any command should exit 2 when an AuthenticationError is raised."""
        client = MagicMock()
        client.get.side_effect = AuthenticationError("Unauthorized")
        client.post.side_effect = AuthenticationError("Unauthorized")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            *cmd_args,
            client=client,
            modules=[module],
        )
        assert result.exit_code == 2, (
            f"Expected exit code 2, got {result.exit_code} for {cmd_args!r}. "
            f"Output: {result.output}"
        )

    def test_connection_error_message_written_to_stderr(self):
        """Connection errors should print an error message (to stderr/output)."""
        client = MagicMock()
        client.get.side_effect = ConnectionError("Connection refused")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            "feature", "list",
            client=client,
            modules=["ccdash_cli.commands.feature.CCDashClient"],
        )
        # With mix_stderr=False, stderr is available separately; with default
        # CliRunner, error output lands in result.output or result.stderr.
        error_output = (result.stderr if hasattr(result, "stderr") and result.stderr else result.output)
        assert "Error" in error_output or "error" in error_output

    def test_auth_error_message_written_to_stderr(self):
        """Auth errors should print an error message."""
        client = MagicMock()
        client.get.side_effect = AuthenticationError("Invalid token")
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        result = _invoke(
            "session", "list",
            client=client,
            modules=["ccdash_cli.commands.session.CCDashClient"],
        )
        error_output = (result.stderr if hasattr(result, "stderr") and result.stderr else result.output)
        assert "Error" in error_output or "error" in error_output
