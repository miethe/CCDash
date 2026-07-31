"""Model identity parsing utilities for session display/filtering."""
from __future__ import annotations

import re
from typing import Any


_VERSION_TOKEN_PATTERN = re.compile(r"^\d+$")
_DATE_SUFFIX_PATTERN = re.compile(r"(?:-\d{8}|-\d{4}-\d{2}-\d{2})+$")


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in (value or "").strip().split() if part.strip())


def _provider_label(token: str) -> str:
    lowered = (token or "").strip().lower()
    if lowered == "claude":
        return "Claude"
    if lowered in {"gpt", "openai"}:
        return "OpenAI"
    if lowered == "gemini":
        return "Gemini"
    if lowered:
        return _title_case(lowered)
    return "Unknown"


def derive_model_identity(raw_model: str | None) -> dict[str, str]:
    """Derive normalized model identity fields from a raw model string."""
    raw = (raw_model or "").strip()
    if not raw:
        return {
            "modelDisplayName": "",
            "modelProvider": "",
            "modelFamily": "",
            "modelVersion": "",
        }

    normalized = raw.lower()
    parts = [part for part in re.split(r"[-_\s]+", normalized) if part]
    provider_token = parts[0] if parts else ""
    provider = _provider_label(provider_token)

    family = ""
    version_number = ""

    if len(parts) >= 2:
        family = _title_case(parts[1])

    numeric_tokens: list[str] = []
    for token in parts[2:]:
        if _VERSION_TOKEN_PATTERN.match(token):
            numeric_tokens.append(token)
            if len(numeric_tokens) >= 2:
                break
        elif numeric_tokens:
            break

    if len(numeric_tokens) >= 2:
        version_number = f"{numeric_tokens[0]}.{numeric_tokens[1]}"
    elif len(numeric_tokens) == 1:
        version_number = numeric_tokens[0]

    model_version = ""
    if family and version_number:
        model_version = f"{family} {version_number}"
    elif family:
        model_version = family
    elif version_number:
        model_version = version_number

    display_name = " ".join(part for part in [provider, model_version or family] if part).strip()
    if not display_name:
        display_name = raw

    return {
        "modelDisplayName": display_name,
        "modelProvider": provider,
        "modelFamily": family,
        "modelVersion": model_version,
    }


def canonical_model_name(raw_model: str | None) -> str:
    """Return a canonical model identifier with build/date suffixes removed.

    Example:
      claude-opus-4-5-20251101 -> claude-opus-4-5
    """
    raw = (raw_model or "").strip().lower()
    if not raw:
        return ""
    normalized = re.sub(r"[\s_]+", "-", raw)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    stripped = _DATE_SUFFIX_PATTERN.sub("", normalized).strip("-")
    return stripped or normalized


def model_family_name(raw_model: str | None) -> str:
    """Return a human-friendly model family label (e.g., Opus, Sonnet)."""
    identity = derive_model_identity(raw_model)
    family = (identity.get("modelFamily") or "").strip()
    if family:
        return family
    canonical = canonical_model_name(raw_model)
    if not canonical:
        return "Unknown"
    parts = [part for part in canonical.split("-") if part]
    if len(parts) >= 2:
        return _title_case(parts[1])
    return _title_case(parts[0]) or "Unknown"


_PROVIDER_VENDOR_TOKENS: dict[str, str] = {
    "claude": "Anthropic",
    "gpt": "OpenAI",
    "openai": "OpenAI",
    "gemini": "Google",
}

_PROVIDER_SURFACE_LABELS: dict[str, str] = {
    "claude code": "Claude Code",
    "codex": "Codex",
}

_PROVIDER_CHANNEL_LABEL_SUFFIX: dict[str, str] = {
    "ica": "ICA",
    "api": "API",
}

_ICA_MODEL_VARIANT_PATTERN = re.compile(r"(?:^|[\[\-_])1m(?:$|[\]\-_])")


def _provider_vendor(raw_model: str | None) -> str:
    """Derive the model vendor (Anthropic/OpenAI/Google/Unknown) from a raw model slug.

    Deliberately independent of ``_provider_label`` above: that helper returns
    "Claude"/"OpenAI"/"Gemini" display labels for session badges and must not change.
    This returns the underlying company name and only recognizes the three vendors
    CCDash currently observes (Claude Code + Codex sessions); anything else — including
    unrecognized/synthetic model slugs — is "Unknown", never a title-cased guess.
    """
    raw = (raw_model or "").strip().lower()
    if not raw:
        return "Unknown"
    parts = [part for part in re.split(r"[-_\s]+", raw) if part]
    token = parts[0] if parts else ""
    return _PROVIDER_VENDOR_TOKENS.get(token, "Unknown")


def _provider_surface(platform_type: str | None) -> str:
    """Normalize a session's ``platform_type`` into a provider surface label."""
    raw = (platform_type or "").strip()
    if not raw:
        return "Unknown"
    return _PROVIDER_SURFACE_LABELS.get(raw.lower(), raw)


def _provider_channel(launcher: str | None, model_variant: str | None) -> str:
    """Derive the provider channel: subscription | ica | api | unknown.

    ``launcher`` is authoritative when present (Rule 1). It is populated by the
    launch-time capture hook (``CCDASH_LAUNCHER``) and, as of this writing, is not
    yet exported by any launcher — so it is empty for essentially all captured
    sessions today; this function still branches on it first so the channel split
    lights up automatically the moment capture is activated, with zero further
    changes needed here.

    Rule 1 — launcher (case-insensitive substring match):
      - contains "ica"  -> "ica"
      - contains "api"  -> "api"
      - any other non-empty value -> "subscription"

    Rule 2 — else, ``model_variant`` carries a ``1m`` / ``[1m]`` marker -> "ica".
      This is a **documented operator convention**, not an inference: per this
      operator's model registry (``~/.claude/CLAUDE.md`` "Model routing" section /
      ``~/.claude/config/model-registry.yaml``), ``[1m]``-suffixed model IDs
      (e.g. ``claude-sonnet-5[1m]``) denote the long-context pool served through
      ICA, as distinct from the plain-id (200k) direct-provider variant.

    Rule 3 — else -> "unknown". This is the current state for 100% of captured
    sessions (see analytics-provider-views grounding finding): ``launcher`` and
    ``model_variant`` are both unpopulated in the wild today, so this channel is
    structurally wired but not yet observable — never faked or inferred beyond
    what Rules 1-2 establish.
    """
    launcher_norm = (launcher or "").strip().lower()
    if launcher_norm:
        if "ica" in launcher_norm:
            return "ica"
        if "api" in launcher_norm:
            return "api"
        return "subscription"

    variant_norm = (model_variant or "").strip().lower()
    if variant_norm and _ICA_MODEL_VARIANT_PATTERN.search(variant_norm):
        return "ica"

    return "unknown"


def _provider_slug(value: str) -> str:
    lowered = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "unknown"


def derive_provider_identity(
    raw_model: str | None,
    platform_type: str | None = None,
    launcher: str | None = None,
    model_variant: str | None = None,
) -> dict[str, str]:
    """Derive the additive provider-identity axes for a session.

    This is the single derivation path for provider identity in the backend — do not
    reimplement this logic elsewhere. It is purely additive: it does NOT touch
    ``_provider_label``, ``derive_model_identity``, ``canonical_model_name``,
    ``model_family_name``, or ``model_filter_tokens``, all of which remain the
    source of truth for the existing "modelProvider" ("Claude"/"OpenAI"/"Gemini")
    semantics consumed by session badges, ``/api/sessions``, and feature views.

    Provider is modelled as three orthogonal axes, per the analytics-provider-views
    grounding finding (only the first two are live in captured data today):

    - ``providerVendor``  — Anthropic / OpenAI / Google / Unknown, from the model slug.
    - ``providerSurface`` — normalized ``platform_type`` ("Claude Code" / "Codex");
      empty/unrecognized/None -> "Unknown".
    - ``providerChannel`` — subscription / ica / api / unknown; see ``_provider_channel``
      docstring for the full launcher/model_variant derivation rules.

    Returns a dict with exactly these keys:
      - ``providerVendor``
      - ``providerSurface``
      - ``providerChannel``
      - ``providerId``    — stable lowercase machine key: "{vendor}:{surface}:{channel}"
        (each segment slugified, e.g. "anthropic:claude-code:subscription").
      - ``providerLabel`` — display string, e.g. "Anthropic · Claude Code"; a
        " · ICA" / " · API" suffix is appended only when the channel is a known
        non-subscription value ("ica"/"api") — "subscription" and "unknown" add no suffix.
    """
    vendor = _provider_vendor(raw_model)
    surface = _provider_surface(platform_type)
    channel = _provider_channel(launcher, model_variant)

    provider_id = f"{_provider_slug(vendor)}:{_provider_slug(surface)}:{_provider_slug(channel)}"

    label = f"{vendor} · {surface}"
    channel_suffix = _PROVIDER_CHANNEL_LABEL_SUFFIX.get(channel)
    if channel_suffix:
        label = f"{label} · {channel_suffix}"

    return {
        "providerVendor": vendor,
        "providerSurface": surface,
        "providerChannel": channel,
        "providerId": provider_id,
        "providerLabel": label,
    }


def model_filter_tokens(value: str | None) -> list[str]:
    """Build normalized filter tokens for model string matching.

    Tokens are intended to be combined with AND semantics per filter field.
    Example: "Opus 4.5" -> ["opus", "4-5"].
    """
    raw = (value or "").strip().lower()
    if not raw:
        return []

    pieces = [piece.strip() for piece in re.split(r"[\s/_-]+", raw) if piece.strip()]
    tokens: list[str] = []
    for piece in pieces:
        normalized = piece.replace(".", "-").strip("-")
        if not normalized:
            continue
        tokens.append(normalized)
        # Allow OpenAI provider searches to match GPT-prefixed raw model IDs.
        if normalized == "openai":
            tokens.append("gpt")
        elif normalized == "gpt":
            tokens.append("openai")

    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip("- ")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique
