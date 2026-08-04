"""Canonical vocabulary for ``sessions.skill_name_source`` (subagent-skill-inheritance).

``sessions.skill_name`` is populated either by direct detection (the session's own
transcript produced a non-None ``_primary_skill_name`` result) or by inheritance
(copied from the parent session's ``skill_name`` because this session's own value
was NULL). Those two origins differ in trustworthiness — a subagent may do work
unrelated to its parent's skill — so a rollup or UI surface must be able to tell
them apart rather than treat every non-null ``skill_name`` as directly observed.
This module is the single source of truth for the token vocabulary that
distinguishes them, mirroring ``backend/parsers/effort_provenance.py`` (the Gap 4 /
schema v44 precedent) shape-for-shape.

Trust ordering (strongest first)
---------------------------------
=========================== =================================================
Token                       Meaning / strength
=========================== =================================================
``directly_detected``       The session's own transcript produced a non-None
                            skill detection. Strongest signal — observed, not
                            derived.
``inherited_parent``        Copied from the parent session's ``skill_name``
                            because this session's own value was NULL. One hop
                            only (never a grandparent or the family root — see
                            the transitivity decision below). Weaker: the
                            inference is auditable and reversible, but it is
                            not itself an observation.
=========================== =================================================

Token naming note
------------------
The subagent-skill-inheritance Feature Contract's expansion originally proposed
``inherited_from_parent`` for the second token. This module deliberately uses
``inherited_parent`` instead, matching the spelling already declared (but
unused) at ``effort_provenance.EFFORT_SOURCE_INHERITED_PARENT`` — per that
contract's Architecture Constraint 7 ("added at Opus sanity review 2026-08-03"),
which recommends matching the existing spelling rather than introducing a second
near-identical token for the same concept across sibling provenance vocabularies.
Two spellings for "derived from a parent session" is exactly the kind of drift
that costs a future reader an hour; this module does not repeat that mistake.

Transitivity decision (one hop only)
-------------------------------------
Inheritance walks exactly one hop: a child inherits only its direct
``subagent_parent_id``'s ``skill_name``, never a grandparent or the family root.
Rationale (see the Feature Contract's Implementation Notes §6 for the full
argument): the measured 51.3% baseline this work is scored against is itself a
one-hop join; both feasibility spikes measured only the one-hop yield; and a
multi-hop walk would need cycle/depth guards against an uncharacterized dataset
for no measured additional gain. An orphaned subagent whose immediate parent is
also NULL stays NULL, even if a grandparent has a skill — a known, accepted
boundary, not a gap this module closes.

Contract
--------
* ``skill_name_source`` is written **only** where ``skill_name`` itself is, and
  always together with it. A non-null ``skill_name`` with a null ``source``
  means the row predates this column (provenance unknown) — a legitimate
  contract state, never backfilled or guessed.
* A null ``skill_name`` always carries a null ``source``.
* Direct detection always outranks inheritance: the inheritance backfill/write
  path MUST NOT overwrite a row whose ``skill_name`` is already non-null.
* Tokens are stored verbatim. Consumers MUST treat an unrecognised token as
  "unknown provenance" rather than hard-failing — the vocabulary may grow.

This module is standalone (no cross-import from ``effort_provenance``) because
the two provenance columns are independent contract states for independent
capture facts; the trust-order duplication is intentional, not drift.
"""
from __future__ import annotations

from typing import Final

#: The session's own transcript produced a non-None skill detection.
SKILL_SOURCE_DIRECT: Final[str] = "directly_detected"

#: Copied from the parent session's skill_name (one hop only).
SKILL_SOURCE_INHERITED_PARENT: Final[str] = "inherited_parent"

#: Every token this codebase may write, in trust order (strongest first).
SKILL_SOURCE_TRUST_ORDER: Final[tuple[str, ...]] = (
    SKILL_SOURCE_DIRECT,
    SKILL_SOURCE_INHERITED_PARENT,
)

#: Membership set for validation / test assertions.
KNOWN_SKILL_SOURCES: Final[frozenset[str]] = frozenset(SKILL_SOURCE_TRUST_ORDER)
