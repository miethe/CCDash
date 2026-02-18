"""Incremental file → DB sync engine.

Scans filesystem for changed files (mtime-based), parses them using
existing parsers, and upserts the results into the DB cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.models import Project
from backend.parsers.sessions import parse_session_file
from backend.parsers.documents import parse_document_file, scan_documents
from backend.parsers.progress import parse_progress_file, scan_progress
from backend.parsers.features import scan_features

from backend.db.factory import (
    get_session_repository,
    get_document_repository,
    get_task_repository,
    get_analytics_repository,
    get_entity_link_repository,
    get_sync_state_repository,
    get_tag_repository,
    get_feature_repository, # Added in factory
)

logger = logging.getLogger("ccdash.sync")

_COMMAND_NAME_TAG_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_TAG_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_NON_CONSEQUENTIAL_COMMAND_PREFIXES = {"/clear", "/model"}
_KEY_WORKFLOW_COMMANDS = (
    "/dev:execute-phase",
    "/dev:quick-feature",
    "/plan:plan-feature",
    "/dev:implement-story",
    "/dev:complete-user-story",
    "/fix:debug",
)


def _file_hash(path: Path) -> str:
    """Compute a fast hash of file content for change detection."""
    h = hashlib.md5()
    try:
        h.update(path.read_bytes())
    except Exception:
        return ""
    return h.hexdigest()


def _canonical_task_source(path: Path, progress_dir: Path) -> str:
    """Store task source paths relative to project root for stable linking."""
    try:
        return str(path.relative_to(progress_dir.parent))
    except ValueError:
        return str(path)


def _task_storage_id(task_id: str, source_file: str) -> str:
    """Create a deterministic DB key for tasks.

    Task IDs in progress files are often reused across features/phases
    (for example, TASK-1.1), so a global PK on raw ID causes collisions.
    """
    raw = f"{source_file}::{task_id}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:20]
    return f"T-{digest}"


def _prepare_task_for_storage(task_dict: dict) -> dict:
    """Convert parser task shape into collision-safe DB row shape."""
    raw_task_id = str(task_dict.get("rawTaskId") or task_dict.get("id") or "").strip()
    source_file = str(task_dict.get("sourceFile") or "").strip()
    if not raw_task_id:
        return task_dict

    if not source_file:
        fallback_scope = f"{task_dict.get('featureId', '')}::{task_dict.get('phaseId', '')}"
        source_file = fallback_scope if fallback_scope != "::" else "unknown"

    task_dict["rawTaskId"] = raw_task_id
    task_dict["id"] = _task_storage_id(raw_task_id, source_file)
    return task_dict


def _normalize_command_label(command_name: str) -> str:
    return " ".join((command_name or "").strip().split())


def _command_token(command_name: str) -> str:
    normalized = _normalize_command_label(command_name).lower()
    if not normalized:
        return ""
    return normalized.split()[0]


def _is_non_consequential_command(command_name: str) -> bool:
    return _command_token(command_name) in _NON_CONSEQUENTIAL_COMMAND_PREFIXES


def _command_priority_rank(command_name: str) -> int:
    lowered = _normalize_command_label(command_name).lower()
    if not lowered:
        return len(_KEY_WORKFLOW_COMMANDS) + 1
    for idx, marker in enumerate(_KEY_WORKFLOW_COMMANDS):
        if marker in lowered:
            return idx
    return len(_KEY_WORKFLOW_COMMANDS)


def _select_linking_commands(command_names: set[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in command_names:
        normalized = _normalize_command_label(raw)
        if not normalized or _is_non_consequential_command(normalized):
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    unique.sort(key=lambda value: (_command_priority_rank(value), value.lower()))
    return unique


def _select_preferred_command_event(command_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    meaningful = [
        event
        for event in command_events
        if isinstance(event, dict) and not _is_non_consequential_command(str(event.get("name") or ""))
    ]
    if not meaningful:
        return None

    for marker in _KEY_WORKFLOW_COMMANDS:
        for event in meaningful:
            command_name = _normalize_command_label(str(event.get("name") or ""))
            if marker in command_name.lower():
                return event
    return meaningful[0]


def _extract_tagged_commands_from_message(content: str) -> list[tuple[str, str]]:
    if not content:
        return []
    command_names = [
        _normalize_command_label(match.group(1))
        for match in _COMMAND_NAME_TAG_PATTERN.finditer(content)
        if _normalize_command_label(match.group(1))
    ]
    if not command_names:
        return []

    command_args = [match.group(1).strip() for match in _COMMAND_ARGS_TAG_PATTERN.finditer(content)]
    pairs: list[tuple[str, str]] = []
    for idx, command_name in enumerate(command_names):
        args_text = command_args[idx] if idx < len(command_args) else ""
        pairs.append((command_name, args_text))
    return pairs


def _pop_matching_tagged_command(
    tagged_commands: list[dict[str, Any]],
    command_name: str,
) -> dict[str, Any] | None:
    token = _command_token(command_name)
    if not token:
        return None
    for idx, tagged in enumerate(tagged_commands):
        if _command_token(str(tagged.get("name") or "")) == token:
            return tagged_commands.pop(idx)
    return None


class SyncEngine:
    """Incremental mtime-based file → DB synchronization.

    Uses existing parsers to read files, then upserts parsed data
    into the SQLite/Postgres cache via repositories.
    """

    def __init__(self, db: Any): # db is Union[aiosqlite.Connection, asyncpg.Pool]
        self.db = db
        self.session_repo = get_session_repository(db)
        self.document_repo = get_document_repository(db)
        self.task_repo = get_task_repository(db)
        self.feature_repo = get_feature_repository(db)
        self.link_repo = get_entity_link_repository(db)
        self.sync_repo = get_sync_state_repository(db)
        self.tag_repo = get_tag_repository(db)
        self.analytics_repo = get_analytics_repository(db)

    async def sync_project(
        self,
        project: Project,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        force: bool = False,
    ) -> dict:
        """Full incremental sync for a project.

        Returns stats dict with counts of synced entities.
        """
        stats = {
            "sessions_synced": 0,
            "sessions_skipped": 0,
            "documents_synced": 0,
            "documents_skipped": 0,
            "tasks_synced": 0,
            "tasks_skipped": 0,
            "features_synced": 0,
            "links_created": 0,
            "duration_ms": 0,
        }
        t0 = time.monotonic()

        # Phase 1: Sessions
        s_stats = await self._sync_sessions(project.id, sessions_dir, force)
        stats["sessions_synced"] = s_stats["synced"]
        stats["sessions_skipped"] = s_stats["skipped"]

        # Phase 2: Documents
        d_stats = await self._sync_documents(project.id, docs_dir, force)
        stats["documents_synced"] = d_stats["synced"]
        stats["documents_skipped"] = d_stats["skipped"]

        # Phase 3: Tasks (progress files)
        t_stats = await self._sync_progress(project.id, progress_dir, force)
        stats["tasks_synced"] = t_stats["synced"]
        stats["tasks_skipped"] = t_stats["skipped"]

        # Phase 4: Features (derived from docs + progress)
        f_stats = await self._sync_features(project.id, docs_dir, progress_dir)
        stats["features_synced"] = f_stats["synced"]

        # Phase 5: Auto-discover cross-references
        l_stats = await self._rebuild_entity_links(project.id)
        stats["links_created"] = l_stats["created"]

        # Phase 6: Analytics Snapshot
        await self._capture_analytics(project.id)

        elapsed = int((time.monotonic() - t0) * 1000)
        stats["duration_ms"] = elapsed
        logger.info(
            f"Sync complete for {project.name}: "
            f"{stats['sessions_synced']} sessions, "
            f"{stats['documents_synced']} docs, "
            f"{stats['tasks_synced']} tasks, "
            f"{stats['features_synced']} features, "
            f"{stats['links_created']} links "
            f"in {elapsed}ms"
        )
        return stats

    async def sync_changed_files(
        self, project_id: str, changed_files: list[tuple[str, Path]],
        sessions_dir: Path, docs_dir: Path, progress_dir: Path,
    ) -> dict:
        """Sync only specific changed files. Used by file watcher.

        changed_files: list of (change_type, path) where change_type is 'modified'|'added'|'deleted'
        """
        stats = {"sessions": 0, "documents": 0, "tasks": 0, "features": 0}
        should_resync_features = False

        for change_type, path in changed_files:
            if change_type == "deleted":
                # Remove sync state and associated entities
                await self.sync_repo.delete_sync_state(str(path))
                if path.suffix == ".jsonl":
                    await self.session_repo.delete_by_source(str(path))
                    stats["sessions"] += 1
                elif path.suffix == ".md":
                    await self.document_repo.delete_by_source(str(path))
                    await self.task_repo.delete_by_source(str(path))
                    stats["documents"] += 1
                    if docs_dir in path.parents or progress_dir in path.parents:
                        should_resync_features = True
                continue

            # Modified or added
            if path.suffix == ".jsonl" and sessions_dir in path.parents:
                await self._sync_single_session(project_id, path)
                stats["sessions"] += 1
            elif path.suffix == ".md":
                if docs_dir in path.parents:
                    await self._sync_single_document(project_id, path, docs_dir)
                    stats["documents"] += 1
                    should_resync_features = True
                if progress_dir in path.parents:
                    await self._sync_single_progress(project_id, path, progress_dir)
                    stats["tasks"] += 1
                    should_resync_features = True

        if should_resync_features:
            f_stats = await self._sync_features(project_id, docs_dir, progress_dir)
            stats["features"] = f_stats.get("synced", 0)

        return stats

    # ── Session Sync ────────────────────────────────────────────────

    async def _sync_sessions(self, project_id: str, sessions_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        if not sessions_dir.exists():
            return stats

        for jsonl_file in sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            synced = await self._sync_single_session(project_id, jsonl_file, force)
            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

        return stats

    async def _sync_single_session(self, project_id: str, path: Path, force: bool = False) -> bool:
        """Parse and upsert a single session file. Returns True if actually synced."""
        file_path = str(path)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False  # unchanged

        t0 = time.monotonic()
        session = parse_session_file(path)
        parse_ms = int((time.monotonic() - t0) * 1000)

        # Always clear existing rows for this source file before re-inserting.
        # This prevents stale duplicates when session ID derivation changes.
        await self.session_repo.delete_by_source(file_path)

        if session:
            session_dict = session.model_dump()
            session_dict["sourceFile"] = file_path
            await self.session_repo.upsert(session_dict, project_id)

            # Detail tables
            logs = [log.model_dump() for log in session.logs]
            await self.session_repo.upsert_logs(session.id, logs)

            tools = [t.model_dump() for t in session.toolsUsed]
            await self.session_repo.upsert_tool_usage(session.id, tools)

            files = [f.model_dump() for f in session.updatedFiles]
            await self.session_repo.upsert_file_updates(session.id, files)

            artifacts = [a.model_dump() for a in session.linkedArtifacts]
            await self.session_repo.upsert_artifacts(session.id, artifacts)

        # Update sync state
        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "session",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Document Sync ───────────────────────────────────────────────

    async def _sync_documents(self, project_id: str, docs_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        if not docs_dir.exists():
            return stats

        for md_file in sorted(docs_dir.rglob("*.md")):
            if md_file.name.startswith("."):
                continue
            synced = await self._sync_single_document(project_id, md_file, docs_dir, force)
            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

        return stats

    async def _sync_single_document(
        self, project_id: str, path: Path, docs_dir: Path, force: bool = False,
    ) -> bool:
        file_path = str(path)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False

        t0 = time.monotonic()
        doc = parse_document_file(path, docs_dir)
        parse_ms = int((time.monotonic() - t0) * 1000)

        if doc:
            doc_dict = doc.model_dump()
            doc_dict["sourceFile"] = file_path
            # Serialize frontmatter for storage
            fm = doc_dict.pop("frontmatter", {})
            doc_dict["frontmatter"] = fm
            await self.document_repo.upsert(doc_dict, project_id)

            # Auto-tag from frontmatter tags
            fm_tags = fm.get("tags", []) if isinstance(fm, dict) else []
            for tag_name in fm_tags:
                if tag_name:
                    tag_id = await self.tag_repo.get_or_create(str(tag_name))
                    await self.tag_repo.tag_entity("document", doc.id, tag_id)

        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "document",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Progress / Task Sync ────────────────────────────────────────

    async def _sync_progress(self, project_id: str, progress_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        if not progress_dir.exists():
            return stats

        for md_file in sorted(progress_dir.rglob("*progress*.md")):
            if md_file.name.startswith("."):
                continue
            synced = await self._sync_single_progress(project_id, md_file, progress_dir, force)
            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

        return stats

    async def _sync_single_progress(
        self, project_id: str, path: Path, progress_dir: Path, force: bool = False,
    ) -> bool:
        file_path = str(path)
        canonical_source = _canonical_task_source(path, progress_dir)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False

        t0 = time.monotonic()
        tasks = parse_progress_file(path, progress_dir)
        parse_ms = int((time.monotonic() - t0) * 1000)

        # Delete old tasks from this source first (legacy absolute + canonical relative)
        await self.task_repo.delete_by_source(file_path)
        if canonical_source != file_path:
            await self.task_repo.delete_by_source(canonical_source)

        for task in tasks:
            task_dict = task.model_dump()
            task_dict["sourceFile"] = canonical_source
            task_dict = _prepare_task_for_storage(task_dict)
            await self.task_repo.upsert(task_dict, project_id)

            # Auto-tag
            for tag_name in task.tags:
                if tag_name:
                    tag_id = await self.tag_repo.get_or_create(str(tag_name))
                    await self.tag_repo.tag_entity("task", task.id, tag_id)

        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "task",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Feature Sync ────────────────────────────────────────────────

    async def _sync_features(self, project_id: str, docs_dir: Path, progress_dir: Path) -> dict:
        """Re-derive features from docs + progress and upsert all."""
        stats = {"synced": 0}

        features = scan_features(docs_dir, progress_dir)
        for feature in features:
            try:
                f_dict = feature.model_dump()
                await self.feature_repo.upsert(f_dict, project_id)

                # Upsert phases and link tasks
                phases = []
                for idx, p in enumerate(feature.phases):
                    p_dict = p.model_dump()
                    
                    # Generate deterministic phase_id (mirroring repo logic)
                    phase_id = p_dict.get("id")
                    if not phase_id:
                        phase_id = f"{feature.id}:phase-{str(p_dict.get('phase', '0'))}-{idx}"
                        p_dict["id"] = phase_id
                    
                    phases.append(p_dict)
                    
                    # Link tasks in this phase to feature and phase
                    for task in p.tasks:
                        task_dict = task.model_dump()
                        if not task_dict.get("sourceFile"):
                            task_dict["sourceFile"] = f"progress/{feature.id}"
                        task_dict["featureId"] = feature.id
                        task_dict["phaseId"] = phase_id
                        task_dict = _prepare_task_for_storage(task_dict)
                        await self.task_repo.upsert(task_dict, project_id)

                await self.feature_repo.upsert_phases(feature.id, phases)

                # Auto-tag
                for tag_name in feature.tags:
                    if tag_name:
                        tag_id = await self.tag_repo.get_or_create(str(tag_name))
                        await self.tag_repo.tag_entity("feature", feature.id, tag_id)

                stats["synced"] += 1
            except Exception as e:
                logger.error(f"Failed to sync feature {feature.id}: {e}")


        return stats

    # ── Entity Link Discovery ───────────────────────────────────────

    async def _rebuild_entity_links(self, project_id: str) -> dict:
        """Auto-discover cross-references between entities."""
        stats = {"created": 0}

        path_pattern = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
        req_id_pattern = re.compile(r"\bREQ-\d{8}-[A-Za-z0-9-]+-\d+\b")
        version_suffix_pattern = re.compile(r"-v\d+(?:\.\d+)?$", re.IGNORECASE)
        noisy_path_pattern = re.compile(r"(\*|\$\{[^}]+\}|<[^>]+>|\{[^{}]+\})")

        def _normalize_ref_path(raw: str) -> str:
            value = (raw or "").strip().strip("\"'`<>[](),;")
            if not value:
                return ""
            while value.startswith("./"):
                value = value[2:]
            if value.startswith("../"):
                return ""
            value = value.replace("\\", "/")
            if noisy_path_pattern.search(value):
                return ""
            return value

        def _canonical_slug(slug: str) -> str:
            normalized = slug.strip().lower()
            if not normalized:
                return ""
            return version_suffix_pattern.sub("", normalized)

        def _slug_from_path(path_value: str) -> str:
            normalized = _normalize_ref_path(path_value)
            if not normalized:
                return ""
            return Path(normalized).stem.lower()

        def _extract_paths_from_text(text: str) -> list[str]:
            if not text:
                return []
            values: list[str] = []
            for raw in path_pattern.findall(text):
                normalized = _normalize_ref_path(raw)
                if normalized:
                    values.append(normalized)
            return values

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
                    phases = [str(v) for v in range(start, end + 1)]
                else:
                    phases = [str(start), str(end)]
                return f"{start}-{end}", phases

            amp_match = re.match(r"^(\d+(?:\s*&\s*\d+)+)\b", normalized)
            if amp_match:
                phases = [part.strip() for part in amp_match.group(1).split("&") if part.strip()]
                return " & ".join(phases), phases

            single_match = re.match(r"^(\d+)\b", normalized)
            if single_match:
                token = single_match.group(1)
                return token, [token]

            return "", []

        def _parse_command_context(command_name: str, args_text: str) -> dict[str, Any]:
            context: dict[str, Any] = {}
            command = (command_name or "").strip()
            args = (args_text or "").strip()
            if not command:
                return context

            if args:
                req_match = req_id_pattern.search(args)
                if req_match:
                    context["requestId"] = req_match.group(0).upper()
                paths = _extract_paths_from_text(args)
                if paths:
                    context["paths"] = paths[:8]
                    primary_path = paths[0]
                    impl_paths = [p for p in paths if "implementation_plans/" in p and p.lower().endswith(".md")]
                    if impl_paths:
                        primary_path = impl_paths[0]
                    context["featurePath"] = primary_path
                    feature_slug = _slug_from_path(primary_path)
                    if feature_slug:
                        context["featureSlug"] = feature_slug
                        context["featureSlugCanonical"] = _canonical_slug(feature_slug)

            if "dev:execute-phase" in command.lower():
                phase_token, phases = _extract_phase_token(args)
                if phase_token:
                    context["phaseToken"] = phase_token
                if phases:
                    context["phases"] = phases
            return context

        def _path_matches(candidate: str, ref: str) -> bool:
            candidate_norm = _normalize_ref_path(candidate)
            ref_norm = _normalize_ref_path(ref)
            if not candidate_norm or not ref_norm:
                return False
            if candidate_norm == ref_norm:
                return True
            if candidate_norm.endswith(f"/{ref_norm}"):
                return True
            if ref_norm.endswith(f"/{candidate_norm}"):
                return True
            return False

        def _source_weight(tool_name: str) -> tuple[float, str]:
            name = (tool_name or "").strip().lower()
            if name in {"command"}:
                return 0.96, "command_args_path"
            if name in {"write", "writefile", "edit", "multiedit"}:
                return 0.95, "file_write"
            if name in {"bash", "exec"}:
                return 0.84, "shell_reference"
            if name in {"grep", "glob"}:
                return 0.66, "search_reference"
            if name in {"read", "readfile"}:
                return 0.46, "file_read"
            return 0.52, "file_reference"

        def _confidence_from_signals(
            weights: list[float],
            has_command_path: bool,
            has_command_hint: bool,
            has_write: bool,
        ) -> float:
            if not weights:
                return 0.0
            peak = max(weights)
            score = 0.35
            if has_command_path and has_write:
                score = 0.90
            elif has_command_path:
                score = 0.75
            elif has_write and peak >= 0.84:
                score = 0.75
            elif has_write:
                score = 0.62
            elif peak >= 0.84:
                score = 0.55

            if len(weights) >= 3:
                score += 0.05
            elif len(weights) >= 2:
                score += 0.03

            if has_command_hint:
                score += 0.03
            if has_write:
                score += 0.02
            return round(min(0.95, score), 3)

        def _derive_session_title(
            feature_id: str,
            custom_title: str,
            latest_summary: str,
            command_events: list[dict[str, Any]],
            command_names: set[str],
            file_updates: list[dict[str, Any]],
        ) -> tuple[str, str, float]:
            if custom_title:
                return custom_title[:160], "custom-title", 1.0
            if latest_summary:
                return latest_summary[:160], "summary", 0.92

            preferred = _select_preferred_command_event(command_events)
            if preferred:
                command_name = str(preferred.get("name") or "")
                parsed = preferred.get("parsed") if isinstance(preferred.get("parsed"), dict) else {}

                if "dev:execute-phase" in command_name.lower():
                    phase = str(parsed.get("phaseToken") or "unknown")
                    slug = str(parsed.get("featureSlug") or feature_id)
                    confidence = 0.90 if parsed.get("featurePath") else 0.75
                    return f"Execute Phase {phase} - {slug}", "command-template", confidence

                if "dev:quick-feature" in command_name.lower():
                    quick_slug = ""
                    for update in file_updates:
                        update_path = str(update.get("file_path") or "")
                        if "/quick-features/" in update_path and update_path.lower().endswith(".md"):
                            quick_slug = Path(update_path).stem
                            break
                    if not quick_slug:
                        quick_slug = str(parsed.get("featureSlug") or parsed.get("requestId") or feature_id)
                    confidence = 0.85 if quick_slug else 0.65
                    return f"Quick Feature - {quick_slug or feature_id}", "command-template", confidence

                if "plan:plan-feature" in command_name.lower():
                    basis = str(parsed.get("featureSlug") or parsed.get("requestId") or feature_id)
                    confidence = 0.88 if parsed.get("featurePath") or parsed.get("requestId") else 0.65
                    return f"Plan Feature - {basis}", "command-template", confidence

                if "fix:debug" in command_name.lower():
                    basis = str(parsed.get("featureSlug") or feature_id)
                    return f"Debug - {basis}", "command-template", 0.62

            ordered_commands = _select_linking_commands(command_names)
            if ordered_commands:
                primary = ordered_commands[0]
                return f"{primary} - {feature_id}", "command-fallback", 0.55
            return f"Session - {feature_id}", "feature-fallback", 0.35

        features = await self.feature_repo.list_all(project_id)
        feature_ref_paths: dict[str, set[str]] = {}
        feature_slug_aliases: dict[str, set[str]] = {}
        feature_command_hints: dict[str, set[str]] = {}
        task_bound_feature_sessions: set[tuple[str, str]] = set()

        for f in features:
            feature_id = f["id"]
            await self.link_repo.delete_auto_links("feature", feature_id)
            feature_ref_paths[feature_id] = set()
            feature_slug_aliases[feature_id] = {feature_id.lower(), _canonical_slug(feature_id)}
            feature_command_hints[feature_id] = set()

            try:
                f_data = json.loads(f.get("data_json") or "{}")
            except Exception:
                f_data = {}

            for doc in f_data.get("linkedDocs", []):
                if not isinstance(doc, dict):
                    continue
                doc_path = _normalize_ref_path(str(doc.get("filePath") or ""))
                if doc_path:
                    feature_ref_paths[feature_id].add(doc_path)
                    doc_slug = _slug_from_path(doc_path)
                    if doc_slug:
                        feature_slug_aliases[feature_id].add(doc_slug)
                        feature_slug_aliases[feature_id].add(_canonical_slug(doc_slug))

            # Command names associated with plan-heavy workflows.
            feature_command_hints[feature_id].update(_KEY_WORKFLOW_COMMANDS)

            # Link feature → tasks
            tasks = await self.task_repo.list_by_feature(feature_id)
            for t in tasks:
                await self.link_repo.delete_auto_links("task", t["id"])

                source_file = _normalize_ref_path(str(t.get("source_file") or ""))
                if source_file:
                    feature_ref_paths[feature_id].add(source_file)
                    source_slug = _slug_from_path(source_file)
                    if source_slug:
                        feature_slug_aliases[feature_id].add(source_slug)
                        feature_slug_aliases[feature_id].add(_canonical_slug(source_slug))

                await self.link_repo.upsert({
                    "source_type": "feature",
                    "source_id": feature_id,
                    "target_type": "task",
                    "target_id": t["id"],
                    "link_type": "child",
                    "origin": "auto",
                })
                stats["created"] += 1

                # Link task → session if available
                if t.get("session_id"):
                    feature_session_metadata = {
                        "linkStrategy": "task_frontmatter",
                        "taskId": t.get("id"),
                        "taskSource": t.get("source_file"),
                        "commitHash": t.get("commit_hash") or "",
                    }
                    await self.link_repo.upsert({
                        "source_type": "feature",
                        "source_id": feature_id,
                        "target_type": "session",
                        "target_id": t["session_id"],
                        "link_type": "related",
                        "origin": "auto",
                        "confidence": 1.0,
                        "metadata_json": json.dumps(feature_session_metadata),
                    })
                    stats["created"] += 1
                    task_bound_feature_sessions.add((feature_id, str(t["session_id"])))

                    await self.link_repo.upsert({
                        "source_type": "task",
                        "source_id": t["id"],
                        "target_type": "session",
                        "target_id": t["session_id"],
                        "link_type": "related",
                        "origin": "auto",
                    })
                    stats["created"] += 1

        # Build feature ↔ session links from session evidence.
        total_sessions = await self.session_repo.count(project_id, {"include_subagents": True})
        sessions_data: list[dict[str, Any]] = []
        page_size = 250
        for offset in range(0, total_sessions, page_size):
            page = await self.session_repo.list_paginated(
                offset,
                page_size,
                project_id,
                "started_at",
                "desc",
                {"include_subagents": True},
            )
            sessions_data.extend(page)

        for s in sessions_data:
            session_id = s["id"]
            file_updates = await self.session_repo.get_file_updates(session_id)
            artifacts = await self.session_repo.get_artifacts(session_id)
            logs = await self.session_repo.get_logs(session_id)

            command_events: list[dict[str, Any]] = []
            tagged_commands: list[dict[str, Any]] = []
            latest_summary = ""
            custom_title = ""
            queue_events: list[dict[str, str]] = []
            pr_links: list[dict[str, str]] = []

            for log in logs:
                log_type = str(log.get("type") or "")
                metadata_raw = log.get("metadata_json")
                try:
                    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) and metadata_raw else {}
                except Exception:
                    metadata = {}

                if log_type == "message":
                    content_text = str(log.get("content") or "")
                    for command_name, args_text in _extract_tagged_commands_from_message(content_text):
                        tagged_commands.append({
                            "name": command_name,
                            "args": args_text,
                            "parsed": _parse_command_context(command_name, args_text) if args_text else {},
                        })
                    continue

                if log_type == "command":
                    command_name = _normalize_command_label(str(log.get("content") or ""))
                    args_text = str(metadata.get("args") or "")
                    parsed = metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {}

                    if not args_text or not parsed:
                        tagged = _pop_matching_tagged_command(tagged_commands, command_name)
                        if tagged:
                            if not args_text:
                                args_text = str(tagged.get("args") or "")
                            if not parsed and isinstance(tagged.get("parsed"), dict):
                                parsed = tagged.get("parsed")

                    if not parsed and args_text:
                        parsed = _parse_command_context(command_name, args_text)
                    command_events.append({
                        "name": command_name,
                        "args": args_text,
                        "parsed": parsed if isinstance(parsed, dict) else {},
                    })
                    continue

                if log_type != "system":
                    continue

                event_type = str(metadata.get("eventType") or "").strip().lower()
                if event_type == "summary":
                    text = str(log.get("content") or "").strip()
                    if text:
                        latest_summary = text
                elif event_type == "custom-title":
                    text = str(log.get("content") or "").strip()
                    if text:
                        custom_title = text
                elif event_type == "queue-operation":
                    queue_event = {
                        "taskId": str(metadata.get("task-id") or ""),
                        "status": str(metadata.get("status") or ""),
                        "summary": str(metadata.get("summary") or log.get("content") or ""),
                    }
                    if queue_event["taskId"] or queue_event["summary"]:
                        queue_events.append(queue_event)
                elif event_type == "pr-link":
                    pr_link = {
                        "prNumber": str(metadata.get("prNumber") or ""),
                        "prUrl": str(metadata.get("prUrl") or ""),
                        "prRepository": str(metadata.get("prRepository") or ""),
                    }
                    if pr_link["prUrl"] or pr_link["prNumber"]:
                        pr_links.append(pr_link)

            for tagged in tagged_commands:
                command_name = _normalize_command_label(str(tagged.get("name") or ""))
                if not command_name:
                    continue
                command_events.append({
                    "name": command_name,
                    "args": str(tagged.get("args") or ""),
                    "parsed": tagged.get("parsed") if isinstance(tagged.get("parsed"), dict) else {},
                })

            command_name_candidates = {
                str(a.get("title") or "").strip()
                for a in artifacts
                if str(a.get("type") or "").strip().lower() == "command" and str(a.get("title") or "").strip()
            }
            command_name_candidates.update(
                event.get("name", "").strip()
                for event in command_events
                if isinstance(event.get("name"), str) and event.get("name", "").strip()
            )
            ordered_commands = _select_linking_commands(command_name_candidates)
            command_names = set(ordered_commands)
            command_names_lower = {name.lower() for name in command_names}

            session_commit_hashes: set[str] = set()
            if s.get("git_commit_hash"):
                session_commit_hashes.add(str(s["git_commit_hash"]))
            try:
                parsed_hashes = json.loads(s.get("git_commit_hashes_json") or "[]")
            except Exception:
                parsed_hashes = []
            if isinstance(parsed_hashes, list):
                for h in parsed_hashes:
                    if isinstance(h, str) and h.strip():
                        session_commit_hashes.add(h.strip())

            candidates: list[dict[str, Any]] = []
            for feature_id, refs in feature_ref_paths.items():
                signal_weights: list[float] = []
                evidence: list[dict[str, Any]] = []
                has_write = False
                has_command_path = False
                has_read_reference = False

                for update in file_updates:
                    update_path = str(update.get("file_path") or "")
                    if not update_path:
                        continue
                    if not any(_path_matches(update_path, ref_path) for ref_path in refs):
                        continue

                    weight, signal_type = _source_weight(str(update.get("source_tool_name") or ""))
                    signal_weights.append(weight)
                    if signal_type == "file_write":
                        has_write = True
                    if signal_type == "file_read":
                        has_read_reference = True
                    evidence.append({
                        "type": signal_type,
                        "path": update_path,
                        "sourceTool": update.get("source_tool_name"),
                        "weight": weight,
                    })

                if (feature_id, session_id) in task_bound_feature_sessions:
                    continue

                feature_aliases = feature_slug_aliases.get(feature_id, set())
                for command_event in command_events:
                    command_name = str(command_event.get("name") or "").strip()
                    if _is_non_consequential_command(command_name):
                        continue
                    parsed = command_event.get("parsed") if isinstance(command_event.get("parsed"), dict) else {}
                    command_slug = str(parsed.get("featureSlug") or "").lower()
                    command_slug_canonical = _canonical_slug(str(parsed.get("featureSlugCanonical") or command_slug))
                    command_paths = parsed.get("paths", [])
                    if not isinstance(command_paths, list):
                        command_paths = []

                    matched = False
                    if command_slug and (command_slug in feature_aliases or command_slug_canonical in feature_aliases):
                        matched = True
                    else:
                        for command_path in command_paths:
                            if not isinstance(command_path, str):
                                continue
                            if any(_path_matches(command_path, ref_path) for ref_path in refs):
                                matched = True
                                break
                            path_slug = _slug_from_path(command_path)
                            if path_slug and (_canonical_slug(path_slug) in feature_aliases or path_slug in feature_aliases):
                                matched = True
                                break

                    if matched:
                        has_command_path = True
                        signal_weights.append(0.96)
                        signal = {
                            "type": "command_args_path",
                            "path": str(parsed.get("featurePath") or (command_paths[0] if command_paths else "")),
                            "command": command_name,
                            "weight": 0.96,
                        }
                        phase_token = parsed.get("phaseToken")
                        if isinstance(phase_token, str) and phase_token:
                            signal["phaseToken"] = phase_token
                        evidence.append(signal)

                feature_hints = {hint.lower() for hint in feature_command_hints.get(feature_id, set())}
                has_command_hint = bool(command_names_lower.intersection(feature_hints))
                base_confidence = _confidence_from_signals(signal_weights, has_command_path, has_command_hint, has_write)
                if base_confidence <= 0:
                    continue

                raw_signal_weight = round(sum(signal_weights), 3)
                candidates.append({
                    "featureId": feature_id,
                    "baseConfidence": base_confidence,
                    "rawSignalWeight": raw_signal_weight,
                    "evidence": evidence,
                    "hasWrite": has_write,
                    "hasCommandPath": has_command_path,
                    "hasReadOnlySignals": has_read_reference and not has_write and not has_command_path,
                })

            total_signal_weight = sum(candidate["rawSignalWeight"] for candidate in candidates)
            for candidate in candidates:
                feature_id = candidate["featureId"]
                share = (
                    candidate["rawSignalWeight"] / total_signal_weight
                    if total_signal_weight > 0
                    else 0.0
                )
                confidence = float(candidate["baseConfidence"])
                if share < 0.50:
                    confidence -= 0.20
                elif share < 0.70:
                    confidence -= 0.10
                if candidate["hasReadOnlySignals"]:
                    confidence -= 0.08
                confidence = round(max(0.35, min(0.95, confidence)), 3)
                title, title_source, title_confidence = _derive_session_title(
                    feature_id,
                    custom_title,
                    latest_summary,
                    command_events,
                    command_names,
                    file_updates,
                )
                metadata = {
                    "linkStrategy": "session_evidence",
                    "signals": candidate["evidence"][:25],
                    "commands": ordered_commands[:15],
                    "commitHashes": sorted(session_commit_hashes),
                    "ambiguityShare": round(share, 3),
                    "title": title,
                    "titleSource": title_source,
                    "titleConfidence": round(title_confidence, 3),
                    "prLinks": pr_links[:10],
                    "queueEvents": queue_events[:10],
                }
                await self.link_repo.upsert({
                    "source_type": "feature",
                    "source_id": feature_id,
                    "target_type": "session",
                    "target_id": session_id,
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": confidence,
                    "metadata_json": json.dumps(metadata),
                })
                stats["created"] += 1

        # Link documents → features via frontmatter linkedFeatures
        docs = await self.document_repo.list_all(project_id)
        for d in docs:
            await self.link_repo.delete_auto_links("document", d["id"])
            fm = d.get("frontmatter_json", "{}")
            try:
                fm_dict = json.loads(fm) if isinstance(fm, str) else fm
            except Exception:
                fm_dict = {}

            linked_features = fm_dict.get("linkedFeatures", [])
            for feat_ref in linked_features:
                if feat_ref:
                    await self.link_repo.upsert({
                        "source_type": "document",
                        "source_id": d["id"],
                        "target_type": "feature",
                        "target_id": str(feat_ref),
                        "link_type": "related",
                        "origin": "auto",
                    })
                    stats["created"] += 1
        return stats


    # ── Analytics Snapshot ──────────────────────────────────────────

    async def _capture_analytics(self, project_id: str) -> None:
        """Capture a point-in-time snapshot of project metrics."""
        now = datetime.now(timezone.utc).isoformat()

        # 1. Session Metrics
        s_stats = await self.session_repo.get_project_stats(project_id)
        
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "session_count",
            "value": s_stats.get("count", 0),
            "captured_at": now,
        })
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "session_cost",
            "value": s_stats.get("cost", 0.0),
            "captured_at": now,
        })
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "session_tokens",
            "value": s_stats.get("tokens", 0),
            "captured_at": now,
        })
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "session_duration",
            "value": s_stats.get("duration", 0.0),
            "captured_at": now,
        })

        # 2. Task Metrics
        t_stats = await self.task_repo.get_project_stats(project_id)

        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "task_velocity",  # Total completed tasks for now
            "value": t_stats.get("completed", 0),
            "captured_at": now,
        })
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "task_completion_pct",
            "value": t_stats.get("completion_pct", 0.0),
            "captured_at": now,
        })

        # 3. Feature Progress
        f_stats = await self.feature_repo.get_project_stats(project_id)
        
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "feature_progress",
            "value": f_stats.get("avg_progress", 0.0),
            "captured_at": now,
        })

        # 4. Tool Usage
        tool_stats = await self.session_repo.get_tool_stats(project_id)
        
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "tool_call_count",
            "value": tool_stats.get("calls", 0),
            "captured_at": now,
        })
        await self.analytics_repo.insert_entry({
            "project_id": project_id,
            "metric_type": "tool_success_rate",
            "value": tool_stats.get("success_rate", 0.0),
            "captured_at": now,
        })
