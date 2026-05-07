"""Shared session-feature correlation helpers (transport-neutral).

This module contains the standalone correlation pipeline extracted from
``PlanningSessionQueryService``.  It is intentionally import-free of any
board-specific concerns (grouping, card building, route hrefs) so that both
the planning session board (``planning_sessions.py``) and the feature evidence
summary service (``feature_evidence_summary.py``) can consume it without
coupling to board internals.

Public surface
--------------
``correlate_session``
    Async top-level orchestrator — mirrors the former method signature on
    ``PlanningSessionQueryService.correlate_session``.

Internal helpers
----------------
All ``_correlate_*``, ``_extract_*``, ``_feature_slug_tokens``,
``_build_index``, and ``_higher_confidence`` functions are module-private but
importable by sibling modules that need fine-grained access.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .models import (
    SessionCorrelation,
    SessionCorrelationEvidence,
)

__all__ = ["correlate_session"]

logger = logging.getLogger(__name__)

# ── Confidence ordering ───────────────────────────────────────────────────────

_CONFIDENCE_RANK: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


# ── Low-level safety helpers ─────────────────────────────────────────────────


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


# ── Confidence helper ─────────────────────────────────────────────────────────


def _higher_confidence(a: str, b: str) -> str:
    """Return whichever confidence string ranks higher."""
    return a if _CONFIDENCE_RANK.get(a, 0) >= _CONFIDENCE_RANK.get(b, 0) else b


# ── Feature slug / index helpers ──────────────────────────────────────────────


def _feature_slug_tokens(feature_id: str, feature_name: str) -> set[str]:
    """Build a set of lowercase slug tokens for a feature for command matching."""
    tokens: set[str] = set()
    for text in (feature_id, feature_name):
        clean = _safe_str(text).lower()
        if clean:
            tokens.add(clean)
            # Also add slug-normalized variant (replace spaces/underscores with hyphens)
            slug = re.sub(r"[\s_]+", "-", clean)
            if slug:
                tokens.add(slug)
    return tokens


def _build_index(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index features by id for fast lookup."""
    return {_safe_str(f.get("id")): f for f in features if _safe_str(f.get("id"))}


# ── Session field extractors ──────────────────────────────────────────────────


def _extract_task_id(session: dict[str, Any]) -> str | None:
    """Extract a task_id from a session dict (DB column name)."""
    raw = _safe_str(session.get("task_id"))
    return raw or None


def _extract_tool_summary(session: dict[str, Any]) -> list[str]:
    """Return the tool_summary list from session_forensics_json or direct field."""
    forensics = _safe_json_dict(session.get("session_forensics_json"))
    if forensics:
        tools = forensics.get("toolSummary") or forensics.get("tool_summary") or []
        if isinstance(tools, list) and tools:
            return [_safe_str(t) for t in tools if _safe_str(t)]

    # Fallback: try timeline_json for recent tool events
    timeline = _safe_json_list(session.get("timeline_json"))
    tool_names: list[str] = []
    for event in reversed(timeline[-20:]):
        if isinstance(event, dict):
            tool = _safe_str(event.get("toolName") or event.get("tool_name"))
            if tool and tool not in tool_names:
                tool_names.append(tool)
            if len(tool_names) >= 5:
                break
    return tool_names


def _extract_phase_hints(session: dict[str, Any]) -> list[str]:
    """Extract phase hint strings from session forensics or timeline."""
    forensics = _safe_json_dict(session.get("session_forensics_json"))
    raw = forensics.get("phaseHints") or forensics.get("phase_hints") or []
    hints = [_safe_str(h) for h in _safe_json_list(raw) if _safe_str(h)]
    return hints


def _extract_task_hints(session: dict[str, Any]) -> list[str]:
    """Extract task hint strings from session forensics."""
    forensics = _safe_json_dict(session.get("session_forensics_json"))
    raw = forensics.get("taskHints") or forensics.get("task_hints") or []
    hints = [_safe_str(h) for h in _safe_json_list(raw) if _safe_str(h)]
    return hints


# ── Correlation pipeline steps ────────────────────────────────────────────────


def _correlate_explicit_link(
    session: dict[str, Any],
    links: list[dict[str, Any]],
    feature_index: dict[str, dict[str, Any]],
) -> list[SessionCorrelationEvidence]:
    """Check entity_links table for session→feature links."""
    evidence: list[SessionCorrelationEvidence] = []
    session_id = _safe_str(session.get("id"))
    if not session_id:
        return evidence

    for link in links:
        src_type = _safe_str(link.get("source_type"))
        src_id = _safe_str(link.get("source_id"))
        tgt_type = _safe_str(link.get("target_type"))
        tgt_id = _safe_str(link.get("target_id"))

        feature_id: str | None = None
        if src_type == "session" and src_id == session_id and tgt_type == "feature":
            feature_id = tgt_id
        elif tgt_type == "session" and tgt_id == session_id and src_type == "feature":
            feature_id = src_id

        if feature_id and feature_id in feature_index:
            feat = feature_index[feature_id]
            evidence.append(
                SessionCorrelationEvidence(
                    source_type="explicit_link",
                    source_id=feature_id,
                    source_label=_safe_str(feat.get("name") or feat.get("id"), "feature"),
                    confidence="high",
                    detail=f"entity_links: session→feature ({feature_id})",
                )
            )

    return evidence


def _correlate_phase_hints(
    session: dict[str, Any],
) -> list[SessionCorrelationEvidence]:
    """Check session phase hints for planning references."""
    evidence: list[SessionCorrelationEvidence] = []
    hints = _extract_phase_hints(session)
    if not hints:
        return evidence

    for hint in hints:
        evidence.append(
            SessionCorrelationEvidence(
                source_type="phase_hint",
                source_id=None,
                source_label=hint,
                confidence="high",
                detail=f"phase_hint: {hint}",
            )
        )
    return evidence


def _correlate_task_hints(
    session: dict[str, Any],
) -> list[SessionCorrelationEvidence]:
    """Check session task hints for task ID references."""
    evidence: list[SessionCorrelationEvidence] = []
    hints = _extract_task_hints(session)
    if not hints:
        return evidence

    for hint in hints:
        evidence.append(
            SessionCorrelationEvidence(
                source_type="task_hint",
                source_id=None,
                source_label=hint,
                confidence="medium",
                detail=f"task_hint: {hint}",
            )
        )
    return evidence


def _correlate_command_tokens(
    session: dict[str, Any],
    feature_index: dict[str, dict[str, Any]],
) -> list[SessionCorrelationEvidence]:
    """Check if session task_id or forensics contain recognizable feature slugs."""
    evidence: list[SessionCorrelationEvidence] = []

    # Build searchable text from task_id and session forensics prompt snippets
    forensics = _safe_json_dict(session.get("session_forensics_json"))
    candidate_text_parts: list[str] = []

    task_id = _extract_task_id(session)
    if task_id:
        candidate_text_parts.append(task_id.lower())

    # Check initial prompt / command from forensics
    for key in ("initialPrompt", "initial_prompt", "command", "taskDescription", "task_description"):
        val = _safe_str(forensics.get(key))
        if val:
            candidate_text_parts.append(val.lower())

    if not candidate_text_parts:
        return evidence

    combined = " ".join(candidate_text_parts)
    for feature_id, feat in feature_index.items():
        slug_tokens = _feature_slug_tokens(feature_id, _safe_str(feat.get("name")))
        for token in slug_tokens:
            if len(token) >= 4 and token in combined:
                evidence.append(
                    SessionCorrelationEvidence(
                        source_type="command_token",
                        source_id=feature_id,
                        source_label=_safe_str(feat.get("name") or feature_id, "feature"),
                        confidence="medium",
                        detail=f"token '{token}' found in session command/task",
                    )
                )
                break  # one evidence item per feature is enough

    return evidence


def _correlate_lineage(
    session: dict[str, Any],
    session_correlations: dict[str, SessionCorrelation],
) -> list[SessionCorrelationEvidence]:
    """If parent/root session has a known feature correlation, inherit it at low confidence."""
    evidence: list[SessionCorrelationEvidence] = []

    parent_id = _safe_str(session.get("parent_session_id"))
    root_id = _safe_str(session.get("root_session_id"))

    for ancestor_id in (parent_id, root_id):
        if not ancestor_id or ancestor_id == _safe_str(session.get("id")):
            continue
        ancestor_corr = session_correlations.get(ancestor_id)
        if ancestor_corr and ancestor_corr.feature_id and ancestor_corr.confidence in ("high", "medium"):
            evidence.append(
                SessionCorrelationEvidence(
                    source_type="lineage",
                    source_id=ancestor_corr.feature_id,
                    source_label=_safe_str(ancestor_corr.feature_name, "feature"),
                    confidence="low",
                    detail=f"inherited from ancestor session {ancestor_id}",
                )
            )
            break  # one lineage item is sufficient

    return evidence


# ── Public orchestrator ───────────────────────────────────────────────────────


async def correlate_session(
    session: dict[str, Any],
    links: list[dict[str, Any]],
    features: list[dict[str, Any]],
    all_sessions: list[dict[str, Any]] | None = None,
    prior_correlations: dict[str, SessionCorrelation] | None = None,
) -> SessionCorrelation:
    """Correlate a single session to planning entities.

    Checks evidence sources in priority order and accumulates all evidence.
    The overall confidence is the highest individual evidence confidence.

    This is the transport-neutral, service-agnostic version of the correlation
    pipeline.  It is called directly by consumers such as
    ``PlanningSessionQueryService`` and (in P3-003) by
    ``FeatureEvidenceSummaryService`` for heuristic correlation of unlinked
    sessions.

    Args:
        session: Raw session dict from the DB.
        links: All entity_links rows for the project (bidirectional).
        features: All feature dicts for the project.
        all_sessions: All project sessions (unused directly here; kept for
            forward-compatibility with callers that pass it).
        prior_correlations: Correlations already computed for other sessions,
            keyed by session_id (used for lineage inheritance).

    Returns:
        ``SessionCorrelation`` with accumulated evidence and resolved
        feature/phase binding at the highest confidence found.
    """
    prior_correlations = prior_correlations or {}

    feature_index = _build_index(features)
    all_evidence: list[SessionCorrelationEvidence] = []

    # 1. Explicit links (entity_links table)
    all_evidence.extend(_correlate_explicit_link(session, links, feature_index))

    # 2. Phase hints from session forensics
    all_evidence.extend(_correlate_phase_hints(session))

    # 3. Task hints from session forensics
    all_evidence.extend(_correlate_task_hints(session))

    # 4. Command tokens — feature slug in task_id or prompt
    all_evidence.extend(_correlate_command_tokens(session, feature_index))

    # 5. Lineage — inherit from parent/root session
    all_evidence.extend(_correlate_lineage(session, prior_correlations))

    if not all_evidence:
        return SessionCorrelation(confidence="unknown", evidence=[])

    # Overall confidence = highest individual evidence confidence
    best_confidence = "unknown"
    for ev in all_evidence:
        best_confidence = _higher_confidence(best_confidence, ev.confidence)

    # Resolve primary feature binding from highest-confidence explicit evidence
    feature_id: str | None = None
    feature_name: str | None = None

    # Prefer explicit_link > phase_hint > command_token > lineage for feature binding
    priority_order = ["explicit_link", "phase_hint", "command_token", "lineage"]
    for source_type in priority_order:
        for ev in all_evidence:
            if ev.source_type == source_type and ev.source_id:
                feat = feature_index.get(ev.source_id)
                if feat:
                    feature_id = ev.source_id
                    feature_name = _safe_str(feat.get("name")) or feature_id
                    break
        if feature_id:
            break

    # Resolve phase number from phase hints
    phase_number: int | None = None
    phase_title: str | None = None
    phase_evidence = [ev for ev in all_evidence if ev.source_type == "phase_hint"]
    if phase_evidence:
        hint_label = phase_evidence[0].source_label
        match = re.search(r"\b(\d+)\b", hint_label)
        if match:
            phase_number = int(match.group(1))
        phase_title = hint_label or None

    # Resolve task from task hints
    task_id: str | None = None
    task_title: str | None = None
    task_evidence = [ev for ev in all_evidence if ev.source_type == "task_hint"]
    if task_evidence:
        task_id = task_evidence[0].source_label or None
        task_title = task_id

    return SessionCorrelation(
        feature_id=feature_id,
        feature_name=feature_name,
        phase_number=phase_number,
        phase_title=phase_title,
        task_id=task_id,
        task_title=task_title,
        confidence=best_confidence,
        evidence=all_evidence,
    )
