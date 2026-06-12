#!/usr/bin/env python3
"""CCDash launch-time capture writer — Claude Code SessionStart hook.

Reads the SessionStart hook JSON payload from stdin (fields: ``session_id``,
``transcript_path``), reads the CCDASH_LAUNCH_* env contract, and writes a
co-located ``<session-id>.capture.json`` sidecar next to the session JSONL.

Fail-open contract
------------------
* All work is wrapped in a single top-level try/except.
* The process ALWAYS exits 0 — it must never block or abort a Claude launch.
* Any error → no sidecar written (session simply carries null capture fields).
* No blocking stdout output is ever emitted.

Schema (schemaVersion=1)
------------------------
{
  "schemaVersion": 1,
  "sessionId": "<uuid>",
  "launcher": "<str|null>",
  "profile": "<str|null>",
  "effortTier": "<str|null>",
  "modelVariant": "<str|null>",
  "capturedAt": "<ISO-8601 UTC|null>"
}

All non-schemaVersion/sessionId fields are nullable.
Unknown / unset env vars → null, NEVER defaulted.

Operator installation (do NOT apply these automatically — T11-008 documents it)
----------------------------------------------------------------------------------
# 1. Add to ~/ica-claude.sh (before the `exec` line):
#    export CCDASH_LAUNCH_PROFILE=ica-delegate
#    export CCDASH_LAUNCHER=ica-claude.sh
#    export CCDASH_LAUNCH_MODEL="$ANTHROPIC_MODEL"   # best-effort
#    # CCDASH_LAUNCH_EFFORT — only set when the effort tier is known (e.g. Ultracode)
#
# 2. Register hook in ~/.claude/settings.json AND ~/.claude/ica-settings.json
#    (add in both, or in a shared user-global block both files inherit):
#
#    {
#      "hooks": {
#        "SessionStart": [
#          {
#            "matcher": "",
#            "hooks": [
#              {
#                "type": "command",
#                "command": "python3 /path/to/CCDash/scripts/hooks/ccdash_capture_session_start.py"
#              }
#            ]
#          }
#        ]
#      }
#    }
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ccdash.hooks.capture_session_start")

# ---------------------------------------------------------------------------
# Public API (importable — used directly by tests)
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1
_FALLBACK_CAPTURE_DIR = "data/capture"


def _nullable_str(env: dict, key: str) -> Optional[str]:
    """Return stripped env value or None — never default."""
    raw = env.get(key)
    if raw is None:
        return None
    stripped = str(raw).strip()
    return stripped if stripped else None


def _resolve_sidecar_path(
    session_id: str,
    transcript_path: Optional[str],
    *,
    fallback_base: Optional[Path] = None,
) -> Optional[Path]:
    """Derive the sidecar output path.

    Primary: co-located sibling of the transcript JSONL, derived via
    ``path.with_name(f"{stem}.capture.json")``.

    Fallback (used when *transcript_path* is absent): a directory under the
    CCDash data dir, resolved relative to *fallback_base* (default: ``Path.cwd()``).
    """
    sidecar_name = f"{session_id}.capture.json"

    if transcript_path:
        tp = Path(transcript_path).expanduser()
        return tp.with_name(sidecar_name)

    # Fallback: data/capture/<session-id>.capture.json relative to repo root
    base = fallback_base if fallback_base is not None else Path.cwd()
    return base / _FALLBACK_CAPTURE_DIR / sidecar_name


def write_capture_sidecar(
    payload: dict[str, Any],
    env: dict[str, str],
    *,
    fallback_base: Optional[Path] = None,
) -> Optional[Path]:
    """Write the capture sidecar JSON for a SessionStart event.

    Parameters
    ----------
    payload:
        The JSON object delivered on the hook's stdin.  Expected fields:
        ``session_id`` (str) and ``transcript_path`` (str, optional).
    env:
        The environment mapping to read ``CCDASH_LAUNCH_*`` vars from.
        Typically ``os.environ``.
    fallback_base:
        If supplied, used as the root for the fallback
        ``data/capture/<sid>.capture.json`` path when *transcript_path* is
        absent.  Defaults to ``Path.cwd()`` inside the function.

    Returns
    -------
    Path
        The path of the written sidecar file on success.
    None
        If the sidecar could not be written (missing session_id, unwritable
        location, serialisation error, etc.).

    Raises
    ------
    Never.  All exceptions are caught and result in a ``None`` return.
    """
    try:
        session_id: Optional[str] = None
        raw_sid = payload.get("session_id") or payload.get("sessionId")
        if raw_sid:
            session_id = str(raw_sid).strip() or None

        if not session_id:
            logger.debug("ccdash_capture: no session_id in payload — skipping")
            return None

        transcript_path: Optional[str] = (
            payload.get("transcript_path") or payload.get("transcriptPath")
        )

        sidecar_path = _resolve_sidecar_path(
            session_id,
            transcript_path,
            fallback_base=fallback_base,
        )
        if sidecar_path is None:
            logger.debug("ccdash_capture: could not resolve sidecar path — skipping")
            return None

        # Build the sidecar document — strict no-default rule
        try:
            captured_at: Optional[str] = (
                datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        except Exception:
            captured_at = None

        sidecar: dict[str, Any] = {
            "schemaVersion": _SCHEMA_VERSION,
            "sessionId": session_id,
            "launcher": _nullable_str(env, "CCDASH_LAUNCHER"),
            "profile": _nullable_str(env, "CCDASH_LAUNCH_PROFILE"),
            "effortTier": _nullable_str(env, "CCDASH_LAUNCH_EFFORT"),
            "modelVariant": _nullable_str(env, "CCDASH_LAUNCH_MODEL"),
            "capturedAt": captured_at,
        }

        # Ensure parent directory exists
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)

        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        logger.debug("ccdash_capture: wrote sidecar → %s", sidecar_path)
        return sidecar_path

    except Exception as exc:  # noqa: BLE001
        logger.debug("ccdash_capture: error writing sidecar (ignored): %s", exc)
        return None


# ---------------------------------------------------------------------------
# __main__ stdin entrypoint — invoked by Claude Code as the hook command
# ---------------------------------------------------------------------------

def _main() -> None:
    """Read SessionStart JSON payload from stdin and write the capture sidecar.

    Always exits 0 — fail-open contract.
    """
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            # Empty payload — nothing to capture; not an error
            sys.exit(0)

        payload = json.loads(raw_input)
        write_capture_sidecar(payload, dict(os.environ))
    except Exception as exc:  # noqa: BLE001
        # Log to stderr only (not stdout) so it does not pollute hook output
        logger.debug("ccdash_capture: unhandled error in __main__ (ignored): %s", exc)

    sys.exit(0)


if __name__ == "__main__":
    _main()
