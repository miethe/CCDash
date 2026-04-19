"""Document-first feature discovery.

Scan Implementation Plans → PRDs → Progress dirs and merge into Feature objects.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.models import (
    EntityDates,
    FeatureDocumentCoverage,
    Feature,
    FeaturePhase,
    FeaturePrimaryDocuments,
    FeatureQualitySignals,
    LinkedFeatureRef,
    LinkedDocument,
    PlanningEffectiveStatus,
    PlanningMismatchState,
    PlanningPhaseBatch,
    PlanningPhaseBatchReadiness,
    PlanningStatusEvidence,
    PlanningStatusProvenance,
    ProjectTask,
    TimelineEvent,
)
from backend.document_linking import (
    alias_tokens_from_path,
    canonical_project_path,
    canonical_slug,
    classify_doc_category,
    classify_doc_type,
    extract_frontmatter_references,
    feature_slug_from_path,
    infer_project_root,
    is_generic_alias_token,
    is_feature_like_token,
    normalize_doc_status,
    normalize_ref_path,
)
from backend.parsers.status_writer import FrontmatterParseError, update_frontmatter_field
from backend.date_utils import (
    choose_earliest,
    choose_first,
    choose_latest,
    file_metadata_dates,
    make_date_value,
    normalize_iso_date,
)

logger = logging.getLogger("ccdash")

# ── Status helpers ──────────────────────────────────────────────────

# Ordering for "furthest progression" inference.
# `deferred` is completion-equivalent with `done`.
_STATUS_ORDER = {"backlog": 0, "in-progress": 1, "review": 2, "done": 3, "deferred": 3}
_TERMINAL_STATUSES = {"done", "deferred"}
_DOC_COMPLETION_STATUSES = {"completed", "deferred", "inferred_complete"}
_DOC_WRITE_THROUGH_TYPES = {"prd", "implementation_plan", "phase_plan"}
_INFERRED_COMPLETE_STATUS = "inferred_complete"
_DATE_CONFIDENCE_LEVELS = {"high", "medium", "low"}
_FEATURE_PRIORITY_ORDER = {
    "critical": 5,
    "highest": 5,
    "high": 4,
    "p1": 4,
    "medium": 3,
    "normal": 3,
    "p2": 3,
    "low": 2,
    "minor": 2,
    "p3": 2,
    "deferred": 1,
}
_FEATURE_RISK_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "minimal": 1,
}
_TEST_IMPACT_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "none": 1,
}
_READINESS_ORDER = {
    "blocked": 1,
    "at_risk": 2,
    "planning": 3,
    "in_progress": 4,
    "review": 5,
    "ready": 6,
}


_STATUS_MAP = {
    "completed": "done",
    "complete": "done",
    "done": "done",
    "in_progress": "in-progress",
    "active": "in-progress",
    "review": "review",
    "ready": "backlog",
    "draft": "backlog",
    "blocked": "backlog",
    "planning": "backlog",
    "pending": "backlog",
    "not_started": "backlog",
    "reference": "done",
    "deferred": "deferred",
    "defer": "deferred",
    "postponed": "deferred",
    "skipped": "deferred",
    "wont_do": "deferred",
    "won_t_do": "deferred",
    "inferred_complete": "done",
}

_TASK_STATUS_MAP = {
    "completed": "done",
    "complete": "done",
    "done": "done",
    "in_progress": "in-progress",
    "review": "review",
    "blocked": "backlog",
    "pending": "backlog",
    "not_started": "backlog",
    "deferred": "deferred",
    "defer": "deferred",
    "postponed": "deferred",
    "skipped": "deferred",
    "wont_do": "deferred",
    "won_t_do": "deferred",
    "inferred_complete": "done",
}


def _normalize_status_token(raw: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower())
    return re.sub(r"_+", "_", token).strip("_")


def _map_status(raw: str) -> str:
    return _STATUS_MAP.get(_normalize_status_token(raw), "backlog")


def _map_task_status(raw: str) -> str:
    return _TASK_STATUS_MAP.get(_normalize_status_token(raw), "backlog")


def _is_completion_equivalent_doc_status(raw: str) -> bool:
    normalized = normalize_doc_status(raw, default="")
    return normalized in _DOC_COMPLETION_STATUSES


# ── Frontmatter extraction ──────────────────────────────────────────

def _extract_frontmatter(text: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _to_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        result: list[str] = []
        for entry in value:
            result.extend(_to_string_list(entry))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for nested in value.values():
            result.extend(_to_string_list(nested))
        return result
    return []


def _normalize_feature_ref(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    path_slug = feature_slug_from_path(raw)
    if path_slug:
        return path_slug
    normalized_path = normalize_ref_path(raw)
    if normalized_path and normalized_path.endswith(".md"):
        stem = Path(normalized_path).stem.lower()
        if is_feature_like_token(stem):
            return stem
    token = raw.lower()
    return token if is_feature_like_token(token) else ""


def _normalize_feature_refs(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_feature_ref(value)
        if not token or token in seen:
            continue
        seen.add(token)
        items.append(token)
    return items


def _normalize_linked_feature_refs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        feature = str(entry.get("feature") or "").strip().lower()
        if not feature:
            continue
        relation_type = str(entry.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_")
        source = str(entry.get("source") or "").strip().lower().replace("-", "_").replace(" ", "_")
        key = (feature, relation_type, source)
        if key in seen:
            continue
        seen.add(key)
        confidence: float | None = None
        confidence_raw = entry.get("confidence")
        if confidence_raw is not None:
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except Exception:
                confidence = None
        refs.append(
            {
                "feature": feature,
                "type": relation_type,
                "source": source,
                "confidence": confidence,
                "notes": str(entry.get("notes") or ""),
                "evidence": [
                    str(v)
                    for v in _to_string_list(entry.get("evidence"))
                    if isinstance(v, str) and str(v).strip()
                ],
            }
        )
    return refs


def _normalize_choice_token(raw: Any) -> str:
    token = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", token).strip("_")


def _to_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return None
        try:
            return int(float(token))
        except Exception:
            return None
    return None


def _pick_highest_ranked(values: list[str], ranking: dict[str, int]) -> str:
    best_value = ""
    best_rank = -1
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        rank = ranking.get(_normalize_choice_token(value), 0)
        if rank > best_rank:
            best_rank = rank
            best_value = value
    return best_value


def _pick_latest_document(docs: list["LinkedDocument"]) -> Optional["LinkedDocument"]:
    def _doc_sort_value(doc: "LinkedDocument") -> str:
        updated = getattr(getattr(doc, "dates", None), "updatedAt", None)
        if getattr(updated, "value", ""):
            return str(updated.value)
        created = getattr(getattr(doc, "dates", None), "createdAt", None)
        if getattr(created, "value", ""):
            return str(created.value)
        return ""

    if not docs:
        return None
    ordered = sorted(docs, key=_doc_sort_value, reverse=True)
    return ordered[0] if ordered else None


def _make_status_evidence(
    *,
    evidence_id: str,
    label: str,
    detail: str,
    source_type: str,
    source_id: str,
    source_path: str,
) -> PlanningStatusEvidence:
    return PlanningStatusEvidence(
        id=evidence_id,
        label=label,
        detail=detail,
        sourceType=source_type,
        sourceId=source_id,
        sourcePath=source_path,
    )


def _batch_sort_key(batch_id: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", str(batch_id or ""))
    if match:
        return (int(match.group(1)), str(batch_id or ""))
    return (10_000, str(batch_id or ""))


def _extract_related_doc_refs(refs: dict[str, Any]) -> list[str]:
    values = [
        *[str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)],
        *[str(v) for v in refs.get("sourceDocumentRefs", []) if isinstance(v, str)],
        *[str(v) for v in refs.get("prdRefs", []) if isinstance(v, str)],
    ]
    related_refs: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        related_refs.append(value)
    return related_refs


def _safe_list(raw: Any) -> list[Any]:
    return raw if isinstance(raw, list) else []


def _normalize_feature_finding_severity(raw: Any) -> str:
    token = _normalize_choice_token(raw)
    if not token:
        return "unspecified"
    if token in {"critical", "high", "medium", "low"}:
        return token
    return "unspecified"


def _normalize_doc_type_token(raw: Any) -> str:
    token = _normalize_choice_token(raw)
    aliases = {
        "implementationplan": "implementation_plan",
        "phaseplan": "phase_plan",
        "designspec": "design_doc",
        "design_spec": "design_doc",
        "design_doc": "design_doc",
        "specification": "spec",
    }
    return aliases.get(token, token or "document")


def _slug_from_path(path: Path) -> str:
    """Derive a slug from a file's stem, stripping version suffixes for matching."""
    return path.stem.lower()


def _base_slug(slug: str) -> str:
    """Strip trailing version markers (-v1, -v1.5, -v2) for related-feature matching."""
    return canonical_slug(slug)


def _project_relative(path: Path, project_root: Path) -> str:
    return canonical_project_path(path, project_root)


def _extract_doc_metadata(
    path: Path,
    project_root: Path,
    frontmatter: dict[str, Any],
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> dict[str, Any]:
    project_rel = _project_relative(path, project_root)
    refs = extract_frontmatter_references(frontmatter)
    slug = _slug_from_path(path)
    status_raw = str(frontmatter.get("status") or "")
    status_normalized = normalize_doc_status(status_raw, default="")
    lineage_family_raw = str(frontmatter.get("lineage_family") or frontmatter.get("feature_family") or "").strip()
    lineage_parent_raw = str(
        frontmatter.get("lineage_parent")
        or frontmatter.get("parent_feature")
        or frontmatter.get("parent_feature_slug")
        or frontmatter.get("extends_feature")
        or frontmatter.get("derived_from")
        or frontmatter.get("supersedes")
        or ""
    ).strip()
    lineage_children_raw = _to_string_list(
        frontmatter.get("lineage_children")
        or frontmatter.get("child_features")
        or frontmatter.get("superseded_by")
    )
    lineage_type = str(
        frontmatter.get("lineage_type")
        or frontmatter.get("lineage_relationship")
        or frontmatter.get("feature_lineage_type")
        or ""
    ).strip().lower().replace(" ", "_")
    lineage_parent = _normalize_feature_ref(lineage_parent_raw)
    lineage_children = _normalize_feature_refs(lineage_children_raw)
    lineage_family = canonical_slug(
        _normalize_feature_ref(lineage_family_raw) or _normalize_feature_ref(str(frontmatter.get("feature_slug") or ""))
    )
    fs_dates = file_metadata_dates(path)
    git_dates: dict[str, str] = {}
    dirty = False
    if isinstance(git_date_index, dict):
        candidate = git_date_index.get(project_rel)
        if isinstance(candidate, dict):
            git_dates = candidate
    if isinstance(dirty_paths, set):
        dirty = project_rel in dirty_paths
    fm_created = normalize_iso_date(frontmatter.get("created") or frontmatter.get("created_at"))
    fm_updated = normalize_iso_date(
        frontmatter.get("updated")
        or frontmatter.get("updated_at")
        or frontmatter.get("last_updated")
    )
    fm_completed = normalize_iso_date(
        frontmatter.get("completed")
        or frontmatter.get("completed_at")
        or frontmatter.get("completion_date")
    )
    git_created = normalize_iso_date(git_dates.get("createdAt"))
    git_updated = normalize_iso_date(git_dates.get("updatedAt"))

    created_date = choose_first([
        make_date_value(fm_created, "high", "frontmatter", "created"),
        make_date_value(git_created, "high", "git", "first_commit"),
        make_date_value(fs_dates.get("createdAt", ""), "medium", "filesystem", "file_birthtime"),
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_fallback")
        if not git_created else {},
    ])
    updated_date = choose_latest([
        make_date_value(git_updated, "high", "git", "latest_commit"),
        make_date_value(fm_updated, "medium", "frontmatter", "updated"),
        make_date_value(fs_dates.get("updatedAt", ""), "high", "filesystem", "dirty_worktree")
        if dirty else {},
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_fallback")
        if not git_updated and not fm_updated else {},
        make_date_value(fm_created, "low", "frontmatter", "created_fallback"),
    ])
    completed_date = choose_first([
        make_date_value(fm_completed, "high", "frontmatter", "completed"),
        make_date_value(fm_updated, "medium", "frontmatter", "updated_completion_fallback")
        if status_normalized in _DOC_COMPLETION_STATUSES else {},
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_completion_fallback")
        if status_normalized in _DOC_COMPLETION_STATUSES else {},
    ])
    last_activity = choose_latest([updated_date, completed_date])

    dates: dict[str, Any] = {}
    if created_date:
        dates["createdAt"] = created_date
    if updated_date:
        dates["updatedAt"] = updated_date
    if completed_date:
        dates["completedAt"] = completed_date
    if last_activity:
        dates["lastActivityAt"] = last_activity

    timeline: list[dict[str, Any]] = []
    if created_date:
        timeline.append({
            "id": "doc-created",
            "timestamp": created_date["value"],
            "label": "Document Created",
            "kind": "created",
            "confidence": created_date["confidence"],
            "source": created_date["source"],
            "description": created_date.get("reason", ""),
        })
    if updated_date:
        timeline.append({
            "id": "doc-updated",
            "timestamp": updated_date["value"],
            "label": "Last Updated",
            "kind": "updated",
            "confidence": updated_date["confidence"],
            "source": updated_date["source"],
            "description": updated_date.get("reason", ""),
        })
    if completed_date:
        timeline.append({
            "id": "doc-completed",
            "timestamp": completed_date["value"],
            "label": "Marked Complete",
            "kind": "completed",
            "confidence": completed_date["confidence"],
            "source": completed_date["source"],
            "description": completed_date.get("reason", ""),
        })

    return {
        "file_path": project_rel,
        "slug": slug,
        "canonical_slug": _base_slug(slug),
        "doc_type": classify_doc_type(project_rel, frontmatter),
        "category": classify_doc_category(project_rel, frontmatter),
        "feature_family": canonical_slug(str(frontmatter.get("feature_family") or frontmatter.get("lineage_family") or "").strip()),
        "primary_doc_role": str(frontmatter.get("primary_doc_role") or "").strip(),
        "blocked_by": _normalize_feature_refs(_to_string_list(frontmatter.get("blocked_by"))),
        "sequence_order": _to_optional_int(frontmatter.get("sequence_order")),
        "frontmatter_keys": sorted(str(key) for key in frontmatter.keys()),
        "related_refs": _extract_related_doc_refs(refs),
        "feature_refs": [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)],
        "linked_feature_refs": _normalize_linked_feature_refs(
            [
                *(_safe_list(refs.get("typedFeatureRefs"))),
                *[
                    {
                        "feature": dependency,
                        "type": "blocked_by",
                        "source": "blocked_by",
                        "confidence": 1.0,
                    }
                    for dependency in _normalize_feature_refs(_to_string_list(frontmatter.get("blocked_by")))
                ],
            ]
        ),
        "prd_ref": str(refs.get("prd") or ""),
        "dates": dates,
        "timeline": timeline,
        "created_at": created_date.get("value", ""),
        "updated_at": updated_date.get("value", ""),
        "completed_at": completed_date.get("value", ""),
        "status_normalized": status_normalized,
        "lineage_family": lineage_family,
        "lineage_parent": lineage_parent,
        "lineage_children": lineage_children,
        "lineage_type": lineage_type,
    }


# ── Phase 1: Scan Implementation Plans ──────────────────────────────

def _scan_impl_plans(
    docs_dir: Path,
    project_root: Path,
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> dict[str, dict]:
    """Scan implementation_plans/ and return a dict keyed by slug."""
    impl_dir = docs_dir / "implementation_plans"
    plans: dict[str, dict] = {}
    if not impl_dir.exists():
        return plans

    for path in sorted(impl_dir.rglob("*.md")):
        if path.name.startswith(".") or path.name == "README.md":
            continue
        # Skip summary/index files
        if "SUMMARY" in path.name.upper():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm = _extract_frontmatter(text)
        if not fm:
            continue

        slug = _slug_from_path(path)
        title = fm.get("title", path.stem.replace("-", " ").replace("_", " ").title())
        status = str(fm.get("status", "draft"))
        category = str(fm.get("category", ""))
        prd_ref = str(fm.get("prd_reference", ""))
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        doc_meta = _extract_doc_metadata(path, project_root, fm, git_date_index=git_date_index, dirty_paths=dirty_paths)
        rel_path = doc_meta["file_path"]
        updated = str(doc_meta.get("updated_at") or "")

        # Determine if this is a phase sub-plan (inside a sub-dir of an impl plan)
        # Phase sub-plans are files like impl_plans/harden-polish/discovery-import-fixes-v1/phase-1-bug-fixes.md
        parent_dir_name = path.parent.name

        # If the file is inside a feature-named subdirectory, it's a phase sub-plan
        is_phase_subplan = (
            path.parent != impl_dir
            and path.parent.parent != impl_dir  # not directly in a category dir
            and not path.parent.name in (
                "bug-fixes", "bugs", "enhancements", "features",
                "harden-polish", "refactors", "remediations", "scripts",
            )
        )

        if is_phase_subplan:
            # Attach to parent feature as a phase sub-plan doc
            parent_slug = parent_dir_name.lower()
            if parent_slug in plans:
                plans[parent_slug].setdefault("phase_docs", []).append({
                    "path": rel_path,
                    "title": title,
                    "slug": slug,
                    "status": status,
                    "category": doc_meta["category"],
                    "feature_family": doc_meta.get("feature_family", ""),
                    "primary_doc_role": doc_meta.get("primary_doc_role", ""),
                    "blocked_by": doc_meta.get("blocked_by", []),
                    "sequence_order": doc_meta.get("sequence_order"),
                    "frontmatter_keys": doc_meta["frontmatter_keys"],
                    "related_refs": doc_meta["related_refs"],
                    "prd_ref": doc_meta["prd_ref"],
                    "lineage_family": doc_meta.get("lineage_family", ""),
                    "lineage_parent": doc_meta.get("lineage_parent", ""),
                    "lineage_children": doc_meta.get("lineage_children", []),
                    "lineage_type": doc_meta.get("lineage_type", ""),
                    "linked_feature_refs": doc_meta.get("linked_feature_refs", []),
                    "dates": doc_meta.get("dates", {}),
                    "timeline": doc_meta.get("timeline", []),
                })
            continue

        plans[slug] = {
            "title": title,
            "status": status,
            "category": category or doc_meta["category"],
            "prd_ref": prd_ref or doc_meta["prd_ref"],
            "tags": tags if isinstance(tags, list) else [],
            "updated": updated,
            "rel_path": rel_path,
            "feature_family": doc_meta.get("feature_family", ""),
            "primary_doc_role": doc_meta.get("primary_doc_role", ""),
            "blocked_by": doc_meta.get("blocked_by", []),
            "sequence_order": doc_meta.get("sequence_order"),
            "frontmatter_keys": doc_meta["frontmatter_keys"],
            "related_refs": doc_meta["related_refs"],
            "lineage_family": doc_meta.get("lineage_family", ""),
            "lineage_parent": doc_meta.get("lineage_parent", ""),
            "lineage_children": doc_meta.get("lineage_children", []),
            "lineage_type": doc_meta.get("lineage_type", ""),
            "linked_feature_refs": doc_meta.get("linked_feature_refs", []),
            "phase_docs": [],
            "dates": doc_meta.get("dates", {}),
            "timeline": doc_meta.get("timeline", []),
        }

    return plans


# ── Phase 2: Scan PRDs ──────────────────────────────────────────────

def _scan_prds(
    docs_dir: Path,
    project_root: Path,
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> dict[str, dict]:
    """Scan PRDs/ and return a dict keyed by slug."""
    prd_dir = docs_dir / "PRDs"
    prds: dict[str, dict] = {}
    if not prd_dir.exists():
        return prds

    for path in sorted(prd_dir.rglob("*.md")):
        if path.name.startswith(".") or path.name == "README.md":
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm = _extract_frontmatter(text)
        if not fm:
            continue

        slug = _slug_from_path(path)
        title = fm.get("title", path.stem.replace("-", " ").replace("_", " ").title())
        status = str(fm.get("status", "draft"))
        refs = extract_frontmatter_references(fm)
        related = [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        doc_meta = _extract_doc_metadata(path, project_root, fm, git_date_index=git_date_index, dirty_paths=dirty_paths)
        rel_path = doc_meta["file_path"]
        updated = str(doc_meta.get("updated_at") or "")

        prds[slug] = {
            "title": title,
            "status": status,
            "related": [str(r) for r in related],
            "tags": tags if isinstance(tags, list) else [],
            "updated": updated,
            "rel_path": rel_path,
            "feature_family": doc_meta.get("feature_family", ""),
            "primary_doc_role": doc_meta.get("primary_doc_role", ""),
            "blocked_by": doc_meta.get("blocked_by", []),
            "sequence_order": doc_meta.get("sequence_order"),
            "frontmatter_keys": doc_meta["frontmatter_keys"],
            "related_refs": doc_meta["related_refs"],
            "prd_ref": doc_meta["prd_ref"],
            "lineage_family": doc_meta.get("lineage_family", ""),
            "lineage_parent": doc_meta.get("lineage_parent", ""),
            "lineage_children": doc_meta.get("lineage_children", []),
            "lineage_type": doc_meta.get("lineage_type", ""),
            "linked_feature_refs": doc_meta.get("linked_feature_refs", []),
            "dates": doc_meta.get("dates", {}),
            "timeline": doc_meta.get("timeline", []),
        }

    return prds


# ── Phase 3: Scan Progress directories ──────────────────────────────

def _parse_progress_tasks(tasks_raw: list, source_file: str = "") -> list[ProjectTask]:
    """Parse task entries from progress file frontmatter."""
    tasks: list[ProjectTask] = []
    for t in tasks_raw:
        if not isinstance(t, dict):
            continue
        task_id = t.get("id", "")
        if not task_id:
            continue

        title = t.get("title", t.get("name", t.get("description", task_id)))
        status = _map_task_status(str(t.get("status", "pending")))
        priority = t.get("priority", "medium")
        if not isinstance(priority, str):
            priority = "medium"

        assigned = t.get("assigned_to", [])
        if isinstance(assigned, str):
            assigned = [assigned]
        owner = assigned[0] if assigned else ""

        # Rough cost from effort
        effort_str = str(t.get("estimated_effort", t.get("story_points", "")))
        cost = 0.0
        m = re.search(r"(\d+(?:\.\d+)?)", effort_str)
        if m:
            cost = float(m.group(1)) * 0.50

        # Session and commit linking
        session_id = str(t.get("session_id", t.get("sessionId", ""))) if t.get("session_id") or t.get("sessionId") else ""
        commit_hash = str(t.get("git_commit", t.get("commitHash", ""))) if t.get("git_commit") or t.get("commitHash") else ""

        tasks.append(ProjectTask(
            id=task_id,
            title=title,
            description="",
            status=status,
            owner=owner,
            lastAgent="",
            cost=round(cost, 2),
            priority=priority,
            projectType="",
            projectLevel="",
            tags=[],
            updatedAt=str(t.get("completed_at", "")),
            relatedFiles=[str(d) for d in (t.get("deliverables", []) or [])[:10]],
            sourceFile=source_file,
            sessionId=session_id,
            commitHash=commit_hash,
        ))
    return tasks


def _derive_phase_planning_status(
    *,
    raw_status: str,
    effective_status: str,
    source_id: str,
    source_path: str,
    source_title: str,
) -> PlanningEffectiveStatus:
    normalized_raw = normalize_doc_status(raw_status, default="")
    mapped_raw = _map_status(raw_status) if str(raw_status or "").strip() else ""
    provenance_source = "raw"
    provenance_reason = "Phase status is taken directly from progress frontmatter."
    if normalized_raw == _INFERRED_COMPLETE_STATUS:
        provenance_source = "inferred_complete"
        provenance_reason = "Phase status is marked inferred_complete in progress frontmatter."

    mismatch_state = PlanningMismatchState(
        state="aligned",
        reason="Raw phase status maps directly to the parsed phase status.",
        isMismatch=False,
        evidence=[
            _make_status_evidence(
                evidence_id=f"{source_id}:raw-status",
                label=source_title or "Progress Phase",
                detail=f"raw={raw_status or '(missing)'}; effective={effective_status or '(missing)'}",
                source_type="progress",
                source_id=source_id,
                source_path=source_path,
            )
        ],
    )
    if mapped_raw and mapped_raw != effective_status:
        mismatch_state = PlanningMismatchState(
            state="derived",
            reason="Parsed phase status differs from the direct raw-status mapping.",
            isMismatch=False,
            evidence=mismatch_state.evidence,
        )

    return PlanningEffectiveStatus(
        rawStatus=str(raw_status or ""),
        effectiveStatus=str(effective_status or ""),
        provenance=PlanningStatusProvenance(
            source=provenance_source,  # type: ignore[arg-type]
            reason=provenance_reason,
            evidence=mismatch_state.evidence,
        ),
        mismatchState=mismatch_state,
    )


def _extract_phase_batches(
    *,
    feature_slug: str,
    phase: str,
    tasks: list[ProjectTask],
    tasks_raw: list[dict[str, Any]],
    parallelization: Any,
    blockers: list[str],
    files_modified: list[str],
    source_path: str,
    source_title: str,
) -> list[PlanningPhaseBatch]:
    if not isinstance(parallelization, dict):
        return []

    task_by_id = {
        str(task.id or "").strip(): task
        for task in tasks
        if str(task.id or "").strip()
    }
    raw_task_by_id = {
        str(task.get("id") or "").strip(): task
        for task in tasks_raw
        if isinstance(task, dict) and str(task.get("id") or "").strip()
    }
    terminal_task_statuses = {"done", "deferred"}
    batches: list[PlanningPhaseBatch] = []

    for batch_key, batch_value in sorted(parallelization.items(), key=lambda item: _batch_sort_key(str(item[0]))):
        batch_id = str(batch_key or "").strip()
        if not batch_id.startswith("batch_"):
            continue

        declared_task_ids = _to_string_list(batch_value)
        declared_agents: list[str] = []
        declared_files: list[str] = []
        if isinstance(batch_value, dict):
            declared_task_ids = _to_string_list(
                batch_value.get("tasks")
                or batch_value.get("task_ids")
                or batch_value.get("items")
            )
            declared_agents = _to_string_list(
                batch_value.get("assigned_to")
                or batch_value.get("owners")
                or batch_value.get("agents")
            )
            declared_files = _to_string_list(
                batch_value.get("files")
                or batch_value.get("files_modified")
                or batch_value.get("file_scope_hints")
            )

        task_ids: list[str] = []
        seen_task_ids: set[str] = set()
        for task_id in declared_task_ids:
            token = str(task_id or "").strip()
            if not token or token in seen_task_ids:
                continue
            seen_task_ids.add(token)
            task_ids.append(token)
        if not task_ids:
            continue

        batch_tasks = [task_by_id[task_id] for task_id in task_ids if task_id in task_by_id]
        assigned_agents = sorted(
            {
                *[agent for agent in declared_agents if str(agent).strip()],
                *[str(task.owner or "").strip() for task in batch_tasks if str(task.owner or "").strip()],
            }
        )
        file_scope_hints = sorted(
            {
                *[value for value in declared_files if str(value).strip()],
                *[
                    str(path).strip()
                    for task in batch_tasks
                    for path in (task.relatedFiles or [])
                    if str(path).strip()
                ],
                *[str(path).strip() for path in files_modified if str(path).strip()],
            }
        )

        blocking_task_ids = [
            task.id
            for task in batch_tasks
            if str(task.status or "") == "backlog"
            and _normalize_choice_token(raw_task_by_id.get(str(task.id), {}).get("status")) == "blocked"
        ]

        unresolved_dependencies: list[str] = []
        for task_id in task_ids:
            raw_task = raw_task_by_id.get(task_id, {})
            for dependency in _to_string_list(raw_task.get("dependencies")):
                dep_task = task_by_id.get(str(dependency or "").strip())
                if dep_task is None or dep_task.status not in terminal_task_statuses:
                    unresolved_dependencies.append(str(dependency))

        evidence: list[PlanningStatusEvidence] = []
        for blocker in blockers:
            blocker_value = str(blocker).strip()
            if not blocker_value:
                continue
            evidence.append(
                _make_status_evidence(
                    evidence_id=f"{batch_id}:blocker:{len(evidence) + 1}",
                    label=source_title or f"Phase {phase}",
                    detail=blocker_value,
                    source_type="progress",
                    source_id=batch_id,
                    source_path=source_path,
                )
            )
        for task_id in blocking_task_ids:
            evidence.append(
                _make_status_evidence(
                    evidence_id=f"{batch_id}:task:{task_id}",
                    label=f"Blocked task {task_id}",
                    detail="Task is explicitly marked blocked in progress frontmatter.",
                    source_type="task",
                    source_id=task_id,
                    source_path=source_path,
                )
            )

        if blockers or blocking_task_ids:
            readiness_state = "blocked"
            readiness_reason = "Batch has explicit blockers in progress metadata."
        elif _batch_sort_key(batch_id)[0] > 1 or unresolved_dependencies:
            readiness_state = "waiting"
            readiness_reason = "Batch is sequenced after earlier work or depends on unfinished tasks."
        else:
            readiness_state = "ready"
            readiness_reason = "No explicit blockers were found in parser-visible progress metadata."

        batches.append(
            PlanningPhaseBatch(
                featureSlug=str(feature_slug or ""),
                phase=str(phase or ""),
                batchId=batch_id,
                taskIds=task_ids,
                assignedAgents=assigned_agents,
                fileScopeHints=file_scope_hints,
                readinessState=readiness_state,  # type: ignore[arg-type]
                readiness=PlanningPhaseBatchReadiness(
                    state=readiness_state,  # type: ignore[arg-type]
                    reason=readiness_reason,
                    blockingNodeIds=[],
                    blockingTaskIds=sorted({*blocking_task_ids, *[str(dep) for dep in unresolved_dependencies if str(dep).strip()]}),
                    evidence=evidence,
                    isReady=readiness_state == "ready",
                ),
            )
        )

    return batches


def _scan_progress_dirs(
    progress_dir: Path,
    project_root: Path,
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> dict[str, dict]:
    """Scan progress/ subdirectories and return dict keyed by slug."""
    progress_data: dict[str, dict] = {}
    if not progress_dir.exists():
        return progress_data

    for subdir in sorted(progress_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue

        slug = subdir.name.lower()
        phases: list[FeaturePhase] = []
        overall_status = "backlog"
        latest_updated = ""
        progress_docs: list[dict[str, Any]] = []

        # Find all markdown files in this progress dir
        for md_file in sorted(subdir.glob("*.md")):
            if md_file.name.startswith("."):
                continue

            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            fm = _extract_frontmatter(text)
            if not fm:
                continue

            phase_num = str(fm.get("phase", "all"))
            phase_title = fm.get("phase_title", fm.get("title", fm.get("name", "")))
            phase_status_raw = str(fm.get("status", "pending"))
            phase_status = _map_status(phase_status_raw)
            phase_progress = fm.get("progress", 0)
            if not isinstance(phase_progress, (int, float)):
                phase_progress = 0

            total = fm.get("total_tasks", 0)
            completed = fm.get("completed_tasks", 0)
            deferred = fm.get("deferred_tasks", 0)
            if not isinstance(total, int):
                total = 0
            if not isinstance(completed, int):
                completed = 0
            if not isinstance(deferred, int):
                deferred = 0

            doc_meta = _extract_doc_metadata(md_file, project_root, fm, git_date_index=git_date_index, dirty_paths=dirty_paths)
            updated = str(doc_meta.get("updated_at") or "")
            if updated and updated > latest_updated:
                latest_updated = updated

            progress_docs.append({
                "path": doc_meta["file_path"],
                "title": str(fm.get("title", md_file.stem.replace("-", " ").title())),
                "slug": doc_meta["slug"],
                "status_raw": phase_status_raw,
                "category": doc_meta["category"],
                "feature_family": doc_meta.get("feature_family", ""),
                "primary_doc_role": doc_meta.get("primary_doc_role", ""),
                "blocked_by": doc_meta.get("blocked_by", []),
                "sequence_order": doc_meta.get("sequence_order"),
                "frontmatter_keys": doc_meta["frontmatter_keys"],
                "related_refs": doc_meta["related_refs"],
                "prd_ref": doc_meta["prd_ref"],
                "lineage_family": doc_meta.get("lineage_family", ""),
                "lineage_parent": doc_meta.get("lineage_parent", ""),
                "lineage_children": doc_meta.get("lineage_children", []),
                "lineage_type": doc_meta.get("lineage_type", ""),
                "linked_feature_refs": doc_meta.get("linked_feature_refs", []),
                "dates": doc_meta.get("dates", {}),
                "timeline": doc_meta.get("timeline", []),
            })

            # Parse tasks
            tasks_raw = fm.get("tasks", [])
            if not isinstance(tasks_raw, list):
                tasks_raw = []
            # Pass project-relative path so tasks and links align with command args.
            source_rel = _project_relative(md_file, project_root)
            tasks = _parse_progress_tasks(tasks_raw, source_file=source_rel)
            blockers = _to_string_list(fm.get("blockers"))
            phase_batches = _extract_phase_batches(
                feature_slug=slug,
                phase=phase_num,
                tasks=tasks,
                tasks_raw=[task for task in tasks_raw if isinstance(task, dict)],
                parallelization=fm.get("parallelization"),
                blockers=blockers,
                files_modified=[str(v) for v in _to_string_list(fm.get("files_modified")) if str(v).strip()],
                source_path=source_rel,
                source_title=str(fm.get("title", md_file.stem.replace("-", " ").title())),
            )

            if tasks:
                # Task statuses are the source of truth for completion math.
                total = total or len(tasks)
                done_count = sum(1 for t in tasks if t.status == "done")
                deferred = sum(1 for t in tasks if t.status == "deferred")
                completed = done_count + deferred

            if phase_status == "deferred" and total > 0:
                # A deferred phase is terminal-complete even with partial task detail.
                completed = total
                deferred = total

            if total > 0 and completed > total:
                completed = total
            if completed < 0:
                completed = 0
            if deferred < 0:
                deferred = 0
            if deferred > completed:
                deferred = completed

            phases.append(FeaturePhase(
                phase=phase_num,
                title=str(phase_title),
                status=phase_status,
                progress=int(phase_progress),
                totalTasks=total,
                completedTasks=completed,
                deferredTasks=deferred,
                tasks=tasks,
                planningStatus=_derive_phase_planning_status(
                    raw_status=phase_status_raw,
                    effective_status=phase_status,
                    source_id=f"PROGRESS-{doc_meta['slug']}",
                    source_path=source_rel,
                    source_title=str(phase_title),
                ),
                phaseBatches=phase_batches,
            ))

        if not phases:
            continue

        # Derive overall status from phases
        all_terminal = all(p.status in _TERMINAL_STATUSES for p in phases)
        total_tasks = sum(max(p.totalTasks, 0) for p in phases)
        completed_tasks = sum(max(p.completedTasks, 0) for p in phases)
        any_in_progress = any(p.status == "in-progress" for p in phases)
        any_review = any(p.status == "review" for p in phases)

        if total_tasks > 0 and completed_tasks >= total_tasks:
            overall_status = "done"
        elif all_terminal:
            overall_status = "done"
        elif any_in_progress:
            overall_status = "in-progress"
        elif any_review:
            overall_status = "review"
        else:
            overall_status = "backlog"

        progress_data[slug] = {
            "phases": phases,
            "status": overall_status,
            "updated": latest_updated,
            "prd_slug": "",  # will be set from first progress file's prd field
            "docs": progress_docs,
        }

        # Extract prd slug from the first file that has one
        for md_file in sorted(subdir.glob("*.md")):
            try:
                fm = _extract_frontmatter(md_file.read_text(encoding="utf-8"))
                prd_val = fm.get("prd", "")
                if prd_val:
                    progress_data[slug]["prd_slug"] = str(prd_val).lower()
                    break
            except Exception:
                continue

    return progress_data


# ── File resolution helpers (for status write-back) ────────────────


def resolve_file_for_feature(
    feature_id: str, docs_dir: Path, progress_dir: Path
) -> Optional[Path]:
    """Return the top-level file for a feature (PRD first, then impl plan)."""
    # Check PRDs
    prd_dir = docs_dir / "PRDs"
    if prd_dir.exists():
        for path in prd_dir.rglob("*.md"):
            if _slug_from_path(path) == feature_id or _base_slug(_slug_from_path(path)) == _base_slug(feature_id):
                return path

    # Check impl plans
    impl_dir = docs_dir / "implementation_plans"
    if impl_dir.exists():
        for path in impl_dir.rglob("*.md"):
            if _slug_from_path(path) == feature_id or _base_slug(_slug_from_path(path)) == _base_slug(feature_id):
                return path

    return None


def resolve_file_for_phase(
    feature_id: str, phase_id: str, progress_dir: Path
) -> Optional[Path]:
    """Return the progress file for a specific phase of a feature."""
    subdir = progress_dir / feature_id
    if not subdir.exists():
        # Try base-slug matching
        for d in progress_dir.iterdir():
            if d.is_dir() and _base_slug(d.name.lower()) == _base_slug(feature_id):
                subdir = d
                break
        else:
            return None

    for md_file in sorted(subdir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm = _extract_frontmatter(text)
            if str(fm.get("phase", "all")) == phase_id:
                return md_file
        except Exception:
            continue

    return None


def _max_status(*statuses: str) -> str:
    """Return the status with the highest progression."""
    best = "backlog"
    terminal_score = _STATUS_ORDER["done"]
    for s in statuses:
        score = _STATUS_ORDER.get(s, 0)
        best_score = _STATUS_ORDER.get(best, 0)
        if score > best_score:
            best = s
            continue
        # Tie-break completion-equivalent statuses in favor of deferred so
        # mixed terminal states remain visible as partially deferred work.
        if score == best_score == terminal_score and s == "deferred":
            best = s
    return best


# ── Merge into Features ─────────────────────────────────────────────

def _linked_doc_id_from_path(file_path: str) -> str:
    normalized = normalize_ref_path(file_path)
    token = (normalized or file_path).replace("/", "-").replace("\\", "-").replace(".md", "")
    return f"DOC-{token}"


def _scan_auxiliary_docs(
    docs_dir: Path,
    progress_dir: Path,
    project_root: Path,
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    roots = [docs_dir, progress_dir]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name.startswith(".") or path.name == "README.md":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            fm = _extract_frontmatter(text)
            metadata = _extract_doc_metadata(path, project_root, fm, git_date_index=git_date_index, dirty_paths=dirty_paths)
            file_path = str(metadata["file_path"])
            if not file_path or file_path in seen_paths:
                continue
            seen_paths.add(file_path)

            title = str(fm.get("title", path.stem.replace("-", " ").replace("_", " ").title()))
            slug = str(metadata["slug"] or "")
            canonical = str(metadata["canonical_slug"] or "")
            feature_refs = [str(v) for v in metadata.get("feature_refs", []) if isinstance(v, str)]
            aliases = set(alias_tokens_from_path(file_path))
            aliases.update(feature_refs)
            if slug and not is_generic_alias_token(slug):
                aliases.add(slug)
            if canonical and not is_generic_alias_token(canonical):
                aliases.add(canonical)
            docs.append({
                "id": _linked_doc_id_from_path(file_path),
                "title": title,
                "filePath": file_path,
                "docType": str(metadata["doc_type"]),
                "category": str(metadata["category"]),
                "slug": slug,
                "canonicalSlug": canonical,
                "featureFamily": str(metadata.get("feature_family") or ""),
                "primaryDocRole": str(metadata.get("primary_doc_role") or ""),
                "blockedBy": [str(v) for v in metadata.get("blocked_by", []) if isinstance(v, str)],
                "sequenceOrder": metadata.get("sequence_order"),
                "frontmatterKeys": metadata["frontmatter_keys"],
                "relatedRefs": metadata["related_refs"],
                "prdRef": str(metadata["prd_ref"] or ""),
                "featureRefs": feature_refs,
                "aliases": aliases,
                "lineageFamily": str(metadata.get("lineage_family") or ""),
                "lineageParent": str(metadata.get("lineage_parent") or ""),
                "lineageChildren": [str(v) for v in metadata.get("lineage_children", []) if isinstance(v, str)],
                "lineageType": str(metadata.get("lineage_type") or ""),
                "linkedFeatures": metadata.get("linked_feature_refs", []),
                "dates": metadata.get("dates", {}),
                "timeline": metadata.get("timeline", []),
            })
    return docs


def _feature_aliases(feature: Feature) -> set[str]:
    feature_base = _base_slug(feature.id)
    aliases: set[str] = {feature.id.lower(), feature_base}
    for doc in feature.linkedDocs:
        slug = (doc.slug or Path(doc.filePath).stem).strip().lower()
        if slug and not is_generic_alias_token(slug) and _base_slug(slug) == feature_base:
            aliases.add(slug)
            aliases.add(_base_slug(slug))
        path_feature_slug = feature_slug_from_path(doc.filePath)
        if path_feature_slug and _base_slug(path_feature_slug) == feature_base:
            aliases.add(path_feature_slug)
            aliases.add(_base_slug(path_feature_slug))
    return {alias for alias in aliases if alias}


def _doc_matches_feature(doc: dict[str, Any], feature_aliases: set[str], feature_id: str) -> bool:
    feature_bases = {_base_slug(alias) for alias in feature_aliases if alias}
    feature_token = (feature_id or "").strip().lower()
    doc_type = str(doc.get("docType") or "").strip().lower()
    is_owned_doc = doc_type in _DOC_WRITE_THROUGH_TYPES or doc_type == "progress"

    def _matches_feature(candidate: str) -> bool:
        value = (candidate or "").strip().lower()
        if not value:
            return False
        if is_owned_doc:
            return bool(feature_token) and value == feature_token
        return value in feature_aliases or _base_slug(value) in feature_bases

    doc_path = str(doc.get("filePath") or "")
    path_feature_slug = feature_slug_from_path(doc_path)
    if path_feature_slug:
        if _matches_feature(path_feature_slug):
            return True
        # Ownership guard for plan/progress docs: if path and target disagree,
        # do not accept indirect refs that would cross-link feature ownership.
        if doc_type in _DOC_WRITE_THROUGH_TYPES or doc_type == "progress":
            return False
    feature_refs = {str(v).lower() for v in doc.get("featureRefs", []) if str(v).strip()}
    if any(_matches_feature(feature_ref) for feature_ref in feature_refs):
        return True
    prd_ref = str(doc.get("prdRef") or "").strip().lower()
    if prd_ref:
        prd_slug = feature_slug_from_path(prd_ref) if ("/" in prd_ref or prd_ref.endswith(".md")) else prd_ref
        if _matches_feature(prd_slug):
            return True
    return False


def _doc_owned_by_feature(doc: LinkedDocument, feature_id: str) -> bool:
    feature_token = (feature_id or "").strip().lower()
    if not feature_token:
        return False

    path_feature_slug = feature_slug_from_path(str(doc.filePath or ""))
    if path_feature_slug:
        return path_feature_slug == feature_token

    doc_slug = (doc.slug or Path(doc.filePath).stem).strip().lower()
    if doc_slug and doc_slug == feature_token:
        return True

    return False


def _aggregate_feature_linked_features(
    feature: Feature,
    related_ids: set[str],
    derived_refs: list[LinkedFeatureRef] | None = None,
) -> list[LinkedFeatureRef]:
    merged: dict[tuple[str, str, str], LinkedFeatureRef] = {}
    self_slug = str(feature.id or "").strip().lower()

    for doc in feature.linkedDocs:
        for raw_ref in doc.linkedFeatures or []:
            if isinstance(raw_ref, LinkedFeatureRef):
                feature_ref = str(raw_ref.feature or "").strip().lower()
                relation_type = str(raw_ref.type or "").strip().lower().replace("-", "_").replace(" ", "_")
                source = str(raw_ref.source or "").strip().lower().replace("-", "_").replace(" ", "_")
                confidence = raw_ref.confidence
                notes = raw_ref.notes
                evidence = [str(v) for v in raw_ref.evidence if str(v).strip()]
            elif isinstance(raw_ref, dict):
                feature_ref = str(raw_ref.get("feature") or "").strip().lower()
                relation_type = str(raw_ref.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_")
                source = str(raw_ref.get("source") or "").strip().lower().replace("-", "_").replace(" ", "_")
                confidence_raw = raw_ref.get("confidence")
                confidence = None
                if confidence_raw is not None:
                    try:
                        confidence = max(0.0, min(1.0, float(confidence_raw)))
                    except Exception:
                        confidence = None
                notes = str(raw_ref.get("notes") or "")
                evidence = [str(v) for v in _to_string_list(raw_ref.get("evidence")) if str(v).strip()]
            else:
                continue
            if not feature_ref or feature_ref == self_slug:
                continue
            source = source or "explicit_doc_field"
            key = (feature_ref, relation_type, source)
            merged[key] = LinkedFeatureRef(
                feature=feature_ref,
                type=relation_type,
                source=source,
                confidence=confidence,
                notes=notes,
                evidence=evidence,
            )

    for related_id in sorted(related_ids):
        related_slug = str(related_id or "").strip().lower()
        if not related_slug or related_slug == self_slug:
            continue
        key = (related_slug, "related", "correlated_ref")
        if key not in merged:
            merged[key] = LinkedFeatureRef(
                feature=related_slug,
                type="related",
                source="correlated_ref",
            )

    for ref in derived_refs or []:
        related_slug = str(ref.feature or "").strip().lower()
        if not related_slug or related_slug == self_slug:
            continue
        relation_type = str(ref.type or "").strip().lower().replace("-", "_").replace(" ", "_")
        source = str(ref.source or "").strip().lower().replace("-", "_").replace(" ", "_")
        key = (related_slug, relation_type, source)
        if key in merged:
            continue
        merged[key] = LinkedFeatureRef(
            feature=related_slug,
            type=relation_type,
            source=source,
            confidence=ref.confidence,
            notes=ref.notes,
            evidence=[str(v) for v in ref.evidence if str(v).strip()],
        )

    return sorted(
        merged.values(),
        key=lambda ref: (ref.feature, ref.type or "", ref.source or ""),
    )


def _phase_is_completion_equivalent(phase: FeaturePhase) -> bool:
    if phase.status in _TERMINAL_STATUSES:
        return True
    total = max(int(phase.totalTasks or 0), 0)
    completed = max(int(phase.completedTasks or 0), 0)
    return total > 0 and completed >= total


def _date_candidate_from_value(value: Any, default_source: str = "") -> dict[str, str]:
    if not value:
        return {}
    if isinstance(value, dict):
        normalized_value = normalize_iso_date(value.get("value"))
        if not normalized_value:
            return {}
        return {
            "value": normalized_value,
            "confidence": str(value.get("confidence") or "low"),
            "source": str(value.get("source") or default_source),
            "reason": str(value.get("reason") or ""),
        }
    normalized_value = normalize_iso_date(getattr(value, "value", ""))
    if not normalized_value:
        return {}
    return {
        "value": normalized_value,
        "confidence": str(getattr(value, "confidence", "low") or "low"),
        "source": str(getattr(value, "source", "") or default_source),
        "reason": str(getattr(value, "reason", "") or ""),
    }


def _timeline_event(
    event_id: str,
    label: str,
    kind: str,
    candidate: dict[str, str],
    source: str = "",
) -> dict[str, str]:
    if not candidate:
        return {}
    return {
        "id": event_id,
        "timestamp": candidate.get("value", ""),
        "label": label,
        "kind": kind,
        "confidence": candidate.get("confidence", "low"),
        "source": source or candidate.get("source", ""),
        "description": candidate.get("reason", ""),
    }


def _normalize_date_confidence(raw: Any) -> str:
    token = str(raw or "low").strip().lower()
    return token if token in _DATE_CONFIDENCE_LEVELS else "low"


def _normalize_entity_dates_payload(raw_dates: dict[str, Any]) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for key, raw_value in raw_dates.items():
        if not isinstance(raw_value, dict):
            continue
        normalized_value = normalize_iso_date(raw_value.get("value"))
        if not normalized_value:
            continue
        normalized[str(key)] = {
            "value": normalized_value,
            "confidence": _normalize_date_confidence(raw_value.get("confidence")),
            "source": str(raw_value.get("source") or ""),
            "reason": str(raw_value.get("reason") or ""),
        }
    return normalized


def _normalize_timeline_payload(raw_timeline: list[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for idx, raw_event in enumerate(raw_timeline):
        if not isinstance(raw_event, dict):
            continue
        timestamp = normalize_iso_date(raw_event.get("timestamp"))
        if not timestamp:
            continue
        normalized.append(
            {
                "id": str(raw_event.get("id") or f"feature-event-{idx}"),
                "timestamp": timestamp,
                "label": str(raw_event.get("label") or "Feature Event"),
                "kind": str(raw_event.get("kind") or ""),
                "confidence": _normalize_date_confidence(raw_event.get("confidence")),
                "source": str(raw_event.get("source") or ""),
                "description": str(raw_event.get("description") or ""),
            }
        )
    return normalized


def _load_doc_frontmatter(
    project_root: Path,
    doc: LinkedDocument,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    file_path = normalize_ref_path(str(doc.filePath or "")) or str(doc.filePath or "")
    if not file_path:
        return {}
    cached = cache.get(file_path)
    if cached is not None:
        return cached

    absolute = project_root / file_path
    if not absolute.exists():
        cache[file_path] = {}
        return {}

    try:
        text = absolute.read_text(encoding="utf-8")
        frontmatter = _extract_frontmatter(text)
    except Exception:
        frontmatter = {}

    cache[file_path] = frontmatter if isinstance(frontmatter, dict) else {}
    return cache[file_path]


def _extract_doc_rollup_context(
    project_root: Path,
    doc: LinkedDocument,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    frontmatter = _load_doc_frontmatter(project_root, doc, cache)
    doc_type = _normalize_doc_type_token(doc.docType)
    status = normalize_doc_status(frontmatter.get("status"), default="")

    owner_values = _to_string_list(frontmatter.get("owners"))
    owner = str(frontmatter.get("owner") or "").strip()
    if owner:
        owner_values.append(owner)

    commit_refs = _to_string_list(frontmatter.get("commit_refs") or frontmatter.get("commitRefs"))
    commit_refs.extend(_to_string_list(frontmatter.get("commits")))
    pr_refs = _to_string_list(frontmatter.get("pr_refs") or frontmatter.get("prRefs"))
    pr_refs.extend(_to_string_list(frontmatter.get("prs")))
    request_log_ids = _to_string_list(frontmatter.get("request_log_ids") or frontmatter.get("requestLogIds"))
    integrity_signal_refs = _to_string_list(
        frontmatter.get("integrity_signal_refs") or frontmatter.get("integritySignalRefs")
    )

    blockers = _to_string_list(frontmatter.get("blockers"))
    tasks_raw = _safe_list(frontmatter.get("tasks"))
    at_risk_statuses = {"blocked", "at_risk", "at-risk", "risk", "atrisk", "high_risk"}
    at_risk_task_count = 0
    task_commit_refs: list[str] = []
    for task in tasks_raw:
        if not isinstance(task, dict):
            continue
        status_token = _normalize_choice_token(task.get("status"))
        if status_token in at_risk_statuses:
            at_risk_task_count += 1
        task_commit_refs.extend(
            _to_string_list(task.get("git_commit") or task.get("commitHash") or task.get("commit_hash"))
        )

    report_findings_by_severity: dict[str, int] = {}
    for finding in _safe_list(frontmatter.get("findings")):
        if not isinstance(finding, dict):
            continue
        severity = _normalize_feature_finding_severity(finding.get("severity"))
        report_findings_by_severity[severity] = report_findings_by_severity.get(severity, 0) + 1

    return {
        "doc": doc,
        "docType": doc_type,
        "status": status,
        "description": str(frontmatter.get("description") or "").strip(),
        "summary": str(frontmatter.get("summary") or "").strip(),
        "priority": str(frontmatter.get("priority") or "").strip(),
        "riskLevel": str(frontmatter.get("risk_level") or "").strip(),
        "complexity": str(frontmatter.get("complexity") or "").strip(),
        "track": str(frontmatter.get("track") or "").strip(),
        "timelineEstimate": str(frontmatter.get("timeline_estimate") or "").strip(),
        "targetRelease": str(frontmatter.get("target_release") or "").strip(),
        "milestone": str(frontmatter.get("milestone") or "").strip(),
        "executionReadiness": str(frontmatter.get("execution_readiness") or "").strip(),
        "testImpact": str(frontmatter.get("test_impact") or "").strip(),
        "featureFamily": canonical_slug(str(frontmatter.get("feature_family") or frontmatter.get("lineage_family") or "").strip()),
        "blockedBy": _normalize_feature_refs(_to_string_list(frontmatter.get("blocked_by"))),
        "sequenceOrder": _to_optional_int(frontmatter.get("sequence_order")),
        "owners": [str(v).strip() for v in owner_values if str(v).strip()],
        "contributors": [str(v).strip() for v in _to_string_list(frontmatter.get("contributors")) if str(v).strip()],
        "requestLogIds": [str(v).strip() for v in request_log_ids if str(v).strip()],
        "commitRefs": [str(v).strip() for v in commit_refs if str(v).strip()],
        "taskCommitRefs": [str(v).strip() for v in task_commit_refs if str(v).strip()],
        "prRefs": [str(v).strip() for v in pr_refs if str(v).strip()],
        "integritySignalRefs": [str(v).strip() for v in integrity_signal_refs if str(v).strip()],
        "blockerCount": len([v for v in blockers if str(v).strip()]),
        "atRiskTaskCount": at_risk_task_count,
        "reportFindingsBySeverity": report_findings_by_severity,
    }


def _derive_execution_readiness(
    explicit_values: list[str],
    *,
    has_prd: bool,
    has_plan: bool,
    has_progress: bool,
    blocker_count: int,
    at_risk_task_count: int,
    test_impact: str,
) -> str:
    normalized_explicit = [_normalize_choice_token(value) for value in explicit_values if str(value).strip()]
    if blocker_count > 0 or at_risk_task_count > 0:
        return "blocked"
    if not has_prd or not has_plan:
        return "planning"
    if any(value == "blocked" for value in normalized_explicit):
        return "blocked"
    if any(value == "review" for value in normalized_explicit):
        return "review"
    impact_token = _normalize_choice_token(test_impact)
    if impact_token in {"critical", "high"}:
        return "review"
    if any(value == "ready" for value in normalized_explicit):
        return "ready"
    if has_progress or any(value in {"in_progress", "active"} for value in normalized_explicit):
        return "in_progress"
    if normalized_explicit:
        return max(normalized_explicit, key=lambda value: _READINESS_ORDER.get(value, 0))
    return "planning"


def _derive_feature_rollups(
    feature: Feature,
    project_root: Path,
) -> dict[str, Any]:
    cache: dict[str, dict[str, Any]] = {}
    contexts = [
        _extract_doc_rollup_context(project_root, doc, cache)
        for doc in feature.linkedDocs
    ]

    def _contexts_for_type(doc_type: str) -> list[dict[str, Any]]:
        return [ctx for ctx in contexts if ctx.get("docType") == doc_type]

    prd_contexts = _contexts_for_type("prd")
    plan_contexts = _contexts_for_type("implementation_plan")
    progress_contexts = _contexts_for_type("progress")
    phase_contexts = _contexts_for_type("phase_plan")
    report_contexts = _contexts_for_type("report")
    design_contexts = _contexts_for_type("design_doc")
    spec_contexts = _contexts_for_type("spec")

    def _latest_doc(context_rows: list[dict[str, Any]]) -> Optional[LinkedDocument]:
        docs = [row.get("doc") for row in context_rows if isinstance(row.get("doc"), LinkedDocument)]
        return _pick_latest_document(docs) if docs else None

    def _first_non_empty(rows: list[dict[str, Any]], key: str) -> str:
        for row in rows:
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    description = _first_non_empty(prd_contexts, "description") or _first_non_empty(plan_contexts, "description")
    summary = _first_non_empty(prd_contexts, "summary") or _first_non_empty(plan_contexts, "summary")

    all_priorities = [str(ctx.get("priority") or "").strip() for ctx in contexts if str(ctx.get("priority") or "").strip()]
    priority = (
        _first_non_empty(prd_contexts, "priority")
        or _first_non_empty(plan_contexts, "priority")
        or _pick_highest_ranked(all_priorities, _FEATURE_PRIORITY_ORDER)
    )

    all_risk_levels = [str(ctx.get("riskLevel") or "").strip() for ctx in contexts if str(ctx.get("riskLevel") or "").strip()]
    risk_level = (
        _first_non_empty(prd_contexts, "riskLevel")
        or _first_non_empty(plan_contexts, "riskLevel")
        or _pick_highest_ranked(all_risk_levels, _FEATURE_RISK_ORDER)
    )

    complexity = _first_non_empty(plan_contexts, "complexity") or _first_non_empty(prd_contexts, "complexity")
    track = _first_non_empty(plan_contexts, "track") or _first_non_empty(prd_contexts, "track")
    timeline_estimate = _first_non_empty(plan_contexts, "timelineEstimate") or _first_non_empty(prd_contexts, "timelineEstimate")
    target_release = _first_non_empty(prd_contexts, "targetRelease") or _first_non_empty(plan_contexts, "targetRelease")
    milestone = _first_non_empty(prd_contexts, "milestone") or _first_non_empty(plan_contexts, "milestone")
    feature_family = (
        _first_non_empty(plan_contexts, "featureFamily")
        or _first_non_empty(prd_contexts, "featureFamily")
        or _first_non_empty(progress_contexts, "featureFamily")
        or _first_non_empty(phase_contexts, "featureFamily")
    )

    owner_values: set[str] = set()
    contributor_values: set[str] = set()
    request_log_values: set[str] = set()
    commit_ref_values: set[str] = set()
    pr_ref_values: set[str] = set()
    integrity_signal_values: set[str] = set()
    blocked_by_values: set[str] = set()
    explicit_readiness_values: list[str] = []
    explicit_test_impact_values: list[str] = []
    blocker_count = 0
    at_risk_task_count = 0
    report_findings_by_severity: dict[str, int] = {}

    for ctx in contexts:
        for owner in ctx.get("owners", []):
            if owner:
                owner_values.add(owner)
        for contributor in ctx.get("contributors", []):
            if contributor:
                contributor_values.add(contributor)
        for request_id in ctx.get("requestLogIds", []):
            if request_id:
                request_log_values.add(request_id)
        for commit_ref in [*ctx.get("commitRefs", []), *ctx.get("taskCommitRefs", [])]:
            if commit_ref:
                commit_ref_values.add(commit_ref)
        for pr_ref in ctx.get("prRefs", []):
            if pr_ref:
                pr_ref_values.add(pr_ref)
        for signal_ref in ctx.get("integritySignalRefs", []):
            if signal_ref:
                integrity_signal_values.add(signal_ref)
        for dependency in ctx.get("blockedBy", []):
            if dependency:
                blocked_by_values.add(dependency)
        readiness = str(ctx.get("executionReadiness") or "").strip()
        if readiness:
            explicit_readiness_values.append(readiness)
        test_impact = str(ctx.get("testImpact") or "").strip()
        if test_impact:
            explicit_test_impact_values.append(test_impact)
        blocker_count += int(ctx.get("blockerCount") or 0)
        at_risk_task_count += int(ctx.get("atRiskTaskCount") or 0)
        for severity, count in (ctx.get("reportFindingsBySeverity") or {}).items():
            if not severity:
                continue
            report_findings_by_severity[severity] = report_findings_by_severity.get(severity, 0) + int(count or 0)

    active_progress_contexts = [
        ctx for ctx in progress_contexts
        if str(ctx.get("status") or "") in {"in_progress", "review", "pending"}
    ]
    for ctx in [*prd_contexts, *plan_contexts, *active_progress_contexts]:
        for owner in ctx.get("owners", []):
            if owner:
                owner_values.add(owner)

    test_impact = _pick_highest_ranked(explicit_test_impact_values, _TEST_IMPACT_ORDER)
    execution_readiness = _derive_execution_readiness(
        explicit_readiness_values,
        has_prd=bool(prd_contexts),
        has_plan=bool(plan_contexts),
        has_progress=bool(progress_contexts),
        blocker_count=blocker_count,
        at_risk_task_count=at_risk_task_count,
        test_impact=test_impact,
    )

    required_doc_types = ["prd", "implementation_plan", "progress", "report", "design_doc", "spec"]
    counts_by_type: dict[str, int] = {}
    for doc in feature.linkedDocs:
        doc_type = _normalize_doc_type_token(doc.docType)
        counts_by_type[doc_type] = counts_by_type.get(doc_type, 0) + 1
    present_doc_types = [doc_type for doc_type in required_doc_types if counts_by_type.get(doc_type, 0) > 0]
    missing_doc_types = [doc_type for doc_type in required_doc_types if counts_by_type.get(doc_type, 0) == 0]
    coverage_score = round(len(present_doc_types) / len(required_doc_types), 3) if required_doc_types else 0.0

    def _doc_updated_sort_key(doc: LinkedDocument) -> str:
        updated = getattr(getattr(doc, "dates", None), "updatedAt", None)
        if getattr(updated, "value", ""):
            return str(updated.value)
        created = getattr(getattr(doc, "dates", None), "createdAt", None)
        if getattr(created, "value", ""):
            return str(created.value)
        return ""

    supporting_contexts = [*report_contexts, *design_contexts, *spec_contexts]
    supporting_docs = [
        ctx.get("doc")
        for ctx in supporting_contexts
        if isinstance(ctx.get("doc"), LinkedDocument)
    ]
    supporting_docs = sorted(supporting_docs, key=_doc_updated_sort_key, reverse=True)

    high_impact_findings = (
        report_findings_by_severity.get("critical", 0)
        + report_findings_by_severity.get("high", 0)
    )
    has_blocking_signals = blocker_count > 0 or at_risk_task_count > 0 or high_impact_findings > 0

    return {
        "description": description,
        "summary": summary,
        "priority": priority,
        "riskLevel": risk_level,
        "complexity": complexity,
        "track": track,
        "timelineEstimate": timeline_estimate,
        "targetRelease": target_release,
        "milestone": milestone,
        "featureFamily": feature_family,
        "blockedBy": sorted(blocked_by_values),
        "owners": sorted(owner_values),
        "contributors": sorted(contributor_values),
        "requestLogIds": sorted(request_log_values),
        "commitRefs": sorted(commit_ref_values),
        "prRefs": sorted(pr_ref_values),
        "executionReadiness": execution_readiness,
        "testImpact": test_impact,
        "primaryDocuments": FeaturePrimaryDocuments(
            prd=_latest_doc(prd_contexts),
            implementationPlan=_latest_doc(plan_contexts),
            phasePlans=[
                ctx["doc"] for ctx in phase_contexts
                if isinstance(ctx.get("doc"), LinkedDocument)
            ],
            progressDocs=sorted(
                [
                    ctx["doc"] for ctx in progress_contexts
                    if isinstance(ctx.get("doc"), LinkedDocument)
                ],
                key=_doc_updated_sort_key,
                reverse=True,
            )[:3],
            supportingDocs=supporting_docs[:6],
        ),
        "documentCoverage": FeatureDocumentCoverage(
            present=present_doc_types,
            missing=missing_doc_types,
            countsByType=counts_by_type,
            coverageScore=coverage_score,
        ),
        "qualitySignals": FeatureQualitySignals(
            blockerCount=blocker_count,
            atRiskTaskCount=at_risk_task_count,
            integritySignalRefs=sorted(integrity_signal_values),
            reportFindingsBySeverity=report_findings_by_severity,
            testImpact=test_impact,
            hasBlockingSignals=has_blocking_signals,
        ),
    }


def _derive_feature_planning_status(
    feature: Feature,
    project_root: Path,
) -> PlanningEffectiveStatus | None:
    cache: dict[str, dict[str, Any]] = {}
    contexts: list[dict[str, Any]] = []
    for doc in feature.linkedDocs:
        frontmatter = _load_doc_frontmatter(project_root, doc, cache)
        raw_status = str(frontmatter.get("status") or "").strip()
        normalized = normalize_doc_status(raw_status, default="")
        mapped = _map_status(raw_status) if raw_status else ""
        contexts.append(
            {
                "doc": doc,
                "raw": raw_status,
                "normalized": normalized,
                "mapped": mapped,
            }
        )

    if not contexts and not feature.status:
        return None

    type_priority = {
        "implementation_plan": 0,
        "prd": 1,
        "progress": 2,
        "phase_plan": 3,
        "design_doc": 4,
        "report": 5,
        "spec": 6,
        "document": 7,
    }

    def _context_sort_key(ctx: dict[str, Any]) -> tuple[int, str]:
        doc = ctx["doc"]
        return (type_priority.get(str(doc.docType or ""), 99), str(doc.filePath or ""))

    ordered_contexts = sorted(contexts, key=_context_sort_key)
    primary_context = next((ctx for ctx in ordered_contexts if ctx.get("raw")), ordered_contexts[0] if ordered_contexts else None)
    raw_status = str(primary_context.get("raw") or "") if primary_context else ""
    effective_status = str(feature.status or "")

    evidence: list[PlanningStatusEvidence] = []
    for ctx in ordered_contexts[:6]:
        doc = ctx["doc"]
        detail_parts = []
        raw_value = str(ctx.get("raw") or "").strip()
        if raw_value:
            detail_parts.append(f"raw={raw_value}")
        mapped_value = str(ctx.get("mapped") or "").strip()
        if mapped_value:
            detail_parts.append(f"mapped={mapped_value}")
        if effective_status:
            detail_parts.append(f"effective={effective_status}")
        evidence.append(
            _make_status_evidence(
                evidence_id=f"{doc.id}:status",
                label=str(doc.title or doc.id),
                detail="; ".join(detail_parts) or "No explicit status found.",
                source_type=str(doc.docType or "document"),
                source_id=str(doc.id or ""),
                source_path=str(doc.filePath or ""),
            )
        )
    for phase in feature.phases[:4]:
        if phase.planningStatus is None:
            continue
        evidence.append(
            _make_status_evidence(
                evidence_id=f"{feature.id}:phase:{phase.phase}",
                label=phase.title or f"Phase {phase.phase}",
                detail=f"raw={phase.planningStatus.rawStatus or '(missing)'}; effective={phase.planningStatus.effectiveStatus or '(missing)'}",
                source_type="phase",
                source_id=str(phase.id or phase.phase),
                source_path="",
            )
        )

    mapped_raw = str(primary_context.get("mapped") or "") if primary_context else ""
    normalized_raw = str(primary_context.get("normalized") or "") if primary_context else ""
    if normalized_raw == _INFERRED_COMPLETE_STATUS:
        provenance_source = "inferred_complete"
        provenance_reason = "Primary planning artifact is marked inferred_complete."
    elif raw_status and mapped_raw == effective_status:
        provenance_source = "raw"
        provenance_reason = "Effective feature status matches the primary planning artifact status."
    else:
        provenance_source = "derived"
        provenance_reason = "Effective feature status is derived from combined planning and progress evidence."

    if raw_status and mapped_raw == effective_status:
        mismatch_state = PlanningMismatchState(
            state="aligned",
            reason="Raw and effective feature status are aligned.",
            isMismatch=False,
            evidence=evidence,
        )
    else:
        mismatch_state = PlanningMismatchState(
            state="derived" if effective_status else "unresolved",
            reason="Raw feature status differs from or is missing for the effective feature status.",
            isMismatch=bool(raw_status and effective_status and mapped_raw != effective_status),
            evidence=evidence,
        )

    return PlanningEffectiveStatus(
        rawStatus=raw_status,
        effectiveStatus=effective_status,
        provenance=PlanningStatusProvenance(
            source=provenance_source,  # type: ignore[arg-type]
            reason=provenance_reason,
            evidence=evidence,
        ),
        mismatchState=mismatch_state,
    )


def _derive_feature_dates(feature: Feature) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    planning_doc_types = {"prd", "implementation_plan", "phase_plan", "report", "spec", "document"}
    progress_doc_types = {"progress"}

    planned_candidates: list[dict[str, str]] = []
    started_candidates: list[dict[str, str]] = []
    completed_candidates: list[dict[str, str]] = []
    updated_candidates: list[dict[str, str]] = []
    timeline: list[dict[str, Any]] = []

    for doc in feature.linkedDocs:
        doc_dates = getattr(doc, "dates", None)
        doc_type = str(doc.docType or "").strip().lower()
        created = _date_candidate_from_value(getattr(doc_dates, "createdAt", None), f"document:{doc_type}")
        updated = _date_candidate_from_value(getattr(doc_dates, "updatedAt", None), f"document:{doc_type}")
        completed = _date_candidate_from_value(getattr(doc_dates, "completedAt", None), f"document:{doc_type}")

        if created and doc_type in planning_doc_types:
            planned_candidates.append({**created, "reason": f"{doc_type} created"})
        if created and doc_type in progress_doc_types:
            started_candidates.append({**created, "reason": "progress doc created"})
        if updated:
            updated_candidates.append({**updated, "reason": f"{doc_type} updated"})
        if updated and doc_type in progress_doc_types:
            started_candidates.append({**updated, "reason": "progress doc updated"})
        if completed:
            completed_candidates.append({**completed, "reason": f"{doc_type} completed"})

        for raw_event in getattr(doc, "timeline", []) or []:
            if not isinstance(raw_event, dict):
                continue
            timestamp = normalize_iso_date(raw_event.get("timestamp"))
            if not timestamp:
                continue
            timeline.append({
                "id": f"{doc.id}-{raw_event.get('id') or raw_event.get('kind') or 'event'}",
                "timestamp": timestamp,
                "label": str(raw_event.get("label") or f"{doc_type} update"),
                "kind": str(raw_event.get("kind") or "document"),
                "confidence": str(raw_event.get("confidence") or "low"),
                "source": str(raw_event.get("source") or f"document:{doc.filePath}"),
                "description": str(raw_event.get("description") or ""),
            })

    if feature.updatedAt:
        updated_candidates.append(make_date_value(feature.updatedAt, "low", "feature", "feature_updated"))

    planned_at = choose_earliest(planned_candidates)
    started_at = choose_earliest(started_candidates)
    completed_at = choose_latest(completed_candidates)
    updated_at = choose_latest(updated_candidates)

    if feature.status in _TERMINAL_STATUSES and not completed_at:
        completed_at = choose_first([
            make_date_value(updated_at.get("value", ""), updated_at.get("confidence", "low"), updated_at.get("source", "derived"), "terminal_status_fallback"),
        ])

    last_activity = choose_latest([updated_at, completed_at])

    derived_events = [
        _timeline_event("feature-planned", "Feature Planned", "planned", planned_at, "feature"),
        _timeline_event("feature-started", "Implementation Began", "started", started_at, "feature"),
        _timeline_event("feature-completed", "Feature Completed", "completed", completed_at, "feature"),
        _timeline_event("feature-updated", "Latest Feature Update", "updated", updated_at, "feature"),
    ]
    timeline.extend([event for event in derived_events if event])
    timeline = sorted(
        timeline,
        key=lambda event: normalize_iso_date(str(event.get("timestamp") or "")),
    )

    dates: dict[str, Any] = {}
    if planned_at:
        dates["plannedAt"] = planned_at
    if started_at:
        dates["startedAt"] = started_at
    if completed_at:
        dates["completedAt"] = completed_at
    if updated_at:
        dates["updatedAt"] = updated_at
    if last_activity:
        dates["lastActivityAt"] = last_activity

    return dates, timeline


def _read_frontmatter_status_cached(
    project_root: Path,
    relative_path: str,
    status_cache: dict[str, str],
) -> str:
    normalized = normalize_ref_path(relative_path) or relative_path
    cached = status_cache.get(normalized)
    if cached is not None:
        return cached
    absolute_path = project_root / normalized
    status_value = ""
    try:
        text = absolute_path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(text)
        status_value = str(fm.get("status") or "")
    except Exception:
        status_value = ""
    status_cache[normalized] = status_value
    return status_value


def _reconcile_completion_equivalence(features: list[Feature], project_root: Path) -> int:
    """Infer feature completion from equivalent doc collections and write through inferred status."""
    status_cache: dict[str, str] = {}
    write_updates = 0

    for feature in features:
        prd_statuses: list[str] = []
        plan_statuses: list[str] = []
        phase_plan_statuses: list[str] = []
        completion_doc_paths: list[tuple[str, str]] = []

        for doc in feature.linkedDocs:
            doc_type = str(doc.docType or "").strip().lower()
            if doc_type not in _DOC_WRITE_THROUGH_TYPES:
                continue
            if not _doc_owned_by_feature(doc, feature.id):
                continue
            status_value = _read_frontmatter_status_cached(project_root, doc.filePath, status_cache)
            completion_doc_paths.append((doc_type, doc.filePath))
            if doc_type == "prd":
                prd_statuses.append(status_value)
            elif doc_type == "implementation_plan":
                plan_statuses.append(status_value)
            elif doc_type == "phase_plan":
                phase_plan_statuses.append(status_value)

        prd_complete = any(_is_completion_equivalent_doc_status(s) for s in prd_statuses)
        plan_complete = any(_is_completion_equivalent_doc_status(s) for s in plan_statuses)
        phased_plan_complete = bool(phase_plan_statuses) and all(
            _is_completion_equivalent_doc_status(s) for s in phase_plan_statuses
        )
        progress_complete = bool(feature.phases) and all(_phase_is_completion_equivalent(p) for p in feature.phases)

        equivalent_complete = prd_complete or plan_complete or phased_plan_complete or progress_complete
        if not equivalent_complete:
            continue

        feature.status = _max_status(feature.status, "done")

        for doc_type, relative_path in completion_doc_paths:
            if doc_type not in {"prd", "implementation_plan", "phase_plan"}:
                continue
            current_status = _read_frontmatter_status_cached(project_root, relative_path, status_cache)
            if _is_completion_equivalent_doc_status(current_status):
                continue
            normalized = normalize_ref_path(relative_path) or relative_path
            absolute_path = project_root / normalized
            if not absolute_path.exists():
                continue
            try:
                update_frontmatter_field(absolute_path, "status", _INFERRED_COMPLETE_STATUS)
                status_cache[normalized] = _INFERRED_COMPLETE_STATUS
                write_updates += 1
            except FrontmatterParseError as exc:
                logger.warning("Skipping inferred status write for %s: %s", absolute_path, exc)
            except Exception:
                logger.exception("Failed to write inferred status for %s", absolute_path)

    return write_updates


def scan_features(
    docs_dir: Path,
    progress_dir: Path,
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> list[Feature]:
    """
    Discover features by cross-referencing impl plans, PRDs, and progress dirs.

    Priority: impl plans seed features, enriched with PRD + progress data.
    """
    project_root = infer_project_root(docs_dir, progress_dir)
    impl_plans = _scan_impl_plans(
        docs_dir,
        project_root,
        git_date_index=git_date_index,
        dirty_paths=dirty_paths,
    )
    prds = _scan_prds(
        docs_dir,
        project_root,
        git_date_index=git_date_index,
        dirty_paths=dirty_paths,
    )
    progress_data = _scan_progress_dirs(
        progress_dir,
        project_root,
        git_date_index=git_date_index,
        dirty_paths=dirty_paths,
    )
    auxiliary_docs = _scan_auxiliary_docs(
        docs_dir,
        progress_dir,
        project_root,
        git_date_index=git_date_index,
        dirty_paths=dirty_paths,
    )

    features: dict[str, Feature] = {}

    # Step 1: Seed features from implementation plans
    for slug, plan in impl_plans.items():
        linked_docs = [
                LinkedDocument(
                    id=f"PLAN-{slug}",
                    title=plan["title"],
                    filePath=plan["rel_path"],
                    docType="implementation_plan",
                    category=plan.get("category", ""),
                    slug=slug,
                    canonicalSlug=_base_slug(slug),
                    featureFamily=str(plan.get("feature_family") or ""),
                    primaryDocRole=str(plan.get("primary_doc_role") or ""),
                    blockedBy=[str(v) for v in plan.get("blocked_by", []) if isinstance(v, str)],
                    sequenceOrder=plan.get("sequence_order"),
                    frontmatterKeys=plan.get("frontmatter_keys", []),
                    relatedRefs=plan.get("related_refs", []),
                    prdRef=plan.get("prd_ref", ""),
                    lineageFamily=str(plan.get("lineage_family", "")),
                    lineageParent=str(plan.get("lineage_parent", "")),
                    lineageChildren=[str(v) for v in plan.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(plan.get("lineage_type", "")),
                    linkedFeatures=_normalize_linked_feature_refs(plan.get("linked_feature_refs")),
                    dates=plan.get("dates", {}),
                    timeline=plan.get("timeline", []),
                )
        ]

        # Add phase sub-plan docs
        for pd in plan.get("phase_docs", []):
            linked_docs.append(LinkedDocument(
                id=f"PHASE-{pd['slug']}",
                title=pd["title"],
                filePath=pd["path"],
                docType="phase_plan",
                category=pd.get("category", ""),
                slug=pd["slug"],
                canonicalSlug=_base_slug(pd["slug"]),
                featureFamily=str(pd.get("feature_family") or ""),
                primaryDocRole=str(pd.get("primary_doc_role") or ""),
                blockedBy=[str(v) for v in pd.get("blocked_by", []) if isinstance(v, str)],
                sequenceOrder=pd.get("sequence_order"),
                frontmatterKeys=pd.get("frontmatter_keys", []),
                relatedRefs=pd.get("related_refs", []),
                prdRef=pd.get("prd_ref", ""),
                lineageFamily=str(pd.get("lineage_family", "")),
                lineageParent=str(pd.get("lineage_parent", "")),
                lineageChildren=[str(v) for v in pd.get("lineage_children", []) if isinstance(v, str)],
                lineageType=str(pd.get("lineage_type", "")),
                linkedFeatures=_normalize_linked_feature_refs(pd.get("linked_feature_refs")),
                dates=pd.get("dates", {}),
                timeline=pd.get("timeline", []),
            ))

        features[slug] = Feature(
            id=slug,
            name=plan["title"],
            status=_map_status(plan["status"]),
            category=plan["category"],
            tags=plan["tags"],
            featureFamily=str(plan.get("feature_family") or ""),
            updatedAt=plan["updated"],
            linkedDocs=linked_docs,
        )

    # Step 2: Match PRDs to features
    for prd_slug, prd in prds.items():
        matched_feature_id: Optional[str] = None

        # Try exact slug match
        if prd_slug in features:
            matched_feature_id = prd_slug

        # Try matching via PRD's related links → impl plan paths
        if not matched_feature_id:
            for related_path in prd.get("related", []):
                # Extract slug from path like /docs/project_plans/implementation_plans/.../discovery-cache-fixes-v1.md
                related_stem = Path(related_path).stem.lower()
                if related_stem in features:
                    matched_feature_id = related_stem
                    break

        # Try base slug matching (strip version suffixes)
        if not matched_feature_id:
            prd_base = _base_slug(prd_slug)
            for feat_slug in features:
                if _base_slug(feat_slug) == prd_base:
                    matched_feature_id = feat_slug
                    break

        if matched_feature_id:
            # Enrich existing feature with PRD
            feat = features[matched_feature_id]
            feat.linkedDocs.append(LinkedDocument(
                id=f"PRD-{prd_slug}",
                title=prd["title"],
                filePath=prd["rel_path"],
                docType="prd",
                category="PRDs",
                slug=prd_slug,
                canonicalSlug=_base_slug(prd_slug),
                featureFamily=str(prd.get("feature_family") or ""),
                primaryDocRole=str(prd.get("primary_doc_role") or ""),
                blockedBy=[str(v) for v in prd.get("blocked_by", []) if isinstance(v, str)],
                sequenceOrder=prd.get("sequence_order"),
                frontmatterKeys=prd.get("frontmatter_keys", []),
                relatedRefs=prd.get("related_refs", []),
                prdRef=prd.get("prd_ref", ""),
                lineageFamily=str(prd.get("lineage_family", "")),
                lineageParent=str(prd.get("lineage_parent", "")),
                lineageChildren=[str(v) for v in prd.get("lineage_children", []) if isinstance(v, str)],
                lineageType=str(prd.get("lineage_type", "")),
                linkedFeatures=_normalize_linked_feature_refs(prd.get("linked_feature_refs")),
                dates=prd.get("dates", {}),
                timeline=prd.get("timeline", []),
            ))
            # Merge tags
            for tag in prd.get("tags", []):
                if tag not in feat.tags:
                    feat.tags.append(tag)
        else:
            # Standalone PRD → create new feature
            features[prd_slug] = Feature(
                id=prd_slug,
                name=prd["title"],
                status=_map_status(prd["status"]),
                tags=prd.get("tags", []),
                featureFamily=str(prd.get("feature_family") or ""),
                updatedAt=prd.get("updated", ""),
                linkedDocs=[LinkedDocument(
                    id=f"PRD-{prd_slug}",
                    title=prd["title"],
                    filePath=prd["rel_path"],
                    docType="prd",
                    category="PRDs",
                    slug=prd_slug,
                    canonicalSlug=_base_slug(prd_slug),
                    featureFamily=str(prd.get("feature_family") or ""),
                    primaryDocRole=str(prd.get("primary_doc_role") or ""),
                    blockedBy=[str(v) for v in prd.get("blocked_by", []) if isinstance(v, str)],
                    sequenceOrder=prd.get("sequence_order"),
                    frontmatterKeys=prd.get("frontmatter_keys", []),
                    relatedRefs=prd.get("related_refs", []),
                    prdRef=prd.get("prd_ref", ""),
                    lineageFamily=str(prd.get("lineage_family", "")),
                    lineageParent=str(prd.get("lineage_parent", "")),
                    lineageChildren=[str(v) for v in prd.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(prd.get("lineage_type", "")),
                    linkedFeatures=_normalize_linked_feature_refs(prd.get("linked_feature_refs")),
                    dates=prd.get("dates", {}),
                    timeline=prd.get("timeline", []),
                )],
            )

    # Step 3: Attach progress data to features
    for prog_slug, prog in progress_data.items():
        matched_feature_id: Optional[str] = None

        # Try exact slug match
        if prog_slug in features:
            matched_feature_id = prog_slug

        # Try the prd_slug from progress file metadata
        if not matched_feature_id and prog.get("prd_slug"):
            prd_sl = prog["prd_slug"]
            prd_sl_base = _base_slug(prd_sl)
            if prd_sl in features:
                matched_feature_id = prd_sl
            else:
                for feat_slug in features:
                    if _base_slug(feat_slug) == prd_sl_base:
                        matched_feature_id = feat_slug
                        break

        # Try base slug matching
        if not matched_feature_id:
            prog_base = _base_slug(prog_slug)
            for feat_slug in features:
                if _base_slug(feat_slug) == prog_base:
                    matched_feature_id = feat_slug
                    break

        if matched_feature_id:
            feat = features[matched_feature_id]
            feat.phases = prog["phases"]
            for phase in feat.phases:
                phase.id = phase.id or f"{feat.id}:phase:{phase.phase}"
                for task in phase.tasks:
                    task.featureId = feat.id
                    task.phaseId = phase.id
                for batch in phase.phaseBatches:
                    batch.featureSlug = feat.id

            # Smart status inference: take the furthest progression
            feat.status = _max_status(feat.status, prog["status"])

            # Update counts
            feat.totalTasks = sum(p.totalTasks for p in feat.phases)
            feat.completedTasks = sum(p.completedTasks for p in feat.phases)
            feat.deferredTasks = sum(p.deferredTasks for p in feat.phases)

            # Update timestamp if progress has a newer one
            if prog["updated"] and prog["updated"] > feat.updatedAt:
                feat.updatedAt = prog["updated"]
            existing_paths = {doc.filePath for doc in feat.linkedDocs}
            for progress_doc in prog.get("docs", []):
                file_path = str(progress_doc.get("path") or "")
                if not file_path or file_path in existing_paths:
                    continue
                doc_slug = str(progress_doc.get("slug") or Path(file_path).stem).lower()
                feat.linkedDocs.append(LinkedDocument(
                    id=f"PROGRESS-{doc_slug}",
                    title=str(progress_doc.get("title") or doc_slug),
                    filePath=file_path,
                    docType="progress",
                    category=str(progress_doc.get("category") or ""),
                    slug=doc_slug,
                    canonicalSlug=_base_slug(doc_slug),
                    featureFamily=str(progress_doc.get("feature_family") or ""),
                    primaryDocRole=str(progress_doc.get("primary_doc_role") or ""),
                    blockedBy=[str(v) for v in progress_doc.get("blocked_by", []) if isinstance(v, str)],
                    sequenceOrder=progress_doc.get("sequence_order"),
                    frontmatterKeys=[str(v) for v in progress_doc.get("frontmatter_keys", []) if isinstance(v, str)],
                    relatedRefs=[str(v) for v in progress_doc.get("related_refs", []) if isinstance(v, str)],
                    prdRef=str(progress_doc.get("prd_ref") or ""),
                    lineageFamily=str(progress_doc.get("lineage_family") or ""),
                    lineageParent=str(progress_doc.get("lineage_parent") or ""),
                    lineageChildren=[str(v) for v in progress_doc.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(progress_doc.get("lineage_type") or ""),
                    linkedFeatures=_normalize_linked_feature_refs(progress_doc.get("linked_feature_refs")),
                    dates=progress_doc.get("dates", {}),
                    timeline=progress_doc.get("timeline", []),
                ))
                existing_paths.add(file_path)
        else:
            # Progress dir with no matching plan or PRD → create feature
            # Use slug as name, cleaned up
            name = prog_slug.replace("-", " ").replace("_", " ").title()
            phases = prog["phases"]
            linked_docs: list[LinkedDocument] = []
            for progress_doc in prog.get("docs", []):
                file_path = str(progress_doc.get("path") or "")
                if not file_path:
                    continue
                doc_slug = str(progress_doc.get("slug") or Path(file_path).stem).lower()
                linked_docs.append(LinkedDocument(
                    id=f"PROGRESS-{doc_slug}",
                    title=str(progress_doc.get("title") or doc_slug),
                    filePath=file_path,
                    docType="progress",
                    category=str(progress_doc.get("category") or ""),
                    slug=doc_slug,
                    canonicalSlug=_base_slug(doc_slug),
                    featureFamily=str(progress_doc.get("feature_family") or ""),
                    primaryDocRole=str(progress_doc.get("primary_doc_role") or ""),
                    blockedBy=[str(v) for v in progress_doc.get("blocked_by", []) if isinstance(v, str)],
                    sequenceOrder=progress_doc.get("sequence_order"),
                    frontmatterKeys=[str(v) for v in progress_doc.get("frontmatter_keys", []) if isinstance(v, str)],
                    relatedRefs=[str(v) for v in progress_doc.get("related_refs", []) if isinstance(v, str)],
                    prdRef=str(progress_doc.get("prd_ref") or ""),
                    lineageFamily=str(progress_doc.get("lineage_family") or ""),
                    lineageParent=str(progress_doc.get("lineage_parent") or ""),
                    lineageChildren=[str(v) for v in progress_doc.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(progress_doc.get("lineage_type") or ""),
                    linkedFeatures=_normalize_linked_feature_refs(progress_doc.get("linked_feature_refs")),
                    dates=progress_doc.get("dates", {}),
                    timeline=progress_doc.get("timeline", []),
                ))
            features[prog_slug] = Feature(
                id=prog_slug,
                name=name,
                status=prog["status"],
                totalTasks=sum(p.totalTasks for p in phases),
                completedTasks=sum(p.completedTasks for p in phases),
                deferredTasks=sum(p.deferredTasks for p in phases),
                phases=phases,
                featureFamily=str(prog.get("feature_family") or ""),
                updatedAt=prog.get("updated", ""),
                linkedDocs=linked_docs,
            )
            for phase in features[prog_slug].phases:
                phase.id = phase.id or f"{prog_slug}:phase:{phase.phase}"
                for task in phase.tasks:
                    task.featureId = prog_slug
                    task.phaseId = phase.id
                for batch in phase.phaseBatches:
                    batch.featureSlug = prog_slug

    # Step 4: Augment features with auxiliary docs (reports/specs/additional plans/PRD versions).
    for feat in features.values():
        aliases = _feature_aliases(feat)
        existing_paths = {doc.filePath for doc in feat.linkedDocs}
        for doc in auxiliary_docs:
            file_path = str(doc.get("filePath") or "")
            if not file_path or file_path in existing_paths:
                continue
            if not _doc_matches_feature(doc, aliases, feat.id):
                continue
            feat.linkedDocs.append(LinkedDocument(
                id=str(doc.get("id") or _linked_doc_id_from_path(file_path)),
                title=str(doc.get("title") or file_path),
                filePath=file_path,
                docType=str(doc.get("docType") or "document"),
                category=str(doc.get("category") or ""),
                slug=str(doc.get("slug") or Path(file_path).stem.lower()),
                canonicalSlug=str(doc.get("canonicalSlug") or _base_slug(Path(file_path).stem.lower())),
                featureFamily=str(doc.get("featureFamily") or ""),
                primaryDocRole=str(doc.get("primaryDocRole") or ""),
                blockedBy=[str(v) for v in doc.get("blockedBy", []) if isinstance(v, str)],
                sequenceOrder=doc.get("sequenceOrder"),
                frontmatterKeys=[str(v) for v in doc.get("frontmatterKeys", []) if isinstance(v, str)],
                relatedRefs=[str(v) for v in doc.get("relatedRefs", []) if isinstance(v, str)],
                prdRef=str(doc.get("prdRef") or ""),
                lineageFamily=str(doc.get("lineageFamily") or ""),
                lineageParent=str(doc.get("lineageParent") or ""),
                lineageChildren=[str(v) for v in doc.get("lineageChildren", []) if isinstance(v, str)],
                lineageType=str(doc.get("lineageType") or ""),
                linkedFeatures=_normalize_linked_feature_refs(doc.get("linkedFeatures")),
                dates=doc.get("dates", {}),
                timeline=doc.get("timeline", []),
            ))
            existing_paths.add(file_path)

    # Step 5: Derive normalized feature dates and timeline from linked docs/progress evidence.
    for feat in features.values():
        dates, timeline = _derive_feature_dates(feat)
        feat.dates = EntityDates.model_validate(
            _normalize_entity_dates_payload(dates if isinstance(dates, dict) else {})
        )
        feat.timeline = [
            TimelineEvent.model_validate(event)
            for event in _normalize_timeline_payload(timeline if isinstance(timeline, list) else [])
        ]
        feat.plannedAt = str(feat.dates.plannedAt.value if feat.dates.plannedAt else "")
        feat.startedAt = str(feat.dates.startedAt.value if feat.dates.startedAt else "")
        feat.completedAt = str(feat.dates.completedAt.value if feat.dates.completedAt else "")
        derived_updated = str(feat.dates.updatedAt.value if feat.dates.updatedAt else "")
        if derived_updated:
            feat.updatedAt = derived_updated

        rollups = _derive_feature_rollups(feat, project_root)
        feat.description = str(rollups.get("description") or feat.description or "")
        feat.summary = str(rollups.get("summary") or feat.summary or "")
        feat.priority = str(rollups.get("priority") or feat.priority or "")
        feat.riskLevel = str(rollups.get("riskLevel") or feat.riskLevel or "")
        feat.complexity = str(rollups.get("complexity") or feat.complexity or "")
        feat.track = str(rollups.get("track") or feat.track or "")
        feat.timelineEstimate = str(rollups.get("timelineEstimate") or feat.timelineEstimate or "")
        feat.targetRelease = str(rollups.get("targetRelease") or feat.targetRelease or "")
        feat.milestone = str(rollups.get("milestone") or feat.milestone or "")
        feat.featureFamily = str(rollups.get("featureFamily") or feat.featureFamily or "")
        feat.owners = [str(v) for v in rollups.get("owners") or feat.owners]
        feat.contributors = [str(v) for v in rollups.get("contributors") or feat.contributors]
        feat.requestLogIds = [str(v) for v in rollups.get("requestLogIds") or feat.requestLogIds]
        feat.commitRefs = [str(v) for v in rollups.get("commitRefs") or feat.commitRefs]
        feat.prRefs = [str(v) for v in rollups.get("prRefs") or feat.prRefs]
        feat.executionReadiness = str(rollups.get("executionReadiness") or feat.executionReadiness or "")
        feat.testImpact = str(rollups.get("testImpact") or feat.testImpact or "")
        primary_docs = rollups.get("primaryDocuments")
        if isinstance(primary_docs, FeaturePrimaryDocuments):
            feat.primaryDocuments = primary_docs
        document_coverage = rollups.get("documentCoverage")
        if isinstance(document_coverage, FeatureDocumentCoverage):
            feat.documentCoverage = document_coverage
        quality_signals = rollups.get("qualitySignals")
        if isinstance(quality_signals, FeatureQualitySignals):
            feat.qualitySignals = quality_signals
        feat.planningStatus = _derive_feature_planning_status(feat, project_root)

    # Step 6: Link related features (same base slug, different versions)
    feature_list = list(features.values())
    feature_ids = sorted(features.keys())
    related_by_id: dict[str, set[str]] = {feat_id: set() for feat_id in feature_ids}
    relation_refs_by_id: dict[str, list[LinkedFeatureRef]] = {feat_id: [] for feat_id in feature_ids}

    def _add_relation_ref(
        source_id: str,
        target_id: str,
        relation_type: str,
        source: str,
        confidence: float | None,
        *,
        notes: str = "",
        evidence: list[str] | None = None,
    ) -> None:
        if source_id == target_id or source_id not in related_by_id or target_id not in related_by_id:
            return
        related_by_id[source_id].add(target_id)
        relation_refs_by_id[source_id].append(
            LinkedFeatureRef(
                feature=target_id,
                type=relation_type,
                source=source,
                confidence=confidence,
                notes=notes,
                evidence=[str(v) for v in (evidence or []) if str(v).strip()],
            )
        )

    base_groups: dict[str, list[str]] = {}
    for feat in feature_list:
        base = _base_slug(feat.id)
        base_groups.setdefault(base, []).append(feat.id)

    for group in base_groups.values():
        if len(group) > 1:
            for feat_id in group:
                for other_id in group:
                    if other_id != feat_id:
                        _add_relation_ref(
                            feat_id,
                            other_id,
                            "version_peer",
                            "derived_lineage",
                            1.0,
                        )

    def _resolve_lineage_target_ids(raw_ref: str, current_id: str) -> list[str]:
        token = _normalize_feature_ref(raw_ref)
        if not token:
            return []
        if token in features and token != current_id:
            return [token]
        token_base = _base_slug(token)
        return [feat_id for feat_id in feature_ids if feat_id != current_id and _base_slug(feat_id) == token_base]

    for feat in feature_list:
        for doc in feat.linkedDocs:
            for raw_ref in [str(doc.lineageParent or ""), *[str(v) for v in doc.lineageChildren or []]]:
                is_parent_ref = bool(str(doc.lineageParent or "").strip()) and raw_ref == str(doc.lineageParent or "")
                for target_id in _resolve_lineage_target_ids(raw_ref, feat.id):
                    if is_parent_ref:
                        _add_relation_ref(
                            feat.id,
                            target_id,
                            "lineage_parent",
                            "derived_lineage",
                            1.0,
                            evidence=[doc.filePath],
                        )
                        _add_relation_ref(
                            target_id,
                            feat.id,
                            "lineage_child",
                            "derived_lineage",
                            1.0,
                            evidence=[doc.filePath],
                        )
                    else:
                        _add_relation_ref(
                            feat.id,
                            target_id,
                            "lineage_child",
                            "derived_lineage",
                            1.0,
                            evidence=[doc.filePath],
                        )
                        _add_relation_ref(
                            target_id,
                            feat.id,
                            "lineage_parent",
                            "derived_lineage",
                            1.0,
                            evidence=[doc.filePath],
                        )
            lineage_family = canonical_slug(str(doc.lineageFamily or "").strip().lower())
            if not lineage_family:
                continue
            for target_id in feature_ids:
                if target_id == feat.id:
                    continue
                if _base_slug(target_id) == lineage_family:
                    _add_relation_ref(
                        feat.id,
                        target_id,
                        "lineage_family",
                        "derived_lineage",
                        0.9,
                        evidence=[doc.filePath],
                    )
                    _add_relation_ref(
                        target_id,
                        feat.id,
                        "lineage_family",
                        "derived_lineage",
                        0.9,
                        evidence=[doc.filePath],
                    )

    shared_doc_refs: dict[str, set[str]] = {}
    for feat in feature_list:
        for doc in feat.linkedDocs:
            for raw_ref in [*[str(v) for v in doc.relatedRefs or []], str(doc.prdRef or "")]:
                ref_value = str(raw_ref or "").strip()
                if not ref_value:
                    continue
                normalized_path = normalize_ref_path(ref_value)
                ref_token = normalized_path if normalized_path else canonical_slug(ref_value)
                if not ref_token:
                    continue
                shared_doc_refs.setdefault(ref_token, set()).add(feat.id)

    for ref_token, feature_group in shared_doc_refs.items():
        if len(feature_group) < 2:
            continue
        members = sorted(feature_group)
        for idx, source_id in enumerate(members):
            for target_id in members[idx + 1 :]:
                _add_relation_ref(
                    source_id,
                    target_id,
                    "shared_document_context",
                    "inferred",
                    0.65,
                    evidence=[ref_token],
                )
                _add_relation_ref(
                    target_id,
                    source_id,
                    "shared_document_context",
                    "inferred",
                    0.65,
                    evidence=[ref_token],
                )

    for feat_id in feature_ids:
        features[feat_id].relatedFeatures = sorted(related_by_id[feat_id])
        features[feat_id].linkedFeatures = _aggregate_feature_linked_features(
            features[feat_id],
            related_by_id[feat_id],
            relation_refs_by_id.get(feat_id, []),
        )

    inferred_updates = _reconcile_completion_equivalence(feature_list, project_root)

    result = sorted(feature_list, key=lambda f: f.updatedAt or "", reverse=True)
    terminal_count = sum(1 for f in result if f.status in _TERMINAL_STATUSES)
    logger.info(
        "Discovered %s features (%s terminal, %s inferred write-through updates)",
        len(result),
        terminal_count,
        inferred_updates,
    )
    return result
