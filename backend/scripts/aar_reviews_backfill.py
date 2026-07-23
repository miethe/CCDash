#!/usr/bin/env python3
"""One-time idempotent backfill: aar_reviews rows for every AAR<->session pair
already discoverable via ``entity_links`` (T1-008, ``ccdash-automated-aar-review-v1``
Phase 1).

HARD INVARIANT: zero LLM/model calls anywhere on this path. This module
performs zero derivation of its own -- every correlation/flag/verdict value
it persists is computed by the existing, already-shipped deterministic
triage service (``backend/application/services/agent_queries/aar_review.py``
:: ``AARReviewQueryService.get_review``, which reuses ``_correlate`` and
``compute_verdict`` internally). This module's only job is:

  1. Discover candidate AAR document rows already synced into the
     ``documents`` table (a filename heuristic -- see
     ``looks_like_aar_document``; matches the ``op story``-produced AAR
     naming convention observed in this repo, e.g.
     ``docs/project_plans/reports/<slug>-aar-<date>.md``).
  2. For each candidate, call the existing ``AARReviewQueryService`` to
     compute its (correlation, flags, verdict) via ``entity_links`` --
     exactly what a live REST/CLI/MCP caller would get.
  3. Fan the result out into one ``aar_reviews`` row per resolved
     ``correlation.session_ids`` entry (``build_aar_review_rows``) and
     upsert each row by the ``(aar_document_id, session_id)`` dedup key.

Idempotency: re-running is a no-op on row *count* -- the upsert conflict
target is exactly the dedup key, and the computed DTO for an unchanged
document/entity_links snapshot is byte-identical across runs, so a second
pass overwrites each row in place rather than inserting a duplicate.
Documents whose correlation resolves zero sessions contribute zero rows on
every run (there is no pairing to persist) -- this is what makes "row count
matches the discoverable pair count" hold exactly, not just approximately.

Usage:
  python backend/scripts/aar_reviews_backfill.py
  python backend/scripts/aar_reviews_backfill.py --project default-skillmeat
  python backend/scripts/aar_reviews_backfill.py --all-projects
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path as _Path
from typing import Any

ROOT = _Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite

from backend.application.ports import CorePorts
from backend.application.services.agent_queries.aar_review import AARReviewQueryService
from backend.application.services.common import resolve_application_request
from backend.db.repositories.aar_reviews import (
    PostgresAarReviewsRepository,
    SqliteAarReviewsRepository,
    build_aar_review_rows,
)

__all__ = ["looks_like_aar_document", "backfill_aar_reviews_for_project"]

# Filename fragments that mark a synced ``documents`` row as an AAR document.
# Matches the ``op story``-produced naming convention observed in this repo
# (``<feature-slug>-aar-<date>.md``) plus the plain ``aar.md`` worknote
# convention. Deterministic string matching only -- never a semantic/model
# judgment (Hard Invariant).
_AAR_STEM_INFIX = "-aar-"
_AAR_STEM_SUFFIX = "-aar"
_AAR_STEM_PREFIX = "aar-"
_AAR_STEM_EXACT = "aar"


def looks_like_aar_document(doc_row: dict[str, Any]) -> bool:
    """Return True when *doc_row* (a ``documents`` table row) looks like an AAR.

    Checks the document's file stem (falling back to deriving it from
    ``canonical_path``/``file_path`` when the ``file_stem`` column is empty)
    against the naming convention documented on the module docstring.
    """
    stem = str(doc_row.get("file_stem") or "").strip().lower()
    if not stem:
        raw_path = str(doc_row.get("canonical_path") or doc_row.get("file_path") or "")
        stem = _Path(raw_path).stem.lower()
    if not stem:
        return False
    return (
        stem == _AAR_STEM_EXACT
        or _AAR_STEM_INFIX in stem
        or stem.endswith(_AAR_STEM_SUFFIX)
        or stem.startswith(_AAR_STEM_PREFIX)
    )


def _aar_reviews_repo(db: Any) -> SqliteAarReviewsRepository | PostgresAarReviewsRepository:
    if isinstance(db, aiosqlite.Connection):
        return SqliteAarReviewsRepository(db)
    return PostgresAarReviewsRepository(db)


async def backfill_aar_reviews_for_project(
    db: Any,
    project_id: str,
    *,
    ports: CorePorts | None = None,
) -> int:
    """Backfill every discoverable AAR<->session pair for *project_id*.

    Returns the number of ``aar_reviews`` rows written (inserted or
    updated-in-place) on this pass. Safe to call repeatedly -- see module
    docstring for the idempotency contract.
    """
    app_request = await resolve_application_request(
        None, ports, db, requested_project_id=project_id,
    )
    context, resolved_ports = app_request.context, app_request.ports

    documents_repo = resolved_ports.storage.documents()
    doc_rows = await documents_repo.list_all(project_id)
    candidates = [row for row in doc_rows if looks_like_aar_document(row)]

    review_service = AARReviewQueryService()
    reviews_repo = _aar_reviews_repo(db)

    written = 0
    for doc_row in candidates:
        document_id = str(doc_row.get("id") or "")
        if not document_id:
            continue
        dto = await review_service.get_review(context, resolved_ports, document_id, bypass_cache=True)
        if dto.status != "ok":
            continue
        aar_document_path = str(
            doc_row.get("canonical_path") or doc_row.get("file_path") or ""
        )
        rows = build_aar_review_rows(dto, project_id=project_id, aar_document_path=aar_document_path)
        for row in rows:
            await reviews_repo.upsert(row)
            written += 1

    return written


async def _run(project_id: str | None, all_projects: bool) -> int:
    from backend.db import connection, migrations
    # T1-007 / ADR-006: use the DB-backed authoritative registry.
    from backend.project_manager import db_project_manager as project_manager

    db = await connection.get_connection()
    await migrations.run_migrations(db)

    if all_projects:
        targets = project_manager.list_projects()
    elif project_id:
        project = project_manager.get_project(project_id)
        if not project:
            print(f"Project not found: {project_id}")
            await connection.close_connection()
            return 1
        targets = [project]
    else:
        active = project_manager.get_active_project()
        targets = [active] if active else []

    if not targets:
        print("No projects available to backfill.")
        await connection.close_connection()
        return 0

    for project in targets:
        written = await backfill_aar_reviews_for_project(db, project.id)
        print(f"{project.id}: aar_reviews_rows_written={written}")

    await connection.close_connection()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="", help="Project ID to backfill (default: active project)")
    parser.add_argument("--all-projects", action="store_true", help="Backfill all configured projects")
    args = parser.parse_args()
    return asyncio.run(_run(args.project or None, args.all_projects))


if __name__ == "__main__":
    raise SystemExit(main())
