"""Root Typer app for standalone CCDash CLI."""
from __future__ import annotations

import typer

app = typer.Typer(
    help="CCDash CLI — project intelligence from any terminal.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show CLI version."""
    from importlib.metadata import version as pkg_version
    try:
        ver = pkg_version("ccdash-cli")
    except Exception:
        ver = "0.1.0-dev"
    typer.echo(f"ccdash-cli {ver}")
