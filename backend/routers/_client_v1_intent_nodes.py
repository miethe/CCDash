"""IntentTree node <-> session cost attribution handlers for the v1 client API.

Pure handler functions (no router) — wired onto ``client_v1_router`` by
``backend/routers/client_v1.py``, matching the ``_client_v1_sessions.py`` /
``_client_v1_features.py`` pattern.

Implements the itt-node-session-cost-join feature:
  AC1: ``GET /api/v1/intent-nodes/{node_id}/cost`` joins a node to its
       session token/cost totals purely by query (via the transport-neutral
       ``intent_node_cost`` service).
  (Binding declaration): ``POST /api/v1/intent-nodes/{node_id}/sessions``
       idempotently records which sessions belong to a node.

AC2 (``session_logs`` external reachability) is served by a sibling handler
in ``_client_v1_sessions.py`` (``get_session_tool_calls_v1``), not here.
"""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.application.ports import CorePorts
from backend.application.services.agent_queries.intent_node_cost import (
    declare_intent_node_sessions,
    get_intent_node_cost,
)
from ccdash_contracts import (
    IntentNodeCostV1,
    IntentNodeSessionBindingV1,
)
from backend.routers.client_v1_models import ClientV1Envelope, build_client_v1_meta


def _instance_id() -> str:
    from backend import config as _cfg

    return getattr(_cfg, "INSTANCE_ID", "") or "ccdash-local"


# ---------------------------------------------------------------------------
# Request body for POST /intent-nodes/{node_id}/sessions
# ---------------------------------------------------------------------------


class IntentNodeSessionBindingRequest(BaseModel):
    """Body for ``POST /api/v1/intent-nodes/{node_id}/sessions``.

    Field names are the exact contract shape (``project_id``/``session_ids``,
    snake_case) rather than the camelCase alias-generator pattern used
    elsewhere in this router — this endpoint is the declared IntentTree ->
    CCDash binding surface, and IntentTree's own tooling calls it with these
    literal field names.
    """

    project_id: str = Field(..., min_length=1)
    session_ids: list[str] = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Handler: declare node<->session bindings
# ---------------------------------------------------------------------------


async def declare_intent_node_sessions_v1(
    node_id: str,
    payload: IntentNodeSessionBindingRequest,
    core_ports: CorePorts,
) -> ClientV1Envelope[IntentNodeSessionBindingV1]:
    """Idempotently declare that *payload.session_ids* belong to *node_id*.

    Always succeeds (200) for a well-formed body — an unknown/nonexistent
    ``session_id`` is simply recorded as a binding and will surface as a
    zero-contribution entry (or be silently excluded) at cost-rollup time
    rather than rejecting the whole declare call; IntentTree may legitimately
    declare a binding slightly ahead of CCDash's own session sync.

    ``payload.project_id`` is already rejected as HTTP 422 by
    ``IntentNodeSessionBindingRequest``'s ``Field(..., min_length=1)`` before
    this handler ever runs for an empty string. The ``except ValueError``
    below is defense in depth for the underlying service's own falsy-
    ``project_id`` guard (``declare_intent_node_sessions``) — unreachable via
    this exact HTTP path today, but keeps this handler correct if the
    pydantic constraint is ever loosened, and keeps the two layers'
    contracts in sync.
    """
    try:
        linked_ids = await declare_intent_node_sessions(
            node_id, payload.session_ids, payload.project_id, core_ports
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = IntentNodeSessionBindingV1(
        nodeId=node_id,
        projectId=payload.project_id,
        linkedSessionIds=linked_ids,
        linkedCount=len(linked_ids),
    )
    return ClientV1Envelope(
        status="ok",
        data=data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: node cost rollup
# ---------------------------------------------------------------------------


async def get_intent_node_cost_v1(
    node_id: str,
    project_id: str,
    expand_family: bool,
    core_ports: CorePorts,
) -> ClientV1Envelope[IntentNodeCostV1]:
    """Return a node's session token/cost rollup (AC1).

    ``project_id`` is required — HTTP 400 if falsy. NOTE: the router's
    ``Query(...)`` declaration only rejects a fully OMITTED ``project_id``
    (HTTP 422, FastAPI's own required-param validation); it does NOT reject
    an explicitly empty string (``?project_id=``), since ``str`` carries no
    length constraint at the Query level. That falsy-but-present case is
    caught here, explicitly — mirroring ``get_session_tool_calls_v1``'s
    identical guard. This check is load-bearing, not cosmetic: without it, a
    falsy ``project_id`` reaches ``session_repo.get_many_by_ids``/
    ``list_by_workflow_ids``, which both treat a falsy ``project_id`` as
    "deliberately unscoped" — turning ``?project_id=&expand_family=true``
    into an unscoped, cross-project read that folds other projects'
    sessions into this node's totals.

    A node with no declared session bindings yields the explicit
    zero-workload response, never a 404 — "not yet attributed" is a valid,
    expected state for a node, not an error.
    """
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "project_id is required for GET /intent-nodes/{node_id}/cost. "
                "Pass ?project_id=<project_id>. "
                "Active-project fallback is not supported on this endpoint."
            ),
        )
    try:
        result = await get_intent_node_cost(
            node_id, project_id, core_ports, expand_family=expand_family
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = IntentNodeCostV1.model_validate(result.as_dict())
    return ClientV1Envelope(
        status="ok",
        data=data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )
