"""Spec document creation service — P5-010.

Writes a new markdown spec document under a project's plan-docs directory.
This is the only write-path for spec documents; all reads go through the
sync engine and repositories as normal.

Design decisions:
- Path safety: the resolved write path is validated to be under the project's
  plan_docs root before writing. Traversal attempts raise ValueError.
- Slug derivation: matches how ``make_document_id`` in document_linking.py
  derives DOC-<slug> identifiers. The slug is the filename stem (sans .md).
- Light sync: we do NOT run a full sync inline. Callers note that the new file
  will appear in the DB after the next background sync cycle (typically <60s).
- Timestamp: generated at call-time, never at import, to satisfy the
  "do NOT call datetime.now at import" constraint.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert a human title to a URL/filename-safe slug.

    Keeps only ASCII alphanumerics and hyphens; collapses runs of non-word
    chars into a single dash; strips leading/trailing dashes.
    """
    lower = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", lower)
    slug = slug.strip("-")
    return slug or "untitled"


def _short_uid() -> str:
    """Return a 6-char hex suffix for collision avoidance."""
    return uuid.uuid4().hex[:6]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class SpecCreateResult(TypedDict):
    id: str
    path: str
    status: str


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def create_spec_document(
    plan_docs_dir: Path,
    title: str,
    doc_type: str = "design-spec",
    *,
    now: datetime | None = None,
) -> SpecCreateResult:
    """Write a new spec markdown file and return (id, path, status).

    Parameters
    ----------
    plan_docs_dir:
        The resolved plan-docs directory for the target project (must exist or
        be creatable; must be an absolute path resolved from the project root).
    title:
        Human-readable spec title (1–200 chars).
    doc_type:
        Frontmatter ``doc_type`` value.  Defaults to ``"design-spec"``.
    now:
        Timestamp to embed in the frontmatter.  Injected by callers for
        testability; defaults to ``datetime.now(timezone.utc)`` when None.

    Returns
    -------
    SpecCreateResult
        ``id``: the DOC-<slug> identifier the sync engine would assign.
        ``path``: the relative path from ``plan_docs_dir`` to the new file.
        ``status``: always ``"created"`` on success.

    Raises
    ------
    ValueError
        If ``title`` is empty/too long, ``doc_type`` contains invalid chars,
        or the resolved write path would escape ``plan_docs_dir`` (traversal).
    FileExistsError
        Should be unreachable in practice (uid suffix), but surfaced if somehow
        the generated filename already exists.
    """
    # ── Input validation ────────────────────────────────────────────────────
    title = (title or "").strip()
    if not title:
        raise ValueError("title must not be empty")
    if len(title) > 200:
        raise ValueError("title must be 200 characters or fewer")

    doc_type = (doc_type or "design-spec").strip()
    if not re.match(r"^[a-z0-9][a-z0-9\-]*$", doc_type):
        raise ValueError(
            "doc_type must be lower-kebab-case (e.g. 'design-spec', 'prd')"
        )

    # ── Filename derivation ─────────────────────────────────────────────────
    slug = _slugify(title)
    uid = _short_uid()
    filename = f"{slug}-{uid}.md"

    # ── Path safety ─────────────────────────────────────────────────────────
    plan_docs_dir = plan_docs_dir.resolve()
    target = (plan_docs_dir / filename).resolve()

    try:
        target.relative_to(plan_docs_dir)
    except ValueError as exc:
        raise ValueError(
            f"Resolved write path {target} escapes plan_docs_dir {plan_docs_dir}."
        ) from exc

    # ── Timestamp ───────────────────────────────────────────────────────────
    ts: datetime = now if now is not None else datetime.now(timezone.utc)
    created_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = ts.strftime("%Y-%m-%d")

    # ── Frontmatter + body ──────────────────────────────────────────────────
    content = (
        f"---\n"
        f"schema_version: 2\n"
        f"doc_type: {doc_type}\n"
        f"title: {title}\n"
        f"status: draft\n"
        f"created: {created_str}\n"
        f"updated: {date_str}\n"
        f"---\n"
        f"\n"
        f"# {title}\n"
        f"\n"
        f"> Status: draft — created {date_str}\n"
        f"\n"
        f"## Overview\n"
        f"\n"
        f"<!-- Add spec content here -->\n"
    )

    # ── Write ────────────────────────────────────────────────────────────────
    plan_docs_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"File already exists: {target}")
    target.write_text(content, encoding="utf-8")

    # ── Derive doc id (mirrors document_linking.make_document_id) ───────────
    # make_document_id normalises the path, replaces "/" with "-", strips ".md"
    # then prepends "DOC-".  Since we write the file into plan_docs_dir, the
    # relative path IS just the filename.  We replicate the logic directly to
    # avoid importing the full document_linking module (which has heavy deps).
    relative_path = filename  # plan_docs_dir-relative
    doc_id = "DOC-" + relative_path.replace("/", "-").replace("\\", "-").replace(".md", "")

    # Note: a light sync of this specific file is NOT triggered here.
    # The background sync cycle (CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS,
    # default 300s) will pick it up.  For immediate visibility, callers may
    # call the cache-invalidation endpoint.

    return SpecCreateResult(id=doc_id, path=relative_path, status="created")
