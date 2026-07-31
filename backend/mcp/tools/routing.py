"""Routing-feedback rollup MCP tool (T5-002).

Exposes the persisted ``routing_rollup`` table -- computed offline by
Phase 4's worker sweep (``backend/adapters/jobs/routing_rollup_sweep_job.py``)
via Phase 3's deterministic rollup compute service
(``backend/application/services/agent_queries/routing_rollup.py::
RoutingRollupQueryService``) -- through a single ``ccdash_routing_rollup``
MCP tool. Mirrors ``reports.py``'s ``ccdash_aar_review`` tool shape exactly:
an inline ``_query(context, ports)`` closure, ``execute_query(...)`` from
``backend.mcp.bootstrap``, and ``build_envelope(result)`` from
``backend.mcp.tools`` for response shaping.

Read-source note
-----------------
The task's literal wording calls for delegating to
``RoutingRollupQueryService`` directly, but that service has no "read the
persisted table back" method -- it only owns the live-aggregation pipeline
Phase 4's worker sweep runs (see Phase 5's T5-001 finding notes). The
REST transport (``backend/routers/_client_v1_routing_rollup.py``) hit the
identical gap and resolved it by reading the persisted rows itself via
``_fetch_routing_rollup`` (deserialise + in-memory FR-7 coverage-counter
reassembly, zero live SQL aggregation). This tool reuses that same
``_fetch_routing_rollup`` coroutine rather than re-implementing the
repository read + counter reassembly a second time -- sharing the one
fetch implementation is what guarantees the three transports stay
byte-identical (T5-004), not three independently-written copies that
happen to agree.

``build_envelope`` meta-fields note
------------------------------------
``build_envelope`` expects ``status``/``generated_at``/``data_freshness``/
``source_refs`` on the result. ``RoutingRollupResponseDTO`` defines
``generated_at`` only -- it has no ``status``, ``data_freshness``, or
``source_refs`` fields. The helper degrades gracefully for the fields it is
missing (``data_freshness``/``source_refs`` come back ``None``/``[]`` in
``meta``), but the top-level envelope ``status`` key resolves to the
literal string ``"error"`` on every call (``payload.get("status", "error")``
with no ``status`` key present) -- including successful, enabled responses.
This is a genuine drift signal against ``ccdash_aar_review`` (whose
``AARReviewDTO`` *does* define ``status: Literal["ok", "error"] = "ok"``),
flagged here as a Finding per the phase plan's explicit instruction rather
than patched from this task -- ``RoutingRollupResponseDTO`` is Phase 3's
frozen contract and this task's ``files_affected`` list does not include
``models.py``.
"""
from __future__ import annotations

from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope
from backend.routers._client_v1_routing_rollup import _fetch_routing_rollup


def register_routing_tools(mcp) -> None:
    @mcp.tool(name="ccdash_routing_rollup")
    async def ccdash_routing_rollup(project_id: str | None = None) -> dict:
        """Read-only Proof -> Routing Feedback Loop rollup (BP-6 producer surface).

        Serves the persisted ``routing_rollup`` table computed offline by
        Phase 4's worker sweep. No live aggregation happens on this tool's
        request path -- it only deserialises already-persisted rows and
        reassembles the FR-7 coverage counters over them, mirroring the
        REST transport's ``_fetch_routing_rollup`` byte-for-byte. Returns
        the deterministic disabled envelope (``enabled: false``, empty
        ``keys[]``, zero counters) when
        ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is false.
        """

        async def _query(context, ports):
            return await _fetch_routing_rollup(context, ports, project_id_override=project_id)

        result = await execute_query(
            _query,
            tool_name="ccdash_routing_rollup",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_routing_tools"]
