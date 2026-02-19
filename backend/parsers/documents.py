"""Parse markdown documentation files into typed PlanDocument models."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.models import (
    PlanDocument,
    DocumentFrontmatter,
    DocumentMetadata,
    DocumentTaskCounts,
)
from backend.document_linking import (
    alias_tokens_from_path,
    canonical_project_path,
    canonical_slug,
    classify_doc_category,
    classify_doc_subtype,
    classify_doc_type,
    detect_root_kind,
    extract_frontmatter_references,
    feature_slug_from_path,
    is_feature_like_token,
    make_document_id,
)

_DONE_STATUSES = {"done", "completed", "complete"}
_IN_PROGRESS_STATUSES = {"in-progress", "in_progress", "active", "working"}
_BLOCKED_STATUSES = {"blocked", "waiting", "stalled"}

_NORMALIZED_STATUS = {
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "active": "in_progress",
    "in-progress": "in_progress",
    "in_progress": "in_progress",
    "review": "in_progress",
    "draft": "pending",
    "planning": "pending",
    "pending": "pending",
    "backlog": "pending",
    "blocked": "blocked",
    "archived": "archived",
}


def _extract_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text, False
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    body = match.group(2)
    return fm, body, True


def _to_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    items.append(text)
            elif isinstance(entry, dict):
                for key in ("id", "path", "value", "url", "hash", "commit"):
                    raw = entry.get(key)
                    if isinstance(raw, str) and raw.strip():
                        items.append(raw.strip())
                        break
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for nested in value.values():
            items.extend(_to_string_list(nested))
        return items
    return []


def _first_string(value: Any) -> str:
    values = _to_string_list(value)
    return values[0] if values else ""


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        token = value.strip().replace("%", "")
        if not token:
            return 0
        try:
            return int(float(token))
        except Exception:
            return 0
    return 0


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        token = value.strip().replace("%", "")
        if not token:
            return None
        try:
            return float(token)
        except Exception:
            return None
    return None


def _normalize_status(status: str) -> str:
    token = (status or "").strip().lower()
    if not token:
        return "pending"
    return _NORMALIZED_STATUS.get(token, token.replace("-", "_"))


def _normalize_task_counts(fm: dict[str, Any]) -> DocumentTaskCounts:
    total = _to_int(fm.get("total_tasks"))
    completed = _to_int(fm.get("completed_tasks"))
    in_progress = _to_int(fm.get("in_progress_tasks"))
    blocked = _to_int(fm.get("blocked_tasks"))

    tasks_raw = fm.get("tasks")
    if isinstance(tasks_raw, list) and tasks_raw:
        total = max(total, len(tasks_raw))
        derived_completed = 0
        derived_in_progress = 0
        derived_blocked = 0
        for task in tasks_raw:
            if not isinstance(task, dict):
                continue
            status_token = str(task.get("status") or "").strip().lower()
            if status_token in _DONE_STATUSES:
                derived_completed += 1
            elif status_token in _IN_PROGRESS_STATUSES:
                derived_in_progress += 1
            elif status_token in _BLOCKED_STATUSES:
                derived_blocked += 1
        if completed == 0:
            completed = derived_completed
        if in_progress == 0:
            in_progress = derived_in_progress
        if blocked == 0:
            blocked = derived_blocked

    if total > 0 and completed > total:
        completed = total

    return DocumentTaskCounts(
        total=max(0, total),
        completed=max(0, completed),
        inProgress=max(0, in_progress),
        blocked=max(0, blocked),
    )


def _parse_phase_metadata(path: Path, fm: dict[str, Any]) -> tuple[str, int | None]:
    phase_token = str(
        fm.get("phase")
        or fm.get("phase_id")
        or fm.get("phase_token")
        or ""
    ).strip()
    if not phase_token:
        stem = path.stem.lower()
        match = re.match(r"^phase[-_ ]?(\d+)", stem)
        if match:
            phase_token = match.group(1)

    phase_number: int | None = None
    if phase_token.isdigit():
        phase_number = int(phase_token)
    return phase_token, phase_number


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def parse_document_file(
    path: Path,
    base_dir: Path,
    project_root: Path | None = None,
) -> PlanDocument | None:
    """Parse a single markdown file into a PlanDocument."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    fm, body, had_frontmatter = _extract_frontmatter(text)
    refs = extract_frontmatter_references(fm)

    if project_root:
        canonical_path = canonical_project_path(path, project_root)
    else:
        try:
            canonical_path = str(path.relative_to(base_dir)).replace("\\", "/")
        except Exception:
            canonical_path = str(path).replace("\\", "/")

    doc_id = make_document_id(canonical_path)
    title = str(fm.get("title") or path.stem.replace("-", " ").replace("_", " ").title())
    status = str(fm.get("status") or "active")
    status_normalized = _normalize_status(status)
    tags = [str(v) for v in _to_string_list(fm.get("tags"))]

    created = fm.get("created", "")
    updated = fm.get("updated", created)
    last_modified = str(updated) if updated else ""
    audience = fm.get("audience", [])
    if isinstance(audience, list) and audience:
        author = str(audience[0])
    else:
        author = str(fm.get("author", ""))

    path_refs = [str(v) for v in refs.get("pathRefs", []) if isinstance(v, str)]
    slug_refs = [str(v) for v in refs.get("slugRefs", []) if isinstance(v, str)]
    related_refs = [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)]
    linked_feature_refs = [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)]
    linked_session_refs = [str(v) for v in refs.get("sessionRefs", []) if isinstance(v, str)]
    prd_refs = [str(v) for v in refs.get("prdRefs", []) if isinstance(v, str)]
    prd_primary = str(refs.get("prd") or "")
    request_refs = [str(v) for v in refs.get("requestRefs", []) if isinstance(v, str)]
    commit_refs = [str(v) for v in refs.get("commitRefs", []) if isinstance(v, str)]
    owner_refs = [str(v) for v in refs.get("ownerRefs", []) if isinstance(v, str)]

    direct_commit_refs = _to_string_list(
        fm.get("commits")
        or fm.get("commit")
        or fm.get("git_commit")
        or fm.get("git_commits")
        or fm.get("git_commit_hashes")
    )
    all_commit_refs = sorted({*commit_refs, *direct_commit_refs})
    prs = _to_string_list(
        fm.get("prs")
        or fm.get("pr")
        or fm.get("pull_requests")
        or fm.get("pullRequests")
    )
    version = _first_string(fm.get("version"))

    doc_type = classify_doc_type(canonical_path, fm)
    doc_subtype = classify_doc_subtype(canonical_path, fm)
    root_kind = detect_root_kind(canonical_path)
    category = classify_doc_category(canonical_path, fm)
    path_segments = list(Path(canonical_path).parts)
    phase_token, phase_number = _parse_phase_metadata(Path(canonical_path), fm)
    task_counts = _normalize_task_counts(fm)

    overall_progress = _to_optional_float(
        fm.get("overall_progress")
        if fm.get("overall_progress") is not None
        else fm.get("progress")
    )

    frontmatter_type = str(fm.get("type") or fm.get("doc_type") or fm.get("doctype") or "").strip()

    feature_slug_hint = str(fm.get("feature_slug") or fm.get("feature_slug_hint") or "").strip().lower()
    if not feature_slug_hint:
        for candidate in linked_feature_refs:
            token = str(candidate or "").strip().lower()
            if is_feature_like_token(token):
                feature_slug_hint = token
                break
    if not feature_slug_hint:
        feature_slug_hint = feature_slug_from_path(canonical_path)
    feature_slug_canonical = canonical_slug(feature_slug_hint) if feature_slug_hint else ""

    feature_candidates = sorted(
        {
            *linked_feature_refs,
            *alias_tokens_from_path(canonical_path),
            *( [feature_slug_hint] if feature_slug_hint else [] ),
            *( [feature_slug_canonical] if feature_slug_canonical else [] ),
        }
    )

    contributors = [str(v) for v in _to_string_list(fm.get("contributors"))]
    owners = sorted({*owner_refs, *[str(v) for v in _to_string_list(fm.get("owner") or fm.get("owners"))]})
    contributors = sorted({*contributors, *owner_refs})

    metadata = DocumentMetadata(
        phase=phase_token,
        phaseNumber=phase_number,
        overallProgress=overall_progress,
        taskCounts=task_counts,
        owners=owners,
        contributors=contributors,
        requestLogIds=request_refs,
        commitRefs=all_commit_refs,
        featureSlugHint=feature_slug_hint,
        canonicalPath=canonical_path,
    )

    return PlanDocument(
        id=doc_id,
        title=title,
        filePath=canonical_path,
        status=status,
        lastModified=last_modified,
        author=author,
        docType=doc_type,
        category=str(category),
        docSubtype=doc_subtype,
        rootKind=root_kind,  # type: ignore[arg-type]
        canonicalPath=canonical_path,
        hasFrontmatter=had_frontmatter,
        frontmatterType=frontmatter_type,
        statusNormalized=status_normalized,
        featureSlugHint=feature_slug_hint,
        featureSlugCanonical=feature_slug_canonical,
        prdRef=prd_primary,
        phaseToken=phase_token,
        phaseNumber=phase_number,
        overallProgress=overall_progress,
        totalTasks=task_counts.total,
        completedTasks=task_counts.completed,
        inProgressTasks=task_counts.inProgress,
        blockedTasks=task_counts.blocked,
        pathSegments=path_segments,
        featureCandidates=feature_candidates,
        frontmatter=DocumentFrontmatter(
            tags=tags,
            linkedFeatures=linked_feature_refs,
            linkedSessions=linked_session_refs,
            version=version or None,
            commits=all_commit_refs,
            prs=prs,
            relatedRefs=related_refs,
            pathRefs=path_refs,
            slugRefs=slug_refs,
            prd=prd_primary,
            prdRefs=prd_refs,
            fieldKeys=sorted(str(key) for key in fm.keys()),
            raw=_json_safe({str(k): v for k, v in fm.items()}),
        ),
        metadata=metadata,
        content=body[:5000] if body else None,
    )


def scan_documents(documents_dir: Path, project_root: Path | None = None) -> list[PlanDocument]:
    """Scan a directory recursively for .md files and parse them."""
    docs: list[PlanDocument] = []
    if not documents_dir.exists():
        return docs

    for path in sorted(documents_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        doc = parse_document_file(path, documents_dir, project_root=project_root)
        if doc:
            docs.append(doc)

    return docs
