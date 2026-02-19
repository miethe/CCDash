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
    Feature,
    FeaturePhase,
    LinkedDocument,
    ProjectTask,
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

logger = logging.getLogger("ccdash")

# ── Status helpers ──────────────────────────────────────────────────

# Ordering for "furthest progression" inference.
# `deferred` is completion-equivalent with `done`.
_STATUS_ORDER = {"backlog": 0, "in-progress": 1, "review": 2, "done": 3, "deferred": 3}
_TERMINAL_STATUSES = {"done", "deferred"}
_DOC_COMPLETION_STATUSES = {"completed", "deferred", "inferred_complete"}
_DOC_WRITE_THROUGH_TYPES = {"prd", "implementation_plan", "phase_plan"}
_INFERRED_COMPLETE_STATUS = "inferred_complete"


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


def _slug_from_path(path: Path) -> str:
    """Derive a slug from a file's stem, stripping version suffixes for matching."""
    return path.stem.lower()


def _base_slug(slug: str) -> str:
    """Strip trailing version markers (-v1, -v1.5, -v2) for related-feature matching."""
    return canonical_slug(slug)


def _project_relative(path: Path, project_root: Path) -> str:
    return canonical_project_path(path, project_root)


def _extract_doc_metadata(path: Path, project_root: Path, frontmatter: dict[str, Any]) -> dict[str, Any]:
    project_rel = _project_relative(path, project_root)
    refs = extract_frontmatter_references(frontmatter)
    slug = _slug_from_path(path)
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
    }


# ── Phase 1: Scan Implementation Plans ──────────────────────────────

def _scan_impl_plans(docs_dir: Path, project_root: Path) -> dict[str, dict]:
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
        updated = str(fm.get("updated", fm.get("created", "")))
        doc_meta = _extract_doc_metadata(path, project_root, fm)
        rel_path = doc_meta["file_path"]

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
            "phase_docs": [],
        }

    return plans


# ── Phase 2: Scan PRDs ──────────────────────────────────────────────

def _scan_prds(docs_dir: Path, project_root: Path) -> dict[str, dict]:
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
        updated = str(fm.get("updated", fm.get("created", "")))
        doc_meta = _extract_doc_metadata(path, project_root, fm)
        rel_path = doc_meta["file_path"]

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


def _scan_progress_dirs(progress_dir: Path, project_root: Path) -> dict[str, dict]:
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

            updated = str(fm.get("updated", fm.get("completed_at", "")))
            if updated and updated > latest_updated:
                latest_updated = updated

            doc_meta = _extract_doc_metadata(md_file, project_root, fm)
            progress_docs.append({
                "path": doc_meta["file_path"],
                "title": str(fm.get("title", md_file.stem.replace("-", " ").title())),
                "slug": doc_meta["slug"],
                "category": doc_meta["category"],
                "frontmatter_keys": doc_meta["frontmatter_keys"],
                "related_refs": doc_meta["related_refs"],
                "prd_ref": doc_meta["prd_ref"],
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


def _scan_auxiliary_docs(docs_dir: Path, progress_dir: Path, project_root: Path) -> list[dict[str, Any]]:
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
            metadata = _extract_doc_metadata(path, project_root, fm)
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

    def _matches_feature(candidate: str) -> bool:
        value = (candidate or "").strip().lower()
        if not value:
            return False
        return value in feature_aliases or _base_slug(value) in feature_bases

    doc_path = str(doc.get("filePath") or "")
    path_feature_slug = feature_slug_from_path(doc_path)
    if path_feature_slug and _matches_feature(path_feature_slug):
        return True
    feature_refs = {str(v).lower() for v in doc.get("featureRefs", []) if str(v).strip()}
    if any(_matches_feature(feature_ref) for feature_ref in feature_refs):
        return True
    prd_ref = str(doc.get("prdRef") or "").strip().lower()
    if prd_ref:
        prd_slug = feature_slug_from_path(prd_ref) if ("/" in prd_ref or prd_ref.endswith(".md")) else prd_ref
        if _matches_feature(prd_slug):
            return True
    return False


def _phase_is_completion_equivalent(phase: FeaturePhase) -> bool:
    if phase.status in _TERMINAL_STATUSES:
        return True
    total = max(int(phase.totalTasks or 0), 0)
    completed = max(int(phase.completedTasks or 0), 0)
    return total > 0 and completed >= total


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


def scan_features(docs_dir: Path, progress_dir: Path) -> list[Feature]:
    """
    Discover features by cross-referencing impl plans, PRDs, and progress dirs.

    Priority: impl plans seed features, enriched with PRD + progress data.
    """
    project_root = infer_project_root(docs_dir, progress_dir)
    impl_plans = _scan_impl_plans(docs_dir, project_root)
    prds = _scan_prds(docs_dir, project_root)
    progress_data = _scan_progress_dirs(progress_dir, project_root)
    auxiliary_docs = _scan_auxiliary_docs(docs_dir, progress_dir, project_root)

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
            ))
            existing_paths.add(file_path)

    # Step 5: Link related features (same base slug, different versions)
    feature_list = list(features.values())
    base_groups: dict[str, list[str]] = {}
    for feat in feature_list:
        base = _base_slug(feat.id)
        base_groups.setdefault(base, []).append(feat.id)

    for group in base_groups.values():
        if len(group) > 1:
            for feat_id in group:
                features[feat_id].relatedFeatures = [
                    fid for fid in group if fid != feat_id
                ]

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
