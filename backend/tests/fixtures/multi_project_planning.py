"""Shared fixture helpers for Multi-Project Planning Command Center (MPCC) tests.

Exposes builder functions and pre-assembled constant fixtures that cover the
full aggregate DTO contract introduced by MPCC-101:

    ProjectDisplayMetadata, ProjectWorkItemCounts, ProjectSummary,
    ProjectIdentityFields, AggregateWorkItem, AggregateSessionWorkerSummary,
    AggregateSessionCard, AggregatePagination, ProjectWarning,
    MultiProjectCommandCenterResponse, AggregateBoardGroup,
    MultiProjectSessionBoardResponse.

The fixture data is VALUE-CONSISTENT with the TypeScript counterpart at
``services/__tests__/fixtures/multiProjectPlanning.ts`` — same project IDs,
names, counts, and session IDs — so cross-layer contract tests can compare
both sides of the wire boundary.

Scenarios covered
-----------------
* 3 healthy projects with distinct ``display_metadata`` (color / group).
* 1 stale project (``is_stale=True``, large ``freshness_seconds``).
* 1 failed project (``error`` populated; appears in both ``project_summaries``
  and a ``ProjectWarning``).
* Active sessions across projects including a root→worker lineage (an
  ``AggregateSessionCard`` with nested ``workers``).
* Work items (``AggregateWorkItem``) with blocked / review / stale variety.
* Fully assembled ``MultiProjectCommandCenterResponse`` and
  ``MultiProjectSessionBoardResponse`` with pagination + warnings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.models import (
    AggregateBoardGroup,
    AggregatePagination,
    AggregateSessionCard,
    AggregateSessionWorkerSummary,
    AggregateWorkItem,
    MultiProjectCommandCenterResponse,
    MultiProjectSessionBoardResponse,
    ProjectDisplayMetadata,
    ProjectIdentityFields,
    ProjectSummary,
    ProjectWarning,
    ProjectWorkItemCounts,
)

# ---------------------------------------------------------------------------
# Canonical project IDs / names (mirrored in the TS fixture file)
# ---------------------------------------------------------------------------

PROJ_ALPHA_ID = "proj-alpha"
PROJ_ALPHA_NAME = "Alpha Platform"

PROJ_BETA_ID = "proj-beta"
PROJ_BETA_NAME = "Beta Mobile"

PROJ_GAMMA_ID = "proj-gamma"
PROJ_GAMMA_NAME = "Gamma Infra"

PROJ_STALE_ID = "proj-stale"
PROJ_STALE_NAME = "Stale Repo"

PROJ_FAILED_ID = "proj-failed"
PROJ_FAILED_NAME = "Failed Repo"

# Canonical session IDs (same values used in TS fixtures)
SESSION_ROOT_ID = "sess-root-001"
SESSION_WORKER_A_ID = "sess-worker-002"
SESSION_WORKER_B_ID = "sess-worker-003"
SESSION_BETA_ID = "sess-beta-001"

# ---------------------------------------------------------------------------
# Display metadata builders
# ---------------------------------------------------------------------------


def make_display_metadata(
    *,
    color: str | None = None,
    group: str | None = None,
    sort_order: int | None = None,
    label_override: str | None = None,
) -> ProjectDisplayMetadata:
    """Return a ``ProjectDisplayMetadata`` with the given optional fields."""
    return ProjectDisplayMetadata(
        color=color,
        group=group,
        sort_order=sort_order,
        label_override=label_override,
    )


# Pre-built metadata constants
META_ALPHA = make_display_metadata(color="#6366f1", group="core-platform", sort_order=1)
META_BETA = make_display_metadata(color="#22c55e", group="mobile", sort_order=2)
META_GAMMA = make_display_metadata(color="#f59e0b", group="infra", sort_order=3)
META_STALE = make_display_metadata(color="#94a3b8", group="default", sort_order=4)
META_FAILED = make_display_metadata(color="#ef4444", group="default", sort_order=5)

# ---------------------------------------------------------------------------
# ProjectSummary builders
# ---------------------------------------------------------------------------


def make_project_summary(
    *,
    project_id: str,
    name: str,
    display_metadata: ProjectDisplayMetadata | None = None,
    counts: ProjectWorkItemCounts | None = None,
    is_stale: bool | None = False,
    error: str | None = None,
    last_updated: str | None = "2026-05-29T08:00:00+00:00",
    freshness_seconds: int | None = 120,
) -> ProjectSummary:
    """Return a fully populated ``ProjectSummary``."""
    return ProjectSummary(
        project_id=project_id,
        name=name,
        display_metadata=display_metadata or ProjectDisplayMetadata(),
        counts=counts or ProjectWorkItemCounts(),
        is_stale=is_stale,
        error=error,
        last_updated=last_updated,
        freshness_seconds=freshness_seconds,
    )


# ── 3 healthy projects ───────────────────────────────────────────────────────

SUMMARY_ALPHA = make_project_summary(
    project_id=PROJ_ALPHA_ID,
    name=PROJ_ALPHA_NAME,
    display_metadata=META_ALPHA,
    counts=ProjectWorkItemCounts(
        work_items=8,
        blocked=1,
        review=2,
        stale=0,
        active_sessions=2,
        errors=0,
    ),
    is_stale=False,
    freshness_seconds=60,
)

SUMMARY_BETA = make_project_summary(
    project_id=PROJ_BETA_ID,
    name=PROJ_BETA_NAME,
    display_metadata=META_BETA,
    counts=ProjectWorkItemCounts(
        work_items=5,
        blocked=0,
        review=1,
        stale=1,
        active_sessions=1,
        errors=0,
    ),
    is_stale=False,
    freshness_seconds=90,
)

SUMMARY_GAMMA = make_project_summary(
    project_id=PROJ_GAMMA_ID,
    name=PROJ_GAMMA_NAME,
    display_metadata=META_GAMMA,
    counts=ProjectWorkItemCounts(
        work_items=3,
        blocked=0,
        review=0,
        stale=0,
        active_sessions=0,
        errors=0,
    ),
    is_stale=False,
    freshness_seconds=200,
)

# ── Stale project ────────────────────────────────────────────────────────────

SUMMARY_STALE = make_project_summary(
    project_id=PROJ_STALE_ID,
    name=PROJ_STALE_NAME,
    display_metadata=META_STALE,
    counts=ProjectWorkItemCounts(
        work_items=2,
        blocked=0,
        review=0,
        stale=2,
        active_sessions=0,
        errors=0,
    ),
    is_stale=True,
    freshness_seconds=7200,  # 2 hours — clearly stale
    last_updated="2026-05-29T06:00:00+00:00",
)

# ── Failed project ───────────────────────────────────────────────────────────

SUMMARY_FAILED = make_project_summary(
    project_id=PROJ_FAILED_ID,
    name=PROJ_FAILED_NAME,
    display_metadata=META_FAILED,
    counts=ProjectWorkItemCounts(),  # partial / empty counts
    is_stale=None,
    error="aggregate query timed out after 30s",
    freshness_seconds=None,
    last_updated=None,
)

# All five summaries in declaration order
ALL_PROJECT_SUMMARIES: list[ProjectSummary] = [
    SUMMARY_ALPHA,
    SUMMARY_BETA,
    SUMMARY_GAMMA,
    SUMMARY_STALE,
    SUMMARY_FAILED,
]

# ---------------------------------------------------------------------------
# ProjectIdentityFields helpers
# ---------------------------------------------------------------------------


def make_identity(
    *,
    project_id: str,
    project_name: str,
    project_color: str | None = None,
    project_group: str | None = None,
) -> ProjectIdentityFields:
    return ProjectIdentityFields(
        project_id=project_id,
        project_name=project_name,
        project_color=project_color,
        project_group=project_group,
    )


IDENTITY_ALPHA = make_identity(
    project_id=PROJ_ALPHA_ID,
    project_name=PROJ_ALPHA_NAME,
    project_color="#6366f1",
    project_group="core-platform",
)

IDENTITY_BETA = make_identity(
    project_id=PROJ_BETA_ID,
    project_name=PROJ_BETA_NAME,
    project_color="#22c55e",
    project_group="mobile",
)

IDENTITY_GAMMA = make_identity(
    project_id=PROJ_GAMMA_ID,
    project_name=PROJ_GAMMA_NAME,
    project_color="#f59e0b",
    project_group="infra",
)

IDENTITY_FAILED = make_identity(
    project_id=PROJ_FAILED_ID,
    project_name=PROJ_FAILED_NAME,
    project_color="#ef4444",
    project_group="default",
)

# ---------------------------------------------------------------------------
# V1 PlanningCommandCenterItem payload builders
# ---------------------------------------------------------------------------
# item/card fields are typed as dict[str, Any] in the aggregate models to
# avoid circular imports.  The helpers below produce dicts matching the V1
# wire shape (snake_case) so that tests can round-trip them.


def make_v1_item_dict(
    *,
    feature_id: str,
    feature_slug: str,
    name: str,
    raw_status: str = "in-progress",
    effective_status: str = "in-progress",
    planning_signal: str = "active",
    is_mismatch: bool = False,
    total_phases: int = 4,
    completed_phases: int = 1,
    current_phase: int | None = 2,
    story_points_total: int = 8,
    story_points_remaining: int = 5,
    story_points_completed: int = 3,
    blockers: list[dict] | None = None,
    category: str = "enhancement",
    priority: str = "high",
    summary: str = "",
) -> dict[str, Any]:
    """Return a minimal V1 PlanningCommandCenterItemDTO dict."""
    return {
        "feature": {
            "feature_id": feature_id,
            "feature_slug": feature_slug,
            "name": name,
            "category": category,
            "tags": [],
            "priority": priority,
            "summary": summary or name,
        },
        "status": {
            "raw_status": raw_status,
            "effective_status": effective_status,
            "planning_signal": planning_signal,
            "mismatch_state": "none",
            "is_mismatch": is_mismatch,
        },
        "story_points": {
            "total": story_points_total,
            "remaining": story_points_remaining,
            "completed": story_points_completed,
        },
        "phase": {
            "current_phase": current_phase,
            "next_phase": current_phase + 1 if current_phase is not None else None,
            "total_phases": total_phases,
            "completed_phases": completed_phases,
        },
        "artifacts": [],
        "target_artifact": None,
        "command": None,
        "related_files": [],
        "phase_rows": [],
        "launch_batch": None,
        "worktree": None,
        "git_state": None,
        "pull_request": None,
        "blockers": blockers or [],
        "last_activity": {},
        "capabilities": {
            "copy_command": True,
            "launch": True,
            "review": False,
            "merge": False,
            "cleanup": False,
            "open_pr": False,
            "edit_command": True,
        },
    }


# ── Work items covering blocked / review / stale variety ─────────────────────

ITEM_ALPHA_BLOCKED = AggregateWorkItem(
    project=IDENTITY_ALPHA,
    item=make_v1_item_dict(
        feature_id="feat-alpha-001",
        feature_slug="auth-hardening",
        name="Auth Hardening",
        effective_status="blocked",
        planning_signal="blocked",
        blockers=[{"label": "Awaiting security review", "reason": "external", "severity": "high"}],
    ),
)

ITEM_ALPHA_REVIEW = AggregateWorkItem(
    project=IDENTITY_ALPHA,
    item=make_v1_item_dict(
        feature_id="feat-alpha-002",
        feature_slug="api-rate-limiting",
        name="API Rate Limiting",
        raw_status="review",
        effective_status="review",
        planning_signal="review",
    ),
)

ITEM_BETA_STALE = AggregateWorkItem(
    project=IDENTITY_BETA,
    item=make_v1_item_dict(
        feature_id="feat-beta-001",
        feature_slug="push-notifications",
        name="Push Notifications",
        raw_status="completed",
        effective_status="stale",
        planning_signal="stale",
        story_points_remaining=0,
    ),
)

ITEM_BETA_INPROGRESS = AggregateWorkItem(
    project=IDENTITY_BETA,
    item=make_v1_item_dict(
        feature_id="feat-beta-002",
        feature_slug="offline-mode",
        name="Offline Mode",
        effective_status="in-progress",
    ),
)

ITEM_GAMMA_INPROGRESS = AggregateWorkItem(
    project=IDENTITY_GAMMA,
    item=make_v1_item_dict(
        feature_id="feat-gamma-001",
        feature_slug="k8s-autoscaling",
        name="K8s Autoscaling",
        priority="medium",
        effective_status="in-progress",
    ),
)

ALL_WORK_ITEMS: list[AggregateWorkItem] = [
    ITEM_ALPHA_BLOCKED,
    ITEM_ALPHA_REVIEW,
    ITEM_BETA_STALE,
    ITEM_BETA_INPROGRESS,
    ITEM_GAMMA_INPROGRESS,
]

# ---------------------------------------------------------------------------
# V1 PlanningAgentSessionCard payload builder
# ---------------------------------------------------------------------------


def make_v1_card_dict(
    *,
    session_id: str,
    state: str = "running",
    model: str = "claude-sonnet-4-6",
    agent_name: str = "dev-agent",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    started_at: str = "2026-05-29T09:00:00+00:00",
    last_activity_at: str = "2026-05-29T09:30:00+00:00",
    duration_seconds: float = 1800.0,
    feature_id: str | None = None,
    feature_name: str | None = None,
) -> dict[str, Any]:
    """Return a minimal V1 PlanningAgentSessionCardDTO dict."""
    correlation = None
    if feature_id:
        correlation = {
            "feature_id": feature_id,
            "feature_name": feature_name or feature_id,
            "phase_number": 2,
            "confidence": 0.9,
            "evidence": [{"evidence_type": "explicit_link", "detail": "linked via entity_links"}],
        }
    return {
        "session_id": session_id,
        "agent_name": agent_name,
        "agent_type": "claude_code",
        "state": state,
        "model": model,
        "correlation": correlation,
        "transcript_href": f"/sessions/{session_id}",
        "planning_href": f"/planning/{feature_id}" if feature_id else None,
        "phase_href": None,
        "parent_session_id": parent_session_id,
        "root_session_id": root_session_id or session_id,
        "started_at": started_at,
        "last_activity_at": last_activity_at,
        "duration_seconds": duration_seconds,
        "token_summary": {
            "total_tokens": 45000,
            "input_tokens": 20000,
            "output_tokens": 10000,
            "cache_read_tokens": 15000,
            "cache_write_tokens": 0,
        },
        "relationships": [],
        "activity_markers": [],
    }


# ---------------------------------------------------------------------------
# AggregateSessionWorkerSummary constants
# ---------------------------------------------------------------------------

WORKER_A = AggregateSessionWorkerSummary(
    session_id=SESSION_WORKER_A_ID,
    agent_name="python-backend-engineer",
    state="running",
    model="claude-sonnet-4-6",
    started_at="2026-05-29T09:05:00+00:00",
    last_activity_at="2026-05-29T09:35:00+00:00",
    duration_seconds=1800.0,
)

WORKER_B = AggregateSessionWorkerSummary(
    session_id=SESSION_WORKER_B_ID,
    agent_name="frontend-engineer",
    state="completed",
    model="claude-sonnet-4-6",
    started_at="2026-05-29T09:05:00+00:00",
    last_activity_at="2026-05-29T09:25:00+00:00",
    duration_seconds=1200.0,
)

# ---------------------------------------------------------------------------
# AggregateSessionCard constants
# ---------------------------------------------------------------------------

# Root session (alpha project) — has two nested workers
CARD_ALPHA_ROOT = AggregateSessionCard(
    project=IDENTITY_ALPHA,
    card=make_v1_card_dict(
        session_id=SESSION_ROOT_ID,
        state="running",
        root_session_id=SESSION_ROOT_ID,
        feature_id="feat-alpha-001",
        feature_name="Auth Hardening",
    ),
    workers=[WORKER_A, WORKER_B],
)

# Beta project — standalone session, no children
CARD_BETA = AggregateSessionCard(
    project=IDENTITY_BETA,
    card=make_v1_card_dict(
        session_id=SESSION_BETA_ID,
        state="thinking",
        feature_id="feat-beta-002",
        feature_name="Offline Mode",
    ),
    workers=[],
)

ALL_SESSION_CARDS: list[AggregateSessionCard] = [CARD_ALPHA_ROOT, CARD_BETA]

# ---------------------------------------------------------------------------
# Pagination / warnings
# ---------------------------------------------------------------------------

PAGINATION_FULL = AggregatePagination(page=1, page_size=50, total=5, has_more=False)
PAGINATION_PAGE2 = AggregatePagination(page=2, page_size=3, total=5, has_more=False)

WARNING_STALE = ProjectWarning(
    project_id=PROJ_STALE_ID,
    message="Project data is stale — last sync was 2 hours ago.",
    severity="low",
    code="sync_stale",
)

WARNING_FAILED = ProjectWarning(
    project_id=PROJ_FAILED_ID,
    message="Aggregate query timed out after 30s — displaying partial data.",
    severity="high",
    code="feature_load_failed",
)

ALL_WARNINGS: list[ProjectWarning] = [WARNING_STALE, WARNING_FAILED]

# ---------------------------------------------------------------------------
# Assembled top-level responses
# ---------------------------------------------------------------------------


def make_command_center_response(
    *,
    status: str = "partial",
    items: list[AggregateWorkItem] | None = None,
    project_summaries: list[ProjectSummary] | None = None,
    pagination: AggregatePagination | None = None,
    warnings: list[ProjectWarning] | None = None,
    generated_at: datetime | None = None,
    data_freshness: str | None = "2026-05-29T08:00:00+00:00",
) -> MultiProjectCommandCenterResponse:
    """Build a ``MultiProjectCommandCenterResponse`` from the canonical fixtures."""
    return MultiProjectCommandCenterResponse(
        status=status,  # type: ignore[arg-type]
        items=items if items is not None else ALL_WORK_ITEMS,
        project_summaries=project_summaries if project_summaries is not None else ALL_PROJECT_SUMMARIES,
        pagination=pagination or PAGINATION_FULL,
        warnings=warnings if warnings is not None else ALL_WARNINGS,
        generated_at=generated_at or datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc),
        data_freshness=data_freshness,
    )


# Fully assembled constant — the canonical MPCC fixture
COMMAND_CENTER_RESPONSE = make_command_center_response()


def make_board_group(
    *,
    group_key: str,
    group_label: str,
    group_type: str = "state",
    cards: list[AggregateSessionCard] | None = None,
) -> AggregateBoardGroup:
    """Build an ``AggregateBoardGroup`` with auto-populated ``card_count``."""
    card_list = cards or []
    return AggregateBoardGroup(
        group_key=group_key,
        group_label=group_label,
        group_type=group_type,
        cards=card_list,
        card_count=len(card_list),
    )


BOARD_GROUP_RUNNING = make_board_group(
    group_key="running",
    group_label="Running",
    cards=[CARD_ALPHA_ROOT],
)

BOARD_GROUP_THINKING = make_board_group(
    group_key="thinking",
    group_label="Thinking",
    cards=[CARD_BETA],
)

ALL_BOARD_GROUPS: list[AggregateBoardGroup] = [BOARD_GROUP_RUNNING, BOARD_GROUP_THINKING]


def make_session_board_response(
    *,
    status: str = "partial",
    grouping: str = "state",
    groups: list[AggregateBoardGroup] | None = None,
    project_summaries: list[ProjectSummary] | None = None,
    pagination: AggregatePagination | None = None,
    warnings: list[ProjectWarning] | None = None,
    total_card_count: int = 2,
    active_count: int = 2,
    completed_count: int = 0,
) -> MultiProjectSessionBoardResponse:
    """Build a ``MultiProjectSessionBoardResponse`` from the canonical fixtures."""
    return MultiProjectSessionBoardResponse(
        status=status,  # type: ignore[arg-type]
        grouping=grouping,
        groups=groups if groups is not None else ALL_BOARD_GROUPS,
        project_summaries=project_summaries if project_summaries is not None else ALL_PROJECT_SUMMARIES,
        pagination=pagination or AggregatePagination(page=1, page_size=50, total=2, has_more=False),
        warnings=warnings if warnings is not None else ALL_WARNINGS,
        total_card_count=total_card_count,
        active_count=active_count,
        completed_count=completed_count,
    )


# Fully assembled constant — the canonical session board fixture
SESSION_BOARD_RESPONSE = make_session_board_response()
