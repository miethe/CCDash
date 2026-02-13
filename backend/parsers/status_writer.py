"""Utilities for writing status changes back to markdown frontmatter."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a markdown file into (frontmatter_text, body).

    Returns (None, full_text) if no frontmatter is found.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return None, text
    return match.group(1), match.group(2)


def _rebuild_file(fm_dict: dict, body: str) -> str:
    """Reconstruct a markdown file from frontmatter dict + body."""
    fm_text = yaml.dump(fm_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return f"---\n{fm_text}---\n{body}"


def update_frontmatter_field(file_path: Path, field: str, value: str) -> None:
    """Update a top-level field in a markdown file's YAML frontmatter.

    Reads the file, modifies the field, and writes back preserving the body.
    """
    text = file_path.read_text(encoding="utf-8")
    fm_text, body = _split_frontmatter(text)

    if fm_text is None:
        # No frontmatter — create one with just this field
        fm_dict = {field: value}
    else:
        fm_dict = yaml.safe_load(fm_text) or {}
        fm_dict[field] = value

    file_path.write_text(_rebuild_file(fm_dict, body), encoding="utf-8")


def update_task_in_frontmatter(
    file_path: Path,
    task_id: str,
    field: str,
    value: str,
) -> bool:
    """Update a specific task entry within the tasks array in frontmatter.

    Returns True if the task was found and updated, False otherwise.
    """
    text = file_path.read_text(encoding="utf-8")
    fm_text, body = _split_frontmatter(text)

    if fm_text is None:
        return False

    fm_dict = yaml.safe_load(fm_text) or {}
    tasks = fm_dict.get("tasks", [])
    if not isinstance(tasks, list):
        return False

    found = False
    for task in tasks:
        if isinstance(task, dict) and task.get("id") == task_id:
            task[field] = value
            found = True
            break

    if not found:
        return False

    fm_dict["tasks"] = tasks
    file_path.write_text(_rebuild_file(fm_dict, body), encoding="utf-8")
    return True
