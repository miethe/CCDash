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
from backend.services.feature_execution import feature_from_row
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.repo_workspaces.github_client import fetch_pr_status

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import (
    AggregateWorkItemSession,
    PlanningCommandCenterArtifactDTO,
    PlanningCommandCenterBlockerDTO,
    PlanningCommandCenterCapabilitiesDTO,
    PlanningCommandCenterFeatureDTO,
    PlanningCommandCenterGitStateDTO,
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
    SessionLink,
)
from .planning_sessions import _STATUS_STATE_MAP as _SESSION_STATE_MAP
from .planning import (
    _effective_status,
    _feature_key,
    _is_mismatch,
    _linked_doc_from_row,
    _load_all_doc_rows,
    _load_all_features,
    _load_doc_rows_for_feature,
    _load_phase_session_links,
    _mismatch_state,
    _project_with_planning,
    _raw_status,
    _synthetic_feature_from_doc_rows,
)

# ── No-op git probe (parity with MPCC-206) ───────────────────────────────────

class _NullGitProbe(WorktreeGitStateProbe):
    """WorktreeGitStateProbe that skips all filesystem and git I/O.

    Injected into V1 builds (P2-013) so that ``_build_item`` calls inside
    ``_build_items_for_scope`` do not spawn a git subprocess per item.
    Parity with the same sentinel defined in
    ``multi_project_planning_command_center``.

    The returned ``PlanningCommandCenterGitStateDTO`` is intentionally sparse
    (``path_exists=None``) so callers can detect items whose git state was
    not yet probed.
    """

    async def probe(self, worktree_path: str) -> PlanningCommandCenterGitStateDTO:
        return PlanningCommandCenterGitStateDTO(
            path_exists=None,
            probed_at="",
            warnings=["git probe deferred — NullGitProbe"],
        )


# ── Cache param extractor for V1 command center ───────────────────────────────

def _pcc_params(
    self: Any,
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
    hide_done: bool = False,
    **_: Any,
) -> dict[str, Any]:
    """Extract cache-key parameters for the V1 single-project command-center query.

    ``project_id_override`` is returned as ``project_id`` so the
    ``memoized_query`` decorator pops it into the cache-key scope slot
    rather than hashing it into the param dict twice.
    """
    return {
        "project_id": project_id_override,
        "q": q or "",
        "status": status or "",
        "phase": phase,
        "artifact_type": artifact_type or "",
        "worktree_state": worktree_state or "",
        "pr_state": pr_state or "",
        "launch_readiness": launch_readiness or "",
        "sort_by": sort_by,
        "sort_direction": sort_direction,
        "page": page,
        "page_size": page_size,
        "hide_done": hide_done,
    }


_TERMINAL_STATUSES = {"done", "completed", "closed", "deferred", "superseded"}
_ACTIVE_STATUSES = {"active", "in-progress", "in_progress", "review"}
_REVIEW_STATUSES = {"review", "review-ready", "review_ready"}

# DB statuses that map to board state "running" — derived from _SESSION_STATE_MAP
# (planning_sessions._STATUS_STATE_MAP) so there is one canonical liveness heuristic.
_RUNNING_DB_STATUSES: frozenset[str] = frozenset(
    s for s, state in _SESSION_STATE_MAP.items() if state == "running"
)


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


def _phase_rows(
    feature: Feature,
    docs: Sequence[LinkedDocument],
    phase_session_map: dict[int, list[SessionLink]] | None = None,
) -> list[PlanningCommandCenterPhaseRowDTO]:
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
        linked = (phase_session_map or {}).get(num) if num is not None else None
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
                linked_sessions=linked or [],
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


_github_settings_store = GitHubSettingsStore()


async def _pr_dto(feature: Feature) -> PlanningCommandCenterPullRequestDTO | None:
    """Build a pull-request DTO, optionally enriched with live GitHub status.

    Capability-gated: the GitHub API call is skipped when no token is
    configured, falling back to ``state="linked"`` (same as before).

    Results are cached in-process by ``fetch_pr_status`` for ~60 s.
    """
    refs = list(getattr(feature, "prRefs", []) or [])
    if not refs:
        return None
    first = str(refs[0] or "")
    number_match = re.search(r"/pull/(\d+)|#(\d+)", first)
    number = None
    if number_match:
        number = _safe_int(number_match.group(1) or number_match.group(2), 0) or None
    is_github = "github.com" in first.lower()
    provider = "github" if is_github else ""

    state = "linked"
    review_status: str | None = None

    # Enrich with live GitHub data when a token is available
    if is_github and number:
        try:
            settings = _github_settings_store.load()
            token = str(settings.token or "").strip()
        except Exception:
            token = ""

        if token:
            # Extract repo slug from the PR URL
            slug_match = re.search(r"github\.com/([^/]+/[^/]+)/pull/", first, re.IGNORECASE)
            repo_slug = slug_match.group(1) if slug_match else ""
            if repo_slug:
                live = await fetch_pr_status(repo_slug, number, token=token)
                if live:
                    state = str(live.get("state") or state)
                    review_status = live.get("review_status") or None

    return PlanningCommandCenterPullRequestDTO(
        provider=provider,
        number=number,
        url=first,
        state=state,
        review_status=review_status or "",
    )


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


async def _load_running_sessions_by_feature(
    ports: CorePorts,
    project_id: str,
    warnings: list[str],
) -> dict[str, list[AggregateWorkItemSession]]:
    """Load running-state sessions for *project_id* and group by feature_id.

    Uses the same state classification as ``planning_sessions._STATUS_STATE_MAP``
    (R4 hard constraint): only sessions whose DB ``status`` maps to board state
    ``"running"`` are included.  The mapping is pulled from
    ``_RUNNING_DB_STATUSES`` which is derived directly from ``_SESSION_STATE_MAP``
    at import time so there is one canonical liveness heuristic.

    Returns a dict keyed by normalised feature_id.  Sessions without a
    ``feature_id`` are ignored.  Returns an empty dict on any storage failure
    (non-fatal; the caller should not surface this as an error to the user).
    """
    result: dict[str, list[AggregateWorkItemSession]] = {}
    try:
        sessions_repo = ports.storage.sessions()
        # Query once per running DB status and de-duplicate by session_id.
        seen: set[str] = set()
        all_rows: list[dict[str, Any]] = []
        for db_status in _RUNNING_DB_STATUSES:
            try:
                rows = await sessions_repo.list_paginated(
                    offset=0,
                    limit=200,
                    project_id=project_id,
                    filters={"status": db_status, "include_subagents": True},
                )
                for row in rows:
                    sid = str(row.get("id") or "").strip()
                    if sid and sid not in seen:
                        seen.add(sid)
                        all_rows.append(row)
            except Exception:
                pass  # partial: skip this status bucket

        for row in all_rows:
            feature_id = str(row.get("feature_id") or "").strip()
            if not feature_id:
                continue
            session_id = str(row.get("id") or "").strip()
            if not session_id:
                continue
            agent_session = AggregateWorkItemSession(
                session_id=session_id,
                state="running",
                model=str(row.get("model") or "") or None,
                started_at=str(row.get("started_at") or "") or None,
                agent_name=str(row.get("agent_id") or "") or None,
            )
            result.setdefault(feature_id, []).append(agent_session)
    except Exception as exc:
        warnings.append(f"Running sessions unavailable: {exc}")
    return result


class PlanningCommandCenterQueryService:
    """Compose planning, execution, worktree, and resolver context in one read."""

    def __init__(
        self,
        *,
        resolver: PlanningCommandResolver | None = None,
        git_probe: WorktreeGitStateProbe | None = None,
    ) -> None:
        self.resolver = resolver or PlanningCommandResolver()
        # P2-013: default to NullGitProbe so V1 item builds do not spawn a
        # git subprocess per item.  Callers that need real git state (e.g. the
        # router after pagination) should pass an explicit WorktreeGitStateProbe.
        self.git_probe = git_probe if git_probe is not None else _NullGitProbe()

    # ------------------------------------------------------------------
    # Public V1 endpoint — behavior-compatible wrapper
    # ------------------------------------------------------------------

    @memoized_query("pcc_command_center", param_extractor=_pcc_params, ttl=30)
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
        hide_done: bool = False,
    ) -> PlanningCommandCenterPageDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return PlanningCommandCenterPageDTO(
                status="error",
                project_id=str(project_id_override or ""),
                warnings=["Project scope could not be resolved."],
            )

        feature_rows, features, feature_index, doc_rows, partial, warnings = await self._load_project_data(
            ports, scope.project.id
        )

        items, _, had_build_errors = await self._build_items_for_scope(
            ports=ports,
            project_id=scope.project.id,
            features=features,
            feature_index=feature_index,
            doc_rows=doc_rows,
            warnings=warnings,
            q=q,
            status=status,
            phase=phase,
            artifact_type=artifact_type,
            worktree_state=worktree_state,
            pr_state=pr_state,
            launch_readiness=launch_readiness,
            hide_done=hide_done,
        )

        partial = partial or had_build_errors
        shaped = self._sort_items(items, sort_by=sort_by, sort_direction=sort_direction)
        safe_page_size = min(200, max(1, int(page_size or 50)))
        safe_page = max(1, int(page or 1))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        page_items = shaped[start:end]

        return PlanningCommandCenterPageDTO(
            status="partial" if partial else "ok",
            project_id=scope.project.id,
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
            source_refs=collect_source_refs(scope.project.id, [item.feature.feature_id for item in page_items]),
        )

    # ------------------------------------------------------------------
    # Reusable cross-project helper — no HTTP, accepts explicit scope
    # ------------------------------------------------------------------

    async def _load_project_data(
        self,
        ports: CorePorts,
        project_id: str,
    ) -> tuple[
        list[dict[str, Any]],   # feature_rows
        list[Feature],          # features
        dict[str, Feature],     # feature_index  (key → Feature)
        list[dict[str, Any]],   # doc_rows
        bool,                   # partial
        list[str],              # warnings
    ]:
        """Load raw feature and document rows for an explicit project scope.

        Callers supply *project_id* directly; no active-project resolution
        is performed here.  This is the entry point for cross-project
        iteration (MPCC-202 and later).

        Returns the ``feature_index`` alongside raw rows so
        ``_build_items_for_scope`` does not need a second storage round-trip.

        NOTE (MPCC-206): ``_build_item`` still calls ``git_probe.probe()``
        which may trigger filesystem/git I/O per item.  That seam is
        intentionally left here for MPCC-206 to address; callers that want
        to skip git probes should override ``_build_item`` or pass a no-op
        ``WorktreeGitStateProbe``.
        """
        partial = False
        warnings: list[str] = []
        feature_index: dict[str, Feature] = {}

        try:
            feature_rows, features, feature_index = await _load_all_features(ports, project_id)
        except Exception as exc:
            feature_rows, features = [], []
            partial = True
            warnings.append(f"Feature rows unavailable: {exc}")

        try:
            doc_rows = await _load_all_doc_rows(ports, project_id)
        except Exception as exc:
            doc_rows = []
            partial = True
            warnings.append(f"Document rows unavailable: {exc}")

        return feature_rows, features, feature_index, doc_rows, partial, warnings

    async def _build_items_for_scope(
        self,
        *,
        ports: CorePorts,
        project_id: str,
        features: list[Feature],
        feature_index: dict[str, Feature],
        doc_rows: list[dict[str, Any]],
        warnings: list[str],
        q: str | None = None,
        status: str | None = None,
        phase: int | None = None,
        artifact_type: str | None = None,
        worktree_state: str | None = None,
        pr_state: str | None = None,
        launch_readiness: str | None = None,
        hide_done: bool = False,
    ) -> tuple[list[PlanningCommandCenterItemDTO], list[PlanningCommandCenterItemDTO], bool]:
        """Build and filter work-item DTOs for an *explicit* project scope.

        Accepts pre-loaded ``feature_rows``, ``features``, ``feature_index``,
        and ``doc_rows`` — no additional storage round-trips are made here.
        A future cross-project service can iterate projects, call
        ``_load_project_data`` per project, then pass the results here
        without routing through HTTP or mutating the active project.

        The ``feature_index`` returned by ``_load_project_data`` must be
        supplied so ``_project_with_planning`` can resolve cross-feature
        references without a second DB call.

        Returns ``(filtered_items, all_items, had_errors)`` where
        ``had_errors`` is ``True`` if any per-feature projection failed (so
        the caller can propagate ``partial`` status).  Callers that need
        the unfiltered set (e.g. cross-project aggregation) can use
        ``all_items`` directly.

        NOTE (MPCC-206): git probes inside ``_build_item`` run per item.
        The interface is kept clean here so MPCC-206 can inject a deferred
        or no-op probe without touching this method.
        """
        had_errors = False

        # Project features with their planning overlay; ``feature_index`` was
        # built during data-load so no extra storage call is needed here.
        projected: list[Feature] = []
        for feature in features:
            try:
                projected.append(_project_with_planning(feature, doc_rows, feature_index))
            except Exception:
                projected.append(feature)
                had_errors = True

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

        worktrees_by_feature = await self._worktrees_by_feature(ports, project_id, warnings)
        running_sessions_by_feature = await _load_running_sessions_by_feature(
            ports, project_id, warnings
        )

        all_items: list[PlanningCommandCenterItemDTO] = []
        filtered_items: list[PlanningCommandCenterItemDTO] = []
        for feature in projected:
            docs = _dedupe_documents(
                [
                    *list(getattr(feature, "linkedDocs", []) or []),
                    *[_linked_doc_from_row(row) for row in _load_doc_rows_for_feature(doc_rows, feature.id)],
                ]
            )
            worktree_row = worktrees_by_feature.get(_feature_key(feature.id))
            active_sessions = running_sessions_by_feature.get(
                str(getattr(feature, "id", "") or "").strip(), []
            )
            item = await self._build_item(
                feature,
                docs,
                worktree_row,
                active_sessions=active_sessions,
                ports=ports,
                project_id=project_id,
            )
            all_items.append(item)
            if self._matches_filters(item, q, status, phase, artifact_type, worktree_state, pr_state, launch_readiness, hide_done=hide_done):
                filtered_items.append(item)

        return filtered_items, all_items, had_errors

    async def get_command_center_item(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        project_id_override: str | None = None,
    ) -> PlanningCommandCenterItemDTO | None:
        """Return the command-center item for a single feature.

        P2-011: loads ONLY the target feature via ``get_by_id`` instead of
        issuing a 500-item full-page scan.  The document list is bounded to
        the resolved project scope.  If the feature is not found in the repo
        the method returns ``None``.

        NOTE (followup): doc loading still calls ``_load_all_doc_rows`` for
        the project because there is no per-feature document getter on the
        repo today.  A targeted ``documents.get_by_feature_slug`` would
        remove this last full-scan; tracked as a future optimisation.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return None

        # ── Single-feature fast path (P2-011) ─────────────────────────────
        try:
            feature_row = await ports.storage.features().get_by_id(feature_id)
        except Exception:
            feature_row = None
        if feature_row is None:
            return None

        feature = feature_from_row(feature_row)

        try:
            doc_rows = await _load_all_doc_rows(ports, scope.project.id)
        except Exception:
            doc_rows = []

        feature_index: dict[str, Feature] = {_feature_key(feature.id): feature}
        try:
            feature = _project_with_planning(feature, doc_rows, feature_index)
        except Exception:
            pass

        docs = _dedupe_documents(
            [
                *list(getattr(feature, "linkedDocs", []) or []),
                *[_linked_doc_from_row(row) for row in _load_doc_rows_for_feature(doc_rows, feature.id)],
            ]
        )

        warnings: list[str] = []
        worktrees_by_feature = await self._worktrees_by_feature(ports, scope.project.id, warnings)
        worktree_row = worktrees_by_feature.get(_feature_key(feature.id))
        return await self._build_item(
            feature,
            docs,
            worktree_row,
            ports=ports,
            project_id=scope.project.id,
        )

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
        *,
        active_sessions: list[AggregateWorkItemSession] | None = None,
        ports: CorePorts | None = None,
        project_id: str | None = None,
    ) -> PlanningCommandCenterItemDTO:
        command = self.resolver.resolve(feature, docs)
        phase_summary = _phase_summary(feature)
        worktree = _worktree_dto(worktree_row)
        git_state = await self.git_probe.probe(worktree.path if worktree is not None else "")
        status_detail = getattr(feature, "planningStatus", None)
        raw_status = _raw_status(status_detail) or str(getattr(feature, "status", "") or "")
        effective_status = _effective_status(status_detail) or raw_status
        pull_request = await _pr_dto(feature)
        capabilities = _capabilities(command, feature)
        launch_phase = command.phase or phase_summary.current_phase or phase_summary.next_phase
        last_activity = str(getattr(feature, "updatedAt", "") or "")

        # Populate the inverse phase→sessions map when a storage context is available.
        phase_session_map: dict[int, list[SessionLink]] | None = None
        feature_id = str(getattr(feature, "id", "") or "")
        if ports is not None and project_id and feature_id and feature.phases:
            try:
                phase_session_map = await _load_phase_session_links(
                    ports.storage.db,
                    project_id,
                    feature_id,
                    feature.phases,
                )
            except Exception:
                pass  # non-fatal; phase_session_map stays None

        commit_refs = [str(v) for v in (getattr(feature, "commitRefs", None) or []) if str(v).strip()]
        pr_refs = [str(v) for v in (getattr(feature, "prRefs", None) or []) if str(v).strip()]

        return PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(
                feature_id=feature_id,
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
            phase_rows=_phase_rows(feature, docs, phase_session_map),
            launch_batch=_launch_batch(feature, launch_phase),
            worktree=worktree,
            git_state=git_state,
            pull_request=pull_request,
            blockers=_blockers(feature),
            last_activity={"timestamp": last_activity, "actor": "", "source": "feature"},
            capabilities=capabilities,
            active_sessions=active_sessions if active_sessions is not None else [],
            commit_refs=commit_refs,
            pr_refs=pr_refs,
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
        *,
        hide_done: bool = False,
    ) -> bool:
        if hide_done:
            if (
                item.status.raw_status.lower() in _TERMINAL_STATUSES
                or item.status.effective_status.lower() in _TERMINAL_STATUSES
            ):
                return False
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
            # last_activity (catch-all): items with a timestamp sort before
            # items without one, regardless of direction.
            # Under desc (reverse=True):  (1, ts) > (0, "")  → timestamped first ✓
            # Under asc  (reverse=False): we negate has_ts so (0, ts) < (1, "") and
            #   timestamped items still precede no-timestamp items after sorting.
            ts = str(item.last_activity.get("timestamp") or "").strip()
            if reverse:
                # desc: higher has_ts floats to top
                return (1 if ts else 0, ts)
            else:
                # asc: lower key floats to top; negate has_ts so no-ts (key 1) sinks
                return (0 if ts else 1, ts)

        return sorted(items, key=sort_key, reverse=reverse)
