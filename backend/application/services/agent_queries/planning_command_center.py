"""Aggregate Planning Command Center query service."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.planning_command_resolver import PlanningCommandResolver
from backend.application.services.worktree_git_state import WorktreeGitStateProbe
from backend.models import Feature, FeaturePhase, LinkedDocument

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .models import (
    PlanningCommandCenterArtifactDTO,
    PlanningCommandCenterBlockerDTO,
    PlanningCommandCenterCapabilitiesDTO,
    PlanningCommandCenterFeatureDTO,
    PlanningCommandCenterItemDTO,
    PlanningCommandCenterLaunchAgentDTO,
    PlanningCommandCenterLaunchBatchDTO,
    PlanningCommandCenterPageDTO,
    PlanningCommandCenterPhaseDTO,
    PlanningCommandCenterPhaseRowDTO,
    PlanningCommandCenterPullRequestDTO,
    PlanningCommandCenterRelatedFileDTO,
    PlanningCommandCenterStatusDTO,
    PlanningCommandCenterStoryPointsDTO,
    PlanningCommandCenterTierDTO,
    PlanningCommandCenterWorktreeDTO,
)
from .planning import (
    _effective_status,
    _feature_key,
    _is_mismatch,
    _linked_doc_from_row,
    _load_all_doc_rows,
    _load_all_features,
    _load_doc_rows_for_feature,
    _mismatch_state,
    _project_with_planning,
    _raw_status,
    _synthetic_feature_from_doc_rows,
)


_TERMINAL_STATUSES = {"done", "completed", "closed", "deferred", "superseded"}
_ACTIVE_STATUSES = {"active", "in-progress", "in_progress", "review"}
_REVIEW_STATUSES = {"review", "review-ready", "review_ready"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _doc_type(doc: LinkedDocument) -> str:
    return str(getattr(doc, "docType", "") or "").strip().lower()


def _doc_path(doc: LinkedDocument) -> str:
    return str(getattr(doc, "filePath", "") or "").strip()


def _doc_title(doc: LinkedDocument) -> str:
    return str(getattr(doc, "title", "") or _doc_path(doc) or "").strip()


def _dedupe_documents(docs: Iterable[LinkedDocument]) -> list[LinkedDocument]:
    seen: set[tuple[str, str]] = set()
    deduped: list[LinkedDocument] = []
    for doc in docs:
        key = (str(getattr(doc, "id", "") or ""), _doc_path(doc))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
    return deduped


def _phase_number(phase: FeaturePhase) -> int | None:
    try:
        return int(str(getattr(phase, "phase", "") or "").strip().replace("phase", ""))
    except (TypeError, ValueError):
        return None


def _phase_status(phase: FeaturePhase) -> str:
    ps = getattr(phase, "planningStatus", None)
    return str(_effective_status(ps) or getattr(phase, "status", "") or "").strip().lower()


def _completed_phase_count(phases: Sequence[FeaturePhase]) -> int:
    return sum(1 for phase in phases if _phase_status(phase) in _TERMINAL_STATUSES)


def _active_phase_number(phases: Sequence[FeaturePhase]) -> int | None:
    for phase in phases:
        num = _phase_number(phase)
        if num is not None and _phase_status(phase) in _ACTIVE_STATUSES:
            return num
    return None


def _next_phase_number(phases: Sequence[FeaturePhase]) -> int | None:
    numbers = sorted(num for phase in phases if (num := _phase_number(phase)) is not None)
    completed = sorted(
        num
        for phase in phases
        if (num := _phase_number(phase)) is not None and _phase_status(phase) in _TERMINAL_STATUSES
    )
    if not numbers:
        return None
    if not completed:
        return numbers[0]
    candidate = max(completed) + 1
    return candidate if candidate in numbers else None


def _feature_slug(feature: Feature) -> str:
    return str(getattr(feature, "id", "") or "").rsplit("/", 1)[-1]


def _tier_from_feature(feature: Feature) -> PlanningCommandCenterTierDTO:
    haystack = " ".join(
        [
            *[str(tag) for tag in getattr(feature, "tags", [])],
            str(getattr(feature, "complexity", "") or ""),
            str(getattr(feature, "summary", "") or ""),
        ]
    )
    match = re.search(r"\btier[-\s_:]*(\d+)\b", haystack, re.IGNORECASE)
    tier = int(match.group(1)) if match else None
    points_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:pts?|points?)\b", haystack, re.IGNORECASE)
    points = _safe_float(points_match.group(1), 0.0) if points_match else None
    return PlanningCommandCenterTierDTO(
        tier_number=tier,
        tier_name=f"Tier {tier}" if tier is not None else "",
        estimated_points=points,
    )


def _story_points(feature: Feature) -> PlanningCommandCenterStoryPointsDTO:
    phase_total = sum(max(0, _safe_int(getattr(phase, "totalTasks", 0))) for phase in feature.phases)
    phase_completed = sum(max(0, _safe_int(getattr(phase, "completedTasks", 0))) for phase in feature.phases)
    total = float(phase_total or _safe_int(getattr(feature, "totalTasks", 0)))
    completed = float(phase_completed or _safe_int(getattr(feature, "completedTasks", 0)))
    remaining = max(0.0, total - completed)
    return PlanningCommandCenterStoryPointsDTO(total=total, completed=completed, remaining=remaining)


def _phase_summary(feature: Feature) -> PlanningCommandCenterPhaseDTO:
    phases = list(feature.phases or [])
    current = _active_phase_number(phases)
    next_phase = _next_phase_number(phases)
    return PlanningCommandCenterPhaseDTO(
        current_phase=current,
        next_phase=next_phase,
        total_phases=len([phase for phase in phases if _phase_number(phase) is not None]),
        completed_phases=_completed_phase_count(phases),
    )


def _artifact_dtos(docs: Sequence[LinkedDocument]) -> list[PlanningCommandCenterArtifactDTO]:
    return [
        PlanningCommandCenterArtifactDTO(
            artifact_id=str(getattr(doc, "id", "") or _doc_path(doc)),
            path=_doc_path(doc),
            doc_type=_doc_type(doc),
            title=_doc_title(doc),
            status=str(getattr(doc, "status", "") or ""),
        )
        for doc in docs
    ]


def _related_files(docs: Sequence[LinkedDocument]) -> list[PlanningCommandCenterRelatedFileDTO]:
    items: list[PlanningCommandCenterRelatedFileDTO] = []
    for doc in docs:
        path = _doc_path(doc)
        stat = None
        try:
            if path:
                candidate = Path(path)
                stat = candidate.stat() if candidate.is_absolute() and candidate.exists() else None
        except OSError:
            stat = None
        items.append(
            PlanningCommandCenterRelatedFileDTO(
                path=path,
                doc_type=_doc_type(doc),
                size_bytes=stat.st_size if stat is not None else None,
                last_modified=str(stat.st_mtime) if stat is not None else "",
                addable=bool(path),
            )
        )
    return items


def _phase_rows(feature: Feature, docs: Sequence[LinkedDocument]) -> list[PlanningCommandCenterPhaseRowDTO]:
    rows: list[PlanningCommandCenterPhaseRowDTO] = []
    doc_paths = [_doc_path(doc) for doc in docs]
    for phase in feature.phases:
        num = _phase_number(phase)
        phase_token = str(getattr(phase, "phase", "") or num or "")
        phase_files = [
            path
            for path in doc_paths
            if phase_token and (f"phase-{phase_token}" in path.lower() or f"phase_{phase_token}" in path.lower())
        ]
        batches = list(getattr(phase, "phaseBatches", []) or [])
        agents = sorted(
            {
                str(agent)
                for batch in batches
                for agent in getattr(batch, "assignedAgents", []) or []
                if str(agent or "").strip()
            }
        )
        rows.append(
            PlanningCommandCenterPhaseRowDTO(
                phase_number=num,
                name=str(getattr(phase, "title", "") or f"Phase {phase_token}"),
                story_points=float(_safe_int(getattr(phase, "totalTasks", 0))),
                phase_files=phase_files,
                agents=agents,
                status=_phase_status(phase),
                details={
                    "total_tasks": _safe_int(getattr(phase, "totalTasks", 0)),
                    "completed_tasks": _safe_int(getattr(phase, "completedTasks", 0)),
                    "deferred_tasks": _safe_int(getattr(phase, "deferredTasks", 0)),
                },
            )
        )
    return rows


def _launch_batch(feature: Feature, phase_number: int | None) -> PlanningCommandCenterLaunchBatchDTO | None:
    for phase in feature.phases:
        if phase_number is not None and _phase_number(phase) != phase_number:
            continue
        batches = list(getattr(phase, "phaseBatches", []) or [])
        if not batches:
            continue
        batch = batches[0]
        agents = [
            PlanningCommandCenterLaunchAgentDTO(agent_id=str(agent), label=str(agent), state="queued")
            for agent in getattr(batch, "assignedAgents", []) or []
        ]
        return PlanningCommandCenterLaunchBatchDTO(
            batch_id=str(getattr(batch, "batchId", "") or ""),
            label=str(getattr(batch, "batchId", "") or "Launch batch"),
            readiness=str(getattr(batch, "readinessState", "") or "unknown"),
            agents=agents,
        )
    return None


def _worktree_dto(row: dict[str, Any] | None) -> PlanningCommandCenterWorktreeDTO | None:
    if not row:
        return None
    return PlanningCommandCenterWorktreeDTO(
        context_id=str(row.get("id") or ""),
        path=str(row.get("worktree_path") or ""),
        branch=str(row.get("branch") or ""),
        status=str(row.get("status") or ""),
        phase_number=row.get("phase_number"),
        batch_id=str(row.get("batch_id") or ""),
    )


def _pr_dto(feature: Feature) -> PlanningCommandCenterPullRequestDTO | None:
    refs = list(getattr(feature, "prRefs", []) or [])
    if not refs:
        return None
    first = str(refs[0] or "")
    number_match = re.search(r"/pull/(\d+)|#(\d+)", first)
    number = None
    if number_match:
        number = _safe_int(number_match.group(1) or number_match.group(2), 0) or None
    provider = "github" if "github.com" in first.lower() else ""
    return PlanningCommandCenterPullRequestDTO(provider=provider, number=number, url=first, state="linked")


def _blockers(feature: Feature) -> list[PlanningCommandCenterBlockerDTO]:
    blockers: list[PlanningCommandCenterBlockerDTO] = []
    quality = getattr(feature, "qualitySignals", None)
    if quality is not None and bool(getattr(quality, "hasBlockingSignals", False)):
        blockers.append(
            PlanningCommandCenterBlockerDTO(
                label="Quality signal",
                reason=str(getattr(quality, "testImpact", "") or "Blocking planning signal detected."),
                severity="high",
            )
        )
    for phase in feature.phases:
        if _phase_status(phase) == "blocked":
            blockers.append(
                PlanningCommandCenterBlockerDTO(
                    label=str(getattr(phase, "title", "") or getattr(phase, "phase", "") or "Blocked phase"),
                    reason="Phase is blocked.",
                    severity="medium",
                )
            )
    return blockers


def _capabilities(command: Any, feature: Feature) -> PlanningCommandCenterCapabilitiesDTO:
    command_text = str(getattr(command, "command", "") or "")
    unsupported = any(not bool(getattr(cap, "supported", True)) for cap in getattr(command, "required_capabilities", []) or [])
    has_pr = bool(getattr(feature, "prRefs", []) or [])
    status = str(getattr(feature, "status", "") or "").lower()
    return PlanningCommandCenterCapabilitiesDTO(
        copy_command=bool(command_text),
        launch=bool(command_text) and not unsupported,
        review=status in _REVIEW_STATUSES or has_pr,
        merge=has_pr,
        cleanup=has_pr or status in _TERMINAL_STATUSES,
        open_pr=has_pr,
        edit_command=bool(command_text),
    )


class PlanningCommandCenterQueryService:
    """Compose planning, execution, worktree, and resolver context in one read."""

    def __init__(
        self,
        *,
        resolver: PlanningCommandResolver | None = None,
        git_probe: WorktreeGitStateProbe | None = None,
    ) -> None:
        self.resolver = resolver or PlanningCommandResolver()
        self.git_probe = git_probe or WorktreeGitStateProbe()

    async def get_command_center(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
        q: str | None = None,
        status: str | None = None,
        phase: int | None = None,
        artifact_type: str | None = None,
        worktree_state: str | None = None,
        pr_state: str | None = None,
        launch_readiness: str | None = None,
        sort_by: str = "last_activity",
        sort_direction: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> PlanningCommandCenterPageDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return PlanningCommandCenterPageDTO(
                status="error",
                project_id=str(project_id_override or ""),
                warnings=["Project scope could not be resolved."],
            )

        project = scope.project
        partial = False
        warnings: list[str] = []

        try:
            feature_rows, features, feature_index = await _load_all_features(ports, project.id)
        except Exception as exc:
            feature_rows, features, feature_index = [], [], {}
            partial = True
            warnings.append(f"Feature rows unavailable: {exc}")

        try:
            doc_rows = await _load_all_doc_rows(ports, project.id)
        except Exception as exc:
            doc_rows = []
            partial = True
            warnings.append(f"Document rows unavailable: {exc}")

        projected: list[Feature] = []
        for feature in features:
            try:
                projected.append(_project_with_planning(feature, doc_rows, feature_index))
            except Exception:
                projected.append(feature)
                partial = True

        emitted_keys = {_feature_key(feature.id) for feature in projected}
        orphan_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in doc_rows:
            doc_type = str(row.get("doc_type") or "").lower()
            if doc_type not in {"prd", "design_spec", "design_doc", "spec", "report"}:
                continue
            feature_slug = str(row.get("feature_slug_canonical") or row.get("feature_slug_hint") or "").strip()
            if not feature_slug:
                path = str(row.get("file_path") or "")
                feature_slug = path.rsplit("/", 1)[-1].removesuffix(".md") if path else ""
            key = _feature_key(feature_slug)
            if key and key not in emitted_keys:
                orphan_groups[key].append(row)
        for key, rows in orphan_groups.items():
            projected.append(_synthetic_feature_from_doc_rows(key, rows))

        worktrees_by_feature = await self._worktrees_by_feature(ports, project.id, warnings)

        items: list[PlanningCommandCenterItemDTO] = []
        for feature in projected:
            docs = _dedupe_documents(
                [
                    *list(getattr(feature, "linkedDocs", []) or []),
                    *[_linked_doc_from_row(row) for row in _load_doc_rows_for_feature(doc_rows, feature.id)],
                ]
            )
            worktree_row = worktrees_by_feature.get(_feature_key(feature.id))
            item = await self._build_item(feature, docs, worktree_row)
            if self._matches_filters(item, q, status, phase, artifact_type, worktree_state, pr_state, launch_readiness):
                items.append(item)

        shaped = self._sort_items(items, sort_by=sort_by, sort_direction=sort_direction)
        safe_page_size = min(200, max(1, int(page_size or 50)))
        safe_page = max(1, int(page or 1))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        page_items = shaped[start:end]

        return PlanningCommandCenterPageDTO(
            status="partial" if partial else "ok",
            project_id=project.id,
            items=page_items,
            total=len(shaped),
            page=safe_page,
            page_size=safe_page_size,
            sort_by=sort_by,
            sort_direction="desc" if str(sort_direction).lower() == "desc" else "asc",
            warnings=warnings,
            data_freshness=derive_data_freshness(
                *[row.get("updated_at") or row.get("updatedAt") for row in feature_rows],
                *[row.get("updated_at") or row.get("updatedAt") for row in doc_rows],
            ),
            source_refs=collect_source_refs(project.id, [item.feature.feature_id for item in page_items]),
        )

    async def get_command_center_item(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        project_id_override: str | None = None,
    ) -> PlanningCommandCenterItemDTO | None:
        page = await self.get_command_center(
            context,
            ports,
            project_id_override=project_id_override,
            q=None,
            page=1,
            page_size=500,
        )
        for item in page.items:
            if _feature_key(item.feature.feature_id) == _feature_key(feature_id):
                return item
        return None

    async def _worktrees_by_feature(
        self,
        ports: CorePorts,
        project_id: str,
        warnings: list[str],
    ) -> dict[str, dict[str, Any]]:
        try:
            rows = await ports.storage.worktree_contexts().list(project_id, limit=500, offset=0)
        except Exception as exc:
            warnings.append(f"Worktree contexts unavailable: {exc}")
            return {}
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = _feature_key(str(row.get("feature_id") or ""))
            if key and key not in grouped:
                grouped[key] = row
        return grouped

    async def _build_item(
        self,
        feature: Feature,
        docs: Sequence[LinkedDocument],
        worktree_row: dict[str, Any] | None,
    ) -> PlanningCommandCenterItemDTO:
        command = self.resolver.resolve(feature, docs)
        phase_summary = _phase_summary(feature)
        worktree = _worktree_dto(worktree_row)
        git_state = await self.git_probe.probe(worktree.path if worktree is not None else "")
        status_detail = getattr(feature, "planningStatus", None)
        raw_status = _raw_status(status_detail) or str(getattr(feature, "status", "") or "")
        effective_status = _effective_status(status_detail) or raw_status
        pull_request = _pr_dto(feature)
        capabilities = _capabilities(command, feature)
        launch_phase = command.phase or phase_summary.current_phase or phase_summary.next_phase
        last_activity = str(getattr(feature, "updatedAt", "") or "")

        return PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(
                feature_id=str(getattr(feature, "id", "") or ""),
                feature_slug=_feature_slug(feature),
                name=str(getattr(feature, "name", "") or getattr(feature, "id", "") or ""),
                category=str(getattr(feature, "category", "") or ""),
                tags=list(getattr(feature, "tags", []) or []),
                priority=str(getattr(feature, "priority", "") or ""),
                summary=str(getattr(feature, "summary", "") or getattr(feature, "description", "") or ""),
            ),
            status=PlanningCommandCenterStatusDTO(
                raw_status=raw_status,
                effective_status=effective_status,
                planning_signal=effective_status,
                mismatch_state=_mismatch_state(status_detail),
                is_mismatch=_is_mismatch(status_detail),
            ),
            tier=_tier_from_feature(feature),
            story_points=_story_points(feature),
            phase=phase_summary,
            artifacts=_artifact_dtos(docs),
            target_artifact=command.target_artifact,
            command=command,
            related_files=_related_files(docs),
            phase_rows=_phase_rows(feature, docs),
            launch_batch=_launch_batch(feature, launch_phase),
            worktree=worktree,
            git_state=git_state,
            pull_request=pull_request,
            blockers=_blockers(feature),
            last_activity={"timestamp": last_activity, "actor": "", "source": "feature"},
            capabilities=capabilities,
        )

    def _matches_filters(
        self,
        item: PlanningCommandCenterItemDTO,
        q: str | None,
        status: str | None,
        phase: int | None,
        artifact_type: str | None,
        worktree_state: str | None,
        pr_state: str | None,
        launch_readiness: str | None,
    ) -> bool:
        query = str(q or "").strip().lower()
        if query:
            haystack = " ".join(
                [
                    item.feature.feature_id,
                    item.feature.name,
                    item.feature.summary,
                    item.command.command if item.command is not None else "",
                    *[artifact.path for artifact in item.artifacts],
                ]
            ).lower()
            if query not in haystack:
                return False
        if status and str(status).lower() not in {item.status.raw_status.lower(), item.status.effective_status.lower()}:
            return False
        if phase is not None and phase not in {item.phase.current_phase, item.phase.next_phase}:
            return False
        if artifact_type and artifact_type.lower() not in {artifact.doc_type.lower() for artifact in item.artifacts}:
            return False
        if worktree_state and (item.worktree is None or item.worktree.status.lower() != worktree_state.lower()):
            return False
        if pr_state and (item.pull_request is None or item.pull_request.state.lower() != pr_state.lower()):
            return False
        if launch_readiness and (item.launch_batch is None or item.launch_batch.readiness.lower() != launch_readiness.lower()):
            return False
        return True

    def _sort_items(
        self,
        items: Sequence[PlanningCommandCenterItemDTO],
        *,
        sort_by: str,
        sort_direction: str,
    ) -> list[PlanningCommandCenterItemDTO]:
        key = str(sort_by or "last_activity").lower()
        reverse = str(sort_direction or "desc").lower() == "desc"

        def sort_key(item: PlanningCommandCenterItemDTO) -> Any:
            if key == "status":
                return item.status.effective_status
            if key == "phase":
                return item.phase.current_phase or item.phase.next_phase or 0
            if key == "story_points":
                return item.story_points.remaining
            if key == "command":
                return item.command.command if item.command is not None else ""
            if key == "name":
                return item.feature.name.lower()
            return str(item.last_activity.get("timestamp") or "")

        return sorted(items, key=sort_key, reverse=reverse)
