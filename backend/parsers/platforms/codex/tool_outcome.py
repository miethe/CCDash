"""Codex tool-result outcome detection (DI-4d).

Why this module exists
----------------------
Real Codex ``function_call_output`` / ``custom_tool_call_output`` payloads carry
**no** ``status`` field. Measured 2026-08-03 across every local rollout JSONL
(``~/.codex/sessions/**/*.jsonl``, 3,389 files, 189,392 tool-result payloads):
the payload key set is exactly
``{type, id, call_id, output, internal_chat_message_metadata_passthrough}`` and
``payload.get("status")`` was ``None`` on 100% of them.

The prior heuristic (``codex/parser.py`` — ``status in {"error","failed","failure"}``)
therefore never fired, and ``session_tool_usage.success_count`` recorded
``call_count == success_count`` exactly, for every GPT/Codex model, across
190,450 all-time tool calls — an unpopulated field masquerading as perfect
reliability.

Where the signal actually lives
-------------------------------
The tool-level outcome is emitted by the harness *inside the output payload*, in
a small, stable set of shapes. Each is keyed by ``OutcomeSource`` below.

``envelope_exit_code`` — ``apply_patch`` / ``shell`` / some ``exec_command``::

    {"output": "Success. Updated the following files:\\nM foo.py\\n",
     "metadata": {"exit_code": 0, "duration_seconds": 0.1}}

``exit_code_line`` — a harness metadata line in the header block that precedes
``Output:``. Two spellings, both observed::

    Chunk ID: beb018
    Wall time: 0.0513 seconds
    Process exited with code 1        <-- exec_command / write_stdin
    Original token count: 0
    Output:

    Exit code: 1                      <-- shell_command / legacy apply_patch
    Wall time: 0 seconds
    Output:
    sed: nope.md: No such file or directory

``script_lifecycle`` — code-mode ``exec`` / ``wait`` first line::

    Script completed / Script failed / Script terminated
    Script running with cell ID 4     (in flight, not a failure)

``in_flight`` — async ``exec_command`` / ``write_stdin`` launch::

    Process running with session ID 47488

``failure_marker`` — bare harness failure strings with no header block::

    write_stdin failed: stdin is closed for this session; rerun exec_command ...
    apply_patch verification failed: Failed to find expected lines in ...
    collab spawn failed: agent thread limit reached (max 6)
    failed to parse function arguments: missing field `input` at line 1 ...
    failed in sandbox MacosSeatbelt with execution error: sandbox denied ...
    failed to spawn code-mode host /Users/.../codex-code-mode-host: No such ...
    unsupported call: spawn_agent
    execution error: Io(Os { code: 20, kind: NotADirectory, ... })
    Blocked by robots.txt
    exec command rejected by user

``structured_ok`` — the tool returned a structured JSON result, i.e. it ran::

    {"agent_id": "...", "nickname": "Franklin"}   spawn_agent
    {"status": {...}, "timed_out": true}          wait_agent
    {"message": "Wait timed out.", ...}           wait_agent
    {"previous_status": "running"}                close_agent
    {"submission_id": "..."}                      send_input
    {"agents": [...]}                             list_agents

Deliberate non-error decisions
------------------------------
* ``wait_agent`` ``timed_out: true`` is a *poll* result, not a tool failure.
* ``Process running with session ID`` / ``Script running with cell ID`` are
  in-flight launches; the outcome is not yet known and must not be scored.
* ``unknown`` is returned rather than guessed. Callers map ``unknown`` to
  "not an error" (preserving today's behaviour) but should record the source so
  detection coverage stays measurable instead of silently degrading.

Scope note (DI-4d): this module only recovers the per-call error bit at parse
time. It makes no change to ``routing_rollup`` ``success_rate`` emission, which
stays ``null`` pending DI-4e.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "OUTCOME_SOURCES",
    "SOURCE_UNKNOWN",
    "classify_tool_outcome",
    "normalize_tool_output_text",
]

SOURCE_PAYLOAD_STATUS = "payload_status"
SOURCE_ENVELOPE_EXIT_CODE = "envelope_exit_code"
SOURCE_EXIT_CODE_LINE = "exit_code_line"
SOURCE_SCRIPT_LIFECYCLE = "script_lifecycle"
SOURCE_IN_FLIGHT = "in_flight"
SOURCE_FAILURE_MARKER = "failure_marker"
SOURCE_STRUCTURED_OK = "structured_ok"
SOURCE_EMPTY_OUTPUT = "empty_output"
SOURCE_KNOWN_OK = "known_ok"
SOURCE_UNKNOWN = "unknown"

OUTCOME_SOURCES = frozenset(
    {
        SOURCE_PAYLOAD_STATUS,
        SOURCE_ENVELOPE_EXIT_CODE,
        SOURCE_EXIT_CODE_LINE,
        SOURCE_SCRIPT_LIFECYCLE,
        SOURCE_IN_FLIGHT,
        SOURCE_FAILURE_MARKER,
        SOURCE_STRUCTURED_OK,
        SOURCE_EMPTY_OUTPUT,
        SOURCE_KNOWN_OK,
        SOURCE_UNKNOWN,
    }
)

_ERROR_STATUS_TOKENS = {"error", "failed", "failure"}

# Separator between the harness metadata header and the captured process output.
# Everything after it is arbitrary user/command text and MUST NOT be scanned for
# failure markers — command bodies routinely contain "error:" while succeeding.
_OUTPUT_SEPARATOR = "\nOutput:"

_EXIT_CODE_LINE_RE = re.compile(
    r"^(?:Exit code\s*:|Process exited with code)\s*(-?\d+)\s*$",
    re.IGNORECASE,
)

_SCRIPT_ERROR_LINES = {"script failed", "script terminated"}
_SCRIPT_OK_PREFIXES = ("script completed", "script running with cell id", "script started")
_IN_FLIGHT_PREFIXES = ("process running with session id", "process running")

_FAILURE_MARKER_PREFIXES = (
    "execution error:",
    "unsupported call:",
    "failed to spawn ",
    "failed in sandbox ",
    "error: ",
    "blocked by robots.txt",
)
_FAILURE_MARKER_SUBSTRINGS = (
    "rejected by user",
    "aborted by user",
)
# "<anything without a colon> failed[ ...]:" — e.g. "write_stdin failed:",
# "apply_patch verification failed:", "collab spawn failed:",
# "failed to parse function arguments:".
_FAILED_PREFIX_RE = re.compile(r"^[^\n:]{0,80}\bfailed\b[^\n:]{0,60}:", re.IGNORECASE)
# "<tool_name> failed <preposition> ..." with the colon far past the 60-char
# window — e.g. "exec_command failed for `/bin/zsh -lc '...'`: CreateProcess {".
_TOOL_FAILED_PREFIX_RE = re.compile(r"^[\w.\-]{1,60}\s+failed\b", re.IGNORECASE)

_KNOWN_OK_EXACT = {"plan updated"}


def normalize_tool_output_text(raw_output: Any) -> str:
    """Flatten a Codex tool-result ``output`` value to plain text.

    ``function_call_output`` carries a plain string. ``custom_tool_call_output``
    carries a list of ``{"type": "input_text", "text": ...}`` blocks — the
    parser's generic ``_coerce_text_blob`` JSON-dumps that list, which buries
    the ``Script failed`` / ``Exit code:`` markers inside a JSON string. This
    helper joins the block text instead.
    """
    if raw_output is None:
        return ""
    if isinstance(raw_output, str):
        return raw_output.strip()
    if isinstance(raw_output, list):
        parts: list[str] = []
        for block in raw_output:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                content = block.get("content")
                if isinstance(content, str):
                    parts.append(content)
                    continue
                parts.append(json.dumps(block, ensure_ascii=True))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    if isinstance(raw_output, dict):
        try:
            return json.dumps(raw_output, ensure_ascii=True).strip()
        except Exception:
            return str(raw_output).strip()
    return str(raw_output).strip()


def _envelope_exit_code(text: str) -> int | None:
    """Return ``metadata.exit_code`` when the output is a ``{output, metadata}`` envelope."""
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("exit_code")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_json_object(text: str) -> bool:
    if not text.startswith("{"):
        return False
    try:
        return isinstance(json.loads(text), dict)
    except Exception:
        return False


def classify_tool_outcome(
    raw_output: Any,
    *,
    payload_status: Any = None,
) -> tuple[bool | None, str]:
    """Classify a Codex tool result as error / success / unknown.

    Returns ``(is_error, source)`` where ``is_error`` is ``True`` (failed),
    ``False`` (succeeded / in flight) or ``None`` (not classifiable). ``source``
    is one of :data:`OUTCOME_SOURCES` and exists so detection coverage is
    observable rather than silently assumed.
    """
    status_token = str(payload_status or "").strip().lower()
    if status_token in _ERROR_STATUS_TOKENS:
        return True, SOURCE_PAYLOAD_STATUS
    if status_token in {"completed", "success", "succeeded", "ok"}:
        return False, SOURCE_PAYLOAD_STATUS

    text = normalize_tool_output_text(raw_output)
    if not text:
        return False, SOURCE_EMPTY_OUTPUT

    exit_code = _envelope_exit_code(text)
    if exit_code is not None:
        return exit_code != 0, SOURCE_ENVELOPE_EXIT_CODE

    separator_idx = text.find(_OUTPUT_SEPARATOR)
    header = text if separator_idx < 0 else text[:separator_idx]
    header_lines = [line.strip() for line in header.splitlines() if line.strip()]

    # Harness metadata lines sit at the END of the header (a multi-line
    # `Command:` echo can precede them), so prefer the last match.
    last_exit_code: int | None = None
    for line in header_lines:
        match = _EXIT_CODE_LINE_RE.match(line)
        if match:
            last_exit_code = int(match.group(1))
    if last_exit_code is not None:
        return last_exit_code != 0, SOURCE_EXIT_CODE_LINE

    if header_lines:
        first = header_lines[0]
        lowered = first.lower()
        if lowered in _SCRIPT_ERROR_LINES:
            return True, SOURCE_SCRIPT_LIFECYCLE
        if lowered.startswith(_SCRIPT_OK_PREFIXES):
            return False, SOURCE_SCRIPT_LIFECYCLE
        if lowered.startswith(_IN_FLIGHT_PREFIXES):
            return False, SOURCE_IN_FLIGHT
        if any(lowered.startswith(marker) for marker in _FAILURE_MARKER_PREFIXES):
            return True, SOURCE_FAILURE_MARKER
        if any(marker in lowered for marker in _FAILURE_MARKER_SUBSTRINGS):
            return True, SOURCE_FAILURE_MARKER
        if _FAILED_PREFIX_RE.match(first) or _TOOL_FAILED_PREFIX_RE.match(first):
            return True, SOURCE_FAILURE_MARKER
        if lowered in _KNOWN_OK_EXACT:
            return False, SOURCE_KNOWN_OK

    for line in header_lines:
        if line.lower().startswith(_IN_FLIGHT_PREFIXES):
            return False, SOURCE_IN_FLIGHT

    if _is_json_object(text):
        return False, SOURCE_STRUCTURED_OK

    return None, SOURCE_UNKNOWN
