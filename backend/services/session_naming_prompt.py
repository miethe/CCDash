"""Shared prompt-building/output-validation for the M3 derived-naming backends.

Both Lane A (``session_naming_local_backend.LocalOllamaNamingBackend``, T3-002)
and Lane B (``session_naming_hosted_backend.HostedGeminiNamingBackend``,
T3-003) turn a candidate session's *already-redacted* transcript excerpt into
a bounded model prompt, then validate the raw completion before it may be
stored. That excerpt-building and output-validation logic is backend-agnostic
-- it does not know or care whether the completion came from a local Ollama
daemon or a hosted Gemini call -- so it lives here once rather than as two
near-duplicate copies (per this feature's own rubric: "extend what exists
rather than adding parallel machinery").

Both functions operate on data the caller has already fetched via
``session_detail.get_session_detail`` (which runs every transcript entry
through ``agent_queries.redaction.redact_entries`` before returning it) --
this module never reads a transcript itself and has no I/O of its own.

P1 (TextCompletionPort seam) DEVIATION -- ``build_prompt_text`` still returns
``str``, not ``PromptEnvelope``, though the P1 scope line called for the
retype. Recorded here deliberately so a later phase does not read the seam as
accidentally inconsistent:

1. This function returns the transcript *excerpt*, not the prompt. Each
   backend wraps that excerpt in its own instruction template, and it is the
   wrapped ``instruction`` string that is actually sent. An envelope built
   here would therefore carry the wrong text -- provenance would describe the
   excerpt while the adapter transmitted something else.
2. ``PromptEnvelope.redaction_events`` is not derivable from this signature
   (``items`` alone). Threading a real count out of ``get_session_detail`` is
   P2/P3 scope; inventing one here would be worse than passing 0.

So the envelope is constructed at each call site instead, and the two lanes
differ ON PURPOSE: Lane B (hosted, off-box egress) goes through
``envelope_from_redacted_transcript``'s fail-closed redaction gate, while
Lane A (local Ollama, loopback-only, zero egress by construction) builds the
envelope directly -- it never consulted that flag before P1, so gating it
would be an untested behaviour change, which P1 forbids. Revisit in P3, where
the redaction-count thread and a third (Anthropic/ICA) lane both land.
"""
from __future__ import annotations

import logging
import re
from typing import Any

__all__ = [
    "build_prompt_text",
    "sanitize_title",
    "MAX_TITLE_LENGTH",
    "REJECT_ABOVE_LENGTH",
    "MAX_PROMPT_CHARS",
    "MAX_PROMPT_ITEMS",
]

logger = logging.getLogger("ccdash.services.session_naming_prompt")

# ── Output-validation bounds ─────────────────────────────────────────────────
# Target length for a stored title.
MAX_TITLE_LENGTH = 100
# Anything longer than this is not a "long title that needs truncating" -- it
# is non-conforming output (e.g. the model echoed back a paragraph or the
# whole prompt). Rejected outright (return None) rather than truncated, so a
# clearly-wrong completion never becomes a plausible-looking stored name.
REJECT_ABOVE_LENGTH = 400
# Upper bound on how much transcript text is fed into the prompt. Keeps the
# inference call bounded regardless of how large the session is.
MAX_PROMPT_CHARS = 4000
# How many transcript entries (earliest-first) are considered as candidate
# prompt material before the character bound above is applied.
MAX_PROMPT_ITEMS = 8

_QUOTE_CHARS = "\"'“”‘’`"


def build_prompt_text(items: list[dict[str, Any]]) -> str:
    """Build a bounded prompt excerpt from a session's (already-redacted) transcript.

    Prefers human/assistant message content (the parts of a transcript that
    actually describe what a session was about) over tool-call noise, but
    falls back to whatever text content is present if no such entries are
    found -- some sessions may not carry the speaker labels this heuristic
    prefers. Returns ``""`` when no usable text is found (caller treats that
    as "nothing to name," not an error).
    """
    preferred_speakers = {"user", "human", "assistant"}

    def _collect(predicate: Any) -> list[str]:
        collected: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            text = content.strip()
            if not text or not predicate(item):
                continue
            collected.append(text)
            if len(collected) >= MAX_PROMPT_ITEMS:
                break
        return collected

    pieces = _collect(
        lambda item: str(item.get("speaker") or "").strip().lower() in preferred_speakers
    )
    if not pieces:
        # Resilient fallback: no speaker-labeled entries matched -- take any
        # entry with string content rather than yielding an empty prompt.
        pieces = _collect(lambda _item: True)

    joined = "\n".join(pieces).strip()
    if len(joined) > MAX_PROMPT_CHARS:
        joined = joined[:MAX_PROMPT_CHARS]
    return joined


def sanitize_title(raw: str | None) -> str | None:
    """Validate and bound a raw model completion before it may be stored.

    Returns ``None`` (never a fallback string) for empty output or output
    that is wildly non-conforming (over ``REJECT_ABOVE_LENGTH``) -- rejected
    outright rather than stored raw or silently truncated into something
    that still looks plausible. Conforming-but-long output is truncated to
    ``MAX_TITLE_LENGTH``, matching this feature's existing truncation
    convention (no ellipsis appended, per the M2 fallback-chain precedent).
    """
    if not raw:
        return None
    # Only the first line -- a multi-line completion is not a title.
    first_line = raw.strip().splitlines()[0] if raw.strip() else ""
    text = first_line.strip().strip(_QUOTE_CHARS).strip()
    # Collapse internal whitespace/control characters into single spaces.
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) > REJECT_ABOVE_LENGTH:
        logger.warning(
            "session_naming_prompt: rejecting non-conforming model output "
            "(len=%d > reject threshold %d)",
            len(text),
            REJECT_ABOVE_LENGTH,
        )
        return None
    if len(text) > MAX_TITLE_LENGTH:
        text = text[:MAX_TITLE_LENGTH].rstrip()
    return text or None
