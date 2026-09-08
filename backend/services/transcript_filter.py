# =============================================================================
# VENDORED — do not edit here. Upstream owns this file.
#
#   Upstream:        agentic_meta_dev/scripts/aos_transcript_filter.py
#   Upstream sha256: eb50cb30af49fb72ccacccfeee31bf8dba898ef2c9e26c77e2a040bd00e95f92
#   Vendored:        2026-09-07 for node_01M1YV12EH7AQSXSMSFSKQJXM8
#                    (parent finding node_01M1YQE73ZT7T4EZSKNYX007ER)
#   Policy:          agentic_meta_dev/docs/policies/transcript-exclusions.md
#
# CCDash must not import agentic_meta_dev at runtime, so the predicate is COPIED
# rather than depended on. That is a deliberate trade: a copy can drift, and the
# mitigations are (a) this header, which names the exact upstream bytes it was
# cut from, and (b) the module's own EMBEDDED_SPEC, asserted equal to upstream's
# JSON spec by a test in that repo. The JSON spec is deliberately NOT vendored:
# load_spec() falls back to EMBEDDED_SPEC when it is absent, so this copy has one
# source of rules rather than two that can disagree.
#
# CHCW vendored the same bytes at the same sha (chcw main 18c5c4e,
# backend/src/chcw/pipeline/transcript_filter.py). Three copies now exist; they
# are byte-identical below this header by construction, and a drift between them
# is a bug in whichever copy was edited locally.
#
# Fix a rule UPSTREAM and re-vendor. A local edit is drift with a head start
# (agentic_meta_dev/.claude/rules/artifact-registration.md).
#
# CCDash integration (what consumes this): backend/services/transcript_egress.py.
# =============================================================================
"""Shared egress-exclusion predicate for Claude Code JSONL transcript records.

**Why this module exists in ONE place.** A session transcript is an egress surface. Metis's
private journal reaches it by three independent routes, and each route was discovered
separately, months apart, by a different reader:

1. A session whose ``cwd`` is under ``~/.metis`` writes an ordinary transcript under
   ``~/.claude/projects``. Claude Code stores every transcript there **regardless of where the
   session ran**, so the transcript's *path* carries no ``.metis`` component
   (``~/.metis/journal`` slugs to ``-Users-miethe--metis-journal``). Path filtering let two
   private-journal sessions through on the CHCW adapter's first real run.
2. ``op journal write "<text>" --kind felt`` run from an *ordinary* chat session records the
   full entry text in **that** session's transcript, as the Bash ``tool_use`` ``input.command``
   — and again in the paired ``tool_result`` where the wrapper echoes it back. No marker, no
   ``.metis`` cwd, nothing a path or marker filter can see.
3. An assistant turn that quotes an entry id (``jrn_YYYYMMDD_xxxxxxxx``) is quoting journal
   content by construction.

Route 2 is why a marker-only skip is not sufficient and why ``op journal write`` now prepends
the marker itself (``operator_core.adapters.journal.add``) rather than leaving it to the caller
— but the prepend lands in the *store*, not in the command line that was already typed, so the
command-pattern rule below stays load-bearing forever.

**Contract.**

* **Dependency-free.** Standard library only, single file, no package. It is *vendored* into
  readers that must not import this repo at runtime (CHCW copies it with a provenance header).
* **Fails CLOSED.** A match drops the **whole record**, never one fragment. Journal text is
  echoed into the transcript as ordinary prose and ordinary tool arguments, so partial
  redaction is not a safe posture: what remains would still be the entry, minus a phrase.
* **Stateful across records, deliberately.** A ``tool_result`` names its ``tool_use`` only by
  ``tool_use_id``, and the two live in *different* JSONL records. So the filter carries a taint
  set. Feed records in file order, one :class:`TranscriptFilter` per transcript.

  ⚠️ **A reader that resumes MID-FILE must call** :meth:`TranscriptFilter.prime` **over the
  records it is skipping.** A transcript is appended to while its own session runs, so an
  incremental reader routinely stops between a ``tool_use`` and its ``tool_result`` — and a
  fresh filter starting after that boundary has no taint for the echo, which then survives on
  nothing but the coincidence that ``op journal write``'s echo happens to quote an entry id.
  ``op journal read``/``surface`` output need not. Found by review before this shipped.
* **Never reports content.** Reasons are stable machine strings. Nothing here logs, returns, or
  raises the matched text — a filter that protects journal egress must not become the leak.

Policy: ``docs/policies/transcript-exclusions.md``. Rule: ``.claude/rules/metis-journal.md``
§ Egress. Spec data: ``scripts/aos-transcript-exclusions.json`` (this module's
``EMBEDDED_SPEC`` is a byte-for-byte fallback so a vendored single file still works; a test
asserts the two agree).

Origin: ``node_01M1YQE73ZT7T4EZSKNYX007ER``, 2026-09-07.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "EMBEDDED_SPEC",
    "SPEC_PATH",
    "SPEC_VERSION",
    "JOURNAL_MARKER",
    "REASONS",
    "TranscriptFilter",
    "is_forbidden_cwd",
    "load_spec",
    "should_exclude",
]

SPEC_VERSION = "1"

#: Fallback copy of ``scripts/aos-transcript-exclusions.json``. The JSON file is the spec a
#: human edits; this dict is what a *vendored* single-file copy runs on. They are asserted
#: equal by test, so an edit to one that is not mirrored to the other is a red build, not a
#: silently divergent filter in a downstream reader.
EMBEDDED_SPEC: dict[str, Any] = {
    "spec_version": SPEC_VERSION,
    "journal_marker": "JOURNAL ENTRY START",
    "forbidden_cwd_names": [".metis"],
    "journal_command_pattern": r"\bop\s+journal\s+(?:write|read|surface)\b",
    "journal_entry_id_pattern": r"\bjrn_\d{8}_[0-9a-f]{8}\b",
}

SPEC_PATH = Path(__file__).with_name("aos-transcript-exclusions.json")

JOURNAL_MARKER: str = EMBEDDED_SPEC["journal_marker"]


class REASONS:
    """Stable machine reasons. Callers key counters off these; never off prose."""

    METIS_CWD = "metis_cwd"
    JOURNAL_MARKER = "journal_marker"
    JOURNAL_COMMAND = "journal_command"
    JOURNAL_COMMAND_RESULT = "journal_command_result"
    JOURNAL_ENTRY_ID = "journal_entry_id"

    ALL = (
        METIS_CWD,
        JOURNAL_MARKER,
        JOURNAL_COMMAND,
        JOURNAL_COMMAND_RESULT,
        JOURNAL_ENTRY_ID,
    )


def load_spec(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Read the JSON spec, falling back to :data:`EMBEDDED_SPEC`.

    A missing or unreadable spec file is NOT an error: a vendored copy legitimately ships
    without it. A *malformed* one is also not an error, for the same reason a filter must never
    fail open on a syntax slip — the embedded defaults are always a valid filter.
    """
    candidate = Path(path) if path is not None else SPEC_PATH
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(EMBEDDED_SPEC)
    if not isinstance(raw, dict):
        return dict(EMBEDDED_SPEC)
    merged = dict(EMBEDDED_SPEC)
    for key in EMBEDDED_SPEC:
        if key in raw:
            merged[key] = raw[key]
    return merged


def is_forbidden_cwd(value: Any, forbidden: Iterable[str] = (".metis",)) -> bool:
    """True when ``value`` is a path with a forbidden component (default ``.metis``).

    Compares **path components**, not substrings: ``/Users/x/.metis/journal`` matches while
    ``/Users/x/dotmetis`` and ``/Users/x/metis-notes`` do not. ``~`` is expanded so a
    transcript recording ``~/.metis/journal`` is caught as well as an absolute one.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        expanded = os.path.expanduser(value.strip())
    except (OSError, ValueError):
        expanded = value.strip()
    parts = {part for part in Path(expanded).parts}
    return any(name in parts for name in forbidden)


def _iter_content_blocks(record: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield the ``message.content`` blocks of a record, tolerating every observed shape."""
    message = record.get("message")
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                yield block
    # `toolUseResult` is Claude Code's out-of-band echo of a tool result; it can carry the
    # command's own output even when the message content has been elided.
    extra = record.get("toolUseResult")
    if isinstance(extra, dict):
        yield extra


def _command_strings(block: dict[str, Any]) -> Iterable[str]:
    """Every string in a ``tool_use`` input that could hold a shell command line.

    ``input.command`` is the Bash tool's field and the one the rule names, but the same text
    reaches the transcript through ``description`` and through nested inputs in a batch tool,
    so the whole input subtree is searched. Over-matching here costs a dropped record; under-
    matching costs an egress.
    """
    payload = block.get("input")
    if payload is None:
        return
    try:
        yield json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        yield str(payload)


def _blob(record: dict[str, Any]) -> str:
    """The record serialized for substring/regex scanning. Never returned to a caller."""
    try:
        return json.dumps(record, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(record)


class TranscriptFilter:
    """Per-transcript exclusion state. One instance per transcript, records in file order.

    The instance exists only to carry ``tainted_tool_use_ids``: a ``tool_result`` that must be
    dropped names its ``tool_use`` by id, and the two are separate JSONL records. A caller that
    reuses one filter across transcripts is not wrong (ids are unique) but a caller that resets
    mid-file will let paired results through.
    """

    def __init__(self, spec: dict[str, Any] | None = None) -> None:
        self.spec = dict(spec) if spec else load_spec()
        self.marker: str = str(self.spec.get("journal_marker") or JOURNAL_MARKER)
        self.forbidden_cwd_names: tuple[str, ...] = tuple(
            self.spec.get("forbidden_cwd_names") or (".metis",)
        )
        self._command_re = re.compile(
            str(self.spec.get("journal_command_pattern") or EMBEDDED_SPEC["journal_command_pattern"])
        )
        self._entry_id_re = re.compile(
            str(self.spec.get("journal_entry_id_pattern") or EMBEDDED_SPEC["journal_entry_id_pattern"])
        )
        self.tainted_tool_use_ids: set[str] = set()

    # -- rule helpers ---------------------------------------------------------------------

    def _journal_tool_use_ids(self, record: dict[str, Any]) -> set[str]:
        """Ids of ``tool_use`` blocks in this record whose input invokes ``op journal``."""
        found: set[str] = set()
        for block in _iter_content_blocks(record):
            if block.get("type") != "tool_use":
                continue
            for text in _command_strings(block):
                if self._command_re.search(text):
                    found.add(str(block.get("id") or ""))
                    break
        return found

    def _paired_result_ids(self, record: dict[str, Any]) -> set[str]:
        """``tool_use_id``s referenced by ``tool_result`` blocks in this record."""
        found: set[str] = set()
        for block in _iter_content_blocks(record):
            if block.get("type") != "tool_result":
                continue
            ref = block.get("tool_use_id")
            if isinstance(ref, str) and ref:
                found.add(ref)
        return found

    # -- the predicate --------------------------------------------------------------------

    def should_exclude(self, record: Any) -> tuple[bool, str | None]:
        """``(True, reason)`` when this record must never reach an index; else ``(False, None)``.

        Taint registration happens **before** the verdict so a record excluded for one reason
        still poisons its paired ``tool_result`` — otherwise the first matching rule would win
        and the echo would survive.
        """
        if not isinstance(record, dict):
            return (False, None)

        # 0. Register taint first, unconditionally (see docstring).
        journal_uses = self._journal_tool_use_ids(record)
        self.tainted_tool_use_ids.update(uid for uid in journal_uses if uid)

        # 1. The session's own cwd. Authoritative and cheapest; a caller that sees this should
        #    normally abandon the WHOLE transcript, not just this record.
        if is_forbidden_cwd(record.get("cwd"), self.forbidden_cwd_names):
            return (True, REASONS.METIS_CWD)

        # 2. `op journal ...` invocation in this record.
        if journal_uses:
            return (True, REASONS.JOURNAL_COMMAND)

        # 3. The paired result of an earlier (or same-record) `op journal ...` invocation.
        if self._paired_result_ids(record) & self.tainted_tool_use_ids:
            return (True, REASONS.JOURNAL_COMMAND_RESULT)

        blob = _blob(record)

        # 4. The marker, anywhere in the record.
        if self.marker in blob:
            return (True, REASONS.JOURNAL_MARKER)

        # 5. A quoted journal entry id.
        if self._entry_id_re.search(blob):
            return (True, REASONS.JOURNAL_ENTRY_ID)

        return (False, None)

    def prime(self, record: Any) -> str | None:
        """Register taint from a record WITHOUT rendering a verdict on it.

        For readers that resume mid-file: replay the SKIPPED prefix through this before
        reading forward, so a ``tool_result`` arriving after the resume point is still paired
        with the ``op journal`` call that produced it.

        Returns :data:`REASONS.METIS_CWD` when the primed record proves the session's cwd is
        forbidden — a caller seeing that should abandon the whole transcript, not resume into
        it, because the prefix has already established what this session is. Returns ``None``
        otherwise; a primed record is never itself "excluded" (it was already read, or is about
        to be read normally).
        """
        if not isinstance(record, dict):
            return None
        self.tainted_tool_use_ids.update(
            uid for uid in self._journal_tool_use_ids(record) if uid
        )
        if is_forbidden_cwd(record.get("cwd"), self.forbidden_cwd_names):
            return REASONS.METIS_CWD
        return None

    def reset(self) -> None:
        """Forget taint. Call between transcripts, never inside one."""
        self.tainted_tool_use_ids.clear()


_DEFAULT = TranscriptFilter()


def should_exclude(record: Any, *, state: TranscriptFilter | None = None) -> tuple[bool, str | None]:
    """Module-level convenience over a shared :class:`TranscriptFilter`.

    Pass ``state`` for anything real: the process-wide default accumulates taint forever, which
    is safe (fail-closed) but makes counts non-reproducible across runs.
    """
    return (state or _DEFAULT).should_exclude(record)
