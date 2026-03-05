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
    normalize_doc_status,
    normalize_ref_path,
)
from backend.date_utils import (
    choose_first,
    choose_latest,
    file_metadata_dates,
    make_date_value,
    normalize_iso_date,
)

_DONE_STATUSES = {"done", "completed", "complete"}
_IN_PROGRESS_STATUSES = {"in-progress", "in_progress", "active", "working"}
_BLOCKED_STATUSES = {"blocked", "waiting", "stalled"}

_NORMALIZED_STATUS = {
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "inferred_complete": "inferred_complete",
    "inferred-complete": "inferred_complete",
    "inferred complete": "inferred_complete",
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
_COMPLETION_EQUIVALENT_STATUSES = {"completed", "inferred_complete", "deferred"}
_PRIORITY_LEVELS = {"low", "medium", "high", "critical"}
_RISK_LEVELS = {"low", "medium", "high", "critical"}
_TEST_IMPACT_LEVELS = {"none", "low", "medium", "high", "critical"}
_DECISION_STATUSES = {"proposed", "approved", "accepted", "superseded", "rejected", "draft"}
_EXECUTION_READINESS_STATES = {"unknown", "not_ready", "needs_inputs", "ready", "in_progress", "complete"}
_DOC_TYPE_FIELD_KEYS: dict[str, set[str]] = {
    "prd": {
        "problem_statement",
        "context",
        "goals",
        "non_goals",
        "users",
        "jobs_to_be_done",
        "success_metrics",
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
        "assumptions",
        "dependencies",
        "risks",
        "decisions",
    },
    "implementation_plan": {
        "objective",
        "scope",
        "architecture_summary",
        "rollout_strategy",
        "rollback_strategy",
        "observability_plan",
        "testing_strategy",
        "security_considerations",
        "data_considerations",
        "phases",
        "dependencies",
        "risks",
        "execution_entrypoints",
    },
    "phase_plan": {
        "phase_title",
        "phase_goal",
        "depends_on_phases",
        "entry_criteria",
        "exit_criteria",
        "tasks",
        "parallelization",
        "blockers",
        "success_criteria",
        "files_modified",
    },
    "progress": {
        "completion_estimate",
        "deferred_tasks",
        "at_risk_tasks",
        "blockers",
        "success_criteria",
        "next_steps",
        "files_modified",
        "tasks",
        "parallelization",
    },
    "report": {
        "report_kind",
        "scope",
        "evidence",
        "findings",
        "recommendations",
        "impacted_features",
    },
    "design_doc": {
        "surfaces",
        "user_flows",
        "ux_goals",
        "components",
        "accessibility_notes",
        "motion_notes",
        "asset_refs",
    },
    "spec": {
        "spec_kind",
        "interfaces",
        "entities",
        "data_contracts",
        "validation_rules",
        "migration_notes",
        "open_questions",
    },
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


def _first_non_empty(*values: Any) -> str:
    for value in values:
        token = _first_string(value)
        if token:
            return token
    return ""


def _normalize_choice(value: Any, allowed: set[str]) -> str:
    token = _first_string(value).strip().lower().replace("-", "_").replace(" ", "_")
    return token if token in allowed else ""


def _normalize_feature_identity(value: Any, *, canonicalize: bool = False) -> str:
    token = _normalize_feature_ref(_first_string(value))
    if not token:
        return ""
    return canonical_slug(token) if canonicalize else token


def _normalize_linked_feature_refs(raw_refs: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_refs, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_refs:
        if not isinstance(raw, dict):
            continue
        feature = str(raw.get("feature") or "").strip().lower()
        if not feature:
            continue
        relation_type = str(raw.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_")
        source = str(raw.get("source") or "").strip().lower().replace("-", "_").replace(" ", "_")
        key = (feature, relation_type, source)
        if key in seen:
            continue
        seen.add(key)
        confidence_value: float | None = None
        confidence_raw = raw.get("confidence")
        if confidence_raw is not None:
            try:
                confidence_value = max(0.0, min(1.0, float(confidence_raw)))
            except Exception:
                confidence_value = None
        normalized.append(
            {
                "feature": feature,
                "type": relation_type,
                "source": source,
                "confidence": confidence_value,
                "notes": str(raw.get("notes") or ""),
                "evidence": [
                    str(v)
                    for v in _to_string_list(raw.get("evidence"))
                    if isinstance(v, str) and str(v).strip()
                ],
            }
        )
    return normalized


def _extract_doc_type_fields(doc_type: str, fm: dict[str, Any]) -> dict[str, Any]:
    keys = _DOC_TYPE_FIELD_KEYS.get(doc_type, set())
    if not keys:
        return {}
    fields: dict[str, Any] = {}
    for key in keys:
        if key not in fm:
            continue
        fields[key] = _json_safe(fm.get(key))
    return fields


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


def _normalize_feature_ref_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_feature_ref(value)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


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
    mapped = _NORMALIZED_STATUS.get(token, token.replace("-", "_"))
    return normalize_doc_status(mapped, default="pending")


def _frontmatter_date(fm: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = normalize_iso_date(fm.get(key))
        if value:
            return value
    return ""


def _build_document_date_fields(path: Path, fm: dict[str, Any], status_normalized: str) -> tuple[str, str, str, dict[str, Any], list[dict[str, Any]]]:
    return _build_document_date_fields_with_git(path, fm, status_normalized)


def _build_document_date_fields_with_git(
    path: Path,
    fm: dict[str, Any],
    status_normalized: str,
    canonical_path: str = "",
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
) -> tuple[str, str, str, dict[str, Any], list[dict[str, Any]]]:
    fs_dates = file_metadata_dates(path)
    git_dates = (git_date_index or {}).get(canonical_path, {})
    dirty = canonical_path in (dirty_paths or set())

    fm_created = _frontmatter_date(fm, "created", "created_at", "date_created")
    fm_updated = _frontmatter_date(fm, "updated", "updated_at", "last_updated", "modified", "modified_at")
    fm_completed = _frontmatter_date(fm, "completed", "completed_at", "completion_date", "done_at")
    git_created = normalize_iso_date(git_dates.get("createdAt"))
    git_updated = normalize_iso_date(git_dates.get("updatedAt"))

    created = choose_first([
        make_date_value(fm_created, "high", "frontmatter", "created"),
        make_date_value(git_created, "high", "git", "first_commit"),
        make_date_value(fs_dates.get("createdAt", ""), "medium", "filesystem", "file_birthtime"),
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_fallback")
        if not git_created else {},
    ])
    updated_candidates = [
        make_date_value(git_updated, "high", "git", "latest_commit"),
        make_date_value(fm_updated, "medium", "frontmatter", "updated"),
        make_date_value(fs_dates.get("updatedAt", ""), "high", "filesystem", "dirty_worktree")
        if dirty else {},
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_fallback")
        if not git_updated and not fm_updated else {},
        make_date_value(fm_created, "low", "frontmatter", "created_fallback"),
    ]
    updated = choose_latest([
        candidate for candidate in updated_candidates if candidate
    ])
    completed = choose_first([
        make_date_value(fm_completed, "high", "frontmatter", "completed"),
        make_date_value(fm_updated, "medium", "frontmatter", "updated_completion_fallback")
        if status_normalized in _COMPLETION_EQUIVALENT_STATUSES else {},
        make_date_value(fs_dates.get("updatedAt", ""), "low", "filesystem", "mtime_completion_fallback")
        if status_normalized in _COMPLETION_EQUIVALENT_STATUSES else {},
    ])
    last_activity = choose_latest([updated, completed])

    dates: dict[str, Any] = {}
    if created:
        dates["createdAt"] = created
    if updated:
        dates["updatedAt"] = updated
    if completed:
        dates["completedAt"] = completed
    if last_activity:
        dates["lastActivityAt"] = last_activity

    timeline: list[dict[str, Any]] = []
    if created:
        timeline.append({
            "id": "doc-created",
            "timestamp": created["value"],
            "label": "Document Created",
            "kind": "created",
            "confidence": created["confidence"],
            "source": created["source"],
            "description": created.get("reason", ""),
        })
    if updated:
        timeline.append({
            "id": "doc-updated",
            "timestamp": updated["value"],
            "label": "Last Updated",
            "kind": "updated",
            "confidence": updated["confidence"],
            "source": updated["source"],
            "description": updated.get("reason", ""),
        })
    if completed:
        timeline.append({
            "id": "doc-completed",
            "timestamp": completed["value"],
            "label": "Marked Complete",
            "kind": "completed",
            "confidence": completed["confidence"],
            "source": completed["source"],
            "description": completed.get("reason", ""),
        })

    created_at = created.get("value", "")
    updated_at = updated.get("value", "")
    completed_at = completed.get("value", "")
    return created_at, updated_at, completed_at, dates, timeline


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
    git_date_index: dict[str, dict[str, str]] | None = None,
    dirty_paths: set[str] | None = None,
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

    created_at, updated_at, completed_at, dates, timeline = _build_document_date_fields_with_git(
        path,
        fm,
        status_normalized,
        canonical_path=canonical_path,
        git_date_index=git_date_index,
        dirty_paths=dirty_paths,
    )
    last_modified = updated_at or created_at
    audience = fm.get("audience", [])
    if isinstance(audience, list) and audience:
        author = str(audience[0])
    else:
        author = str(fm.get("author", ""))

    path_refs = [str(v) for v in refs.get("pathRefs", []) if isinstance(v, str)]
    slug_refs = [str(v) for v in refs.get("slugRefs", []) if isinstance(v, str)]
    related_refs = [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)]
    linked_feature_refs = [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)]
    typed_linked_feature_refs = _normalize_linked_feature_refs(refs.get("typedFeatureRefs"))
    linked_session_refs = [str(v) for v in refs.get("sessionRefs", []) if isinstance(v, str)]
    linked_task_refs = [str(v) for v in refs.get("taskRefs", []) if isinstance(v, str)]
    prd_refs = [str(v) for v in refs.get("prdRefs", []) if isinstance(v, str)]
    prd_primary = str(refs.get("prd") or "")
    request_refs = [str(v) for v in refs.get("requestRefs", []) if isinstance(v, str)]
    commit_refs = [str(v) for v in refs.get("commitRefs", []) if isinstance(v, str)]
    pr_refs = [str(v) for v in refs.get("prRefs", []) if isinstance(v, str)]
    source_document_refs = [str(v) for v in refs.get("sourceDocumentRefs", []) if isinstance(v, str)]
    integrity_signal_refs = [str(v) for v in refs.get("integritySignalRefs", []) if isinstance(v, str)]
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
    all_pr_refs = sorted({*pr_refs, *prs})
    version = _first_string(fm.get("version"))

    doc_type = classify_doc_type(canonical_path, fm)
    doc_subtype = classify_doc_subtype(canonical_path, fm)
    root_kind = detect_root_kind(canonical_path)
    category = classify_doc_category(canonical_path, fm)
    path_segments = list(Path(canonical_path).parts)
    phase_token, phase_number = _parse_phase_metadata(Path(canonical_path), fm)
    task_counts = _normalize_task_counts(fm)
    doc_type_fields = _extract_doc_type_fields(doc_type, fm)

    overall_progress = _to_optional_float(
        fm.get("overall_progress")
        if fm.get("overall_progress") is not None
        else fm.get("progress")
    )
    completion_estimate = _first_non_empty(
        fm.get("completion_estimate"),
        fm.get("eta"),
        fm.get("target_date"),
    )

    description = _first_non_empty(fm.get("description"), fm.get("objective"))
    summary = _first_non_empty(fm.get("summary"))
    priority = _normalize_choice(fm.get("priority"), _PRIORITY_LEVELS)
    risk_level = _normalize_choice(fm.get("risk_level"), _RISK_LEVELS)
    complexity = _first_non_empty(fm.get("complexity"))
    track = _first_non_empty(fm.get("track"))
    timeline_estimate = _first_non_empty(fm.get("timeline_estimate"), fm.get("timeline"), fm.get("estimate"))
    target_release = _first_non_empty(fm.get("target_release"), fm.get("release"))
    milestone = _first_non_empty(fm.get("milestone"))
    decision_status = _normalize_choice(fm.get("decision_status"), _DECISION_STATUSES)
    execution_readiness = _normalize_choice(fm.get("execution_readiness"), _EXECUTION_READINESS_STATES)
    test_impact = _normalize_choice(fm.get("test_impact"), _TEST_IMPACT_LEVELS)
    primary_doc_role = _first_non_empty(fm.get("primary_doc_role"))

    frontmatter_type = str(fm.get("type") or fm.get("doc_type") or fm.get("doctype") or "").strip()

    feature_slug = _normalize_feature_identity(
        fm.get("feature_slug")
        or fm.get("feature")
        or fm.get("feature_id")
        or fm.get("feature_slug_hint")
    )
    feature_family = _normalize_feature_identity(
        fm.get("feature_family") or fm.get("lineage_family"),
        canonicalize=True,
    )
    feature_version = _first_non_empty(fm.get("feature_version"), fm.get("version"))
    plan_ref = _first_non_empty(fm.get("plan_ref"))
    implementation_plan_ref = _first_non_empty(fm.get("implementation_plan_ref"))

    feature_slug_hint = feature_slug or str(fm.get("feature_slug_hint") or "").strip().lower()
    if not feature_slug_hint:
        feature_slug_hint = feature_slug_from_path(canonical_path)
    if not feature_slug_hint:
        for candidate in linked_feature_refs:
            token = str(candidate or "").strip().lower()
            if is_feature_like_token(token):
                feature_slug_hint = token
                break
    feature_slug_canonical = canonical_slug(feature_slug_hint) if feature_slug_hint else ""

    lineage_family_raw = _first_string(fm.get("lineage_family") or fm.get("feature_family"))
    lineage_parent_raw = _first_string(
        fm.get("lineage_parent")
        or fm.get("parent_feature")
        or fm.get("parent_feature_slug")
        or fm.get("extends_feature")
        or fm.get("derived_from")
        or fm.get("supersedes")
    )
    lineage_children_raw = _to_string_list(
        fm.get("lineage_children")
        or fm.get("child_features")
        or fm.get("superseded_by")
    )
    lineage_type = str(
        _first_string(
            fm.get("lineage_type")
            or fm.get("lineage_relationship")
            or fm.get("feature_lineage_type")
        )
    ).strip().lower().replace(" ", "_")
    lineage_parent = _normalize_feature_ref(lineage_parent_raw)
    lineage_children = _normalize_feature_ref_list(lineage_children_raw)
    normalized_lineage_family = _normalize_feature_ref(lineage_family_raw)
    lineage_family = canonical_slug(
        normalized_lineage_family or feature_family or feature_slug_hint or feature_slug_canonical
    )

    all_linked_feature_refs = sorted(
        {
            *linked_feature_refs,
            *[str(ref.get("feature") or "") for ref in typed_linked_feature_refs],
            *([lineage_parent] if lineage_parent else []),
            *lineage_children,
        }
    )
    if feature_slug:
        all_linked_feature_refs = sorted({*all_linked_feature_refs, feature_slug})

    feature_candidates = sorted(
        {
            *all_linked_feature_refs,
            *alias_tokens_from_path(canonical_path),
            *( [feature_slug_hint] if feature_slug_hint else [] ),
            *( [feature_slug_canonical] if feature_slug_canonical else [] ),
            *( [lineage_family] if lineage_family else [] ),
        }
    )

    contributors = [str(v) for v in _to_string_list(fm.get("contributors"))]
    reviewers = [str(v) for v in _to_string_list(fm.get("reviewers"))]
    approvers = [str(v) for v in _to_string_list(fm.get("approvers"))]
    audience_values = [str(v) for v in _to_string_list(fm.get("audience"))]
    labels = sorted({*tags, *[str(v) for v in _to_string_list(fm.get("labels"))]})
    files_affected = [str(v) for v in _to_string_list(fm.get("files_affected") or fm.get("filesAffected"))]
    files_modified = [str(v) for v in _to_string_list(fm.get("files_modified") or fm.get("filesModified"))]
    context_files = [str(v) for v in _to_string_list(fm.get("context_files") or fm.get("contextFiles"))]
    owners = sorted({*owner_refs, *[str(v) for v in _to_string_list(fm.get("owner") or fm.get("owners"))]})
    contributors = sorted({*contributors, *owner_refs})
    source_document_refs = sorted({*source_document_refs, *_to_string_list(fm.get("source_documents"))})
    integrity_signal_refs = sorted({*integrity_signal_refs, *_to_string_list(fm.get("integrity_signal_refs"))})
    execution_entrypoints_raw = fm.get("execution_entrypoints")
    execution_entrypoints = [
        _json_safe(entry)
        for entry in execution_entrypoints_raw
        if isinstance(entry, dict)
    ] if isinstance(execution_entrypoints_raw, list) else []

    metadata = DocumentMetadata(
        phase=phase_token,
        phaseNumber=phase_number,
        overallProgress=overall_progress,
        completionEstimate=completion_estimate,
        description=description,
        summary=summary,
        priority=priority,
        riskLevel=risk_level,
        complexity=complexity,
        track=track,
        timelineEstimate=timeline_estimate,
        targetRelease=target_release,
        milestone=milestone,
        decisionStatus=decision_status,
        executionReadiness=execution_readiness,
        testImpact=test_impact,
        primaryDocRole=primary_doc_role,
        featureSlug=feature_slug,
        featureFamily=feature_family,
        featureVersion=feature_version,
        planRef=plan_ref,
        implementationPlanRef=implementation_plan_ref,
        taskCounts=task_counts,
        owners=owners,
        contributors=contributors,
        reviewers=reviewers,
        approvers=approvers,
        audience=audience_values,
        labels=labels,
        linkedTasks=linked_task_refs,
        requestLogIds=request_refs,
        commitRefs=all_commit_refs,
        prRefs=all_pr_refs,
        sourceDocuments=source_document_refs,
        filesAffected=files_affected,
        filesModified=files_modified,
        contextFiles=context_files,
        integritySignalRefs=integrity_signal_refs,
        executionEntrypoints=execution_entrypoints,
        linkedFeatureRefs=typed_linked_feature_refs,
        docTypeFields=doc_type_fields,
        featureSlugHint=feature_slug_hint,
        canonicalPath=canonical_path,
    )

    return PlanDocument(
        id=doc_id,
        title=title,
        filePath=canonical_path,
        status=status,
        createdAt=created_at,
        updatedAt=updated_at,
        completedAt=completed_at,
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
        completionEstimate=completion_estimate,
        description=description,
        summary=summary,
        priority=priority,
        riskLevel=risk_level,
        complexity=complexity,
        track=track,
        timelineEstimate=timeline_estimate,
        targetRelease=target_release,
        milestone=milestone,
        decisionStatus=decision_status,
        executionReadiness=execution_readiness,
        testImpact=test_impact,
        primaryDocRole=primary_doc_role,
        featureSlug=feature_slug,
        featureFamily=feature_family,
        featureVersion=feature_version,
        planRef=plan_ref,
        implementationPlanRef=implementation_plan_ref,
        totalTasks=task_counts.total,
        completedTasks=task_counts.completed,
        inProgressTasks=task_counts.inProgress,
        blockedTasks=task_counts.blocked,
        pathSegments=path_segments,
        featureCandidates=feature_candidates,
        frontmatter=DocumentFrontmatter(
            tags=tags,
            linkedFeatures=all_linked_feature_refs,
            linkedFeatureRefs=typed_linked_feature_refs,
            linkedSessions=linked_session_refs,
            linkedTasks=linked_task_refs,
            lineageFamily=lineage_family,
            lineageParent=lineage_parent,
            lineageChildren=lineage_children,
            lineageType=lineage_type,
            version=version or None,
            commits=all_commit_refs,
            prs=prs,
            requestLogIds=request_refs,
            commitRefs=all_commit_refs,
            prRefs=all_pr_refs,
            relatedRefs=related_refs,
            pathRefs=path_refs,
            slugRefs=slug_refs,
            prd=prd_primary,
            prdRefs=prd_refs,
            sourceDocuments=source_document_refs,
            filesAffected=files_affected,
            filesModified=files_modified,
            contextFiles=context_files,
            integritySignalRefs=integrity_signal_refs,
            fieldKeys=sorted(str(key) for key in fm.keys()),
            raw=_json_safe({str(k): v for k, v in fm.items()}),
        ),
        metadata=metadata,
        dates=dates,
        timeline=timeline,
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
