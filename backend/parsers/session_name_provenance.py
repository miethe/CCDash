"""Canonical vocabulary for ``sessions.session_name_source`` (automatic-session-naming).

``sessions.session_name`` will be populated from several lanes that differ sharply
in trustworthiness: a name the provider itself persisted into the transcript
(Claude Code's ``ai-title`` record, Codex's ``thread_name_updated`` event) versus a
name this codebase derives deterministically (subagent-parent inheritance,
``git.branch``, a truncated first message) versus a name a model generates from
transcript content. A consumer must be able to tell those apart rather than treat
every non-null ``session_name`` as equally authoritative. This module is the single
source of truth for the token vocabulary that distinguishes them, mirroring
``backend/parsers/skill_provenance.py`` / ``backend/parsers/effort_provenance.py``
(the ``skill_name_source`` / ``effort_tier_source`` precedents, schema v49 / v44)
shape-for-shape.

Trust ordering (strongest first)
---------------------------------
=============================== =========================================
Token                           Meaning / strength
=============================== =========================================
``provider_persisted``          The name came straight from the provider's
                                 own transcript record (Claude Code
                                 ``ai-title``, Codex ``thread_name_updated``).
                                 Strongest signal — observed, not derived.
``derived_deterministic``       Computed by a deterministic rule with no
                                 model call (subagent-parent inheritance,
                                 ``git.branch``, truncated first message).
                                 Weaker than a provider name, but reversible
                                 and auditable.
``derived_embedding_transfer``  RESERVED, unused. Reserved for a future
                                 embedding k-NN title-transfer lane
                                 (deferred; see the implementation plan's
                                 Lane C). No code path writes this token yet.
``derived_generative``          Produced by a model call over transcript
                                 content (the worker-side naming sweep).
                                 Weakest signal — plausible, not observed or
                                 mechanically derived.
=============================== =========================================

``operator_set`` (a human explicitly renamed the session) is declared here as a
RESERVED token, outside the ranked vocabulary above, for the same reason: the
rename-UI follow-on is out of scope for this plan, but the vocabulary should be
closed against it now rather than drift later. No code path writes it yet.

Contract
--------
* ``session_name_source`` is written **only** where ``session_name`` itself is,
  and always together with it. A non-null name with a null source means the row
  predates this column (provenance unknown) — a legitimate contract state, never
  backfilled or guessed.
* A null ``session_name`` always carries a null source.
* A weaker source must never overwrite a stronger one. Use ``session_name_rank``
  (or ``may_overwrite``) to enforce that at every write site — never duplicate
  the ordering inline.
* Tokens are stored verbatim. Consumers MUST treat an unrecognised token as
  "unknown provenance" (rank ``None``) rather than hard-failing — the vocabulary
  may grow.

This module is standalone (no cross-import from ``skill_provenance`` or
``effort_provenance``) because each provenance column is an independent contract
state for an independent capture fact; the trust-order duplication is
intentional, not drift.
"""
from __future__ import annotations

from typing import Final

#: The name came directly from the provider's own transcript record
#: (Claude Code ``ai-title``, Codex ``thread_name_updated``).
SESSION_NAME_SOURCE_PROVIDER_PERSISTED: Final[str] = "provider_persisted"

#: Computed by a deterministic, model-free rule (subagent-parent inheritance,
#: ``git.branch``, truncated first message).
SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC: Final[str] = "derived_deterministic"

#: RESERVED, unused. Future embedding k-NN title-transfer lane (deferred).
SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER: Final[str] = "derived_embedding_transfer"

#: Produced by a model call over transcript content (worker-side naming sweep).
SESSION_NAME_SOURCE_DERIVED_GENERATIVE: Final[str] = "derived_generative"

#: RESERVED, unused. A human explicitly renamed the session (rename-UI follow-on).
#: Deliberately NOT part of SESSION_NAME_SOURCE_TRUST_ORDER: an operator override
#: is out-of-band with respect to the automated lanes above, not a rung on their
#: ladder.
SESSION_NAME_SOURCE_OPERATOR_SET: Final[str] = "operator_set"

#: Every automated token this codebase may write, in trust order (strongest
#: first). ``operator_set`` is intentionally excluded -- see its docstring above.
SESSION_NAME_SOURCE_TRUST_ORDER: Final[tuple[str, ...]] = (
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
    SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
    SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
    SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
)

#: Membership set for validation / test assertions. Includes the reserved
#: ``operator_set`` token so it is recognised (never treated as "unknown
#: provenance") once a future rename-UI starts writing it.
KNOWN_SESSION_NAME_SOURCES: Final[frozenset[str]] = frozenset(
    SESSION_NAME_SOURCE_TRUST_ORDER + (SESSION_NAME_SOURCE_OPERATOR_SET,)
)

#: Tokens declared but not yet written by any code path in this codebase.
RESERVED_SESSION_NAME_SOURCES: Final[frozenset[str]] = frozenset(
    {
        SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
        SESSION_NAME_SOURCE_OPERATOR_SET,
    }
)

#: Character bound applied to a ``derived_deterministic`` name cut from free text
#: (a last prompt, or a first user message) by EITHER provider's parser.
#:
#: Lives here rather than in one parser because both parsers cut such names and the
#: bound must not drift between them (feature-level review finding L-8: it had already
#: become a named constant in one parser and a bare literal in the other). The value
#: itself is inherited from the Claude parser's pre-existing ``summary_text[:120]``
#: convention for provider summaries — a title cut from a prompt is no longer or less
#: title-shaped than one cut from a summary. No ellipsis is appended, matching that
#: same precedent. Distinct from ``session_naming_prompt.MAX_TITLE_LENGTH`` (100),
#: which bounds MODEL-GENERATED titles, not text cuts.
SESSION_NAME_FALLBACK_TRUNCATION_LEN: Final[int] = 120


def session_name_rank(source: str | None) -> int | None:
    """Return the trust rank of ``source`` (lower == stronger), or ``None``.

    ``None`` is returned for a null source, an unrecognised token, and the
    reserved ``operator_set`` token (which sits outside the ranked ladder by
    design -- see its module-level docstring). Callers that need to treat an
    operator override as authoritative regardless of rank should check for
    ``SESSION_NAME_SOURCE_OPERATOR_SET`` explicitly before consulting rank.
    """
    if source is None:
        return None
    try:
        return SESSION_NAME_SOURCE_TRUST_ORDER.index(source)
    except ValueError:
        return None


def may_overwrite(candidate: str | None, incumbent: str | None) -> bool:
    """True if a name sourced from ``candidate`` may replace one from ``incumbent``.

    Enforces "a weaker source never overwrites a stronger one" (this module's
    rubric contract) without callers re-deriving the comparison inline:

    * An ``operator_set`` incumbent is authoritative and may never be
      overwritten by anything. False. This case is checked FIRST and inside
      this helper deliberately: ``operator_set`` sits outside the ranked
      ladder, so ``session_name_rank`` returns ``None`` for it, and the
      unranked-incumbent rule below would otherwise invert it into the
      *weakest* possible incumbent -- the exact opposite of its meaning as
      the strongest (human) signal. This module's docstring names this helper
      as THE enforcement mechanism, so the contract has to hold here rather
      than depend on every call site remembering a special case.
    * No incumbent (``incumbent is None``, i.e. no name written yet) -- anything
      may write. True.
    * An incumbent with unknown/unranked provenance (including a bare non-null
      ``session_name`` written before this column existed) is treated as the
      weakest possible incumbent -- any ranked candidate may overwrite it. True.
    * An unranked candidate (``None``, an unrecognised token, or the reserved
      ``operator_set`` token) may never overwrite a ranked incumbent via this
      helper -- callers writing an operator override should bypass it, not
      rely on it.
    * Otherwise, compare rank: lower rank == stronger, so the candidate's rank
      must be <= the incumbent's rank (strictly stronger or exactly equal) for
      the overwrite to be allowed.
    """
    if incumbent == SESSION_NAME_SOURCE_OPERATOR_SET:
        return False
    incumbent_rank = session_name_rank(incumbent)
    if incumbent_rank is None:
        return True
    candidate_rank = session_name_rank(candidate)
    if candidate_rank is None:
        return False
    return candidate_rank <= incumbent_rank
