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
    Feature,
    FeaturePhase,
    LinkedDocument,
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
from backend.parsers.status_writer import update_frontmatter_field
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
        "frontmatter_keys": sorted(str(key) for key in frontmatter.keys()),
        "related_refs": [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)],
        "feature_refs": [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)],
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
                    "frontmatter_keys": doc_meta["frontmatter_keys"],
                    "related_refs": doc_meta["related_refs"],
                    "prd_ref": doc_meta["prd_ref"],
                    "lineage_family": doc_meta.get("lineage_family", ""),
                    "lineage_parent": doc_meta.get("lineage_parent", ""),
                    "lineage_children": doc_meta.get("lineage_children", []),
                    "lineage_type": doc_meta.get("lineage_type", ""),
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
            "frontmatter_keys": doc_meta["frontmatter_keys"],
            "related_refs": doc_meta["related_refs"],
            "lineage_family": doc_meta.get("lineage_family", ""),
            "lineage_parent": doc_meta.get("lineage_parent", ""),
            "lineage_children": doc_meta.get("lineage_children", []),
            "lineage_type": doc_meta.get("lineage_type", ""),
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
            "frontmatter_keys": doc_meta["frontmatter_keys"],
            "related_refs": doc_meta["related_refs"],
            "prd_ref": doc_meta["prd_ref"],
            "lineage_family": doc_meta.get("lineage_family", ""),
            "lineage_parent": doc_meta.get("lineage_parent", ""),
            "lineage_children": doc_meta.get("lineage_children", []),
            "lineage_type": doc_meta.get("lineage_type", ""),
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
                "category": doc_meta["category"],
                "frontmatter_keys": doc_meta["frontmatter_keys"],
                "related_refs": doc_meta["related_refs"],
                "prd_ref": doc_meta["prd_ref"],
                "lineage_family": doc_meta.get("lineage_family", ""),
                "lineage_parent": doc_meta.get("lineage_parent", ""),
                "lineage_children": doc_meta.get("lineage_children", []),
                "lineage_type": doc_meta.get("lineage_type", ""),
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
                "frontmatterKeys": metadata["frontmatter_keys"],
                "relatedRefs": metadata["related_refs"],
                "prdRef": str(metadata["prd_ref"] or ""),
                "featureRefs": feature_refs,
                "aliases": aliases,
                "lineageFamily": str(metadata.get("lineage_family") or ""),
                "lineageParent": str(metadata.get("lineage_parent") or ""),
                "lineageChildren": [str(v) for v in metadata.get("lineage_children", []) if isinstance(v, str)],
                "lineageType": str(metadata.get("lineage_type") or ""),
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


def _doc_matches_feature(doc: dict[str, Any], feature_aliases: set[str]) -> bool:
    feature_bases = {_base_slug(alias) for alias in feature_aliases if alias}
    doc_type = str(doc.get("docType") or "").strip().lower()

    def _matches_feature(candidate: str) -> bool:
        value = (candidate or "").strip().lower()
        if not value:
            return False
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
    feature_base = _base_slug(feature_id)

    path_feature_slug = feature_slug_from_path(str(doc.filePath or ""))
    if path_feature_slug:
        return _base_slug(path_feature_slug) == feature_base

    doc_slug = (doc.slug or Path(doc.filePath).stem).strip().lower()
    if doc_slug and _base_slug(doc_slug) == feature_base:
        return True

    canonical = str(doc.canonicalSlug or "").strip().lower()
    if canonical and _base_slug(canonical) == feature_base:
        return True

    return False


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
                    frontmatterKeys=plan.get("frontmatter_keys", []),
                    relatedRefs=plan.get("related_refs", []),
                    prdRef=plan.get("prd_ref", ""),
                    lineageFamily=str(plan.get("lineage_family", "")),
                    lineageParent=str(plan.get("lineage_parent", "")),
                    lineageChildren=[str(v) for v in plan.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(plan.get("lineage_type", "")),
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
                frontmatterKeys=pd.get("frontmatter_keys", []),
                relatedRefs=pd.get("related_refs", []),
                prdRef=pd.get("prd_ref", ""),
                lineageFamily=str(pd.get("lineage_family", "")),
                lineageParent=str(pd.get("lineage_parent", "")),
                lineageChildren=[str(v) for v in pd.get("lineage_children", []) if isinstance(v, str)],
                lineageType=str(pd.get("lineage_type", "")),
                dates=pd.get("dates", {}),
                timeline=pd.get("timeline", []),
            ))

        features[slug] = Feature(
            id=slug,
            name=plan["title"],
            status=_map_status(plan["status"]),
            category=plan["category"],
            tags=plan["tags"],
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
                frontmatterKeys=prd.get("frontmatter_keys", []),
                relatedRefs=prd.get("related_refs", []),
                prdRef=prd.get("prd_ref", ""),
                lineageFamily=str(prd.get("lineage_family", "")),
                lineageParent=str(prd.get("lineage_parent", "")),
                lineageChildren=[str(v) for v in prd.get("lineage_children", []) if isinstance(v, str)],
                lineageType=str(prd.get("lineage_type", "")),
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
                updatedAt=prd.get("updated", ""),
                linkedDocs=[LinkedDocument(
                    id=f"PRD-{prd_slug}",
                    title=prd["title"],
                    filePath=prd["rel_path"],
                    docType="prd",
                    category="PRDs",
                    slug=prd_slug,
                    canonicalSlug=_base_slug(prd_slug),
                    frontmatterKeys=prd.get("frontmatter_keys", []),
                    relatedRefs=prd.get("related_refs", []),
                    prdRef=prd.get("prd_ref", ""),
                    lineageFamily=str(prd.get("lineage_family", "")),
                    lineageParent=str(prd.get("lineage_parent", "")),
                    lineageChildren=[str(v) for v in prd.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(prd.get("lineage_type", "")),
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
                    frontmatterKeys=[str(v) for v in progress_doc.get("frontmatter_keys", []) if isinstance(v, str)],
                    relatedRefs=[str(v) for v in progress_doc.get("related_refs", []) if isinstance(v, str)],
                    prdRef=str(progress_doc.get("prd_ref") or ""),
                    lineageFamily=str(progress_doc.get("lineage_family") or ""),
                    lineageParent=str(progress_doc.get("lineage_parent") or ""),
                    lineageChildren=[str(v) for v in progress_doc.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(progress_doc.get("lineage_type") or ""),
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
                    frontmatterKeys=[str(v) for v in progress_doc.get("frontmatter_keys", []) if isinstance(v, str)],
                    relatedRefs=[str(v) for v in progress_doc.get("related_refs", []) if isinstance(v, str)],
                    prdRef=str(progress_doc.get("prd_ref") or ""),
                    lineageFamily=str(progress_doc.get("lineage_family") or ""),
                    lineageParent=str(progress_doc.get("lineage_parent") or ""),
                    lineageChildren=[str(v) for v in progress_doc.get("lineage_children", []) if isinstance(v, str)],
                    lineageType=str(progress_doc.get("lineage_type") or ""),
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
                updatedAt=prog.get("updated", ""),
                linkedDocs=linked_docs,
            )

    # Step 4: Augment features with auxiliary docs (reports/specs/additional plans/PRD versions).
    for feat in features.values():
        aliases = _feature_aliases(feat)
        existing_paths = {doc.filePath for doc in feat.linkedDocs}
        for doc in auxiliary_docs:
            file_path = str(doc.get("filePath") or "")
            if not file_path or file_path in existing_paths:
                continue
            if not _doc_matches_feature(doc, aliases):
                continue
            feat.linkedDocs.append(LinkedDocument(
                id=str(doc.get("id") or _linked_doc_id_from_path(file_path)),
                title=str(doc.get("title") or file_path),
                filePath=file_path,
                docType=str(doc.get("docType") or "document"),
                category=str(doc.get("category") or ""),
                slug=str(doc.get("slug") or Path(file_path).stem.lower()),
                canonicalSlug=str(doc.get("canonicalSlug") or _base_slug(Path(file_path).stem.lower())),
                frontmatterKeys=[str(v) for v in doc.get("frontmatterKeys", []) if isinstance(v, str)],
                relatedRefs=[str(v) for v in doc.get("relatedRefs", []) if isinstance(v, str)],
                prdRef=str(doc.get("prdRef") or ""),
                lineageFamily=str(doc.get("lineageFamily") or ""),
                lineageParent=str(doc.get("lineageParent") or ""),
                lineageChildren=[str(v) for v in doc.get("lineageChildren", []) if isinstance(v, str)],
                lineageType=str(doc.get("lineageType") or ""),
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

    # Step 6: Link related features (same base slug, different versions)
    feature_list = list(features.values())
    feature_ids = sorted(features.keys())
    related_by_id: dict[str, set[str]] = {feat_id: set() for feat_id in feature_ids}
    base_groups: dict[str, list[str]] = {}
    for feat in feature_list:
        base = _base_slug(feat.id)
        base_groups.setdefault(base, []).append(feat.id)

    for group in base_groups.values():
        if len(group) > 1:
            for feat_id in group:
                for other_id in group:
                    if other_id != feat_id:
                        related_by_id[feat_id].add(other_id)

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
                for target_id in _resolve_lineage_target_ids(raw_ref, feat.id):
                    related_by_id[feat.id].add(target_id)
                    related_by_id[target_id].add(feat.id)
            lineage_family = canonical_slug(str(doc.lineageFamily or "").strip().lower())
            if not lineage_family:
                continue
            for target_id in feature_ids:
                if target_id == feat.id:
                    continue
                if _base_slug(target_id) == lineage_family:
                    related_by_id[feat.id].add(target_id)

    for feat_id in feature_ids:
        features[feat_id].relatedFeatures = sorted(related_by_id[feat_id])

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
