"""Transport-neutral IntentTree node <-> session cost attribution service.

Implements the two acceptance criteria of the itt-node-session-cost-join
feature:

  AC1: A completed IntentTree node can be joined to its session token totals
       by query, with no manual correlation.
  AC2: ``session_logs`` rows are reachable by an external script without
       direct postgres access (see the sibling
       ``/api/v1/sessions/{id}/tool-calls`` endpoint, which reuses
       ``SessionTranscriptService.list_session_logs`` directly rather than
       going through this module).

This module owns AC1 only.  It stores the node<->session binding as
``entity_links`` rows (``source_type='intent_node'``, ``origin='declared'``)
via ``backend.db.repositories.entity_graph`` -- **no new table, no schema
migration** -- and rolls up ``tokens_in``/``tokens_out``/``total_cost`` from
the ``sessions`` table for the declared (or family-expanded) session set.

Two attribution scopes:

  - ``"declared"`` (default): the EXACT set of sessions explicitly bound to
    the node via ``declare_intent_node_sessions``. No inference.
  - ``"family"`` (opt-in via ``expand_family=True``): every declared session
    is expanded to its ``workflow_id`` family -- every OTHER session sharing
    that ``workflow_id`` within the same project (e.g. subagent children of
    the same orchestrator run) is folded into the rollup too. This is a
    WIDER claim than "the sessions IntentTree explicitly named", so the
    response always reports which scope produced it via
    ``attributionScope`` -- the caller owns the decision to trust the wider
    claim, this service never picks silently.

Resilience invariants (mirrors ``session_detail.py``'s conventions):
  - An unknown/unlinked node yields the explicit zero-workload response
    shape (``sessionCount=0``, empty ``sessions``) -- never a 500, never a
    silently-coalesced default masking a lookup failure.
  - A declared session id that no longer resolves to a real ``sessions`` row
    (e.g. deleted) is simply absent from the rollup -- a documented contract
    state, not a bug.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.application.ports import CorePorts
from backend.observability import otel

__all__ = [
    "ATTRIBUTION_SCOPE_DECLARED",
    "ATTRIBUTION_SCOPE_FAMILY",
    "IntentNodeSessionCost",
    "IntentNodeCostTotals",
    "IntentNodeCostResult",
    "declare_intent_node_sessions",
    "get_intent_node_cost",
]

logger = logging.getLogger("ccdash.agent_queries.intent_node_cost")

ATTRIBUTION_SCOPE_DECLARED: Literal["declared"] = "declared"
ATTRIBUTION_SCOPE_FAMILY: Literal["family"] = "family"


# ── Data models ─────────────────────────────────────────────────────────────


@dataclass
class IntentNodeSessionCost:
    """One session's contribution to a node's cost rollup."""

    session_id: str
    workflow_id: str | None
    declared: bool
    """True when this session was explicitly bound via ``declare_intent_node_sessions``;
    False when it was pulled in only by ``expand_family`` workflow-id membership."""

    tokens_in: int
    tokens_out: int
    total_cost: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "workflowId": self.workflow_id,
            "declared": self.declared,
            "tokensIn": self.tokens_in,
            "tokensOut": self.tokens_out,
            "totalCost": self.total_cost,
        }


@dataclass
class IntentNodeCostTotals:
    session_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    total_cost: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "sessionCount": self.session_count,
            "tokensIn": self.tokens_in,
            "tokensOut": self.tokens_out,
            "totalCost": self.total_cost,
        }


@dataclass
class IntentNodeCostResult:
    node_id: str
    attribution_scope: Literal["declared", "family"]
    sessions: list[IntentNodeSessionCost] = field(default_factory=list)
    totals: IntentNodeCostTotals = field(default_factory=IntentNodeCostTotals)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "attributionScope": self.attribution_scope,
            "sessions": [s.as_dict() for s in self.sessions],
            "totals": self.totals.as_dict(),
        }


# ── Internal helpers ─────────────────────────────────────────────────────────


def _int_field(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _float_field(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


# ── Public service functions ─────────────────────────────────────────────────


async def declare_intent_node_sessions(
    node_id: str,
    session_ids: list[str],
    project_id: str,
    ports: CorePorts,
) -> list[str]:
    """Idempotently declare that *session_ids* belong to IntentTree node *node_id* (AC1).

    Delegates to ``EntityLinkRepository.link_intent_node_sessions`` -- a pure
    upsert against ``entity_links``, no schema migration.  Re-declaring the
    same (node_id, session_id) pair is a no-op, never a duplicate row.

    Returns the de-duplicated, order-preserved list of session ids that were
    processed (empty list for an empty *node_id*/*session_ids*).

    Raises:
        ValueError: if *project_id* is falsy. Defense in depth: the
            underlying ``entity_links`` write itself does not require a
            project_id, but a falsy value here is always a caller bug (every
            transport-layer caller MUST resolve a real project before
            declaring a binding) -- treated as an error rather than silently
            writing an unscoped/mis-scoped link row.
    """
    if not project_id:
        raise ValueError(
            "project_id is required to declare an IntentTree node<->session "
            "binding; got a falsy value."
        )
    with otel.start_span(
        "ccdash.intent_node_cost.declare",
        {"node_id": node_id, "project_id": project_id, "session_count": len(session_ids)},
    ):
        link_repo = ports.storage.entity_links()
        unique_session_ids = list(dict.fromkeys(session_ids))
        await link_repo.link_intent_node_sessions(
            node_id, unique_session_ids, project_id=project_id
        )
        return unique_session_ids


async def get_intent_node_cost(
    node_id: str,
    project_id: str,
    ports: CorePorts,
    *,
    expand_family: bool = False,
) -> IntentNodeCostResult:
    """Return an IntentTree node's session token/cost rollup (AC1).

    Parameters
    ----------
    node_id:
        The IntentTree node id whose declared session bindings to roll up.
    project_id:
        Required.  Scopes every session lookup -- a declared session id that
        belongs to a different project is silently excluded (never
        cross-project leakage).
    ports:
        Injected ``CorePorts`` providing repository access.
    expand_family:
        When ``False`` (default), the rollup is over EXACTLY the declared
        session set (``attributionScope="declared"``).  When ``True``, each
        declared session is expanded to every other session sharing its
        ``workflow_id`` within *project_id* (``attributionScope="family"``)
        -- a wider claim the caller opts into explicitly.

    Returns
    -------
    ``IntentNodeCostResult`` -- never ``None``.  A node with no declared
    bindings yields the explicit zero-workload result (``sessionCount=0``,
    empty ``sessions``), not an error.

    Raises
    ------
    ValueError
        If *project_id* is falsy. This is a hard guard, not a resilience
        nicety: ``session_repo.get_many_by_ids``/``list_by_workflow_ids``
        both treat a falsy ``project_id`` as "deliberately unscoped" (see
        their own docstrings) -- silently accepting one here would turn into
        an unscoped, cross-project read the moment ``expand_family=True`` is
        set, folding other projects' sessions into this node's totals.
    """
    if not project_id:
        raise ValueError(
            "project_id is required for the IntentTree node cost rollup; got "
            "a falsy value. A missing project_id must never silently degrade "
            "to an unscoped (cross-project) session lookup."
        )
    with otel.start_span(
        "ccdash.intent_node_cost.get",
        {"node_id": node_id, "project_id": project_id, "expand_family": expand_family},
    ):
        return await _impl(node_id, project_id, ports, expand_family=expand_family)


async def _impl(
    node_id: str,
    project_id: str,
    ports: CorePorts,
    *,
    expand_family: bool,
) -> IntentNodeCostResult:
    scope: Literal["declared", "family"] = (
        ATTRIBUTION_SCOPE_FAMILY if expand_family else ATTRIBUTION_SCOPE_DECLARED
    )

    link_repo = ports.storage.entity_links()
    declared_session_ids = await link_repo.get_intent_node_session_ids(node_id)
    if not declared_session_ids:
        return IntentNodeCostResult(node_id=node_id, attribution_scope=scope)

    session_repo = ports.storage.sessions()
    declared_rows: dict[str, dict[str, Any]] = await session_repo.get_many_by_ids(
        declared_session_ids, project_id=project_id
    )

    # effective_rows accumulates every session that contributes to the
    # rollup: the declared set, plus (when expand_family) their workflow_id
    # family. Keyed by session id so a session that is BOTH declared AND a
    # family member of another declared session is counted exactly once
    # (D-001-shape dedup discipline, same as get_session_workload_for_runs).
    effective_rows: dict[str, dict[str, Any]] = dict(declared_rows)

    if expand_family:
        workflow_ids = sorted(
            {
                str(row["workflow_id"])
                for row in declared_rows.values()
                if str(row.get("workflow_id") or "").strip()
            }
        )
        if workflow_ids:
            try:
                family_rows = await session_repo.list_by_workflow_ids(
                    workflow_ids, project_id=project_id
                )
            except Exception:
                logger.warning(
                    "intent_node_cost: family expansion query failed for node %r "
                    "project %r; falling back to declared-only rows",
                    node_id,
                    project_id,
                    exc_info=True,
                )
                family_rows = []
            for row in family_rows:
                sid = str(row.get("id") or "")
                if sid:
                    effective_rows.setdefault(sid, row)

    sessions: list[IntentNodeSessionCost] = []
    totals = IntentNodeCostTotals()
    for sid, row in effective_rows.items():
        tin = _int_field(row, "tokens_in")
        tout = _int_field(row, "tokens_out")
        cost = _float_field(row, "total_cost")
        totals.tokens_in += tin
        totals.tokens_out += tout
        totals.total_cost += cost
        sessions.append(
            IntentNodeSessionCost(
                session_id=sid,
                workflow_id=str(row.get("workflow_id") or "").strip() or None,
                declared=sid in declared_rows,
                tokens_in=tin,
                tokens_out=tout,
                total_cost=cost,
            )
        )
    totals.session_count = len(effective_rows)
    totals.total_cost = round(totals.total_cost, 6)

    return IntentNodeCostResult(
        node_id=node_id,
        attribution_scope=scope,
        sessions=sessions,
        totals=totals,
    )
