"""Tests for the ``ccdash project`` command group.

Covers: add (success, idempotent no-op, --force, --active), list (table and JSON),
use (success, not-found), and unreachable-target error paths.

Mocking strategy mirrors test_commands.py:
- resolve_target is patched to return a known TargetConfig.
- build_client is patched to inject a MagicMock CCDashClient.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ccdash_cli.main import app
from ccdash_cli.runtime.client import (
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ServerError,
)
from ccdash_cli.runtime.config import TargetConfig

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()

_LOCAL_TARGET = TargetConfig(
    name="local",
    url="http://localhost:8000",
    token=None,
    is_implicit_local=True,
)

_REMOTE_TARGET = TargetConfig(
    name="prod",
    url="https://ccdash.example.com",
    token="secret",
    is_implicit_local=False,
)

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

PROJECTS_LIST: list[dict[str, Any]] = [
    {
        "id": "proj-aaa",
        "name": "Alpha",
        "path": "/srv/alpha",
        "description": "",
        "repoUrl": "",
    },
    {
        "id": "proj-bbb",
        "name": "Beta",
        "path": "/srv/beta",
        "description": "",
        "repoUrl": "",
    },
]

ACTIVE_PROJECT: dict[str, Any] = {
    "id": "proj-aaa",
    "name": "Alpha",
    "path": "/srv/alpha",
}

CREATED_PROJECT: dict[str, Any] = {
    "id": "test-uuid-1234",
    "name": "My Repo",
    "path": "/home/user/myrepo",
    "description": "",
    "repoUrl": "",
}


# ---------------------------------------------------------------------------
# Helper: build mock client
# ---------------------------------------------------------------------------


def _make_client(
    *,
    get_side_effects: dict[str, Any] | None = None,
    post_side_effects: dict[str, Any] | None = None,
    get_exception: Exception | None = None,
    post_exception: Exception | None = None,
) -> MagicMock:
    """Build a MagicMock CCDashClient.

    Parameters
    ----------
    get_side_effects:
        Mapping of path-fragment -> return value for ``client.get``.
    post_side_effects:
        Mapping of path-fragment -> return value for ``client.post``.
    get_exception:
        If set, every ``client.get`` call raises this exception.
    post_exception:
        If set, every ``client.post`` call raises this exception.
    """
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    if get_exception is not None:
        client.get.side_effect = get_exception
    elif get_side_effects is not None:
        # Sort keys longest-first so more-specific paths (e.g. /api/projects/active)
        # match before shorter prefixes (e.g. /api/projects).
        _get_keys = sorted(get_side_effects.keys(), key=len, reverse=True)

        def _get_dispatch(path: str, **_: Any) -> Any:
            for key in _get_keys:
                if key in path:
                    val = get_side_effects[key]
                    if isinstance(val, Exception):
                        raise val
                    return val
            return []

        client.get.side_effect = _get_dispatch
    else:
        client.get.return_value = []

    if post_exception is not None:
        client.post.side_effect = post_exception
    elif post_side_effects is not None:
        _post_keys = sorted(post_side_effects.keys(), key=len, reverse=True)

        def _post_dispatch(path: str, **_: Any) -> Any:
            for key in _post_keys:
                if key in path:
                    val = post_side_effects[key]
                    if isinstance(val, Exception):
                        raise val
                    return val
            return {}

        client.post.side_effect = _post_dispatch
    else:
        client.post.return_value = {}

    return client


def _invoke(
    *args: str,
    client: MagicMock,
    target: TargetConfig = _LOCAL_TARGET,
) -> Any:
    """Invoke the CLI with project command, patching resolve_target and build_client."""
    with (
        patch("ccdash_cli.commands.project.resolve_target", return_value=target),
        patch("ccdash_cli.commands.project.build_client", return_value=client),
    ):
        return runner.invoke(app, list(args))


# ---------------------------------------------------------------------------
# project add — success
# ---------------------------------------------------------------------------


class TestProjectAdd:
    def test_add_success_prints_project_id(self):
        """add --name X --path /p registers project and prints its id."""
        client = _make_client(
            get_side_effects={"/api/projects": []},          # idempotency: no match
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "add", "--name", "My Repo", "--path", "/home/user/myrepo",
            client=client,
        )
        assert result.exit_code == 0, result.output
        assert "My Repo" in result.output
        assert "registered" in result.output
        # The id from the server response should appear.
        assert "test-uuid-1234" in result.output

    def test_add_exits_0_on_success(self):
        """add exits 0 when POST succeeds."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "add", "--name", "My Repo", "--path", "/tmp/x",
            client=client,
        )
        assert result.exit_code == 0, result.output

    def test_add_sends_post_to_projects_endpoint(self):
        """add calls client.post on /api/projects."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        _invoke(
            "project", "add", "--name", "X", "--path", "/p",
            client=client,
        )
        assert client.post.called
        call_path = client.post.call_args[0][0]
        assert "/api/projects" in call_path

    def test_add_payload_includes_required_fields(self):
        """add includes id, name, path in the POST body."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        _invoke(
            "project", "add", "--name", "My Repo", "--path", "/home/user/myrepo",
            client=client,
        )
        _, kwargs = client.post.call_args
        body = kwargs.get("json_body", {})
        assert "id" in body
        assert body["name"] == "My Repo"
        assert body["path"] == "/home/user/myrepo"

    # ---------------------------------------------------------------------------
    # add --active
    # ---------------------------------------------------------------------------

    def test_add_active_calls_set_active_endpoint(self):
        """add --active calls POST /api/projects/active/{id} after creation."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={
                "/api/projects/active": {},
                "/api/projects": CREATED_PROJECT,
            },
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/p", "--active",
            client=client,
        )
        assert result.exit_code == 0, result.output
        # Two POSTs: one to /api/projects, one to /api/projects/active/<id>
        assert client.post.call_count == 2

    def test_add_active_confirms_switch_in_output(self):
        """add --active prints 'Active project set to' confirmation."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={
                "/api/projects/active": {},
                "/api/projects": CREATED_PROJECT,
            },
        )
        result = _invoke(
            "project", "add", "--name", "My Repo", "--path", "/p", "--active",
            client=client,
        )
        assert result.exit_code == 0, result.output
        assert "Active project set to" in result.output

    # ---------------------------------------------------------------------------
    # add idempotency
    # ---------------------------------------------------------------------------

    def test_add_idempotent_warns_and_exits_0(self):
        """Re-running add with same --path warns and exits 0 (no-op)."""
        existing = [{"id": "proj-aaa", "name": "Alpha", "path": "/home/user/myrepo"}]
        client = _make_client(
            get_side_effects={"/api/projects": existing},
        )
        result = _invoke(
            "project", "add", "--name", "Alpha", "--path", "/home/user/myrepo",
            client=client,
        )
        assert result.exit_code == 0, result.output
        # Warning goes to stderr, but CliRunner merges by default; check combined output.
        output = result.output
        assert "Warning" in output or "already exists" in output
        # POST should NOT have been called.
        client.post.assert_not_called()

    def test_add_idempotent_includes_existing_id_in_warning(self):
        """Idempotency warning references the existing project id."""
        existing = [{"id": "proj-aaa", "name": "Alpha", "path": "/home/user/myrepo"}]
        client = _make_client(
            get_side_effects={"/api/projects": existing},
        )
        result = _invoke(
            "project", "add", "--name", "Alpha", "--path", "/home/user/myrepo",
            client=client,
        )
        assert "proj-aaa" in result.output

    # ---------------------------------------------------------------------------
    # add --force
    # ---------------------------------------------------------------------------

    def test_add_force_bypasses_idempotency_check(self):
        """add --force sends POST even when a matching path already exists."""
        existing = [{"id": "proj-aaa", "name": "Alpha", "path": "/home/user/myrepo"}]
        client = _make_client(
            get_side_effects={"/api/projects": existing},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "add", "--name", "Alpha", "--path", "/home/user/myrepo", "--force",
            client=client,
        )
        assert result.exit_code == 0, result.output
        assert client.post.called

    def test_add_force_does_not_call_get(self):
        """add --force skips the GET /api/projects idempotency check entirely."""
        client = _make_client(
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        _invoke(
            "project", "add", "--name", "X", "--path", "/p", "--force",
            client=client,
        )
        client.get.assert_not_called()

    # ---------------------------------------------------------------------------
    # remote-target path note
    # ---------------------------------------------------------------------------

    def test_add_remote_target_prints_path_note(self):
        """add against a non-localhost target prints a note about --path semantics."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/home/user/myrepo",
            client=client,
            target=_REMOTE_TARGET,
        )
        assert result.exit_code == 0, result.output
        assert "server host" in result.output or "interpreted on the server" in result.output

    def test_add_localhost_target_no_path_note(self):
        """add against localhost does not print the remote-path note."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/p",
            client=client,
            target=_LOCAL_TARGET,
        )
        # The note should not appear for localhost targets.
        assert "server host" not in result.output


# ---------------------------------------------------------------------------
# project list
# ---------------------------------------------------------------------------


class TestProjectList:
    def test_list_table_shows_id_name_path(self):
        """project list (table) shows ID, Name, Path columns."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": ACTIVE_PROJECT,
            },
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 0, result.output
        assert "proj-aaa" in result.output
        assert "Alpha" in result.output
        assert "/srv/alpha" in result.output

    def test_list_table_marks_active_project(self):
        """project list marks the active project with '*'."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": ACTIVE_PROJECT,
            },
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 0, result.output
        assert "*" in result.output

    def test_list_json_emits_array(self):
        """project list --output json emits a JSON array."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": ACTIVE_PROJECT,
            },
        )
        result = _invoke("project", "list", "--output", "json", client=client)
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_list_json_shortcut_flag(self):
        """project list --json is a shortcut for --output json."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": ACTIVE_PROJECT,
            },
        )
        result = _invoke("project", "list", "--json", client=client)
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_list_active_unavailable_omits_active_column(self):
        """When GET /api/projects/active fails, Active column is omitted with note."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": ServerError("Server error"),
            },
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 0, result.output
        assert "active project unavailable" in result.output

    def test_list_active_not_found_treated_as_no_active(self):
        """GET /api/projects/active returning 404 means no active project (not error)."""
        client = _make_client(
            get_side_effects={
                "/api/projects": PROJECTS_LIST,
                "/api/projects/active": NotFoundError("No active project"),
            },
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 0, result.output
        # No error, no traceback; active column present but no '*' marker.
        assert "active project unavailable" not in result.output

    def test_list_empty_prints_helpful_message(self):
        """project list with no projects prints an empty-state message."""
        client = _make_client(
            get_side_effects={
                "/api/projects": [],
                "/api/projects/active": NotFoundError("No active project"),
            },
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 0, result.output
        assert "No projects" in result.output or "ccdash-cli project add" in result.output


# ---------------------------------------------------------------------------
# project use
# ---------------------------------------------------------------------------


class TestProjectUse:
    def test_use_success_prints_confirmation(self):
        """project use <id> prints confirmation and exits 0."""
        client = _make_client(
            post_side_effects={"/api/projects/active": {}},
        )
        result = _invoke("project", "use", "proj-aaa", client=client)
        assert result.exit_code == 0, result.output
        assert "Active project set to" in result.output
        assert "proj-aaa" in result.output

    def test_use_calls_post_active_endpoint(self):
        """project use calls POST /api/projects/active/{id}."""
        client = _make_client(
            post_side_effects={"/api/projects/active": {}},
        )
        _invoke("project", "use", "proj-aaa", client=client)
        assert client.post.called
        call_path = client.post.call_args[0][0]
        assert "active" in call_path
        assert "proj-aaa" in call_path

    def test_use_not_found_exits_code_1(self):
        """project use <nonexistent-id> exits 1 with a clear error (no traceback)."""
        client = _make_client(
            post_side_effects={"/api/projects/active": NotFoundError("Not found")},
        )
        result = _invoke("project", "use", "nonexistent", client=client)
        assert result.exit_code == 1
        assert "Error" in result.output
        # Must not contain a Python traceback.
        assert "Traceback" not in result.output

    def test_use_not_found_message_does_not_have_traceback(self):
        """Error from project use is a single-line message, not a Python traceback."""
        client = _make_client(
            post_side_effects={"/api/projects/active": NotFoundError("Not found")},
        )
        result = _invoke("project", "use", "bad-id", client=client)
        assert "Traceback" not in result.output
        assert "Exception" not in result.output


# ---------------------------------------------------------------------------
# Unreachable target error handling
# ---------------------------------------------------------------------------


class TestProjectErrorHandling:
    def test_add_unreachable_exits_code_4(self):
        """project add exits 4 when the server is unreachable."""
        client = _make_client(
            get_exception=ConnectionError("Connection refused"),
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/p",
            client=client,
        )
        assert result.exit_code == 4
        assert "Error" in result.output
        assert "Traceback" not in result.output

    def test_list_unreachable_exits_code_4(self):
        """project list exits 4 when the server is unreachable."""
        client = _make_client(
            get_exception=ConnectionError("Connection refused"),
        )
        result = _invoke("project", "list", client=client)
        assert result.exit_code == 4
        assert "Traceback" not in result.output

    def test_use_unreachable_exits_code_4(self):
        """project use exits 4 when the server is unreachable."""
        client = _make_client(
            post_exception=ConnectionError("Connection refused"),
        )
        result = _invoke("project", "use", "proj-aaa", client=client)
        assert result.exit_code == 4
        assert "Traceback" not in result.output

    def test_add_auth_failure_exits_code_2(self):
        """project add exits 2 on HTTP 401."""
        client = _make_client(
            get_exception=AuthenticationError("Unauthorized"),
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/p",
            client=client,
        )
        assert result.exit_code == 2
        assert "Traceback" not in result.output

    def test_use_auth_failure_exits_code_2(self):
        """project use exits 2 on HTTP 401."""
        client = _make_client(
            post_exception=AuthenticationError("Unauthorized"),
        )
        result = _invoke("project", "use", "proj-aaa", client=client)
        assert result.exit_code == 2
        assert "Traceback" not in result.output

    def test_add_unreachable_single_line_error(self):
        """project add unreachable error is a single-line message (no multi-line traceback)."""
        client = _make_client(
            get_exception=ConnectionError("cannot connect"),
        )
        result = _invoke(
            "project", "add", "--name", "X", "--path", "/p",
            client=client,
        )
        # Output should mention 'Error' or 'cannot connect' but no Python traceback.
        assert "Traceback" not in result.output
        error_line = [
            line for line in result.output.splitlines()
            if "Error" in line or "cannot connect" in line
        ]
        assert error_line, f"Expected an error line in output: {result.output!r}"


# ---------------------------------------------------------------------------
# init alias
# ---------------------------------------------------------------------------


class TestProjectInitAlias:
    def test_init_alias_routes_to_project_add(self):
        """'ccdash project init' alias routes to project_add; exits 0 and prints 'registered'."""
        client = _make_client(
            get_side_effects={"/api/projects": []},
            post_side_effects={"/api/projects": CREATED_PROJECT},
        )
        result = _invoke(
            "project", "init", "--name", "X", "--path", "/p",
            client=client,
        )
        assert result.exit_code == 0, result.output
        assert "registered" in result.output


# ---------------------------------------------------------------------------
# CLI registration checks
# ---------------------------------------------------------------------------


class TestCLIRegistration:
    def test_project_appears_in_root_help(self):
        """'project' appears in the top-level --help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "project" in result.output

    def test_project_help_shows_add_list_use(self):
        """ccdash project --help shows add, list, use sub-commands."""
        result = runner.invoke(app, ["project", "--help"])
        assert result.exit_code == 0, result.output
        assert "add" in result.output
        assert "list" in result.output
        assert "use" in result.output
