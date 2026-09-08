"""CCDash-side integration of the shared transcript-egress predicate.

A Claude Code session transcript is an **egress surface**. Metis's private journal reaches it
by three routes (see :mod:`backend.services.transcript_filter`), and CCDash indexes transcripts
into ``session_messages`` + its lexical FTS — so a journal entry written from an ordinary chat
session became *searchable* here. Measured 2026-09-07: 208 rows across 59 sessions
(``node_01M1YV12EH7AQSXSMSFSKQJXM8``).

This module is the **only** place CCDash calls the predicate from. It exists because the
predicate is defined over *raw JSONL records* while CCDash has two shapes to protect:

``filter_transcript_records``
    The raw-record path — the single choke point. ``parse_session_file`` re-reads a transcript
    in full on every scan, and BOTH write paths (the laptop ``worker-watch`` sync engine and
    the node's ``ccdash-ingest-daemon`` -> ``POST /api/v1/ingest/sessions``) go through it, so a
    record dropped here never becomes a ``session_messages`` row, a ``session_logs`` row, an FTS
    entry, or a ``metadata_json`` blob.

``filter_session_logs``
    The parsed-``SessionLog`` backstop. A remote client running *older* code POSTs an
    already-parsed ``AgentSession`` payload that this process never parsed, so the raw-record
    filter cannot have run on it. Rather than reimplement the rules against a second shape,
    each log is reshaped into a record-like dict and fed through the **same**
    :class:`TranscriptFilter`, taint machinery included.

**Resume boundary.** Upstream warns that an incremental reader resuming mid-file starts with an
empty taint set, so a ``tool_result`` echo arriving after the resume point survives. CCDash has
**no mid-file resume**: ``parse_session_file`` always reads from record 0 (``read_text()`` +
full re-parse), the CLI daemon tracks mtimes rather than byte offsets, and its WAL buffers
already-built *events*, not read positions. So on the raw-record path a fresh filter always sees
the whole file and :meth:`TranscriptFilter.prime` is not needed — ``prime_prefix`` is accepted
anyway so that an incremental reader added later cannot regress the boundary silently.

The ``filter_session_logs`` path is where the boundary is *real*: a projected log list has lost
the record framing, and its ``tool_use`` / ``tool_result`` pairing survives only as
``toolCall.id`` / ``relatedToolCallId``. The reshaping below rebuilds exactly that pairing so
the echo is still caught.

**Fails closed, whole-record.** A match drops the entire record/log, never one fragment —
journal text is echoed as ordinary prose and ordinary tool arguments, so partial redaction
would leave the entry minus a phrase. There is no opt-out flag: a switch to disable this is a
switch to re-open the egress.

**Never reports content.** Counters key off the stable machine reasons in ``REASONS``. Nothing
here logs, returns, or raises matched text — a filter protecting journal egress must not become
the leak.

Policy: ``agentic_meta_dev/docs/policies/transcript-exclusions.md``.
Node: ``node_01M1YV12EH7AQSXSMSFSKQJXM8`` (parent ``node_01M1YQE73ZT7T4EZSKNYX007ER``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from backend.services.transcript_filter import REASONS, TranscriptFilter, is_forbidden_cwd

__all__ = [
    "REASONS",
    "TranscriptFilter",
    "EgressFilterResult",
    "filter_transcript_records",
    "filter_session_logs",
    "log_to_record",
    "session_cwd_candidates",
]

logger = logging.getLogger(__name__)


@dataclass
class EgressFilterResult:
    """Counts only. Never carries, and must never be extended to carry, matched text."""

    kept: int = 0
    dropped: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    #: Set to ``REASONS.METIS_CWD`` when the *whole* transcript/session must be abandoned
    #: rather than filtered record-by-record.
    abandoned: str | None = None

    def record_drop(self, reason: str | None) -> None:
        self.dropped += 1
        key = reason or "unknown"
        self.by_reason[key] = self.by_reason.get(key, 0) + 1

    @property
    def any_dropped(self) -> bool:
        return self.dropped > 0 or self.abandoned is not None

    def summary(self) -> str:
        """A log-safe one-liner: reasons and counts, never content."""
        if self.abandoned:
            return f"abandoned={self.abandoned}"
        parts = ",".join(f"{k}={v}" for k, v in sorted(self.by_reason.items()))
        return f"kept={self.kept} dropped={self.dropped} {parts}".strip()


def filter_transcript_records(
    entries: Sequence[dict[str, Any]],
    *,
    prime_prefix: Iterable[dict[str, Any]] | None = None,
    source: str = "",
) -> tuple[list[dict[str, Any]], EgressFilterResult]:
    """Drop journal-bearing records from a raw JSONL transcript, in file order.

    ``prime_prefix`` replays records the caller has already consumed through
    :meth:`TranscriptFilter.prime` so their taint is carried forward. CCDash never resumes
    mid-file today (see module docstring); the parameter exists so that adding an incremental
    reader is a deliberate wiring step rather than a silent regression.

    A record proving a forbidden ``cwd`` abandons the **whole** transcript: the session *is* a
    journal session, so filtering it record-by-record would keep the rest of it.
    """
    state = TranscriptFilter()
    result = EgressFilterResult()

    for prior in prime_prefix or ():
        if state.prime(prior) == REASONS.METIS_CWD:
            result.abandoned = REASONS.METIS_CWD
            _log(result, source)
            return [], result

    kept: list[dict[str, Any]] = []
    for record in entries:
        excluded, reason = state.should_exclude(record)
        if excluded and reason == REASONS.METIS_CWD:
            result.abandoned = REASONS.METIS_CWD
            _log(result, source)
            return [], result
        if excluded:
            result.record_drop(reason)
            continue
        kept.append(record)

    result.kept = len(kept)
    _log(result, source)
    return kept, result


def session_cwd_candidates(session_row: dict[str, Any] | None) -> list[str]:
    """Every string on a session payload that could name the session's working directory.

    ``sessions.cwd`` is populated on only ~15% of CCDash sessions, so an absent value is
    **UNMEASURED, never clean** — which is precisely why the raw-record path above reads each
    record's own ``cwd`` instead of trusting this. These candidates are a best-effort extra for
    the parsed-log backstop, where the records are already gone.
    """
    if not isinstance(session_row, dict):
        return []
    out: list[str] = []
    for key in ("cwd", "workingDirectory", "working_directory", "projectPath", "repoPath"):
        value = session_row.get(key)
        if isinstance(value, str) and value.strip():
            out.append(value)
    for key in ("workingDirectories", "working_directories"):
        values = session_row.get(key)
        if isinstance(values, (list, tuple, set)):
            out.extend(v for v in values if isinstance(v, str) and v.strip())
    context = session_row.get("sessionContext")
    if isinstance(context, dict):
        out.extend(session_cwd_candidates(context))
    return out


def log_to_record(log: dict[str, Any], *, cwd: str = "") -> dict[str, Any]:
    """Reshape one parsed ``SessionLog``-shaped dict into a record the predicate understands.

    The whole log is embedded under ``_ccdash_log`` so the marker and entry-id rules — which
    scan the serialized record — still see ``content``, ``metadata.toolArgs`` and
    ``metadata.toolOutput``. The ``tool_use`` / ``tool_result`` blocks are rebuilt from
    ``toolCall.id`` and ``relatedToolCallId`` so the predicate's own taint pairing catches the
    wrapper's echo of an ``op journal`` call, which is the whole reason the pairing exists.

    Deliberately NOT a reimplementation of any rule: this function only changes shape.
    """
    blocks: list[dict[str, Any]] = []

    tool_call = log.get("toolCall")
    if isinstance(tool_call, dict):
        call_id = tool_call.get("id")
        blocks.append(
            {
                "type": "tool_use",
                "id": str(call_id) if call_id not in (None, "") else "",
                "name": tool_call.get("name"),
                # `args` is the tool input; the predicate serializes the whole subtree, so a
                # command reaching the transcript through `description` or a nested batch input
                # is covered too.
                "input": tool_call.get("args"),
            }
        )

    metadata = log.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    if "toolArgs" in metadata:
        blocks.append({"type": "tool_use", "id": "", "input": metadata.get("toolArgs")})

    related = log.get("relatedToolCallId") or metadata.get("relatedToolCallId")
    if isinstance(related, str) and related:
        blocks.append({"type": "tool_result", "tool_use_id": related})

    record: dict[str, Any] = {"message": {"content": blocks}, "_ccdash_log": log}
    if cwd:
        record["cwd"] = cwd
    return record


def filter_session_logs(
    logs: Sequence[Any],
    *,
    session_row: dict[str, Any] | None = None,
    source: str = "",
) -> tuple[list[Any], EgressFilterResult]:
    """Backstop over already-parsed logs, for payloads this process never parsed.

    Feed logs in their original order: the pairing rebuilt by :func:`log_to_record` only works
    if the ``tool_use`` log is seen before the ``tool_result`` log that echoes it, exactly as in
    the transcript.

    Non-dict entries are passed through untouched — a pydantic ``SessionLog`` reaches some call
    sites unserialized, and dropping what we cannot inspect would be a silent data loss rather
    than a filter. Such a caller is covered by the raw-record path upstream of it.
    """
    result = EgressFilterResult()

    forbidden = next(
        (c for c in session_cwd_candidates(session_row) if is_forbidden_cwd(c)),
        None,
    )
    if forbidden is not None:
        result.abandoned = REASONS.METIS_CWD
        _log(result, source)
        return [], result

    state = TranscriptFilter()
    kept: list[Any] = []
    for log in logs:
        if not isinstance(log, dict):
            kept.append(log)
            continue
        excluded, reason = state.should_exclude(log_to_record(log))
        if excluded:
            result.record_drop(reason)
            continue
        kept.append(log)

    result.kept = len(kept)
    _log(result, source)
    return kept, result


def _log(result: EgressFilterResult, source: str) -> None:
    """Emit counts at WARNING when something was dropped. Content never appears here."""
    if not result.any_dropped:
        return
    logger.warning(
        "transcript egress filter dropped journal-bearing records: %s source=%s",
        result.summary(),
        # A transcript path can name an encoded cwd; it is a path, never entry text.
        source or "<unknown>",
    )
