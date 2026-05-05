#!/usr/bin/env python3
"""Audit host/container source alias duplicates for live-ingest session state.

Usage:
  python backend/scripts/source_alias_duplicate_audit.py --project default-skillmeat
  python backend/scripts/source_alias_duplicate_audit.py --project default-skillmeat --env-file deploy/runtime/.env
  python backend/scripts/source_alias_duplicate_audit.py --project default-skillmeat --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.source_identity import (
    SOURCE_KEY_SCHEME,
    SOURCE_KEY_VERSION,
    ProjectId,
    SourceArtifactKind,
    SourceIdentityInput,
    SourceIdentityPolicy,
    SourceRootAlias,
    resolve_source_identity,
    source_identity_policy_from_env,
)


CANONICAL_SOURCE_PREFIX = f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/"


@dataclass(frozen=True, slots=True)
class AuditQuerySpec:
    table_name: str
    sql: str


@dataclass(frozen=True, slots=True)
class SourceAuditRow:
    table_name: str
    source_path: str
    row_count: int


@dataclass(slots=True)
class DuplicateSourceGroup:
    source_key: str
    source_paths: list[str] = field(default_factory=list)
    table_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return sum(self.table_counts.values())


@dataclass(frozen=True, slots=True)
class AliasPathSummary:
    table_name: str
    root_id: str
    alias_path: str
    row_count: int


@dataclass(slots=True)
class DuplicateAuditReport:
    project_id: str
    duplicate_groups: list[DuplicateSourceGroup]
    alias_path_summaries: list[AliasPathSummary]
    table_totals: dict[str, int]

    @property
    def duplicate_group_count(self) -> int:
        return len(self.duplicate_groups)


@dataclass(frozen=True, slots=True)
class SyncStateCandidate:
    source_path: str
    file_hash: str
    file_mtime: float
    last_synced: str
    parse_ms: int
    row_count: int = 1


@dataclass(frozen=True, slots=True)
class SessionSourceCandidate:
    source_path: str
    session_count: int
    updated_at: str
    canonical_message_count: int = 0
    usage_event_count: int = 0
    telemetry_event_count: int = 0
    lineage_complete_count: int = 0


@dataclass(frozen=True, slots=True)
class SourceCollapsePlan:
    source_key: str
    source_paths: tuple[str, ...]
    sync_state_survivor: SyncStateCandidate | None
    session_survivor: SessionSourceCandidate | None
    actions: tuple[str, ...]

    @property
    def loser_paths(self) -> tuple[str, ...]:
        survivor_paths = {
            candidate.source_path
            for candidate in (self.sync_state_survivor, self.session_survivor)
            if candidate is not None
        }
        return tuple(path for path in self.source_paths if path not in survivor_paths)


@dataclass(frozen=True, slots=True)
class CollapseApplyResult:
    project_id: str
    planned_groups: int
    sync_state_upserts: int
    sync_state_deletes: int
    session_updates: int
    relationship_updates: int
    applied: bool


COLLAPSE_STRATEGY = """
Source alias collapse strategy:

1. Scope every run by explicit project id and the same SourceIdentityPolicy used
   by live ingest. Never collapse by suffix-only path matching.
2. Group legacy host/container source paths by canonical source key.
3. Choose the sync_state survivor by newest file_mtime, then newest
   last_synced, then highest parse_ms. Preserve that row's file_hash and mtime
   when upserting the canonical source key.
4. Choose the session survivor by transcript completeness first
   (canonical_message_count), then usage/telemetry evidence, lineage
   completeness, session_count, and updated_at. The apply path updates source
   fields to the canonical source key before deleting duplicate sync_state rows.
5. Apply must run inside one transaction after a dry-run review. Rollback is
   restoring the Postgres volume backup or transaction snapshot captured before
   apply.
""".strip()


AUDIT_QUERY_SPECS: tuple[AuditQuerySpec, ...] = (
    AuditQuerySpec(
        table_name="sync_state",
        sql="""
            SELECT
                'sync_state' AS table_name,
                file_path AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sync_state
            WHERE project_id = $1
              AND entity_type = 'session'
              AND COALESCE(file_path, '') != ''
            GROUP BY file_path
        """,
    ),
    AuditQuerySpec(
        table_name="sessions",
        sql="""
            SELECT
                'sessions' AS table_name,
                source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions
            WHERE project_id = $1
              AND COALESCE(source_file, '') != ''
            GROUP BY source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_logs",
        sql="""
            SELECT
                'session_logs' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_logs sl ON sl.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_messages",
        sql="""
            SELECT
                'session_messages' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_messages sm ON sm.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_tool_usage",
        sql="""
            SELECT
                'session_tool_usage' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_tool_usage stu ON stu.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_file_updates",
        sql="""
            SELECT
                'session_file_updates' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_file_updates sfu ON sfu.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_artifacts",
        sql="""
            SELECT
                'session_artifacts' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_artifacts sa ON sa.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_usage_events",
        sql="""
            SELECT
                'session_usage_events' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_usage_events sue ON sue.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_usage_attributions",
        sql="""
            SELECT
                'session_usage_attributions' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_usage_events sue ON sue.session_id = s.id
            JOIN session_usage_attributions sua ON sua.event_id = sue.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_relationships",
        sql="""
            SELECT
                'session_relationships' AS table_name,
                source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM session_relationships
            WHERE project_id = $1
              AND COALESCE(source_file, '') != ''
            GROUP BY source_file
        """,
    ),
    AuditQuerySpec(
        table_name="telemetry_events",
        sql="""
            SELECT
                'telemetry_events' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN telemetry_events te ON te.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="commit_correlations",
        sql="""
            SELECT
                'commit_correlations' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN commit_correlations cc ON cc.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_sentiment_facts",
        sql="""
            SELECT
                'session_sentiment_facts' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_sentiment_facts ssf ON ssf.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_code_churn_facts",
        sql="""
            SELECT
                'session_code_churn_facts' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_code_churn_facts sccf ON sccf.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
    AuditQuerySpec(
        table_name="session_scope_drift_facts",
        sql="""
            SELECT
                'session_scope_drift_facts' AS table_name,
                s.source_file AS source_path,
                COUNT(*)::bigint AS row_count
            FROM sessions s
            JOIN session_scope_drift_facts ssdf ON ssdf.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        """,
    ),
)


def _canonical_source_key(
    *,
    project_id: str,
    source_path: str,
    policy: SourceIdentityPolicy,
    artifact_kind: SourceArtifactKind = "session",
) -> str:
    if source_path.startswith(CANONICAL_SOURCE_PREFIX):
        return source_path
    identity = resolve_source_identity(
        SourceIdentityInput(
            project_id=ProjectId(project_id),
            observed_path=PurePosixPath(source_path),
            artifact_kind=artifact_kind,
        ),
        policy,
    )
    return str(identity.source_key)


def _matched_alias(source_path: str, policy: SourceIdentityPolicy) -> SourceRootAlias | None:
    if source_path.startswith(CANONICAL_SOURCE_PREFIX):
        return None
    try:
        observed = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("_audit"),
                observed_path=PurePosixPath(source_path),
                artifact_kind="session",
            ),
            policy,
        )
    except ValueError:
        return None
    if str(observed.root_id) == "opaque":
        return None
    aliases = sorted(
        policy.aliases,
        key=lambda alias: len(PurePosixPath(str(alias.alias_path)).parts),
        reverse=True,
    )
    for alias in aliases:
        try:
            PurePosixPath(source_path).relative_to(alias.alias_path)
        except ValueError:
            continue
        if str(alias.root_id) == str(observed.root_id):
            return alias
    return None


def build_duplicate_audit_report(
    *,
    project_id: str,
    rows: Iterable[SourceAuditRow],
    policy: SourceIdentityPolicy,
) -> DuplicateAuditReport:
    groups_by_key: dict[str, DuplicateSourceGroup] = {}
    table_totals: dict[str, int] = {}
    alias_totals: dict[tuple[str, str, str], int] = {}

    for row in rows:
        source_path = str(row.source_path or "").strip()
        if not source_path:
            continue
        row_count = int(row.row_count or 0)
        table_totals[row.table_name] = table_totals.get(row.table_name, 0) + row_count
        source_key = _canonical_source_key(
            project_id=project_id,
            source_path=source_path,
            policy=policy,
        )
        group = groups_by_key.setdefault(source_key, DuplicateSourceGroup(source_key=source_key))
        if source_path not in group.source_paths:
            group.source_paths.append(source_path)
        group.table_counts[row.table_name] = group.table_counts.get(row.table_name, 0) + row_count

        alias = _matched_alias(source_path, policy)
        if alias is not None:
            alias_key = (row.table_name, str(alias.root_id), alias.alias_path.as_posix())
            alias_totals[alias_key] = alias_totals.get(alias_key, 0) + row_count

    duplicate_groups = [
        group
        for group in groups_by_key.values()
        if len(group.source_paths) > 1
    ]
    for group in duplicate_groups:
        group.source_paths.sort()
    duplicate_groups.sort(key=lambda group: (-group.total_rows, group.source_key))

    alias_path_summaries = [
        AliasPathSummary(
            table_name=table_name,
            root_id=root_id,
            alias_path=alias_path,
            row_count=row_count,
        )
        for (table_name, root_id, alias_path), row_count in alias_totals.items()
    ]
    alias_path_summaries.sort(key=lambda item: (item.table_name, item.root_id, item.alias_path))
    return DuplicateAuditReport(
        project_id=project_id,
        duplicate_groups=duplicate_groups,
        alias_path_summaries=alias_path_summaries,
        table_totals=dict(sorted(table_totals.items())),
    )


def _candidate_canonical_key(
    *,
    project_id: str,
    source_path: str,
    policy: SourceIdentityPolicy,
) -> str:
    return _canonical_source_key(
        project_id=project_id,
        source_path=source_path,
        policy=policy,
    )


def _sync_state_sort_key(candidate: SyncStateCandidate) -> tuple[float, str, int, int, str]:
    return (
        float(candidate.file_mtime or 0.0),
        str(candidate.last_synced or ""),
        int(candidate.parse_ms or 0),
        int(candidate.row_count or 0),
        candidate.source_path,
    )


def _session_source_sort_key(candidate: SessionSourceCandidate) -> tuple[int, int, int, int, int, str, str]:
    return (
        int(candidate.canonical_message_count or 0),
        int(candidate.usage_event_count or 0),
        int(candidate.telemetry_event_count or 0),
        int(candidate.lineage_complete_count or 0),
        int(candidate.session_count or 0),
        str(candidate.updated_at or ""),
        candidate.source_path,
    )


def choose_sync_state_survivor(candidates: Iterable[SyncStateCandidate]) -> SyncStateCandidate | None:
    items = list(candidates)
    if not items:
        return None
    return max(items, key=_sync_state_sort_key)


def choose_session_source_survivor(
    candidates: Iterable[SessionSourceCandidate],
) -> SessionSourceCandidate | None:
    items = list(candidates)
    if not items:
        return None
    return max(items, key=_session_source_sort_key)


def build_source_collapse_plans(
    *,
    project_id: str,
    policy: SourceIdentityPolicy,
    sync_state_candidates: Iterable[SyncStateCandidate],
    session_candidates: Iterable[SessionSourceCandidate],
) -> list[SourceCollapsePlan]:
    grouped_sync: dict[str, list[SyncStateCandidate]] = {}
    grouped_sessions: dict[str, list[SessionSourceCandidate]] = {}
    source_paths_by_key: dict[str, set[str]] = {}

    for candidate in sync_state_candidates:
        source_key = _candidate_canonical_key(
            project_id=project_id,
            source_path=candidate.source_path,
            policy=policy,
        )
        grouped_sync.setdefault(source_key, []).append(candidate)
        source_paths_by_key.setdefault(source_key, set()).add(candidate.source_path)

    for candidate in session_candidates:
        source_key = _candidate_canonical_key(
            project_id=project_id,
            source_path=candidate.source_path,
            policy=policy,
        )
        grouped_sessions.setdefault(source_key, []).append(candidate)
        source_paths_by_key.setdefault(source_key, set()).add(candidate.source_path)

    plans: list[SourceCollapsePlan] = []
    for source_key, source_paths in source_paths_by_key.items():
        if len(source_paths) <= 1:
            continue
        sync_survivor = choose_sync_state_survivor(grouped_sync.get(source_key, []))
        session_survivor = choose_session_source_survivor(grouped_sessions.get(source_key, []))
        ordered_paths = tuple(sorted(source_paths))
        actions = [
            "upsert canonical sync_state survivor and delete alias sync_state rows",
            "update sessions.source_file to canonical source key",
            "update session_relationships.source_file to canonical source key",
            "preserve child rows through session_id foreign keys and regenerate telemetry/commit facts on next ingest if needed",
        ]
        plans.append(
            SourceCollapsePlan(
                source_key=source_key,
                source_paths=ordered_paths,
                sync_state_survivor=sync_survivor,
                session_survivor=session_survivor,
                actions=tuple(actions),
            )
        )
    plans.sort(key=lambda plan: plan.source_key)
    return plans


def collapse_plans_as_dict(plans: Iterable[SourceCollapsePlan]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for plan in plans:
        payload.append(
            {
                "sourceKey": plan.source_key,
                "sourcePaths": list(plan.source_paths),
                "syncStateSurvivor": (
                    {
                        "sourcePath": plan.sync_state_survivor.source_path,
                        "fileHash": plan.sync_state_survivor.file_hash,
                        "fileMtime": plan.sync_state_survivor.file_mtime,
                        "lastSynced": plan.sync_state_survivor.last_synced,
                        "parseMs": plan.sync_state_survivor.parse_ms,
                    }
                    if plan.sync_state_survivor
                    else None
                ),
                "sessionSurvivor": (
                    {
                        "sourcePath": plan.session_survivor.source_path,
                        "sessionCount": plan.session_survivor.session_count,
                        "updatedAt": plan.session_survivor.updated_at,
                        "canonicalMessageCount": plan.session_survivor.canonical_message_count,
                        "usageEventCount": plan.session_survivor.usage_event_count,
                        "telemetryEventCount": plan.session_survivor.telemetry_event_count,
                        "lineageCompleteCount": plan.session_survivor.lineage_complete_count,
                    }
                    if plan.session_survivor
                    else None
                ),
                "actions": list(plan.actions),
            }
        )
    return payload


def render_collapse_plan_report(plans: Iterable[SourceCollapsePlan], *, limit: int = 50) -> str:
    items = list(plans)
    lines = [
        "Source alias collapse dry run",
        f"Planned groups: {len(items)}",
        "",
        COLLAPSE_STRATEGY,
    ]
    if not items:
        lines.extend(["", "No duplicate source alias groups require collapse."])
        return "\n".join(lines)

    safe_limit = max(1, int(limit or 50))
    lines.extend(["", "Planned source groups:"])
    for idx, plan in enumerate(items[:safe_limit], start=1):
        lines.append(f"  {idx:02d}. {plan.source_key}")
        for path in plan.source_paths:
            lines.append(f"      sourcePath={path}")
        if plan.sync_state_survivor:
            lines.append(
                "      syncStateSurvivor="
                f"{plan.sync_state_survivor.source_path} "
                f"mtime={plan.sync_state_survivor.file_mtime} "
                f"lastSynced={plan.sync_state_survivor.last_synced}"
            )
        if plan.session_survivor:
            lines.append(
                "      sessionSurvivor="
                f"{plan.session_survivor.source_path} "
                f"sessions={plan.session_survivor.session_count} "
                f"messages={plan.session_survivor.canonical_message_count}"
            )
    remaining = len(items) - safe_limit
    if remaining > 0:
        lines.append(f"  ... {remaining} more groups omitted by --limit")
    return "\n".join(lines)


def _parse_execute_count(result: str) -> int:
    try:
        return int(str(result).split()[-1])
    except (IndexError, ValueError):
        return 0


async def apply_source_collapse_plans(
    conn: Any,
    *,
    project_id: str,
    plans: Iterable[SourceCollapsePlan],
    apply: bool,
) -> CollapseApplyResult:
    items = list(plans)
    if not apply:
        return CollapseApplyResult(
            project_id=project_id,
            planned_groups=len(items),
            sync_state_upserts=sum(1 for item in items if item.sync_state_survivor is not None),
            sync_state_deletes=sum(
                len([path for path in item.source_paths if path != item.source_key])
                for item in items
            ),
            session_updates=sum(
                item.session_survivor.session_count if item.session_survivor else 0
                for item in items
            ),
            relationship_updates=0,
            applied=False,
        )

    sync_state_upserts = 0
    sync_state_deletes = 0
    session_updates = 0
    relationship_updates = 0
    for plan in items:
        alias_paths = [path for path in plan.source_paths if path != plan.source_key]
        if plan.sync_state_survivor is not None:
            await conn.execute(
                """
                INSERT INTO sync_state (
                    file_path, file_hash, file_mtime, entity_type,
                    project_id, last_synced, parse_ms
                ) VALUES ($1, $2, $3, 'session', $4, $5, $6)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_hash = EXCLUDED.file_hash,
                    file_mtime = EXCLUDED.file_mtime,
                    entity_type = EXCLUDED.entity_type,
                    project_id = EXCLUDED.project_id,
                    last_synced = EXCLUDED.last_synced,
                    parse_ms = EXCLUDED.parse_ms
                """,
                plan.source_key,
                plan.sync_state_survivor.file_hash,
                float(plan.sync_state_survivor.file_mtime),
                project_id,
                plan.sync_state_survivor.last_synced,
                int(plan.sync_state_survivor.parse_ms),
            )
            sync_state_upserts += 1
        if alias_paths:
            deleted = await conn.execute(
                """
                DELETE FROM sync_state
                WHERE project_id = $1
                  AND entity_type = 'session'
                  AND file_path = ANY($2::text[])
                """,
                project_id,
                alias_paths,
            )
            sync_state_deletes += _parse_execute_count(deleted)
            updated_sessions = await conn.execute(
                """
                UPDATE sessions
                SET source_file = $1
                WHERE project_id = $2
                  AND source_file = ANY($3::text[])
                  AND source_file <> $1
                """,
                plan.source_key,
                project_id,
                alias_paths,
            )
            session_updates += _parse_execute_count(updated_sessions)
            updated_relationships = await conn.execute(
                """
                UPDATE session_relationships
                SET source_file = $1
                WHERE project_id = $2
                  AND source_file = ANY($3::text[])
                  AND source_file <> $1
                """,
                plan.source_key,
                project_id,
                alias_paths,
            )
            relationship_updates += _parse_execute_count(updated_relationships)

    return CollapseApplyResult(
        project_id=project_id,
        planned_groups=len(items),
        sync_state_upserts=sync_state_upserts,
        sync_state_deletes=sync_state_deletes,
        session_updates=session_updates,
        relationship_updates=relationship_updates,
        applied=True,
    )


def collapse_apply_result_as_dict(result: CollapseApplyResult) -> dict[str, Any]:
    return {
        "projectId": result.project_id,
        "plannedGroups": result.planned_groups,
        "syncStateUpserts": result.sync_state_upserts,
        "syncStateDeletes": result.sync_state_deletes,
        "sessionUpdates": result.session_updates,
        "relationshipUpdates": result.relationship_updates,
        "applied": result.applied,
    }


def render_collapse_apply_result(result: CollapseApplyResult) -> str:
    mode = "applied" if result.applied else "dry-run"
    return "\n".join(
        [
            f"Project: {result.project_id}",
            f"Mode: {mode}",
            f"Planned groups: {result.planned_groups}",
            f"sync_state upserts: {result.sync_state_upserts}",
            f"sync_state deletes: {result.sync_state_deletes}",
            f"sessions updated: {result.session_updates}",
            f"session_relationships updated: {result.relationship_updates}",
        ]
    )


def report_as_dict(report: DuplicateAuditReport) -> dict[str, Any]:
    return {
        "projectId": report.project_id,
        "duplicateGroupCount": report.duplicate_group_count,
        "tableTotals": report.table_totals,
        "aliasPathSummaries": [
            {
                "tableName": item.table_name,
                "rootId": item.root_id,
                "aliasPath": item.alias_path,
                "rowCount": item.row_count,
            }
            for item in report.alias_path_summaries
        ],
        "duplicateGroups": [
            {
                "sourceKey": group.source_key,
                "sourcePaths": group.source_paths,
                "tableCounts": dict(sorted(group.table_counts.items())),
                "totalRows": group.total_rows,
            }
            for group in report.duplicate_groups
        ],
    }


def render_text_report(report: DuplicateAuditReport, *, limit: int = 50) -> str:
    lines = [
        f"Project: {report.project_id}",
        f"Duplicate source groups: {report.duplicate_group_count}",
        "",
        "Table totals:",
    ]
    for table_name, row_count in report.table_totals.items():
        lines.append(f"  {table_name}: {row_count}")

    if report.alias_path_summaries:
        lines.extend(["", "Alias path counts:"])
        for item in report.alias_path_summaries:
            lines.append(
                f"  {item.table_name} root={item.root_id} alias={item.alias_path}: {item.row_count}"
            )

    lines.extend(["", "Duplicate groups:"])
    if not report.duplicate_groups:
        lines.append("  none")
        return "\n".join(lines)

    safe_limit = max(1, int(limit or 50))
    for idx, group in enumerate(report.duplicate_groups[:safe_limit], start=1):
        lines.append(f"  {idx:02d}. {group.source_key}")
        lines.append(f"      totalRows={group.total_rows}")
        lines.append(
            "      tableCounts="
            + ", ".join(f"{name}={count}" for name, count in sorted(group.table_counts.items()))
        )
        for source_path in group.source_paths:
            lines.append(f"      sourcePath={source_path}")
    remaining = len(report.duplicate_groups) - safe_limit
    if remaining > 0:
        lines.append(f"  ... {remaining} more groups omitted by --limit")
    return "\n".join(lines)


def load_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                values[key] = value
    return values


async def fetch_audit_rows(database_url: str, project_id: str) -> list[SourceAuditRow]:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        rows: list[SourceAuditRow] = []
        for spec in AUDIT_QUERY_SPECS:
            fetched = await conn.fetch(spec.sql, project_id)
            for row in fetched:
                rows.append(
                    SourceAuditRow(
                        table_name=str(row["table_name"]),
                        source_path=str(row["source_path"]),
                        row_count=int(row["row_count"]),
                    )
                )
        return rows
    finally:
        await conn.close()


async def fetch_collapse_candidates(conn: Any, project_id: str) -> tuple[list[SyncStateCandidate], list[SessionSourceCandidate]]:
    sync_rows = await conn.fetch(
        """
        SELECT
            file_path,
            file_hash,
            file_mtime,
            last_synced,
            parse_ms,
            COUNT(*)::bigint AS row_count
        FROM sync_state
        WHERE project_id = $1
          AND entity_type = 'session'
          AND COALESCE(file_path, '') != ''
        GROUP BY file_path, file_hash, file_mtime, last_synced, parse_ms
        """,
        project_id,
    )
    session_rows = await conn.fetch(
        """
        WITH sessions_by_source AS (
            SELECT
                source_file,
                COUNT(*)::bigint AS session_count,
                MAX(updated_at) AS updated_at,
                SUM(
                    CASE
                        WHEN COALESCE(thread_kind, '') != ''
                         AND COALESCE(conversation_family_id, '') != ''
                        THEN 1 ELSE 0
                    END
                )::bigint AS lineage_complete_count
            FROM sessions
            WHERE project_id = $1
              AND COALESCE(source_file, '') != ''
            GROUP BY source_file
        ),
        messages_by_source AS (
            SELECT s.source_file, COUNT(sm.*)::bigint AS canonical_message_count
            FROM sessions s
            JOIN session_messages sm ON sm.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        ),
        usage_by_source AS (
            SELECT s.source_file, COUNT(sue.*)::bigint AS usage_event_count
            FROM sessions s
            JOIN session_usage_events sue ON sue.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        ),
        telemetry_by_source AS (
            SELECT s.source_file, COUNT(te.*)::bigint AS telemetry_event_count
            FROM sessions s
            JOIN telemetry_events te ON te.session_id = s.id
            WHERE s.project_id = $1
              AND COALESCE(s.source_file, '') != ''
            GROUP BY s.source_file
        )
        SELECT
            s.source_file,
            s.session_count,
            COALESCE(s.updated_at, '') AS updated_at,
            COALESCE(m.canonical_message_count, 0)::bigint AS canonical_message_count,
            COALESCE(u.usage_event_count, 0)::bigint AS usage_event_count,
            COALESCE(t.telemetry_event_count, 0)::bigint AS telemetry_event_count,
            COALESCE(s.lineage_complete_count, 0)::bigint AS lineage_complete_count
        FROM sessions_by_source s
        LEFT JOIN messages_by_source m ON m.source_file = s.source_file
        LEFT JOIN usage_by_source u ON u.source_file = s.source_file
        LEFT JOIN telemetry_by_source t ON t.source_file = s.source_file
        """,
        project_id,
    )
    return (
        [
            SyncStateCandidate(
                source_path=str(row["file_path"]),
                file_hash=str(row["file_hash"] or ""),
                file_mtime=float(row["file_mtime"] or 0.0),
                last_synced=str(row["last_synced"] or ""),
                parse_ms=int(row["parse_ms"] or 0),
                row_count=int(row["row_count"] or 0),
            )
            for row in sync_rows
        ],
        [
            SessionSourceCandidate(
                source_path=str(row["source_file"]),
                session_count=int(row["session_count"] or 0),
                updated_at=str(row["updated_at"] or ""),
                canonical_message_count=int(row["canonical_message_count"] or 0),
                usage_event_count=int(row["usage_event_count"] or 0),
                telemetry_event_count=int(row["telemetry_event_count"] or 0),
                lineage_complete_count=int(row["lineage_complete_count"] or 0),
            )
            for row in session_rows
        ],
    )


async def fetch_collapse_plans(
    *,
    database_url: str,
    project_id: str,
    policy: SourceIdentityPolicy,
) -> list[SourceCollapsePlan]:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        sync_candidates, session_candidates = await fetch_collapse_candidates(conn, project_id)
        return build_source_collapse_plans(
            project_id=project_id,
            policy=policy,
            sync_state_candidates=sync_candidates,
            session_candidates=session_candidates,
        )
    finally:
        await conn.close()


async def apply_collapse_to_database(
    *,
    database_url: str,
    project_id: str,
    policy: SourceIdentityPolicy,
) -> CollapseApplyResult:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            sync_candidates, session_candidates = await fetch_collapse_candidates(conn, project_id)
            plans = build_source_collapse_plans(
                project_id=project_id,
                policy=policy,
                sync_state_candidates=sync_candidates,
                session_candidates=session_candidates,
            )
            return await apply_source_collapse_plans(
                conn,
                project_id=project_id,
                plans=plans,
                apply=True,
            )
    finally:
        await conn.close()


async def _run(args: argparse.Namespace) -> int:
    env: Mapping[str, str] = os.environ
    if args.env_file:
        values = dict(os.environ)
        values.update(load_env_file(args.env_file))
        env = values

    if args.strategy:
        print(COLLAPSE_STRATEGY)
        return 0

    database_url = args.database_url or env.get("CCDASH_DATABASE_URL") or ""
    if not database_url:
        print("Missing database URL. Set CCDASH_DATABASE_URL or pass --database-url.")
        return 1

    try:
        policy = source_identity_policy_from_env(env)
        if args.collapse_plan or args.apply_collapse:
            if args.apply_collapse:
                result = await apply_collapse_to_database(
                    database_url=database_url,
                    project_id=args.project,
                    policy=policy,
                )
                if args.json:
                    print(json.dumps(collapse_apply_result_as_dict(result), indent=2))
                else:
                    print(render_collapse_apply_result(result))
                return 0

            plans = await fetch_collapse_plans(
                database_url=database_url,
                project_id=args.project,
                policy=policy,
            )
            dry_run = await apply_source_collapse_plans(
                None,
                project_id=args.project,
                plans=plans,
                apply=False,
            )
            if args.json:
                print(
                    json.dumps(
                        {
                            "apply": collapse_apply_result_as_dict(dry_run),
                            "plans": collapse_plans_as_dict(plans),
                        },
                        indent=2,
                    )
                )
            else:
                print(render_collapse_apply_result(dry_run))
                print("")
                print(render_collapse_plan_report(plans, limit=args.limit))
            return 0

        rows = await fetch_audit_rows(database_url, args.project)
        report = build_duplicate_audit_report(project_id=args.project, rows=rows, policy=policy)
    except Exception as exc:
        print(f"Duplicate audit query failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(report_as_dict(report), indent=2))
    else:
        print(render_text_report(report, limit=args.limit))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit host/container source alias duplicates.")
    parser.add_argument("--project", required=True, help="Project ID to audit.")
    parser.add_argument("--database-url", default="", help="Postgres connection URL. Defaults to CCDASH_DATABASE_URL.")
    parser.add_argument("--env-file", default="", help="Optional env file with source alias root settings.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum duplicate groups to print in text output.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--strategy", action="store_true", help="Print the collapse strategy and exit.")
    parser.add_argument("--collapse-plan", action="store_true", help="Print dry-run source alias collapse actions.")
    parser.add_argument("--apply-collapse", action="store_true", help="Apply source alias collapse in one transaction.")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
