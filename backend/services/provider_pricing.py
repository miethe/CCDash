"""Provider-backed pricing fetchers with safe HTML parsing fallbacks."""
from __future__ import annotations

import html
import re
import urllib.request
from typing import Any


_USER_AGENT = "Mozilla/5.0 CCDash/1.0"
_ANTHROPIC_PRICING_URL = "https://docs.anthropic.com/en/docs/about-claude/pricing"
_OPENAI_PRICING_URL = "https://platform.openai.com/docs/pricing/"

_ANTHROPIC_ROW_RE = re.compile(
    r">(?P<label>Claude [^<]+?)(?:\s*\([^<]+\))?</td>"
    r".*?\$(?P<input>\d+(?:\.\d+)?)\s*/\s*MTok</td>"
    r".*?\$(?P<cache_create>\d+(?:\.\d+)?)\s*/\s*MTok</td>"
    r".*?\$(?P<cache_create_long>\d+(?:\.\d+)?)\s*/\s*MTok</td>"
    r".*?\$(?P<cache_read>\d+(?:\.\d+)?)\s*/\s*MTok</td>"
    r".*?\$(?P<output>\d+(?:\.\d+)?)\s*/\s*MTok</td>",
    re.IGNORECASE | re.DOTALL,
)
_OPENAI_ROW_RE = re.compile(
    r"&quot;(?P<label>gpt-5(?:\.\d+)?-codex|codex-mini-latest)&quot;\],\[0,(?P<input>\d+(?:\.\d+)?)\],\[0,(?P<cached_input>\d+(?:\.\d+)?)\],\[0,(?P<output>\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)

_ANTHROPIC_MODEL_ID_BY_LABEL = {
    "claude opus 4.6": "claude-opus-4-6",
    "claude opus 4.5": "claude-opus-4-5",
    "claude opus 4.1": "claude-opus-4-1",
    "claude opus 4": "claude-opus-4",
    "claude opus 3": "claude-3-opus",
    "claude sonnet 4.6": "claude-sonnet-4-6",
    "claude sonnet 4.5": "claude-sonnet-4-5",
    "claude sonnet 4": "claude-sonnet-4",
    "claude sonnet 3.7": "claude-3-7-sonnet",
    "claude sonnet 3.5": "claude-3-5-sonnet",
    "claude haiku 4.5": "claude-haiku-4-5",
    "claude haiku 3.5": "claude-haiku-3-5",
}


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_anthropic_pricing() -> list[dict[str, Any]]:
    text = _fetch_text(_ANTHROPIC_PRICING_URL)
    entries: list[dict[str, Any]] = []
    for match in _ANTHROPIC_ROW_RE.finditer(text):
        label = html.unescape(match.group("label")).strip()
        model_id = _ANTHROPIC_MODEL_ID_BY_LABEL.get(label.lower())
        if not model_id:
            continue
        entries.append(
            {
                "platformType": "Claude Code",
                "modelId": model_id,
                "inputCostPerMillion": float(match.group("input")),
                "outputCostPerMillion": float(match.group("output")),
                "cacheCreationCostPerMillion": float(match.group("cache_create")),
                "cacheReadCostPerMillion": float(match.group("cache_read")),
                "sourceType": "fetched",
            }
        )
    return entries


def fetch_openai_codex_pricing() -> list[dict[str, Any]]:
    text = _fetch_text(_OPENAI_PRICING_URL)
    entries: list[dict[str, Any]] = []
    for match in _OPENAI_ROW_RE.finditer(text):
        label = html.unescape(match.group("label")).strip().lower()
        entries.append(
            {
                "platformType": "Codex",
                "modelId": label,
                "inputCostPerMillion": float(match.group("input")),
                "outputCostPerMillion": float(match.group("output")),
                "cacheReadCostPerMillion": float(match.group("cached_input")),
                "sourceType": "fetched",
            }
        )
    return entries
