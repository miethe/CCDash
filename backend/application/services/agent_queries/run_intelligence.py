"""Transport-neutral Research Foundry ``research_runs`` query service (T2-003).

Phase 2 (research-foundry-run-telemetry-v1) — pattern-matched to
``system_metrics.py``: dual-dialect (SQLite/PostgreSQL) SQL is written
directly in this service, because ``backend/db/repositories/research_runs.py``
(T2-001) only exposes ``get_by_run_id``/``get_by_rf_run_id``/
``backfill_from_rf_events`` — no list/page method. Single-run detail reuses
that module's existing ``get_by_run_id`` repository methods rather than
duplicating the lookup; the list page is a small SQL query owned entirely by
this file.

Two entry points, both cursor-paginated / single-lookup and both returning
Pydantic DTOs (never raw ORM/DB rows) so every transport (REST — T2-004,
MCP/CLI — T2-005) can return this service's output verbatim:

  - :meth:`RunIntelligenceQueryService.list_runs` — a page of
    :class:`ResearchRunSummaryDTO` rows for a project, newest-first
    (``last_event_at DESC``), cursor-paginated exactly like
    ``session_detail.py``'s transcript pagination (opaque base64-encoded
    offset; ``next_cursor`` is ``None`` on the last page).
  - :meth:`RunIntelligenceQueryService.get_run_detail` — a single
    :class:`ResearchRunDetailDTO` (superset of the summary DTO with the
    latest-snapshot array fields), plus a ``found`` flag so "no such run"
    is a normal ``status="ok"``/``found=False`` response, never a 500.

AC-2-Field — FE-facing optional-field resilience contract
-----------------------------------------------------------
Every field on these DTOs that is optional at the source (not every RF event
carries every metric) is explicitly ``Optional``/nullable, and is populated
with ``None`` — never ``0``/``""``/``[]`` — when the source column is
``NULL`` or otherwise unavailable. This is the backend half of the R-P2
contract Phase 3 (T3-005) consumes on the FE side. Two fields —
``mode``/``selected_providers`` — are always ``None`` today: RF's spec (PRD
§16.2, FR-12 "Provider Economics") defines them, but the ``research_runs``
rollup schema (T2-001) has no dedicated column for them yet (they exist only
inside individual ``rf_events.raw_payload_json`` blobs, which the rollup
deliberately never joins against per D6 — raw log vs. derived rollup stay
split). The fields are present and nullable now so the FE contract shape is
locked ahead of whichever future phase adds the extraction; this is a
documented "contract state, not a bug" gap, not an oversight.

Run<->session correlation (AC-3)
---------------------------------
``linked_session_id``/``linked_session_ids`` are populated via
``ports.storage.entity_links()`` — ``get_linked_session_ids_for_run``
(detail) / ``get_links_for_many`` (list, batched to avoid N+1) — filtered to
the ``research_run`` link kind (T2-006, ``backend/db/repositories/
entity_graph.py``). Both lookups are wrapped so a run with zero linked
sessions yields the explicit empty list ``[]`` (the AC-3 "no linked session"
resilience state), and any repository error/attribute-missing degrades to the
same empty state rather than raising — this service works whether it ships
before or after T2-006 lands.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import aiosqlite
from pydantic import BaseModel, Field

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.db.repositories.entity_graph import (
    RESEARCH_RUN_LINK_SOURCE_TYPE,
    RESEARCH_RUN_LINK_TARGET_TYPE,
    RESEARCH_RUN_LINK_TYPE,
)
from backend.db.repositories.research_runs import (
    PostgresResearchRunsRepository,
    SqliteResearchRunsRepository,
)
from backend.observability import otel

from ._filters import collect_source_refs, resolve_project_scope
from .cache import memoized_query
from .models import AgentQueryEnvelope

logger = logging.getLogger("ccdash.agent_queries.run_intelligence")

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "ResearchRunSummaryDTO",
    "ResearchRunDetailDTO",
    "ResearchRunListResponseDTO",
    "ResearchRunDetailResponseDTO",
    "RunIntelligenceQueryService",
]

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_LIMIT: int = 50
MAX_LIMIT: int = 200


# ── Cursor helpers (mirrors session_detail.py's opaque offset cursor) ───────

def _encode_cursor(offset: int) -> str:
    """Encode an integer offset as an opaque URL-safe base64 cursor string."""
    raw = json.dumps({"o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    """Decode an opaque cursor string to an integer offset.

    Returns 0 on ``None``, empty string, or any decoding error (resilient —
    an unparseable cursor restarts the page rather than 500ing).
    """
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        payload = json.loads(raw)
        return max(0, int(payload.get("o", 0)))
    except Exception:
        logger.warning("run_intelligence: invalid cursor %r — resetting to offset 0", cursor)
        return 0


# ── Safe scalar coercion helpers ─────────────────────────────────────────────
#
# "unknown == null, never a fabricated default" (research_runs.py module
# docstring) — every helper returns None on missing/unparseable input, never
# 0 / "" / [] / False.

def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return bool(value)


def _json_list_or_none(value: Any) -> list[str] | None:
    """Decode a JSON-array snapshot column; ``None`` in stays ``None`` out.

    A column that was never populated must not be indistinguishable from one
    explicitly set to an empty list, so decoding failures and ``NULL`` both
    return ``None`` rather than ``[]``.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            logger.warning("run_intelligence: failed to decode JSON snapshot column")
            return None
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
        return None
    return None


# ── DTOs ──────────────────────────────────────────────────────────────────────

class ResearchRunSummaryDTO(BaseModel):
    """One ``research_runs`` rollup row (a single list-page item).

    Every metric field that is optional at the source is explicitly
    ``Optional``/nullable (AC-2-Field) — see module docstring for the
    ``mode``/``selected_providers`` "always None today" gap and the
    ``linked_session_id``/``linked_session_ids`` correlation contract.
    """

    run_id: str
    rf_run_id: str | None = None
    project_id: str
    workspace_id: str = "default-local"

    # RF display-only correlation attributes (D2 — never join keys).
    intent_id: str | None = None
    task_node_id: str | None = None
    rf_project: str | None = None

    event_count: int = 0
    first_event_at: str | None = None
    last_event_at: str | None = None

    # Summed metrics.
    queries_executed: int | None = None
    urls_extracted: int | None = None
    useful_source_count: int | None = None
    tokens_estimated: int | None = None
    claims_total: int | None = None
    claims_supported: int | None = None
    claims_mixed: int | None = None
    claims_contradicted: int | None = None
    unsupported_claims: int | None = None
    estimated_cost_usd: float | None = None
    latency_ms: float | None = None

    # Latest-non-null snapshot metrics (rate/score-shaped).
    citation_coverage: float | None = None
    duplicate_rate: float | None = None
    extraction_failure_rate: float | None = None
    quality_score: str | None = None
    drift_score: float | None = None

    # RF search-mode/provider-mix attributes (PRD FR-12, §16.2). Always None
    # today — see module docstring "AC-2-Field" section for the documented
    # rollup-schema gap this is standing in for.
    mode: str | None = None
    selected_providers: list[str] | None = None

    # Governance / human-review rollups.
    governance_sensitivity: str | None = None
    governance_policy_passed: bool | None = None
    human_review_required: bool | None = None
    human_review_status: str | None = None
    human_review_reviewer: str | None = None

    # Reuse-candidate flags.
    reuse_meatywiki_writeback_candidate: bool | None = None
    reuse_skillbom_candidate: bool | None = None
    reuse_reusable_source_pack_candidate: bool | None = None

    # Run<->session correlation (T2-006, AC-3). ``linked_session_ids`` is the
    # explicit resilience state — an empty list means "checked, none found",
    # never coalesced into a bare ``0``/``None``. ``linked_session_id`` is a
    # convenience pointer to the first linked session (``None`` when empty).
    linked_session_id: str | None = None
    linked_session_ids: list[str] = Field(default_factory=list)

    created_at: str | None = None
    updated_at: str | None = None


class ResearchRunDetailDTO(ResearchRunSummaryDTO):
    """Full single-run detail — superset of :class:`ResearchRunSummaryDTO`.

    Adds the latest-snapshot array-shaped fields that are only decoded at
    single-run granularity (omitted from list rows to keep pages lightweight).
    """

    agent_postures: list[str] | None = None
    skillbom_ids: list[str] | None = None
    tools: list[str] | None = None
    input_artifacts: list[str] | None = None
    output_artifacts: list[str] | None = None


class ResearchRunListResponseDTO(AgentQueryEnvelope):
    """Cursor-paginated ``research_runs`` list response."""

    project_id: str
    items: list[ResearchRunSummaryDTO] = Field(default_factory=list)
    cursor: str = ""
    limit: int = DEFAULT_LIMIT
    next_cursor: str | None = None


class ResearchRunDetailResponseDTO(AgentQueryEnvelope):
    """Single-run detail response envelope.

    ``found=False`` (with ``run=None``) is the normal, non-error shape for
    "no such run in this project" — never a 500/exception.
    """

    project_id: str
    run_id: str
    found: bool = False
    run: ResearchRunDetailDTO | None = None


# ── Row → DTO mapping ────────────────────────────────────────────────────────

def _run_row_to_summary(
    row: dict[str, Any], *, linked_session_ids: list[str] | None = None
) -> ResearchRunSummaryDTO:
    linked = linked_session_ids or []
    return ResearchRunSummaryDTO(
        run_id=str(row.get("run_id") or ""),
        rf_run_id=_safe_str_or_none(row.get("rf_run_id")),
        project_id=str(row.get("project_id") or ""),
        workspace_id=str(row.get("workspace_id") or "default-local"),
        intent_id=_safe_str_or_none(row.get("intent_id")),
        task_node_id=_safe_str_or_none(row.get("task_node_id")),
        rf_project=_safe_str_or_none(row.get("rf_project")),
        event_count=_safe_int_or_none(row.get("event_count")) or 0,
        first_event_at=_safe_str_or_none(row.get("first_event_at")),
        last_event_at=_safe_str_or_none(row.get("last_event_at")),
        queries_executed=_safe_int_or_none(row.get("total_queries_executed")),
        urls_extracted=_safe_int_or_none(row.get("total_urls_extracted")),
        useful_source_count=_safe_int_or_none(row.get("total_useful_source_count")),
        tokens_estimated=_safe_int_or_none(row.get("total_tokens_estimated")),
        claims_total=_safe_int_or_none(row.get("total_claims_total")),
        claims_supported=_safe_int_or_none(row.get("total_claims_supported")),
        claims_mixed=_safe_int_or_none(row.get("total_claims_mixed")),
        claims_contradicted=_safe_int_or_none(row.get("total_claims_contradicted")),
        unsupported_claims=_safe_int_or_none(row.get("total_unsupported_claims")),
        estimated_cost_usd=_safe_float_or_none(row.get("total_estimated_cost_usd")),
        latency_ms=_safe_float_or_none(row.get("total_latency_ms")),
        citation_coverage=_safe_float_or_none(row.get("citation_coverage")),
        duplicate_rate=_safe_float_or_none(row.get("duplicate_rate")),
        extraction_failure_rate=_safe_float_or_none(row.get("extraction_failure_rate")),
        quality_score=_safe_str_or_none(row.get("quality_score")),
        drift_score=_safe_float_or_none(row.get("drift_score")),
        mode=None,
        selected_providers=None,
        governance_sensitivity=_safe_str_or_none(row.get("governance_sensitivity")),
        governance_policy_passed=_bool_or_none(row.get("governance_policy_passed")),
        human_review_required=_bool_or_none(row.get("human_review_required")),
        human_review_status=_safe_str_or_none(row.get("human_review_status")),
        human_review_reviewer=_safe_str_or_none(row.get("human_review_reviewer")),
        reuse_meatywiki_writeback_candidate=_bool_or_none(
            row.get("reuse_meatywiki_writeback_candidate")
        ),
        reuse_skillbom_candidate=_bool_or_none(row.get("reuse_skillbom_candidate")),
        reuse_reusable_source_pack_candidate=_bool_or_none(
            row.get("reuse_reusable_source_pack_candidate")
        ),
        linked_session_id=linked[0] if linked else None,
        linked_session_ids=linked,
        created_at=_safe_str_or_none(row.get("created_at")),
        updated_at=_safe_str_or_none(row.get("updated_at")),
    )


def _run_row_to_detail(
    row: dict[str, Any], *, linked_session_ids: list[str] | None = None
) -> ResearchRunDetailDTO:
    summary = _run_row_to_summary(row, linked_session_ids=linked_session_ids)
    return ResearchRunDetailDTO(
        **summary.model_dump(),
        agent_postures=_json_list_or_none(row.get("agent_postures_json")),
        skillbom_ids=_json_list_or_none(row.get("skillbom_ids_json")),
        tools=_json_list_or_none(row.get("tools_json")),
        input_artifacts=_json_list_or_none(row.get("input_artifacts_json")),
        output_artifacts=_json_list_or_none(row.get("output_artifacts_json")),
    )


# ── Run<->session correlation lookups (T2-006, AC-3) ────────────────────────

async def _fetch_linked_session_ids_for_run(ports: CorePorts, run_id: str) -> list[str]:
    """Best-effort single-run correlation lookup.

    Degrades to ``[]`` (never raises) when ``entity_links()`` does not expose
    ``get_linked_session_ids_for_run`` yet, or the lookup otherwise fails —
    an empty list is the correct AC-3 "no linked session" resilience state
    either way.
    """
    try:
        entity_links = ports.storage.entity_links()
        getter = getattr(entity_links, "get_linked_session_ids_for_run", None)
        if getter is None:
            return []
        ids = await getter(run_id)
        return [str(i) for i in ids if str(i or "").strip()]
    except Exception:
        logger.debug(
            "run_intelligence: linked-session lookup failed for run_id=%s",
            run_id,
            exc_info=True,
        )
        return []


async def _fetch_linked_session_ids_for_runs(
    ports: CorePorts, run_ids: list[str]
) -> dict[str, list[str]]:
    """Batched correlation lookup for a list page (avoids one query per row)."""
    if not run_ids:
        return {}
    try:
        entity_links = ports.storage.entity_links()
        getter = getattr(entity_links, "get_links_for_many", None)
        if getter is None:
            return {}
        by_run: dict[str, list[dict[str, Any]]] = await getter(
            RESEARCH_RUN_LINK_SOURCE_TYPE, run_ids
        )
    except Exception:
        logger.debug("run_intelligence: batched linked-session lookup failed", exc_info=True)
        return {}

    result: dict[str, list[str]] = {}
    for run_id, rows in by_run.items():
        ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if (
                row.get("link_type") == RESEARCH_RUN_LINK_TYPE
                and row.get("target_type") == RESEARCH_RUN_LINK_TARGET_TYPE
            ):
                sid = str(row.get("target_id") or "").strip()
                if sid and sid not in seen:
                    seen.add(sid)
                    ids.append(sid)
        result[run_id] = ids
    return result


# ── List-page SQL (dual-dialect; no repository list method exists yet) ─────

async def _fetch_research_runs_page(
    db: Any, project_id: str, *, limit: int, offset: int
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` ``research_runs`` rows for *project_id*.

    Dual-path for SQLite (aiosqlite) and PostgreSQL (asyncpg), following the
    pattern established in ``system_metrics.py``. Ordered newest-first
    (``last_event_at DESC``) with ``run_id`` as a stable tiebreaker so paging
    stays deterministic across calls.
    """
    sqlite_sql = (
        "SELECT * FROM research_runs WHERE project_id = ? "
        "ORDER BY last_event_at DESC, run_id ASC LIMIT ? OFFSET ?"  # noqa: S608
    )
    pg_sql = (
        "SELECT * FROM research_runs WHERE project_id = $1 "
        "ORDER BY last_event_at DESC, run_id ASC LIMIT $2 OFFSET $3"  # noqa: S608
    )

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (project_id, limit, offset)) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql, project_id, limit, offset)
    return [dict(r) for r in rows]


# ── Cache param extractors ───────────────────────────────────────────────────

def _run_list_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id": project_id_override or "",
        "cursor": cursor or "",
        "limit": min(max(int(limit or DEFAULT_LIMIT), 1), MAX_LIMIT),
    }


def _run_detail_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    run_id: str,
    *,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_id": project_id_override or "", "run_id": str(run_id or "")}


# ── Service ──────────────────────────────────────────────────────────────────

class RunIntelligenceQueryService:
    """Transport-neutral query surface over the ``research_runs`` rollup.

    Mirrors the structural shape of ``system_metrics.py``/
    ``artifact_intelligence.py``: no REST/MCP/CLI-specific logic lives here —
    every transport (T2-004 REST, T2-005 MCP/CLI) must call these methods and
    return the resulting DTOs verbatim.
    """

    @memoized_query("run_intelligence_list", param_extractor=_run_list_params)
    async def list_runs(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIMIT,
        bypass_cache: bool = False,  # noqa: ARG002 - consumed by the decorator; kept for REST parity
    ) -> ResearchRunListResponseDTO:
        """Return a cursor-paginated page of ``research_runs`` rollup rows."""
        scope = resolve_project_scope(context, ports, project_id_override)
        project_id = (
            project_id_override
            or getattr(getattr(context, "project", None), "project_id", "")
            or ""
        )
        eff_limit = min(max(int(limit or DEFAULT_LIMIT), 1), MAX_LIMIT)

        if scope is None:
            return ResearchRunListResponseDTO(
                status="error",
                project_id=project_id,
                cursor=cursor or "",
                limit=eff_limit,
                source_refs=collect_source_refs(project_id),
            )

        if not config.CCDASH_RF_TELEMETRY_ENABLED:
            return ResearchRunListResponseDTO(
                status="ok",
                project_id=scope.project.id,
                items=[],
                cursor=cursor or "",
                limit=eff_limit,
                next_cursor=None,
                source_refs=collect_source_refs(scope.project.id),
            )

        offset = _decode_cursor(cursor)

        with otel.start_span(
            "run_intelligence.list_runs",
            {"project_id": scope.project.id, "limit": eff_limit},
        ):
            try:
                db = ports.storage.db
                rows = await _fetch_research_runs_page(
                    db, scope.project.id, limit=eff_limit + 1, offset=offset
                )
            except Exception:
                logger.exception(
                    "run_intelligence: list_runs failed project=%s", scope.project.id
                )
                return ResearchRunListResponseDTO(
                    status="error",
                    project_id=scope.project.id,
                    cursor=cursor or "",
                    limit=eff_limit,
                    source_refs=collect_source_refs(scope.project.id),
                )

            has_more = len(rows) > eff_limit
            page_rows = rows[:eff_limit]
            run_ids = [str(r.get("run_id") or "") for r in page_rows]
            linked_by_run = await _fetch_linked_session_ids_for_runs(ports, run_ids)

            items = [
                _run_row_to_summary(
                    row,
                    linked_session_ids=linked_by_run.get(str(row.get("run_id") or "")),
                )
                for row in page_rows
            ]

            next_cursor = _encode_cursor(offset + eff_limit) if has_more else None

            return ResearchRunListResponseDTO(
                status="ok",
                project_id=scope.project.id,
                items=items,
                cursor=_encode_cursor(offset),
                limit=eff_limit,
                next_cursor=next_cursor,
                source_refs=collect_source_refs(scope.project.id, run_ids),
            )

    @memoized_query("run_intelligence_detail", param_extractor=_run_detail_params)
    async def get_run_detail(
        self,
        context: RequestContext,
        ports: CorePorts,
        run_id: str,
        *,
        project_id_override: str | None = None,
        bypass_cache: bool = False,  # noqa: ARG002 - consumed by the decorator; kept for REST parity
    ) -> ResearchRunDetailResponseDTO:
        """Return a single ``research_runs`` row plus its linked sessions.

        "No such run" (missing, or belonging to a different project) is a
        normal ``status="ok"``/``found=False`` response, never a 500.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        project_id = (
            project_id_override
            or getattr(getattr(context, "project", None), "project_id", "")
            or ""
        )
        run_id_norm = str(run_id or "").strip()

        if scope is None:
            return ResearchRunDetailResponseDTO(
                status="error",
                project_id=project_id,
                run_id=run_id_norm,
                found=False,
                source_refs=collect_source_refs(project_id, run_id_norm),
            )

        if not run_id_norm:
            return ResearchRunDetailResponseDTO(
                status="error",
                project_id=scope.project.id,
                run_id=run_id_norm,
                found=False,
                source_refs=collect_source_refs(scope.project.id),
            )

        if not config.CCDASH_RF_TELEMETRY_ENABLED:
            return ResearchRunDetailResponseDTO(
                status="ok",
                project_id=scope.project.id,
                run_id=run_id_norm,
                found=False,
                source_refs=collect_source_refs(scope.project.id, run_id_norm),
            )

        with otel.start_span(
            "run_intelligence.get_run_detail",
            {"project_id": scope.project.id, "run_id": run_id_norm},
        ):
            try:
                db = ports.storage.db
                repo: Any = (
                    SqliteResearchRunsRepository(db)
                    if isinstance(db, aiosqlite.Connection)
                    else PostgresResearchRunsRepository(db)
                )
                row = await repo.get_by_run_id(run_id_norm)
            except Exception:
                logger.exception(
                    "run_intelligence: get_run_detail failed run_id=%s", run_id_norm
                )
                return ResearchRunDetailResponseDTO(
                    status="error",
                    project_id=scope.project.id,
                    run_id=run_id_norm,
                    found=False,
                    source_refs=collect_source_refs(scope.project.id, run_id_norm),
                )

            if row is None or str(row.get("project_id") or "") != scope.project.id:
                # Missing, or belongs to a different project — never leak a
                # cross-project row through a same-run_id coincidence.
                return ResearchRunDetailResponseDTO(
                    status="ok",
                    project_id=scope.project.id,
                    run_id=run_id_norm,
                    found=False,
                    source_refs=collect_source_refs(scope.project.id, run_id_norm),
                )

            linked_session_ids = await _fetch_linked_session_ids_for_run(ports, run_id_norm)
            detail = _run_row_to_detail(row, linked_session_ids=linked_session_ids)

            return ResearchRunDetailResponseDTO(
                status="ok",
                project_id=scope.project.id,
                run_id=run_id_norm,
                found=True,
                run=detail,
                source_refs=collect_source_refs(
                    scope.project.id, run_id_norm, linked_session_ids
                ),
            )
