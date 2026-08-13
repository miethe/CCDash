"""Workspace-token provisioning commands (ADR-008 §Migration Path).

``ccdash token mint`` is the operator entry point for minting a workspace-scoped
bearer token, replacing the deprecated
``python -m backend.scripts.migrate_bearer_to_workspace_token`` script. Both now
call the same backend-aware
``backend.application.services.auth.token_provisioning.provision_workspace_token``.

This is the repo-local ``ccdash`` CLI, which has direct DB access via
``runtime.bootstrap_cli`` — the right home for a bootstrap write like minting the
first token. The standalone pipx ``ccdash-cli`` is HTTP-only and deliberately does
not carry this command: minting the first token is the bootstrap that has no token
to authenticate an HTTP call with yet.

Security note: the plaintext token is read from ``--token`` or, preferably, the
``CCDASH_AUTH_TOKEN`` env var. The token is NEVER echoed back — only its
``token_id`` and scope are printed.
"""
from __future__ import annotations

import json
import os

import typer

from backend.application.services.auth.token_provisioning import (
    SchemaNotReadyError,
    provision_workspace_token,
)
from backend.cli import runtime

token_app = typer.Typer(help="Workspace-token provisioning.", no_args_is_help=True)


@token_app.command("mint")
def mint(
    project: str = typer.Option(
        ..., "--project", help="Project ID the token is scoped to."
    ),
    token: str = typer.Option(
        "",
        "--token",
        help=(
            "Plaintext bearer token. Defaults to the CCDASH_AUTH_TOKEN env var; "
            "prefer the env var so the secret is not in shell history."
        ),
    ),
    workspace: str = typer.Option(
        "default-local", "--workspace", help="Workspace ID (default: default-local)."
    ),
    scope: str = typer.Option("admin", "--scope", help="Token scope (default: admin)."),
    description: str = typer.Option(
        "Provisioned workspace token",
        "--description",
        help="Human-readable description stored on the row.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    """Mint (or confirm) a workspace-scoped bearer token.

    Idempotent: re-running with the same plaintext token is a no-op that reports
    the existing token_id. Aborts with a clear message (never runs migrations) if
    the schema is not yet provisioned.
    """
    resolved_token = token or os.environ.get("CCDASH_AUTH_TOKEN", "")
    if not resolved_token:
        typer.echo(
            "ERROR: no token supplied. Pass --token or set CCDASH_AUTH_TOKEN.",
            err=True,
        )
        raise typer.Exit(code=1)

    async def _run():
        container = await runtime.bootstrap_cli()
        try:
            return await provision_workspace_token(
                container.db,
                token=resolved_token,
                workspace_id=workspace,
                project_id=project,
                description=description,
                scope=scope,
            )
        finally:
            await runtime.shutdown_cli()

    try:
        result = runtime.run_async(_run())
    except SchemaNotReadyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "created": result.created,
                    "tokenId": result.token_id,
                    "workspaceId": result.workspace_id,
                    "projectId": result.project_id,
                    "scope": result.scope,
                }
            )
        )
        return

    if result.created:
        typer.echo(f"SUCCESS: minted token_id={result.token_id}")
    else:
        typer.echo(
            f"NO-OP: token already present as token_id={result.token_id}"
        )
    typer.echo(f"  workspace_id = {result.workspace_id}")
    typer.echo(f"  project_id   = {result.project_id}")
    typer.echo(f"  scope        = {result.scope}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  export CCDASH_AUTH_TOKEN=<your-token>   # keep the same plaintext")
    typer.echo("  export CCDASH_PROFILE=api               # activate WorkspaceTokenAuthBackend")
    typer.echo("  # restart the server")
    typer.echo("  # verify: GET /api/health -> auth_mode == 'workspace_token'")
