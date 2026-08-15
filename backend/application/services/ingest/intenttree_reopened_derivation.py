"""Reopened-trendline derivation (are-we-winning-dashboard-v1 M2 part B).

There is no ``node.reopened`` event type in IntentTree's event log, and
``node.updated`` carries no payload (measured 0/200 sampled -- see the
mandatory worknote ``.claude/worknotes/are-we-winning-dashboard/measured-
data-availability.md``, Finding 1). A "reopen" cannot be read off the event
stream directly -- it must be **derived** by walking per-node status history.

This module runs entirely on the ingestion/derivation side, never on the
query-service render path (``backend/application/services/agent_queries/
are_we_winning.py``): it is invoked by a scheduled job, writes to
``intent_tree_reopened_events`` (v56 DDL), and the render path only ever
reads that cache.

Scope boundary -- the load-bearing AC
--------------------------------------
Only a node that was **ever completed** can be reopened. The candidate set
is the **distinct node ids that appear in CCDash's own already-ingested
``intent_tree_events`` rows with ``event_type = 'node.completed'``** (745
today, per the worknote) -- never the full node tree (3,941+ nodes). This
module never queries "all nodes"; ``distinct_node_ids_for_event_type`` is
the single, injectable, observable choke point that enforces and makes this
boundary assertable (a test can wrap/patch it and assert the exact node-id
set fetched, or assert on the exact set of node ids the injected HTTP getter
was called with -- see ``test_are_we_winning_derivations.py``).

Terminal-status decision (recorded here AND in the implementation notes,
per the task's explicit instruction -- this is the single highest-risk
"silently plausible wrong" boundary in this feature)
--------------------------------------------------------------------------
``TERMINAL_STATUSES = frozenset({"completed"})`` -- **``completed`` only**,
deliberately not the broader set a first pass might reach for (``archived``,
``deferred``). Ground-truth verified against the live IntentTree source
(``intenttree.models.enums.NodeStatus``, 15 values: not_started, ready,
in_progress, blocked, waiting_review, completed, deferred, archived, inbox,
backlog, side_quest, active, running, waiting_human, reviewing):

* The candidate-set gate for this whole derivation is explicitly "ever
  emitted ``node.completed``" -- tying the derivation conceptually to
  ``completed`` specifically as the one terminal event being tracked. Using
  a different set to decide *reopens* than the set used to decide
  *eligibility* would be an unstated, easy-to-miss inconsistency.
* ``archived`` is ambiguous: it can mean "done and put away" OR "abandoned
  without ever finishing" (a deferred/cancelled node can also be archived).
  Treating it as terminal risks a false-positive reopen when a *cancelled*
  node is later un-archived and resumed -- that is not "completed work
  regressed," it is "shelved work resumed," and counting it as a reopen
  would misreport regression exactly as the plan's routing_constraints
  warn ("a wrong terminal-status transition boundary is silently plausible
  and would misreport regression, not just render wrong").
* ``deferred``/``backlog``/``inbox`` are parking states for work that was
  never done in the first place; a transition out of them is "starting/
  resuming," not "reopening completed work."

Destination-status decision -- both ends of the transition are constrained
------------------------------------------------------------------------------
A reopen is a transition **from** a terminal status **to an ACTIVE status**
-- constraining only the source (as an earlier pass did) silently counts
``completed -> archived`` and ``completed -> deferred`` as reopens, which is
wrong in the specific way this milestone was warned about: archiving or
deferring a finished node is **disposal**, not "completed work regressed."
Counting it would inflate the regression trendline with routine cleanup.

``ACTIVE_DESTINATION_STATUSES`` is an explicit **allow-list**, deliberately
not a deny-list: a status added upstream later defaults to "not a reopen"
until someone explicitly adds it here, rather than silently becoming a
reopen destination the moment IntentTree ships a new value. Ground-truthed
against the same live enum as ``TERMINAL_STATUSES`` above
(``intenttree.models.enums.NodeStatus``, 15 values: not_started, ready,
in_progress, blocked, waiting_review, completed, deferred, archived, inbox,
backlog, side_quest, active, running, waiting_human, reviewing):

* **Active** (``ACTIVE_DESTINATION_STATUSES``): ``ready``, ``in_progress``,
  ``blocked``, ``waiting_review``, ``active``, ``running``,
  ``waiting_human``, ``reviewing`` -- every status that puts a node back
  into the live execution pipeline (claimable, being worked, or paused
  mid-work waiting on a gate). A transition into any of these from
  ``completed`` is a genuine "this finished thing needs attention again."
* **Not active** -- ``archived``/``deferred`` are disposal/parking (see the
  ``TERMINAL_STATUSES`` rationale above -- the same reasoning that keeps
  them out of the terminal set keeps them out of the active-destination
  set too: they are "shelved," not "resumed"). ``not_started``/``inbox``/
  ``backlog`` are pre-triage queue states for work that was never started
  in the first place -- routing a finished node back into a queue bucket is
  "re-parking," not "actively resuming." ``side_quest`` is an off-tree
  capture bucket, not a work state. ``completed`` itself is excluded by
  construction (staying/re-completing is not a reopen).

A transition counts as a reopen iff a single ``NodeHistoryRead`` row for
``field=status`` has an unwrapped ``old_value`` in ``TERMINAL_STATUSES`` and
an unwrapped ``new_value`` in ``ACTIVE_DESTINATION_STATUSES``.

Fail-soft (mirrors ``intenttree_events_ingest.py`` exactly)
-------------------------------------------------------------
A transport/HTTP failure while fetching one node's history stops the whole
sweep immediately (no partial-candidate skipping that could silently miss a
node) and returns a non-ok result; rows already derived and committed for
nodes processed *before* the failure are **not** rolled back -- they are
real, idempotently-upserted derivations. The cursor watermark
(``ingest_cursors``, source_id ``intenttree:reopened_derivation``) only
advances on a fully clean pass, so ``AreWeWinningQueryService`` can tell
"never successfully derived" (returns ``None``, per the absent-not-zero
contract) apart from "derived, and the result happens to be empty."

Incremental vs. full re-walk -- correctness first
----------------------------------------------------
Every pass re-walks the **entire** ever-completed candidate set (not just
newly-completed nodes). A node can complete, reopen, and re-complete more
than once, and each pass must be able to see a *new* reopen on a node that
was already in the candidate set on a prior pass -- skipping "already-seen"
nodes would silently miss those. ``insert_if_not_exists`` keyed on the
upstream history-row id keeps a full re-walk idempotent and cheap to persist
(only genuinely new reopen rows write). At 745 candidate nodes today this is
affordable as a periodic background job; if the ever-completed set grows by
an order of magnitude, revisit (e.g. bound to nodes with a new
``node.completed`` event since the last successful pass, unioned with nodes
already known to have reopened at least once).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Final

import httpx

from backend.db.repositories.base import retry_on_locked

logger = logging.getLogger("ccdash.ingest.intenttree_reopened_derivation")

#: The one and only terminal status this derivation treats as "done" for the
#: purposes of detecting a reopen. See the module docstring for the full
#: rationale on why ``archived``/``deferred`` are deliberately excluded.
TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({"completed"})

#: The allow-list of destination statuses that count as "reopened" -- see
#: the module docstring for the full ground-truthed rationale. Deliberately
#: an allow-list, not a deny-list of disposal statuses: an unrecognized
#: future status defaults to "not a reopen" rather than silently becoming one.
ACTIVE_DESTINATION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "ready",
        "in_progress",
        "blocked",
        "waiting_review",
        "active",
        "running",
        "waiting_human",
        "reviewing",
    }
)

SOURCE_ID: Final[str] = "intenttree:reopened_derivation"

HttpGetter = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[dict[str, Any]]]


async def _default_http_get(
    url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _unwrap(value: Any) -> str | None:
    """Unwrap a NodeHistoryRead ``old_value``/``new_value`` field.

    Per the worknote and the upstream ``NodeHistoryRead`` schema, these are
    passed through **verbatim**: either ``{"value": <scalar>}`` or a bare
    ``None`` (never ``{"value": None}``). This does not assume either shape
    -- a bare scalar (defensive, in case a future API version stops
    wrapping) and an empty/malformed dict both degrade to ``None`` rather
    than raising.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        inner = value.get("value")
        return str(inner) if inner is not None else None
    return str(value)


@dataclass(slots=True)
class ReopenedDerivationResult:
    ok: bool
    candidate_node_ids: list[str] = field(default_factory=list)
    """Every node id this pass fetched history for -- the assertable scope boundary."""
    nodes_processed: int = 0
    reopens_written: int = 0
    error: str | None = None


class IntentTreeReopenedDerivationService:
    """Derives reopen events for the ever-completed candidate set only.

    Parameters
    ----------
    events_db:
        The raw DB connection (aiosqlite.Connection or asyncpg
        connection/pool) backing ``intent_tree_events`` -- used only to
        compute the candidate set via ``distinct_node_ids_for_event_type``.
    reopened_repo:
        A ``SqliteIntentTreeReopenedEventsRepository`` /
        ``PostgresIntentTreeReopenedEventsRepository`` (or duck-typed
        equivalent).
    cursor_repo:
        Optional ``SqliteIngestCursorRepository`` / equivalent.
    """

    MAX_PAGE_SIZE: int = 200
    MAX_PAGES_PER_NODE: int = 50

    def __init__(
        self,
        events_db: Any,
        reopened_repo: Any,
        cursor_repo: Any | None,
        *,
        api_url: str,
        api_token: str,
        workspace_id: str,
        page_size: int = 200,
        timeout_seconds: float = 10.0,
        http_get: HttpGetter | None = None,
    ) -> None:
        self._events_db = events_db
        self._reopened_repo = reopened_repo
        self._cursor_repo = cursor_repo
        self._api_url = api_url.rstrip("/")
        self._api_token = api_token
        self._workspace_id = workspace_id
        self._page_size = min(int(page_size), self.MAX_PAGE_SIZE)
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or _default_http_get

    async def derive_all(self) -> ReopenedDerivationResult:
        """Walk every ever-completed node's status history. Never raises."""
        await self._cursor_get_or_create()

        candidate_node_ids = sorted(
            await distinct_node_ids_for_event_type(self._events_db, "node.completed")
        )
        nodes_processed = 0
        reopens_written = 0

        for node_id in candidate_node_ids:
            try:
                written = await self._derive_for_node(node_id)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                # fail-soft: stop the sweep, do not roll back what already
                # committed for earlier nodes in this pass (mirrors
                # intenttree_events_ingest.py's fail-soft contract exactly).
                logger.warning(
                    "intenttree reopened derivation: fetch failed for node_id=%s "
                    "after %d/%d node(s) processed (reopens_written=%d so far, "
                    "not rolled back): %s",
                    node_id,
                    nodes_processed,
                    len(candidate_node_ids),
                    reopens_written,
                    exc,
                )
                await self._cursor_record_error(str(exc))
                return ReopenedDerivationResult(
                    ok=False,
                    candidate_node_ids=candidate_node_ids,
                    nodes_processed=nodes_processed,
                    reopens_written=reopens_written,
                    error=str(exc),
                )
            nodes_processed += 1
            reopens_written += written

        cursor_advanced = await self._cursor_advance()
        if not cursor_advanced:
            # The success watermark itself is load-bearing here (unlike a
            # purely-telemetry cursor): AreWeWinningQueryService gates
            # ``reopened`` on this exact watermark via
            # ``_derivation_has_ever_run``. Reporting ok=True while failing
            # to record it would be a fail-soft claim about a failure that
            # was never actually the remote being unavailable -- the same
            # defect class the M1 ingestion service's fetch handler already
            # guards against by never reporting success on an error it
            # cannot characterize as remote-unavailability.
            return ReopenedDerivationResult(
                ok=False,
                candidate_node_ids=candidate_node_ids,
                nodes_processed=nodes_processed,
                reopens_written=reopens_written,
                error="failed to record derivation success watermark (ingest_cursors advance failed)",
            )
        return ReopenedDerivationResult(
            ok=True,
            candidate_node_ids=candidate_node_ids,
            nodes_processed=nodes_processed,
            reopens_written=reopens_written,
        )

    async def _derive_for_node(self, node_id: str) -> int:
        """Fetch this node's full status history (paginated) and persist reopens.

        Returns the count of NEW reopen rows written for this node.
        """
        written = 0
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0

        while True:
            params: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "field": "status",
                "limit": self._page_size,
            }
            if cursor:
                params["cursor"] = cursor

            page = await self._http_get(
                f"{self._api_url}/api/v1/nodes/{node_id}/history",
                params,
                {"Authorization": f"Bearer {self._api_token}"},
                self._timeout_seconds,
            )
            pages_fetched += 1
            items = page.get("items") or []

            for item in items:
                if item.get("field") not in (None, "status"):
                    continue
                old_status = _unwrap(item.get("old_value"))
                new_status = _unwrap(item.get("new_value"))
                changed_at = item.get("changed_at") or item.get("occurred_at")
                history_id = item.get("id")
                if not (old_status and new_status and changed_at and history_id):
                    continue
                if old_status in TERMINAL_STATUSES and new_status in ACTIVE_DESTINATION_STATUSES:
                    was_new = await retry_on_locked(
                        lambda r={
                            "id": history_id,
                            "node_id": node_id,
                            "from_status": old_status,
                            "to_status": new_status,
                            "occurred_at": changed_at,
                        }: self._reopened_repo.insert_if_not_exists(r),
                        repo="intent_tree_reopened_events",
                    )
                    if was_new:
                        written += 1

            cursor = page.get("next_cursor")
            if not cursor or cursor in seen_cursors or pages_fetched >= self.MAX_PAGES_PER_NODE:
                break
            seen_cursors.add(cursor)

        return written

    # ── Cursor bookkeeping (best-effort, mirrors intenttree_events_ingest.py) ──

    async def _cursor_get_or_create(self) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.get_or_create(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree reopened derivation: cursor get_or_create failed: %s", exc)

    async def _cursor_advance(self) -> bool:
        """Advance the success watermark. Returns False (never raises) on failure.

        Unlike ``_cursor_get_or_create``/``_cursor_record_error`` (best-effort
        bookkeeping), this return value is checked by ``derive_all`` -- the
        watermark this call writes IS the "did a full clean pass complete"
        signal the render path depends on, so a failure here must not be
        reported as ``ok=True``.
        """
        if self._cursor_repo is None:
            return True
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.advance(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                    cursor_value=datetime.now(timezone.utc).isoformat(),
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                ),
                repo="ingest_cursors",
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree reopened derivation: cursor advance failed: %s", exc)
            return False

    async def _cursor_record_error(self, error_message: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.record_error(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                    error_message=error_message,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree reopened derivation: cursor record_error failed: %s", exc)


async def distinct_node_ids_for_event_type(db: Any, event_type: str) -> set[str]:
    """Return the distinct ``node_id`` set from ``intent_tree_events`` for *event_type*.

    This is the single choke point that defines the reopened-derivation
    candidate set -- deliberately factored out so a test can assert exactly
    which node ids the derivation examined (AC: "the candidate set is
    exactly the ever-completed set, not all nodes").
    """
    import aiosqlite  # local import: keep this module importable without aiosqlite present

    sqlite_sql = (
        "SELECT DISTINCT node_id FROM intent_tree_events "
        "WHERE event_type = ? AND node_id IS NOT NULL"  # noqa: S608
    )
    pg_sql = (
        "SELECT DISTINCT node_id FROM intent_tree_events "
        "WHERE event_type = $1 AND node_id IS NOT NULL"  # noqa: S608
    )
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (event_type,)) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql, event_type)
    # Both aiosqlite.Row (row_factory=aiosqlite.Row) and asyncpg.Record
    # support name-based subscript access.
    return {str(row["node_id"]) for row in rows}


__all__ = [
    "TERMINAL_STATUSES",
    "ACTIVE_DESTINATION_STATUSES",
    "SOURCE_ID",
    "ReopenedDerivationResult",
    "IntentTreeReopenedDerivationService",
    "distinct_node_ids_for_event_type",
]
