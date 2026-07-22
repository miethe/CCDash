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
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.document_linking import extract_frontmatter_references, normalize_ref_path
from backend.observability.otel import log_aar_review_candidate
from backend.services.workflow_effectiveness import detect_failure_patterns

from ._filters import collect_source_refs, resolve_project_scope
from .cache import memoized_query
from .models import AARReviewDTO, AARReviewFlag

logger = logging.getLogger(__name__)

__all__ = ["AARReviewQueryService"]


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
) -> tuple[list[str], float, str | None]:
    """Resolve a document's direct session correlation from ``entity_links`` rows.

    Falls back to the AAR document's own (possibly not-yet-synced) frontmatter
    session references only when ``entity_links`` has no direct session link at
    all -- in that fallback case the result is reported exactly as the sync
    engine would report it (``explicit_session_ref``, confidence 1.0), since
    that is the only strategy an unmaterialized frontmatter ref can represent.
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
        return [], 0.0, None

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
) -> tuple[list[str], float, str | None, str | None]:
    """Resolve document->session(s), trying direct links then the two-hop fallback.

    Returns ``(session_ids, correlation_confidence, correlation_strategy, feature_id)``.
    ``feature_id`` is populated only for the two-hop strategy (used downstream
    to scope the read-only ``detect_failure_patterns`` lookup).
    """
    doc_links = await ports.storage.entity_links().get_links_for("document", document_id, "related")

    session_ids, confidence, strategy = resolve_direct_session_links(
        document_id, doc_links, frontmatter_refs.get("sessionRefs", []) or []
    )
    if session_ids:
        return session_ids, confidence, strategy, None

    feature_hit = resolve_feature_link(document_id, doc_links)
    if feature_hit is None:
        return [], 0.0, None, None

    feature_id, feature_confidence, _feature_strategy = feature_hit
    feature_links = await ports.storage.entity_links().get_links_for("feature", feature_id, "related")
    two_hop_ids = resolve_feature_session_ids(feature_id, feature_links)
    if not two_hop_ids:
        return [], 0.0, None, None

    return two_hop_ids, round(feature_confidence, 3), "two_hop_doc_feature_session", feature_id


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


def evaluate_context_ballooning(
    session_rows: list[dict[str, Any]],
    threshold_pct: float,
) -> AARReviewFlag:
    evidence: list[str] = []
    peak: float | None = None
    for row in session_rows:
        pct = _context_utilization_pct(row)
        if pct is None:
            continue
        if peak is None or pct > peak:
            peak = pct
        if pct >= threshold_pct:
            evidence.append(f"{row.get('id')}: {pct:.1f}% context utilization")

    if peak is None:
        return AARReviewFlag(
            flag_id="context_ballooning", triggered=False, severity="low",
            evidence_refs=[], rationale="insufficient token data",
        )
    if evidence:
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
) -> AARReviewFlag:
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
        return AARReviewFlag(
            flag_id="missing_artifacts", triggered=True, severity="medium",
            evidence_refs=missing,
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
) -> AARReviewFlag:
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
        evidence.append(f"{session_id}: general-purpose used for {extension} work (expected {specialist})")

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
) -> AARReviewFlag:
    if not feature_scope_available:
        return AARReviewFlag(
            flag_id="stack_ineffectiveness", triggered=False, severity="low",
            evidence_refs=[], rationale="no feature scope available for failure-pattern lookup",
        )

    evidence: list[str] = []
    any_stack_resolved = False
    for session_id in session_ids:
        extension = _dominant_extension(file_paths_by_session.get(session_id, []))
        lookup = _EXTENSION_STACK_LOOKUP.get(extension) if extension else None
        if lookup is None:
            continue
        any_stack_resolved = True
        stack, _specialist = lookup
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

    if evidence:
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


# ── Verdict combinator ───────────────────────────────────────────────────────


def compute_verdict(
    correlation_confidence: float,
    has_sessions: bool,
    flags: list[AARReviewFlag],
    min_confidence: float,
) -> tuple[str, list[str]]:
    if not has_sessions:
        return "surface_only", ["no correlated sessions found"]
    if correlation_confidence < min_confidence:
        return (
            "surface_only",
            [
                f"correlation confidence {correlation_confidence:.2f} is below the floor "
                f"{min_confidence:.2f}; low-confidence correlations never auto-escalate"
            ],
        )
    triggered = [flag for flag in flags if flag.triggered]
    if not triggered:
        return "surface_only", ["no flags triggered"]
    flag_names = ", ".join(flag.flag_id for flag in triggered)
    return "deep_review_recommended", [f"{len(triggered)} flag(s) triggered: {flag_names}"]


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

        session_ids, confidence, strategy, feature_id = await _correlate(
            ports, resolved_document_id, frontmatter_refs
        )

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

        failure_items: list[dict[str, Any]] = []
        if feature_id:
            try:
                failure_payload = await detect_failure_patterns(
                    ports.storage.db, scope.project, feature_id=feature_id, limit=20, offset=0,
                )
                failure_items = [item for item in failure_payload.get("items", []) if isinstance(item, dict)]
            except Exception:
                failure_items = []

        flags = [
            evaluate_context_ballooning(session_rows, config.CCDASH_AAR_REVIEW_CONTEXT_BALLOON_PCT),
            evaluate_missing_artifacts(claimed_files, file_paths_by_session),
            evaluate_generic_agent_vs_specialist(session_rows, file_paths_by_session),
            evaluate_stack_ineffectiveness(
                session_ids, file_paths_by_session, failure_items,
                feature_scope_available=feature_id is not None,
            ),
        ]

        verdict, reasons = compute_verdict(
            confidence, bool(session_ids), flags, config.CCDASH_AAR_REVIEW_MIN_CONFIDENCE,
        )

        result = AARReviewDTO(
            status="ok",
            document_id=resolved_document_id,
            session_refs=session_ids,
            correlation_confidence=round(confidence, 3),
            correlation_strategy=strategy,
            flags=flags,
            verdict=verdict,
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
