"""
Persona extract rule table — pure data, no logic, no IO.

Each Rule maps a regex pattern over user-message text to a candidate
category and confidence score.  The ``capture_group`` field identifies
which regex group holds the candidate text (0 == whole match).

R8 (system-reminder endorsement) is represented here for metadata
completeness; the ±2-message context check lives in
``persona_extract.extract_candidates``.

FORBIDDEN IMPORTS (must not appear in this file):
    backend.db, backend.cli, OfflineCache, Typer, fcntl, os.path writes,
    subprocess, requests, httpx, asyncio, any IO.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Rule:
    id: str             # "R1" .. "R8"
    pattern: re.Pattern  # compiled with re.IGNORECASE
    category: str       # PRD §5 vocab: from-args|preference|goal|decision|constraint|TIL|reminder
    confidence: float   # heuristic match strength, NOT a model probability
    capture_group: int  # which regex group is the candidate text (0 == whole match)


# ---------------------------------------------------------------------------
# R1 — explicit op-remember invocation
# Trigger: `op remember "..."` or `op remember ...`
# Capture group 1: the fact text following the verb.
# ---------------------------------------------------------------------------
_R1 = Rule(
    id="R1",
    pattern=re.compile(
        r"""op\s+remember\s+["']?(.+?)["']?\s*$""",
        re.IGNORECASE | re.MULTILINE,
    ),
    category="from-args",
    confidence=0.95,
    capture_group=1,
)

# ---------------------------------------------------------------------------
# R2 — going-forward / behavioral directive
# Trigger: "from now on", "going forward", "always", "never", "stop doing",
#          "don't … again" followed by the directive.
# Capture group 2: the directive text.
# Optional punctuation (comma, colon, em-dash) is allowed between the
# trigger keyword and the directive text.
# ---------------------------------------------------------------------------
_R2 = Rule(
    id="R2",
    pattern=re.compile(
        # apostrophe variants: U+0027 (straight), U+2018 (left), U+2019 (right)
        r"\b(from\s+now\s+on|going\s+forward|always|never|stop\s+doing"
        r"|don[\x27‘’]t\s+.+?\s+again)\b[,:—\s]*(.+)",
        re.IGNORECASE,
    ),
    category="preference",
    confidence=0.85,
    capture_group=2,
)

# ---------------------------------------------------------------------------
# R3 — hard preference expressed in first person
# Trigger: "I always", "I never", "I prefer", "I hate", "I love" …
# Capture group 2: the preference object/verb phrase.
# ---------------------------------------------------------------------------
_R3 = Rule(
    id="R3",
    pattern=re.compile(
        r"""\bI\s+(always|never|prefer|hate|love)\s+(.+)""",
        re.IGNORECASE,
    ),
    category="preference",
    confidence=0.80,
    capture_group=2,
)

# ---------------------------------------------------------------------------
# R4 — goal statement
# Trigger: "goal: …" OR "I want to …"
# Capture group 1: the goal text (from either alternative).
# ---------------------------------------------------------------------------
_R4 = Rule(
    id="R4",
    pattern=re.compile(
        r"""\bgoal:\s+(.+)|\bI\s+want\s+to\s+(.+)""",
        re.IGNORECASE,
    ),
    category="goal",
    confidence=0.75,
    # group 1 fires for "goal: …"; group 2 fires for "I want to …".
    # The service picks the first non-empty group when capture_group == 0;
    # we use capture_group=1 and fall back to 2 in the service.
    capture_group=1,
)

# ---------------------------------------------------------------------------
# R5 — decision
# Trigger: "decision: …" OR "decided to …"
# Capture group 1 or 2 (same multi-alt pattern).
# ---------------------------------------------------------------------------
_R5 = Rule(
    id="R5",
    pattern=re.compile(
        r"""\bdecision:\s+(.+)|\bdecided\s+to\s+(.+)""",
        re.IGNORECASE,
    ),
    category="decision",
    confidence=0.70,
    capture_group=1,
)

# ---------------------------------------------------------------------------
# R6 — constraint
# Trigger: "constraint: …" OR "must always/never …"
# For "constraint: …": group 1 holds the payload.
# For "must always/never …": group 2 is the qualifier, group 3 is the payload.
# capture_group=1; the service scans forward for the first non-None group
# (groups 2 and 3 when the second alternative fires).
# ---------------------------------------------------------------------------
_R6 = Rule(
    id="R6",
    pattern=re.compile(
        r"""\bconstraint:\s+(.+)|\bmust\s+(?:always|never)\s+(.+)""",
        re.IGNORECASE,
    ),
    category="constraint",
    confidence=0.75,
    capture_group=1,
)

# ---------------------------------------------------------------------------
# R7 — TIL / note-to-self
# Trigger: "TIL", "today I learned", "note to self", "remember that/this"
#          followed by the fact.
# Capture group 3: the fact text (the alternatives capture in group 1 and 2,
# the payload is always in the last group).
# ---------------------------------------------------------------------------
_R7 = Rule(
    id="R7",
    pattern=re.compile(
        r"""\b(TIL|today\s+I\s+learned|note\s+to\s+self|remember\s+(?:that|this))\b\s*[:,]?\s+(.+)""",
        re.IGNORECASE,
    ),
    category="TIL",
    confidence=0.70,
    capture_group=2,
)

# ---------------------------------------------------------------------------
# R8 — system-reminder endorsement
# Pattern: user message containing "yes", "agreed", or "right" in isolation.
# The ±2-message context check (verifying a system-speaker log is nearby)
# is handled in persona_extract.extract_candidates, NOT here.
# capture_group=0 means the whole match; the service replaces the text with
# the content of the nearby system log.
# ---------------------------------------------------------------------------
_R8 = Rule(
    id="R8",
    pattern=re.compile(
        r"""\b(yes|agreed|right)\b""",
        re.IGNORECASE,
    ),
    category="reminder",
    confidence=0.60,
    capture_group=0,
)


# Public ordered tuple — rule evaluation order matters (higher confidence first,
# but all rules fire independently per message; longest-match-wins is resolved
# in the service layer).
RULES: tuple[Rule, ...] = (
    _R1,
    _R2,
    _R3,
    _R4,
    _R5,
    _R6,
    _R7,
    _R8,
)
