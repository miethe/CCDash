from __future__ import annotations

import unittest
from pathlib import PurePosixPath

from backend.scripts.source_alias_duplicate_audit import (
    AUDIT_QUERY_SPECS,
    COLLAPSE_STRATEGY,
    SessionSourceCandidate,
    SourceAuditRow,
    SyncStateCandidate,
    build_duplicate_audit_report,
    build_source_collapse_plans,
    choose_session_source_survivor,
    choose_sync_state_survivor,
    render_text_report,
    report_as_dict,
)
from backend.services.source_identity import SourceIdentityPolicy, SourceRootAlias, SourceRootId


def _policy() -> SourceIdentityPolicy:
    return SourceIdentityPolicy(
        aliases=(
            SourceRootAlias(
                root_id=SourceRootId("claude_home"),
                alias_path=PurePosixPath("/Users/miethe/.claude"),
            ),
            SourceRootAlias(
                root_id=SourceRootId("claude_home"),
                alias_path=PurePosixPath("/home/ccdash/.claude"),
            ),
        )
    )


class SourceAliasDuplicateAuditTests(unittest.TestCase):
    def test_groups_host_container_aliases_by_canonical_source_key(self) -> None:
        rows = [
            SourceAuditRow("sync_state", "/Users/miethe/.claude/projects/foo/session.jsonl", 1),
            SourceAuditRow("sync_state", "/home/ccdash/.claude/projects/foo/session.jsonl", 1),
            SourceAuditRow("sessions", "/Users/miethe/.claude/projects/foo/session.jsonl", 2),
            SourceAuditRow("sessions", "/home/ccdash/.claude/projects/foo/session.jsonl", 3),
            SourceAuditRow("session_messages", "/home/ccdash/.claude/projects/foo/session.jsonl", 12),
        ]

        report = build_duplicate_audit_report(project_id="project-1", rows=rows, policy=_policy())

        self.assertEqual(report.duplicate_group_count, 1)
        group = report.duplicate_groups[0]
        self.assertEqual(
            group.source_key,
            "ccdash-source:v1/project-1/session/claude_home/projects/foo/session.jsonl",
        )
        self.assertEqual(
            group.source_paths,
            [
                "/Users/miethe/.claude/projects/foo/session.jsonl",
                "/home/ccdash/.claude/projects/foo/session.jsonl",
            ],
        )
        self.assertEqual(group.table_counts["sync_state"], 2)
        self.assertEqual(group.table_counts["sessions"], 5)
        self.assertEqual(group.table_counts["session_messages"], 12)

    def test_unknown_singletons_do_not_report_as_alias_duplicates(self) -> None:
        rows = [
            SourceAuditRow("sync_state", "/tmp/one.jsonl", 1),
            SourceAuditRow("sessions", "/tmp/two.jsonl", 1),
        ]

        report = build_duplicate_audit_report(project_id="project-1", rows=rows, policy=_policy())

        self.assertEqual(report.duplicate_group_count, 0)
        self.assertEqual(report.table_totals, {"sessions": 1, "sync_state": 1})

    def test_alias_path_summaries_preserve_investigation_style_counts(self) -> None:
        rows = [
            SourceAuditRow("sessions", "/Users/miethe/.claude/projects/foo/a.jsonl", 1809),
            SourceAuditRow("sessions", "/home/ccdash/.claude/projects/foo/a.jsonl", 4106),
            SourceAuditRow("sync_state", "/Users/miethe/.claude/projects/foo/a.jsonl", 5603),
            SourceAuditRow("sync_state", "/home/ccdash/.claude/projects/foo/a.jsonl", 4077),
        ]

        report = build_duplicate_audit_report(project_id="project-1", rows=rows, policy=_policy())
        payload = report_as_dict(report)

        summaries = {
            (item["tableName"], item["aliasPath"]): item["rowCount"]
            for item in payload["aliasPathSummaries"]
        }
        self.assertEqual(summaries[("sessions", "/Users/miethe/.claude")], 1809)
        self.assertEqual(summaries[("sessions", "/home/ccdash/.claude")], 4106)
        self.assertEqual(summaries[("sync_state", "/Users/miethe/.claude")], 5603)
        self.assertEqual(summaries[("sync_state", "/home/ccdash/.claude")], 4077)

    def test_text_report_lists_duplicates_without_failing_on_them(self) -> None:
        report = build_duplicate_audit_report(
            project_id="project-1",
            rows=[
                SourceAuditRow("sync_state", "/Users/miethe/.claude/projects/foo/session.jsonl", 1),
                SourceAuditRow("sync_state", "/home/ccdash/.claude/projects/foo/session.jsonl", 1),
            ],
            policy=_policy(),
        )

        text = render_text_report(report)

        self.assertIn("Duplicate source groups: 1", text)
        self.assertIn("sourcePath=/Users/miethe/.claude/projects/foo/session.jsonl", text)
        self.assertIn("sourcePath=/home/ccdash/.claude/projects/foo/session.jsonl", text)

    def test_audit_queries_are_project_scoped(self) -> None:
        spec_names = {spec.table_name for spec in AUDIT_QUERY_SPECS}

        self.assertIn("sync_state", spec_names)
        self.assertIn("sessions", spec_names)
        self.assertIn("session_messages", spec_names)
        self.assertIn("telemetry_events", spec_names)
        self.assertIn("session_usage_attributions", spec_names)
        for spec in AUDIT_QUERY_SPECS:
            self.assertIn("$1", spec.sql, spec.table_name)

    def test_sync_state_survivor_prefers_newest_mtime_then_synced_evidence(self) -> None:
        survivor = choose_sync_state_survivor(
            [
                SyncStateCandidate("/host/session.jsonl", "old", 10.0, "2026-05-04T10:00:00Z", 500),
                SyncStateCandidate("/container/session.jsonl", "new", 20.0, "2026-05-04T09:00:00Z", 100),
                SyncStateCandidate("/other/session.jsonl", "tie", 20.0, "2026-05-04T11:00:00Z", 10),
            ]
        )

        self.assertIsNotNone(survivor)
        self.assertEqual(survivor.source_path, "/other/session.jsonl")
        self.assertEqual(survivor.file_hash, "tie")

    def test_session_survivor_prefers_transcript_and_derived_evidence(self) -> None:
        survivor = choose_session_source_survivor(
            [
                SessionSourceCandidate(
                    "/host/session.jsonl",
                    session_count=2,
                    updated_at="2026-05-04T12:00:00Z",
                    canonical_message_count=4,
                    usage_event_count=5,
                ),
                SessionSourceCandidate(
                    "/container/session.jsonl",
                    session_count=1,
                    updated_at="2026-05-04T09:00:00Z",
                    canonical_message_count=12,
                    telemetry_event_count=3,
                ),
            ]
        )

        self.assertIsNotNone(survivor)
        self.assertEqual(survivor.source_path, "/container/session.jsonl")

    def test_build_source_collapse_plans_requires_alias_groups_and_project_scope(self) -> None:
        plans = build_source_collapse_plans(
            project_id="project-1",
            policy=_policy(),
            sync_state_candidates=[
                SyncStateCandidate(
                    "/Users/miethe/.claude/projects/foo/session.jsonl",
                    "host-hash",
                    10.0,
                    "2026-05-04T10:00:00Z",
                    100,
                ),
                SyncStateCandidate(
                    "/home/ccdash/.claude/projects/foo/session.jsonl",
                    "container-hash",
                    20.0,
                    "2026-05-04T11:00:00Z",
                    200,
                ),
            ],
            session_candidates=[
                SessionSourceCandidate(
                    "/Users/miethe/.claude/projects/foo/session.jsonl",
                    session_count=1,
                    updated_at="2026-05-04T10:00:00Z",
                    canonical_message_count=1,
                ),
                SessionSourceCandidate(
                    "/home/ccdash/.claude/projects/foo/session.jsonl",
                    session_count=1,
                    updated_at="2026-05-04T11:00:00Z",
                    canonical_message_count=2,
                ),
            ],
        )

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(
            plan.source_key,
            "ccdash-source:v1/project-1/session/claude_home/projects/foo/session.jsonl",
        )
        self.assertEqual(plan.sync_state_survivor.source_path, "/home/ccdash/.claude/projects/foo/session.jsonl")
        self.assertEqual(plan.session_survivor.source_path, "/home/ccdash/.claude/projects/foo/session.jsonl")
        self.assertIn("update sessions.source_file", "\n".join(plan.actions))

    def test_collapse_strategy_documents_dry_run_project_scope_and_rollback(self) -> None:
        self.assertIn("explicit project id", COLLAPSE_STRATEGY)
        self.assertIn("dry-run", COLLAPSE_STRATEGY)
        self.assertIn("Rollback", COLLAPSE_STRATEGY)


if __name__ == "__main__":
    unittest.main()
