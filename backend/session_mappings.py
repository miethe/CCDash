"""Session command mapping configuration and classification utilities."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

import aiosqlite

_MAPPINGS_METADATA_KEY = "session_mappings"

_DEFAULT_SESSION_MAPPINGS: list[dict[str, Any]] = [
    {
        "id": "git-commit",
        "label": "Git Commit",
        "category": "git",
        "pattern": r"\bgit\s+commit\b",
        "transcriptLabel": "Git Commit",
        "priority": 100,
        "enabled": True,
    },
    {
        "id": "git-command",
        "label": "Git Command",
        "category": "git",
        "pattern": r"\bgit\s+",
        "transcriptLabel": "Git Command",
        "priority": 90,
        "enabled": True,
    },
    {
        "id": "test-command",
        "label": "Test Run",
        "category": "test",
        "pattern": r"\b(pytest|pnpm\s+test|npm\s+test|vitest|jest|go\s+test|cargo\s+test)\b",
        "transcriptLabel": "Test Run",
        "priority": 80,
        "enabled": True,
    },
    {
        "id": "lint-command",
        "label": "Lint Check",
        "category": "lint",
        "pattern": r"\b(eslint|pnpm\s+lint|npm\s+run\s+lint|ruff|flake8|mypy|black)\b",
        "transcriptLabel": "Lint Check",
        "priority": 70,
        "enabled": True,
    },
    {
        "id": "deploy-command",
        "label": "Deployment",
        "category": "deploy",
        "pattern": r"\b(deploy|release|publish|vercel|netlify|kubectl|docker\s+push)\b",
        "transcriptLabel": "Deployment",
        "priority": 60,
        "enabled": True,
    },
]


def default_session_mappings() -> list[dict[str, Any]]:
    """Return a deep copy of built-in mappings."""
    return deepcopy(_DEFAULT_SESSION_MAPPINGS)


def _coerce_mapping(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    mapping_id = str(raw.get("id") or f"custom-{idx}").strip() or f"custom-{idx}"
    label = str(raw.get("label") or mapping_id).strip() or mapping_id
    category = str(raw.get("category") or "bash").strip() or "bash"
    pattern = str(raw.get("pattern") or "").strip()
    transcript_label = str(raw.get("transcriptLabel") or label).strip() or label
    enabled = bool(raw.get("enabled", True))
    try:
        priority = int(raw.get("priority", 10))
    except Exception:
        priority = 10

    return {
        "id": mapping_id,
        "label": label,
        "category": category,
        "pattern": pattern,
        "transcriptLabel": transcript_label,
        "enabled": enabled,
        "priority": priority,
    }


def normalize_session_mappings(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize user-provided mapping payload into a stable shape."""
    if not isinstance(raw, list):
        return default_session_mappings()

    normalized: list[dict[str, Any]] = []
    for idx, candidate in enumerate(raw):
        if not isinstance(candidate, dict):
            continue
        mapping = _coerce_mapping(candidate, idx)
        if not mapping["pattern"]:
            continue
        normalized.append(mapping)

    if not normalized:
        return default_session_mappings()

    # Merge defaults to preserve baseline behavior while allowing overrides.
    merged_by_id: dict[str, dict[str, Any]] = {
        item["id"]: item for item in default_session_mappings()
    }
    for item in normalized:
        merged_by_id[item["id"]] = item

    merged = list(merged_by_id.values())
    merged.sort(key=lambda item: int(item.get("priority", 0)), reverse=True)
    return merged


def classify_bash_command(command: str, mappings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Classify a Bash command using configured mapping rules."""
    command_text = (command or "").strip()
    if not command_text:
        return None

    for mapping in sorted(mappings, key=lambda item: int(item.get("priority", 0)), reverse=True):
        if not mapping.get("enabled", True):
            continue
        pattern = str(mapping.get("pattern") or "").strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, command_text, re.IGNORECASE):
                return mapping
        except re.error:
            continue
    return None


async def load_session_mappings(db: Any, project_id: str) -> list[dict[str, Any]]:
    """Load merged session mappings for a project."""
    raw_value: str | None = None
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(
            """
            SELECT value
            FROM app_metadata
            WHERE entity_type = ? AND entity_id = ? AND key = ?
            LIMIT 1
            """,
            ("project", project_id, _MAPPINGS_METADATA_KEY),
        ) as cur:
            row = await cur.fetchone()
            raw_value = row[0] if row else None
    else:
        row = await db.fetchrow(
            """
            SELECT value
            FROM app_metadata
            WHERE entity_type = $1 AND entity_id = $2 AND key = $3
            LIMIT 1
            """,
            "project",
            project_id,
            _MAPPINGS_METADATA_KEY,
        )
        raw_value = row["value"] if row else None

    if not raw_value:
        return default_session_mappings()

    try:
        parsed = json.loads(raw_value)
    except Exception:
        return default_session_mappings()

    return normalize_session_mappings(parsed if isinstance(parsed, list) else None)


async def save_session_mappings(db: Any, project_id: str, mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist normalized session mappings for a project."""
    normalized = normalize_session_mappings(mappings)
    payload = json.dumps(normalized)

    if isinstance(db, aiosqlite.Connection):
        await db.execute(
            """
            INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            ("project", project_id, _MAPPINGS_METADATA_KEY, payload),
        )
        await db.commit()
    else:
        await db.execute(
            """
            INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
            VALUES ($1, $2, $3, $4, NOW()::text)
            ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """,
            "project",
            project_id,
            _MAPPINGS_METADATA_KEY,
            payload,
        )

    return normalized
