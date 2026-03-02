#!/usr/bin/env python3
"""Platform-configurable discovery for session JSON/JSONL datasets.

This tool is intentionally sampling-oriented:
- It does not parse full datasets by default.
- It infers dominant shapes/key frequencies from recent files.
- It can surface candidate signals for downstream parser work.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_MAX_FILES = 500
_DEFAULT_MAX_JSONL_LINES = 200
_DEFAULT_TOP_N = 40


@dataclass(slots=True)
class SidecarPattern:
    name: str
    glob: str


@dataclass(slots=True)
class PlatformProfile:
    platform_id: str
    description: str
    roots: list[str]
    env_roots: list[str]
    file_globs: list[str]
    sidecar_patterns: list[SidecarPattern]
    schema: dict[str, Any]
    global_config_files: list[str]


def _expand_path(raw_path: str, workspace_root: Path) -> Path:
    substituted = raw_path.replace("${WORKSPACE_ROOT}", str(workspace_root))
    return Path(os.path.expandvars(os.path.expanduser(substituted))).resolve()


def _load_profiles(config_path: Path, workspace_root: Path) -> dict[str, PlatformProfile]:
    parsed = json.loads(config_path.read_text(encoding="utf-8"))
    platforms = parsed.get("platforms") if isinstance(parsed, dict) else {}
    if not isinstance(platforms, dict):
        raise ValueError(f"Invalid profiles file at {config_path}")

    result: dict[str, PlatformProfile] = {}
    for platform_id, payload in platforms.items():
        if not isinstance(payload, dict):
            continue
        sidecar_patterns: list[SidecarPattern] = []
        for item in payload.get("sidecarPatterns", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            glob = str(item.get("glob") or "").strip()
            if not name or not glob:
                continue
            sidecar_patterns.append(SidecarPattern(name=name, glob=glob))

        result[platform_id] = PlatformProfile(
            platform_id=platform_id,
            description=str(payload.get("description") or "").strip(),
            roots=[str(x) for x in (payload.get("roots") or []) if str(x).strip()],
            env_roots=[str(x) for x in (payload.get("envRoots") or []) if str(x).strip()],
            file_globs=[str(x) for x in (payload.get("fileGlobs") or []) if str(x).strip()],
            sidecar_patterns=sidecar_patterns,
            schema=payload.get("schema") if isinstance(payload.get("schema"), dict) else {},
            global_config_files=[str(x) for x in (payload.get("globalConfigFiles") or []) if str(x).strip()],
        )
    return result


def _resolved_roots(profile: PlatformProfile, cli_roots: list[str], workspace_root: Path) -> list[Path]:
    candidates: list[Path] = []

    for raw_root in cli_roots:
        candidates.append(_expand_path(raw_root, workspace_root))

    for env_var in profile.env_roots:
        value = os.getenv(env_var, "").strip()
        if not value:
            continue
        for token in value.split(os.pathsep):
            token = token.strip()
            if token:
                candidates.append(_expand_path(token, workspace_root))

    for raw_root in profile.roots:
        candidates.append(_expand_path(raw_root, workspace_root))

    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            resolved.append(candidate)
    return resolved


def _counter_top(counter: Counter[str], top_n: int) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(top_n)]


def _safe_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _normalize_host(host: str) -> str:
    return host.strip().strip("[]").lower()


def _is_local_host(host: str) -> bool:
    return _normalize_host(host) in {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


_URL_RE = re.compile(r"https?://([a-zA-Z0-9.-]+)(?::(\d+))?")
_SSH_TARGET_RE = re.compile(r"\b(?:ssh|scp|rsync)\b[^\n]*?\b([A-Za-z0-9._-]+@[A-Za-z0-9.-]+)")
_DB_SYSTEM_RE = re.compile(r"\b(psql|mysql|sqlite3|mongosh|mongo|redis-cli|pg_dump|pg_restore)\b")
_DOCKER_RE = re.compile(r"\bdocker(?:\s+compose|[- ]compose|\s+\w+)")
_SERVICE_RE = re.compile(r"\b(pm2|systemctl)\b")


def _split_command_segments(command: str) -> list[str]:
    parts: list[str] = []
    current = []
    in_single = False
    in_double = False
    escaped = False
    depth = 0

    for ch in command:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            continue
        if in_single or in_double:
            current.append(ch)
            continue
        if ch in "({":
            depth += 1
            current.append(ch)
            continue
        if ch in ")}":
            depth = max(0, depth - 1)
            current.append(ch)
            continue
        if depth == 0 and ch in ";|":
            chunk = "".join(current).strip()
            if chunk:
                parts.append(chunk)
            current = []
            continue
        current.append(ch)

    chunk = "".join(current).strip()
    if chunk:
        parts.append(chunk)
    return parts


def _extract_resources_from_command(command: str) -> list[tuple[str, str, str]]:
    resources: list[tuple[str, str, str]] = []
    if not command.strip():
        return resources

    for segment in _split_command_segments(command):
        db_match = _DB_SYSTEM_RE.search(segment)
        if db_match:
            tool = db_match.group(1)
            db_system_map = {
                "psql": "postgresql",
                "pg_dump": "postgresql",
                "pg_restore": "postgresql",
                "mysql": "mysql",
                "sqlite3": "sqlite",
                "mongosh": "mongodb",
                "mongo": "mongodb",
                "redis-cli": "redis",
            }
            db_system = db_system_map.get(tool, tool)

            host = ""
            host_match = re.search(r"(?:-h|--host)\s+([^\s]+)", segment)
            if host_match:
                host = _normalize_host(host_match.group(1))
            elif "docker exec" in segment:
                host = "docker"
            else:
                host = "localhost"

            scope = "internal" if _is_local_host(host) or host == "docker" else "external"
            resources.append(("database", f"{db_system}:{host or 'localhost'}", scope))

        for url_match in _URL_RE.finditer(segment):
            host = _normalize_host(url_match.group(1))
            port = url_match.group(2)
            target = f"{host}:{port}" if port else host
            scope = "internal" if _is_local_host(host) else "external"
            resources.append(("api", target, scope))

        for ssh_match in _SSH_TARGET_RE.finditer(segment):
            target = ssh_match.group(1)
            resources.append(("ssh", target, "external"))

        if _DOCKER_RE.search(segment):
            resources.append(("docker", "docker", "internal"))

        service_match = _SERVICE_RE.search(segment)
        if service_match:
            resources.append(("service", service_match.group(1), "internal"))

    return resources


def _discover_files(roots: list[Path], file_globs: list[str], max_files: int) -> tuple[list[Path], int]:
    discovered: list[Path] = []
    seen: set[str] = set()
    total_candidates = 0

    for root in roots:
        for pattern in file_globs:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                total_candidates += 1
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                discovered.append(path)

    def _mtime(path: Path) -> float:
        try:
            return float(path.stat().st_mtime)
        except Exception:
            return 0.0

    discovered.sort(key=_mtime, reverse=True)
    return discovered[:max_files], total_candidates


def _relative_path(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            continue
    return path.name


def _bucket_path(relative: str) -> str:
    parts = relative.split("/")
    if len(parts) >= 2 and parts[1] in {"subagents", "tool-results"}:
        return f"*/{parts[1]}"
    if len(parts) >= 2 and parts[0] in {"tasks", "todos", "teams", "session-env"}:
        return f"{parts[0]}/*"
    return parts[0] if parts else relative


def _build_candidate_signals(
    sidecar_counts: Counter[str],
    unknown_entry_keys: Counter[str],
    unknown_payload_keys: Counter[str],
    progress_types: Counter[str],
    resource_categories: Counter[str],
    global_summary: dict[str, Any],
) -> list[str]:
    suggestions: list[str] = []

    if sidecar_counts.get("subagents", 0) > 0:
        suggestions.append(
            "Track per-root-session subagent fan-out (count, depth, and agent completion lag) from nested `subagents/*.jsonl`."
        )
    if sidecar_counts.get("tool_results", 0) > 0:
        suggestions.append(
            "Index `tool-results/*.txt` as optional large artifacts (line count, checksum, and tail preview) to correlate heavy tool outputs."
        )
    if progress_types.get("waiting_for_task", 0) > 0:
        suggestions.append(
            "Add queue pressure metrics from `progress.data.type=waiting_for_task` events (wait count and wait duration estimates)."
        )
    if resource_categories:
        suggestions.append(
            "Persist command-level resource usage (database/api/docker/ssh/service) from Bash calls for operational footprint analytics."
        )
    if unknown_entry_keys:
        top_unknown = ", ".join(key for key, _ in unknown_entry_keys.most_common(4))
        suggestions.append(f"Review unknown entry keys for parser extension candidates: {top_unknown}.")
    if unknown_payload_keys:
        top_unknown = ", ".join(key for key, _ in unknown_payload_keys.most_common(4))
        suggestions.append(f"Review unknown payload keys for parser extension candidates: {top_unknown}.")
    if global_summary:
        suggestions.append(
            "Use global config telemetry (feature flags, per-project MCP server setup, onboarding stats) for platform health dashboards."
        )
    return suggestions


def run_discovery(
    profile: PlatformProfile,
    roots: list[Path],
    max_files: int,
    max_jsonl_lines: int,
    top_n: int,
) -> dict[str, Any]:
    files, total_candidates = _discover_files(roots, profile.file_globs, max_files=max_files)

    known_entry_keys = {str(x) for x in (profile.schema.get("knownEntryKeys") or [])}
    entry_type_field = str(profile.schema.get("entryTypeField") or "type")
    message_field = str(profile.schema.get("messageField") or "message")
    content_field = str(profile.schema.get("contentField") or "content")
    progress_field = str(profile.schema.get("progressField") or "data")
    progress_type_field = str(profile.schema.get("progressTypeField") or "type")
    payload_field = str(profile.schema.get("payloadField") or "payload")
    payload_type_field = str(profile.schema.get("payloadTypeField") or "type")
    known_payload_keys = {str(x) for x in (profile.schema.get("knownPayloadKeys") or [])}

    by_extension: Counter[str] = Counter()
    by_bucket: Counter[str] = Counter()
    sidecar_counts: Counter[str] = Counter()
    top_level_keys: Counter[str] = Counter()
    array_item_keys: Counter[str] = Counter()
    json_type_counts: Counter[str] = Counter()
    entry_type_counts: Counter[str] = Counter()
    payload_type_counts: Counter[str] = Counter()
    content_block_types: Counter[str] = Counter()
    progress_type_counts: Counter[str] = Counter()
    tool_name_counts: Counter[str] = Counter()
    unknown_entry_keys: Counter[str] = Counter()
    payload_keys: Counter[str] = Counter()
    unknown_payload_keys: Counter[str] = Counter()
    parse_errors: list[str] = []

    resource_categories: Counter[str] = Counter()
    resource_targets: Counter[str] = Counter()
    resource_scopes: Counter[str] = Counter()
    sample_commands: list[dict[str, str]] = []
    seen_commands: set[str] = set()

    def register_command(command: str, source: str) -> None:
        normalized = " ".join(command.strip().split())
        if not normalized:
            return
        if normalized not in seen_commands and len(sample_commands) < 30:
            seen_commands.add(normalized)
            sample_commands.append({"source": source, "command": normalized[:400]})
        for category, target, scope in _extract_resources_from_command(normalized):
            resource_categories[category] += 1
            resource_targets[f"{category}:{target}"] += 1
            resource_scopes[f"{category}:{scope}"] += 1

    for path in files:
        relative = _relative_path(path, roots)
        extension = path.suffix.lower() or "<noext>"
        by_extension[extension] += 1
        by_bucket[_bucket_path(relative)] += 1

        for pattern in profile.sidecar_patterns:
            if fnmatch.fnmatch(relative, pattern.glob):
                sidecar_counts[pattern.name] += 1

        if extension not in {".json", ".jsonl"}:
            continue

        try:
            if extension == ".json":
                raw = path.read_text(encoding="utf-8", errors="ignore")
                parsed = _safe_json_loads(raw)
                if parsed is None:
                    continue
                json_type_counts[type(parsed).__name__] += 1
                if isinstance(parsed, dict):
                    for key in parsed:
                        top_level_keys[str(key)] += 1
                elif isinstance(parsed, list):
                    for item in parsed[:80]:
                        if isinstance(item, dict):
                            for key in item:
                                array_item_keys[str(key)] += 1
                continue

            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for idx, line in enumerate(handle):
                    if idx >= max_jsonl_lines:
                        break
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    entry = _safe_json_loads(raw_line)
                    if not isinstance(entry, dict):
                        continue

                    for key in entry:
                        string_key = str(key)
                        top_level_keys[string_key] += 1
                        if known_entry_keys and string_key not in known_entry_keys:
                            unknown_entry_keys[string_key] += 1

                    entry_type = str(entry.get(entry_type_field) or "").strip()
                    if entry_type:
                        entry_type_counts[entry_type] += 1

                    message = entry.get(message_field)
                    payload = entry.get(payload_field)
                    payload_type = ""
                    if isinstance(payload, dict):
                        for key in payload:
                            string_key = str(key)
                            payload_keys[string_key] += 1
                            if known_payload_keys and string_key not in known_payload_keys:
                                unknown_payload_keys[string_key] += 1
                        payload_type = str(payload.get(payload_type_field) or "").strip()
                        if payload_type:
                            payload_type_counts[payload_type] += 1

                    if isinstance(message, dict):
                        content = message.get(content_field)
                        if isinstance(content, list):
                            for block in content[:40]:
                                if not isinstance(block, dict):
                                    continue
                                block_type = str(block.get("type") or "").strip()
                                if block_type:
                                    content_block_types[block_type] += 1
                                if block_type == "tool_use":
                                    tool_name = str(block.get("name") or "").strip()
                                    if tool_name:
                                        tool_name_counts[tool_name] += 1
                                    if tool_name == "Bash":
                                        tool_input = block.get("input")
                                        if isinstance(tool_input, dict):
                                            command = str(tool_input.get("command") or "").strip()
                                            if command:
                                                register_command(command, "assistant.tool_use")

                    # Some platforms place content blocks directly on the entry.
                    direct_content = entry.get(content_field)
                    if isinstance(direct_content, list):
                        for block in direct_content[:40]:
                            if isinstance(block, dict):
                                block_type = str(block.get("type") or "").strip()
                                if block_type:
                                    content_block_types[block_type] += 1

                    # Codex-style event payload wrapper.
                    if isinstance(payload, dict):
                        payload_content = payload.get(content_field)
                        if isinstance(payload_content, list):
                            for block in payload_content[:40]:
                                if isinstance(block, dict):
                                    block_type = str(block.get("type") or "").strip()
                                    if block_type:
                                        content_block_types[block_type] += 1

                        if payload_type in {"function_call", "custom_tool_call"}:
                            tool_name = str(payload.get("name") or "").strip()
                            if tool_name:
                                tool_name_counts[tool_name] += 1
                            raw_args = payload.get("arguments")
                            if raw_args is None:
                                raw_args = payload.get("input")
                            parsed_args: Any = raw_args
                            if isinstance(raw_args, str):
                                candidate = _safe_json_loads(raw_args)
                                if isinstance(candidate, dict):
                                    parsed_args = candidate
                            if isinstance(parsed_args, dict):
                                command = str(parsed_args.get("command") or parsed_args.get("cmd") or "").strip()
                                if command:
                                    register_command(command, f"payload.{payload_type}")

                        # Generic command fields that appear in wrapped payload events.
                        for generic_key in ("command", "cmd", "bashCommand"):
                            generic_command = str(payload.get(generic_key) or "").strip()
                            if generic_command:
                                register_command(generic_command, f"payload.{generic_key}")
                                break

                    progress_data = entry.get(progress_field)
                    if isinstance(progress_data, dict):
                        progress_type = str(progress_data.get(progress_type_field) or "").strip()
                        if progress_type:
                            progress_type_counts[progress_type] += 1
                        progress_command = str(progress_data.get("command") or "").strip()
                        if progress_command:
                            register_command(progress_command, "progress.data")

                    # Generic fallback fields used by some tools.
                    for generic_key in ("command", "cmd", "bashCommand"):
                        generic_command = str(entry.get(generic_key) or "").strip()
                        if generic_command:
                            register_command(generic_command, f"entry.{generic_key}")
                            break
        except Exception as exc:  # pragma: no cover - defensive only
            parse_errors.append(f"{path}: {exc}")
            if len(parse_errors) > 50:
                parse_errors = parse_errors[:50]

    global_config_summary: dict[str, Any] = {}
    global_config_key_counts: Counter[str] = Counter()
    project_field_counts: Counter[str] = Counter()
    mcp_server_name_counts: Counter[str] = Counter()
    global_files_seen: list[str] = []

    workspace_root = Path.cwd().resolve()
    for raw_path in profile.global_config_files:
        candidate = _expand_path(raw_path, workspace_root)
        if not candidate.exists() or not candidate.is_file():
            continue
        global_files_seen.append(str(candidate))
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        for key in parsed:
            global_config_key_counts[str(key)] += 1
        projects = parsed.get("projects")
        if isinstance(projects, dict):
            for project_payload in projects.values():
                if not isinstance(project_payload, dict):
                    continue
                for key in project_payload:
                    project_field_counts[str(key)] += 1
                mcp_servers = project_payload.get("mcpServers")
                if isinstance(mcp_servers, dict):
                    for name in mcp_servers:
                        mcp_server_name_counts[str(name)] += 1

    if global_files_seen:
        global_config_summary = {
            "files": global_files_seen,
            "topLevelKeys": _counter_top(global_config_key_counts, top_n=top_n),
            "projectFieldKeys": _counter_top(project_field_counts, top_n=top_n),
            "mcpServerNames": _counter_top(mcp_server_name_counts, top_n=top_n),
        }

    suggestions = _build_candidate_signals(
        sidecar_counts=sidecar_counts,
        unknown_entry_keys=unknown_entry_keys,
        unknown_payload_keys=unknown_payload_keys,
        progress_types=progress_type_counts,
        resource_categories=resource_categories,
        global_summary=global_config_summary,
    )

    return {
        "platform": profile.platform_id,
        "description": profile.description,
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "roots": [str(root) for root in roots],
        "options": {
            "maxFiles": max_files,
            "maxJsonlLinesPerFile": max_jsonl_lines,
            "topN": top_n,
        },
        "files": {
            "totalDiscoveredCandidates": total_candidates,
            "processedFiles": len(files),
            "byExtension": _counter_top(by_extension, top_n=20),
            "pathBuckets": _counter_top(by_bucket, top_n=20),
            "sidecarMatches": _counter_top(sidecar_counts, top_n=20),
        },
        "schema": {
            "jsonTypeCounts": _counter_top(json_type_counts, top_n=10),
            "topLevelKeys": _counter_top(top_level_keys, top_n=top_n),
            "arrayItemKeys": _counter_top(array_item_keys, top_n=top_n),
            "entryTypes": _counter_top(entry_type_counts, top_n=top_n),
            "payloadTypes": _counter_top(payload_type_counts, top_n=top_n),
            "payloadKeys": _counter_top(payload_keys, top_n=top_n),
            "contentBlockTypes": _counter_top(content_block_types, top_n=top_n),
            "progressTypes": _counter_top(progress_type_counts, top_n=top_n),
            "toolNames": _counter_top(tool_name_counts, top_n=top_n),
            "unknownEntryKeys": _counter_top(unknown_entry_keys, top_n=top_n),
            "unknownPayloadKeys": _counter_top(unknown_payload_keys, top_n=top_n),
        },
        "resources": {
            "categories": _counter_top(resource_categories, top_n=top_n),
            "targets": _counter_top(resource_targets, top_n=top_n),
            "scopes": _counter_top(resource_scopes, top_n=top_n),
            "sampleCommands": sample_commands,
        },
        "globalConfig": global_config_summary,
        "candidateSignals": suggestions,
        "errors": parse_errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover session-data schema/resource signals without full dataset ingestion."
    )
    parser.add_argument(
        "--config",
        default="backend/parsers/platforms/discovery_profiles.json",
        help="Path to platform discovery profile JSON.",
    )
    parser.add_argument(
        "--platform",
        default="claude_code",
        help="Profile id from discovery profile JSON (for example: claude_code, codex).",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Additional dataset root. Repeatable; takes precedence over profile roots.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=_DEFAULT_MAX_FILES,
        help=f"Max files to sample (default: {_DEFAULT_MAX_FILES}).",
    )
    parser.add_argument(
        "--max-jsonl-lines",
        type=int,
        default=_DEFAULT_MAX_JSONL_LINES,
        help=f"Max JSONL lines per file (default: {_DEFAULT_MAX_JSONL_LINES}).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=_DEFAULT_TOP_N,
        help=f"Top counter rows to include in each section (default: {_DEFAULT_TOP_N}).",
    )
    parser.add_argument(
        "--write",
        default="",
        help="Optional output file path (JSON). If omitted, prints to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(json.dumps({"error": f"Config file not found: {config_path}"}, indent=2))
        return 1

    workspace_root = Path.cwd().resolve()
    profiles = _load_profiles(config_path, workspace_root=workspace_root)
    profile = profiles.get(args.platform)
    if not profile:
        print(
            json.dumps(
                {
                    "error": f"Unknown platform profile: {args.platform}",
                    "availableProfiles": sorted(profiles.keys()),
                },
                indent=2,
            )
        )
        return 1

    roots = _resolved_roots(profile, cli_roots=list(args.root or []), workspace_root=workspace_root)
    if not roots:
        print(
            json.dumps(
                {
                    "error": "No readable roots found for discovery.",
                    "platform": profile.platform_id,
                    "hint": "Pass --root or set env roots from the profile.",
                    "envRoots": profile.env_roots,
                    "configuredRoots": profile.roots,
                },
                indent=2,
            )
        )
        return 1

    result = run_discovery(
        profile=profile,
        roots=roots,
        max_files=max(1, int(args.max_files)),
        max_jsonl_lines=max(1, int(args.max_jsonl_lines)),
        top_n=max(5, int(args.top_n)),
    )

    payload = json.dumps(result, indent=2, ensure_ascii=True)
    if args.write:
        out_path = Path(args.write).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(json.dumps({"ok": True, "output": str(out_path), "platform": profile.platform_id}, indent=2))
        return 0

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
