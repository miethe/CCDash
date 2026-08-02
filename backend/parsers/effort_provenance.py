"""Canonical vocabulary for ``sessions.effort_tier_source`` (Gap 4).

``sessions.effort_tier`` is populated by several lanes whose values differ in
trustworthiness by a wide margin.  Without provenance a rollup cannot tell a
harness-authoritative Codex value from a possibly-stale Claude Code settings
snapshot from an inherited guess.  This module is the single source of truth for
the token vocabulary that distinguishes them.

Trust ordering (strongest first)
-------------------------------
=========================== =================================================
Token                       Meaning / strength
=========================== =================================================
``launch_env``              ``CCDASH_LAUNCH_EFFORT`` was set at SessionStart.
                            Explicit launcher intent — strongest signal.
``codex_payload_effort``    Codex ``turn_context`` ``payload.effort``.
                            Harness-recorded, per-session, cannot be stale.
``codex_collaboration_mode`` Codex ``payload.collaboration_mode.settings``
                            ``.reasoning_effort``.  Same authority as above;
                            a distinct token because it is a secondary field
                            read only when ``payload.effort`` is absent.
``claude_settings``         ``effortLevel`` read from a Claude Code
                            ``settings.json`` at SessionStart.  A snapshot of
                            a mutable global — **can be stale** if ``/effort``
                            changed the tier mid-session (Gap 1).
``inherited_parent``        Derived from a parent session rather than
                            observed.  Declared here so the vocabulary is
                            closed; **reserved for Gap 2** — no code path
                            writes it yet.
=========================== =================================================

Contract
--------
* ``effort_tier_source`` is written **only** where ``effort_tier`` itself is
  resolved, and always together with it.  A non-null tier with a null source
  means the row predates this column (provenance unknown) — a legitimate
  contract state, never backfilled or guessed.
* A null tier always carries a null source.
* Tokens are stored verbatim.  Consumers MUST treat an unrecognised token as
  "unknown provenance" rather than hard-failing — the vocabulary may grow.

``scripts/hooks/ccdash_capture_session_start.py`` is a standalone stdlib script
(no ``backend`` import available at hook runtime), so it repeats the
``launch_env`` / ``claude_settings`` literals inline.  ``backend/tests/
test_effort_tier_source_provenance.py`` asserts those literals stay identical to
the constants below — edit both or neither.
"""
from __future__ import annotations

from typing import Final

#: ``CCDASH_LAUNCH_EFFORT`` env var set by the launcher (explicit intent).
EFFORT_SOURCE_LAUNCH_ENV: Final[str] = "launch_env"

#: Codex ``turn_context`` ``payload.effort`` (harness-authoritative).
EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT: Final[str] = "codex_payload_effort"

#: Codex ``payload.collaboration_mode.settings.reasoning_effort`` (secondary).
EFFORT_SOURCE_CODEX_COLLABORATION_MODE: Final[str] = "codex_collaboration_mode"

#: Claude Code ``settings.json`` ``effortLevel`` snapshot (can be stale).
EFFORT_SOURCE_CLAUDE_SETTINGS: Final[str] = "claude_settings"

#: Derived from a parent session — reserved for Gap 2, not yet written.
EFFORT_SOURCE_INHERITED_PARENT: Final[str] = "inherited_parent"

#: Every token this codebase may write, in trust order (strongest first).
EFFORT_SOURCE_TRUST_ORDER: Final[tuple[str, ...]] = (
    EFFORT_SOURCE_LAUNCH_ENV,
    EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
    EFFORT_SOURCE_CODEX_COLLABORATION_MODE,
    EFFORT_SOURCE_CLAUDE_SETTINGS,
    EFFORT_SOURCE_INHERITED_PARENT,
)

#: Membership set for validation / test assertions.
KNOWN_EFFORT_SOURCES: Final[frozenset[str]] = frozenset(EFFORT_SOURCE_TRUST_ORDER)

#: Tokens whose value is recorded by the harness itself and therefore cannot be
#: stale or derived.  Useful for rollups that want to restrict to hard evidence.
AUTHORITATIVE_EFFORT_SOURCES: Final[frozenset[str]] = frozenset({
    EFFORT_SOURCE_LAUNCH_ENV,
    EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
    EFFORT_SOURCE_CODEX_COLLABORATION_MODE,
})
