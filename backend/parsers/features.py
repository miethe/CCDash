"""Document-first feature discovery.

Scan Implementation Plans → PRDs → Progress dirs and merge into Feature objects.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from backend.models import (
    Feature,
    FeaturePhase,
    LinkedDocument,
    ProjectTask,
)

logger = logging.getLogger("ccdash")

# ── Status helpers ──────────────────────────────────────────────────

# Ordering for "furthest progression" inference
_STATUS_ORDER = {"backlog": 0, "in-progress": 1, "review": 2, "done": 3}


_STATUS_MAP = {
    "completed": "done",
    "complete": "done",
    "done": "done",
    "in-progress": "in-progress",
    "in_progress": "in-progress",
    "active": "in-progress",
    "review": "review",
    "ready": "backlog",
    "draft": "backlog",
    "blocked": "backlog",
    "planning": "backlog",
    "pending": "backlog",
    "not-started": "backlog",
    "not_started": "backlog",
    "reference": "done",
}

_TASK_STATUS_MAP = {
    "completed": "done",
    "complete": "done",
    "in-progress": "in-progress",
    "in_progress": "in-progress",
    "review": "review",
    "blocked": "backlog",
    "pending": "backlog",
    "not-started": "backlog",
    "not_started": "backlog",
}


def _map_status(raw: str) -> str:
    return _STATUS_MAP.get(raw.lower().strip(), "backlog")


def _map_task_status(raw: str) -> str:
    return _TASK_STATUS_MAP.get(raw.lower().strip(), "backlog")


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
    return re.sub(r"-v\d+(\.\d+)?$", "", slug)


# ── Phase 1: Scan Implementation Plans ──────────────────────────────

def _scan_impl_plans(docs_dir: Path) -> dict[str, dict]:
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
        rel_path = str(path.relative_to(docs_dir))

        # Determine if this is a phase sub-plan (inside a sub-dir of an impl plan)
        # Phase sub-plans are files like impl_plans/harden-polish/discovery-import-fixes-v1/phase-1-bug-fixes.md
        parent_dir_name = path.parent.name
        grandparent = path.parent.parent.name if path.parent.parent != impl_dir else ""

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
                })
            continue

        plans[slug] = {
            "title": title,
            "status": status,
            "category": category,
            "prd_ref": prd_ref,
            "tags": tags if isinstance(tags, list) else [],
            "updated": updated,
            "rel_path": rel_path,
            "phase_docs": [],
        }

    return plans


# ── Phase 2: Scan PRDs ──────────────────────────────────────────────

def _scan_prds(docs_dir: Path) -> dict[str, dict]:
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
        related = fm.get("related", [])
        if isinstance(related, str):
            related = [related]
        if not isinstance(related, list):
            related = []
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        updated = str(fm.get("updated", fm.get("created", "")))
        rel_path = str(path.relative_to(docs_dir))

        prds[slug] = {
            "title": title,
            "status": status,
            "related": [str(r) for r in related],
            "tags": tags if isinstance(tags, list) else [],
            "updated": updated,
            "rel_path": rel_path,
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


def _scan_progress_dirs(progress_dir: Path) -> dict[str, dict]:
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
            phase_progress = fm.get("progress", 0)
            if not isinstance(phase_progress, (int, float)):
                phase_progress = 0

            total = fm.get("total_tasks", 0)
            completed = fm.get("completed_tasks", 0)
            if not isinstance(total, int):
                total = 0
            if not isinstance(completed, int):
                completed = 0

            updated = str(fm.get("updated", fm.get("completed_at", "")))
            if updated and updated > latest_updated:
                latest_updated = updated

            # Parse tasks
            tasks_raw = fm.get("tasks", [])
            if not isinstance(tasks_raw, list):
                tasks_raw = []
            # Pass relative path so tasks know their source file
            try:
                source_rel = str(md_file.relative_to(progress_dir.parent))
            except ValueError:
                source_rel = str(md_file)
            tasks = _parse_progress_tasks(tasks_raw, source_file=source_rel)

            # If total/completed not provided, derive from tasks
            if total == 0 and tasks:
                total = len(tasks)
                completed = sum(1 for t in tasks if t.status == "done")

            phases.append(FeaturePhase(
                phase=phase_num,
                title=str(phase_title),
                status=_map_status(phase_status_raw),
                progress=int(phase_progress),
                totalTasks=total,
                completedTasks=completed,
                tasks=tasks,
            ))

        if not phases:
            continue

        # Derive overall status from phases
        all_done = all(p.status == "done" for p in phases)
        any_in_progress = any(p.status == "in-progress" for p in phases)
        any_review = any(p.status == "review" for p in phases)

        if all_done:
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
    for s in statuses:
        if _STATUS_ORDER.get(s, 0) > _STATUS_ORDER.get(best, 0):
            best = s
    return best


# ── Merge into Features ─────────────────────────────────────────────

def scan_features(docs_dir: Path, progress_dir: Path) -> list[Feature]:
    """
    Discover features by cross-referencing impl plans, PRDs, and progress dirs.

    Priority: impl plans seed features, enriched with PRD + progress data.
    """
    impl_plans = _scan_impl_plans(docs_dir)
    prds = _scan_prds(docs_dir)
    progress_data = _scan_progress_dirs(progress_dir)

    features: dict[str, Feature] = {}

    # Step 1: Seed features from implementation plans
    for slug, plan in impl_plans.items():
        linked_docs = [
            LinkedDocument(
                id=f"PLAN-{slug}",
                title=plan["title"],
                filePath=plan["rel_path"],
                docType="implementation_plan",
            )
        ]

        # Add phase sub-plan docs
        for pd in plan.get("phase_docs", []):
            linked_docs.append(LinkedDocument(
                id=f"PHASE-{pd['slug']}",
                title=pd["title"],
                filePath=pd["path"],
                docType="phase_plan",
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
            if prd_sl in features:
                matched_feature_id = prd_sl

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

            # Update timestamp if progress has a newer one
            if prog["updated"] and prog["updated"] > feat.updatedAt:
                feat.updatedAt = prog["updated"]
        else:
            # Progress dir with no matching plan or PRD → create feature
            # Use slug as name, cleaned up
            name = prog_slug.replace("-", " ").replace("_", " ").title()
            phases = prog["phases"]
            features[prog_slug] = Feature(
                id=prog_slug,
                name=name,
                status=prog["status"],
                totalTasks=sum(p.totalTasks for p in phases),
                completedTasks=sum(p.completedTasks for p in phases),
                phases=phases,
                updatedAt=prog.get("updated", ""),
            )

    # Step 4: Link related features (same base slug, different versions)
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

    result = sorted(feature_list, key=lambda f: f.updatedAt or "", reverse=True)
    logger.info(f"Discovered {len(result)} features ({sum(1 for f in result if f.status == 'done')} done)")
    return result
