"""Parse markdown project plan files (frontmatter-first) into PlanDocument models."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend.models import PlanDocument, DocumentFrontmatter


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
    related = fm.get("related", [])
    if isinstance(related, str):
        related = [related]
    if not isinstance(related, list):
        related = []

    category = fm.get("category", "")
    rel_path = str(path.relative_to(base_dir))

    return PlanDocument(
        id=_make_doc_id(path, base_dir),
        title=title,
        filePath=rel_path,
        status=str(status),
        lastModified=last_modified,
        author=str(author),
        frontmatter=DocumentFrontmatter(
            tags=tags,
            linkedFeatures=[str(r) for r in related],
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
