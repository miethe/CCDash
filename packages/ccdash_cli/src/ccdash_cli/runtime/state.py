"""Module-level shared state for global CLI options.

This module exists solely to break the circular import between ``main.py``
(which registers command sub-apps) and command modules (which need access
to the ``--target``, ``--output``, and ``--timeout`` values set by the root
callback).

Commands import from here instead of ``ccdash_cli.main``.
"""
from __future__ import annotations

import logging
import os

import typer

from ccdash_cli.formatters import OutputMode

_LOG = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_TIMEOUT_ENV_VAR = "CCDASH_TIMEOUT"

TARGET_FLAG: str | None = None
OUTPUT_MODE: OutputMode = OutputMode.human
TIMEOUT_SECONDS: float = _DEFAULT_TIMEOUT
TIMEOUT_SOURCE: str = "default"


def resolve_timeout(flag_value: float | None) -> tuple[float, str]:
    """Resolve the effective HTTP timeout from flag, env var, or built-in default.

    Precedence (highest to lowest): CLI ``--timeout`` flag > ``CCDASH_TIMEOUT``
    env var > 30.0 s built-in default.

    Args:
        flag_value: Value passed via ``--timeout``, or ``None`` if not provided.

    Returns:
        Tuple of ``(timeout_seconds, source)`` where *source* is one of
        ``"flag"``, ``"env"``, or ``"default"``.

    Raises:
        typer.BadParameter: When *flag_value* is non-positive (hard error —
            the user explicitly passed a bad value).
    """
    if flag_value is not None:
        if flag_value <= 0:
            raise typer.BadParameter(
                f"--timeout must be a positive number, got {flag_value}",
                param_hint="'--timeout'",
            )
        return flag_value, "flag"

    env_raw = os.environ.get(_TIMEOUT_ENV_VAR)
    if env_raw is not None:
        try:
            env_val = float(env_raw)
        except ValueError:
            _LOG.warning(
                "%s=%r is not a valid number; falling back to default timeout of %.1fs",
                _TIMEOUT_ENV_VAR,
                env_raw,
                _DEFAULT_TIMEOUT,
            )
            return _DEFAULT_TIMEOUT, "default"

        if env_val <= 0:
            _LOG.warning(
                "%s=%r is not positive; falling back to default timeout of %.1fs",
                _TIMEOUT_ENV_VAR,
                env_raw,
                _DEFAULT_TIMEOUT,
            )
            return _DEFAULT_TIMEOUT, "default"

        return env_val, "env"

    return _DEFAULT_TIMEOUT, "default"
