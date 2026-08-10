"""Pure logic for ICA per-session key identity and dollar-spend attribution (v51).

Two dimensions the launch-time capture sidecar could not carry are captured for
ICA-launched sessions: WHICH ICA key ran the session (``ica_key``, the key NAME
CC1..CC6 — never secret bytes) and how many DOLLARS it cost. Spend is read from
the ``x-litellm-key-spend`` response header of the ICA gateway, which reports a
**cumulative-per-key** running total (dollars) shared across *every* request that
key makes — all sessions, all machines. So a lone session's cost is the delta
between its start reading and its end reading, and that delta is honest **only if
no other request hit the same key in between**.

This module is intentionally standalone and pure (no DB / IO / network). It:

* parses a raw ``x-litellm-key-spend`` header string into a float,
* decides whether a start→end delta is *attributable* to one session, and
* names the reason it is not, from a closed vocabulary.

Attribution vocabulary (``sessions.ica_spend_attribution``)
-----------------------------------------------------------
=========================== =================================================
Token                       Meaning
=========================== =================================================
``attributed``              Both readings parsed, key unchanged, and no other
                            session shared the key during this session's
                            window. ``ica_spend_delta`` = end - start.
``concurrent_shared_key``   Another session used the same ``ica_key`` with an
                            overlapping [start, end] window. The cumulative
                            counter moved for reasons outside this session, so
                            the delta is **unattributable** — stored NULL,
                            never silently divided among the sharers.
``key_changed``             The key identity differed between the start and end
                            readings (mid-session key rotation). The two
                            readings are counters for *different* keys, so
                            their difference is meaningless — delta NULL.
``incomplete_readings``     One or both readings are missing or unparseable
                            (e.g. the gateway probe failed). Delta NULL.
=========================== =================================================

Contract
--------
* ``ica_key`` is a key NAME, never a token. Unset == NULL, **never defaulted**
  to ``CC1`` (a wrong attribution is worse than an absent one).
* ``ica_spend_delta`` is populated **only** for the ``attributed`` verdict;
  every other verdict stores NULL. "Never silently divided" (AC3) is enforced
  here by construction: there is no code path that emits a non-null delta for a
  contaminated window.
* Raw readings (``ica_spend_start`` / ``ica_spend_end``) are stored verbatim as
  strings so the exact header value is preserved without float round-trip.
* Consumers MUST treat an unrecognised attribution token as "unknown" rather
  than hard-failing — the vocabulary may grow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

#: Delta equals end - start; window provably exclusive to this session.
ICA_SPEND_ATTRIBUTED: Final[str] = "attributed"
#: Another session shared the key during an overlapping window — delta NULL.
ICA_SPEND_CONCURRENT_SHARED_KEY: Final[str] = "concurrent_shared_key"
#: Key identity changed between the start and end readings — delta NULL.
ICA_SPEND_KEY_CHANGED: Final[str] = "key_changed"
#: One or both readings absent/unparseable — delta NULL.
ICA_SPEND_INCOMPLETE_READINGS: Final[str] = "incomplete_readings"

#: The closed set, for validation and tests. Consumers still must not hard-fail
#: on an unrecognised token (forward-compat), but writers only emit these.
ICA_SPEND_ATTRIBUTION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        ICA_SPEND_ATTRIBUTED,
        ICA_SPEND_CONCURRENT_SHARED_KEY,
        ICA_SPEND_KEY_CHANGED,
        ICA_SPEND_INCOMPLETE_READINGS,
    }
)


def parse_spend_reading(raw: Optional[str]) -> Optional[float]:
    """Parse a raw ``x-litellm-key-spend`` header value into a float.

    Returns ``None`` for ``None``, empty/whitespace, or any unparseable value.
    Negative values are rejected (a cumulative counter is monotonic and
    non-negative); a negative reading signals a corrupt capture, not a real
    spend, so it is treated as unparseable.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


@dataclass(frozen=True)
class SpendVerdict:
    """Outcome of an attribution decision.

    ``delta`` is a float only for the ``attributed`` verdict; ``None`` otherwise.
    ``attribution`` is always one token from the closed vocabulary.
    """

    attribution: str
    delta: Optional[float] = None

    @property
    def delta_str(self) -> Optional[str]:
        """The delta rendered for TEXT storage, or ``None`` when unattributable."""
        if self.delta is None:
            return None
        # repr(float) round-trips exactly; strip a trailing ".0" is unnecessary —
        # keep full precision so re-parsing the column recovers the same value.
        return repr(self.delta)


def decide_attribution(
    *,
    start_reading: Optional[str],
    end_reading: Optional[str],
    key_changed: bool = False,
    shared_key_overlap: bool = False,
) -> SpendVerdict:
    """Decide the spend attribution for a single session.

    Precedence (first match wins):

    1. ``incomplete_readings`` — either reading missing/unparseable, or the end
       reading is *below* the start reading (a cumulative counter cannot go
       backwards for the same key; treat as corrupt rather than invent a
       negative cost).
    2. ``key_changed`` — the caller observed different key identities at start
       and end.
    3. ``concurrent_shared_key`` — another session shared the key during an
       overlapping window.
    4. ``attributed`` — none of the above; delta = end - start.

    Note ``incomplete_readings`` and ``key_changed`` are checked before the
    concurrency guard so a genuinely uncomputable delta is never mislabelled as
    a merely-contaminated one.
    """
    start = parse_spend_reading(start_reading)
    end = parse_spend_reading(end_reading)

    if start is None or end is None or end < start:
        return SpendVerdict(ICA_SPEND_INCOMPLETE_READINGS)

    if key_changed:
        return SpendVerdict(ICA_SPEND_KEY_CHANGED)

    if shared_key_overlap:
        return SpendVerdict(ICA_SPEND_CONCURRENT_SHARED_KEY)

    return SpendVerdict(ICA_SPEND_ATTRIBUTED, delta=end - start)


def windows_overlap(
    a_start: Optional[str],
    a_end: Optional[str],
    b_start: Optional[str],
    b_end: Optional[str],
) -> bool:
    """True if two half-open time windows [start, end) overlap.

    Inputs are ISO-8601 strings (or ``None``). A window with a missing bound is
    treated conservatively as *open* on that side — an unknown end means "still
    possibly running", which can overlap anything at or after its start. Purely
    lexicographic comparison of normalized ISO-8601 UTC strings is sufficient
    for overlap and avoids importing a datetime parser into this pure module;
    callers already normalize timestamps to the same ISO-8601 shape at ingest.
    """
    # Missing start on either side → cannot establish separation → assume overlap.
    if not a_start or not b_start:
        return True
    a_lo = a_start
    a_hi = a_end or "9999-12-31T23:59:59Z"
    b_lo = b_start
    b_hi = b_end or "9999-12-31T23:59:59Z"
    # Overlap iff a starts before b ends AND b starts before a ends.
    return a_lo < b_hi and b_lo < a_hi
