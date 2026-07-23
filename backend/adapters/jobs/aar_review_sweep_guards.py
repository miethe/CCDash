"""Pure, deterministic guard functions for the AAR-review autonomous sweep worker.

Phase 6 (``ccdash-automated-aar-review-v1``, T6-003/T6-004) implements two
self-recursion / idempotency guards that gate ``AARReviewSweepJob``'s
(``backend/adapters/jobs/aar_review_sweep_job.py``) input and write path.
Both guards are PURE functions over already-fetched rows -- neither performs
any I/O, content-sniffing, or model/LLM call (Hard Invariant #1, unchanged
from the rest of this feature; see ``test_aar_review_no_llm_imports.py``'s
static-walk contract, which this module's zero-import-of-anything-heavy
surface trivially satisfies).

Guard 1 -- provenance self-exclusion (T6-003)
-----------------------------------------------
Excludes any session whose OWN provenance columns (``skill_name`` /
``workflow_id`` -- the detection/capture columns already materialized on the
``sessions`` table; see root CLAUDE.md "Session columns -- detection,
pricing, capture") identify it as having been produced BY the aar-review
worker itself. This is checked exclusively against those two columns --
NEVER against the session's transcript/tool-call/frontmatter content -- so
that a self-referential session (one AAR-review sweep triaging a document
written by, or describing, a PRIOR aar-review sweep) can never be fed back
into triage input, no matter what its body contains. Without this guard the
worker could review documents/sessions it itself produced, entering an
unbounded self-reference loop.

Guard 2 -- idempotent dedup ledger (T6-004)
--------------------------------------------
Uses the existing ``(aar_document_id, session_id)`` composite primary key on
``aar_reviews`` (P1) as the dedup ledger: any pair already present as a
persisted row is considered "already triaged" and must never be re-persisted
by a later sweep tick -- including across a worker restart, since the ledger
is read fresh from the DB at the start of every sweep tick (never held only
in process memory; see ``aar_review_sweep_job.py``'s ``_execute_inner``,
which re-reads the ledger from the repository on every call). This module
ONLY builds/queries the in-memory *set* representation of that ledger from
already-fetched repository rows -- it never talks to the DB itself.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = [
    "AAR_REVIEW_SELF_SKILL_NAME",
    "AAR_REVIEW_SELF_WORKFLOW_ID_PREFIX",
    "TriagedPair",
    "is_self_referential_session_row",
    "filter_self_referential_session_ids",
    "build_triaged_pair_ledger",
    "is_already_triaged",
    "filter_untriaged_pairs",
    "select_incremental_documents",
]

TriagedPair = tuple[str, str]

# The aar-review worker's own reserved skill-name / workflow-id-prefix.  Any
# session whose provenance metadata matches either marker was itself produced
# by (a run of) the aar-review sweep and must be excluded UNCONDITIONALLY
# from the triage input set -- see module docstring, Guard 1.
AAR_REVIEW_SELF_SKILL_NAME = "aar-review"
AAR_REVIEW_SELF_WORKFLOW_ID_PREFIX = "aar-review-"


def is_self_referential_session_row(session_row: Mapping[str, Any]) -> bool:
    """Guard 1: True when *session_row*'s OWN provenance columns mark it as aar-review-originated.

    Checks ``skill_name`` (exact match, case-insensitive) and ``workflow_id``
    (reserved-prefix match, case-insensitive) ONLY -- these are the two
    detection/capture columns already materialized on the ``sessions`` table.
    Never inspects any other field (transcript, tool calls, frontmatter, ...)
    -- that is the "provenance metadata columns ONLY, never content-sniff"
    rule from the dispatch contract.
    """
    skill_name = str(session_row.get("skill_name") or "").strip().lower()
    if skill_name == AAR_REVIEW_SELF_SKILL_NAME:
        return True
    workflow_id = str(session_row.get("workflow_id") or "").strip().lower()
    if workflow_id.startswith(AAR_REVIEW_SELF_WORKFLOW_ID_PREFIX):
        return True
    return False


def filter_self_referential_session_ids(
    session_ids: Iterable[str],
    session_rows_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    """Partition *session_ids* into ``(allowed, excluded)`` via Guard 1 -- FAIL CLOSED.

    A session id with NO corresponding row in *session_rows_by_id* (row
    missing / ``None`` / the caller's fetch failed) is treated as EXCLUDED,
    not allowed. This is a deliberate fail-closed default for a
    self-recursion guard: an undeterminable provenance is a POTENTIAL
    self-reference, and the safe failure mode is to under-triage a session
    rather than risk feeding an aar-review-originated session back into
    triage input. A practical consequence: if session-fetch is broken
    workspace-wide, this sweep triages nothing for the affected sessions
    rather than silently losing self-recursion protection.

    Only a session whose row IS resolvable AND whose provenance columns
    positively indicate ordinary (non-aar-review) origin is ALLOWED.
    """
    allowed: list[str] = []
    excluded: list[str] = []
    for session_id in session_ids:
        row = session_rows_by_id.get(session_id)
        if row is None or is_self_referential_session_row(row):
            excluded.append(session_id)
        else:
            allowed.append(session_id)
    return allowed, excluded


def build_triaged_pair_ledger(rows: Iterable[Mapping[str, Any]]) -> set[TriagedPair]:
    """Guard 2: build the in-memory dedup-ledger set from already-persisted ``aar_reviews`` rows.

    *rows* is whatever the repository already returned (e.g. a lightweight
    ``(aar_document_id, session_id)``-only projection) -- this function only
    reads those two keys off each row; it never queries anything itself.
    """
    ledger: set[TriagedPair] = set()
    for row in rows:
        doc_id = str(row.get("aar_document_id") or "")
        session_id = str(row.get("session_id") or "")
        if doc_id and session_id:
            ledger.add((doc_id, session_id))
    return ledger


def is_already_triaged(ledger: set[TriagedPair], aar_document_id: str, session_id: str) -> bool:
    """Guard 2: True when ``(aar_document_id, session_id)`` is already on *ledger*."""
    return (aar_document_id, session_id) in ledger


def filter_untriaged_pairs(
    candidate_pairs: Iterable[TriagedPair],
    ledger: set[TriagedPair],
) -> tuple[list[TriagedPair], list[TriagedPair]]:
    """Partition *candidate_pairs* into ``(new, already_triaged)`` via Guard 2.

    Idempotency contract: re-running this function with the SAME *ledger*
    snapshot and SAME *candidate_pairs* always returns the same partition --
    this is what makes a worker restart safe.  The ledger is read fresh from
    the DB at the top of every sweep tick (see ``aar_review_sweep_job.py``),
    so a pair persisted by a prior (possibly crashed) run is recognized as
    "already triaged" by the next run with zero in-process state carried
    over the restart boundary.
    """
    new_pairs: list[TriagedPair] = []
    already_triaged: list[TriagedPair] = []
    for pair in candidate_pairs:
        if pair in ledger:
            already_triaged.append(pair)
        else:
            new_pairs.append(pair)
    return new_pairs, already_triaged


def select_incremental_documents(
    doc_rows: Iterable[Mapping[str, Any]],
    watermark: str,
) -> list[Mapping[str, Any]]:
    """Mirror the ``CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`` approach: scope to changed/new rows only.

    Returns every row in *doc_rows* whose ``updated_at`` (falling back to
    ``created_at`` when absent) sorts strictly AFTER *watermark*.  An empty
    *watermark* (the worker's first tick for a project, or a project with no
    prior checkpoint) selects every row -- "no checkpoint yet" is a contract
    state, not a bug.  Pure string comparison on ISO-8601 timestamps
    (lexicographic ordering is correct for that format) -- never a
    semantic/model judgment.
    """
    if not watermark:
        return list(doc_rows)
    selected: list[Mapping[str, Any]] = []
    for row in doc_rows:
        stamp = str(row.get("updated_at") or row.get("created_at") or "")
        if stamp > watermark:
            selected.append(row)
    return selected
