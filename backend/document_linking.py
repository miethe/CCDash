"""Shared utilities for document/session/feature linking.

These helpers centralize path normalization, slug extraction, document
classification, and frontmatter reference parsing so parsers and linkers
use consistent matching semantics.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_VERSION_SUFFIX_PATTERN = re.compile(r"-v\d+(?:\.\d+)?$", re.IGNORECASE)
_NOISY_PATH_PATTERN = re.compile(r"(\*|\$\{[^}]+\}|<[^>]+>|\{[^{}]+\})")
_GENERIC_PHASE_PROGRESS_PATTERN = re.compile(r"^phase-[a-z0-9._&-]+-progress$", re.IGNORECASE)
_FEATURE_TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,}$", re.IGNORECASE)
_PATH_WITH_EXT_PATTERN = re.compile(r"^[A-Za-z0-9._~:/@+\-\\]+$")

_GENERIC_ALIAS_TOKENS = {
    "docs",
    "project_plans",
    "implementation_plans",
    "prds",
    "progress",
    "reports",
    "specs",
    "features",
    "enhancements",
    "refactors",
    "remediations",
    "harden-polish",
    "scripts",
    "bugs",
    "bug-fixes",
    "phase-plans",
    "phases",
    "all",
}

_RELATED_KEYS = (
    "related",
    "related_documents",
    "related_specs",
    "related_prd",
    "parent_prd",
    "related_request_logs",
    "references",
    "reference",
    "links",
    "plan_ref",
    "prd_link",
    "source_document",
    "linked_docs",
    "linkeddocs",
    "source_docs",
    "sources",
    "artifacts",
    "related_features",
)
_PRD_KEYS = (
    "prd",
    "prd_reference",
    "prdreference",
    "prd_ref",
    "prdref",
    "related_prd",
    "parent_prd",
    "prd_link",
)
_SESSION_KEYS = ("session", "session_id", "sessionid", "sessions", "linked_sessions", "linkedsessions")
_REQUEST_KEYS = (
    "request_log",
    "request_log_id",
    "source_req",
    "source_request",
    "related_request_logs",
)
_COMMIT_KEYS = (
    "commit",
    "commits",
    "git_commit",
    "git_commits",
    "git_commit_hashes",
    "git_commit_hash",
    "commit_refs",
    "commithash",
)
_FILE_KEYS = (
    "files",
    "files_modified",
    "files_affected",
    "files_created",
    "context_files",
    "source_document",
    "plan_ref",
    "file",
    "file_path",
)
_OWNER_KEYS = ("owner", "owners", "assigned_to", "contributors", "maintainers")
_FEATURE_KEYS = (
    "feature",
    "feature_slug",
    "feature_ref",
    "feature_id",
    "feature_slug_hint",
    "linked_features",
    "linkedfeatures",
    "related_features",
    "lineage_parent",
    "lineage_children",
    "parent_feature",
    "parent_feature_slug",
    "extends_feature",
    "derived_from",
    "supersedes",
    "superseded_by",
)
_DOC_TYPE_DIR_TOKENS = {
    "implementation_plans",
    "prds",
    "reports",
    "specs",
    "design-specs",
    "design",
    "spikes",
    "bugs",
    "enhancements",
    "refactors",
    "remediations",
}
_FEATURE_TYPE_DIR_TOKENS = {
    "feature",
    "features",
    "enhancement",
    "enhancements",
    "refactor",
    "refactors",
    "remediation",
    "remediations",
    "bug",
    "bugs",
    "quick-features",
}

_DOC_TYPE_ALIASES = {
    "prd": "prd",
    "product_requirements": "prd",
    "product_requirements_doc": "prd",
    "requirements": "prd",
    "implementation_plan": "implementation_plan",
    "implementation_plans": "implementation_plan",
    "implementationplan": "implementation_plan",
    "plan": "implementation_plan",
    "phase_plan": "phase_plan",
    "phase_plans": "phase_plan",
    "phaseplan": "phase_plan",
    "report": "report",
    "reports": "report",
    "implementation_report": "report",
    "status_report": "report",
    "qa_report": "report",
    "benchmark": "report",
    "postmortem": "report",
    "spec": "spec",
    "specification": "spec",
    "technical_spec": "spec",
    "api_spec": "spec",
    "progress": "progress",
}

_DOC_STATUS_ALIASES = {
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "active": "in_progress",
    "in_progress": "in_progress",
    "inprogress": "in_progress",
    "working": "in_progress",
    "wip": "in_progress",
    "review": "review",
    "in_review": "review",
    "pending": "pending",
    "draft": "pending",
    "planning": "pending",
    "backlog": "pending",
    "todo": "pending",
    "blocked": "blocked",
    "waiting": "blocked",
    "stalled": "blocked",
    "deferred": "deferred",
    "postponed": "deferred",
    "skipped": "deferred",
    "archived": "archived",
    "inferred_complete": "inferred_complete",
    "inferredcompleted": "inferred_complete",
    "auto_complete": "inferred_complete",
}

_CANONICAL_DOC_STATUSES = {
    "pending",
    "in_progress",
    "review",
    "completed",
    "deferred",
    "blocked",
    "archived",
    "inferred_complete",
}

_DOC_SUBTYPE_ALIASES = {
    "implementation_plan": "implementation_plan",
    "implementationplan": "implementation_plan",
    "plan": "implementation_plan",
    "phase_plan": "phase_plan",
    "phaseplan": "phase_plan",
    "prd": "prd",
    "product_requirements": "prd",
    "product_requirements_doc": "prd",
    "requirements": "prd",
    "report": "report",
    "implementation_report": "report",
    "status_report": "report",
    "qa_report": "report",
    "benchmark": "report",
    "postmortem": "report",
    "spec": "spec",
    "technical_spec": "spec",
    "api_spec": "spec",
    "design_spec": "design_spec",
    "design_doc": "design_doc",
    "spike": "spike",
    "idea": "idea",
    "bug_doc": "bug_doc",
    "progress_phase": "progress_phase",
    "phase_progress": "progress_phase",
    "progress_all_phases": "progress_all_phases",
    "all_phases_progress": "progress_all_phases",
    "progress_quick_feature": "progress_quick_feature",
    "quick_feature_progress": "progress_quick_feature",
    "progress_other": "progress_other",
    "document": "document",
}

_CANONICAL_DOC_SUBTYPES = {
    "implementation_plan",
    "phase_plan",
    "prd",
    "report",
    "spec",
    "design_spec",
    "design_doc",
    "spike",
    "idea",
    "bug_doc",
    "progress_phase",
    "progress_all_phases",
    "progress_quick_feature",
    "progress_other",
    "document",
}


def _normalize_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return re.sub(r"_+", "_", token).strip("_")


def normalize_doc_status(value: str, default: str = "pending") -> str:
    token = _normalize_token(value)
    if not token:
        return default
    mapped = _DOC_STATUS_ALIASES.get(token, token)
    if mapped in _CANONICAL_DOC_STATUSES:
        return mapped
    if token.startswith("inferred") and "complete" in token:
        return "inferred_complete"
    return default


def normalize_doc_type(value: str, default: str = "document") -> str:
    token = _normalize_token(value)
    if not token:
        return default
    mapped = _DOC_TYPE_ALIASES.get(token)
    if mapped:
        return mapped
    if "progress" in token:
        return "progress"
    if "phase" in token and "plan" in token:
        return "phase_plan"
    if "plan" in token:
        return "implementation_plan"
    if "prd" in token or "requirements" in token:
        return "prd"
    if "report" in token:
        return "report"
    if "spec" in token:
        return "spec"
    return default


def normalize_doc_subtype(
    value: str,
    *,
    root_kind: str = "",
    doc_type: str = "",
    default: str = "document",
) -> str:
    token = _normalize_token(value)
    mapped = _DOC_SUBTYPE_ALIASES.get(token, token)
    if mapped in _CANONICAL_DOC_SUBTYPES:
        return mapped

    normalized_root = _normalize_token(root_kind)
    normalized_doc_type = normalize_doc_type(doc_type, default="")
    if normalized_root == "progress" or normalized_doc_type == "progress":
        if "quick" in token:
            return "progress_quick_feature"
        if "all" in token and "phase" in token:
            return "progress_all_phases"
        if token.startswith("phase") or "phase" in token:
            return "progress_phase"
        return "progress_other"

    if normalized_doc_type in {"prd", "implementation_plan", "phase_plan", "report", "spec"}:
        return normalized_doc_type

    return default


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def canonical_slug(slug: str) -> str:
    normalized = (slug or "").strip().lower()
    if not normalized:
        return ""
    return _VERSION_SUFFIX_PATTERN.sub("", normalized)


def normalize_ref_path(raw: str) -> str:
    value = (raw or "").strip().strip("\"'`<>[](),;")
    if not value:
        return ""
    while value.startswith("./"):
        value = value[2:]
    if value.startswith("../"):
        return ""
    value = value.replace("\\", "/")
    if _NOISY_PATH_PATTERN.search(value):
        return ""
    return value


def infer_project_root(docs_dir: Path | None = None, progress_dir: Path | None = None) -> Path:
    """Infer project root from docs/progress roots.

    Priority:
    1) common parent of docs+progress,
    2) docs parent parent for docs/project_plans layout,
    3) progress parent parent for .claude/progress layout.
    """
    candidates = [p.resolve() for p in (docs_dir, progress_dir) if isinstance(p, Path)]
    if len(candidates) >= 2:
        common = Path(os.path.commonpath([str(v) for v in candidates]))
        return common

    if isinstance(docs_dir, Path):
        resolved = docs_dir.resolve()
        if resolved.name.lower() == "project_plans" and resolved.parent.name.lower() == "docs":
            return resolved.parent.parent
        return resolved.parent

    if isinstance(progress_dir, Path):
        resolved = progress_dir.resolve()
        if resolved.name.lower() == "progress" and resolved.parent.name.lower() == ".claude":
            return resolved.parent.parent
        return resolved.parent

    return Path.cwd()


def canonical_project_path(path_value: Path | str, project_root: Path) -> str:
    """Return a normalized project-relative path when possible."""
    path = Path(path_value)
    try:
        rel = path.resolve().relative_to(project_root.resolve())
        value = str(rel)
    except Exception:
        value = str(path)
    return normalize_ref_path(value)


def make_document_id(path_value: str) -> str:
    normalized = normalize_ref_path(path_value)
    token = (normalized or path_value).replace("/", "-").replace("\\", "-").replace(".md", "")
    return f"DOC-{token}"


def slug_from_path(path_value: str) -> str:
    normalized = normalize_ref_path(path_value)
    if not normalized:
        return ""
    return Path(normalized).stem.lower()


def is_generic_phase_progress_slug(slug: str) -> bool:
    token = (slug or "").strip().lower()
    if not token:
        return False
    return bool(_GENERIC_PHASE_PROGRESS_PATTERN.match(token))


def is_generic_alias_token(token: str) -> bool:
    value = (token or "").strip().lower()
    if not value:
        return True
    if value in _GENERIC_ALIAS_TOKENS:
        return True
    if value.startswith("phase-") and value.endswith("-progress"):
        return True
    if is_generic_phase_progress_slug(value):
        return True
    return False


def is_feature_like_token(token: str) -> bool:
    value = (token or "").strip().lower()
    if not value:
        return False
    if is_generic_alias_token(value):
        return False
    if not _FEATURE_TOKEN_PATTERN.match(value):
        return False
    # Feature IDs are typically kebab/snake tokens, often versioned.
    if "-" not in value and "_" not in value and not re.search(r"v\d", value):
        return False
    return True


def _is_path_like(value: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    lowered = candidate.lower()
    if lowered.endswith(".md"):
        return True
    if "/" not in candidate and "\\" not in candidate:
        return False
    if any(ch.isspace() for ch in candidate):
        return False
    if _NOISY_PATH_PATTERN.search(candidate):
        return False
    if not _PATH_WITH_EXT_PATTERN.match(candidate):
        return False
    normalized = candidate.replace("\\", "/")
    if normalized.endswith("/"):
        return False
    tail = normalized.rsplit("/", 1)[-1]
    has_extension = "." in tail and not tail.startswith(".")
    has_doc_marker = any(
        marker in lowered
        for marker in (
            "project_plans/",
            "implementation_plans/",
            "prds/",
            "reports/",
            "specs/",
            ".claude/progress/",
            "/progress/",
            "progress/",
        )
    )
    return has_extension or has_doc_marker


def feature_slug_from_path(path_value: str) -> str:
    normalized = normalize_ref_path(path_value)
    if not normalized:
        return ""
    path = Path(normalized)
    parts = [part for part in path.parts if part]
    lowered = [part.lower() for part in parts]

    for idx, part in enumerate(lowered):
        if part == "progress" and idx + 1 < len(parts):
            candidate = parts[idx + 1].lower()
            if is_feature_like_token(candidate):
                return candidate

    for idx, part in enumerate(lowered):
        if part not in _DOC_TYPE_DIR_TOKENS:
            continue
        if idx + 2 >= len(parts):
            continue
        feature_type = lowered[idx + 1]
        if feature_type not in _FEATURE_TYPE_DIR_TOKENS:
            continue
        target = parts[idx + 2]
        candidate = Path(target).stem.lower() if target.lower().endswith(".md") else target.lower()
        if is_feature_like_token(candidate):
            return candidate

    stem = path.stem.lower()
    if is_feature_like_token(stem):
        return stem
    if (is_generic_phase_progress_slug(stem) or stem.startswith("phase-")) and is_feature_like_token(path.parent.name.lower()):
        return path.parent.name.lower()
    return ""


def split_path_and_slug_refs(values: list[str]) -> tuple[list[str], list[str]]:
    path_refs: list[str] = []
    slug_refs: list[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        if _is_path_like(value):
            normalized = normalize_ref_path(value)
            if normalized:
                path_refs.append(normalized)
                stem = slug_from_path(normalized)
                if stem and not is_generic_alias_token(stem):
                    slug_refs.append(stem)
            continue
        slug = value.lower().strip()
        if slug and not is_generic_alias_token(slug):
            slug_refs.append(slug)
    return _unique(path_refs), _unique(slug_refs)


def _flatten_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        collected: list[str] = []
        for item in value:
            collected.extend(_flatten_string_values(item))
        return collected
    if isinstance(value, dict):
        collected = []
        # Prefer explicit path-ish keys first, then include all string leaves.
        for preferred in ("path", "file", "file_path", "target", "source", "doc", "id", "name"):
            if preferred in value:
                collected.extend(_flatten_string_values(value.get(preferred)))
        for nested in value.values():
            collected.extend(_flatten_string_values(nested))
        return collected
    return []


def alias_tokens_from_path(path_value: str) -> set[str]:
    normalized = normalize_ref_path(path_value)
    if not normalized:
        return set()
    path = Path(normalized)
    raw_tokens: set[str] = set()
    feature_slug = feature_slug_from_path(normalized)
    if feature_slug:
        raw_tokens.add(feature_slug)

    stem = path.stem.lower()
    parent = path.parent.name.lower()
    if is_feature_like_token(stem):
        raw_tokens.add(stem)
    if (is_generic_phase_progress_slug(stem) or stem.startswith("phase-")) and is_feature_like_token(parent):
        raw_tokens.add(parent)
    elif is_feature_like_token(parent):
        raw_tokens.add(parent)

    aliases: set[str] = set()
    for token in raw_tokens:
        value = (token or "").strip().lower()
        if not value or is_generic_alias_token(value):
            continue
        aliases.add(value)
        canonical = canonical_slug(value)
        if canonical and not is_generic_alias_token(canonical):
            aliases.add(canonical)
    return aliases


def classify_doc_type(path_value: str, frontmatter: dict[str, Any] | None = None) -> str:
    normalized = normalize_ref_path(path_value).lower()
    fm = frontmatter or {}
    explicit = normalize_doc_type(str(fm.get("doc_type") or fm.get("doctype") or ""), default="")
    if explicit:
        return explicit
    if normalized.startswith("progress/") or "/progress/" in normalized:
        return "progress"
    if normalized.startswith("prds/") or "/prds/" in normalized:
        return "prd"
    if normalized.startswith("implementation_plans/") or "/implementation_plans/" in normalized:
        stem = Path(normalized).stem.lower()
        if stem.startswith("phase-"):
            return "phase_plan"
        return "implementation_plan"
    if normalized.startswith("reports/") or "/reports/" in normalized:
        return "report"
    if normalized.startswith("specs/") or "/specs/" in normalized or "/spec/" in normalized:
        return "spec"
    return "document"


def detect_root_kind(path_value: str) -> str:
    normalized = normalize_ref_path(path_value).lower()
    if not normalized:
        return "document"
    if normalized.startswith(".claude/progress/") or normalized.startswith("progress/") or "/progress/" in normalized:
        return "progress"
    return "project_plans"


def classify_doc_subtype(path_value: str, frontmatter: dict[str, Any] | None = None) -> str:
    normalized = normalize_ref_path(path_value).lower()
    fm = frontmatter or {}
    explicit_type_raw = str(fm.get("type") or fm.get("doc_type") or fm.get("doctype") or "")
    explicit_type = normalize_doc_type(explicit_type_raw, default="")
    explicit_type_token = _normalize_token(explicit_type_raw)
    explicit_subtype = str(fm.get("doc_subtype") or fm.get("docSubtype") or fm.get("subtype") or "").strip()
    stem = Path(normalized).stem.lower() if normalized else ""
    parent = Path(normalized).parent.name.lower() if normalized else ""
    root_kind = detect_root_kind(normalized)
    if root_kind == "progress":
        if parent == "quick-features" or explicit_type_token in {"quick_feature", "quick_feature_plan"}:
            return "progress_quick_feature"
        if "all-phases" in stem:
            return "progress_all_phases"
        if stem.startswith("phase-"):
            return "progress_phase"
        raw_subtype = explicit_subtype or "progress_other"
        return normalize_doc_subtype(raw_subtype, root_kind=root_kind, doc_type="progress", default="progress_other")

    doc_type = classify_doc_type(normalized, fm)
    if explicit_subtype:
        return normalize_doc_subtype(explicit_subtype, root_kind=root_kind, doc_type=doc_type)
    if doc_type == "phase_plan":
        return "phase_plan"
    if doc_type == "implementation_plan":
        return "implementation_plan"
    if doc_type == "prd":
        return "prd"
    if doc_type == "report":
        return "report"
    if doc_type == "spec":
        return "spec"
    if normalized.startswith("design-specs/") or "/design-specs/" in normalized:
        return "design_spec"
    if normalized.startswith("design/") or "/design/" in normalized:
        return "design_doc"
    if normalized.startswith("spikes/") or "/spikes/" in normalized:
        return "spike"
    if normalized.startswith("ideas/") or "/ideas/" in normalized:
        return "idea"
    if normalized.startswith("bugs/") or "/bugs/" in normalized:
        return "bug_doc"
    return normalize_doc_subtype("", root_kind=root_kind, doc_type=doc_type, default="document")


def classify_doc_category(path_value: str, frontmatter: dict[str, Any] | None = None) -> str:
    fm = frontmatter or {}
    explicit = str(fm.get("category") or "").strip()
    if explicit:
        return explicit
    normalized = normalize_ref_path(path_value)
    if not normalized:
        return ""
    parts = [p for p in Path(normalized).parts if p]
    lowered = [p.lower() for p in parts]
    for marker in ("implementation_plans", "prds", "reports", "progress"):
        if marker in lowered:
            idx = lowered.index(marker)
            if idx + 1 < len(parts):
                return parts[idx + 1]
    if len(parts) >= 2:
        return parts[-2]
    return ""


def extract_frontmatter_references(frontmatter: dict[str, Any] | None) -> dict[str, list[str] | str]:
    fm = frontmatter or {}
    refs_raw: list[str] = []
    prd_values: list[str] = []
    session_values: list[str] = []
    request_values: list[str] = []
    commit_values: list[str] = []
    file_values: list[str] = []
    owner_values: list[str] = []
    feature_values: list[str] = []

    lowered_map = {str(key).strip().lower(): value for key, value in fm.items()}
    for key, value in lowered_map.items():
        if key in _RELATED_KEYS:
            refs_raw.extend(_flatten_string_values(value))
        if key in _PRD_KEYS:
            prd_values.extend(_flatten_string_values(value))
        if key in _SESSION_KEYS:
            session_values.extend(_flatten_string_values(value))
        if key in _REQUEST_KEYS:
            request_values.extend(_flatten_string_values(value))
        if key in _COMMIT_KEYS:
            commit_values.extend(_flatten_string_values(value))
        if key in _FILE_KEYS:
            file_values.extend(_flatten_string_values(value))
        if key in _OWNER_KEYS:
            owner_values.extend(_flatten_string_values(value))
        if key in _FEATURE_KEYS:
            feature_values.extend(_flatten_string_values(value))

    # Include obvious markdown path references in any scalar field.
    for value in fm.values():
        for token in _flatten_string_values(value):
            if _is_path_like(token):
                refs_raw.append(token)

    prd_values = _unique(prd_values)
    session_values = _unique(session_values)
    request_values = _unique(request_values)
    commit_values = _unique(commit_values)
    file_values = _unique(file_values)
    owner_values = _unique(owner_values)
    feature_values = _unique(feature_values)
    refs_raw = _unique(refs_raw + prd_values + file_values + feature_values)
    path_refs, slug_refs = split_path_and_slug_refs(refs_raw)
    path_feature_refs = [feature_slug_from_path(path_ref) for path_ref in path_refs]
    slug_feature_refs = [slug for slug in slug_refs if is_feature_like_token(slug)] + [
        slug for slug in feature_values if is_feature_like_token(slug)
    ]
    feature_refs = _unique([
        *path_feature_refs,
        *slug_feature_refs,
        *[canonical_slug(v) for v in [*path_feature_refs, *slug_feature_refs] if canonical_slug(v)],
    ])
    prd_primary = prd_values[0] if prd_values else ""
    return {
        "relatedRefs": refs_raw,
        "pathRefs": path_refs,
        "slugRefs": slug_refs,
        "featureRefs": feature_refs,
        "prdRefs": prd_values,
        "prd": prd_primary,
        "sessionRefs": session_values,
        "requestRefs": request_values,
        "commitRefs": commit_values,
        "fileRefs": _unique(file_values + path_refs),
        "ownerRefs": owner_values,
    }
