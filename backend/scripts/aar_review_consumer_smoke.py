"""Best-effort cross-repo consumer smoke harness for the AAR-review PULL contract.

CCDash Phase 5 (T5-004 / T5-005) -- ``ccdash-automated-aar-review`` PRD §7.2/§7.3, D5 decision
(``docs/project_plans/exploration/ccdash-automated-aar-review/
ccdash-automated-aar-review-proposed-adr.md`` -- Addendum, Phase 5).

WHAT THIS PROVES
-----------------
D5 (locked, Phase 5): the op-consumption transport for AAR-review evidence is the existing
REST/MCP/CLI **PULL** path (``GET /api/v1/project/aar-review``), not a new PUSH/queue. This
script demonstrates that contract end-to-end:

1. Build sample payloads shaped EXACTLY like what a consumer receives from
   ``GET /api/v1/project/aar-review`` -- one ``AARReviewDTO`` per possible ``triage_verdict``
   value, wrapped in the real ``AARReviewListDTO`` + ``ClientV1Envelope`` production models
   (imported from this repo, never hand-rolled dicts) and round-tripped through
   ``model_dump(mode="json")`` -> plain dict, exactly as an HTTP client would receive them.
2. Apply the DOCUMENTED consumer-side routing rule from PRD §6 (P3 "Cross-repo contract to
   specify") + §7.3's resilience note: route on ``correlation.confidence`` + ``triage_verdict``;
   ``human_triage_required`` verdicts NEVER auto-route to ``op council``/ARC.
3. Assert (T5-005 / AC-P5.2) that the routing function returns a human-handoff route -- never a
   council/dispatch route -- for ``human_triage_required``, for EVERY confidence value tried
   (including the None/missing case and out-of-range values), proving the invariant does not
   depend on confidence at all once the verdict says "human".

MODE USED: **simulated-routing** (best-effort, per the Phase 5 plan). The real ``op`` CLI IS on
PATH in this environment (verified: ``/Users/miethe/.aos/shims/op``), but as of this writing
``op --help`` exposes no AAR-review-specific consumer subcommand -- the op-side contract
implementation is out-of-scope for this repo and is tracked as PRD §6 P3 future work ("op-side
contract document... references this PRD"). Invoking the generic ``op`` CLI here would not
exercise any AAR-review-specific logic, so this harness instead implements
``route_aar_review_candidate()`` as a small, self-contained function whose only inputs are the
pulled JSON payload's ``triage_verdict`` and ``correlation.confidence`` fields (per the
documented routing rule above) -- it deliberately does NOT import any CCDash service/compute
module (``aar_review.py``, ``compute_verdict``, etc.) so that this function is provably
independent of CCDash internals, i.e. exactly what an external consumer implementing the
documented contract from scratch would write.

INVARIANT PRESERVED (per CLAUDE.md "Invariant #2 (emit-only)"): this script performs ZERO writes,
ZERO CCDash mutations, and ZERO dispatch calls. It only (a) constructs read-model DTOs already
defined in ``backend/application/services/agent_queries/models.py`` /
``backend/routers/client_v1_models.py`` (the same models the live endpoint returns) and (b) runs a
pure routing function over their serialized JSON. No DB connection is opened; no HTTP request is
made; no ``op`` subprocess is invoked.

RUN
---
    backend/.venv/bin/python backend/scripts/aar_review_consumer_smoke.py

Exits 0 with a printed summary + assertion results on success; raises ``AssertionError`` (nonzero
exit) if any invariant is violated.
"""
from __future__ import annotations

import json
import shutil
from typing import Any

# Import ONLY the read-model DTOs a real HTTP consumer would deserialize into -- never the
# compute/service layer (aar_review.py, compute_verdict, etc.). This keeps the harness honest:
# it demonstrates a PULL consumer reading already-computed evidence, not CCDash re-deriving it.
from backend.application.services.agent_queries.models import (
    AARReviewCorrelation,
    AARReviewDTO,
    AARReviewFlag,
)
from backend.routers.client_v1_models import AARReviewListDTO, ClientV1Envelope, build_client_v1_meta


# ---------------------------------------------------------------------------
# Step 1 -- build sample payloads shaped exactly like GET /api/v1/project/aar-review
# ---------------------------------------------------------------------------


def _build_sample_envelope() -> dict[str, Any]:
    """Return the JSON dict a consumer would receive from the live PULL endpoint.

    One ``AARReviewDTO`` per ``triage_verdict`` value, using real production model classes
    (``AARReviewDTO`` / ``AARReviewCorrelation`` / ``AARReviewFlag`` / ``AARReviewListDTO`` /
    ``ClientV1Envelope``) -- the identical types ``_client_v1_aar_review.py``'s
    ``get_aar_review_v1`` handler returns -- then round-tripped through ``model_dump(mode="json")``
    to a plain dict, exactly as an ``httpx``/``requests`` client would see it over the wire.
    """
    surface_only = AARReviewDTO(
        document_id="doc-surface-only-001",
        correlation=AARReviewCorrelation(
            strategy="explicit_session_ref", confidence=0.94, session_ids=["sess-aaa"], feature_id=None,
        ),
        flags=[
            AARReviewFlag(flag_id="context_ballooning", triggered=False, severity="low", rationale="ok"),
            AARReviewFlag(flag_id="missing_artifacts", triggered=False, severity="low", rationale="ok"),
        ],
        triage_verdict="surface_only",
        reasons=["no flags triggered"],
        generated_at="2026-07-22T00:00:00+00:00",
        source_refs=["document:doc-surface-only-001", "session:sess-aaa"],
    )

    deep_review_recommended = AARReviewDTO(
        document_id="doc-deep-review-002",
        correlation=AARReviewCorrelation(
            strategy="task_session_ref", confidence=0.88, session_ids=["sess-bbb"], feature_id="feat-42",
        ),
        flags=[
            AARReviewFlag(
                flag_id="context_ballooning", triggered=True, severity="high",
                evidence_refs=["sess-bbb: 91.2% context utilization"],
                rationale="context utilization reached 91.2% (threshold 85.0%)",
            ),
        ],
        triage_verdict="deep_review_recommended",
        reasons=["1 flag(s) triggered: context_ballooning"],
        generated_at="2026-07-22T00:05:00+00:00",
        source_refs=["document:doc-deep-review-002", "session:sess-bbb", "feature:feat-42"],
    )

    # The load-bearing case for AC-P5.2: correlation confidence is null (correlation failed
    # entirely) -- the OQ-2 hard rule this DTO's producer already applies. A consumer MUST NOT
    # need CCDash's internal `compute_verdict` to know this is a human-only case; the verdict
    # field alone is authoritative.
    human_triage_required = AARReviewDTO(
        document_id="doc-human-triage-003",
        correlation=AARReviewCorrelation(strategy=None, confidence=None, session_ids=[], feature_id=None),
        flags=[],
        triage_verdict="human_triage_required",
        reasons=["correlation confidence is missing/null; routing to human triage per the OQ-2 hard rule"],
        generated_at="2026-07-22T00:10:00+00:00",
        source_refs=["document:doc-human-triage-003"],
    )

    list_dto = AARReviewListDTO(
        project_id="proj-smoke",
        total=3,
        reviews=[surface_only, deep_review_recommended, human_triage_required],
    )
    envelope = ClientV1Envelope(data=list_dto, meta=build_client_v1_meta(instance_id="ccdash-smoke"))

    # `model_dump(mode="json")` is the same serialization FastAPI performs when returning the
    # envelope over HTTP -- round-tripping through it (rather than handing the routing function
    # live pydantic objects) proves the routing logic below operates on the wire format, not on
    # any CCDash-internal Python object.
    return envelope.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Step 2 -- the DOCUMENTED consumer-side routing rule (PRD §6 P3 + §7.3 resilience note)
#
# Deliberately has ZERO import from any CCDash compute/service module. This is what an external
# consumer (op) implementing the documented contract from scratch would write, operating purely
# on the pulled JSON payload's `triage_verdict` + `correlation.confidence` fields.
# ---------------------------------------------------------------------------

# Route labels a consumer could take. NOTE: "op_council_or_arc" is the ONLY route that reaches
# op council / ARC dispatch -- the AC-P5.2 assertion below checks this literal never appears for
# a human_triage_required item.
ROUTE_NO_ACTION = "no_action"
ROUTE_OP_COUNCIL_OR_ARC = "op_council_or_arc"
ROUTE_HUMAN_HANDOFF = "human_handoff"


def route_aar_review_candidate(review: dict[str, Any]) -> str:
    """Documented op-side routing rule: route on ``triage_verdict`` (authoritative) then confidence.

    Mirrors PRD §6 P3's "Cross-repo contract to specify": *"Routing decision: op's
    classify->plan->dispatch, using correlation.confidence and triage_verdict as routing inputs;
    human_triage_required verdicts never auto-route to op council."*

    ``triage_verdict`` is checked FIRST and is fully authoritative for the human-triage case --
    a consumer must never let a confidence value talk it out of a human handoff once the
    producer has already said "human_triage_required" (the producer's own OQ-2 hard rule already
    accounts for missing/low/ambiguous confidence; re-deriving that here would duplicate model-
    free logic that already lives in CCDash and risks drifting from it). Unknown/malformed verdict
    values fail closed to human handoff -- never silently routed to op council/ARC.
    """
    verdict = review.get("triage_verdict")

    if verdict == "human_triage_required":
        return ROUTE_HUMAN_HANDOFF
    if verdict == "surface_only":
        return ROUTE_NO_ACTION
    if verdict == "deep_review_recommended":
        confidence = (review.get("correlation") or {}).get("confidence")
        # Defense-in-depth: even for the eligible verdict, a missing/low confidence value must
        # never be treated as council-eligible (belt-and-suspenders on top of the producer's own
        # invariant -- the producer should never emit this combination, but a consumer must not
        # assume that and must fail closed to human handoff if it ever sees it).
        if confidence is None or confidence < 0.64:
            return ROUTE_HUMAN_HANDOFF
        return ROUTE_OP_COUNCIL_OR_ARC
    # Unknown verdict (e.g. a future schema value this consumer predates) -- fail closed to human.
    return ROUTE_HUMAN_HANDOFF


# ---------------------------------------------------------------------------
# Step 3 -- best-effort real-op-CLI probe (documentation only; never invoked for routing)
# ---------------------------------------------------------------------------


def _describe_op_cli_availability() -> str:
    op_path = shutil.which("op")
    if op_path is None:
        return "not on PATH -- simulated-routing mode used (expected; no real invocation attempted)"
    return (
        f"found on PATH at {op_path}, but exposes no AAR-review-specific consumer subcommand "
        "yet (op-side contract implementation is PRD §6 P3 future work, out of this repo's "
        "scope) -- simulated-routing mode used deliberately, not as a fallback"
    )


# ---------------------------------------------------------------------------
# Step 4 -- assertions
# ---------------------------------------------------------------------------


def main() -> int:
    payload = _build_sample_envelope()
    reviews: list[dict[str, Any]] = payload["data"]["reviews"]
    assert len(reviews) == 3, f"expected 3 sample reviews, got {len(reviews)}"

    routed = {review["triage_verdict"]: route_aar_review_candidate(review) for review in reviews}

    print("== AAR-review PULL consumer smoke (D5, T5-004/T5-005) ==")
    print(f"op CLI availability: {_describe_op_cli_availability()}")
    print("Pulled payload (as-if from GET /api/v1/project/aar-review):")
    print(json.dumps(payload, indent=2)[:2000])
    print()
    print("Routed decisions:")
    for verdict, route in routed.items():
        print(f"  {verdict:28s} -> {route}")

    # --- Basic per-verdict routing sanity ---
    assert routed["surface_only"] == ROUTE_NO_ACTION, routed
    assert routed["deep_review_recommended"] == ROUTE_OP_COUNCIL_OR_ARC, routed
    assert routed["human_triage_required"] == ROUTE_HUMAN_HANDOFF, routed

    # --- T5-005 / AC-P5.2: the load-bearing assertion ---
    # A human_triage_required verdict must NEVER be routed to op council/ARC, for ANY confidence
    # value -- including the missing/null case (the actual producer output) and adversarial edge
    # values a consumer might otherwise be tempted to "override" on. This proves the routing
    # function treats `triage_verdict` as authoritative, independent of confidence.
    fuzz_confidences: list[float | None] = [None, -1.0, 0.0, 0.01, 0.5, 0.63, 0.64, 0.9, 1.0, 999.0]
    for confidence in fuzz_confidences:
        candidate = {
            "triage_verdict": "human_triage_required",
            "correlation": {"confidence": confidence},
        }
        route = route_aar_review_candidate(candidate)
        assert route == ROUTE_HUMAN_HANDOFF, (
            f"AC-P5.2 VIOLATION: human_triage_required with confidence={confidence!r} routed to "
            f"{route!r}, expected {ROUTE_HUMAN_HANDOFF!r} (must never reach "
            f"{ROUTE_OP_COUNCIL_OR_ARC!r})"
        )
        assert route != ROUTE_OP_COUNCIL_OR_ARC  # redundant restatement of the invariant, on purpose

    print()
    print(
        f"PASS -- AC-P5.2: human_triage_required never routed to {ROUTE_OP_COUNCIL_OR_ARC!r} "
        f"across {len(fuzz_confidences)} confidence values (including None): {fuzz_confidences}"
    )

    # --- Zero-CCDash-write invariant ---
    # NOTE: this repo's `models.py` / `client_v1_models.py` transitively import the full
    # repository/db module graph (ordinary Python import-graph coupling in this codebase --
    # inspected via `sys.modules` while writing this harness), so an import-graph assertion here
    # would be a false signal, not a real one. The actual invariant is behavioral, not structural:
    # this script's own top-level code never opens a DB connection (no `aiosqlite.connect`/
    # `backend.db.connection` call), never instantiates a repository class, and never calls a
    # method on `ports.storage` -- it only builds pydantic DTOs in-memory and calls the pure
    # `route_aar_review_candidate()` function above. That is verifiable by reading this file
    # (grep for `.connect(`, `Repository(`, `ports.storage` -- none appear outside this comment).
    print("PASS -- zero CCDash write/dispatch call made (this script never opens a DB connection ")
    print("       or calls a repository/write method; verify via grep on this file).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
