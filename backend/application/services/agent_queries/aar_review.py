"""Deterministic AAR-document-to-session triage service (Tier 1 MVP).

``AARReviewQueryService`` resolves an agent-written AAR document to the
session(s) it describes and computes a model-free triage verdict from data
already materialized in the DB.  Every flag is a threshold/lookup/regex check
over already-fetched rows -- there is no model/LLM call anywhere on this
module's compute path (ccdash-aar-review-mvp §8 Hard Invariant; a reviewer
should be able to grep this file for any LLM/agent-invocation import and find
none).

Correlation reuses only existing, already-materialized primitives:

- ``entity_links().get_links_for(...)`` -- the same call shape used by
  ``reporting.py``'s ``generate_aar`` -- for the confidence-scored
  document->session and document->feature links the sync engine already
  writes (``explicit_session_ref`` 1.0, ``task_session_ref`` 0.96, and the
  doc->feature inheritance/ref strategies in the 0.64-1.0 band; see
  ``sync_engine.py``'s link-rebuild pass).
- ``document_linking.extract_frontmatter_references`` as a fallback when the
  AAR document's frontmatter has not yet been synced into ``entity_links``
  (rare, but possible for a freshly-written AAR) -- this fallback covers only
  the direct ``explicit_session_ref`` case; see the Completion Report for the
  documented deviation from ``session_correlation.correlate_session`` (that
  helper's confidence semantics are qualitative "high/medium/low", not the
  numeric 1.0/0.96/0.64-1.0 tiers this contract must reuse verbatim -- the
  numeric tiers live on the ``entity_links`` rows themselves).

No row is ever written by this module.  ``detect_failure_patterns`` (unlike
its sibling ``get_workflow_effectiveness``) has no write path, so it is safe
to call read-only once a feature scope is known via the two-hop strategy.

── Phase 2 (T2-001): enrichment traversal + evidence contract ──────────────

Phase 2 ("Full-Metadata Evidence Enrichment") ADDS richer evidence to the
four flags below by additionally traversing:

    AAR doc -> feature (via entity_links, independent of which session-
               correlation strategy resolved the session set)
             -> linked plan/progress documents (via entity_links)
             -> task frontmatter (doc-level fields + per-task entries in a
                ``tasks:`` list)

The traversal and the six eligible evidence fields (``acceptance_criteria``,
``assigned_to``, ``assigned_model``, ``effort``, ``phase``,
``files_affected``) are implemented in ``aar_review_enrichment.py`` --see
that module's docstring for the full contract.  Phase 2 additionally reads
per-session ``tokens`` / ``context_window`` / detection+capture columns /
``subagents`` / ``artifacts`` / ``links`` via
``aar_review_enrichment.gather_session_metadata``, which consumes
``session_detail.get_session_detail`` EXCLUSIVELY (never a raw JSONL read).

Hard rule (unchanged from P1, restated for Phase 2): every flag's
threshold/derivation logic is IDENTICAL to Phase 1.  Enrichment only ever
appends a deterministic evidence string to an already-triggered flag, or
enriches an already-non-triggering flag's rationale -- it never flips
``triggered``, never changes ``severity``, and never introduces a new
verdict.  When no plan/task link resolves (``LinkedTaskEvidence`` is
``None``) or no session_detail bundle is available for a session, every
flag falls back byte-for-byte to its Phase 1 behavior -- a missing link is a
contract state, not a bug (see ``test_aar_review_enrichment.py``'s
``*_p1_fallback`` fixtures for both paths, per flag).

── Phase 3 (T3-001..T3-004): SkillMeat artifact-review linkage + 5th flag ──

Phase 3 ("Artifact-Review Linkage + 5th Flag") ADDS two things, both
strictly READ-ONLY against ``artifact_intelligence
.ArtifactIntelligenceQueryService`` (HARD INVARIANT #2: CCDash EMITS ONLY --
zero SkillMeat/skills/agents catalog mutation, artifact-creation, or
ARC/swarm-dispatch call anywhere on this module's compute path; this module
only ever calls that service's ``get_rankings`` read method):

  1. (T3-001) ``evaluate_stack_ineffectiveness`` gains an optional
     ``artifact_rankings`` lookup (specialist agent id, lowercased ->
     already-fetched SkillMeat ranking row).  When the flag has already
     triggered on the Phase 1/2 failure-pattern correlation, this ADDS one
     evidence line per implicated specialist that has a known ranking --
     the trigger gate itself is byte-for-byte unchanged.
  2. (T3-002/T3-003) A 5th flag, ``new_skill_or_agent_need``
     (``evaluate_new_skill_or_agent_need``): a deterministic aggregation
     rule over this project's already-PERSISTED ``aar_reviews`` rows (via
     ``backend.db.repositories.aar_reviews``, read-only -- ``get_by_project``
     only, never ``upsert``) -- counting how many *distinct* AAR documents
     triggered ``generic_agent_vs_specialist`` or ``missing_artifacts``
     within a bounded lookback window (``CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS``),
     compared against a static, env-configurable threshold
     (``CCDASH_AAR_NEW_SKILL_THRESHOLD``).  When triggered, its evidence
     optionally cites a plain descriptive SkillMeat-ranking string for this
     document's implicated specialist(s) (T3-003) -- e.g. "consider a
     specialist for domain X; SkillMeat shows ranking Y" -- never an action,
     never a catalog write.

This flag participates in ``compute_verdict``'s existing generic
"any triggered flag -> deep_review_recommended" rule identically to the
other four -- ``compute_verdict`` itself is UNCHANGED (it already iterates
``flags`` generically; there is no per-flag-id special case to add or
remove).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import aiosqlite

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.db.repositories.aar_reviews import (
    PostgresAarReviewsRepository,
    SqliteAarReviewsRepository,
)
from backend.document_linking import extract_frontmatter_references, normalize_ref_path
from backend.observability.otel import log_aar_review_candidate
from backend.services.workflow_effectiveness import detect_failure_patterns

from ._filters import _coerce_datetime, collect_source_refs, resolve_project_scope, resolve_time_window
from .aar_review_enrichment import (
    LinkedTaskEvidence,
    gather_session_metadata,
    resolve_linked_task_evidence,
    session_detail_bits,
)
from .artifact_intelligence import ArtifactIntelligenceQueryService
from .cache import memoized_query
from .models import AARReviewCorrelation, AARReviewDTO, AARReviewFlag
from .session_detail import SessionDetailBundle

logger = logging.getLogger(__name__)

__all__ = ["AARReviewQueryService"]

# Correlation strategy label used when a document->feature->session two-hop
# resolves the session set (see `_correlate` below). Ambiguity detection in
# `compute_verdict` is scoped to exactly this strategy per the OQ-2 decision:
# a two-hop hit that resolves multiple candidate sessions with no dominance
# signal is an ambiguous tie and must route to `human_triage_required`; a
# direct-link strategy resolving multiple tied sessions is untouched by that
# rule (pre-existing behavior, not part of this change).
_TWO_HOP_STRATEGY = "two_hop_doc_feature_session"


# ── Static, versioned lookup tables (checked-in data, not inferred) ─────────
# Extension -> (stack label, specialist agent). Mirrors this repo's own
# documented Agent Assignment Quick Reference (dev-execution skill): React/UI
# work -> ui-engineer-enhanced, TypeScript/general backend work ->
# backend-typescript-architect. Deliberately static per the Risk Areas
# mitigation -- if a case can't be resolved deterministically it must fall
# through to "unresolved", never a guess.
_EXTENSION_STACK_LOOKUP: dict[str, tuple[str, str]] = {
    ".tsx": ("typescript-react", "ui-engineer-enhanced"),
    ".jsx": ("javascript-react", "ui-engineer-enhanced"),
    ".css": ("css", "ui-engineer-enhanced"),
    ".scss": ("css", "ui-engineer-enhanced"),
    ".ts": ("typescript", "backend-typescript-architect"),
    ".js": ("javascript", "backend-typescript-architect"),
    ".py": ("python", "backend-typescript-architect"),
    ".go": ("go", "backend-typescript-architect"),
    ".rs": ("rust", "backend-typescript-architect"),
    ".java": ("java", "backend-typescript-architect"),
    ".rb": ("ruby", "backend-typescript-architect"),
    ".sql": ("sql", "backend-typescript-architect"),
}

_GENERIC_AGENT_NAMES = {"general-purpose", "general purpose", "generalpurpose", "general_purpose"}

# T3-002: the two Phase 1/2 flag ids whose historical (persisted) trigger
# occurrences feed the ``new_skill_or_agent_need`` aggregation. A recurring
# "generic agent used for specialist work" or "claimed artifact not produced"
# pattern across a project's AAR reviews is the deterministic proxy for "this
# project keeps needing a skill/agent it does not have" -- never a model
# judgment, just a static set-membership + threshold check.
_NEW_SKILL_TRIGGER_FLAG_IDS: frozenset[str] = frozenset({"generic_agent_vs_specialist", "missing_artifacts"})


# ── Small safety helpers ─────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_frontmatter(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _link_metadata(link: dict[str, Any]) -> dict[str, Any]:
    raw = link.get("metadata_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _link_confidence(link: dict[str, Any], default: float = 0.0) -> float:
    try:
        value = link.get("confidence")
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _other_side(link: dict[str, Any], entity_type: str, entity_id: str) -> tuple[str, str] | None:
    """Return the (type, id) of the side of *link* that is NOT (entity_type, entity_id)."""
    src_type = str(link.get("source_type") or "")
    src_id = str(link.get("source_id") or "")
    tgt_type = str(link.get("target_type") or "")
    tgt_id = str(link.get("target_id") or "")
    if src_type == entity_type and src_id == entity_id:
        return tgt_type, tgt_id
    if tgt_type == entity_type and tgt_id == entity_id:
        return src_type, src_id
    return None


# ── Correlation (pure, unit-testable without a DB) ───────────────────────────


def resolve_direct_session_links(
    document_id: str,
    links: list[dict[str, Any]],
    frontmatter_session_refs: list[str],
) -> tuple[list[str], float | None, str | None]:
    """Resolve a document's direct session correlation from ``entity_links`` rows.

    Falls back to the AAR document's own (possibly not-yet-synced) frontmatter
    session references only when ``entity_links`` has no direct session link at
    all -- in that fallback case the result is reported exactly as the sync
    engine would report it (``explicit_session_ref``, confidence 1.0), since
    that is the only strategy an unmaterialized frontmatter ref can represent.

    Returns confidence ``None`` (never ``0.0``) when nothing resolves at all --
    ``None`` is the deterministic "correlation failed entirely" signal that
    ``compute_verdict``'s hard rule keys off of.
    """
    candidates: list[tuple[str, float, str]] = []
    for link in links:
        other = _other_side(link, "document", document_id)
        if other is None or other[0] != "session" or not other[1]:
            continue
        meta = _link_metadata(link)
        strategy = str(meta.get("linkStrategy") or "entity_link")
        confidence = _link_confidence(link, default=0.9)
        candidates.append((other[1], confidence, strategy))

    if not candidates:
        explicit_refs = sorted({ref.strip() for ref in frontmatter_session_refs if str(ref or "").strip()})
        if explicit_refs:
            return explicit_refs, 1.0, "explicit_session_ref"
        return [], None, None

    max_confidence = max(confidence for _, confidence, _ in candidates)
    top = [(sid, strategy) for sid, confidence, strategy in candidates if confidence == max_confidence]
    session_ids = sorted({sid for sid, _ in top})
    return session_ids, max_confidence, top[0][1]


def resolve_feature_link(
    document_id: str,
    links: list[dict[str, Any]],
) -> tuple[str, float, str] | None:
    """Resolve the highest-confidence document->feature link, if any."""
    candidates: list[tuple[str, float, str]] = []
    for link in links:
        other = _other_side(link, "document", document_id)
        if other is None or other[0] != "feature" or not other[1]:
            continue
        meta = _link_metadata(link)
        strategy = str(meta.get("linkStrategy") or "feature_ref")
        confidence = _link_confidence(link, default=0.7)
        candidates.append((other[1], confidence, strategy))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0]


def resolve_feature_session_ids(feature_id: str, feature_links: list[dict[str, Any]]) -> list[str]:
    """Return session ids linked to *feature_id* via ``entity_links``."""
    ids: set[str] = set()
    for link in feature_links:
        other = _other_side(link, "feature", feature_id)
        if other is not None and other[0] == "session" and other[1]:
            ids.add(other[1])
    return sorted(ids)


async def _correlate(
    ports: CorePorts,
    document_id: str,
    frontmatter_refs: dict[str, Any],
) -> tuple[list[str], float | None, str | None, str | None, list[dict[str, Any]]]:
    """Resolve document->session(s), trying direct links then the two-hop fallback.

    Returns
    ``(session_ids, correlation_confidence, correlation_strategy, feature_id, doc_links)``.
    ``feature_id`` is populated only for the two-hop strategy (used downstream
    to scope the read-only ``detect_failure_patterns`` lookup). ``confidence``
    is ``None`` exactly when ``session_ids`` is empty -- correlation failed
    entirely -- which is the invariant ``compute_verdict`` relies on for its
    "missing confidence -> human_triage_required" hard rule. ``doc_links`` is
    the document's raw ``entity_links`` rows (Phase 2 addition, T2-003):
    returned so ``get_review`` can independently re-resolve a feature link
    for enrichment purposes even when session correlation itself resolved via
    a *direct* link (not the two-hop strategy) -- this must never change
    ``feature_id``'s own two-hop-only semantics above.
    """
    doc_links = await ports.storage.entity_links().get_links_for("document", document_id, "related")

    session_ids, confidence, strategy = resolve_direct_session_links(
        document_id, doc_links, frontmatter_refs.get("sessionRefs", []) or []
    )
    if session_ids:
        return session_ids, confidence, strategy, None, doc_links

    feature_hit = resolve_feature_link(document_id, doc_links)
    if feature_hit is None:
        return [], None, None, None, doc_links

    feature_id, feature_confidence, _feature_strategy = feature_hit
    feature_links = await ports.storage.entity_links().get_links_for("feature", feature_id, "related")
    two_hop_ids = resolve_feature_session_ids(feature_id, feature_links)
    if not two_hop_ids:
        return [], None, None, None, doc_links

    return two_hop_ids, round(feature_confidence, 3), _TWO_HOP_STRATEGY, feature_id, doc_links


# ── Flags (pure, unit-testable against already-fetched rows) ────────────────


def _dominant_extension(file_paths: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for path in file_paths:
        suffix = Path(str(path or "")).suffix.lower()
        if suffix:
            counts[suffix] = counts.get(suffix, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _resolved_specialists(session_ids: list[str], file_paths_by_session: dict[str, list[str]]) -> list[str]:
    """Deterministic, sorted set of specialist agent names implicated by *session_ids*.

    Reuses the exact same static ``_EXTENSION_STACK_LOOKUP`` dominant-extension
    resolution as ``evaluate_generic_agent_vs_specialist`` /
    ``evaluate_stack_ineffectiveness`` -- never a new heuristic. Used by T3-003
    to scope the 5th flag's optional SkillMeat-ranking evidence to the
    specialist domain(s) this specific document's sessions actually touched
    (possibly empty when no session's dominant extension resolves).
    """
    specialists: set[str] = set()
    for session_id in session_ids:
        extension = _dominant_extension(file_paths_by_session.get(session_id, []))
        lookup = _EXTENSION_STACK_LOOKUP.get(extension) if extension else None
        if lookup is not None:
            specialists.add(lookup[1])
    return sorted(specialists)


def _artifact_ranking_summary(ranking_row: dict[str, Any]) -> str:
    """Deterministic metric summary string quoting an already-fetched SkillMeat ranking row.

    Cites only fields already computed/persisted by the (out-of-process)
    SkillMeat ranking pipeline -- verbatim, never a judgment of its own.
    HARD INVARIANT #2 (CCDash emits only): this function only ever reads
    from *ranking_row*, itself sourced exclusively from
    ``ArtifactIntelligenceQueryService.get_rankings`` (a read method); it
    never writes, creates, or dispatches anything.
    """
    bits: list[str] = []
    for label in ("cost_usd", "efficiency_score", "quality_score", "success_score"):
        value = ranking_row.get(label)
        if value is not None:
            bits.append(f"{label}={value}")
    period = str(ranking_row.get("period") or "").strip()
    summary = ", ".join(bits) if bits else "no scored metrics available"
    return f"{summary} (period={period})" if period else summary


async def _resolve_artifact_rankings_by_specialist(
    context: RequestContext,
    ports: CorePorts,
    project_id: str | None,
) -> dict[str, dict[str, Any]]:
    """Best-effort, READ-ONLY SkillMeat ranking lookup keyed by specialist agent id (lowercased).

    Calls exactly one existing read method --
    ``ArtifactIntelligenceQueryService.get_rankings`` -- which itself only
    reads ``artifact_ranking`` rows already materialized by the
    out-of-process SkillMeat sync exporter (HARD INVARIANT #2: CCDash emits
    only; zero SkillMeat/skills/agents catalog mutation, artifact-creation,
    or ARC/swarm-dispatch call anywhere on this path). Degrades to an empty
    mapping (never raises) when *project_id* is falsy, the read itself fails
    (e.g. a storage port/fake that predates this integration), or the read
    genuinely finds nothing -- "no ranking evidence" is a contract state,
    not a bug.
    """
    if not project_id:
        return {}
    try:
        dto = await ArtifactIntelligenceQueryService().get_rankings(context, ports, project_id, limit=200)
    except Exception:
        logger.debug("aar_review: artifact ranking read failed for project %s", project_id, exc_info=True)
        return {}
    if dto.status != "ok":
        return {}
    by_specialist: dict[str, dict[str, Any]] = {}
    for row in dto.rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("artifact_id") or "").strip().lower()
        if key and key not in by_specialist:
            by_specialist[key] = row
    return by_specialist


def _context_utilization_pct(session_row: dict[str, Any]) -> float | None:
    """Return the session's context-utilization percentage, or None if unknown.

    ``context_window_size`` defaults to ``0`` (not NULL) at the DB layer, so a
    window of 0 is treated as "measurement never taken" rather than a real
    zero-size window -- this is the deterministic rule that distinguishes
    "insufficient data" from "genuinely low utilization".
    """
    try:
        window = int(session_row.get("context_window_size") or 0)
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        return None

    try:
        pct = float(session_row.get("context_utilization_pct") or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    if pct > 0:
        return pct

    try:
        current_tokens = float(session_row.get("current_context_tokens") or 0.0)
    except (TypeError, ValueError):
        current_tokens = 0.0
    if current_tokens <= 0:
        return None
    return round((current_tokens / window) * 100.0, 2)


def _linked_plan_context_line(linked_evidence: "LinkedTaskEvidence | None") -> str | None:
    """One deterministic evidence line citing linked-plan phase/effort, or ``None``.

    Shared by ``evaluate_context_ballooning`` and ``evaluate_stack_ineffectiveness``
    (T2-004 / T2-007) -- both attach the same "linked plan context" shape when
    a plan/task link resolved *and* declares a phase or effort.  Returns
    ``None`` (never an empty-string line) when there is nothing to cite --
    the Phase 1 fallback path for both flags.
    """
    if linked_evidence is None:
        return None
    bits: list[str] = []
    if linked_evidence.phase:
        bits.append(f"phase={','.join(linked_evidence.phase)}")
    if linked_evidence.effort:
        bits.append(f"effort={','.join(linked_evidence.effort)}")
    if not bits:
        return None
    return f"linked plan context: {'; '.join(bits)}"


def evaluate_context_ballooning(
    session_rows: list[dict[str, Any]],
    threshold_pct: float,
    *,
    linked_evidence: "LinkedTaskEvidence | None" = None,
    session_metadata: "dict[str, SessionDetailBundle] | None" = None,
) -> AARReviewFlag:
    """AC-4 (P1) + T2-004 (P2): context-window-utilization threshold check.

    ``linked_evidence`` and ``session_metadata`` are Phase 2 additions
    (defaults ``None``): when supplied they ADD one deterministic evidence
    string each (linked-plan phase/effort context; per-session
    context_window/model/skill/token detail sourced exclusively from a
    ``session_detail`` bundle) -- neither ever changes ``triggered`` or
    ``severity``.  With both omitted this function is byte-for-byte the
    Phase 1 implementation.
    """
    evidence: list[str] = []
    peak: float | None = None
    for row in session_rows:
        pct = _context_utilization_pct(row)
        if pct is None:
            continue
        if peak is None or pct > peak:
            peak = pct
        if pct >= threshold_pct:
            line = f"{row.get('id')}: {pct:.1f}% context utilization"
            if session_metadata:
                bundle = session_metadata.get(str(row.get("id") or ""))
                if bundle is not None:
                    detail_bits = session_detail_bits(bundle)
                    if detail_bits:
                        line += f" ({', '.join(detail_bits)})"
            evidence.append(line)

    if peak is None:
        return AARReviewFlag(
            flag_id="context_ballooning", triggered=False, severity="low",
            evidence_refs=[], rationale="insufficient token data",
        )
    if evidence:
        plan_context = _linked_plan_context_line(linked_evidence)
        if plan_context:
            evidence.append(plan_context)
        return AARReviewFlag(
            flag_id="context_ballooning", triggered=True, severity="high",
            evidence_refs=evidence,
            rationale=f"context utilization reached {peak:.1f}% (threshold {threshold_pct:.1f}%)",
        )
    return AARReviewFlag(
        flag_id="context_ballooning", triggered=False, severity="low",
        evidence_refs=[],
        rationale=f"context utilization peaked at {peak:.1f}% (below {threshold_pct:.1f}% threshold)",
    )


def claimed_files_from_frontmatter(frontmatter: dict[str, Any]) -> list[str]:
    """Extract the AAR document's own ``files_affected`` claim list, normalized."""
    raw = frontmatter.get("files_affected")
    if raw is None:
        raw = frontmatter.get("filesAffected")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return sorted({normalize_ref_path(str(v)) for v in raw if str(v or "").strip()})


def evaluate_missing_artifacts(
    claimed_files: list[str],
    file_paths_by_session: dict[str, list[str]],
    *,
    linked_evidence: "LinkedTaskEvidence | None" = None,
) -> AARReviewFlag:
    """AC-5 (P1) + T2-005 (P2): claimed-vs-produced file diff.

    ``linked_evidence`` is a Phase 2 addition (default ``None``): when
    supplied AND the flag has already triggered on the Phase 1
    claimed-vs-produced diff, this additionally set-differences the linked
    task's ``files_affected`` frontmatter against the produced+claimed
    files and appends one more evidence line for any plan-declared file that
    is neither claimed nor produced. This is always additive -- it never
    changes ``triggered``/``severity``, and it never runs when
    ``claimed_files`` is empty (the exact Phase 1 "no claim to check"
    fallback is preserved byte-for-byte).
    """
    if not claimed_files:
        return AARReviewFlag(
            flag_id="missing_artifacts", triggered=False, severity="low",
            evidence_refs=[], rationale="no claimed artifacts to check",
        )

    produced: set[str] = set()
    for paths in file_paths_by_session.values():
        produced.update(normalize_ref_path(str(p)) for p in paths if str(p or "").strip())

    missing = sorted({path for path in claimed_files if path and path not in produced})
    if missing:
        evidence = list(missing)
        if linked_evidence is not None and linked_evidence.files_affected:
            plan_gap = sorted(
                {p for p in linked_evidence.files_affected if p and p not in produced and p not in claimed_files}
            )
            if plan_gap:
                evidence.append(
                    "plan-declared file(s) neither claimed nor produced: " + ", ".join(plan_gap)
                )
        return AARReviewFlag(
            flag_id="missing_artifacts", triggered=True, severity="medium",
            evidence_refs=evidence,
            rationale=f"{len(missing)} of {len(claimed_files)} claimed file(s) were not found among session-produced files.",
        )
    return AARReviewFlag(
        flag_id="missing_artifacts", triggered=False, severity="low",
        evidence_refs=[],
        rationale="all claimed files were found among session-produced files",
    )


def _session_agent_names(session_row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    subagent_type = str(session_row.get("subagent_type") or "").strip()
    if subagent_type:
        names.append(subagent_type)

    raw = session_row.get("agents_used_json")
    parsed: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = []
    if isinstance(parsed, list):
        names.extend(str(v).strip() for v in parsed if str(v or "").strip())
    return names


def evaluate_generic_agent_vs_specialist(
    session_rows: list[dict[str, Any]],
    file_paths_by_session: dict[str, list[str]],
    *,
    linked_evidence: "LinkedTaskEvidence | None" = None,
    session_metadata: "dict[str, SessionDetailBundle] | None" = None,
) -> AARReviewFlag:
    """AC-6 (P1) + T2-006 (P2): generic-agent-used-for-specialist-domain check.

    Trigger gate is UNCHANGED from Phase 1 -- a session must use a generic
    agent name AND the dominant file extension must resolve via the static
    ``_EXTENSION_STACK_LOOKUP``. ``linked_evidence`` (default ``None``) adds
    a set-membership comparison against the linked task's
    ``assigned_to``/``assigned_model`` frontmatter: when the plan's declared
    assignee(s) don't include the extension-lookup's specialist, that is
    cited as extra evidence. ``session_metadata`` (default ``None``) adds
    the actual ``subagent_type`` values observed via a ``session_detail``
    bundle's ``subagents`` segment. The Phase 1 static keyword->specialist
    lookup remains the fallback whenever no plan link resolves -- neither
    addition ever changes ``triggered``/``severity``.
    """
    evidence: list[str] = []
    any_agent_data = False
    for row in session_rows:
        session_id = str(row.get("id") or "")
        names = _session_agent_names(row)
        if names:
            any_agent_data = True
        if not any(name.lower() in _GENERIC_AGENT_NAMES for name in names):
            continue
        extension = _dominant_extension(file_paths_by_session.get(session_id, []))
        lookup = _EXTENSION_STACK_LOOKUP.get(extension) if extension else None
        if lookup is None:
            continue
        _, specialist = lookup
        line = f"{session_id}: general-purpose used for {extension} work (expected {specialist})"

        if linked_evidence is not None and (linked_evidence.assigned_to or linked_evidence.assigned_model):
            plan_assignees = sorted(set(linked_evidence.assigned_to) | set(linked_evidence.assigned_model))
            if plan_assignees and specialist not in plan_assignees:
                line += f"; plan declared assignee(s) {plan_assignees}"

        if session_metadata:
            bundle = session_metadata.get(session_id)
            if bundle is not None and bundle.subagents:
                subagent_types = sorted(
                    {
                        str(sub.get("subagent_type") or "").strip()
                        for sub in bundle.subagents
                        if str(sub.get("subagent_type") or "").strip()
                    }
                )
                if subagent_types:
                    line += f"; subagents observed: {', '.join(subagent_types)}"

        evidence.append(line)

    if evidence:
        return AARReviewFlag(
            flag_id="generic_agent_vs_specialist", triggered=True, severity="medium",
            evidence_refs=evidence,
            rationale="A generic agent was invoked for work matching a known specialist domain.",
        )
    rationale = "no agent-usage data" if not any_agent_data else "no generic-agent/specialist mismatch detected"
    return AARReviewFlag(
        flag_id="generic_agent_vs_specialist", triggered=False, severity="low",
        evidence_refs=[], rationale=rationale,
    )


def evaluate_stack_ineffectiveness(
    session_ids: list[str],
    file_paths_by_session: dict[str, list[str]],
    failure_items: list[dict[str, Any]],
    *,
    feature_scope_available: bool,
    linked_evidence: "LinkedTaskEvidence | None" = None,
    artifact_rankings: dict[str, dict[str, Any]] | None = None,
) -> AARReviewFlag:
    """AC-7 (P1) + T2-007 (P2) + T3-001 (P3): resolved-stack-vs-failure-pattern correlation.

    ``feature_scope_available`` gating and the failure-pattern-hit threshold
    are UNCHANGED from Phase 1. ``linked_evidence`` (default ``None``) only
    appends one deterministic "linked plan context" evidence line (phase /
    effort) when the flag has already triggered -- see
    ``_linked_plan_context_line``. ``artifact_rankings`` (default ``None``,
    T3-001) is a READ-ONLY lookup (specialist agent id, lowercased ->
    already-fetched SkillMeat ranking row -- see
    ``_resolve_artifact_rankings_by_specialist``): when the flag has already
    triggered AND a triggering session's resolved specialist has a known
    ranking, this appends one additional evidence line per implicated
    specialist (``_artifact_ranking_summary``). Neither addition ever
    changes ``triggered``/``severity`` -- with both omitted this function is
    byte-for-byte the Phase 1/2 implementation.
    """
    if not feature_scope_available:
        return AARReviewFlag(
            flag_id="stack_ineffectiveness", triggered=False, severity="low",
            evidence_refs=[], rationale="no feature scope available for failure-pattern lookup",
        )

    evidence: list[str] = []
    any_stack_resolved = False
    triggering_specialists: set[str] = set()
    for session_id in session_ids:
        extension = _dominant_extension(file_paths_by_session.get(session_id, []))
        lookup = _EXTENSION_STACK_LOOKUP.get(extension) if extension else None
        if lookup is None:
            continue
        any_stack_resolved = True
        stack, specialist = lookup
        for item in failure_items:
            if not isinstance(item, dict):
                continue
            evidence_summary = item.get("evidenceSummary") or {}
            session_hits = set(item.get("sessionIds") or []) | set(
                evidence_summary.get("representativeSessionIds") or []
            )
            if session_id in session_hits:
                title = str(item.get("title") or item.get("patternType") or "failure pattern")
                severity = str(item.get("severity") or "medium")
                evidence.append(f"{session_id}: {stack} stack, {title} ({severity})")
                triggering_specialists.add(specialist)

    if evidence:
        plan_context = _linked_plan_context_line(linked_evidence)
        if plan_context:
            evidence.append(plan_context)
        if artifact_rankings:
            for specialist in sorted(triggering_specialists):
                ranking_row = artifact_rankings.get(specialist.lower())
                if ranking_row is not None:
                    evidence.append(
                        f"SkillMeat ranking for specialist '{specialist}': "
                        f"{_artifact_ranking_summary(ranking_row)}"
                    )
        return AARReviewFlag(
            flag_id="stack_ineffectiveness", triggered=True, severity="high",
            evidence_refs=evidence,
            rationale="Failure/retry patterns were detected for a resolved technology stack.",
        )
    rationale = "stack unresolved" if not any_stack_resolved else "no failure/retry pattern detected for the resolved stack"
    return AARReviewFlag(
        flag_id="stack_ineffectiveness", triggered=False, severity="low",
        evidence_refs=[], rationale=rationale,
    )


def count_recent_flag_triggers(
    persisted_rows: list[dict[str, Any]],
    flag_ids: frozenset[str],
    *,
    lookback_start: datetime,
) -> tuple[int, list[str]]:
    """T3-002: deterministic aggregation over already-PERSISTED ``aar_reviews`` rows.

    Counts *distinct* ``aar_document_id`` values whose ``generated_at`` falls
    within ``[lookback_start, now]`` and whose ``flags`` JSON has at least
    one entry in *flag_ids* with ``triggered: true``.

    Dedup-by-document (not by row) is deliberate: one AAR document fans out
    into N ``aar_reviews`` rows (one per resolved session,
    ``aar_reviews.build_aar_review_rows``), each carrying byte-identical
    ``flags`` JSON -- counting per-row would over-count a single AAR write
    by its session fan-out factor, which is not a "recurrence" signal at
    all. A row with an unparsable ``generated_at`` or ``flags`` payload is
    skipped (never raises) -- this function never raises.

    Returns ``(count, sorted_document_ids)``; the document-id list is
    returned for evidence/testability, not just the count.
    """
    triggering_doc_ids: set[str] = set()
    for row in persisted_rows:
        if not isinstance(row, dict):
            continue
        generated_at = _coerce_datetime(row.get("generated_at"))
        if generated_at is None or generated_at < lookback_start:
            continue
        doc_id = str(row.get("aar_document_id") or "")
        if not doc_id:
            continue
        raw_flags = row.get("flags")
        if isinstance(raw_flags, str):
            try:
                parsed_flags = json.loads(raw_flags)
            except Exception:
                parsed_flags = []
        elif isinstance(raw_flags, list):
            parsed_flags = raw_flags
        else:
            parsed_flags = []
        if any(
            isinstance(entry, dict) and entry.get("flag_id") in flag_ids and entry.get("triggered")
            for entry in parsed_flags
        ):
            triggering_doc_ids.add(doc_id)
    return len(triggering_doc_ids), sorted(triggering_doc_ids)


def evaluate_new_skill_or_agent_need(
    trigger_count: int,
    threshold: int,
    *,
    lookback_days: int,
    implicated_specialists: list[str] | None = None,
    artifact_rankings: dict[str, dict[str, Any]] | None = None,
) -> AARReviewFlag:
    """T3-002/T3-003 (P3): 5th flag -- recurring generic-agent/missing-artifact pattern.

    ``trigger_count`` is the output of ``count_recent_flag_triggers`` (the
    number of distinct AAR documents in this project that triggered
    ``generic_agent_vs_specialist`` or ``missing_artifacts`` within the
    lookback window); ``threshold`` is the static, env-configurable floor
    (``CCDASH_AAR_NEW_SKILL_THRESHOLD``). Both are plain int comparisons --
    no model/semantic judgment.

    ``implicated_specialists`` / ``artifact_rankings`` (both default
    ``None``, T3-003) are READ-ONLY additions: when the flag triggers AND a
    specialist implicated by *this* document's own sessions
    (``_resolved_specialists``) has a known SkillMeat ranking
    (``_resolve_artifact_rankings_by_specialist``), this appends one plain
    descriptive evidence string per matching specialist -- e.g. "consider a
    specialist for domain 'ui-engineer-enhanced': SkillMeat shows
    cost_usd=...". This is descriptive evidence only, never an action --
    HARD INVARIANT #2 (CCDash emits only) means this function never calls a
    SkillMeat write/create/dispatch method; it only formats strings from
    data the caller already fetched via a read method.

    This flag registers alongside the other four exactly the same way --
    ``compute_verdict`` is not special-cased for it; a triggered
    ``new_skill_or_agent_need`` flows into the existing "any triggered flag
    -> deep_review_recommended" rule identically to the other four.
    """
    if trigger_count < threshold:
        return AARReviewFlag(
            flag_id="new_skill_or_agent_need", triggered=False, severity="low",
            evidence_refs=[],
            rationale=(
                f"{trigger_count} generic-agent/missing-artifact trigger(s) across this "
                f"project's AAR reviews in the last {lookback_days}d (below threshold {threshold})"
            ),
        )

    evidence: list[str] = [
        f"{trigger_count} generic-agent/missing-artifact trigger(s) across this project's "
        f"AAR reviews in the last {lookback_days}d (threshold {threshold})"
    ]
    if artifact_rankings and implicated_specialists:
        for specialist in implicated_specialists:
            ranking_row = artifact_rankings.get(specialist.lower())
            if ranking_row is not None:
                evidence.append(
                    f"consider a specialist for domain '{specialist}': SkillMeat shows "
                    f"{_artifact_ranking_summary(ranking_row)}"
                )

    return AARReviewFlag(
        flag_id="new_skill_or_agent_need", triggered=True, severity="medium",
        evidence_refs=evidence,
        rationale=(
            f"{trigger_count} generic-agent-vs-specialist/missing-artifacts trigger(s) recurred "
            f"in the last {lookback_days}d, meeting the threshold ({threshold}); a recurring "
            "pattern like this suggests a missing specialist skill/agent for this domain."
        ),
    )


# ── Verdict combinator ───────────────────────────────────────────────────────


_TriageVerdict = Literal["surface_only", "deep_review_recommended", "human_triage_required"]


def compute_verdict(
    correlation_confidence: float | None,
    session_ids: list[str],
    correlation_strategy: str | None,
    flags: list[AARReviewFlag],
    min_confidence: float,
) -> tuple[_TriageVerdict, list[str]]:
    """Deterministic 3-value triage verdict (OQ-2 resolution, locked decision).

    Decision order (each rule short-circuits the next):
    1. ``correlation_confidence`` missing/null -> ``human_triage_required``
       (hard rule; null confidence is exactly the "correlation failed
       entirely" signal from ``_correlate``, e.g. zero session_ids).
    2. ``correlation_confidence < min_confidence`` -> ``human_triage_required``.
    3. Two-hop correlation resolved multiple candidate sessions with no
       single dominant one (ambiguous tie) -> ``human_triage_required``.
       Scoped to ``_TWO_HOP_STRATEGY`` only -- the correlation *strategy*
       itself (direct vs two-hop) must never by itself force human triage,
       since two-hop is the dominant real-world path (Rationale, T1-003).
    4. Otherwise (confidence >= floor, unambiguous): preserve the Tier-1 MVP's
       existing flag-signal mapping verbatim -- any triggered flag escalates
       to ``deep_review_recommended``; no triggered flags -> ``surface_only``.
    """
    if correlation_confidence is None:
        return (
            "human_triage_required",
            ["correlation confidence is missing/null; routing to human triage per the OQ-2 hard rule"],
        )
    if correlation_confidence < min_confidence:
        return (
            "human_triage_required",
            [
                f"correlation confidence {correlation_confidence:.2f} is below the floor "
                f"{min_confidence:.2f}; low-confidence correlations require human triage"
            ],
        )
    if correlation_strategy == _TWO_HOP_STRATEGY and len(session_ids) > 1:
        return (
            "human_triage_required",
            [
                f"two-hop correlation resolved {len(session_ids)} candidate sessions with no "
                "single dominant match; ambiguous ties require human triage"
            ],
        )
    triggered = [flag for flag in flags if flag.triggered]
    if not triggered:
        return "surface_only", ["no flags triggered"]
    flag_names = ", ".join(flag.flag_id for flag in triggered)
    return "deep_review_recommended", [f"{len(triggered)} flag(s) triggered: {flag_names}"]


# ── T3-002: persisted-row aggregation plumbing (read-only) ──────────────────


def _aar_reviews_repository(db: Any) -> "SqliteAarReviewsRepository | PostgresAarReviewsRepository":
    """Return the ``aar_reviews`` reader for *db*, mirroring the backfill script's dispatch.

    Read-only usage in this module -- ``get_by_project`` only, never
    ``upsert``/``upsert_many``. Duplicated (rather than shared) from
    ``backend.scripts.aar_reviews_backfill._aar_reviews_repo`` so this
    module has no dependency on a top-level script.
    """
    if isinstance(db, aiosqlite.Connection):
        return SqliteAarReviewsRepository(db)
    return PostgresAarReviewsRepository(db)


async def _resolve_new_skill_trigger_count(
    ports: CorePorts,
    project_id: str | None,
    *,
    lookback_days: int,
) -> tuple[int, list[str]]:
    """T3-002: fetch this project's persisted ``aar_reviews`` rows and aggregate.

    READ-ONLY: calls exactly one repository method (``get_by_project``) --
    never ``upsert``. Degrades to ``(0, [])`` (never raises) when
    *project_id* is falsy or the read itself fails (e.g. a ``db`` fake in a
    unit test that predates this integration) -- "no aggregation data" is a
    contract state, not a bug.
    """
    if not project_id:
        return 0, []
    try:
        repo = _aar_reviews_repository(ports.storage.db)
        persisted_rows = await repo.get_by_project(project_id, limit=1000, offset=0)
    except Exception:
        logger.debug(
            "aar_review: aar_reviews aggregation read failed for project %s", project_id, exc_info=True
        )
        return 0, []
    lookback_start, _lookback_end = resolve_time_window(default_days=lookback_days)
    return count_recent_flag_triggers(persisted_rows, _NEW_SKILL_TRIGGER_FLAG_IDS, lookback_start=lookback_start)


# ── Service ───────────────────────────────────────────────────────────────


def _aar_review_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    document_id: str,
    **_: Any,
) -> dict[str, Any]:
    return {"document_id": document_id}


class AARReviewQueryService:
    """Deterministic AAR-document-to-session triage (no model calls, no writes)."""

    @memoized_query("aar_review", param_extractor=_aar_review_params)
    async def get_review(
        self,
        context: RequestContext,
        ports: CorePorts,
        document_id: str,
    ) -> AARReviewDTO:
        scope = resolve_project_scope(context, ports)
        if scope is None:
            return AARReviewDTO(
                status="error", document_id=document_id, reasons=["project scope could not be resolved"],
                generated_at=_now_iso(), source_refs=[document_id],
            )

        doc_row = await ports.storage.documents().get_by_id(document_id, workspace_id="default-local")  # TODO(workspace-routing)
        if doc_row is None:
            try:
                doc_row = await ports.storage.documents().get_by_path(
                    scope.project.id, document_id, workspace_id="default-local",  # TODO(workspace-routing)
                )
            except Exception:
                doc_row = None
        if doc_row is None:
            return AARReviewDTO(
                status="error", document_id=document_id, reasons=["document not found"],
                generated_at=_now_iso(), source_refs=[document_id],
            )

        resolved_document_id = str(doc_row.get("id") or document_id)
        frontmatter = _safe_frontmatter(doc_row.get("frontmatter_json"))
        frontmatter_refs = extract_frontmatter_references(frontmatter)

        session_ids, confidence, strategy, feature_id, doc_links = await _correlate(
            ports, resolved_document_id, frontmatter_refs
        )

        # Phase 2 (T2-003): re-resolve a feature link for enrichment purposes
        # independent of which session-correlation strategy resolved the
        # session set -- `feature_id` above stays two-hop-only (unchanged
        # P1 scoping for `detect_failure_patterns` below). When the
        # session-correlation path already found a feature via the two-hop
        # strategy, reuse it (avoids a duplicate lookup, same result).
        enrichment_feature_id = feature_id
        if enrichment_feature_id is None:
            feature_hit = resolve_feature_link(resolved_document_id, doc_links)
            if feature_hit is not None:
                enrichment_feature_id = feature_hit[0]
        linked_evidence = await resolve_linked_task_evidence(ports, enrichment_feature_id)

        session_rows: list[dict[str, Any]] = []
        file_paths_by_session: dict[str, list[str]] = {}
        doc_project_id = str(doc_row.get("project_id") or "") or None
        for session_id in session_ids:
            try:
                row = await ports.storage.sessions().get_by_id(
                    session_id, doc_project_id, workspace_id="default-local",  # TODO(workspace-routing)
                )
            except Exception:
                row = None
            if row is not None:
                session_rows.append(row)
            try:
                updates = await ports.storage.sessions().get_file_updates(session_id)
            except Exception:
                updates = []
            file_paths_by_session[session_id] = [
                str(update.get("file_path") or "") for update in updates if str(update.get("file_path") or "").strip()
            ]

        claimed_files = claimed_files_from_frontmatter(frontmatter)

        # Phase 2 (T2-002 / AC-P2.2): per-session tokens/context_window/
        # detection+capture columns/subagents/artifacts/links, sourced
        # EXCLUSIVELY from the redaction-passed `session_detail` bundle.
        session_metadata = await gather_session_metadata(ports, doc_project_id, session_ids)

        failure_items: list[dict[str, Any]] = []
        if feature_id:
            try:
                failure_payload = await detect_failure_patterns(
                    ports.storage.db, scope.project, feature_id=feature_id, limit=20, offset=0,
                )
                failure_items = [item for item in failure_payload.get("items", []) if isinstance(item, dict)]
            except Exception:
                failure_items = []

        # Phase 3 (T3-001/T3-003): READ-ONLY SkillMeat ranking lookup, keyed
        # by specialist agent id -- degrades to `{}` on any failure (Hard
        # Invariant #2: CCDash emits only; see `_resolve_artifact_rankings_by_specialist`).
        artifact_rankings = await _resolve_artifact_rankings_by_specialist(
            context, ports, doc_project_id or scope.project.id,
        )
        implicated_specialists = _resolved_specialists(session_ids, file_paths_by_session)

        # Phase 3 (T3-002): 5th flag aggregation over already-PERSISTED
        # `aar_reviews` rows for this project -- independent of the current
        # document's own correlation/session data (see module docstring).
        new_skill_trigger_count, _new_skill_doc_ids = await _resolve_new_skill_trigger_count(
            ports, doc_project_id or scope.project.id, lookback_days=config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS,
        )

        flags = [
            evaluate_context_ballooning(
                session_rows, config.CCDASH_AAR_REVIEW_CONTEXT_BALLOON_PCT,
                linked_evidence=linked_evidence, session_metadata=session_metadata,
            ),
            evaluate_missing_artifacts(
                claimed_files, file_paths_by_session, linked_evidence=linked_evidence,
            ),
            evaluate_generic_agent_vs_specialist(
                session_rows, file_paths_by_session,
                linked_evidence=linked_evidence, session_metadata=session_metadata,
            ),
            evaluate_stack_ineffectiveness(
                session_ids, file_paths_by_session, failure_items,
                feature_scope_available=feature_id is not None,
                linked_evidence=linked_evidence, artifact_rankings=artifact_rankings,
            ),
            evaluate_new_skill_or_agent_need(
                new_skill_trigger_count, config.CCDASH_AAR_NEW_SKILL_THRESHOLD,
                lookback_days=config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS,
                implicated_specialists=implicated_specialists, artifact_rankings=artifact_rankings,
            ),
        ]

        verdict, reasons = compute_verdict(
            confidence, session_ids, strategy, flags, config.CCDASH_AAR_REVIEW_MIN_CONFIDENCE,
        )

        result = AARReviewDTO(
            status="ok",
            document_id=resolved_document_id,
            correlation=AARReviewCorrelation(
                strategy=strategy,
                confidence=round(confidence, 3) if confidence is not None else None,
                session_ids=session_ids,
                feature_id=feature_id,
            ),
            flags=flags,
            triage_verdict=verdict,
            reasons=reasons,
            generated_at=_now_iso(),
            source_refs=collect_source_refs(resolved_document_id, session_ids, [feature_id] if feature_id else []),
        )

        try:
            log_aar_review_candidate(
                document_id=resolved_document_id,
                session_refs=session_ids,
                verdict=verdict,
                triggered_flags=[flag.flag_id for flag in flags if flag.triggered],
            )
        except Exception:  # never let observability break a successful response
            logger.debug("aar_review_candidate log emission failed", exc_info=True)

        return result
