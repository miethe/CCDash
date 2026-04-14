"""Module-level shared state for global CLI options.

This module exists solely to break the circular import between ``main.py``
(which registers command sub-apps) and command modules (which need access
to the ``--target`` and ``--output`` values set by the root callback).

Commands import from here instead of ``ccdash_cli.main``.
"""
from __future__ import annotations

from ccdash_cli.formatters import OutputMode

TARGET_FLAG: str | None = None
OUTPUT_MODE: OutputMode = OutputMode.human
