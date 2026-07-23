"""AAR review rollup read handler for the v1 client router (T4-002).

Serves the persisted ``aar_reviews`` rollup (``backend/db/repositories/
aar_reviews.py``) computed offline by the deterministic AAR-document-to-
session triage service (``backend/application/services/agent_queries/
aar_review.py::AARReviewQueryService``). This module performs **zero**
derivation of its own -- it deserialises already-computed JSON columns
verbatim into the reconciled §7.2 ``AARReviewDTO`` shape (nested
``correlation``, 3-value ``triage_verdict``, ``flags[]``, ``reasons``, and
the deprecated flat aliases, all auto-synced by that DTO's validator).

Redaction note
--------------
Every session-derived string that can appear in a persisted row
(``flags[].rationale``, ``reasons``, ``evidence_refs``) was already computed
exclusively from the redaction-applied ``session_detail.get_session_detail``
bundle at *persist* time -- see ``aar_review.py`` (module docstring + the
``session_detail_bits`` call site). This module never re-reads session
content and never touches ``session_detail`` itself; it only deserialises
the JSON blobs already written to ``aar_reviews``, so no additional
redaction pass is needed (or possible to add without re-deriving, which is
out of this module's scope) here.

Caching note
------------
``memoized_query``'s data-version fingerprint does NOT track the
``aar_reviews`` table, so cached rollups do not self-invalidate on a raw
row write. Freshness is instead handled at the write site: the P6 sweep
worker (``backend/adapters/jobs/aar_review_sweep_job.py``) calls
``aclear_project_cache`` whenever it persists rows (writes > 0), evicting
this endpoint's cached entries. Rows also originate from the offline
backfill script, which runs before the server serves reads. If a future
writer persists ``aar_reviews`` rows WITHOUT clearing the project cache,
callers could observe a stale verdict for up to the cache TTL -- any such
writer MUST invalidate the cache the way the sweep worker does.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

import aiosqlite

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries._filters import resolve_project_scope
from backend.application.services.agent_queries.cache import memoized_query
from backend.application.services.agent_queries.models import (
    AARReviewCorrelation,
    AARReviewDTO,
    AARReviewFlag,
)
from backend.db.repositories.aar_reviews import (
    PostgresAarReviewsRepository,
    SqliteAarReviewsRepository,
)
from backend.observability import otel
from backend.routers.client_v1_models import (
    AARReviewListDTO,
    ClientV1Envelope,
    build_client_v1_meta,
)

logger = logging.getLogger("ccdash.routers.client_v1_aar_review")


def _get_instance_id() -> str:
    """Return a stable instance identifier, falling back to a default label."""
    return getattr(config, "INSTANCE_ID", "") or "ccdash-local"


# ---------------------------------------------------------------------------
# JSON column parsing -- defensive against both a JSON-text column (SQLite,
# and PostgreSQL when the driver has no jsonb codec registered) and an
# already-decoded value (PostgreSQL when a jsonb codec IS registered).
# Mirrors backend/db/repositories/session_intelligence.py::_loads_dict.
# ---------------------------------------------------------------------------


def _loads_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _loads_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _row_to_aar_review_dto(row: Mapping[str, Any]) -> AARReviewDTO:
    """Deserialise one persisted ``aar_reviews`` row into an ``AARReviewDTO``.

    Zero derivation: every field already exists on the row, verbatim or
    JSON-decoded -- mirrors ``build_aar_review_row``'s mapping in reverse.
    """
    correlation_data = _loads_dict(row.get("correlation"))
    flags_data = _loads_list(row.get("flags"))
    reasons_data = _loads_list(row.get("triage_reasons"))
    evidence_data = _loads_list(row.get("evidence_refs"))

    return AARReviewDTO(
        document_id=str(row.get("aar_document_id") or ""),
        correlation=AARReviewCorrelation(**correlation_data),
        flags=[AARReviewFlag(**flag) for flag in flags_data if isinstance(flag, dict)],
        triage_verdict=row.get("triage_verdict") or None,
        reasons=[str(r) for r in reasons_data],
        generated_at=str(row.get("generated_at") or ""),
        source_refs=[str(r) for r in evidence_data],
    )


def _dedupe_rows_by_document(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Collapse the ``(aar_document_id, session_id)`` fan-out to one row per document.

    Every row for the same ``aar_document_id`` carries an identical
    correlation/flags/triage_verdict snapshot (see aar_reviews.py's module
    docstring) -- only the row's own ``session_id`` column differs, and that
    column is not part of the ``AARReviewDTO`` shape. Keeps the first
    occurrence per document (rows arrive newest-first from
    ``get_by_project``).
    """
    seen: set[str] = set()
    deduped: list[Mapping[str, Any]] = []
    for row in rows:
        doc_id = str(row.get("aar_document_id") or "")
        if doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(row)
    return deduped


# ---------------------------------------------------------------------------
# Cache param extractor + memoized fetch
# ---------------------------------------------------------------------------


def _aar_review_list_params(
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    bypass_cache: bool = False,  # noqa: ARG001 - consumed by the decorator
) -> dict[str, Any]:
    return {"project_id": project_id_override or ""}


@memoized_query("aar_review_list", param_extractor=_aar_review_list_params)
async def _fetch_aar_review_list(
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    bypass_cache: bool = False,  # noqa: ARG001 - consumed by the decorator; kept for REST parity
) -> AARReviewListDTO:
    """Fetch and deserialise the persisted ``aar_reviews`` rollup for a project."""
    scope = resolve_project_scope(context, ports, project_id_override)
    if scope is None:
        # No resolvable project -- normalized empty payload, never an error.
        return AARReviewListDTO(project_id=project_id_override or "", total=0, reviews=[])

    project_id = scope.project.id

    with otel.start_span("aar_review.list", {"project_id": project_id}):
        try:
            db = ports.storage.db
            repo: Any = (
                SqliteAarReviewsRepository(db)
                if isinstance(db, aiosqlite.Connection)
                else PostgresAarReviewsRepository(db)
            )
            rows = await repo.get_by_project(project_id)
        except Exception:
            logger.exception(
                "aar_review: get_by_project failed project_id=%s", project_id
            )
            # Resilience: a read failure degrades to an empty payload, not
            # an HTTP error -- contract state, not a bug.
            return AARReviewListDTO(project_id=project_id, total=0, reviews=[])

        if not rows:
            return AARReviewListDTO(project_id=project_id, total=0, reviews=[])

        deduped_rows = _dedupe_rows_by_document(rows)
        reviews = [_row_to_aar_review_dto(row) for row in deduped_rows]

        return AARReviewListDTO(project_id=project_id, total=len(reviews), reviews=reviews)


# ---------------------------------------------------------------------------
# Public handler (registered on client_v1_router by client_v1.py)
# ---------------------------------------------------------------------------


async def get_aar_review_v1(
    project_id: str | None,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    bypass_cache: bool = False,
) -> ClientV1Envelope[AARReviewListDTO]:
    """Return the persisted AAR review rollup for a project, wrapped in a v1 envelope."""
    result = await _fetch_aar_review_list(
        request_context,
        core_ports,
        project_id_override=project_id,
        bypass_cache=bypass_cache,
    )
    return ClientV1Envelope(
        data=result,
        meta=build_client_v1_meta(instance_id=_get_instance_id()),
    )
