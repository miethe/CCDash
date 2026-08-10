"""Provider dimension commands (provider-channel-credential-entities-v1, M2).

Provides:

- ``ccdash provider backfill`` -- an on-demand, idempotent backfill of the
  ``provider_dimensions`` / ``provider_channels`` / ``provider_credentials``
  tables from the active project's ``sessions`` rows. This is the same
  operation the sync engine runs automatically every pass (see
  ``backend.db.sync_engine.SyncEngine.sync_project``'s phase-1 block); this
  command exists so an operator can trigger it on demand -- e.g. right after
  this milestone ships, to populate the tables for sessions ingested before
  the backfill existed -- without waiting for or forcing a full filesystem
  sync.
- ``ccdash provider declare-rotation`` -- the operator entry point for the
  M2 rotation-declare path: explicitly records that one credential was
  rotated FROM another on a given channel, by setting
  ``provider_credentials.rotated_from_id`` (+ ``rotation_declared_at`` /
  ``rotation_declared_by``). Nothing is inferred; the operator names both
  sides. ``provider_credentials`` is not project-scoped, so this command does
  not resolve a project.

The actual derivation/upsert/validation logic lives entirely in
``backend.db.repositories.provider_dimensions`` (``SqliteProviderDimensionsRepository``
/ ``PostgresProviderDimensionsRepository``, selected via
``get_provider_dimensions_repository``) -- this module is CLI plumbing only
(project resolution where relevant, output formatting, exit codes).
"""
from __future__ import annotations

import getpass
import json

import typer

from backend.application.services.agent_queries._filters import resolve_project_scope
from backend.cli import runtime
from backend.db.repositories.provider_dimensions import get_provider_dimensions_repository

provider_app = typer.Typer(help="Provider dimension commands.", no_args_is_help=True)


@provider_app.command("backfill")
def backfill(
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON stats."),
) -> None:
    """Backfill provider_dimensions/provider_channels/provider_credentials from sessions.

    Scans every ``sessions`` row for the active project (or ``--project``
    override), derives provider identity via
    ``backend.model_identity.derive_provider_identity``, and idempotently
    upserts the three provider dimension tables. Safe to run repeatedly: a
    repeat pass against an unchanged ``sessions`` table reports 0 newly
    inserted rows on every table.

    Works against both database backends -- SQLite and Postgres -- via
    ``get_provider_dimensions_repository``, which picks the correct
    implementation for ``container.db``'s connection type.

    Exit codes: 0 success, 1 unexpected error, 2 project could not be resolved.
    """

    async def _run() -> dict[str, int]:
        container = await runtime.bootstrap_cli()
        try:
            context, ports = await runtime.get_app_request(container)
            scope = resolve_project_scope(context, ports, runtime.PROJECT_OVERRIDE)
            if scope is None:
                raise LookupError(runtime.project_resolution_error_message())
            repo = get_provider_dimensions_repository(container.db)
            return await repo.backfill_provider_dimensions_from_sessions(scope.project.id)
        finally:
            await runtime.shutdown_cli()

    try:
        stats = runtime.run_async(_run())
    except LookupError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(stats, indent=2))
        return

    typer.echo("Provider dimension backfill complete:")
    for key, value in stats.items():
        typer.echo(f"  {key}: {value}")


@provider_app.command("declare-rotation")
def declare_rotation(
    channel: str = typer.Option(
        ..., "--channel", help="The provider_channels channel both credentials belong to."
    ),
    predecessor_credential_name: str = typer.Option(
        ...,
        "--from",
        help="The OLD credential name that was rotated away from (the predecessor).",
    ),
    successor_credential_name: str = typer.Option(
        ...,
        "--to",
        help="The NEW credential name that was rotated to (the successor).",
    ),
    declared_by: str = typer.Option(
        "",
        "--declared-by",
        help="Operator identity to record on rotation_declared_by. Defaults to the "
        "local OS username if omitted.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON result."),
) -> None:
    """Declare that --to was rotated FROM --from on --channel.

    Sets ``provider_credentials.rotated_from_id`` (+ ``rotation_declared_at`` /
    ``rotation_declared_by``) on the successor (--to) credential, pointing at
    the predecessor (--from) credential. Nothing is inferred -- both sides
    must be named explicitly, and both must already exist as
    ``provider_credentials`` rows (e.g. via a prior sync pass or
    ``ccdash provider backfill``).

    Idempotent: re-running with the exact same --from/--to is a no-op
    success. Re-running with a DIFFERENT --from over an already-declared --to
    is rejected (exit code 2) rather than silently overwriting a recorded
    decision. A cycle (declaring a rotation that would make the chain loop
    back on itself) is also rejected (exit code 2).

    Example:
        ccdash provider declare-rotation --channel ica --from CC1 --to CC2

    Exit codes: 0 success (including idempotent no-op), 1 unexpected error,
    2 validation error (missing credential, self-reference, cycle, or
    conflicting re-declare).
    """
    resolved_declared_by = declared_by or _default_declared_by()

    async def _run() -> None:
        container = await runtime.bootstrap_cli()
        try:
            repo = get_provider_dimensions_repository(container.db)
            await repo.declare_rotation(
                channel=channel,
                predecessor_credential_name=predecessor_credential_name,
                successor_credential_name=successor_credential_name,
                declared_by=resolved_declared_by,
            )
        finally:
            await runtime.shutdown_cli()

    try:
        runtime.run_async(_run())
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = {
        "channel": channel,
        "predecessorCredentialName": predecessor_credential_name,
        "successorCredentialName": successor_credential_name,
        "declaredBy": resolved_declared_by,
        "status": "declared",
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return

    typer.echo(
        f"Declared rotation: channel={channel!r} "
        f"{successor_credential_name!r} <- rotated from {predecessor_credential_name!r} "
        f"(declared_by={resolved_declared_by!r})"
    )


def _default_declared_by() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""
