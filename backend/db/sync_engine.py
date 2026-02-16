"""Incremental file → DB sync engine.

Scans filesystem for changed files (mtime-based), parses them using
existing parsers, and upserts the results into the DB cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
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

        def _normalize_ref_path(raw: str) -> str:
            value = (raw or "").strip().strip("\"'`")
            if not value:
                return ""
            while value.startswith("./"):
                value = value[2:]
            return value

        def _path_matches(candidate: str, ref: str) -> bool:
            candidate_norm = _normalize_ref_path(candidate).replace("\\", "/")
            ref_norm = _normalize_ref_path(ref).replace("\\", "/")
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

        def _confidence_from_signals(weights: list[float], has_command: bool, has_write: bool, has_task_link: bool) -> float:
            if has_task_link:
                return 1.0
            if not weights:
                return 0.0
            score = max(weights)
            if len(weights) >= 2:
                score += 0.08
            if has_write:
                score += 0.08
            if has_command:
                score += 0.05
            return round(min(1.0, score), 3)

        features = await self.feature_repo.list_all(project_id)
        feature_ref_paths: dict[str, set[str]] = {}
        feature_command_hints: dict[str, set[str]] = {}
        task_bound_feature_sessions: set[tuple[str, str]] = set()

        for f in features:
            feature_id = f["id"]
            await self.link_repo.delete_auto_links("feature", feature_id)
            feature_ref_paths[feature_id] = set()
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

            # Command names associated with plan-heavy workflows.
            feature_command_hints[feature_id].update({
                "/dev:execute-phase",
                "/dev:quick-feature",
                "/plan:plan-feature",
                "/dev:implement-story",
                "/dev:complete-user-story",
            })

            # Link feature → tasks
            tasks = await self.task_repo.list_by_feature(feature_id)
            for t in tasks:
                await self.link_repo.delete_auto_links("task", t["id"])

                source_file = _normalize_ref_path(str(t.get("source_file") or ""))
                if source_file:
                    feature_ref_paths[feature_id].add(source_file)

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

            command_names = {
                str(a.get("title") or "").strip()
                for a in artifacts
                if str(a.get("type") or "").strip().lower() == "command" and str(a.get("title") or "").strip()
            }

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

            for feature_id, refs in feature_ref_paths.items():
                signal_weights: list[float] = []
                evidence: list[dict[str, Any]] = []
                has_write = False

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
                    evidence.append({
                        "type": signal_type,
                        "path": update_path,
                        "sourceTool": update.get("source_tool_name"),
                        "weight": weight,
                    })

                has_command_hint = bool(command_names.intersection(feature_command_hints.get(feature_id, set())))
                if (feature_id, session_id) in task_bound_feature_sessions:
                    continue
                confidence = _confidence_from_signals(signal_weights, has_command_hint, has_write, False)
                if confidence <= 0:
                    continue

                metadata = {
                    "linkStrategy": "session_evidence",
                    "signals": evidence[:25],
                    "commands": sorted(command_names)[:15],
                    "commitHashes": sorted(session_commit_hashes),
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
