"""Deterministic scope-drift derivation from linked docs and file activity."""
from __future__ import annotations

import json
from typing import Any


_HEURISTIC_VERSION = "scope_drift_v1"
_REPO_ANCHORS = (
    ".claude/",
    "backend/",
    "components/",
    "services/",
    "docs/",
    "tests/",
)


def _safe_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_string_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, tuple):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, set):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _trim_repo_anchor(path: str) -> str:
    lowered = path.lower()
    # Only trim by embedded anchors for absolute paths; relative paths like
    # "backend/services/..." should preserve their full prefix.
    if path.startswith("/"):
        for anchor in _REPO_ANCHORS:
            idx = lowered.find("/" + anchor)
            if idx >= 0:
                return path[idx + 1 :]
    for anchor in _REPO_ANCHORS:
        if lowered.startswith(anchor):
            return path
    return path


def _normalize_path(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    text = text.split("#", 1)[0].split("?", 1)[0].strip()
    while "//" in text:
        text = text.replace("//", "/")
    if text.startswith("./"):
        text = text[2:]
    text = _trim_repo_anchor(text)
    if text.startswith("/"):
        text = text[1:]
    return text.strip()


def _looks_like_path(value: str) -> bool:
    if not value:
        return False
    if "/" in value:
        return True
    stem = value.rsplit("/", 1)[-1]
    if "." not in stem:
        return False
    suffix = stem.rsplit(".", 1)[-1]
    return suffix.isalnum()


def _is_file_like(path: str) -> bool:
    leaf = path.rsplit("/", 1)[-1]
    if "." not in leaf:
        return False
    suffix = leaf.rsplit(".", 1)[-1]
    return suffix.isalnum()


def _path_matches_scope(actual: str, planned: str) -> bool:
    actual_cmp = actual.lower().strip("/")
    planned_cmp = planned.lower().strip("/")
    if not actual_cmp or not planned_cmp:
        return False
    if actual_cmp == planned_cmp:
        return True
    if _is_file_like(planned_cmp):
        return actual_cmp.endswith("/" + planned_cmp)

    # Directory-like path uses prefix matching plus suffix-aware absolute-path matching.
    if actual_cmp.startswith(planned_cmp + "/"):
        return True
    if f"/{planned_cmp}/" in actual_cmp:
        return True
    return actual_cmp.endswith("/" + planned_cmp)


def _extract_planned_scope(
    linked_document_rows: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[str]]]:
    sources_by_path: dict[str, set[str]] = {}

    def add(path_value: Any, source: str) -> None:
        normalized = _normalize_path(path_value)
        if not normalized or not _looks_like_path(normalized):
            return
        sources_by_path.setdefault(normalized, set()).add(source)

    for row in linked_document_rows:
        row_dict = row if isinstance(row, dict) else {}
        frontmatter = row_dict.get("frontmatter")
        if not isinstance(frontmatter, dict):
            frontmatter = _safe_json_dict(row_dict.get("frontmatter_json"))

        row_id = str(row_dict.get("id") or row_dict.get("file_path") or "document")

        for value in _as_string_list(frontmatter.get("context_files") or frontmatter.get("contextFiles")):
            add(value, f"{row_id}:context_files")
        for value in _as_string_list(frontmatter.get("pathRefs")):
            add(value, f"{row_id}:pathRefs")
        for value in _as_string_list(frontmatter.get("relatedRefs")):
            add(value, f"{row_id}:relatedRefs")
        for value in _as_string_list(frontmatter.get("plan_ref") or frontmatter.get("planRef")):
            add(value, f"{row_id}:plan_ref")
        for value in _as_string_list(
            frontmatter.get("implementation_plan_ref") or frontmatter.get("implementationPlanRef")
        ):
            add(value, f"{row_id}:implementation_plan_ref")
        for value in _as_string_list(frontmatter.get("prd")):
            add(value, f"{row_id}:prd")
        for value in _as_string_list(frontmatter.get("prd_ref") or frontmatter.get("prdRef")):
            add(value, f"{row_id}:prd_ref")

        add(row_dict.get("plan_ref"), f"{row_id}:row.plan_ref")
        add(row_dict.get("prd_ref"), f"{row_id}:row.prd_ref")

    planned_paths = sorted(sources_by_path.keys())
    planned_sources = {path: sorted(values) for path, values in sources_by_path.items()}
    return planned_paths, planned_sources


def _extract_actual_scope(file_update_rows: list[dict[str, Any]]) -> list[str]:
    resolved: set[str] = set()
    for row in file_update_rows:
        if not isinstance(row, dict):
            continue
        for key in ("file_path", "filePath", "path"):
            normalized = _normalize_path(row.get(key))
            if normalized and _looks_like_path(normalized):
                resolved.add(normalized)
                break
    return sorted(resolved)


def _resolve_feature_id(session_payload: dict[str, Any]) -> str:
    for key in ("feature_id", "featureId", "task_id", "taskId"):
        value = str(session_payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _compute_confidence(planned_count: int, actual_count: int) -> float:
    if planned_count <= 0 and actual_count <= 0:
        return 0.35
    if planned_count <= 0:
        return 0.45
    if actual_count <= 0:
        return 0.7
    return 0.85


def build_session_scope_drift_facts(
    session_payload: dict[str, Any],
    linked_document_rows: list[dict[str, Any]],
    session_file_update_rows: list[dict[str, Any]],
    *,
    heuristic_version: str = _HEURISTIC_VERSION,
) -> list[dict[str, Any]]:
    """Build deterministic scope-drift fact rows for a session."""
    session_id = str(session_payload.get("id") or "").strip()
    if not session_id:
        return []

    root_session_id = str(
        session_payload.get("rootSessionId")
        or session_payload.get("root_session_id")
        or session_id
    ).strip()
    thread_session_id = str(
        session_payload.get("threadSessionId")
        or session_payload.get("thread_session_id")
        or session_id
    ).strip()
    feature_id = _resolve_feature_id(session_payload)

    planned_paths, planned_sources = _extract_planned_scope(linked_document_rows)
    actual_paths = _extract_actual_scope(session_file_update_rows)

    matched_paths: list[str] = []
    out_of_scope_paths: list[str] = []
    for actual in actual_paths:
        if any(_path_matches_scope(actual, planned) for planned in planned_paths):
            matched_paths.append(actual)
        else:
            out_of_scope_paths.append(actual)

    planned_count = len(planned_paths)
    actual_count = len(actual_paths)
    matched_count = len(matched_paths)
    out_of_scope_count = len(out_of_scope_paths)

    drift_ratio = round(out_of_scope_count / actual_count, 4) if actual_count else 0.0
    adherence_score = round(matched_count / actual_count, 4) if actual_count else 1.0
    confidence = _compute_confidence(planned_count, actual_count)

    evidence_json = {
        "matchingMode": "prefix-aware",
        "plannedPaths": planned_paths,
        "actualPaths": actual_paths,
        "matchedPaths": matched_paths,
        "outOfScopePaths": out_of_scope_paths,
        "plannedPathSources": [
            {"path": path, "sources": planned_sources.get(path, [])}
            for path in planned_paths
        ],
    }

    return [
        {
            "session_id": session_id,
            "feature_id": feature_id,
            "root_session_id": root_session_id,
            "thread_session_id": thread_session_id,
            "planned_path_count": planned_count,
            "actual_path_count": actual_count,
            "matched_path_count": matched_count,
            "out_of_scope_path_count": out_of_scope_count,
            "drift_ratio": drift_ratio,
            "adherence_score": adherence_score,
            "confidence": confidence,
            "heuristic_version": str(heuristic_version or _HEURISTIC_VERSION),
            "evidence_json": evidence_json,
        }
    ]
