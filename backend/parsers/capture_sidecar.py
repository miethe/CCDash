"""Parser for ``<session-id>.capture.json`` launch-time capture sidecar files (T11-004).

A capture sidecar sits co-located (by stem) next to a session JSONL log file and
carries launch-time attributes that cannot be recovered from the transcript:
launcher identity, launch profile (e.g. ``ica-delegate``), effort tier, and model
variant.

This module is intentionally **standalone and pure**: it has no DB / sync-engine
dependencies. The fields are promoted onto ``AgentSession`` inside
``backend/parsers/platforms/claude_code/parser.py`` at parse time.

Resilience contract (AC-11.C): missing/malformed sidecar → ``None`` returned,
DEBUG log, never raises. Partial sidecars are valid — only present fields populate.
No field is ever synthesized to a default (strict null contract: absent == null ==
"not captured").
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ccdash.parsers.capture_sidecar")

# Schema versions this parser accepts. Bump when the sidecar schema changes.
#
# v1 → v2 (Gap 4) added the optional ``effortTierSource`` key.  BOTH versions
# stay accepted deliberately: every sidecar already on disk is v1, and rejecting
# them would blind the whole capture lane to win a cosmetic version check.  A v1
# sidecar parses with ``effort_tier_source=None`` — "provenance unknown", which
# is exactly the truth for a value written before the source was recorded.
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})


@dataclass
class CaptureSidecar:
    """Structured view over a parsed ``<session-id>.capture.json`` sidecar.

    All capture attributes are ``Optional`` — absent field == ``null`` ==
    "not captured". No field is ever synthesized to a default.

    Attribute names are **snake_case** here (Python convention); callers that
    promote these onto ``AgentSession`` must map to the model's camelCase attrs:
    ``effort_tier`` → ``effortTier``, ``model_variant`` → ``modelVariant``,
    ``effort_tier_source`` → ``effortTierSource``.
    """

    session_id: Optional[str] = None
    launcher: Optional[str] = None
    profile: Optional[str] = None
    effort_tier: Optional[str] = None
    #: Gap 4 provenance for ``effort_tier`` — see
    #: ``backend/parsers/effort_provenance.py`` for the token vocabulary.
    #: ``None`` on v1 sidecars (written before the key existed) and whenever
    #: ``effort_tier`` itself is ``None``.
    effort_tier_source: Optional[str] = None
    model_variant: Optional[str] = None
    schema_version: Optional[int] = None
    captured_at: Optional[str] = None


def parse_capture_sidecar(path: Path) -> Optional[CaptureSidecar]:
    """Parse a single ``<session-id>.capture.json`` sidecar.

    Returns a :class:`CaptureSidecar` on success, or ``None`` when the file is
    missing, its JSON is malformed, or the ``schemaVersion`` is absent /
    unsupported (all logged at DEBUG — never raised).
    """
    try:
        if not path.exists() or not path.is_file():
            logger.debug("capture sidecar missing: %s", path)
            return None
    except OSError as exc:  # pragma: no cover — defensive
        logger.debug("capture sidecar stat failed for %s: %s", path, exc)
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("capture sidecar read failed for %s: %s", path, exc)
        return None

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("capture sidecar malformed JSON in %s: %s", path, exc)
        return None

    if not isinstance(payload, dict):
        logger.debug("capture sidecar root is not an object: %s", path)
        return None

    schema_version = payload.get("schemaVersion")
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        logger.debug(
            "capture sidecar unsupported schemaVersion %r in %s",
            schema_version,
            path,
        )
        return None

    def _opt_str(key: str) -> Optional[str]:
        """Extract a nullable string field; strip whitespace, return None on empty."""
        value = payload.get(key)
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped if stripped else None

    effort_tier = _opt_str("effortTier")
    # Provenance without a value is meaningless — drop a stray source when the
    # tier it describes is absent, so the invariant "source non-null implies
    # tier non-null" holds for every consumer.
    effort_tier_source = _opt_str("effortTierSource") if effort_tier else None

    return CaptureSidecar(
        session_id=_opt_str("sessionId"),
        launcher=_opt_str("launcher"),
        profile=_opt_str("profile"),
        effort_tier=effort_tier,
        effort_tier_source=effort_tier_source,
        model_variant=_opt_str("modelVariant"),
        schema_version=int(schema_version),
        captured_at=_opt_str("capturedAt"),
    )
