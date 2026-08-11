"""Project management sub-commands for the CCDash standalone CLI.

Commands in this module register, list, and switch projects on a running
CCDash instance without hand-editing ``projects.json``, and flip the
per-project hosted-LLM egress consent gate.

API endpoints used:
    GET  /api/projects             -- list projects (list command + idempotency)
    POST /api/projects             -- create project (add command)
    POST /api/projects/active/{id} -- set active project (add --active, use command)
    GET  /api/projects/active      -- get active project (list command active marker)
    POST /api/projects/{id}/egress-consent -- grant/revoke per-project hosted-LLM
                                              egress consent (consent command)

Exit code contract (mirrors existing CLI patterns):
    0 -- success
    1 -- server / not-found error
    2 -- HTTP 401 authentication failure, or a usage error (bad flag combination)
    4 -- network / connection failure
"""
from __future__ import annotations

import uuid
from typing import Any, NoReturn, cast
from urllib.parse import urlparse

import typer

from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime import state as app_state
from ccdash_cli.runtime.client import (
    AuthenticationError,
    build_client,
    CCDashClientError,
    ConnectionError,
    NotFoundError,
    ServerError,
)
from ccdash_cli.runtime.config import resolve_target

project_app = typer.Typer(help="Manage CCDash projects.")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LOCAL_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_localhost_target(url: str) -> bool:
    """Return True when *url* points at localhost / 127.0.0.1 / ::1."""
    try:
        host = urlparse(url).hostname or ""
        return host in _LOCAL_HTTP_HOSTS
    except Exception:  # noqa: BLE001
        return False


def _build_project_payload(
    *,
    project_id: str,
    name: str,
    path: str,
    description: str = "",
    repo_url: str = "",
) -> dict[str, Any]:
    """Construct the flat-field project dict that satisfies the server's Project model.

    The server's ``_migrate_legacy_path_config`` validator auto-constructs
    ``pathConfig`` from flat fields at parse time, so we deliberately send only
    flat fields.  Do NOT mix flat and nested ``pathConfig`` here.

    Fields not supplied by the CLI (``agentPlatforms``, ``planDocsPath``,
    ``sessionsPath``, ``progressPath``) use the server model's defaults:
    - agentPlatforms: ["Claude Code"]
    - planDocsPath:   "docs/project_plans/"
    - sessionsPath:   ""
    - progressPath:   "progress"
    """
    return {
        "id": project_id,
        "name": name,
        "path": path,
        "description": description,
        "repoUrl": repo_url,
        "agentPlatforms": ["Claude Code"],
        "planDocsPath": "docs/project_plans/",
        "sessionsPath": "",
        "progressPath": "progress",
    }


def _handle_client_error(exc: CCDashClientError, target_url: str) -> NoReturn:
    """Surface *exc* to stderr with a single-line message and raise typer.Exit.

    Maps each subclass to the established exit-code contract.
    Always raises — never returns.
    """
    if isinstance(exc, ConnectionError):
        typer.echo(
            f"Error: cannot connect to '{target_url}'. Is the CCDash server running?",
            err=True,
        )
        raise typer.Exit(code=4)
    if isinstance(exc, AuthenticationError):
        typer.echo(
            "Error: authentication failed (HTTP 401). Check your bearer token.\n"
            "Tip: run 'ccdash-cli target login <name>' to store credentials.",
            err=True,
        )
        raise typer.Exit(code=2)
    # NotFoundError, ServerError, other CCDashClientError -> exit 1
    typer.echo(f"Error: {exc.message}", err=True)
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# add / init
# ---------------------------------------------------------------------------


@project_app.command("add")
def project_add(
    name: str = typer.Option(..., "--name", help="Display name for the project."),
    path: str = typer.Option(
        ..., "--path", help="Server-side filesystem root for the project."
    ),
    description: str = typer.Option(
        "", "--description", help="Optional project description."
    ),
    repo_url: str = typer.Option(
        "", "--repo-url", help="Optional repository URL."
    ),
    active: bool = typer.Option(
        False, "--active", help="Set this project as the active project after creation."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass idempotency check and always send POST /api/projects.",
    ),
) -> None:
    """Register a new project on the resolved CCDash target.

    Alias: ``ccdash-cli project init`` (same behaviour).
    """
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    # Remote-target path reminder: paths are stored and resolved on the server.
    if not _is_localhost_target(target.url):
        typer.echo(
            "Note: --path is interpreted on the server host, not the local machine."
        )

    try:
        with build_client(target) as client:
            # --- Idempotency check ---
            if not force:
                try:
                    existing_body = client.get("/api/projects")
                    existing_projects: list[dict[str, Any]] = existing_body if isinstance(existing_body, list) else []
                    for proj in existing_projects:
                        if isinstance(proj, dict) and proj.get("path") == path:
                            existing_id = proj.get("id", "")
                            existing_name = proj.get("name", "")
                            typer.echo(
                                f"Warning: a project with path '{path}' already exists "
                                f"(id: {existing_id}, name: '{existing_name}'). "
                                f"Use --force to re-register.",
                                err=True,
                            )
                            raise typer.Exit(code=0)
                except CCDashClientError as exc:
                    _handle_client_error(exc, target.url)

            # --- Build and POST the project ---
            project_id = str(uuid.uuid4())
            payload = _build_project_payload(
                project_id=project_id,
                name=name,
                path=path,
                description=description,
                repo_url=repo_url,
            )

            try:
                result = client.post("/api/projects", json_body=payload)
            except CCDashClientError as exc:
                _handle_client_error(exc, target.url)

            # Server returns the Project model (not an envelope); handle both cases.
            created = result if isinstance(result, dict) else {}
            created_id = created.get("id", project_id)
            created_name = created.get("name", name)
            typer.echo(f"Project '{created_name}' registered (id: {created_id}).")

            # --- Optionally set active ---
            if active:
                try:
                    client.post(f"/api/projects/active/{created_id}")
                except CCDashClientError as exc:
                    typer.echo(
                        f"Warning: project created but could not set as active: {exc.message}",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                typer.echo(
                    f"Active project set to '{created_name}' ({created_id})."
                )

    except typer.Exit:
        raise
    except CCDashClientError as exc:
        _handle_client_error(exc, target.url)


# Typer alias: ccdash-cli project init -> project_add
project_app.command("init")(project_add)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@project_app.command("list")
def project_list(
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
) -> None:
    """List all projects on the resolved CCDash target."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            default=app_state.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    # Pre-initialise so pyright sees these as always-bound after the try block.
    projects: list[dict[str, Any]] = []
    active_id: str | None = None
    active_unavailable = False

    try:
        with build_client(target) as client:
            # Fetch project list.  client.get() is typed dict[str, Any] but the
            # /api/projects endpoint returns a JSON array; cast after the isinstance
            # guard so pyright accepts element-level .get() calls.
            projects_body = client.get("/api/projects")
            if isinstance(projects_body, list):
                projects = cast(list[dict[str, Any]], projects_body)

            # Attempt to fetch active project (non-fatal)
            try:
                active_body = client.get("/api/projects/active")
                # The server returns the Project model directly; pull out the id.
                if isinstance(active_body, dict):
                    active_id = active_body.get("id")
            except NotFoundError:
                # 404 = no active project set; treat as active_id = None, not an error.
                active_id = None
            except CCDashClientError:
                # Any other failure -> omit the Active column.
                active_unavailable = True

    except CCDashClientError as exc:
        _handle_client_error(exc, target.url)

    if mode == OutputMode.json:
        typer.echo(get_formatter(mode).render(projects, title="Projects"))
        return

    # --- Human-readable table ---
    if not projects:
        typer.echo("No projects registered on this target.")
        typer.echo(
            "Register one with: ccdash-cli project add --name <name> --path <path>"
        )
        return

    # Column widths computed from content.
    col_id = max(len("ID"), *(len(str(p.get("id", ""))) for p in projects))
    col_name = max(len("Name"), *(len(str(p.get("name", ""))) for p in projects))
    col_path = max(len("Path"), *(len(str(p.get("path", ""))) for p in projects))

    if active_unavailable:
        header = f"  {'ID':<{col_id}}  {'Name':<{col_name}}  {'Path':<{col_path}}"
        typer.echo(header)
        typer.echo("-" * len(header))
        for proj in projects:
            pid = str(proj.get("id", ""))
            pname = str(proj.get("name", ""))
            ppath = str(proj.get("path", ""))
            typer.echo(f"  {pid:<{col_id}}  {pname:<{col_name}}  {ppath:<{col_path}}")
        typer.echo("(active project unavailable)")
    else:
        header = f"  {'ID':<{col_id}}  {'Name':<{col_name}}  {'Path':<{col_path}}  Active"
        typer.echo(header)
        typer.echo("-" * len(header))
        for proj in projects:
            pid = str(proj.get("id", ""))
            pname = str(proj.get("name", ""))
            ppath = str(proj.get("path", ""))
            marker = "*" if (active_id and pid == active_id) else " "
            typer.echo(
                f"{marker} {pid:<{col_id}}  {pname:<{col_name}}  {ppath:<{col_path}}  {marker}"
            )


# ---------------------------------------------------------------------------
# use
# ---------------------------------------------------------------------------


@project_app.command("use")
def project_use(
    project_id: str = typer.Argument(..., help="Project ID to activate."),
) -> None:
    """Switch the active project on the resolved CCDash target."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        with build_client(target) as client:
            try:
                client.post(f"/api/projects/active/{project_id}")
            except NotFoundError:
                typer.echo(
                    f"Error: project '{project_id}' not found. "
                    f"Check the ID with: ccdash-cli project list",
                    err=True,
                )
                raise typer.Exit(code=1)
            except ServerError as exc:
                # Surface detail verbatim for WatcherRebindError-flavoured 4xx/5xx.
                typer.echo(f"Error: {exc.message}", err=True)
                raise typer.Exit(code=1)
            except CCDashClientError as exc:
                _handle_client_error(exc, target.url)
    except typer.Exit:
        raise
    except CCDashClientError as exc:
        _handle_client_error(exc, target.url)

    typer.echo(f"Active project set to '{project_id}'.")


# ---------------------------------------------------------------------------
# consent (hosted-LLM egress)
# ---------------------------------------------------------------------------


def _read_consent_flag(project: dict[str, Any]) -> bool | None:
    """Extract the per-project egress-consent flag from a Project payload.

    Accepts the canonical snake_case field and a camelCase spelling so the CLI
    keeps working if the wire shape is ever aliased.  Returns None when the
    server response carries no consent field at all (older server) — absence is
    a contract state, not a bug, and must not be reported as ``false``.
    """
    for key in ("llm_egress_consent", "llmEgressConsent"):
        if key in project:
            return bool(project[key])
    return None


@project_app.command("consent")
def project_consent(
    project_id: str = typer.Argument(
        ..., help="Project ID whose hosted-LLM egress consent should change."
    ),
    grant: bool = typer.Option(
        False, "--grant", help="Grant hosted-LLM egress consent for this project."
    ),
    revoke: bool = typer.Option(
        False, "--revoke", help="Revoke hosted-LLM egress consent for this project."
    ),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
) -> None:
    """Grant or revoke a project's hosted-LLM egress consent.

    This flips a data-egress gate: it is the per-project half of a two-level
    fail-closed consent model.  The deployment-wide ``CCDASH_LLM_EGRESS_CONSENT``
    env flag must ALSO be true before any of this project's sessions can reach
    a hosted model.  Exactly one of ``--grant`` / ``--revoke`` is required —
    there is deliberately no default.
    """
    if grant and revoke:
        typer.echo(
            "Error: --grant and --revoke are mutually exclusive; pass exactly one.",
            err=True,
        )
        raise typer.Exit(code=2)
    if not grant and not revoke:
        typer.echo(
            "Error: one of --grant or --revoke is required "
            "(consent changes are never implicit).",
            err=True,
        )
        raise typer.Exit(code=2)

    granted = grant

    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            default=app_state.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    updated: dict[str, Any] = {}

    try:
        with build_client(target) as client:
            try:
                result = client.post(
                    f"/api/projects/{project_id}/egress-consent",
                    json_body={"granted": granted},
                )
            except NotFoundError:
                typer.echo(
                    f"Error: project '{project_id}' not found. "
                    f"Check the ID with: ccdash-cli project list",
                    err=True,
                )
                raise typer.Exit(code=1)
            except CCDashClientError as exc:
                _handle_client_error(exc, target.url)

            if isinstance(result, dict):
                updated = result
    except typer.Exit:
        raise
    except CCDashClientError as exc:
        _handle_client_error(exc, target.url)

    if mode == OutputMode.json:
        typer.echo(get_formatter(mode).render(updated, title="Project"))
        return

    project_name = str(updated.get("name") or project_id)
    server_state = _read_consent_flag(updated)
    effective = granted if server_state is None else server_state
    state_word = "GRANTED" if effective else "REVOKED"

    typer.echo(
        f"Hosted-LLM egress consent {state_word} for project "
        f"'{project_name}' ({project_id})."
    )
    if server_state is None:
        typer.echo(
            "Note: the server response did not report a consent field; "
            "the state above reflects the request that was sent.",
            err=True,
        )
    elif server_state != granted:
        typer.echo(
            f"Warning: requested granted={granted} but the server reports "
            f"{server_state}. The server's value is authoritative.",
            err=True,
        )

    if effective:
        typer.echo(
            "Reminder: this is only the per-project half of the gate. "
            "The deployment-wide CCDASH_LLM_EGRESS_CONSENT env flag must ALSO "
            "be true before any of this project's sessions egress to a hosted "
            "model. Both levels are required; revoking either one stops egress."
        )
    else:
        typer.echo(
            "This project's sessions now stay on the local, zero-egress "
            "naming backend regardless of CCDASH_LLM_EGRESS_CONSENT."
        )
