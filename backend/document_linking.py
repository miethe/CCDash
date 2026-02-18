"""Shared utilities for document/session/feature linking.

These helpers centralize path normalization, slug extraction, document
classification, and frontmatter reference parsing so parsers and linkers
use consistent matching semantics.
"""
from __future__ import annotations

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
    "references",
    "reference",
    "links",
    "linked_docs",
    "linkeddocs",
    "source_docs",
    "sources",
    "artifacts",
)
_PRD_KEYS = ("prd", "prd_reference", "prdreference", "prd_ref", "prdref")
_SESSION_KEYS = ("session", "session_id", "sessionid", "sessions", "linked_sessions", "linkedsessions")
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
    explicit = str(fm.get("doc_type") or fm.get("doctype") or "").strip().lower()
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

    lowered_map = {str(key).strip().lower(): value for key, value in fm.items()}
    for key, value in lowered_map.items():
        if key in _RELATED_KEYS:
            refs_raw.extend(_flatten_string_values(value))
        if key in _PRD_KEYS:
            prd_values.extend(_flatten_string_values(value))
        if key in _SESSION_KEYS:
            session_values.extend(_flatten_string_values(value))

    # Include obvious markdown path references in any scalar field.
    for value in fm.values():
        for token in _flatten_string_values(value):
            if _is_path_like(token):
                refs_raw.append(token)

    prd_values = _unique(prd_values)
    session_values = _unique(session_values)
    refs_raw = _unique(refs_raw + prd_values)
    path_refs, slug_refs = split_path_and_slug_refs(refs_raw)
    path_feature_refs = [feature_slug_from_path(path_ref) for path_ref in path_refs]
    slug_feature_refs = [slug for slug in slug_refs if is_feature_like_token(slug)]
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
    }
