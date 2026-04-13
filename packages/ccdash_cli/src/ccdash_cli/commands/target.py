"""Target management sub-commands for the CCDash standalone CLI.

Commands in this module manage named CCDash server targets stored in the
local TOML config (``~/.config/ccdash/config.toml``).  Targets encapsulate
a server URL, optional bearer-token reference, and optional project slug.
"""
from __future__ import annotations

import getpass

import typer

from ccdash_cli.runtime.config import ConfigStore, set_token

target_app = typer.Typer(help="Manage CCDash server targets.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@target_app.command("list")
def target_list() -> None:
    """List all configured targets, indicating the active one."""
    store = ConfigStore()
    targets = store.list_targets()
    active_name = store.get_active_target_name()

    if not targets:
        typer.echo("No targets configured.")
        typer.echo(
            "Add one with: ccdash target add <name> <url>"
        )
        return

    # Column widths — compute dynamically from content.
    col_name = max(len("Name"), *(len(n) for n in targets))
    col_url = max(len("URL"), *(len(r.get("url", "")) for r in targets.values()))
    col_ref = max(
        len("Token Ref"),
        *(len(r.get("token_ref", "") or "") for r in targets.values()),
    )
    col_proj = max(
        len("Project"),
        *(len(r.get("project", "") or "") for r in targets.values()),
    )

    header = (
        f"{'':2}{'Name':<{col_name}}  {'URL':<{col_url}}  "
        f"{'Token Ref':<{col_ref}}  {'Project':<{col_proj}}  Active"
    )
    separator = "-" * len(header)

    typer.echo(header)
    typer.echo(separator)

    for name, record in targets.items():
        active_marker = "*" if name == active_name else " "
        url = record.get("url", "")
        token_ref = record.get("token_ref") or ""
        project = record.get("project") or ""
        typer.echo(
            f"{active_marker} {name:<{col_name}}  {url:<{col_url}}  "
            f"{token_ref:<{col_ref}}  {project:<{col_proj}}  {active_marker}"
        )


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@target_app.command("add")
def target_add(
    name: str = typer.Argument(..., help="Unique name for this target."),
    url: str = typer.Argument(..., help="Base URL of the CCDash server."),
    token_ref: str | None = typer.Option(
        None, "--token-ref", help="Keyring reference for the bearer token."
    ),
    project: str | None = typer.Option(
        None, "--project", help="Default project slug for this target."
    ),
) -> None:
    """Add a new named target (or replace an existing one)."""
    store = ConfigStore()
    store.add_target(name, url, token_ref=token_ref, project=project)
    typer.echo(f"Target '{name}' saved ({url}).")
    if token_ref:
        typer.echo(
            f"  Token ref: {token_ref!r}. "
            "Store the token with: ccdash target set-token {name}"
        )


# ---------------------------------------------------------------------------
# use
# ---------------------------------------------------------------------------


@target_app.command("use")
def target_use(
    name: str = typer.Argument(..., help="Name of the target to activate."),
) -> None:
    """Set the active target."""
    store = ConfigStore()
    record = store.get_target(name)
    if record is None:
        typer.echo(
            f"Error: target '{name}' not found. "
            f"Add it with: ccdash target add {name} <url>",
            err=True,
        )
        raise typer.Exit(code=1)
    store.set_active_target(name)
    typer.echo(f"Active target set to '{name}'.")


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


@target_app.command("remove")
def target_remove(
    name: str = typer.Argument(..., help="Name of the target to remove."),
) -> None:
    """Remove a named target."""
    store = ConfigStore()
    removed = store.remove_target(name)
    if removed:
        typer.echo(f"Target '{name}' removed.")
    else:
        typer.echo(f"Error: target '{name}' not found.", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# set-token
# ---------------------------------------------------------------------------


@target_app.command("set-token")
def target_set_token(
    name: str = typer.Argument(..., help="Name of the target to set a token for."),
) -> None:
    """Store a bearer token for a target in the system keyring.

    Prompts for the token interactively without echoing to the terminal.
    """
    store = ConfigStore()
    record = store.get_target(name)
    if record is None:
        typer.echo(f"Error: target '{name}' not found.", err=True)
        raise typer.Exit(code=1)

    token_ref: str | None = record.get("token_ref")
    if not token_ref:
        typer.echo(
            f"Error: target '{name}' has no token_ref. "
            f"Add one with: ccdash target add {name} <url> --token-ref <ref>",
            err=True,
        )
        raise typer.Exit(code=1)

    token_value = getpass.getpass(f"Bearer token for '{name}' (token_ref={token_ref!r}): ")
    if not token_value:
        typer.echo("Error: empty token not stored.", err=True)
        raise typer.Exit(code=1)

    try:
        set_token(token_ref, token_value)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Token for '{name}' stored in keyring under ref '{token_ref}'.")
