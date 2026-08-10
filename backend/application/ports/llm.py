"""Text-completion port: a typed seam over the raw httpx call sites.

P1 of the hosted-LLM-provider strategy
(``docs/project_plans/spikes/hosted-llm-provider-strategy.md`` Sec Phased
Implementation Shape) introduces a single ``TextCompletionPort`` protocol +
``PromptEnvelope`` value type that the two derived-naming backends
(``session_naming_local_backend``, ``session_naming_hosted_backend``) and
``ai_insight`` construct and pass to a provider adapter
(``backend/adapters/llm/``), instead of each carrying its own near-duplicate
httpx block. This is a PURE TRANSPORT REFACTOR -- no new provider, no new
egress, no config surface. See the contract at
``docs/project_plans/feature_contracts/refactors/textcompletionport-seam-p1.md``.

``PromptEnvelope`` is an in-memory, request-scoped value object -- never
persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "TextCompletionPort",
    "PromptProvenance",
    "PromptEnvelope",
    "envelope_from_aggregate",
    "envelope_from_redacted_transcript",
    "EGRESS_ALLOWED_PROVENANCE",
    "enforce_egress_provenance",
]


class PromptProvenance(StrEnum):
    """Where a :class:`PromptEnvelope`'s text originated.

    ``AGGREGATE`` -- aggregated, non-transcript dashboard metrics/summaries
    (``ai_insight.py``'s use case). ``TRANSCRIPT_REDACTED`` -- text derived
    from a session transcript that has already passed through
    ``agent_queries.redaction.redact_entries`` (both derived-naming lanes'
    use case). Distinguishing the two lets a future phase (P2/P3) apply
    provenance-specific policy (e.g. consent gating) without re-deriving
    which call sites carry transcript-derived content.
    """

    AGGREGATE = "aggregate"
    TRANSCRIPT_REDACTED = "transcript_redacted"


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    """The text a :class:`TextCompletionPort` adapter sends to a provider.

    ``text`` is the fully-formed instruction/prompt string -- callers build
    it (including any instruction-wrapping) before constructing the
    envelope; an adapter's :meth:`TextCompletionPort.complete` sends
    ``envelope.text`` verbatim, it does not reformat it.
    """

    text: str
    provenance: PromptProvenance
    redaction_events: int = 0


@runtime_checkable
class TextCompletionPort(Protocol):
    """A provider-agnostic single-shot text-completion call."""

    async def complete(self, envelope: PromptEnvelope) -> str | None:
        """Send ``envelope.text`` to the provider; return the raw completion.

        Raises on transport/HTTP error -- callers own the fail-open
        wrapping, matching this codebase's existing convention of
        separating "the call" from "the fail-open guarantee"
        (``ai_insight.generate_dashboard_insight``'s try/except-at-the-
        call-site shape; ``LocalOllamaNamingBackend``/``HostedGeminiNamingBackend``'s
        identical division of labor pre-P1).
        """
        ...


def envelope_from_aggregate(text: str) -> PromptEnvelope:
    """Build an envelope for aggregated, non-transcript content.

    Used by ``ai_insight.generate_dashboard_insight``, which sends only
    aggregated dashboard metrics/task summaries -- never transcript content
    -- per that module's own docstring.
    """
    return PromptEnvelope(text=text, provenance=PromptProvenance.AGGREGATE)


def envelope_from_redacted_transcript(text: str, redaction_events: int = 0) -> PromptEnvelope:
    """Build an envelope for text derived from an already-redacted transcript.

    Fail-closed at the egress boundary: refuses to build a
    transcript-derived envelope while
    ``CCDASH_REDACTION_PATTERNS_ENABLED`` is off, converting the read
    path's existing fail-open-on-read posture into fail-closed-on-egress
    for this specific seam, per the spike proposal. The redaction import is
    LOCAL (deferred to call time), not module-level -- mirrors
    ``session_naming_local_backend.resolve_naming_backend``'s own documented
    reason for a local import: avoiding a module-load-time cycle between
    ``backend.application.ports`` (imported by
    ``agent_queries.session_detail``, which the ``agent_queries`` package
    ``__init__`` re-exports) and ``agent_queries.redaction`` itself.
    """
    from backend.application.services.agent_queries.redaction import (
        redaction_patterns_enabled,
    )

    if not redaction_patterns_enabled():
        raise RuntimeError(
            "envelope_from_redacted_transcript: refusing to build a "
            "transcript-derived prompt envelope while "
            "CCDASH_REDACTION_PATTERNS_ENABLED is off -- fail-closed at the "
            "egress boundary (never sends unredacted, never sends at all "
            "once the gate is off)."
        )
    return PromptEnvelope(
        text=text,
        provenance=PromptProvenance.TRANSCRIPT_REDACTED,
        redaction_events=redaction_events,
    )


# hosted-llm-anthropic-ica-lane-v1 M2: the full vocabulary of provenance
# values ever cleared to leave the process. Today this is BOTH members of
# ``PromptProvenance`` -- there is no "raw, unredacted" provenance value in
# this codebase's vocabulary at all, by construction
# (``envelope_from_redacted_transcript`` already refuses to build one while
# redaction is off). This constant exists so a FUTURE provenance value can
# be added to ``PromptProvenance`` without it silently becoming
# egress-eligible -- it must be added here too, explicitly.
EGRESS_ALLOWED_PROVENANCE: frozenset[PromptProvenance] = frozenset(
    {PromptProvenance.AGGREGATE, PromptProvenance.TRANSCRIPT_REDACTED}
)


def enforce_egress_provenance(envelope: PromptEnvelope) -> None:
    """Raise unless ``envelope.provenance`` is cleared to leave the box.

    Every ``TextCompletionPort`` adapter that performs egress (marked
    ``EGRESS = True`` -- see ``backend/adapters/llm/gemini.py``) calls this
    at the very top of :meth:`TextCompletionPort.complete`, before building
    a URL/payload or opening any connection, so a caller that constructs a
    :class:`PromptEnvelope` with a provenance value outside
    ``EGRESS_ALLOWED_PROVENANCE`` can never reach the network -- this is a
    hard raise, not a fail-open no-op, because reaching this function with a
    disallowed provenance means a caller bypassed (or a future refactor
    broke) every earlier gate; the adapter is the last line of defense
    before the process boundary.

    Local-only adapters (e.g. Ollama, ``EGRESS = False``) never call this --
    a loopback call has nothing off-box to protect.
    """
    if envelope.provenance not in EGRESS_ALLOWED_PROVENANCE:
        raise ValueError(
            "enforce_egress_provenance: refusing to send an envelope with "
            f"provenance={envelope.provenance!r} off-box -- only "
            f"{sorted(p.value for p in EGRESS_ALLOWED_PROVENANCE)} may leave "
            "the box."
        )
