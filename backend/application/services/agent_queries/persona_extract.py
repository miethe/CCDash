"""
Persona extract service — pure function, no IO, no model calls.

Public API
----------
extract_candidates(session, *, prior_max_msg_index=0) -> list[CandidateLine]

FORBIDDEN IMPORTS — must NEVER appear in this module:
    backend.db          (any submodule)
    OfflineCache        (backend.db.cache.OfflineCache or similar)
    backend.cli         (any submodule)
    typer               (CLI framework)
    fcntl               (file locking — belongs to the CLI layer)
    subprocess
    requests / httpx    (no network)
    asyncio             (sync only)
    Any filesystem writes (open(..., 'w'), pathlib.Path.write_*, etc.)

Design notes
------------
* ``ts`` is derived from ``SessionLog.timestamp`` (normalized to ISO-8601 Z
  form).  If the log timestamp is absent or unparseable, ``ts`` is set to the
  empty string ``""``.  The CLI layer (Phase 2) may stamp the real wall-clock
  time when appending to the inbox.

* ``cwd`` and ``transcript_path`` are NOT reliably available on ``AgentSession``
  (the model carries no filesystem path for the JSONL source).  Both fields are
  set to ``""`` here.  The Phase 2 CLI caller MUST populate them from the
  resolved JSONL file path before writing to the inbox.

* ``session_id`` is taken from ``session.id``.

Interop contract (PRD §5) — field names and types are FROZEN:
    ts               str   ISO-8601 Z or ""
    source           str   always "ccdash_persona_extract"
    text             str   candidate fact, collapsed whitespace, ≤500 chars
    session_id       str   AgentSession.id
    cwd              str   "" (populated by CLI)
    category         str   preference|goal|constraint|decision|TIL|reminder|from-args
    confidence       float heuristic match strength
    transcript_path  str   "" (populated by CLI)
    origin_msg_index int   position of the log in session.logs (0-based)
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING
from typing_extensions import TypedDict

from backend.models import AgentSession, SessionLog
from backend.application.services.agent_queries.persona_extract_rules import RULES, Rule

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Public TypedDict — byte-identical to PRD §5 field names.
# ---------------------------------------------------------------------------

class CandidateLine(TypedDict):
    ts: str
    source: str
    text: str
    session_id: str
    cwd: str
    category: str
    confidence: float
    transcript_path: str
    origin_msg_index: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SOURCE = "ccdash_persona_extract"
_TEXT_MAX = 500
_DEDUP_PREFIX = 200
_WHITESPACE = re.compile(r"\s+")


def _normalize_ts(raw: str) -> str:
    """Attempt to normalize a log timestamp to ``YYYY-MM-DDTHH:MM:SSZ`` form.

    Accepts ISO-8601 strings with or without timezone suffix.  Returns ``""``
    on any parse failure — the CLI layer handles missing timestamps.
    """
    if not raw:
        return ""
    # Strip trailing fractional seconds and common timezone designators.
    s = raw.strip()
    # Already in Z form?
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s):
        return s
    # Strip fractional seconds (e.g. ".123456")
    s = re.sub(r"\.\d+", "", s)
    # After stripping fractional seconds, check again for Z form.
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s):
        return s
    # Replace +00:00 or -00:00 with Z
    s = re.sub(r"[+-]00:00$", "Z", s)
    # Replace +HH:MM offset with Z (best-effort — we don't do tz math)
    s = re.sub(r"[+-]\d{2}:\d{2}$", "Z", s)
    # Append Z if bare datetime
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", s):
        return s + "Z"
    # Give up
    return ""


def _collapse(text: str, max_len: int = _TEXT_MAX) -> str:
    """Collapse internal whitespace and truncate to ``max_len`` chars."""
    collapsed = _WHITESPACE.sub(" ", text).strip()
    return collapsed[:max_len]


def _dedup_key(category: str, text: str) -> str:
    normalized = _WHITESPACE.sub(" ", text.strip().lower())[:_DEDUP_PREFIX]
    return f"{category}\x00{normalized}"


def _extract_group(m: re.Match, rule: Rule) -> Optional[str]:
    """Return the candidate text from the match for the given rule.

    For R4/R5/R6 which use ``|``-alternation patterns, ``capture_group`` may
    point to a group that is ``None`` (the non-firing branch).  We scan
    forward through numbered groups to find the first non-empty one, starting
    from ``capture_group``.
    """
    if rule.capture_group == 0:
        return m.group(0)
    # Try the declared group first.
    try:
        val = m.group(rule.capture_group)
    except IndexError:
        val = None
    if val is not None:
        return val
    # Fallback: scan remaining groups for the first non-None.
    for i in range(rule.capture_group + 1, len(m.groups()) + 1):
        try:
            val = m.group(i)
        except IndexError:
            break
        if val is not None:
            return val
    return None


def _find_system_reminder_nearby(
    logs: list[SessionLog],
    msg_index: int,
    window: int = 2,
) -> Optional[str]:
    """Return the content of the nearest ``system``-speaker log within ±window
    positions of ``msg_index``, or ``None`` if no such log exists.

    Best-effort and defensive — never raises.
    """
    start = max(0, msg_index - window)
    end = min(len(logs) - 1, msg_index + window)
    # Prefer logs closest to the trigger message.
    candidates: list[tuple[int, str]] = []
    for i in range(start, end + 1):
        if i == msg_index:
            continue
        log = logs[i]
        if getattr(log, "speaker", None) == "system" and log.content:
            candidates.append((abs(i - msg_index), log.content))
    if not candidates:
        return None
    # Return the content of the closest system log.
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_candidates(
    session: AgentSession,
    *,
    prior_max_msg_index: int = -1,
) -> list[CandidateLine]:
    """Extract persona-candidate lines from a single session.

    Parameters
    ----------
    session:
        The parsed agent session.  Only ``AgentSession.logs`` and
        ``AgentSession.id`` are consumed.
    prior_max_msg_index:
        The last log index already processed for this session (used for
        incremental extraction by the CLI state file).  Logs at index
        ``<= prior_max_msg_index`` are skipped.  Default ``-1`` means
        "nothing has been processed yet" — all logs are eligible.

    Returns
    -------
    list[CandidateLine]
        Ordered by ``(origin_msg_index, rule.id)``; deduplicated within
        this call by ``(category, normalized_text[:200])``.

    Notes on fields left as ``""``
    --------------------------------
    ``cwd`` and ``transcript_path`` are not available on ``AgentSession``;
    the Phase 2 CLI caller must fill them from the resolved JSONL path
    before writing to the inbox file.
    """
    results: list[tuple[int, str, CandidateLine]] = []  # (msg_index, rule_id, line)
    seen: set[str] = set()

    logs = session.logs  # flat list of SessionLog

    for msg_index, log in enumerate(logs):
        # Only process user-speaker messages after the prior watermark.
        if msg_index <= prior_max_msg_index:
            continue
        if getattr(log, "speaker", None) != "user":
            continue

        text = log.content or ""
        if not text:
            continue

        ts = _normalize_ts(getattr(log, "timestamp", "") or "")

        # Collect all rule matches for this message, then apply longest-match-wins.
        message_candidates: list[tuple[str, Rule, str]] = []  # (candidate_text, rule, dedup_key)

        for rule in RULES:
            if rule.id == "R8":
                # R8: endorsement — check pattern, then verify a nearby system log exists.
                m = rule.pattern.search(text)
                if not m:
                    continue
                system_text = _find_system_reminder_nearby(logs, msg_index)
                if system_text is None:
                    continue
                candidate_text = _collapse(system_text)
                if not candidate_text:
                    continue
                dk = _dedup_key(rule.category, candidate_text)
                message_candidates.append((candidate_text, rule, dk))
            else:
                m = rule.pattern.search(text)
                if not m:
                    continue
                raw_candidate = _extract_group(m, rule)
                if not raw_candidate:
                    continue
                candidate_text = _collapse(raw_candidate)
                if not candidate_text:
                    continue
                dk = _dedup_key(rule.category, candidate_text)
                message_candidates.append((candidate_text, rule, dk))

        if not message_candidates:
            continue

        # Longest-match-wins: prefer the candidate with the longest captured text.
        # Tie-break by rule.id (lexicographic → lower id wins, i.e. R1 beats R2).
        message_candidates.sort(key=lambda x: (-len(x[0]), x[1].id))

        for candidate_text, rule, dk in message_candidates:
            if dk in seen:
                continue
            seen.add(dk)
            line: CandidateLine = {
                "ts": ts,
                "source": _SOURCE,
                "text": candidate_text,
                "session_id": session.id,
                "cwd": "",           # populated by CLI (Phase 2)
                "category": rule.category,
                "confidence": rule.confidence,
                "transcript_path": "",  # populated by CLI (Phase 2)
                "origin_msg_index": msg_index,
            }
            results.append((msg_index, rule.id, line))

    # Stable sort by (msg_index, rule_id) for reproducible output.
    results.sort(key=lambda x: (x[0], x[1]))
    return [r[2] for r in results]
