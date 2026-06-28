"""CCDash local ingest daemon package.

Exports
-------
run_daemon
    Async entrypoint that runs the tail-and-flush daemon loop until cancelled.
"""
from __future__ import annotations

from ccdash_cli.daemon.runner import run_daemon

__all__ = ["run_daemon"]
