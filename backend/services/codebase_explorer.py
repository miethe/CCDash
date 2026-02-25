"""Codebase explorer aggregation service."""
from __future__ import annotations

import fnmatch
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from backend import config

try:
    import pathspec
except Exception:  # pragma: no cover - fallback path
    pathspec = None


BUILTIN_EXCLUDES = (".git/", "node_modules/", "dist/", "coverage/", ".venv/")
CACHE_TTL_SECONDS = 30.0
ACTION_WEIGHTS = {
    "create": 1.00,
    "update": 0.80,
    "delete": 0.70,
    "read": 0.40,
}


def clear_codebase_cache(project_id: str | None = None) -> None:
    """Clear in-memory codebase snapshot cache."""
    if project_id:
        keys = [key for key in _CACHE.keys() if key[0] == project_id]
        for key in keys:
            _CACHE.pop(key, None)
        return
    _CACHE.clear()


def _safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_epoch(timestamp: str | None) -> float:
    if not timestamp:
        return 0.0
    try:
        return max(0.0, float(time.mktime(time.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S"))))
    except Exception:
        try:
            return max(0.0, float(time.mktime(time.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S"))))
        except Exception:
            return 0.0


def _normalize_rel_path(raw: str | None) -> str:
    value = str(raw or "").replace("\\", "/").strip()
    if not value:
        return ""
    value = value.lstrip("/")
    if value.startswith("./"):
        value = value[2:]
    parts: list[str] = []
    for token in value.split("/"):
        clean = token.strip()
        if not clean or clean == ".":
            continue
        if clean == "..":
            raise ValueError("Path traversal is not allowed")
        parts.append(clean)
    return "/".join(parts)


def _normalize_project_file_path(raw: str | None, project_root: Path) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")

    candidate = Path(text).expanduser()
    root = project_root.resolve(strict=False)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
        try:
            rel = resolved.relative_to(root)
            return _normalize_rel_path(str(rel))
        except ValueError:
            raw_norm = str(resolved).replace("\\", "/")
            root_norm = str(root).replace("\\", "/").rstrip("/")
            if raw_norm.startswith(f"{root_norm}/"):
                return _normalize_rel_path(raw_norm[len(root_norm) + 1 :])
            return ""

    try:
        return _normalize_rel_path(text)
    except ValueError:
        return ""


def _resolve_safe_path(project_root: Path, requested_path: str) -> tuple[str, Path]:
    rel = _normalize_rel_path(requested_path)
    if not rel:
        raise ValueError("File path cannot be empty")

    root = project_root.resolve(strict=False)
    candidate = (root / rel).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Requested path escapes the project root") from exc
    return rel, candidate


def _normalize_action(action: str | None, source_tool_name: str | None = None) -> str:
    normalized = (action or "").strip().lower()
    if normalized == "read":
        return "read"
    if normalized == "create":
        return "create"
    if normalized in {"update", "write"}:
        return "update"
    if normalized in {"delete", "remove"}:
        return "delete"

    tool = (source_tool_name or "").strip().lower()
    if tool in {"read", "readfile"}:
        return "read"
    if tool in {"write", "writefile", "edit", "multiedit"}:
        return "update"
    if tool in {"delete", "deletefile"}:
        return "delete"
    return "update"


def _sqlite_to_postgres(query: str) -> str:
    index = 0
    out: list[str] = []
    for ch in query:
        if ch == "?":
            index += 1
            out.append(f"${index}")
        else:
            out.append(ch)
    return "".join(out)


async def _fetch_rows(db: Any, query: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    values = list(params or [])
    if config.DB_BACKEND == "postgres":
        rows = await db.fetch(_sqlite_to_postgres(query), *values)
        return [dict(row) for row in rows]
    async with db.execute(query, tuple(values)) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


class _IgnoreMatcher:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._patterns: list[str] = []
        self._spec = None

        gitignore = project_root / ".gitignore"
        if gitignore.exists():
            try:
                lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
                self._patterns = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
            except Exception:
                self._patterns = []

        if pathspec and self._patterns:
            try:
                self._spec = pathspec.PathSpec.from_lines("gitwildmatch", self._patterns)
            except Exception:
                self._spec = None

    def should_ignore(self, rel_path: str, is_dir: bool = False) -> bool:
        rel = (rel_path or "").replace("\\", "/").strip("/")
        if not rel:
            return False

        for blocked in BUILTIN_EXCLUDES:
            token = blocked.strip("/").lower()
            lowered = rel.lower()
            if lowered == token or lowered.startswith(f"{token}/"):
                return True

        if self._spec:
            if self._spec.match_file(rel):
                return True
            if is_dir and self._spec.match_file(f"{rel}/"):
                return True
            return False

        for pattern in self._patterns:
            if pattern.startswith("!"):
                continue
            if pattern.endswith("/"):
                base = pattern.rstrip("/").lower()
                lowered = rel.lower()
                if lowered == base or lowered.startswith(f"{base}/"):
                    return True
                continue
            if "/" in pattern:
                if fnmatch.fnmatch(rel, pattern):
                    return True
            else:
                if fnmatch.fnmatch(PurePosixPath(rel).name, pattern):
                    return True
        return False


@dataclass
class FileEvent:
    session_id: str
    root_session_id: str
    parent_session_id: str
    session_status: str
    session_started_at: str
    session_ended_at: str
    session_total_cost: float
    session_agent_id: str
    file_path: str
    action: str
    file_type: str
    timestamp: str
    additions: int
    deletions: int
    agent_name: str
    source_log_id: str
    source_tool_name: str


@dataclass
class FileSummaryInternal:
    file_path: str
    file_name: str
    directory: str
    exists: bool
    size_bytes: int
    last_modified: str
    actions: set[str] = field(default_factory=set)
    touch_count: int = 0
    session_ids: set[str] = field(default_factory=set)
    agent_names: set[str] = field(default_factory=set)
    last_touched_at: str = ""
    additions: int = 0
    deletions: int = 0
    net_diff: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)
    session_actions: dict[str, set[str]] = field(default_factory=dict)
    source_log_ids: set[str] = field(default_factory=set)
    features: list[dict[str, Any]] = field(default_factory=list)

    def apply_event(self, event: FileEvent) -> None:
        action = event.action
        self.actions.add(action)
        self.touch_count += 1
        self.session_ids.add(event.session_id)
        if event.agent_name:
            self.agent_names.add(event.agent_name)
        if event.timestamp and (not self.last_touched_at or _safe_epoch(event.timestamp) >= _safe_epoch(self.last_touched_at)):
            self.last_touched_at = event.timestamp
        self.additions += max(0, int(event.additions))
        self.deletions += max(0, int(event.deletions))
        self.net_diff = self.additions - self.deletions
        self.action_counts[action] = self.action_counts.get(action, 0) + 1
        self.session_actions.setdefault(event.session_id, set()).add(action)
        if event.source_log_id:
            self.source_log_ids.add(event.source_log_id)


@dataclass
class Snapshot:
    project_id: str
    project_root: Path
    generated_at: float
    summaries: dict[str, FileSummaryInternal]
    events_by_file: dict[str, list[FileEvent]]
    sessions_by_id: dict[str, dict[str, Any]]
    feature_links_by_session: dict[str, list[dict[str, Any]]]
    documents_by_path: dict[str, list[dict[str, Any]]]
    referenced_documents_by_path: dict[str, list[dict[str, Any]]]


@dataclass
class _CacheEntry:
    expires_at: float
    snapshot: Snapshot


_CACHE: dict[tuple[str, str], _CacheEntry] = {}


class CodebaseExplorerService:
    """Builds tree/list/detail payloads for codebase exploration."""

    def __init__(self, db: Any, project: Any):
        self.db = db
        self.project = project
        self.project_root = Path(project.path).expanduser().resolve(strict=False)

    async def get_tree(
        self,
        prefix: str = "",
        depth: int = 4,
        include_untouched: bool = False,
        search: str = "",
    ) -> dict[str, Any]:
        snapshot = await self._get_snapshot(include_untouched=include_untouched)
        normalized_prefix = _normalize_rel_path(prefix) if prefix else ""
        max_depth = max(1, int(depth))
        needle = (search or "").strip().lower()

        root_node: dict[str, Any] = {
            "path": normalized_prefix,
            "name": normalized_prefix.split("/")[-1] if normalized_prefix else ".",
            "nodeType": "folder",
            "depth": 0,
            "parentPath": "",
            "touchCount": 0,
            "isTouched": False,
            "lastTouchedAt": "",
            "actions": [],
            "_actionSet": set(),
            "_sessionIds": set(),
            "_children": {},
        }
        nodes_by_path: dict[str, dict[str, Any]] = {normalized_prefix: root_node}

        total_files = 0
        for path, summary in snapshot.summaries.items():
            if normalized_prefix and path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
                continue
            if not include_untouched and summary.touch_count == 0:
                continue
            if needle and needle not in path.lower() and needle not in summary.file_name.lower():
                continue

            total_files += 1
            relative = path[len(normalized_prefix) + 1 :] if normalized_prefix and path.startswith(f"{normalized_prefix}/") else ("" if path == normalized_prefix else path)
            if not relative:
                continue
            parts = [part for part in relative.split("/") if part]
            if not parts:
                continue

            parent_path = normalized_prefix
            traversed_path = normalized_prefix
            for idx, part in enumerate(parts):
                relative_depth = idx + 1
                if relative_depth > max_depth:
                    parent = nodes_by_path.get(parent_path)
                    if parent is not None:
                        parent["hasChildren"] = True
                    break

                traversed_path = f"{traversed_path}/{part}".strip("/") if traversed_path else part
                is_leaf = idx == len(parts) - 1
                is_file_node = is_leaf
                if relative_depth == max_depth and not is_leaf:
                    is_file_node = False
                node_type = "file" if is_file_node else "folder"

                node = nodes_by_path.get(traversed_path)
                if node is None:
                    node = {
                        "path": traversed_path,
                        "name": part,
                        "nodeType": node_type,
                        "depth": relative_depth,
                        "parentPath": parent_path,
                        "touchCount": 0,
                        "isTouched": False,
                        "lastTouchedAt": "",
                        "actions": [],
                        "_actionSet": set(),
                        "_sessionIds": set(),
                        "_children": {},
                    }
                    nodes_by_path[traversed_path] = node
                    parent = nodes_by_path.get(parent_path)
                    if parent is not None:
                        parent["_children"][traversed_path] = node

                if summary.touch_count > 0:
                    node["touchCount"] += summary.touch_count
                    node["isTouched"] = True
                    node["_sessionIds"].update(summary.session_ids)
                    node["_actionSet"].update(summary.actions)
                    if summary.last_touched_at and (
                        not node["lastTouchedAt"] or _safe_epoch(summary.last_touched_at) >= _safe_epoch(node["lastTouchedAt"])
                    ):
                        node["lastTouchedAt"] = summary.last_touched_at

                if node_type == "file":
                    node["sizeBytes"] = summary.size_bytes
                    node["exists"] = summary.exists
                    node["sessionCount"] = len(summary.session_ids)
                    node["featureCount"] = len(summary.features)
                parent_path = traversed_path
                if is_leaf:
                    break

        def finalize(node: dict[str, Any]) -> dict[str, Any]:
            children = [finalize(child) for child in node["_children"].values()]
            children.sort(key=lambda item: (item["nodeType"] != "folder", item["name"].lower()))
            result: dict[str, Any] = {
                "path": node["path"],
                "name": node["name"],
                "nodeType": node["nodeType"],
                "depth": node["depth"],
                "parentPath": node["parentPath"],
                "touchCount": node["touchCount"],
                "isTouched": node["isTouched"],
                "lastTouchedAt": node["lastTouchedAt"],
                "actions": sorted(node["_actionSet"]),
                "sessionCount": node.get("sessionCount", len(node["_sessionIds"])),
                "featureCount": node.get("featureCount", 0),
                "hasChildren": bool(children),
            }
            if node["nodeType"] == "file":
                result["sizeBytes"] = node.get("sizeBytes", 0)
                result["exists"] = node.get("exists", False)
            if children:
                result["children"] = children
            return result

        tree_nodes = [finalize(child) for child in root_node["_children"].values()]
        tree_nodes.sort(key=lambda item: (item["nodeType"] != "folder", item["name"].lower()))

        return {
            "prefix": normalized_prefix,
            "depth": max_depth,
            "includeUntouched": include_untouched,
            "search": search or "",
            "totalFiles": total_files,
            "nodes": tree_nodes,
        }

    async def list_files(
        self,
        prefix: str = "",
        search: str = "",
        include_untouched: bool = False,
        action: str = "",
        feature_id: str = "",
        sort_by: str = "last_touched",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        snapshot = await self._get_snapshot(include_untouched=include_untouched)
        normalized_prefix = _normalize_rel_path(prefix) if prefix else ""
        needle = (search or "").strip().lower()
        action_filter = (action or "").strip().lower()
        feature_filter = (feature_id or "").strip().lower()

        items = []
        for summary in snapshot.summaries.values():
            if normalized_prefix and summary.file_path != normalized_prefix and not summary.file_path.startswith(f"{normalized_prefix}/"):
                continue
            if not include_untouched and summary.touch_count == 0:
                continue
            if needle and needle not in summary.file_path.lower() and needle not in summary.file_name.lower():
                continue
            if action_filter and action_filter not in summary.actions:
                continue
            if feature_filter and not any(str(feature.get("featureId", "")).lower() == feature_filter for feature in summary.features):
                continue
            items.append(self._serialize_summary(summary))

        reverse = (sort_order or "desc").lower() != "asc"
        sort_key = self._sort_key(sort_by)
        items.sort(key=sort_key, reverse=reverse)

        start = max(0, int(offset))
        end = start + max(1, min(500, int(limit)))
        page_items = items[start:end]
        return {
            "items": page_items,
            "total": len(items),
            "offset": start,
            "limit": end - start,
        }

    async def get_file_detail(self, file_path: str, activity_limit: int = 100) -> dict[str, Any]:
        rel_path, absolute_path = _resolve_safe_path(self.project_root, file_path)
        snapshot = await self._get_snapshot(include_untouched=False)
        summary = snapshot.summaries.get(rel_path)
        if summary is None:
            # Fallback to full snapshot for untouched files when requested directly.
            snapshot = await self._get_snapshot(include_untouched=True)
            summary = snapshot.summaries.get(rel_path)
        if summary is None:
            raise FileNotFoundError(f"File not tracked in codebase explorer: {rel_path}")

        events = sorted(snapshot.events_by_file.get(rel_path, []), key=lambda evt: _safe_epoch(evt.timestamp), reverse=True)
        session_rollups: dict[str, dict[str, Any]] = {}
        for event in events:
            session_info = snapshot.sessions_by_id.get(event.session_id, {})
            rollup = session_rollups.get(event.session_id)
            if rollup is None:
                rollup = {
                    "sessionId": event.session_id,
                    "rootSessionId": session_info.get("rootSessionId", event.root_session_id),
                    "parentSessionId": session_info.get("parentSessionId", event.parent_session_id),
                    "status": session_info.get("status", event.session_status),
                    "startedAt": session_info.get("startedAt", event.session_started_at),
                    "endedAt": session_info.get("endedAt", event.session_ended_at),
                    "totalCost": session_info.get("totalCost", event.session_total_cost),
                    "touchCount": 0,
                    "actions": set(),
                    "lastTouchedAt": "",
                    "agentNames": set(),
                }
                session_rollups[event.session_id] = rollup
            rollup["touchCount"] += 1
            rollup["actions"].add(event.action)
            if event.agent_name:
                rollup["agentNames"].add(event.agent_name)
            if event.timestamp and (not rollup["lastTouchedAt"] or _safe_epoch(event.timestamp) >= _safe_epoch(rollup["lastTouchedAt"])):
                rollup["lastTouchedAt"] = event.timestamp

        session_items = []
        for value in session_rollups.values():
            session_items.append(
                {
                    "sessionId": value["sessionId"],
                    "rootSessionId": value["rootSessionId"],
                    "parentSessionId": value["parentSessionId"],
                    "status": value["status"],
                    "startedAt": value["startedAt"],
                    "endedAt": value["endedAt"],
                    "totalCost": float(value["totalCost"] or 0.0),
                    "touchCount": value["touchCount"],
                    "actions": sorted(value["actions"]),
                    "lastTouchedAt": value["lastTouchedAt"],
                    "agentNames": sorted(value["agentNames"]),
                }
            )
        session_items.sort(key=lambda item: (_safe_epoch(item["lastTouchedAt"]), item["sessionId"]), reverse=True)

        source_docs = snapshot.documents_by_path.get(rel_path, [])
        ref_docs = snapshot.referenced_documents_by_path.get(rel_path, [])
        docs_seen: set[tuple[str, str]] = set()
        document_items: list[dict[str, Any]] = []
        for payload in [*source_docs, *ref_docs]:
            key = (payload.get("documentId", ""), payload.get("relation", ""))
            if key in docs_seen:
                continue
            docs_seen.add(key)
            document_items.append(payload)
        document_items.sort(key=lambda item: (item.get("relation", ""), item.get("title", "")))

        source_log_ids = {event.source_log_id for event in events if event.source_log_id}
        session_ids = {event.session_id for event in events}
        logs_by_key = await self._load_logs_by_source(session_ids)
        artifacts_by_source = await self._load_artifacts_by_source(session_ids)

        activity_entries = []
        for event in events[: max(1, min(500, int(activity_limit)))]:
            log_record = None
            if event.source_log_id:
                log_record = logs_by_key.get((event.session_id, event.source_log_id))
            artifact_list = artifacts_by_source.get((event.session_id, event.source_log_id), [])
            activity_entries.append(
                {
                    "id": f"{event.session_id}:{event.source_log_id or event.timestamp}:{event.action}",
                    "kind": "file_action",
                    "timestamp": event.timestamp,
                    "action": event.action,
                    "filePath": event.file_path,
                    "fileType": event.file_type,
                    "sessionId": event.session_id,
                    "rootSessionId": event.root_session_id,
                    "sourceLogId": event.source_log_id,
                    "sourceToolName": event.source_tool_name,
                    "additions": event.additions,
                    "deletions": event.deletions,
                    "agentName": event.agent_name,
                    "logType": (log_record or {}).get("type", ""),
                    "logContent": (log_record or {}).get("content", ""),
                    "linkedSessionId": (log_record or {}).get("linked_session_id", ""),
                    "artifactCount": len(artifact_list),
                    "artifactIds": [item.get("id", "") for item in artifact_list if item.get("id")],
                }
            )

        return {
            "filePath": summary.file_path,
            "fileName": summary.file_name,
            "directory": summary.directory,
            "absolutePath": str(absolute_path),
            "exists": summary.exists,
            "sizeBytes": summary.size_bytes,
            "lastModified": summary.last_modified,
            "actions": sorted(summary.actions),
            "touchCount": summary.touch_count,
            "sessionCount": len(summary.session_ids),
            "agentCount": len(summary.agent_names),
            "lastTouchedAt": summary.last_touched_at,
            "additions": summary.additions,
            "deletions": summary.deletions,
            "netDiff": summary.net_diff,
            "actionCounts": summary.action_counts,
            "sessions": session_items,
            "features": summary.features,
            "documents": document_items,
            "activity": activity_entries,
        }

    async def _get_snapshot(self, *, include_untouched: bool = False) -> Snapshot:
        project_id = str(self.project.id)
        mode = "full" if include_untouched else "touched"
        cache_key = (project_id, mode)
        now = time.time()
        cached = _CACHE.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.snapshot

        snapshot = await self._build_snapshot(include_untouched=include_untouched)
        _CACHE[cache_key] = _CacheEntry(expires_at=now + CACHE_TTL_SECONDS, snapshot=snapshot)
        return snapshot

    async def _build_snapshot(self, *, include_untouched: bool = False) -> Snapshot:
        # Full filesystem walk is only needed when untouched files are requested.
        summaries = self._scan_filesystem(self.project_root) if include_untouched else {}
        events_by_file: dict[str, list[FileEvent]] = {}
        sessions_by_id: dict[str, dict[str, Any]] = {}

        updates = await _fetch_rows(
            self.db,
            """
            SELECT
                fu.file_path,
                fu.action,
                fu.file_type,
                fu.action_timestamp,
                fu.additions,
                fu.deletions,
                fu.agent_name,
                fu.thread_session_id,
                fu.root_session_id,
                fu.source_log_id,
                fu.source_tool_name,
                s.id AS session_id,
                s.status AS session_status,
                s.started_at AS session_started_at,
                s.ended_at AS session_ended_at,
                s.parent_session_id AS parent_session_id,
                s.root_session_id AS session_root_session_id,
                s.agent_id AS session_agent_id,
                s.total_cost AS session_total_cost
            FROM session_file_updates fu
            JOIN sessions s ON s.id = fu.session_id
            WHERE s.project_id = ?
            ORDER BY fu.id DESC
            """,
            [self.project.id],
        )

        for row in updates:
            normalized = _normalize_project_file_path(row.get("file_path"), self.project_root)
            if not normalized:
                continue

            summary = summaries.get(normalized)
            if summary is None:
                summary = FileSummaryInternal(
                    file_path=normalized,
                    file_name=normalized.split("/")[-1],
                    directory="/".join(normalized.split("/")[:-1]),
                    exists=False,
                    size_bytes=0,
                    last_modified="",
                )
                summaries[normalized] = summary

            event = FileEvent(
                session_id=str(row.get("session_id") or ""),
                root_session_id=str(row.get("session_root_session_id") or row.get("root_session_id") or row.get("session_id") or ""),
                parent_session_id=str(row.get("parent_session_id") or ""),
                session_status=str(row.get("session_status") or ""),
                session_started_at=str(row.get("session_started_at") or ""),
                session_ended_at=str(row.get("session_ended_at") or ""),
                session_total_cost=float(row.get("session_total_cost") or 0.0),
                session_agent_id=str(row.get("session_agent_id") or ""),
                file_path=normalized,
                action=_normalize_action(str(row.get("action") or ""), str(row.get("source_tool_name") or "")),
                file_type=str(row.get("file_type") or "Other"),
                timestamp=str(row.get("action_timestamp") or row.get("session_started_at") or ""),
                additions=int(row.get("additions") or 0),
                deletions=int(row.get("deletions") or 0),
                agent_name=str(row.get("agent_name") or row.get("session_agent_id") or ""),
                source_log_id=str(row.get("source_log_id") or ""),
                source_tool_name=str(row.get("source_tool_name") or ""),
            )
            summary.apply_event(event)
            events_by_file.setdefault(normalized, []).append(event)

            sessions_by_id[event.session_id] = {
                "sessionId": event.session_id,
                "status": event.session_status,
                "startedAt": event.session_started_at,
                "endedAt": event.session_ended_at,
                "parentSessionId": event.parent_session_id,
                "rootSessionId": event.root_session_id,
                "agentId": event.session_agent_id,
                "totalCost": event.session_total_cost,
            }

        feature_links_by_session = await self._load_feature_links_by_session()
        self._apply_feature_involvement(summaries, feature_links_by_session)
        documents_by_path, referenced_documents_by_path = await self._load_document_maps()

        return Snapshot(
            project_id=str(self.project.id),
            project_root=self.project_root,
            generated_at=time.time(),
            summaries=summaries,
            events_by_file=events_by_file,
            sessions_by_id=sessions_by_id,
            feature_links_by_session=feature_links_by_session,
            documents_by_path=documents_by_path,
            referenced_documents_by_path=referenced_documents_by_path,
        )

    def _scan_filesystem(self, project_root: Path) -> dict[str, FileSummaryInternal]:
        matcher = _IgnoreMatcher(project_root)
        summaries: dict[str, FileSummaryInternal] = {}

        if not project_root.exists() or not project_root.is_dir():
            return summaries

        for root, dirs, files in os.walk(project_root):
            root_path = Path(root)
            rel_root = _normalize_project_file_path(str(root_path), project_root)

            kept_dirs = []
            for dirname in dirs:
                child_rel = f"{rel_root}/{dirname}".strip("/")
                if matcher.should_ignore(child_rel, is_dir=True):
                    continue
                kept_dirs.append(dirname)
            dirs[:] = kept_dirs

            for filename in files:
                rel_path = f"{rel_root}/{filename}".strip("/")
                if matcher.should_ignore(rel_path, is_dir=False):
                    continue
                full_path = root_path / filename
                try:
                    stat = full_path.stat()
                except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                    # Filesystem can change while scanning; skip missing/inaccessible entries.
                    continue
                summaries[rel_path] = FileSummaryInternal(
                    file_path=rel_path,
                    file_name=filename,
                    directory=rel_root,
                    exists=True,
                    size_bytes=int(stat.st_size),
                    last_modified=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
                )

        return summaries

    async def _load_feature_links_by_session(self) -> dict[str, list[dict[str, Any]]]:
        rows = await _fetch_rows(
            self.db,
            """
            SELECT
                el.source_id AS feature_id,
                el.target_id AS session_id,
                el.confidence AS confidence,
                el.metadata_json AS metadata_json,
                f.name AS feature_name,
                f.status AS feature_status,
                f.category AS feature_category
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE f.project_id = ?
              AND el.source_type = 'feature'
              AND el.target_type = 'session'
            UNION ALL
            SELECT
                el.target_id AS feature_id,
                el.source_id AS session_id,
                el.confidence AS confidence,
                el.metadata_json AS metadata_json,
                f.name AS feature_name,
                f.status AS feature_status,
                f.category AS feature_category
            FROM entity_links el
            JOIN features f ON f.id = el.target_id
            WHERE f.project_id = ?
              AND el.source_type = 'session'
              AND el.target_type = 'feature'
            """,
            [self.project.id, self.project.id],
        )

        by_session: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            session_id = str(row.get("session_id") or "")
            feature_id = str(row.get("feature_id") or "")
            if not session_id or not feature_id:
                continue

            metadata = _safe_json(row.get("metadata_json"))
            signals = metadata.get("signals", [])
            commands = metadata.get("commands", [])
            if not isinstance(signals, list):
                signals = []
            if not isinstance(commands, list):
                commands = []

            bucket = by_session.setdefault(session_id, {})
            existing = bucket.get(feature_id)
            confidence = float(row.get("confidence") or 0.0)
            item = {
                "featureId": feature_id,
                "featureName": str(row.get("feature_name") or feature_id),
                "featureStatus": str(row.get("feature_status") or ""),
                "featureCategory": str(row.get("feature_category") or ""),
                "confidence": confidence,
                "signals": signals,
                "commands": [str(command) for command in commands if isinstance(command, str)],
            }
            if not existing or confidence >= float(existing.get("confidence") or 0.0):
                bucket[feature_id] = item

        return {session_id: list(features.values()) for session_id, features in by_session.items()}

    async def _load_document_maps(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        docs_by_path: dict[str, list[dict[str, Any]]] = {}
        refs_by_path: dict[str, list[dict[str, Any]]] = {}

        docs = await _fetch_rows(
            self.db,
            """
            SELECT
                id,
                title,
                file_path,
                doc_type,
                category,
                status,
                status_normalized
            FROM documents
            WHERE project_id = ?
            """,
            [self.project.id],
        )
        for row in docs:
            normalized = _normalize_project_file_path(row.get("file_path"), self.project_root)
            if not normalized:
                continue
            docs_by_path.setdefault(normalized, []).append(
                {
                    "documentId": str(row.get("id") or ""),
                    "title": str(row.get("title") or ""),
                    "filePath": str(row.get("file_path") or ""),
                    "docType": str(row.get("doc_type") or ""),
                    "category": str(row.get("category") or ""),
                    "status": str(row.get("status_normalized") or row.get("status") or ""),
                    "relation": "source",
                }
            )

        refs = await _fetch_rows(
            self.db,
            """
            SELECT
                dr.ref_value_norm,
                dr.ref_value,
                d.id,
                d.title,
                d.file_path,
                d.doc_type,
                d.category,
                d.status,
                d.status_normalized
            FROM document_refs dr
            JOIN documents d ON d.id = dr.document_id
            WHERE dr.project_id = ?
              AND dr.ref_kind = 'path'
            """,
            [self.project.id],
        )
        for row in refs:
            normalized = _normalize_project_file_path(row.get("ref_value_norm") or row.get("ref_value"), self.project_root)
            if not normalized:
                continue
            refs_by_path.setdefault(normalized, []).append(
                {
                    "documentId": str(row.get("id") or ""),
                    "title": str(row.get("title") or ""),
                    "filePath": str(row.get("file_path") or ""),
                    "docType": str(row.get("doc_type") or ""),
                    "category": str(row.get("category") or ""),
                    "status": str(row.get("status_normalized") or row.get("status") or ""),
                    "relation": "reference",
                }
            )

        return docs_by_path, refs_by_path

    def _apply_feature_involvement(
        self,
        summaries: dict[str, FileSummaryInternal],
        feature_links_by_session: dict[str, list[dict[str, Any]]],
    ) -> None:
        for summary in summaries.values():
            if not summary.session_actions:
                summary.features = []
                continue

            by_feature: dict[str, dict[str, Any]] = {}
            for session_id, actions in summary.session_actions.items():
                max_action_weight = max((ACTION_WEIGHTS.get(action, 0.0) for action in actions), default=0.0)
                if max_action_weight <= 0.0:
                    continue

                for feature_link in feature_links_by_session.get(session_id, []):
                    feature_id = str(feature_link.get("featureId") or "")
                    confidence = float(feature_link.get("confidence") or 0.0)
                    if not feature_id or confidence <= 0.0:
                        continue

                    score = confidence * max_action_weight
                    if self._has_direct_path_signal(summary.file_path, feature_link.get("signals", [])):
                        score = max(score, min(1.0, confidence * 0.95))
                        score = min(1.0, score + 0.10)
                    score = max(0.0, min(1.0, score))

                    feature_rollup = by_feature.get(feature_id)
                    if feature_rollup is None:
                        feature_rollup = {
                            "featureId": feature_id,
                            "featureName": feature_link.get("featureName") or feature_id,
                            "featureStatus": feature_link.get("featureStatus") or "",
                            "featureCategory": feature_link.get("featureCategory") or "",
                            "score": score,
                            "maxConfidence": confidence,
                            "sessionIds": {session_id},
                            "actions": set(actions),
                        }
                        by_feature[feature_id] = feature_rollup
                    else:
                        feature_rollup["score"] = max(float(feature_rollup["score"]), score)
                        feature_rollup["maxConfidence"] = max(float(feature_rollup["maxConfidence"]), confidence)
                        feature_rollup["sessionIds"].add(session_id)
                        feature_rollup["actions"].update(actions)

            features = []
            for feature in by_feature.values():
                score = float(feature["score"])
                level = "peripheral"
                if score >= 0.75:
                    level = "primary"
                elif score >= 0.50:
                    level = "supporting"
                features.append(
                    {
                        "featureId": feature["featureId"],
                        "featureName": feature["featureName"],
                        "featureStatus": feature["featureStatus"],
                        "featureCategory": feature["featureCategory"],
                        "score": round(score, 3),
                        "confidence": round(float(feature["maxConfidence"]), 3),
                        "involvementLevel": level,
                        "sessionCount": len(feature["sessionIds"]),
                        "actions": sorted(feature["actions"]),
                    }
                )

            features.sort(key=lambda item: (-float(item["score"]), item["featureName"].lower()))
            summary.features = features

    def _has_direct_path_signal(self, file_path: str, signals: Any) -> bool:
        if not isinstance(signals, list):
            return False
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            raw_signal_path = signal.get("path")
            if not isinstance(raw_signal_path, str) or not raw_signal_path.strip():
                continue
            signal_path = _normalize_project_file_path(raw_signal_path, self.project_root)
            if not signal_path:
                continue
            if signal_path == file_path:
                return True
            if signal_path.endswith(f"/{file_path}") or file_path.endswith(f"/{signal_path}"):
                return True
        return False

    def _serialize_summary(self, summary: FileSummaryInternal) -> dict[str, Any]:
        return {
            "filePath": summary.file_path,
            "fileName": summary.file_name,
            "directory": summary.directory,
            "exists": summary.exists,
            "sizeBytes": summary.size_bytes,
            "lastModified": summary.last_modified,
            "actions": sorted(summary.actions),
            "touchCount": summary.touch_count,
            "sessionCount": len(summary.session_ids),
            "agentCount": len(summary.agent_names),
            "lastTouchedAt": summary.last_touched_at,
            "additions": summary.additions,
            "deletions": summary.deletions,
            "netDiff": summary.net_diff,
            "actionCounts": summary.action_counts,
            "featureCount": len(summary.features),
            "features": summary.features,
            "sourceLogIds": sorted(summary.source_log_ids),
        }

    def _sort_key(self, sort_by: str):
        token = (sort_by or "last_touched").strip().lower()
        if token == "path":
            return lambda item: item["filePath"].lower()
        if token == "file_name":
            return lambda item: item["fileName"].lower()
        if token == "touches":
            return lambda item: int(item["touchCount"])
        if token == "sessions":
            return lambda item: int(item["sessionCount"])
        if token == "agents":
            return lambda item: int(item["agentCount"])
        if token == "net_diff":
            return lambda item: int(item["netDiff"])
        return lambda item: _safe_epoch(item["lastTouchedAt"])

    async def _load_logs_by_source(self, session_ids: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
        if not session_ids:
            return {}
        placeholders = ",".join(["?"] * len(session_ids))
        rows = await _fetch_rows(
            self.db,
            f"""
            SELECT
                session_id,
                log_index,
                timestamp,
                type,
                content,
                tool_name,
                linked_session_id
            FROM session_logs
            WHERE session_id IN ({placeholders})
            """,
            list(session_ids),
        )
        logs: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            session_id = str(row.get("session_id") or "")
            log_index = int(row.get("log_index") or 0)
            source_log_id = f"log-{log_index}"
            logs[(session_id, source_log_id)] = row
        return logs

    async def _load_artifacts_by_source(self, session_ids: set[str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        if not session_ids:
            return {}
        placeholders = ",".join(["?"] * len(session_ids))
        rows = await _fetch_rows(
            self.db,
            f"""
            SELECT
                id,
                session_id,
                title,
                type,
                source,
                url,
                source_log_id
            FROM session_artifacts
            WHERE session_id IN ({placeholders})
            """,
            list(session_ids),
        )
        artifacts: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (str(row.get("session_id") or ""), str(row.get("source_log_id") or ""))
            artifacts.setdefault(key, []).append(row)
        return artifacts
