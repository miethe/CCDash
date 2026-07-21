"""Concrete repositories for the ``research_runs`` derived rollup table.

``research_runs`` (T2-001, research-foundry-run-telemetry v1, v41) derives one
row per Research Foundry run from the raw, append-only ``rf_events`` log
(T1-001; ``backend/db/repositories/rf_events.py``). Per D6 (PRD decisions
block), persistence is deliberately split into two tables: ``rf_events`` is
the raw log, ``research_runs`` is the derived rollup — never the other way
around, and never merged into one table.

UUID minting contract (D2, FR-6)
=================================
RF's own ``run_id`` (spec §11.2) is typed as a generic ``string``, not
guaranteed to be a UUID4. ``research_runs.run_id`` is CCDash's canonical
primary/join key and MUST always be a genuine UUID4 string:

  - When RF's raw ``run_id`` already parses as a UUID4, it IS the canonical
    ``run_id`` verbatim (lower-cased) — no separate display column is needed.
  - When RF's raw ``run_id`` does NOT parse as a UUID4 (the common case — RF
    mostly emits semantic slugs), CCDash mints a UUID and stores RF's raw
    value in the separate ``rf_run_id`` display column. RF's non-UUID ids
    never become a primary/join key (this is the same "display-only
    attribute, never a join key" discipline D2 applies to ``intent_id``/
    ``task_node_id`` against ``aos_correlation.py`` — see
    ``backend/services/aos_correlation.py``, zero changes, hard boundary).

Minting is **deterministic** (``uuid.uuid5`` over a fixed namespace and the
``(workspace_id, project_id, raw_run_id)`` triple), not a fresh ``uuid.uuid4()``
per call. This is load-bearing for two reasons:

  1. The T2-001 acceptance criterion requires the rollup to be "derivable from
     seeded ``rf_events`` fixtures with zero live RF traffic" — re-running
     derivation against the same fixtures (e.g. in a test, or after a crash
     mid-batch) must always converge on the same ``research_runs`` row rather
     than minting a new UUID (and thus a new row) every time.
  2. Two events for the same RF run processed concurrently by different
     ingest requests independently compute the identical minted ``run_id``
     with no lookup-then-insert round trip and no race to "claim" the id.

Aggregation semantics (upsert SET clause)
==========================================
One ``research_runs`` row is upserted per rf_events row processed
(``upsert_from_event``). The merge semantics per column group:

  - ``total_*`` metric columns: SUMMED across every folded-in event, using
    ``COALESCE(<col>, 0) + COALESCE(excluded.<col>, 0)``. This means a
    ``total_*`` value of exactly ``0`` is ambiguous between "every event that
    contributed reported a literal zero" and "no event ever reported this
    metric" — the SQL ``NULL + x = NULL`` footgun is avoided deliberately at
    the cost of that distinction. Callers needing to disambiguate should
    consult ``event_count`` or the underlying ``rf_events`` rows directly.
    This tradeoff is intentionally left to the ``run_intelligence.py`` query
    service (T2-003) to resolve for its DTO's nullability contract
    (AC-2-Field) if it matters there.
  - rate/score-shaped columns (``citation_coverage``, ``duplicate_rate``,
    ``extraction_failure_rate``, ``quality_score``, ``drift_score``) and
    governance/human-review/display snapshot columns: "latest wins" via
    ``COALESCE(excluded.<col>, <col>)`` — the newest *processed* event's
    non-null value overwrites the stored snapshot. Note this is
    last-*processed*-wins, not strictly last-by-timestamp-wins, if events
    ever arrive out of order.
  - boolean flag columns (``human_review_required``,
    ``reuse_*_candidate``): OR'd via SQL's three-valued-logic ``OR`` operator
    (``excluded.<col> OR <col>``) — NULL OR NULL stays NULL (metric never
    reported), NULL OR TRUE is TRUE, so a single "yes" anywhere in the run
    wins permanently.
  - ``first_event_at``/``last_event_at``: min/max across every folded-in
    event's ``event_timestamp`` (backend-specific scalar function — SQLite's
    ``min()``/``max()`` vs Postgres's ``LEAST()``/``GREATEST()``).
  - JSON snapshot columns (``agent_postures_json``, ``skillbom_ids_json``,
    ``tools_json``, ``input_artifacts_json``, ``output_artifacts_json``):
    latest-wins snapshot, not a merged/deduped union.

Events without a ``run_id`` at all (RF's ``run_id`` is optional) are skipped
entirely by ``build_research_run_delta`` (returns ``None``) — there is no run
identity to roll up, and inventing one would fabricate a default the RF
payload never supplied (project convention: unknown == null, never a
fabricated default).

Both repository implementations below build their upsert statements from the
same ordered ``RESEARCH_RUNS_COLUMNS`` contract so the two DDLs, the two
INSERT column lists, and the two ON CONFLICT SET clauses cannot silently
drift apart (ADR-007 dual-DDL parity discipline) — mirrors
``backend/db/repositories/rf_events.py`` exactly.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Mapping

import aiosqlite

logger = logging.getLogger("ccdash.db.research_runs")


# ── UUID4 detection + deterministic minting (D2, FR-6) ──────────────────────

_UUID4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

# Fixed namespace for deterministic uuid5 minting (see module docstring for
# why this must be deterministic rather than a fresh uuid4() per call). This
# value is arbitrary but MUST NEVER change once shipped -- changing it would
# re-mint every previously-derived non-UUID4 run's canonical run_id, orphaning
# any entity_links rows (T2-006) already keyed on the old value.
RESEARCH_RUN_ID_NAMESPACE = uuid.UUID("6f2f8c2a-6c39-4e6a-9e1f-8f7f2b9a5b10")


def is_uuid4(value: str) -> bool:
    """Return True when *value* matches the canonical UUID4 string shape."""
    return bool(_UUID4_RE.match(value.strip()))


def resolve_run_id(
    raw_run_id: str,
    *,
    workspace_id: str,
    project_id: str,
) -> tuple[str, str | None]:
    """Resolve RF's raw ``run_id`` string to CCDash's canonical join key.

    Returns ``(canonical_run_id, rf_run_id_display)``:

      - *raw_run_id* already parses as a UUID4 -> ``(raw_run_id.lower(), None)``.
        RF's value IS the canonical id; no separate display column is needed.
      - *raw_run_id* does NOT parse as a UUID4 -> a CCDash UUID is
        deterministically minted and *raw_run_id* (stripped, original casing)
        is returned as the ``rf_run_id`` display value.
    """
    normalized = raw_run_id.strip()
    if is_uuid4(normalized):
        return normalized.lower(), None
    minted = uuid.uuid5(
        RESEARCH_RUN_ID_NAMESPACE,
        f"{workspace_id}:{project_id}:{normalized}",
    )
    return str(minted), normalized


# ── Shared column contract ───────────────────────────────────────────────────
#
# Ordered list of every column written by an upsert (excludes ``created_at``/
# ``updated_at``, which the DDL defaults server-side on insert and the SET
# clause below sets explicitly to "now" on conflict).

RESEARCH_RUNS_COLUMNS: tuple[str, ...] = (
    "run_id",
    "workspace_id",
    "project_id",
    "rf_run_id",
    "intent_id",
    "task_node_id",
    "rf_project",
    "event_count",
    "first_event_at",
    "last_event_at",
    "total_queries_executed",
    "total_urls_extracted",
    "total_useful_source_count",
    "total_tokens_estimated",
    "total_claims_total",
    "total_claims_supported",
    "total_claims_mixed",
    "total_claims_contradicted",
    "total_unsupported_claims",
    "total_estimated_cost_usd",
    "total_latency_ms",
    "citation_coverage",
    "duplicate_rate",
    "extraction_failure_rate",
    "quality_score",
    "drift_score",
    "governance_sensitivity",
    "governance_policy_passed",
    "human_review_required",
    "human_review_status",
    "human_review_reviewer",
    "reuse_meatywiki_writeback_candidate",
    "reuse_skillbom_candidate",
    "reuse_reusable_source_pack_candidate",
    "agent_postures_json",
    "skillbom_ids_json",
    "tools_json",
    "input_artifacts_json",
    "output_artifacts_json",
)

# Columns that are SUMMED (via COALESCE(col,0) + COALESCE(excluded.col,0)) on
# conflict -- see module docstring "Aggregation semantics".
_SUMMED_COLUMNS: tuple[str, ...] = (
    "total_queries_executed",
    "total_urls_extracted",
    "total_useful_source_count",
    "total_tokens_estimated",
    "total_claims_total",
    "total_claims_supported",
    "total_claims_mixed",
    "total_claims_contradicted",
    "total_unsupported_claims",
    "total_estimated_cost_usd",
    "total_latency_ms",
)

# Columns that are OR'd (three-valued SQL logic) on conflict.
_OR_COLUMNS: tuple[str, ...] = (
    "human_review_required",
    "reuse_meatywiki_writeback_candidate",
    "reuse_skillbom_candidate",
    "reuse_reusable_source_pack_candidate",
)

# Columns that are "latest non-null wins" (COALESCE(excluded.col, col)) on
# conflict. rf_run_id is intentionally the OPPOSITE direction -- once minted/
# recorded it must never change out from under an existing row -- so it is
# handled as its own special case rather than folded into this list.
_LATEST_WINS_COLUMNS: tuple[str, ...] = (
    "intent_id",
    "task_node_id",
    "rf_project",
    "citation_coverage",
    "duplicate_rate",
    "extraction_failure_rate",
    "quality_score",
    "drift_score",
    "governance_sensitivity",
    "governance_policy_passed",
    "human_review_status",
    "human_review_reviewer",
    "agent_postures_json",
    "skillbom_ids_json",
    "tools_json",
    "input_artifacts_json",
    "output_artifacts_json",
)


def _row_values(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return *row*'s values in ``RESEARCH_RUNS_COLUMNS`` order."""
    return tuple(row.get(col) for col in RESEARCH_RUNS_COLUMNS)


def build_research_run_delta(
    event_row: Mapping[str, Any],
    *,
    workspace_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    """Map a single ``rf_events``-shaped row onto a ``research_runs`` delta.

    *event_row* uses the same key names as
    ``backend/db/repositories/rf_events.py::RF_EVENTS_COLUMNS`` (i.e. either
    the in-memory dict built by ``RfEventsIngestService._payload_to_row``, or
    a real ``rf_events`` DB row converted to a plain ``dict``).

    Returns ``None`` when *event_row* carries no ``run_id`` at all -- there is
    no run identity to roll up for that event (RF's ``run_id`` is optional;
    this is a contract state, not a bug -- see module docstring).
    """
    raw_run_id = event_row.get("run_id")
    if not raw_run_id:
        return None

    canonical_run_id, rf_run_id_display = resolve_run_id(
        str(raw_run_id), workspace_id=workspace_id, project_id=project_id
    )

    event_timestamp = event_row.get("event_timestamp")

    return {
        "run_id": canonical_run_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "rf_run_id": rf_run_id_display,
        "intent_id": event_row.get("intent_id"),
        "task_node_id": event_row.get("task_node_id"),
        "rf_project": event_row.get("rf_project"),
        "event_count": 1,
        "first_event_at": event_timestamp,
        "last_event_at": event_timestamp,
        "total_queries_executed": event_row.get("metric_queries_executed"),
        "total_urls_extracted": event_row.get("metric_urls_extracted"),
        "total_useful_source_count": event_row.get("metric_useful_source_count"),
        "total_tokens_estimated": event_row.get("metric_tokens_estimated"),
        "total_claims_total": event_row.get("metric_claims_total"),
        "total_claims_supported": event_row.get("metric_claims_supported"),
        "total_claims_mixed": event_row.get("metric_claims_mixed"),
        "total_claims_contradicted": event_row.get("metric_claims_contradicted"),
        "total_unsupported_claims": event_row.get("metric_unsupported_claims"),
        "total_estimated_cost_usd": event_row.get("metric_estimated_cost_usd"),
        "total_latency_ms": event_row.get("metric_latency_ms"),
        "citation_coverage": event_row.get("metric_citation_coverage"),
        "duplicate_rate": event_row.get("metric_duplicate_rate"),
        "extraction_failure_rate": event_row.get("metric_extraction_failure_rate"),
        "quality_score": event_row.get("metric_quality_score"),
        "drift_score": event_row.get("metric_drift_score"),
        "governance_sensitivity": event_row.get("governance_sensitivity"),
        "governance_policy_passed": event_row.get("governance_policy_passed"),
        "human_review_required": event_row.get("human_review_required"),
        "human_review_status": event_row.get("human_review_status"),
        "human_review_reviewer": event_row.get("human_review_reviewer"),
        "reuse_meatywiki_writeback_candidate": event_row.get("reuse_meatywiki_writeback_candidate"),
        "reuse_skillbom_candidate": event_row.get("reuse_skillbom_candidate"),
        "reuse_reusable_source_pack_candidate": event_row.get("reuse_reusable_source_pack_candidate"),
        "agent_postures_json": event_row.get("agent_postures_json"),
        "skillbom_ids_json": event_row.get("skillbom_ids_json"),
        "tools_json": event_row.get("tools_json"),
        "input_artifacts_json": event_row.get("input_artifacts_json"),
        "output_artifacts_json": event_row.get("output_artifacts_json"),
    }


def _build_set_clause(*, sum_fn: str, min_fn: str, max_fn: str) -> str:
    """Build the ON CONFLICT DO UPDATE SET clause shared by both backends.

    *sum_fn* is unused (summation is always plain ``+``); *min_fn*/*max_fn*
    are the backend-specific scalar functions used for
    ``first_event_at``/``last_event_at`` (SQLite: ``min``/``max``; Postgres:
    ``LEAST``/``GREATEST``).
    """
    del sum_fn  # summation itself is backend-portable (+); kept for symmetry
    parts: list[str] = [
        "workspace_id = excluded.workspace_id",
        "project_id = excluded.project_id",
        # rf_run_id: once recorded, never overwritten by a later delta -- it
        # is deterministic per (workspace_id, project_id, raw run id) so this
        # only matters defensively.
        "rf_run_id = COALESCE(research_runs.rf_run_id, excluded.rf_run_id)",
        f"first_event_at = {min_fn}(research_runs.first_event_at, excluded.first_event_at)",
        f"last_event_at = {max_fn}(research_runs.last_event_at, excluded.last_event_at)",
        "event_count = research_runs.event_count + excluded.event_count",
    ]
    for col in _SUMMED_COLUMNS:
        parts.append(
            f"{col} = COALESCE(research_runs.{col}, 0) + COALESCE(excluded.{col}, 0)"
        )
    for col in _OR_COLUMNS:
        parts.append(f"{col} = excluded.{col} OR research_runs.{col}")
    for col in _LATEST_WINS_COLUMNS:
        parts.append(f"{col} = COALESCE(excluded.{col}, research_runs.{col})")
    parts.append("updated_at = {now_expr}")
    return ",\n                ".join(parts)


# ── SQLite ──────────────────────────────────────────────────────────────────

_SQLITE_SET_CLAUSE = _build_set_clause(sum_fn="+", min_fn="min", max_fn="max").format(
    now_expr="datetime('now')"
)


class SqliteResearchRunsRepository:
    """aiosqlite-backed writer/reader for ``research_runs``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def upsert_from_event(
        self,
        event_row: Mapping[str, Any],
        *,
        workspace_id: str,
        project_id: str,
    ) -> str | None:
        """Derive and upsert one ``research_runs`` row from a single rf_events row.

        Returns the canonical ``run_id`` that was upserted, or ``None`` when
        *event_row* carried no ``run_id`` (nothing to roll up).
        """
        delta = build_research_run_delta(
            event_row, workspace_id=workspace_id, project_id=project_id
        )
        if delta is None:
            return None
        await self.upsert_delta(delta)
        return delta["run_id"]

    async def upsert_delta(self, delta: Mapping[str, Any]) -> None:
        """Upsert a pre-built ``RESEARCH_RUNS_COLUMNS``-shaped delta row."""
        columns_sql = ", ".join(RESEARCH_RUNS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(RESEARCH_RUNS_COLUMNS))
        await self.db.execute(
            f"INSERT INTO research_runs ({columns_sql}) VALUES ({placeholders_sql}) "
            f"ON CONFLICT(run_id) DO UPDATE SET\n                {_SQLITE_SET_CLAUSE}",
            _row_values(delta),
        )
        await self.db.commit()

    async def get_by_run_id(self, run_id: str) -> dict[str, Any] | None:
        cursor = await self.db.execute(
            "SELECT * FROM research_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_by_rf_run_id(
        self, rf_run_id: str, *, project_id: str | None = None
    ) -> dict[str, Any] | None:
        if project_id is not None:
            cursor = await self.db.execute(
                "SELECT * FROM research_runs WHERE rf_run_id = ? AND project_id = ?",
                (rf_run_id, project_id),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM research_runs WHERE rf_run_id = ?", (rf_run_id,)
            )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def backfill_from_rf_events(
        self, *, project_id: str, workspace_id: str = "default-local"
    ) -> int:
        """Derive/upsert ``research_runs`` rows from already-persisted ``rf_events``.

        This is the concrete "zero live RF traffic" derivation path named by
        the T2-001 acceptance criterion: it reads whatever ``rf_events`` rows
        are already seeded for *project_id*/*workspace_id* (e.g. by a test
        fixture, or by the T1-003 ingest endpoint having already run) and
        folds each one into ``research_runs`` via ``upsert_from_event``, in
        ``event_timestamp`` order.

        Idempotency: this is a scoped delete + full re-derive (mirrors the
        ``rebuild_for_entities`` / "incremental link rebuild" convention
        already used by ``backend/db/repositories/entity_graph.py`` — scoped
        delete, no accumulation across calls) rather than an incremental
        accumulate. ``upsert_from_event``'s SET clause sums metrics per
        *call*, so blindly re-folding the same already-folded rf_events rows
        a second time would double-count every total_* column — this method
        clears this project/workspace's ``research_runs`` rows first so
        calling it twice on the same ``rf_events`` fixtures always converges
        on the identical result, satisfying the T2-001 AC's "derivable ...
        with zero live RF traffic" contract as a safely re-runnable
        operation, not a one-shot migration.

        Returns the number of ``rf_events`` rows processed (including any
        that were skipped because they carried no ``run_id`` — see
        ``build_research_run_delta``).
        """
        await self.db.execute(
            "DELETE FROM research_runs WHERE project_id = ? AND workspace_id = ?",
            (project_id, workspace_id),
        )
        cursor = await self.db.execute(
            "SELECT * FROM rf_events WHERE project_id = ? AND workspace_id = ? "
            "ORDER BY event_timestamp ASC",
            (project_id, workspace_id),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await self.upsert_from_event(
                dict(row), workspace_id=workspace_id, project_id=project_id
            )
        return len(rows)


# ── PostgreSQL ──────────────────────────────────────────────────────────────

_POSTGRES_SET_CLAUSE = _build_set_clause(
    sum_fn="+", min_fn="LEAST", max_fn="GREATEST"
).format(now_expr="CURRENT_TIMESTAMP")


class PostgresResearchRunsRepository:
    """asyncpg-backed writer/reader for ``research_runs``."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def upsert_from_event(
        self,
        event_row: Mapping[str, Any],
        *,
        workspace_id: str,
        project_id: str,
    ) -> str | None:
        delta = build_research_run_delta(
            event_row, workspace_id=workspace_id, project_id=project_id
        )
        if delta is None:
            return None
        await self.upsert_delta(delta)
        return delta["run_id"]

    async def upsert_delta(self, delta: Mapping[str, Any]) -> None:
        columns_sql = ", ".join(RESEARCH_RUNS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(RESEARCH_RUNS_COLUMNS) + 1))
        await self.db.execute(
            f"INSERT INTO research_runs ({columns_sql}) VALUES ({placeholders_sql}) "
            f"ON CONFLICT(run_id) DO UPDATE SET\n                {_POSTGRES_SET_CLAUSE}",
            *_row_values(delta),
        )

    async def get_by_run_id(self, run_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM research_runs WHERE run_id = $1", run_id
        )
        return dict(row) if row else None

    async def get_by_rf_run_id(
        self, rf_run_id: str, *, project_id: str | None = None
    ) -> dict[str, Any] | None:
        if project_id is not None:
            row = await self.db.fetchrow(
                "SELECT * FROM research_runs WHERE rf_run_id = $1 AND project_id = $2",
                rf_run_id,
                project_id,
            )
        else:
            row = await self.db.fetchrow(
                "SELECT * FROM research_runs WHERE rf_run_id = $1", rf_run_id
            )
        return dict(row) if row else None

    async def backfill_from_rf_events(
        self, *, project_id: str, workspace_id: str = "default-local"
    ) -> int:
        """Derive/upsert ``research_runs`` rows from already-persisted ``rf_events``.

        See ``SqliteResearchRunsRepository.backfill_from_rf_events`` for the
        full idempotency contract (scoped delete + full re-derive); identical
        behavior here against an asyncpg connection/pool.
        """
        await self.db.execute(
            "DELETE FROM research_runs WHERE project_id = $1 AND workspace_id = $2",
            project_id,
            workspace_id,
        )
        rows = await self.db.fetch(
            "SELECT * FROM rf_events WHERE project_id = $1 AND workspace_id = $2 "
            "ORDER BY event_timestamp ASC",
            project_id,
            workspace_id,
        )
        for row in rows:
            await self.upsert_from_event(
                dict(row), workspace_id=workspace_id, project_id=project_id
            )
        return len(rows)


__all__ = [
    "RESEARCH_RUNS_COLUMNS",
    "RESEARCH_RUN_ID_NAMESPACE",
    "is_uuid4",
    "resolve_run_id",
    "build_research_run_delta",
    "SqliteResearchRunsRepository",
    "PostgresResearchRunsRepository",
]
