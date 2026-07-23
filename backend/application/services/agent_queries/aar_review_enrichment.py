"""Deterministic evidence-enrichment reads for the AAR review flags (Phase 2).

This module implements the ``ccdash-automated-aar-review`` Phase 2
("Full-Metadata Evidence Enrichment") traversal and read primitives.  It is
imported by ``aar_review.py`` and is itself part of that module's Hard
Invariant #1 dependency graph: no model/LLM client import, no
Task/Agent-dispatch helper, ever (see ``test_aar_review_no_llm_imports.py``,
which walks this graph statically).

Every function here is a pure/read-only traversal over already-materialized
DB rows -- there is no model/semantic judgment anywhere on this module's
compute path, and no row is ever written.

── T2-001: Traversal + evidence contract ────────────────────────────────────

Deterministic traversal (one direction, read-only, reuses only existing
primitives -- no new port or correlation key per D6):

    AAR doc
      --(entity_links: document -> feature)-->
    feature
      --(entity_links: feature -> document, any doc_type)-->
    linked plan/progress/PRD documents
      --(frontmatter: doc-level fields + per-task entries in a `tasks:` list)-->
    task frontmatter fields

The feature hop reuses ``resolve_feature_link`` (already defined in
``aar_review.py`` for the two-hop session-correlation path); this module
re-derives the feature->document edge independently via
``entity_links().get_links_for("feature", feature_id, "related")`` so that
enrichment is available regardless of which session-correlation strategy
resolved the session set (the two-hop-only scoping of
``detect_failure_patterns`` in ``aar_review.py`` is untouched).

Evidence contract -- the ONLY frontmatter fields eligible to be cited in a
flag's ``evidence_refs`` / ``rationale`` strings, extracted verbatim (never
paraphrased, never model-judged):

    - ``acceptance_criteria``  (doc-level list, or per-task list)
    - ``assigned_to``          (per-task list/str; doc-level ``owners`` /
                                 ``contributors`` are folded in as the same
                                 kind of assignee evidence)
    - ``assigned_model``       (per-task ``assigned_model`` or ``model``)
    - ``effort``                (per-task ``estimated_effort`` / ``effort``,
                                 or doc-level ``effort_estimate``)
    - ``phase``                 (doc-level ``phase``, or per-task ``phase``)
    - ``files_affected``        (doc-level ``files_affected`` / ``files_modified``,
                                 or per-task ``files_affected`` / ``related_files``;
                                 normalized via ``normalize_ref_path``)

Evidence is structured refs + deterministic string interpolation of the
fields above -- never a free-text judgment field, and never anything that
influences a flag's ``triggered``/``severity`` outcome (see each
``evaluate_*`` function in ``aar_review.py`` for the exact "additive evidence
only" wiring).

Resilience (T2 hard AC): when no plan/task link is resolvable --
``feature_id`` is falsy, no feature->document link exists, or every resolved
document's frontmatter has none of the six eligible fields --
``resolve_linked_task_evidence`` returns ``None``.  ``None`` is the
deterministic "no plan/task evidence available" signal; every flag's
enrichment wiring must fall back to its exact Phase-1 behavior on ``None``
(covered by ``test_aar_review_enrichment.py``'s fallback-path fixtures).  No
function in this module ever raises -- any repository failure degrades to
``None`` / an empty mapping.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from backend.application.ports import CorePorts
from backend.document_linking import normalize_ref_path

from .session_detail import (
    INCLUDE_ARTIFACTS,
    INCLUDE_LINKS,
    INCLUDE_SUBAGENTS,
    INCLUDE_TOKENS,
    SessionDetailBundle,
    get_session_detail,
)

logger = logging.getLogger(__name__)

__all__ = [
    "LinkedTaskEvidence",
    "resolve_linked_task_evidence",
    "gather_session_metadata",
]


# ── Small local helpers (deliberately NOT imported from aar_review.py -- this
# module must not import that module, to keep the dependency graph a DAG that
# a static walker can traverse without special-casing cycles) ───────────────


def _coerce_frontmatter(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _other_side(link: dict[str, Any], entity_type: str, entity_id: str) -> tuple[str, str] | None:
    """Return the (type, id) of the side of *link* that is NOT (entity_type, entity_id).

    Mirrors ``aar_review.py``'s private helper of the same name -- duplicated
    (rather than imported) so this module has no dependency on
    ``aar_review.py`` itself.
    """
    src_type = str(link.get("source_type") or "")
    src_id = str(link.get("source_id") or "")
    tgt_type = str(link.get("target_type") or "")
    tgt_id = str(link.get("target_id") or "")
    if src_type == entity_type and src_id == entity_id:
        return tgt_type, tgt_id
    if tgt_type == entity_type and tgt_id == entity_id:
        return src_type, src_id
    return None


def _flatten_str_list(value: Any) -> list[str]:
    """Deterministically flatten a frontmatter scalar/list/tuple into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_str_list(item))
        return out
    if isinstance(value, dict):
        # Structured refs (rare for these fields) contribute no bare string.
        return []
    text = str(value).strip()
    return [text] if text and text.lower() != "none" else []


# ── T2-003: doc + per-task frontmatter field extraction ─────────────────────


def _extract_doc_and_task_fields(
    frontmatter: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    """Extract the six T2-001 evidence-contract fields from one document.

    Doc-level fields are unioned with any per-task entries found in a
    ``tasks:`` frontmatter list (the same shape ``parsers/progress.py``
    parses).  Returns
    ``(acceptance_criteria, assigned_to, assigned_model, effort, phase, files_affected)``
    as raw (not yet deduped/sorted) string lists.
    """
    acceptance_criteria = _flatten_str_list(frontmatter.get("acceptance_criteria"))
    assigned_to = _flatten_str_list(frontmatter.get("assigned_to"))
    assigned_to += _flatten_str_list(frontmatter.get("owners"))
    assigned_to += _flatten_str_list(frontmatter.get("contributors"))
    assigned_model = _flatten_str_list(frontmatter.get("assigned_model"))
    effort = _flatten_str_list(frontmatter.get("effort_estimate"))
    effort += _flatten_str_list(frontmatter.get("effort"))
    phase = _flatten_str_list(frontmatter.get("phase"))
    files_affected = _flatten_str_list(frontmatter.get("files_affected"))
    files_affected += _flatten_str_list(frontmatter.get("files_modified"))

    tasks_raw = frontmatter.get("tasks")
    if isinstance(tasks_raw, list):
        for task in tasks_raw:
            if not isinstance(task, dict):
                continue
            acceptance_criteria += _flatten_str_list(task.get("acceptance_criteria"))
            assigned_to += _flatten_str_list(task.get("assigned_to"))
            assigned_model += _flatten_str_list(task.get("assigned_model"))
            assigned_model += _flatten_str_list(task.get("model"))
            effort += _flatten_str_list(task.get("estimated_effort"))
            effort += _flatten_str_list(task.get("effort"))
            phase += _flatten_str_list(task.get("phase"))
            files_affected += _flatten_str_list(task.get("files_affected"))
            files_affected += _flatten_str_list(task.get("related_files"))

    files_affected = [normalize_ref_path(str(v)) for v in files_affected if str(v or "").strip()]
    return acceptance_criteria, assigned_to, assigned_model, effort, phase, files_affected


@dataclass(frozen=True)
class LinkedTaskEvidence:
    """Deterministic, structured plan/task evidence resolved for one feature.

    Every field is a deduped, sorted tuple of raw frontmatter strings (T2-001
    evidence contract) -- never a free-text judgment.  ``source_document_ids``
    records which linked documents actually contributed at least one field,
    for traceability.
    """

    acceptance_criteria: tuple[str, ...] = ()
    assigned_to: tuple[str, ...] = ()
    assigned_model: tuple[str, ...] = ()
    effort: tuple[str, ...] = ()
    phase: tuple[str, ...] = ()
    files_affected: tuple[str, ...] = ()
    source_document_ids: tuple[str, ...] = ()


async def resolve_linked_task_evidence(
    ports: CorePorts,
    feature_id: str | None,
) -> LinkedTaskEvidence | None:
    """Traverse feature -> linked plan/progress documents -> task frontmatter.

    Read-only; reuses ``entity_links().get_links_for`` and
    ``documents().get_many_by_ids`` (D6) -- no new port or correlation key.

    Returns ``None`` when *feature_id* is falsy, when no feature->document
    link resolves, or when every resolved document's frontmatter is empty of
    the six T2-001 eligible fields.  ``None`` is the deterministic "no
    plan/task evidence available" signal each flag's Phase-1 fallback branch
    keys off of.  Never raises -- any repository failure degrades to
    ``None``.
    """
    if not feature_id:
        return None

    try:
        feature_links = await ports.storage.entity_links().get_links_for("feature", feature_id, "related")
    except Exception:
        logger.debug(
            "aar_review enrichment: feature link fetch failed for %s", feature_id, exc_info=True
        )
        return None

    doc_ids: list[str] = []
    for link in feature_links:
        other = _other_side(link, "feature", feature_id)
        if other is not None and other[0] == "document" and other[1]:
            doc_ids.append(other[1])
    doc_ids = sorted(set(doc_ids))
    if not doc_ids:
        return None

    try:
        docs_by_id = await ports.storage.documents().get_many_by_ids(doc_ids, workspace_id="default-local")
    except Exception:
        logger.debug(
            "aar_review enrichment: document fetch failed for feature %s", feature_id, exc_info=True
        )
        return None
    if not docs_by_id:
        return None

    acceptance_criteria: list[str] = []
    assigned_to: list[str] = []
    assigned_model: list[str] = []
    effort: list[str] = []
    phase: list[str] = []
    files_affected: list[str] = []
    contributing_doc_ids: list[str] = []

    for doc_id in doc_ids:
        doc_row = docs_by_id.get(doc_id)
        if not doc_row:
            continue
        frontmatter = _coerce_frontmatter(doc_row.get("frontmatter_json"))
        if not frontmatter:
            continue
        d_ac, d_assigned, d_model, d_effort, d_phase, d_files = _extract_doc_and_task_fields(frontmatter)
        if not (d_ac or d_assigned or d_model or d_effort or d_phase or d_files):
            continue
        acceptance_criteria += d_ac
        assigned_to += d_assigned
        assigned_model += d_model
        effort += d_effort
        phase += d_phase
        files_affected += d_files
        contributing_doc_ids.append(doc_id)

    if not contributing_doc_ids:
        return None

    return LinkedTaskEvidence(
        acceptance_criteria=tuple(sorted({v for v in acceptance_criteria if v})),
        assigned_to=tuple(sorted({v for v in assigned_to if v})),
        assigned_model=tuple(sorted({v for v in assigned_model if v})),
        effort=tuple(sorted({v for v in effort if v})),
        phase=tuple(sorted({v for v in phase if v})),
        files_affected=tuple(sorted({v for v in files_affected if v})),
        source_document_ids=tuple(sorted(contributing_doc_ids)),
    )


# ── T2-002 (AC-P2.2): session_detail-sourced enrichment reads ───────────────

# Deliberately excludes INCLUDE_TRANSCRIPT: no flag evaluator needs transcript
# content, and omitting it keeps this enrichment path bounded to
# already-materialized session/token/link metadata. This module never reads
# a raw JSONL session log itself -- it only ever calls
# ``session_detail.get_session_detail``, the sanctioned redaction-passed door
# (see that module's docstring for what it fetches internally).
_ENRICHMENT_INCLUDE: frozenset[str] = frozenset(
    {INCLUDE_TOKENS, INCLUDE_SUBAGENTS, INCLUDE_ARTIFACTS, INCLUDE_LINKS}
)


async def gather_session_metadata(
    ports: CorePorts,
    project_id: str | None,
    session_ids: list[str],
) -> dict[str, SessionDetailBundle]:
    """Per-session enrichment reads via ``session_detail.get_session_detail``.

    Consumes the redaction-passed session_detail bundle EXCLUSIVELY for
    tokens / context_window / detection+capture columns (all present on
    ``bundle.session``) / subagents / artifacts / links.  A missing
    *project_id*, or a per-session fetch failure/``None`` result, degrades
    that session to "no enrichment metadata available" (simply absent from
    the returned mapping) -- never raises.
    """
    bundles: dict[str, SessionDetailBundle] = {}
    if not project_id:
        return bundles
    for session_id in session_ids:
        try:
            bundle = await get_session_detail(
                project_id, session_id, ports, include=_ENRICHMENT_INCLUDE
            )
        except Exception:
            logger.debug(
                "aar_review enrichment: session_detail fetch failed for %s", session_id, exc_info=True
            )
            bundle = None
        if bundle is not None:
            bundles[session_id] = bundle
    return bundles


def session_detail_bits(bundle: SessionDetailBundle) -> list[str]:
    """Deterministic, order-stable evidence fragments from a session_detail bundle.

    Cites only the T2-002 fields (tokens / context_window / detection+capture
    columns) -- never a free-text field. Used by ``aar_review.py`` to enrich
    (never to gate) the ``context_ballooning`` flag's per-session evidence
    line.
    """
    bits: list[str] = []
    session_payload = bundle.session or {}

    context_window = str(session_payload.get("context_window") or "").strip()
    if context_window:
        bits.append(f"context_window={context_window}")

    model_slug = str(session_payload.get("model_slug") or "").strip()
    if model_slug:
        bits.append(f"model={model_slug}")

    skill_name = str(session_payload.get("skill_name") or "").strip()
    if skill_name:
        bits.append(f"skill={skill_name}")

    workflow_id = str(session_payload.get("workflow_id") or "").strip()
    if workflow_id:
        bits.append(f"workflow={workflow_id}")

    if bundle.tokens:
        observed_tokens = bundle.tokens.get("observedTokens")
        if observed_tokens:
            bits.append(f"observedTokens={observed_tokens}")

    return bits
