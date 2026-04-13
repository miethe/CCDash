"""Target management sub-commands for the CCDash standalone CLI.

Commands in this module manage named CCDash server targets stored in the
local TOML config (``~/.config/ccdash/config.toml``).  Targets encapsulate
a server URL, optional bearer-token reference, and optional project slug.
"""
from __future__ import annotations

import getpass

import typer

from ccdash_cli.runtime.config import ConfigStore, resolve_target, set_token

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
# show
# ---------------------------------------------------------------------------


@target_app.command("show")
def target_show(
    name: str | None = typer.Argument(
        None,
        help="Optional target name. Defaults to the resolved active target.",
    ),
) -> None:
    """Show the resolved target configuration used by CLI commands."""
    store = ConfigStore()
    target = resolve_target(target_flag=name, config_store=store)
    record = store.get_target(target.name) or {}
    token_ref = record.get("token_ref")

    if token_ref:
        auth_state = (
            f"token ref {token_ref!r} (token loaded)"
            if target.token
            else f"token ref {token_ref!r} (no token resolved)"
        )
    elif target.token:
        auth_state = "token loaded from environment"
    else:
        auth_state = "not configured"

    source = "implicit local fallback" if target.is_implicit_local else "configured target"

    typer.echo(f"Name: {target.name}")
    typer.echo(f"URL: {target.url}")
    typer.echo(f"Project: {target.project or '-'}")
    typer.echo(f"Authentication: {auth_state}")
    typer.echo(f"Source: {source}")


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


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


@target_app.command("login")
def target_login(
    name: str = typer.Argument(..., help="Name of the target to authenticate."),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Bearer token to store. Prompted interactively if not provided.",
    ),
) -> None:
    """Store a bearer token for a target using the conventional token ref.

    The token is saved to the OS keyring under the key ``target:<name>``.
    If no keyring backend is available, you can instead set the
    ``CCDASH_TOKEN`` environment variable.
    """
    store = ConfigStore()
    record = store.get_target(name)
    if record is None:
        typer.echo(
            f"Error: target '{name}' not found. "
            f"Add it with: ccdash target add {name} <url>",
            err=True,
        )
        raise typer.Exit(code=1)

    token_value: str = token or typer.prompt(
        f"Bearer token for '{name}'", hide_input=True
    )
    if not token_value:
        typer.echo("Error: empty token not stored.", err=True)
        raise typer.Exit(code=1)

    token_ref = f"target:{name}"

    try:
        set_token(token_ref, token_value)
    except RuntimeError as exc:
        typer.echo(
            f"Error: {exc}\n"
            f"Tip: set the CCDASH_TOKEN environment variable to authenticate "
            f"without a keyring backend.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    # Persist the token_ref back to the target record so resolution picks it up.
    config = store.load()
    config.setdefault("targets", {}).setdefault(name, {})["token_ref"] = token_ref
    store.save(config)

    typer.echo(
        f"Logged in to '{name}'. Token stored in keyring under ref '{token_ref}'."
    )


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


@target_app.command("logout")
def target_logout(
    name: str = typer.Argument(..., help="Name of the target to deauthenticate."),
) -> None:
    """Remove the stored bearer token for a target.

    Clears the keyring entry (if one exists) and removes the ``token_ref``
    from the target record so the target will no longer send credentials.
    """
    store = ConfigStore()
    record = store.get_target(name)
    if record is None:
        typer.echo(
            f"Error: target '{name}' not found.",
            err=True,
        )
        raise typer.Exit(code=1)

    token_ref: str | None = record.get("token_ref")
    if not token_ref:
        typer.echo(f"No stored credentials for target '{name}'.")
        return

    # Attempt to remove the keyring entry (lazy import — may not be installed).
    try:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password("ccdash", token_ref)
        except keyring.errors.PasswordDeleteError:
            # Entry was not in the keyring — still remove from config below.
            pass
        except keyring.errors.NoKeyringError:
            pass
    except ImportError:
        pass

    # Remove token_ref from the persisted target record.
    config = store.load()
    target_record: dict = config.get("targets", {}).get(name, {})
    target_record.pop("token_ref", None)
    config.setdefault("targets", {})[name] = target_record
    store.save(config)

    typer.echo(f"Logged out of '{name}'. Credentials removed.")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


@target_app.command("check")
def target_check(
    name: str = typer.Argument(..., help="Name of the target to check."),
) -> None:
    """Probe a target's reachability and authentication status.

    Attempts to connect to the CCDash instance and reports whether:
    - The server is reachable
    - The stored credentials (if any) are accepted
    """
    from ccdash_cli.runtime.client import (
        AuthenticationError,
        CCDashClient,
        CCDashClientError,
    )

    store = ConfigStore()
    record = store.get_target(name)
    if record is None:
        typer.echo(
            f"Error: target '{name}' not found. "
            f"Add it with: ccdash target add {name} <url>",
            err=True,
        )
        raise typer.Exit(code=1)

    target = resolve_target(target_flag=name, config_store=store)

    typer.echo(f"Checking target '{name}' at {target.url} ...")

    with CCDashClient(target.url, token=target.token) as client:
        # Step 1: basic connectivity via check_health (swallows ConnectionError).
        reachable = client.check_health()
        if not reachable:
            typer.echo("  Connection: FAILED (server unreachable)")
            raise typer.Exit(code=4)

        typer.echo("  Connection: OK")

        # Step 2: authenticated instance probe to validate credentials.
        try:
            meta = client.get_instance()
            typer.echo("  Auth:       OK")
            instance_label = meta.instance_id or name
            env_label = f"  env={meta.environment}" if meta.environment else ""
            typer.echo(
                f"  Instance:   {instance_label}"
                f"  (version {meta.version or 'unknown'}{env_label})"
            )
        except AuthenticationError:
            typer.echo(
                "  Auth:       FAILED (HTTP 401 — invalid or missing bearer token)\n"
                f"  Tip: run 'ccdash target login {name}' to store credentials.",
                err=True,
            )
            raise typer.Exit(code=2)
        except CCDashClientError as exc:
            typer.echo(f"  Auth:       ERROR — {exc.message}", err=True)
            raise typer.Exit(code=exc.exit_code)
