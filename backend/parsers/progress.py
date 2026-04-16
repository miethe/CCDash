"""Parse progress tracking files into ProjectTask models."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend.models import ProjectTask


# Status mapping: progress file statuses → frontend Kanban statuses
_STATUS_MAP = {
    "completed": "done",
    "complete": "done",
    "done": "done",
    "in-progress": "in-progress",
    "in_progress": "in-progress",
    "review": "review",
    "blocked": "backlog",
    "planning": "backlog",
    "pending": "backlog",
    "not-started": "backlog",
    "not_started": "backlog",
    "deferred": "deferred",
    "defer": "deferred",
    "postponed": "deferred",
    "skipped": "deferred",
    "wont-do": "deferred",
    "won't-do": "deferred",
}

# Model name expansion
_MODEL_MAP = {
    "sonnet": "Claude 3.7 Sonnet",
    "opus": "Claude 3 Opus",
    "haiku": "Claude 3 Haiku",
}


def _extract_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _map_status(raw: str) -> str:
    """Map progress file status to frontend status."""
    return _STATUS_MAP.get(raw.lower().strip(), "backlog")


def _expand_model(short: str) -> str:
    """Expand short model names to full display names."""
    return _MODEL_MAP.get(short.lower().strip(), short)


def _flatten_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        values: list[str] = []
        for entry in value:
            values.extend(_flatten_string_list(entry))
        return values
    return []


def _normalize_batch_task_map(parallelization: object) -> dict[str, str]:
    if not isinstance(parallelization, dict):
        return {}

    task_to_batch: dict[str, str] = {}
    for batch_id, batch_value in parallelization.items():
        batch_token = str(batch_id or "").strip()
        if not batch_token.startswith("batch_"):
            continue
        task_values = _flatten_string_list(batch_value)
        if isinstance(batch_value, dict):
            task_values = _flatten_string_list(
                batch_value.get("tasks")
                or batch_value.get("task_ids")
                or batch_value.get("items")
            )
        for task_id in task_values:
            token = str(task_id or "").strip()
            if token and token not in task_to_batch:
                task_to_batch[token] = batch_token
    return task_to_batch


def _normalize_raw_status_tag(prefix: str, raw_status: object) -> str:
    token = str(raw_status or "").strip().lower()
    token = re.sub(r"[^a-z0-9]+", "-", token).strip("-")
    return f"{prefix}:{token}" if token else ""


def parse_progress_file(path: Path, base_dir: Path) -> list[ProjectTask]:
    """Parse a single progress file into a list of ProjectTask objects."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    fm = _extract_frontmatter(text)

    # Compute relative source file path
    try:
        source_file = str(path.relative_to(base_dir.parent))
    except ValueError:
        source_file = str(path)
    if not fm:
        return []

    tasks_raw = fm.get("tasks", [])
    if not isinstance(tasks_raw, list):
        return []

    prd = fm.get("prd", "")
    phase = fm.get("phase", "")
    phase_name = fm.get("name", fm.get("title", ""))
    phase_status = fm.get("status", "")
    updated = fm.get("updated", fm.get("completed_at", ""))
    batch_by_task_id = _normalize_batch_task_map(fm.get("parallelization"))
    files_modified = fm.get("files_modified", [])
    if not isinstance(files_modified, list):
        files_modified = []
    # Normalize: entries can be strings or dicts with a 'path' key
    normalized_files: list[str] = []
    for f in files_modified:
        if isinstance(f, str):
            normalized_files.append(f)
        elif isinstance(f, dict) and "path" in f:
            normalized_files.append(str(f["path"]))
    files_modified = normalized_files

    # Extract tags from parent info
    base_tags = []
    if prd:
        base_tags.append(str(prd))
    if phase:
        base_tags.append(f"phase-{phase}")

    tasks: list[ProjectTask] = []
    for task_raw in tasks_raw:
        if not isinstance(task_raw, dict):
            continue

        task_id = task_raw.get("id", "")
        if not task_id:
            continue

        # Handle both `name` and `description` fields
        title = task_raw.get("name", task_raw.get("description", task_id))
        raw_task_status = str(task_raw.get("status", "pending"))
        status = _map_status(raw_task_status)

        # Owner: first assigned_to entry
        assigned = task_raw.get("assigned_to", [])
        if isinstance(assigned, str):
            assigned = [assigned]
        owner = assigned[0] if assigned else ""

        # Model
        model = _expand_model(task_raw.get("model", ""))

        # Priority
        priority = task_raw.get("priority", "medium")
        if not isinstance(priority, str):
            priority = "medium"

        # Estimated effort → rough cost estimate
        effort_str = str(task_raw.get("estimated_effort", ""))
        cost = 0.0
        # Parse "2h" or "3 pts" into a numeric value
        import re as _re
        effort_match = _re.search(r"(\d+(?:\.\d+)?)", effort_str)
        if effort_match:
            cost = float(effort_match.group(1)) * 0.50  # rough cost: $0.50/unit

        # Dependencies
        deps = task_raw.get("dependencies", [])
        if not isinstance(deps, list):
            deps = []

        # Session and commit linking
        session_id = str(task_raw.get("session_id", task_raw.get("sessionId", ""))) if task_raw.get("session_id") or task_raw.get("sessionId") else ""
        commit_hash = str(task_raw.get("git_commit", task_raw.get("commitHash", ""))) if task_raw.get("git_commit") or task_raw.get("commitHash") else ""

        extra_tags = []
        phase_status_tag = _normalize_raw_status_tag("raw-phase-status", phase_status)
        if phase_status_tag:
            extra_tags.append(phase_status_tag)
        task_status_tag = _normalize_raw_status_tag("raw-task-status", raw_task_status)
        if task_status_tag:
            extra_tags.append(task_status_tag)
        batch_id = batch_by_task_id.get(str(task_id))
        if batch_id:
            extra_tags.append(f"batch:{batch_id}")

        tasks.append(ProjectTask(
            id=task_id,
            title=title,
            description=f"Phase {phase}: {phase_name}" if phase_name else "",
            status=status,
            owner=owner,
            lastAgent=model,
            cost=round(cost, 2),
            priority=priority,
            projectType=str(prd),
            projectLevel=f"Phase {phase}" if phase else "",
            tags=base_tags + [str(d) for d in deps[:3]] + extra_tags,
            updatedAt=str(updated) if updated else "",
            relatedFiles=files_modified[:10],
            sourceFile=source_file,
            sessionId=session_id,
            commitHash=commit_hash,
        ))

    return tasks


def scan_progress(progress_dir: Path) -> list[ProjectTask]:
    """Scan a directory recursively for progress files and parse them all."""
    all_tasks: list[ProjectTask] = []
    if not progress_dir.exists():
        return all_tasks

    for path in sorted(progress_dir.rglob("*progress*.md")):
        if path.name.startswith("."):
            continue
        tasks = parse_progress_file(path, progress_dir)
        all_tasks.extend(tasks)

    return all_tasks
