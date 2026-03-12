#!/usr/bin/env python3
"""Recursively inventory nested Claude Code session schema paths from JSON/JSONL."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PATTERNS = ("*.jsonl", "*.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _trim_text(value: str, max_chars: int = 240) -> str:
    text = value.replace("\n", "\\n")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _sample_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _trim_text(value)
    if isinstance(value, list):
        preview = [_sample_value(item) for item in value[:3]]
        if len(value) > 3:
            preview.append(f"... ({len(value)} items)")
        return preview
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        keys = list(value.keys())
        for key in keys[:6]:
            preview[str(key)] = _sample_value(value[key])
        if len(keys) > 6:
            preview["..."] = f"{len(keys) - 6} more keys"
        return preview
    return _trim_text(str(value))


def _sample_key(sample: Any) -> str:
    try:
        return json.dumps(sample, ensure_ascii=True, sort_keys=True)
    except Exception:
        return repr(sample)


@dataclass(slots=True)
class PathStats:
    count: int = 0
    file_count: int = 0
    line_count: int = 0
    value_types: Counter[str] = field(default_factory=Counter)
    sample_values: list[Any] = field(default_factory=list)
    sample_sources: list[str] = field(default_factory=list)
    object_keys: Counter[str] = field(default_factory=Counter)
    _sample_seen: set[str] = field(default_factory=set)
    _files_seen: set[str] = field(default_factory=set)
    _lines_seen: set[str] = field(default_factory=set)

    def add(self, value: Any, *, file_path: str, line_no: int, max_examples: int) -> None:
        self.count += 1
        self.value_types[_json_type_name(value)] += 1

        if file_path not in self._files_seen:
            self._files_seen.add(file_path)
            self.file_count += 1

        line_key = f"{file_path}:{line_no}"
        if line_key not in self._lines_seen:
            self._lines_seen.add(line_key)
            self.line_count += 1

        if isinstance(value, dict):
            for key in value.keys():
                self.object_keys[str(key)] += 1

        if len(self.sample_values) >= max_examples:
            return

        sample = _sample_value(value)
        sample_key = _sample_key(sample)
        if sample_key in self._sample_seen:
            return

        self._sample_seen.add(sample_key)
        self.sample_values.append(sample)
        self.sample_sources.append(line_key)


def _walk_value(
    value: Any,
    *,
    path: str,
    file_path: str,
    line_no: int,
    path_stats: dict[str, PathStats],
    field_name_counts: Counter[str],
    max_examples: int,
) -> None:
    stats = path_stats.setdefault(path, PathStats())
    stats.add(value, file_path=file_path, line_no=line_no, max_examples=max_examples)

    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            field_name_counts[key] += 1
            child_path = f"{path}.{key}" if path else key
            _walk_value(
                child,
                path=child_path,
                file_path=file_path,
                line_no=line_no,
                path_stats=path_stats,
                field_name_counts=field_name_counts,
                max_examples=max_examples,
            )
        return

    if isinstance(value, list):
        item_path = f"{path}[]"
        for child in value:
            _walk_value(
                child,
                path=item_path,
                file_path=file_path,
                line_no=line_no,
                path_stats=path_stats,
                field_name_counts=field_name_counts,
                max_examples=max_examples,
            )


def _iter_files(inputs: list[str], patterns: tuple[str, ...], max_files: int) -> list[Path]:
    discovered: list[Path] = []
    seen: set[str] = set()

    for raw_input in inputs:
        candidate = Path(os.path.expanduser(raw_input)).resolve()
        if not candidate.exists():
            continue
        if candidate.is_file():
            key = str(candidate)
            if key not in seen:
                seen.add(key)
                discovered.append(candidate)
            continue

        for root, _, files in os.walk(candidate, followlinks=True):
            for name in files:
                if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
                    continue
                file_path = Path(root) / name
                key = str(file_path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                discovered.append(file_path)

    discovered.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return discovered[:max_files]


def _scan_json_file(
    path: Path,
    *,
    path_stats: dict[str, PathStats],
    field_name_counts: Counter[str],
    max_examples: int,
) -> int:
    entries = 0
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, list):
        iterable = list(enumerate(parsed, start=1))
    else:
        iterable = [(1, parsed)]

    for line_no, payload in iterable:
        _walk_value(
            payload,
            path="$",
            file_path=str(path),
            line_no=line_no,
            path_stats=path_stats,
            field_name_counts=field_name_counts,
            max_examples=max_examples,
        )
        entries += 1
    return entries


def _scan_jsonl_file(
    path: Path,
    *,
    path_stats: dict[str, PathStats],
    field_name_counts: Counter[str],
    max_examples: int,
    max_lines: int,
) -> int:
    entries = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if max_lines > 0 and line_no > max_lines:
                break
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            _walk_value(
                payload,
                path="$",
                file_path=str(path),
                line_no=line_no,
                path_stats=path_stats,
                field_name_counts=field_name_counts,
                max_examples=max_examples,
            )
            entries += 1
    return entries


def build_inventory(
    *,
    inputs: list[str],
    patterns: tuple[str, ...],
    max_files: int,
    max_lines: int,
    max_examples: int,
) -> dict[str, Any]:
    files = _iter_files(inputs, patterns, max_files=max_files)
    path_stats: dict[str, PathStats] = {}
    field_name_counts: Counter[str] = Counter()
    parse_errors: list[str] = []
    total_entries = 0

    for path in files:
        try:
            if path.suffix == ".jsonl":
                total_entries += _scan_jsonl_file(
                    path,
                    path_stats=path_stats,
                    field_name_counts=field_name_counts,
                    max_examples=max_examples,
                    max_lines=max_lines,
                )
            else:
                total_entries += _scan_json_file(
                    path,
                    path_stats=path_stats,
                    field_name_counts=field_name_counts,
                    max_examples=max_examples,
                )
        except Exception as exc:  # pragma: no cover - defensive
            parse_errors.append(f"{path}: {exc}")

    sorted_paths = sorted(
        path_stats.items(),
        key=lambda item: (-item[1].count, item[0]),
    )

    return {
        "generatedAt": _now_iso(),
        "inputs": inputs,
        "patterns": list(patterns),
        "filesScanned": len(files),
        "entriesScanned": total_entries,
        "distinctPaths": len(path_stats),
        "fieldNames": [
            {"name": name, "count": count}
            for name, count in field_name_counts.most_common()
        ],
        "paths": [
            {
                "path": path,
                "observedCount": stats.count,
                "fileCount": stats.file_count,
                "lineCount": stats.line_count,
                "valueTypes": dict(stats.value_types),
                "objectKeys": dict(stats.object_keys) if stats.object_keys else {},
                "sampleValues": stats.sample_values,
                "sampleSources": stats.sample_sources,
            }
            for path, stats in sorted_paths
        ],
        "errors": parse_errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory nested schema paths and sample values from Claude Code session files."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Session files or directories to scan.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="File glob to include when scanning directories. Repeatable.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="Maximum number of files to scan after sorting by modified time.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=0,
        help="Maximum JSONL lines per file. Use 0 for no limit.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=5,
        help="Maximum unique example values to keep per path.",
    )
    parser.add_argument(
        "--write",
        default="",
        help="Optional path to write the JSON inventory.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    patterns = tuple(args.pattern or DEFAULT_PATTERNS)
    inventory = build_inventory(
        inputs=args.inputs,
        patterns=patterns,
        max_files=max(1, int(args.max_files)),
        max_lines=max(0, int(args.max_lines)),
        max_examples=max(1, int(args.max_examples)),
    )
    payload = json.dumps(inventory, indent=2, ensure_ascii=True)
    if args.write:
        output_path = Path(args.write).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
