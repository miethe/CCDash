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

Schema (schemaVersion=3)
------------------------
{
  "schemaVersion": 3,
  "sessionId": "<uuid>",
  "launcher": "<str|null>",
  "profile": "<str|null>",
  "effortTier": "<str|null>",
  "effortTierSource": "<'launch_env'|'claude_settings'|null>",
  "modelVariant": "<str|null>",
  "icaKey": "<str|null>",          # ICA key NAME (CC1..CC6), never secret bytes
  "icaSpendStart": "<str|null>",   # raw x-litellm-key-spend at session start
  "icaSpendEnd": "<str|null>",     # raw x-litellm-key-spend at session end
  "capturedAt": "<ISO-8601 UTC|null>"
}

All non-schemaVersion/sessionId fields are nullable.
Unknown / unset env vars → null, NEVER defaulted.

``icaKey`` / ``icaSpend*`` (v51) carry the two dimensions this sidecar could not
before: WHICH ICA key ran the session and how many dollars it cost. ``icaKey`` is
the key NAME from ``CCDASH_LAUNCH_ICA_KEY`` (never a token). ``icaSpendStart`` /
``icaSpendEnd`` are the raw cumulative-per-key ``x-litellm-key-spend`` header,
read via a strictly-gated, fail-open 1-token gateway probe on SessionStart /
SessionEnd respectively (the ICA gateway exposes spend only on that response
header — no admin endpoint). The attributable delta and its reason token are NOT
computed here; CCDash derives them post-ingest in ``backfill_ica_spend_attribution``
where the cross-session ledger is available (vocab: backend/parsers/ica_spend.py).
The probe reads the auth token from env to authorize the call but NEVER writes,
logs, or stores any token bytes.

``effortTierSource`` (Gap 4) records WHICH lane supplied ``effortTier`` so a
rollup can tell explicit launcher intent from a possibly-stale settings
snapshot.  It is non-null iff ``effortTier`` is non-null.  The two literals are
repeated here rather than imported: this script runs as a bare ``python3`` hook
with no guarantee that CCDash's venv (or the repo itself) is importable.  The
canonical definitions live in ``backend/parsers/effort_provenance.py`` and
``backend/tests/test_effort_tier_source_provenance.py`` asserts they match.

schemaVersion history: v1 omitted ``effortTierSource``; v3 (v51) added
``icaKey`` / ``icaSpendStart`` / ``icaSpendEnd``.  The reader accepts v1, v2, and
v3, so sidecars already on disk keep parsing (older ones carry null for the newer
fields).

Operator installation (do NOT apply these automatically — T11-008 documents it)
----------------------------------------------------------------------------------
# 1. Add to ~/ica-claude.sh (before the `exec` line):
#    export CCDASH_LAUNCH_PROFILE=ica-delegate
#    export CCDASH_LAUNCHER=ica-claude.sh
#    export CCDASH_LAUNCH_MODEL="$ANTHROPIC_MODEL"   # best-effort
#    export CCDASH_LAUNCH_ICA_KEY="${ICA_KEY:-}"     # key NAME (CC1..CC6); empty → null
#    # CCDASH_LAUNCH_EFFORT — only set when the effort tier is known (e.g. Ultracode)
#
# 2. Register hook in ~/.claude/settings.json AND ~/.claude/ica-settings.json
#    for BOTH SessionStart and SessionEnd (the same script handles both; the end
#    event supplies the closing spend reading). Add in both files, or a shared
#    user-global block both inherit:
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
#        ],
#        "SessionEnd": [
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

_SCHEMA_VERSION = 3
_FALLBACK_CAPTURE_DIR = "data/capture"

# Gap 4 provenance tokens for effortTier.  MUST stay identical to
# EFFORT_SOURCE_LAUNCH_ENV / EFFORT_SOURCE_CLAUDE_SETTINGS in
# backend/parsers/effort_provenance.py (asserted by
# backend/tests/test_effort_tier_source_provenance.py).  Duplicated as literals
# because this hook must run without importing the backend package.
_EFFORT_SOURCE_LAUNCH_ENV = "launch_env"
_EFFORT_SOURCE_CLAUDE_SETTINGS = "claude_settings"

# ── ICA key identity + spend probe (v51) ────────────────────────────────────
# The launcher exports CCDASH_LAUNCH_ICA_KEY=<name> (CC1..CC6) — the ICA key
# NAME, never the secret. Unset/empty → null (never defaulted to CC1).
_ICA_KEY_ENV = "CCDASH_LAUNCH_ICA_KEY"

# The ICA gateway reports a cumulative-per-key dollar total on the
# ``x-litellm-key-spend`` response header of every /v1/messages response. There
# is no admin/read endpoint (probed: /key/info, /v1/key/info, /spend/logs all
# 404 on the ICA gateway 2026-08-10), so the only way to read spend is to make a
# 1-token message call and read the header off the response. This probe is:
#   * strictly gated — only fires for an ICA-launched session (an ICA key name
#     is present, or the launcher is ica-claude.sh) with a base URL + token;
#   * fail-open — any error/timeout returns None (session carries null spend);
#   * short-timeout — never blocks a launch for more than a few seconds;
#   * secret-safe — reads the token from env to authorize the call but NEVER
#     writes, logs, or returns any token bytes; only the numeric header is used.
_ICA_SPEND_HEADER = "x-litellm-key-spend"
_ICA_PROBE_TIMEOUT_SECONDS = 4.0


def _is_ica_session(env: dict) -> bool:
    """True when this session was launched through the ICA gateway."""
    if _nullable_str(env, _ICA_KEY_ENV):
        return True
    launcher = (_nullable_str(env, "CCDASH_LAUNCHER") or "").lower()
    if "ica" in launcher:
        return True
    base = (_nullable_str(env, "ANTHROPIC_BASE_URL") or "").lower()
    return "ica" in base and "ibm.com" in base


def _probe_key_spend(env: dict) -> Optional[str]:
    """Read the cumulative ``x-litellm-key-spend`` header via a 1-token probe.

    Returns the raw header string (verbatim, for exact storage) or ``None`` on
    any failure. Uses only the Python stdlib (urllib) — this hook runs as a bare
    ``python3`` with no guaranteed venv. Never raises; never emits token bytes.
    """
    if not _is_ica_session(env):
        return None
    base = _nullable_str(env, "ANTHROPIC_BASE_URL")
    token = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ICA_CLAUDE_CODE_API_KEY")
    if not base or not token:
        return None
    model = _nullable_str(env, "CCDASH_LAUNCH_MODEL") or "claude-haiku-4-5"
    # Strip a trailing model-variant marker like "[1m]" — the gateway rejects it
    # over raw HTTP (that suffix is a Claude-Code-layer convention, not a wire id).
    if "[" in model:
        model = model.split("[", 1)[0]
    url = base.rstrip("/") + "/v1/messages"
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        }
    ).encode("utf-8")
    try:
        import urllib.request as _u

        req = _u.Request(url, data=body, method="POST")
        req.add_header("content-type", "application/json")
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("authorization", f"Bearer {token}")
        with _u.urlopen(req, timeout=_ICA_PROBE_TIMEOUT_SECONDS) as resp:
            # Header names are case-insensitive per HTTPMessage.get.
            spend = resp.headers.get(_ICA_SPEND_HEADER)
    except Exception as exc:  # noqa: BLE001 — fail-open, never block a launch
        logger.debug("ccdash_capture: ICA spend probe failed (ignored): %s", exc)
        return None
    if spend is None:
        return None
    spend = str(spend).strip()
    return spend or None


def _is_session_end(payload: dict) -> bool:
    """True when the hook fired for a session-end event (SessionEnd / Stop)."""
    event = str(payload.get("hook_event_name") or payload.get("hookEventName") or "").strip()
    return event in ("SessionEnd", "Stop")


def _load_existing_sidecar(path: Optional[Path]) -> dict:
    """Best-effort read of an already-written sidecar (for start→end merge)."""
    if path is None:
        return {}
    try:
        if path.exists() and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        logger.debug("ccdash_capture: could not read existing sidecar (ignored): %s", exc)
    return {}


def _nullable_str(env: dict, key: str) -> Optional[str]:
    """Return stripped env value or None — never default."""
    raw = env.get(key)
    if raw is None:
        return None
    stripped = str(raw).strip()
    return stripped if stripped else None


def _settings_effort_level(env: dict, project_dir: Optional[Path]) -> Optional[str]:
    """Resolve a fallback ``effortTier`` from Claude Code settings files.

    Checked in precedence order (first non-empty string wins):

    1. ``<project_dir>/.claude/settings.local.json``
    2. ``<project_dir>/.claude/settings.json``
    3. ``$CLAUDE_CONFIG_DIR/settings.json`` if set and non-empty, else
       ``~/.claude/settings.json``

    Reads the top-level ``effortLevel`` key (written by the ``/effort`` slash
    command). Any missing/unreadable/malformed file, or a non-string value,
    is skipped (treated as absent) rather than raised — callers rely on this
    to never fail the sidecar write.
    """
    candidates: list[Path] = []
    if project_dir is not None:
        candidates.append(project_dir / ".claude" / "settings.local.json")
        candidates.append(project_dir / ".claude" / "settings.json")

    config_dir = _nullable_str(env, "CLAUDE_CONFIG_DIR")
    if config_dir:
        candidates.append(Path(config_dir).expanduser() / "settings.json")
    else:
        candidates.append(Path.home() / ".claude" / "settings.json")

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — malformed/unreadable file → skip, not fatal
            continue

        if not isinstance(data, dict):
            continue

        value = data.get("effortLevel")
        if not isinstance(value, str):
            continue

        stripped = value.strip()
        if stripped:
            return stripped

    return None


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

        # effortTier: explicit launcher env wins; otherwise fall back to the
        # Claude Code settings.json `effortLevel` convention. Isolated in its
        # own try/except so a bad settings file only nulls this one field —
        # it must never take down launcher/profile/modelVariant.
        #
        # effortTierSource (Gap 4) is set at each resolution point and stays
        # null whenever effortTier is null — provenance is never invented.
        effort_tier_source: Optional[str] = None
        effort_tier = _nullable_str(env, "CCDASH_LAUNCH_EFFORT")
        if effort_tier is not None:
            effort_tier_source = _EFFORT_SOURCE_LAUNCH_ENV
        if effort_tier is None:
            try:
                raw_cwd = payload.get("cwd")
                project_dir = (
                    Path(str(raw_cwd).strip()).expanduser()
                    if raw_cwd and str(raw_cwd).strip()
                    else Path.cwd()
                )
                effort_tier = _settings_effort_level(env, project_dir)
                if effort_tier is not None:
                    effort_tier_source = _EFFORT_SOURCE_CLAUDE_SETTINGS
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "ccdash_capture: settings effortLevel lookup failed (ignored): %s",
                    exc,
                )
                effort_tier = None
                effort_tier_source = None

        # ── ICA key identity + spend (v51) ──────────────────────────────
        # Key NAME from the launcher env (null == not an ICA session; never CC1).
        ica_key = _nullable_str(env, _ICA_KEY_ENV)
        # Merge with any sidecar already on disk so the start reading survives
        # into the end write. The gateway probe fires once per hook event and is
        # attributed to the correct phase; a non-ICA session skips it entirely
        # (both readings stay null -- a contract state, not a failure).
        existing = _load_existing_sidecar(sidecar_path)
        is_end = _is_session_end(payload)
        probe = _probe_key_spend(env)
        prev_start = existing.get("icaSpendStart")
        prev_end = existing.get("icaSpendEnd")
        if is_end:
            ica_spend_start = prev_start  # preserve the start reading
            ica_spend_end = probe if probe is not None else prev_end
        else:
            ica_spend_start = probe if probe is not None else prev_start
            ica_spend_end = prev_end
        # Preserve a previously captured key name if this event could not read one.
        if ica_key is None and existing.get("icaKey"):
            ica_key = str(existing.get("icaKey")).strip() or None

        sidecar: dict[str, Any] = {
            "schemaVersion": _SCHEMA_VERSION,
            "sessionId": session_id,
            "launcher": _nullable_str(env, "CCDASH_LAUNCHER"),
            "profile": _nullable_str(env, "CCDASH_LAUNCH_PROFILE"),
            "effortTier": effort_tier,
            "effortTierSource": effort_tier_source,
            "modelVariant": _nullable_str(env, "CCDASH_LAUNCH_MODEL"),
            # ICA key identity + raw spend readings (v51). Null == not captured.
            "icaKey": ica_key,
            "icaSpendStart": ica_spend_start,
            "icaSpendEnd": ica_spend_end,
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
