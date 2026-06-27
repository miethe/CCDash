"""Persona extraction commands.

Provides the ``ccdash persona extract`` verb that mines a single Claude Code
session JSONL post-session and emits high-signal persona-candidate lines into
the universal persona memory bank's ``_inbox/capture.jsonl`` queue.

Phase 2 responsibilities (CLI only — the pure service lives in
``backend.application.services.agent_queries.persona_extract``):

* Resolve a JSONL path from ``--session``, ``--latest``, or ``--since``.
* Parse the JSONL via ``parse_session_file``.
* Call ``extract_candidates`` and compute emitted vs skipped against the state
  file watermark.
* Populate the service-left-empty fields: ``cwd``, ``transcript_path``, ``ts``.
* Lock the inbox file with ``fcntl.flock``, append candidate lines, flush+fsync.
* Update the state file atomically via ``os.replace``.
* Emit a JSON summary (``--json``) or human-readable text.

Mutually exclusive selection flags:
  --session <id>   exactly one session by ID
  --latest         the most recently modified JSONL (default when none given)
  --since <iso>    all sessions modified since the ISO timestamp, capped at
                   min(--limit, 25)

Exit codes:
  0   success (including no candidates)
  1   runtime error (parse failure, IO error)
  2   usage/validation error (bad option combo, session not found)
  4   inbox lock failure (concurrent run that did not release within ~1 s)
"""

from __future__ import annotations

import fcntl
import glob as _glob
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from backend.application.services.agent_queries.persona_extract import (
    CandidateLine,
    extract_candidates,
)
from backend.parsers.platforms.claude_code.parser import parse_session_file

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

persona_app = typer.Typer(
    help="Persona extraction from session logs.",
    no_args_is_help=True,
)

# ``extract`` is itself a Typer group so that ``ccdash persona extract status``
# works as a literal sub-command while ``ccdash persona extract --latest``
# (the primary verb) also works.
extract_app = typer.Typer(
    help="Extract persona candidates from session logs.",
    invoke_without_command=True,
    no_args_is_help=False,
)

persona_app.add_typer(extract_app, name="extract")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SOURCE = "ccdash_persona_extract"
_GLOB_CAP = 5000
_LOCK_RETRIES = 5
_LOCK_RETRY_SLEEP = 0.2  # seconds — 5 × 0.2 = 1.0 s max wait


# ---------------------------------------------------------------------------
# Helpers: bank / inbox / state paths
# ---------------------------------------------------------------------------

def _bank_dir() -> Path:
    """Resolve the persona bank root from env or default."""
    env = os.environ.get("OP_PERSONA_HOME", "").strip()
    return Path(env) if env else Path.home() / ".claude" / "memory"


def _state_file(bank: Path) -> Path:
    return bank / "_meta" / "ccdash-extract-state.json"


def _inbox_file(bank: Path, out_override: Optional[str]) -> Path:
    if out_override:
        return Path(out_override)
    return bank / "_inbox" / "capture.jsonl"


# ---------------------------------------------------------------------------
# Helpers: resolver
# ---------------------------------------------------------------------------

def _all_jsonl() -> list[Path]:
    """Glob all JSONL files under ~/.claude/projects/*, cap at _GLOB_CAP."""
    pattern = str(Path.home() / ".claude" / "projects" / "*" / "*.jsonl")
    paths = [Path(p) for p in _glob.glob(pattern)]
    if len(paths) > _GLOB_CAP:
        typer.echo(
            f"Warning: found {len(paths)} JSONL files; capping at {_GLOB_CAP}.",
            err=True,
        )
        # Sort by mtime desc before truncating so we keep the most recent ones.
        paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        paths = paths[:_GLOB_CAP]
    return paths


def _resolve_session(session_id: str) -> Path:
    """Resolve a JSONL path from a session ID.

    Globs ``~/.claude/projects/*/<id>.jsonl``; if multiple, returns the one
    with the highest mtime.  Exits 2 if none found.
    """
    pattern = str(Path.home() / ".claude" / "projects" / "*" / f"{session_id}.jsonl")
    matches = [Path(p) for p in _glob.glob(pattern)]
    if not matches:
        typer.echo(
            f"Error: no JSONL file found for session '{session_id}'.",
            err=True,
        )
        raise typer.Exit(code=2)
    # Prefer highest mtime (handles rare duplicates across project dirs).
    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return matches[0]


def _resolve_latest() -> Path:
    """Return the JSONL with the highest mtime.  Exits 1 if none exist."""
    paths = _all_jsonl()
    if not paths:
        typer.echo("Error: no JSONL session files found under ~/.claude/projects/.", err=True)
        raise typer.Exit(code=1)
    paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return paths[0]


def _resolve_since(since_iso: str, limit: int) -> list[Path]:
    """Return paths with mtime >= since_iso, sorted desc, capped at min(limit, 25).

    Exits 2 if ``since_iso`` cannot be parsed.
    """
    try:
        # Accept both aware and naive ISO strings.
        dt_since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        since_ts = dt_since.timestamp()
    except ValueError:
        typer.echo(
            f"Error: could not parse --since value as ISO-8601: {since_iso!r}",
            err=True,
        )
        raise typer.Exit(code=2)

    paths = _all_jsonl()
    filtered = [
        p for p in paths
        if p.exists() and p.stat().st_mtime >= since_ts
    ]
    filtered.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    cap = min(limit, 25)
    return filtered[:cap]


# ---------------------------------------------------------------------------
# Helpers: cwd derivation
# ---------------------------------------------------------------------------

def _derive_cwd_from_path(jsonl_path: Path) -> str:
    """Return the working directory for a session JSONL.

    Primary: read the ``cwd`` key from the first line(s) of the JSONL file —
    Claude Code always records the authoritative absolute path there.

    Fallback: decode the encoded project directory name back to a path.
    Claude Code encodes the working directory as the project folder name by
    replacing ``/`` with ``-`` (with a leading ``-``).  For example:
        ``-Users-miethe-dev-homelab`` → ``/Users/miethe/dev/homelab``
    This fallback is inaccurate when directory names contain hyphens, so it is
    only used when the JSONL read fails.
    """
    # Primary: read cwd from the JSONL file (first line that has the key).
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as _fh:
            for _ in range(5):  # inspect at most 5 lines to find cwd
                _line = _fh.readline()
                if not _line:
                    break
                try:
                    _obj = json.loads(_line)
                    _cwd = _obj.get("cwd")
                    if _cwd and isinstance(_cwd, str):
                        return _cwd
                except (json.JSONDecodeError, AttributeError):
                    continue
    except Exception:
        pass

    # Fallback: decode from encoded directory name.
    encoded = jsonl_path.parent.name  # e.g. "-Users-miethe-dev-homelab"
    if not encoded.startswith("-"):
        return ""
    decoded = encoded.replace("-", "/")
    # Ensure it starts with a single slash (not double from leading "-")
    if not decoded.startswith("/"):
        decoded = "/" + decoded
    return decoded


# ---------------------------------------------------------------------------
# Helpers: state file
# ---------------------------------------------------------------------------

def _load_state(state_path: Path) -> dict:
    """Load the state dict (keyed by session_id) or return {} if absent/corrupt."""
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state_path: Path, state: dict) -> None:
    """Write state atomically via a temp file + os.replace."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=state_path.parent, prefix=".ccdash-extract-state-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, separators=(",", ":"))
    except Exception:
        os.unlink(tmp_path)
        raise
    os.replace(tmp_path, state_path)


# ---------------------------------------------------------------------------
# Helpers: inbox writer
# ---------------------------------------------------------------------------

def _write_inbox(inbox_path: Path, candidates: list[CandidateLine]) -> None:
    """Acquire the inbox lock, append candidate lines, flush+fsync.

    Polls up to _LOCK_RETRIES times with _LOCK_RETRY_SLEEP seconds between
    attempts.  Exits 4 on persistent lock failure.
    """
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = inbox_path.parent / ".capture.lock"

    lock_fd = None
    try:
        lock_fd = lock_path.open("a")
        acquired = False
        for _ in range(_LOCK_RETRIES):
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(_LOCK_RETRY_SLEEP)

        if not acquired:
            typer.echo(
                "Error: could not acquire inbox lock after 1 s. "
                "Another ccdash persona extract may be running.",
                err=True,
            )
            raise typer.Exit(code=4)

        # Append all candidates.
        with inbox_path.open("a", encoding="utf-8") as fh:
            for line in candidates:
                fh.write(json.dumps(line, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            lock_fd.close()


# ---------------------------------------------------------------------------
# Helpers: field population (CLI fills service-left-empty fields)
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _populate_fields(
    candidates: list[CandidateLine],
    *,
    jsonl_path: Path,
    cwd: str,
) -> list[CandidateLine]:
    """Return new candidate dicts with CLI-populated fields filled in."""
    transcript_path = str(jsonl_path.resolve())
    now = _now_utc()
    populated = []
    for c in candidates:
        filled = dict(c)
        filled["transcript_path"] = transcript_path
        filled["cwd"] = cwd
        if not filled.get("ts"):
            filled["ts"] = now
        populated.append(filled)  # type: ignore[arg-type]
    return populated  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Core extraction logic (shared by --session, --latest, --since)
# ---------------------------------------------------------------------------

def _extract_one(
    jsonl_path: Path,
    *,
    bank: Path,
    inbox_path: Path,
    dry_run: bool,
    json_output: bool,
    state: dict,
) -> dict:
    """Run extraction for one JSONL file; return a summary dict."""
    session = parse_session_file(jsonl_path)
    if session is None:
        if not json_output:
            typer.echo(f"Warning: could not parse {jsonl_path}; skipping.", err=True)
        return {
            "session_id": jsonl_path.stem,
            "candidates_emitted": 0,
            "candidates_skipped": 0,
            "transcript_path": str(jsonl_path.resolve()),
            "state_file": str(_state_file(bank)),
        }

    session_id = session.id
    prior_max = state.get(session_id, {}).get("max_msg_index", -1)

    # Get full candidate set (all logs, no watermark filter here).
    all_cands = extract_candidates(session, prior_max_msg_index=-1)
    new_cands = [c for c in all_cands if c["origin_msg_index"] > prior_max]
    skipped_count = len(all_cands) - len(new_cands)

    # Derive cwd from the JSONL parent directory name.
    cwd = _derive_cwd_from_path(jsonl_path)

    # Populate CLI-layer fields.
    populated = _populate_fields(new_cands, jsonl_path=jsonl_path, cwd=cwd)

    state_file_path = _state_file(bank)

    if not dry_run and populated:
        _write_inbox(inbox_path, populated)
        # Advance state to max over ALL candidates (not just new ones).
        max_index = (
            max(c["origin_msg_index"] for c in all_cands)
            if all_cands
            else prior_max
        )
        state[session_id] = {
            "max_msg_index": max_index,
            "ts": _now_utc(),
        }
        _save_state(state_file_path, state)

    # Human-readable candidates: print normally (or to stderr for --json --dry-run).
    if not json_output and populated:
        for c in populated:
            typer.echo(
                f"[{c['category']}|{c['confidence']:.2f}] {c['text'][:120]}"
            )
    elif json_output and dry_run and populated:
        # Dry-run + JSON: candidates go to stderr so stdout stays clean for the summary.
        for c in populated:
            typer.echo(
                f"[{c['category']}|{c['confidence']:.2f}] {c['text'][:120]}",
                err=True,
            )

    return {
        "session_id": session_id,
        "candidates_emitted": len(populated),
        "candidates_skipped": skipped_count,
        "transcript_path": str(jsonl_path.resolve()),
        "state_file": str(state_file_path),
    }


# ---------------------------------------------------------------------------
# extract sub-commands
# ---------------------------------------------------------------------------

@extract_app.callback(invoke_without_command=True)
def extract(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(
        None,
        "--session",
        help="Session ID to extract candidates from.",
    ),
    latest: bool = typer.Option(
        False,
        "--latest",
        help="Use the most recently modified session. (default when no flag given)",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="ISO-8601 timestamp; process all sessions modified on or after this time.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help="Maximum sessions to process for --since (hard-capped at 25).",
    ),
    out: Optional[str] = typer.Option(
        None,
        "--out",
        help="Override the output file path (default: $OP_PERSONA_HOME/_inbox/capture.jsonl).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print candidates without writing to inbox or advancing state.",
    ),
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON summary to stdout instead of human-readable output.",
    ),
) -> None:
    """Extract persona candidates from session logs.

    Exactly one of --session, --latest, or --since must be given.
    If none is given, --latest is used by default.
    """
    # Skip if a sub-command (e.g. "status") is being invoked.
    if ctx.invoked_subcommand is not None:
        return

    # Validate mutual exclusivity.
    flags_given = sum([bool(session), latest, bool(since)])
    if flags_given > 1:
        typer.echo(
            "Error: --session, --latest, and --since are mutually exclusive. "
            "Specify at most one.",
            err=True,
        )
        raise typer.Exit(code=2)

    # Default to --latest when none given.
    if flags_given == 0:
        latest = True

    # Clamp --limit.
    clamped_limit = min(limit, 25)

    bank = _bank_dir()
    inbox_path = _inbox_file(bank, out)
    state_file_path = _state_file(bank)
    state = _load_state(state_file_path)

    try:
        if session:
            jsonl_path = _resolve_session(session)
            summary = _extract_one(
                jsonl_path,
                bank=bank,
                inbox_path=inbox_path,
                dry_run=dry_run,
                json_output=json_flag,
                state=state,
            )
            result = summary

        elif latest:
            jsonl_path = _resolve_latest()
            summary = _extract_one(
                jsonl_path,
                bank=bank,
                inbox_path=inbox_path,
                dry_run=dry_run,
                json_output=json_flag,
                state=state,
            )
            result = summary

        else:  # since
            assert since is not None
            paths = _resolve_since(since, clamped_limit)
            if not paths:
                if json_flag:
                    typer.echo(json.dumps([], separators=(",", ":")))
                else:
                    typer.echo("No sessions found matching --since criteria.")
                return

            summaries = []
            for p in paths:
                s = _extract_one(
                    p,
                    bank=bank,
                    inbox_path=inbox_path,
                    dry_run=dry_run,
                    json_output=json_flag,
                    state=state,
                )
                summaries.append(s)
            result = summaries  # type: ignore[assignment]

    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_flag:
        typer.echo(json.dumps(result, separators=(",", ":")))


@extract_app.command("status")
def extract_status(
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON (always true for this command).",
    ),
) -> None:
    """Show the persona extract state file contents."""
    bank = _bank_dir()
    state_file_path = _state_file(bank)
    state = _load_state(state_file_path)
    typer.echo(json.dumps(state, indent=2 if not json_flag else None))


# ---------------------------------------------------------------------------
# status shortcut on persona_app (mirrors ``ccdash persona status``)
# ---------------------------------------------------------------------------

@persona_app.command("status")
def persona_status(
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Show the persona extract state file contents (alias of ``extract status``)."""
    bank = _bank_dir()
    state_file_path = _state_file(bank)
    state = _load_state(state_file_path)
    typer.echo(json.dumps(state, indent=2 if not json_flag else None))


__all__ = ["persona_app"]
