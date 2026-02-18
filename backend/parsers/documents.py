"""Parse markdown project plan files (frontmatter-first) into PlanDocument models."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.models import PlanDocument, DocumentFrontmatter
from backend.document_linking import (
    alias_tokens_from_path,
    classify_doc_category,
    classify_doc_type,
    extract_frontmatter_references,
)


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a markdown file."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = match.group(2)
    return fm, body


def _make_doc_id(path: Path, base_dir: Path) -> str:
    """Create a document ID from its relative path."""
    rel = path.relative_to(base_dir)
    slug = str(rel).replace("/", "-").replace("\\", "-").replace(".md", "")
    return f"DOC-{slug}"


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
                for key in ("id", "path", "value", "url"):
                    raw = entry.get(key)
                    if isinstance(raw, str) and raw.strip():
                        items.append(raw.strip())
                        break
        return items
    return []


def _first_string(value: Any) -> str:
    values = _to_string_list(value)
    return values[0] if values else ""


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


def parse_document_file(path: Path, base_dir: Path) -> PlanDocument | None:
    """Parse a single markdown file into a PlanDocument."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    fm, body = _extract_frontmatter(text)
    if not fm:
        # Files without frontmatter still get indexed
        fm = {}

    title = fm.get("title", path.stem.replace("-", " ").replace("_", " ").title())
    status = fm.get("status", "active")
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    created = fm.get("created", "")
    updated = fm.get("updated", created)
    last_modified = str(updated) if updated else ""

    # Author: use first audience entry or fallback
    audience = fm.get("audience", [])
    author = audience[0] if isinstance(audience, list) and audience else fm.get("author", "")

    # Related links → linkedFeatures
    refs = extract_frontmatter_references(fm)
    related_refs = [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)]
    linked_feature_refs = [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)]
    linked_session_refs = [str(v) for v in refs.get("sessionRefs", []) if isinstance(v, str)]
    prd_refs = [str(v) for v in refs.get("prdRefs", []) if isinstance(v, str)]
    prd_primary = str(refs.get("prd") or "")

    commits = _to_string_list(
        fm.get("commits")
        or fm.get("commit")
        or fm.get("git_commits")
        or fm.get("git_commits_hashes")
    )
    prs = _to_string_list(
        fm.get("prs")
        or fm.get("pr")
        or fm.get("pull_requests")
        or fm.get("pullRequests")
    )
    version = _first_string(fm.get("version"))

    rel_path = str(path.relative_to(base_dir))
    doc_type = classify_doc_type(rel_path, fm)
    category = classify_doc_category(rel_path, fm)
    path_segments = list(Path(rel_path).parts)
    feature_candidates = sorted(
        set(linked_feature_refs).union(alias_tokens_from_path(rel_path))
    )
    frontmatter_keys = sorted(str(key) for key in fm.keys())

    return PlanDocument(
        id=_make_doc_id(path, base_dir),
        title=title,
        filePath=rel_path,
        status=str(status),
        lastModified=last_modified,
        author=str(author),
        docType=doc_type,
        category=str(category),
        pathSegments=path_segments,
        featureCandidates=feature_candidates,
        frontmatter=DocumentFrontmatter(
            tags=tags,
            linkedFeatures=linked_feature_refs,
            linkedSessions=linked_session_refs,
            version=version or None,
            commits=commits,
            prs=prs,
            relatedRefs=related_refs,
            pathRefs=[str(v) for v in refs.get("pathRefs", []) if isinstance(v, str)],
            slugRefs=[str(v) for v in refs.get("slugRefs", []) if isinstance(v, str)],
            prd=prd_primary,
            prdRefs=prd_refs,
            fieldKeys=frontmatter_keys,
            raw=_json_safe({str(k): v for k, v in fm.items()}),
        ),
        content=body[:5000] if body else None,  # store a preview
    )


def scan_documents(documents_dir: Path) -> list[PlanDocument]:
    """Scan a directory recursively for .md files and parse them."""
    docs = []
    if not documents_dir.exists():
        return docs

    for path in sorted(documents_dir.rglob("*.md")):
        # Skip hidden files and READMEs (or include them — your choice)
        if path.name.startswith("."):
            continue
        doc = parse_document_file(path, documents_dir)
        if doc:
            docs.append(doc)

    return docs
