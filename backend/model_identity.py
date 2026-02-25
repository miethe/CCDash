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
