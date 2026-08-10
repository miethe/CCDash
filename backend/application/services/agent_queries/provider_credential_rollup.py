"""Cross-project per-credential spend/token/session rollup service (M3).

Answers "how much did credential X cost, and how much did it do" as a single
read, aggregated across every registered project (ADR-006), following the
declared rotation lineage on ``provider_credentials.rotated_from_id`` so a
rotated key reads as one continuous series rather than two.

Transport-neutral: no FastAPI import, no router wiring. REST + the capability
string are a separate task; this module is meant to be called directly by a
router, the CLI, or the MCP server the same way
``backend/application/services/agent_queries/system_metrics.py`` is.

THE CORRECTNESS CORE — read before touching this file
-----------------------------------------------------
``sessions.ica_spend_delta`` is populated **only** when
``sessions.ica_spend_attribution == 'attributed'`` (see
``backend/parsers/ica_spend.py``'s ``decide_attribution`` — every other verdict
stores NULL rather than dividing a shared-key delta among sessions that didn't
individually earn it). Summing over the other verdicts anyway does not error —
it silently produces a plausible-looking wrong number. That is the feature's
sharpest failure mode, and the plan explicitly prefers making the wrong thing
*unrepresentable* over guarding each call site individually.

This module makes it unrepresentable by construction:

* :func:`_split_by_attribution` is the ONE place in this module that reads
  ``ica_spend_attribution`` to decide inclusion. It returns two *disjoint*
  lists — ``attributed`` and ``excluded`` — and nothing downstream re-derives
  that split.
* :func:`_sum_attributed_spend` is the ONE place in this module that reads
  ``ica_spend_delta`` and adds it to a running total. It takes only the
  ``attributed`` list — there is no parameter, flag, or code path that lets a
  caller hand it the excluded list. Grep the module for ``ica_spend_delta``:
  every read site funnels through this one function.
* The excluded rows are surfaced (opt-in, via ``include_unattributed=True``)
  as raw :class:`ExcludedSessionEntry` records carrying their attribution
  token and (always-NULL-for-non-attributed, by the v51 contract) delta —
  never folded into a second "excluded total" that a future caller could
  mistake for spend and add to the real total.
* Token and session counts are computed from the FULL row set (attributed +
  excluded) via separate helpers that never consult
  ``ica_spend_attribution`` at all — getting this backwards (counting only
  attributed sessions, or excluding unattributed spend from token counts) is
  the mirror-image silent-wrong-answer bug the plan calls out explicitly.

Periodic windowing (``since``/``until``) is layered on top of that choke
point, not around it: :func:`_filter_rows_by_window` is the ONE place that
narrows ``all_rows`` by ``started_at``, and it runs BEFORE the rows are
bucketed into series and handed to :func:`_split_by_attribution`. Every row
that reaches ``_split_by_attribution``/``_sum_attributed_spend`` has already
passed the window check (or no window was requested, in which case nothing
is filtered and behaviour is byte-for-byte the pre-windowing cumulative
result). There is deliberately no second summation path that reads
``ica_spend_delta`` "within a window" — windowed spend is just attributed
spend computed over a pre-narrowed row set, so it inherits the exclusion
automatically instead of needing to re-implement it.

An attribution token outside the closed vocabulary in
``backend/parsers/ica_spend.py`` (the vocabulary may grow) is treated
identically to any other non-``attributed`` token: excluded from spend,
counted, never raises.

Rotation lineage
-----------------
``provider_credentials.rotated_from_id`` is a DECLARED pointer (per M2 — never
inferred). Two credentials merge into one series only when a stored pointer
says so; two credentials with no declared pointer between them stay two
series, which is the *correct* answer, not a missing feature. Grouping is
computed with a union-find over the ``rotated_from_id`` edges
(:func:`_group_credentials_by_series`), which is cycle-safe by construction —
unioning two already-connected nodes is a no-op, not a re-traversal, so a
malformed cycle in the declared data cannot hang or blow the stack.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_provider_identity
from backend.observability import otel

from .cache import memoized_query

logger = logging.getLogger(__name__)


# ── Response DTOs (pydantic — matches the shape system_metrics.py returns) ──


class _RollupCamelModel(BaseModel):
    """Base for provider-credential-rollup response DTOs.

    Matches the camelCase wire-serialisation config every other
    ``ClientV1Envelope``-wrapped DTO on this router uses (see
    ``ccdash_contracts.models.FeatureSurfaceDTO``): serialised keys are
    camelCase, but ``populate_by_name=True`` keeps every existing
    snake_case construction call site and attribute access unchanged.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ExcludedSessionEntry(_RollupCamelModel):
    """One session whose spend was excluded from the attributed total.

    ``spend_delta`` mirrors ``sessions.ica_spend_delta`` verbatim — per the
    v51 contract it is NULL for every non-``attributed`` verdict, so this
    will read ``None`` for the overwhelming majority of rows. It is carried
    through anyway so a caller inspecting an unexpected non-null value here
    has evidence of a contract violation upstream, rather than silence.
    """

    project_id: str
    session_id: str
    attribution: str | None = None
    spend_delta_raw: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class CredentialSeriesRollup(_RollupCamelModel):
    """One rotation-lineage series (one or more credential rows merged by a
    declared ``rotated_from_id`` chain, or exactly one row/synthetic key when
    no rotation is declared).
    """

    series_id: str
    channel: str
    credential_names: list[str] = Field(default_factory=list)
    credential_ids: list[int] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)

    session_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    spend_usd: float = 0.0
    spend_excluded_count: int = 0
    spend_excluded_by_attribution: dict[str, int] = Field(default_factory=dict)

    excluded_sessions: list[ExcludedSessionEntry] | None = None


class ProjectRollupError(_RollupCamelModel):
    project_id: str
    error: str


class ProviderCredentialRollupResponse(_RollupCamelModel):
    status: str = "ok"  # "ok" | "partial"
    generated_at: datetime
    include_unattributed: bool
    since: datetime | None = None
    until: datetime | None = None
    project_ids: list[str] = Field(default_factory=list)
    errors: list[ProjectRollupError] = Field(default_factory=list)
    series: list[CredentialSeriesRollup] = Field(default_factory=list)


# ── Internal row shape ───────────────────────────────────────────────────────


@dataclass(slots=True)
class _SessionSpendRow:
    project_id: str
    session_id: str
    channel: str
    credential_name: str
    tokens_in: int
    tokens_out: int
    spend_delta_raw: str | None
    attribution: str | None
    started_at_raw: str | None


@dataclass(slots=True)
class _CredentialRow:
    id: int
    channel: str
    credential_name: str
    rotated_from_id: int | None


# ── Attribution choke point (see module docstring) ──────────────────────────


def _split_by_attribution(
    rows: list[_SessionSpendRow],
) -> tuple[list[_SessionSpendRow], list[_SessionSpendRow]]:
    """Split *rows* into (attributed, excluded).

    The ONLY predicate in this module that inspects ``attribution`` to decide
    spend eligibility. An unrecognised token (outside the closed vocabulary in
    ``backend/parsers/ica_spend.py``) lands in ``excluded`` — same as any
    other non-``attributed`` value — and never raises.
    """
    attributed: list[_SessionSpendRow] = []
    excluded: list[_SessionSpendRow] = []
    for row in rows:
        if row.attribution == "attributed":
            attributed.append(row)
        else:
            excluded.append(row)
    return attributed, excluded


def _sum_attributed_spend(attributed_rows: list[_SessionSpendRow]) -> float:
    """Sum ``ica_spend_delta`` over *attributed_rows* ONLY.

    The ONLY function in this module that parses ``ica_spend_delta`` and adds
    it to a running total. Takes the pre-filtered attributed list produced by
    :func:`_split_by_attribution` — there is no parameter that accepts the
    excluded list, so a caller cannot accidentally widen the sum by passing
    the wrong list in; the type of "spend" this function produces simply does
    not admit unattributed rows.

    An unparseable ``ica_spend_delta`` (should not happen for an
    ``attributed`` row per the v51 contract, but "should not happen" is not
    "cannot happen") is treated as 0.0 contribution rather than raising or
    corrupting the running total.
    """
    total = 0.0
    for row in attributed_rows:
        if row.spend_delta_raw is None:
            continue
        try:
            total += float(row.spend_delta_raw)
        except (TypeError, ValueError):
            logger.warning(
                "provider_credential_rollup: unparseable ica_spend_delta=%r "
                "on attributed session=%s project=%s; excluded from sum",
                row.spend_delta_raw,
                row.session_id,
                row.project_id,
            )
    return total


def _count_tokens_and_sessions(
    rows: list[_SessionSpendRow],
) -> tuple[int, int, int]:
    """Return (session_count, tokens_in, tokens_out) over ALL rows.

    Deliberately takes the full row set (attributed + excluded) — token and
    session counts are NOT subject to the attribution exclusion (only spend
    is). This function never reads ``attribution`` at all, so it cannot
    accidentally narrow to the attributed subset.
    """
    tokens_in = sum(r.tokens_in for r in rows)
    tokens_out = sum(r.tokens_out for r in rows)
    return len(rows), tokens_in, tokens_out


# ── Periodic windowing (see module docstring for why this runs BEFORE the
#    attribution choke point rather than duplicating it) ───────────────────


def _parse_window_boundary(value: str, *, param_name: str) -> datetime:
    """Parse a caller-supplied ISO-8601 ``since``/``until`` boundary.

    Raises :class:`ValueError` with a clean, user-facing message on anything
    unparseable — callers (the router) are expected to translate that into a
    4xx, never a 500. A naive (tz-less) timestamp is treated as UTC, matching
    ``generated_at``'s own UTC convention on this response.
    """
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(
            f"invalid {param_name} timestamp: {value!r} (expected ISO-8601, e.g. "
            "'2026-08-01T00:00:00Z')"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_started_at(raw: str | None) -> datetime | None:
    """Best-effort parse of a stored ``sessions.started_at`` value.

    Returns ``None`` for empty/missing/unparseable values rather than
    raising — a malformed historical row must not crash a windowed query.
    Such a row is excluded from a windowed result (it cannot be confirmed
    inside the window) but is unaffected when no window is requested, since
    :func:`_filter_rows_by_window` is only invoked once a window is active.
    """
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _filter_rows_by_window(
    rows: list[_SessionSpendRow],
    *,
    since: datetime | None,
    until: datetime | None,
) -> list[_SessionSpendRow]:
    """Narrow *rows* to those started within [*since*, *until*] (inclusive).

    The ONE place in this module that applies a time window. Called ONCE,
    on the full pre-bucketing row set, before any row reaches
    :func:`_split_by_attribution`. If both bounds are ``None`` this returns
    *rows* unchanged (same object-identity-preserving no-op the "omit both
    params" cumulative contract requires) — no separate cumulative code path
    exists; windowing is simply this filter being a no-op.

    A row whose ``started_at`` cannot be parsed is excluded once a window is
    active (see :func:`_parse_started_at`) — never included as an
    unverifiable guess.
    """
    if since is None and until is None:
        return rows
    kept: list[_SessionSpendRow] = []
    for row in rows:
        started = _parse_started_at(row.started_at_raw)
        if started is None:
            continue
        if since is not None and started < since:
            continue
        if until is not None and started > until:
            continue
        kept.append(row)
    return kept


# ── Rotation-lineage grouping (union-find, cycle-safe) ──────────────────────


def _group_credentials_by_series(
    credentials: list[_CredentialRow],
) -> dict[int, int]:
    """Return {credential_id: series_root_id} via union-find over declared
    ``rotated_from_id`` edges.

    Union-find is used specifically because it cannot hang or recurse on a
    malformed cycle: ``_find`` follows parent pointers with path compression
    (bounded by the number of distinct ids, never revisits a node twice
    because compression flattens the chain as it goes), and ``_union`` on two
    already-connected ids is a no-op comparison, not a re-walk. A declared
    cycle (A -> B -> A) still terminates and simply yields one series, same
    as a clean chain would.
    """
    parent: dict[int, int] = {c.id: c.id for c in credentials}

    def _find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        # Path compression.
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            # Deterministic root choice (lower id wins) so series_id is stable.
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    valid_ids = set(parent)
    for cred in credentials:
        if cred.rotated_from_id is not None and cred.rotated_from_id in valid_ids:
            _union(cred.id, cred.rotated_from_id)

    return {cid: _find(cid) for cid in parent}


# ── DB access (dual-path SQLite/PostgreSQL, mirrors system_metrics.py) ──────


async def _fetch_all_credentials(db: Any) -> list[_CredentialRow]:
    sql = "SELECT id, channel, credential_name, rotated_from_id FROM provider_credentials"
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sql) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(sql)
    return [
        _CredentialRow(
            id=int(r["id"]),
            channel=str(r["channel"] or ""),
            credential_name=str(r["credential_name"] or ""),
            rotated_from_id=(
                int(r["rotated_from_id"]) if r["rotated_from_id"] is not None else None
            ),
        )
        for r in rows
    ]


async def _fetch_project_ica_sessions(
    db: Any, project_id: str
) -> list[_SessionSpendRow]:
    """Return every session in *project_id* with a non-empty ``ica_key``.

    ``channel`` is re-derived per session via
    :func:`derive_provider_identity` — the same derivation the M2 backfill
    uses to key ``provider_credentials`` — so a session maps onto the same
    ``(channel, credential_name)`` a backfilled credential row would carry,
    even if the backfill job has not run yet (see the "unmapped" fallback in
    :meth:`ProviderCredentialRollupService.get_rollup`).
    """
    sqlite_sql = (
        "SELECT id, ica_key, model, platform_type, launcher, model_variant, "
        "tokens_in, tokens_out, ica_spend_delta, ica_spend_attribution, started_at "
        "FROM sessions WHERE project_id = ? "
        "AND ica_key IS NOT NULL AND TRIM(ica_key) != ''"  # noqa: S608
    )
    pg_sql = (
        "SELECT id, ica_key, model, platform_type, launcher, model_variant, "
        "tokens_in, tokens_out, ica_spend_delta, ica_spend_attribution, started_at "
        "FROM sessions WHERE project_id = $1 "
        "AND ica_key IS NOT NULL AND TRIM(ica_key) != ''"  # noqa: S608
    )
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (project_id,)) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql, project_id)

    out: list[_SessionSpendRow] = []
    for r in rows:
        identity = derive_provider_identity(
            r["model"], r["platform_type"], r["launcher"], r["model_variant"]
        )
        credential_name = str(r["ica_key"]).strip()
        out.append(
            _SessionSpendRow(
                project_id=project_id,
                session_id=str(r["id"]),
                channel=identity["providerChannel"],
                credential_name=credential_name,
                tokens_in=int(r["tokens_in"] or 0),
                tokens_out=int(r["tokens_out"] or 0),
                spend_delta_raw=(
                    r["ica_spend_delta"] if r["ica_spend_delta"] is not None else None
                ),
                attribution=(
                    r["ica_spend_attribution"]
                    if r["ica_spend_attribution"] is not None
                    else None
                ),
                started_at_raw=(
                    str(r["started_at"]) if r["started_at"] is not None else None
                ),
            )
        )
    return out


# ── Param extractor for @memoized_query (mirrors system_metrics.py style) ──


def _rollup_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_ids: list[str] | None = None,
    include_unattributed: bool = False,
    since: str | None = None,
    until: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    _ = self, context, ports
    # Normalise to the parsed-and-reserialised ISO form so two spellings of
    # the same instant (e.g. trailing "Z" vs "+00:00") hash to the same
    # cache key, while two genuinely different windows never collide.
    since_norm = _parse_window_boundary(since, param_name="since").isoformat() if since else None
    until_norm = _parse_window_boundary(until, param_name="until").isoformat() if until else None
    return {
        "project_ids": sorted(project_ids) if project_ids else None,
        "include_unattributed": include_unattributed,
        "since": since_norm,
        "until": until_norm,
    }


class ProviderCredentialRollupService:
    """Cross-project per-credential spend/token/session rollup (M3)."""

    @memoized_query("provider_credential_rollup", param_extractor=_rollup_params)
    async def get_rollup(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_ids: list[str] | None = None,
        include_unattributed: bool = False,
        since: str | None = None,
        until: str | None = None,
    ) -> ProviderCredentialRollupResponse:
        """Aggregate spend/tokens/sessions per credential series, cross-project.

        Spend excludes every session whose ``ica_spend_attribution`` is not
        exactly ``'attributed'`` (see module docstring for why, and for the
        structural guarantee that no other code path in this module can
        widen that sum). Token and session counts include ALL sessions
        regardless of attribution. ``include_unattributed=True`` additionally
        populates ``excluded_sessions`` on each series for debugging — the
        default response omits that field entirely so an incidental
        ``len(...)`` on it can't be mistaken for "the excluded count", which
        is always available via ``spend_excluded_count``.

        ``since``/``until`` (ISO-8601 strings) narrow every series to
        sessions whose ``started_at`` falls in ``[since, until]``. Omitting
        both reproduces the cumulative (all-time) result exactly — windowing
        is implemented as a filter over the pre-bucketing row set
        (:func:`_filter_rows_by_window`) that is a no-op when no bound is
        given, not a second code path. The attributed-only spend exclusion
        applies identically inside a window (it runs downstream of the
        filter), and the excluded count is still always reported. The
        effective (parsed) window is echoed back on the response via
        ``since``/``until`` so a cached or shared payload is never
        ambiguous about which window produced it. An unparseable boundary
        raises :class:`ValueError` — the router surfaces that as a 4xx.
        """
        t_start = time.monotonic()
        since_dt = _parse_window_boundary(since, param_name="since") if since else None
        until_dt = _parse_window_boundary(until, param_name="until") if until else None
        with otel.start_span(
            "provider_credential_rollup.get_rollup",
            {"include_unattributed": include_unattributed},
        ) as span:
            projects = ports.workspace_registry.list_projects()
            if project_ids is not None:
                allowed = set(project_ids)
                projects = [p for p in projects if p.id in allowed]

            db = ports.storage.db
            credentials = await _fetch_all_credentials(db)
            series_of: dict[int, int] = _group_credentials_by_series(credentials)

            # (channel, credential_name) -> credential row, for session mapping.
            credential_by_key: dict[tuple[str, str], _CredentialRow] = {
                (c.channel, c.credential_name): c for c in credentials
            }
            # series_root_id -> representative info, built lazily below.
            credential_by_id: dict[int, _CredentialRow] = {c.id: c for c in credentials}

            semaphore = asyncio.Semaphore(config.CCDASH_SYSTEM_METRICS_CONCURRENCY)

            async def _safe_fetch(project_id: str) -> tuple[str, list[_SessionSpendRow] | None, str | None]:
                async with semaphore:
                    try:
                        rows = await _fetch_project_ica_sessions(db, project_id)
                        return project_id, rows, None
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "provider_credential_rollup: error for project=%s: %s",
                            project_id,
                            exc,
                        )
                        return project_id, None, str(exc)

            fetched = await asyncio.gather(*[_safe_fetch(p.id) for p in projects])

            errors: list[ProjectRollupError] = []
            all_rows: list[_SessionSpendRow] = []
            for project_id, rows, err in fetched:
                if err is not None:
                    errors.append(ProjectRollupError(project_id=project_id, error=err))
                    continue
                all_rows.extend(rows or [])

            # The ONE place a time window is applied — before bucketing, so
            # every downstream step (including the attribution choke point)
            # only ever sees already-windowed rows. No-op when no window was
            # requested (see _filter_rows_by_window docstring).
            all_rows = _filter_rows_by_window(all_rows, since=since_dt, until=until_dt)

            # Bucket every session row into a series key: a credential's
            # series root if the (channel, name) maps to a known credential
            # row, else a synthetic per-(channel,name) key so sessions ahead
            # of the M2 backfill are still counted rather than dropped.
            buckets: dict[str, list[_SessionSpendRow]] = {}
            bucket_meta: dict[str, dict[str, Any]] = {}

            for row in all_rows:
                cred = credential_by_key.get((row.channel, row.credential_name))
                if cred is not None:
                    root_id = series_of[cred.id]
                    series_key = f"credential-series:{root_id}"
                else:
                    series_key = f"unmapped:{row.channel}:{row.credential_name}"

                buckets.setdefault(series_key, []).append(row)
                meta = bucket_meta.setdefault(
                    series_key,
                    {
                        "channel": row.channel,
                        "credential_names": set(),
                        "credential_ids": set(),
                        "project_ids": set(),
                    },
                )
                meta["credential_names"].add(row.credential_name)
                meta["project_ids"].add(row.project_id)
                if cred is not None:
                    meta["credential_ids"].add(cred.id)

            # Also surface declared series that currently have zero sessions
            # in the fetched window, so a rotated credential with no recent
            # ICA-launched activity still reads as one series in the shape of
            # the response (empty totals), never silently absent.
            for cred in credentials:
                root_id = series_of[cred.id]
                series_key = f"credential-series:{root_id}"
                buckets.setdefault(series_key, [])
                meta = bucket_meta.setdefault(
                    series_key,
                    {
                        "channel": cred.channel,
                        "credential_names": set(),
                        "credential_ids": set(),
                        "project_ids": set(),
                    },
                )
                meta["credential_names"].add(cred.credential_name)
                meta["credential_ids"].add(cred.id)
                if credential_by_id.get(root_id) is not None:
                    meta["channel"] = credential_by_id[root_id].channel

            series_list: list[CredentialSeriesRollup] = []
            for series_key, rows in buckets.items():
                meta = bucket_meta[series_key]
                attributed_rows, excluded_rows = _split_by_attribution(rows)
                spend_usd = _sum_attributed_spend(attributed_rows)
                session_count, tokens_in, tokens_out = _count_tokens_and_sessions(rows)

                excluded_by_attribution: dict[str, int] = {}
                for r in excluded_rows:
                    token = r.attribution if r.attribution is not None else "__null__"
                    excluded_by_attribution[token] = excluded_by_attribution.get(token, 0) + 1

                excluded_sessions: list[ExcludedSessionEntry] | None = None
                if include_unattributed:
                    excluded_sessions = [
                        ExcludedSessionEntry(
                            project_id=r.project_id,
                            session_id=r.session_id,
                            attribution=r.attribution,
                            spend_delta_raw=r.spend_delta_raw,
                            tokens_in=r.tokens_in,
                            tokens_out=r.tokens_out,
                        )
                        for r in excluded_rows
                    ]

                series_list.append(
                    CredentialSeriesRollup(
                        series_id=series_key,
                        channel=str(meta["channel"]),
                        credential_names=sorted(meta["credential_names"]),
                        credential_ids=sorted(meta["credential_ids"]),
                        project_ids=sorted(meta["project_ids"]),
                        session_count=session_count,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        spend_usd=round(spend_usd, 6),
                        spend_excluded_count=len(excluded_rows),
                        spend_excluded_by_attribution=excluded_by_attribution,
                        excluded_sessions=excluded_sessions,
                    )
                )

            series_list.sort(key=lambda s: s.series_id)

            duration_ms = (time.monotonic() - t_start) * 1000
            status = "partial" if errors else "ok"

            if span is not None:
                span.set_attribute("project_count", len(projects))
                span.set_attribute("series_count", len(series_list))
                span.set_attribute("error_count", len(errors))

            logger.info(
                "provider_credential_rollup: completed in %.1f ms — "
                "projects=%d series=%d errors=%d",
                duration_ms,
                len(projects),
                len(series_list),
                len(errors),
            )

            return ProviderCredentialRollupResponse(
                status=status,
                generated_at=datetime.now(timezone.utc),
                include_unattributed=include_unattributed,
                since=since_dt,
                until=until_dt,
                project_ids=[p.id for p in projects],
                errors=errors,
                series=series_list,
            )
