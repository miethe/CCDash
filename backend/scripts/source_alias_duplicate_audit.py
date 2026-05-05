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


async def _run(args: argparse.Namespace) -> int:
    env: Mapping[str, str] = os.environ
    if args.env_file:
        values = dict(os.environ)
        values.update(load_env_file(args.env_file))
        env = values

    database_url = args.database_url or env.get("CCDASH_DATABASE_URL") or ""
    if not database_url:
        print("Missing database URL. Set CCDASH_DATABASE_URL or pass --database-url.")
        return 1

    try:
        rows = await fetch_audit_rows(database_url, args.project)
        report = build_duplicate_audit_report(
            project_id=args.project,
            rows=rows,
            policy=source_identity_policy_from_env(env),
        )
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
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
