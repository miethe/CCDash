"""Doctor command — diagnose CLI configuration and server connectivity.

Running ``ccdash doctor`` (or ``ccdash doctor check``) prints a structured
summary of the resolved target, token status, and live server health.
"""
from __future__ import annotations

import typer

from ccdash_cli.runtime.client import CCDashClient, CCDashClientError, ConnectionError
from ccdash_cli.runtime.config import resolve_target

doctor_app = typer.Typer(help="Diagnose CLI configuration and server connectivity.")

# Styles used throughout the output.
_PASS = typer.style("PASS", fg=typer.colors.GREEN, bold=True)
_FAIL = typer.style("FAIL", fg=typer.colors.RED, bold=True)
_WARN = typer.style("WARN", fg=typer.colors.YELLOW, bold=True)
_INFO = typer.style("INFO", fg=typer.colors.CYAN)


def _label(text: str) -> str:
    """Return a right-padded label string for aligned output."""
    return f"  {text:<22}"


@doctor_app.callback(invoke_without_command=True)
def doctor_check(
    ctx: typer.Context,
    target_flag: str | None = typer.Option(None, "--target", help="Named target to check."),
) -> None:
    """Check CLI configuration and server connectivity.

    When invoked as ``ccdash doctor`` with no sub-command this runs the full
    diagnostic sequence automatically.
    """
    # Only run when invoked directly (not when a sub-command is dispatched).
    if ctx.invoked_subcommand is not None:
        return

    typer.echo(typer.style("CCDash CLI Doctor", bold=True))
    typer.echo("=" * 40)

    # --- Resolve target ---
    try:
        # Import here to read the module-level TARGET_FLAG set by the root callback.
        from ccdash_cli import main as app_state

        effective_flag = target_flag or app_state.TARGET_FLAG
        target = resolve_target(target_flag=effective_flag)
    except SystemExit:
        # resolve_target already printed the error; propagate the exit.
        raise

    typer.echo(f"\n{typer.style('Target', bold=True)}")
    typer.echo(f"{_label('Name:')}{target.name}")
    typer.echo(f"{_label('URL:')}{target.url}")

    if target.is_implicit_local:
        typer.echo(
            f"{_label('Source:')}"
            + typer.style("implicit local default", fg=typer.colors.YELLOW)
        )
    else:
        typer.echo(f"{_label('Source:')}{target.name} (from config)")

    if target.project:
        typer.echo(f"{_label('Project:')}{target.project}")

    if target.token:
        token_status = typer.style("present", fg=typer.colors.GREEN)
    else:
        token_status = typer.style("not set (unauthenticated)", fg=typer.colors.YELLOW)
    typer.echo(f"{_label('Auth token:')}{token_status}")

    # --- Server connectivity ---
    typer.echo(f"\n{typer.style('Server', bold=True)}")

    client = CCDashClient(target.url, token=target.token)
    try:
        instance = client.get_instance()
        typer.echo(f"{_label('Reachable:')}{_PASS}")
        typer.echo(f"{_label('Instance ID:')}{instance.instance_id or '—'}")
        typer.echo(f"{_label('Server version:')}{instance.version or '—'}")
        typer.echo(f"{_label('Environment:')}{instance.environment or '—'}")
        if instance.capabilities:
            caps = ", ".join(sorted(instance.capabilities))
            typer.echo(f"{_label('Capabilities:')}{caps}")
        else:
            typer.echo(f"{_label('Capabilities:')}—")
    except ConnectionError as exc:
        typer.echo(f"{_label('Reachable:')}{_FAIL}")
        typer.echo(
            f"\n  {typer.style('Connection error:', fg=typer.colors.RED)} {exc.message}"
        )
        typer.echo(
            f"\n  Verify the server is running and the URL is correct:\n"
            f"    {target.url}"
        )
    except CCDashClientError as exc:
        # Server is reachable but returned an error (auth, etc.).
        typer.echo(
            f"{_label('Reachable:')}"
            + typer.style("UP (with error)", fg=typer.colors.YELLOW)
        )
        typer.echo(
            f"\n  {typer.style('Server error:', fg=typer.colors.YELLOW)} {exc.message}"
        )
        if exc.exit_code == 2:  # AuthenticationError
            typer.echo(
                "  Hint: store a token with: "
                f"ccdash target set-token {target.name}"
            )
    finally:
        client.close()

    typer.echo("")
