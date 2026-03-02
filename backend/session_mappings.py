"""Session command mapping configuration and classification utilities."""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import aiosqlite

from backend import config

_MAPPINGS_METADATA_KEY = "session_mappings"
_MAPPINGS_ENV_JSON = "CCDASH_SESSION_MAPPINGS_JSON"
_MAPPINGS_ENV_FILE = "CCDASH_SESSION_MAPPINGS_FILE"
_REQ_ID_PATTERN = re.compile(r"\bREQ-\d{8}-[A-Za-z0-9-]+-\d+\b")
_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_NOISY_PATH_PATTERN = re.compile(r"(\*|\$\{[^}]+\}|<[^>]+>|\{[^{}]+\})")
_COMMAND_MARKER_PATTERN = re.compile(r"^\^?\s*(/[A-Za-z0-9:_-]+)")
_DEFAULT_JOIN_WITH = ", "
_MAPPING_TYPE_BASH = "bash"
_MAPPING_TYPE_KEY_COMMAND = "key_command"
_SUPPORTED_MATCH_SCOPES = {"command", "args", "command_and_args"}
_SUPPORTED_FIELD_SOURCES = {"command", "args", "phaseToken", "phases", "featurePath", "featureSlug", "requestId"}
_ALL_PLATFORM_TOKEN = "all"
_NON_CONSEQUENTIAL_COMMAND_PREFIXES = {"/clear", "/model"}

_DEFAULT_SESSION_MAPPINGS: list[dict[str, Any]] = [
    {
        "id": "git-commit",
        "mappingType": _MAPPING_TYPE_BASH,
        "label": "Git Commit",
        "category": "git",
        "pattern": r"\bgit\s+commit\b",
        "transcriptLabel": "Git Commit",
        "priority": 100,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "git-command",
        "mappingType": _MAPPING_TYPE_BASH,
        "label": "Git Command",
        "category": "git",
        "pattern": r"\bgit\s+",
        "transcriptLabel": "Git Command",
        "priority": 90,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "test-command",
        "mappingType": _MAPPING_TYPE_BASH,
        "label": "Test Run",
        "category": "test",
        "pattern": r"\b(pytest|pnpm\s+test|npm\s+test|vitest|jest|go\s+test|cargo\s+test)\b",
        "transcriptLabel": "Test Run",
        "priority": 80,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "lint-command",
        "mappingType": _MAPPING_TYPE_BASH,
        "label": "Lint Check",
        "category": "lint",
        "pattern": r"\b(eslint|pnpm\s+lint|npm\s+run\s+lint|ruff|flake8|mypy|black)\b",
        "transcriptLabel": "Lint Check",
        "priority": 70,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "deploy-command",
        "mappingType": _MAPPING_TYPE_BASH,
        "label": "Deployment",
        "category": "deploy",
        "pattern": r"\b(deploy|release|publish|vercel|netlify|kubectl|docker\s+push)\b",
        "transcriptLabel": "Deployment",
        "priority": 60,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
]

_DEFAULT_KEY_COMMAND_MAPPINGS: list[dict[str, Any]] = [
    {
        "id": "key-dev-execute-phase",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Phased Execution",
        "sessionTypeLabel": "Phased Execution",
        "category": "key_command",
        "transcriptLabel": "Phase Command",
        "commandMarker": "/dev:execute-phase",
        "pattern": r"^/dev:execute-phase\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "related-phases", "label": "Related Phase(s)", "source": "phases", "enabled": True, "joinWith": ", "},
            {"id": "feature-path", "label": "Feature Path", "source": "featurePath", "enabled": True},
        ],
        "priority": 220,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-dev-quick-feature",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Quick Feature Execution",
        "sessionTypeLabel": "Quick Feature Execution",
        "category": "key_command",
        "transcriptLabel": "Quick Feature Command",
        "commandMarker": "/dev:quick-feature",
        "pattern": r"^/dev:quick-feature\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "command-args", "label": "Command Arguments", "source": "args", "enabled": True},
        ],
        "priority": 210,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-dev-implement-story",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Story Implementation",
        "sessionTypeLabel": "Story Implementation",
        "category": "key_command",
        "transcriptLabel": "Implement Story Command",
        "commandMarker": "/dev:implement-story",
        "pattern": r"^/dev:implement-story\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "feature-path", "label": "Feature Path", "source": "featurePath", "enabled": True},
            {"id": "feature-slug", "label": "Feature Slug", "source": "featureSlug", "enabled": True},
        ],
        "priority": 205,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-plan-plan-feature",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Feature Planning",
        "sessionTypeLabel": "Feature Planning",
        "category": "key_command",
        "transcriptLabel": "Plan Feature Command",
        "commandMarker": "/plan:plan-feature",
        "pattern": r"^/plan:plan-feature\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "feature-path", "label": "Feature Path", "source": "featurePath", "enabled": True},
            {"id": "request-id", "label": "Request ID", "source": "requestId", "enabled": True},
        ],
        "priority": 200,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-dev-complete-user-story",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Story Completion",
        "sessionTypeLabel": "Story Completion",
        "category": "key_command",
        "transcriptLabel": "Complete Story Command",
        "commandMarker": "/dev:complete-user-story",
        "pattern": r"^/dev:complete-user-story\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "feature-path", "label": "Feature Path", "source": "featurePath", "enabled": True},
            {"id": "feature-slug", "label": "Feature Slug", "source": "featureSlug", "enabled": True},
        ],
        "priority": 198,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-fix-debug",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Debug Session",
        "sessionTypeLabel": "Debug Session",
        "category": "key_command",
        "transcriptLabel": "Debug Command",
        "commandMarker": "/fix:debug",
        "pattern": r"^/fix:debug\b",
        "matchScope": "command",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "command-args", "label": "Command Arguments", "source": "args", "enabled": True},
        ],
        "priority": 190,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
    {
        "id": "key-recovering-sessions",
        "mappingType": _MAPPING_TYPE_KEY_COMMAND,
        "label": "Session Recovery",
        "sessionTypeLabel": "Session Recovery",
        "category": "key_command",
        "transcriptLabel": "Recover Session Command",
        "commandMarker": "/recovering-sessions",
        "pattern": r"^/recovering-sessions\b",
        "matchScope": "command_and_args",
        "fieldMappings": [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "feature-path", "label": "Feature Path", "source": "featurePath", "enabled": True},
            {"id": "feature-slug", "label": "Feature Slug", "source": "featureSlug", "enabled": True},
        ],
        "priority": 185,
        "enabled": True,
        "platforms": [_ALL_PLATFORM_TOKEN],
    },
]


def _sort_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_mappings = deepcopy(mappings)
    sorted_mappings.sort(key=lambda item: int(item.get("priority", 0)), reverse=True)
    return sorted_mappings


def default_session_mappings() -> list[dict[str, Any]]:
    """Return a deep copy of built-in mappings."""
    return _sort_mappings([*_DEFAULT_SESSION_MAPPINGS, *_DEFAULT_KEY_COMMAND_MAPPINGS])


def workflow_command_exemptions() -> set[str]:
    """Return slash-command prefixes intentionally excluded from workflow ranking."""
    return set(_NON_CONSEQUENTIAL_COMMAND_PREFIXES)


def _command_marker_from_pattern(pattern: str) -> str:
    match = _COMMAND_MARKER_PATTERN.match(str(pattern or "").strip())
    if not match:
        return ""
    marker = str(match.group(1) or "").strip().lower()
    return marker if marker.startswith("/") else ""


def workflow_command_markers(
    mappings: list[dict[str, Any]] | None = None,
    *,
    include_disabled: bool = False,
) -> tuple[str, ...]:
    """Return ordered key workflow command markers from mapping configuration."""
    source = mappings if isinstance(mappings, list) else default_session_mappings()
    markers: list[str] = []
    seen: set[str] = set()
    for mapping in _sort_mappings(source):
        if str(mapping.get("mappingType") or "").strip().lower() != _MAPPING_TYPE_KEY_COMMAND:
            continue
        if not include_disabled and not bool(mapping.get("enabled", True)):
            continue
        marker = str(mapping.get("commandMarker") or "").strip().lower() or _command_marker_from_pattern(
            str(mapping.get("pattern") or "")
        )
        if not marker or not marker.startswith("/") or marker in seen:
            continue
        seen.add(marker)
        markers.append(marker)
    if not markers:
        fallback = [str(item.get("commandMarker") or "").strip().lower() for item in _DEFAULT_KEY_COMMAND_MAPPINGS]
        markers = [value for value in fallback if value]
    return tuple(markers)


def _normalize_ref_path(raw: str) -> str:
    value = (raw or "").strip().strip("\"'`<>[](),;")
    if not value:
        return ""
    while value.startswith("./"):
        value = value[2:]
    if value.startswith("../"):
        return ""
    value = value.replace("\\", "/")
    if _NOISY_PATH_PATTERN.search(value):
        return ""
    return value


def _extract_paths_from_text(text: str) -> list[str]:
    if not text:
        return []
    values: list[str] = []
    for raw in _PATH_PATTERN.findall(text):
        normalized = _normalize_ref_path(raw)
        if normalized:
            values.append(normalized)
    return values


def _slug_from_path(path_value: str) -> str:
    normalized = _normalize_ref_path(path_value)
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()


def _normalize_platform_token(value: str) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return ""
    if raw in {_ALL_PLATFORM_TOKEN, "*", "any", "all_platforms"}:
        return _ALL_PLATFORM_TOKEN
    if "claude" in raw:
        return "claude_code"
    if "codex" in raw:
        return "codex"
    return re.sub(r"[^a-z0-9_]+", "", raw)


def _coerce_platforms(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        values.extend(parts)
    elif isinstance(raw, list):
        values.extend(str(item).strip() for item in raw if str(item).strip())

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in values:
        token = _normalize_platform_token(candidate)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)

    if not normalized:
        return [_ALL_PLATFORM_TOKEN]
    if _ALL_PLATFORM_TOKEN in normalized:
        return [_ALL_PLATFORM_TOKEN]
    return normalized


def _mapping_applies_to_platform(mapping: dict[str, Any], platform_type: str) -> bool:
    raw_platforms = mapping.get("platforms")
    platforms = _coerce_platforms(raw_platforms)
    if not platforms or _ALL_PLATFORM_TOKEN in platforms:
        return True

    platform = _normalize_platform_token(platform_type)
    if not platform:
        return True
    return platform in platforms


def _extract_phase_token(args_text: str) -> tuple[str, list[str]]:
    normalized = " ".join((args_text or "").strip().split())
    if not normalized:
        return "", []

    if normalized.lower().startswith("all"):
        return "all", ["all"]

    range_match = re.match(r"^(\d+)\s*-\s*(\d+)\b", normalized)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if start <= end:
            values = [str(v) for v in range(start, end + 1)]
        else:
            values = [str(start), str(end)]
        return f"{start}-{end}", values

    amp_match = re.match(r"^(\d+(?:\s*&\s*\d+)+)\b", normalized)
    if amp_match:
        values = [part.strip() for part in amp_match.group(1).split("&") if part.strip()]
        return " & ".join(values), values

    single_match = re.match(r"^(\d+)\b", normalized)
    if single_match:
        token = single_match.group(1)
        return token, [token]

    return "", []


def _derive_command_context(command_name: str, args_text: str, parsed: dict[str, Any] | None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if isinstance(parsed, dict):
        context.update(parsed)

    command = (command_name or "").strip()
    args = (args_text or "").strip()
    context["command"] = command
    context["args"] = args

    if args and not context.get("requestId"):
        req_match = _REQ_ID_PATTERN.search(args)
        if req_match:
            context["requestId"] = req_match.group(0).upper()

    paths = context.get("paths")
    if not isinstance(paths, list):
        paths = _extract_paths_from_text(args)
    paths = [str(path) for path in paths if isinstance(path, str) and path]
    if paths:
        context["paths"] = paths[:8]

    if not context.get("featurePath") and paths:
        feature_path = paths[0]
        impl_paths = [p for p in paths if "implementation_plans/" in p and p.lower().endswith(".md")]
        if impl_paths:
            feature_path = impl_paths[0]
        context["featurePath"] = feature_path

    if not context.get("featureSlug") and context.get("featurePath"):
        slug = _slug_from_path(str(context.get("featurePath") or ""))
        if slug:
            context["featureSlug"] = slug

    if "dev:execute-phase" in command.lower():
        phase_token, phases = _extract_phase_token(args)
        if phase_token and not context.get("phaseToken"):
            context["phaseToken"] = phase_token
        if phases and not context.get("phases"):
            context["phases"] = phases

    return context


def _coerce_field_mapping(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    field_id = str(raw.get("id") or f"field-{idx}").strip() or f"field-{idx}"
    label = str(raw.get("label") or field_id).strip() or field_id
    source = str(raw.get("source") or "command").strip() or "command"
    if source not in _SUPPORTED_FIELD_SOURCES:
        source = "command"
    enabled = bool(raw.get("enabled", True))
    join_with = str(raw.get("joinWith") or _DEFAULT_JOIN_WITH)
    include_empty = bool(raw.get("includeEmpty", False))
    return {
        "id": field_id,
        "label": label,
        "source": source,
        "enabled": enabled,
        "joinWith": join_with,
        "includeEmpty": include_empty,
    }


def _default_key_field_mappings(label: str) -> list[dict[str, Any]]:
    default_label = (label or "").strip() or "Session Type"
    if "phase" in default_label.lower():
        return [
            {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
            {"id": "related-phases", "label": "Related Phase(s)", "source": "phases", "enabled": True, "joinWith": ", "},
        ]
    return [
        {"id": "related-command", "label": "Related Command", "source": "command", "enabled": True},
        {"id": "command-args", "label": "Command Arguments", "source": "args", "enabled": True},
    ]


def _coerce_mapping(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    mapping = dict(raw)
    mapping_id = str(raw.get("id") or f"custom-{idx}").strip() or f"custom-{idx}"
    label = str(raw.get("label") or mapping_id).strip() or mapping_id

    mapping_type = str(raw.get("mappingType") or "").strip().lower()
    if not mapping_type:
        mapping_type = _MAPPING_TYPE_KEY_COMMAND if raw.get("sessionTypeLabel") else _MAPPING_TYPE_BASH

    category_default = "key_command" if mapping_type == _MAPPING_TYPE_KEY_COMMAND else (mapping_type or "mapping")
    category = str(raw.get("category") or category_default).strip() or category_default
    pattern = str(raw.get("pattern") or "").strip()
    transcript_label = str(raw.get("transcriptLabel") or label).strip() or label
    enabled = bool(raw.get("enabled", True))
    try:
        priority = int(raw.get("priority", 10))
    except Exception:
        priority = 10

    mapping.update(
        {
            "id": mapping_id,
            "mappingType": mapping_type,
            "label": label,
            "category": category,
            "pattern": pattern,
            "transcriptLabel": transcript_label,
            "enabled": enabled,
            "priority": priority,
            "platforms": _coerce_platforms(raw.get("platforms")),
        }
    )

    if mapping_type == _MAPPING_TYPE_KEY_COMMAND:
        session_type_label = str(raw.get("sessionTypeLabel") or label).strip() or label
        match_scope = str(raw.get("matchScope") or "command").strip().lower()
        if match_scope not in _SUPPORTED_MATCH_SCOPES:
            match_scope = "command"

        raw_fields = raw.get("fieldMappings")
        field_mappings: list[dict[str, Any]] = []
        if isinstance(raw_fields, list):
            for field_idx, field_raw in enumerate(raw_fields):
                if isinstance(field_raw, dict):
                    field_mappings.append(_coerce_field_mapping(field_raw, field_idx))
        if not field_mappings:
            field_mappings = [
                _coerce_field_mapping(field_raw, field_idx)
                for field_idx, field_raw in enumerate(_default_key_field_mappings(session_type_label))
            ]

        command_marker = str(raw.get("commandMarker") or "").strip().lower() or _command_marker_from_pattern(pattern)
        mapping["sessionTypeLabel"] = session_type_label
        mapping["matchScope"] = match_scope
        mapping["fieldMappings"] = field_mappings
        if command_marker:
            mapping["commandMarker"] = command_marker

    return mapping


def _normalize_mapping_overrides(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for idx, candidate in enumerate(raw):
        if not isinstance(candidate, dict):
            continue
        mapping = _coerce_mapping(candidate, idx)
        if not str(mapping.get("pattern") or "").strip():
            continue
        normalized.append(mapping)
    return _sort_mappings(normalized)


def normalize_session_mappings(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize user-provided mappings and merge with built-in defaults."""
    merged_by_id: dict[str, dict[str, Any]] = {item["id"]: item for item in default_session_mappings()}
    for item in _normalize_mapping_overrides(raw):
        merged_by_id[item["id"]] = item
    return _sort_mappings(list(merged_by_id.values()))


def _parse_mappings_json(raw: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def load_env_session_mapping_overrides() -> list[dict[str, Any]]:
    """Load mapping overrides from env JSON or env file path."""
    merged: dict[str, dict[str, Any]] = {}

    file_path = str(os.getenv(_MAPPINGS_ENV_FILE, "")).strip()
    if file_path:
        candidate = Path(file_path).expanduser()
        if not candidate.is_absolute():
            candidate = (config.PROJECT_ROOT / candidate).resolve()
        if candidate.exists() and candidate.is_file():
            try:
                overrides = _normalize_mapping_overrides(_parse_mappings_json(candidate.read_text(encoding="utf-8")))
                for mapping in overrides:
                    merged[str(mapping.get("id") or "")] = mapping
            except Exception:
                pass

    raw_json = str(os.getenv(_MAPPINGS_ENV_JSON, "")).strip()
    if raw_json:
        overrides = _normalize_mapping_overrides(_parse_mappings_json(raw_json))
        for mapping in overrides:
            merged[str(mapping.get("id") or "")] = mapping

    return _sort_mappings(list(merged.values()))


def classify_bash_command(
    command: str,
    mappings: list[dict[str, Any]],
    *,
    platform_type: str = "",
) -> dict[str, Any] | None:
    """Classify a shell command using configured mapping rules."""
    command_text = (command or "").strip()
    if not command_text:
        return None

    for mapping in _sort_mappings(mappings):
        if str(mapping.get("mappingType") or _MAPPING_TYPE_BASH).strip().lower() != _MAPPING_TYPE_BASH:
            continue
        if not mapping.get("enabled", True):
            continue
        if not _mapping_applies_to_platform(mapping, platform_type):
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


def _mapping_match_target(mapping: dict[str, Any], command: str, args_text: str) -> str:
    match_scope = str(mapping.get("matchScope") or "command").strip().lower()
    if match_scope == "args":
        return args_text
    if match_scope == "command_and_args":
        return f"{command} {args_text}".strip()
    return command


def _resolve_field_value(field_source: str, context: dict[str, Any], join_with: str) -> str:
    if field_source in {"command", "args", "phaseToken", "featurePath", "featureSlug", "requestId"}:
        value = context.get(field_source)
        return str(value).strip() if value is not None else ""
    if field_source == "phases":
        phases = context.get("phases")
        if isinstance(phases, list):
            values = [str(v).strip() for v in phases if str(v).strip()]
            return (join_with or _DEFAULT_JOIN_WITH).join(values)
    return ""


def classify_key_command(
    command: str,
    args_text: str,
    parsed_command: dict[str, Any] | None,
    mappings: list[dict[str, Any]],
    *,
    platform_type: str = "",
) -> dict[str, Any] | None:
    """Classify a command as a key session type using configured mapping rules."""
    command_text = (command or "").strip()
    if not command_text:
        return None

    candidates: list[dict[str, Any]] = []
    for mapping in _sort_mappings(mappings):
        if str(mapping.get("mappingType") or "").strip().lower() != _MAPPING_TYPE_KEY_COMMAND:
            continue
        if not mapping.get("enabled", True):
            continue
        if not _mapping_applies_to_platform(mapping, platform_type):
            continue
        pattern = str(mapping.get("pattern") or "").strip()
        if not pattern:
            continue
        match_target = _mapping_match_target(mapping, command_text, args_text)
        try:
            if re.search(pattern, match_target, re.IGNORECASE):
                candidates.append(mapping)
        except re.error:
            continue

    if not candidates:
        return None

    mapping = candidates[0]
    context = _derive_command_context(command_text, args_text, parsed_command)
    fields: list[dict[str, str]] = []
    raw_fields = mapping.get("fieldMappings")
    field_mappings = raw_fields if isinstance(raw_fields, list) else []
    for idx, field_raw in enumerate(field_mappings):
        if not isinstance(field_raw, dict):
            continue
        field = _coerce_field_mapping(field_raw, idx)
        if not field["enabled"]:
            continue
        value = _resolve_field_value(field["source"], context, field["joinWith"])
        if not value and not field.get("includeEmpty", False):
            continue
        fields.append({"id": field["id"], "label": field["label"], "value": value})

    related_phases = context.get("phases")
    if not isinstance(related_phases, list):
        related_phases = []

    return {
        "sessionTypeId": str(mapping.get("id") or ""),
        "sessionTypeLabel": str(mapping.get("sessionTypeLabel") or mapping.get("label") or ""),
        "mappingId": str(mapping.get("id") or ""),
        "relatedCommand": command_text,
        "relatedPhases": [str(v) for v in related_phases if str(v).strip()],
        "relatedFilePath": str(context.get("featurePath") or "").strip(),
        "fields": fields,
    }


def classify_session_key_metadata(
    command_events: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    *,
    platform_type: str = "",
) -> dict[str, Any] | None:
    """Return session key metadata from command events using key-command mappings."""
    best_match: dict[str, Any] | None = None
    best_priority = -1
    best_order = 10_000

    for order_idx, event in enumerate(command_events):
        if not isinstance(event, dict):
            continue
        command = str(event.get("name") or "").strip()
        args_text = str(event.get("args") or "")
        parsed = event.get("parsedCommand") if isinstance(event.get("parsedCommand"), dict) else {}
        event_platform = str(event.get("platformType") or "").strip() or platform_type
        match = classify_key_command(command, args_text, parsed, mappings, platform_type=event_platform)
        if not match:
            continue
        mapping_id = str(match.get("mappingId") or "")
        mapping = next((m for m in mappings if str(m.get("id") or "") == mapping_id), None)
        priority = int(mapping.get("priority", 0)) if isinstance(mapping, dict) else 0
        if priority > best_priority or (priority == best_priority and order_idx < best_order):
            best_priority = priority
            best_order = order_idx
            best_match = match

    return best_match


def _merge_mapping_layers(*layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {item["id"]: item for item in default_session_mappings()}
    for layer in layers:
        for item in layer:
            mapping_id = str(item.get("id") or "").strip()
            if not mapping_id:
                continue
            merged[mapping_id] = item
    return _sort_mappings(list(merged.values()))


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
    elif hasattr(db, "fetchrow"):
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
    else:
        raw_value = None

    db_overrides = _normalize_mapping_overrides(_parse_mappings_json(raw_value or "")) if raw_value else []
    env_overrides = load_env_session_mapping_overrides()
    return _merge_mapping_layers(db_overrides, env_overrides)


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
    elif hasattr(db, "execute"):
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
    else:
        return normalized

    return normalized
