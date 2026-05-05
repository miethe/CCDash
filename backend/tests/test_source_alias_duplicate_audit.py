from __future__ import annotations

import unittest
from pathlib import PurePosixPath

from backend.scripts.source_alias_duplicate_audit import (
    AUDIT_QUERY_SPECS,
    SourceAuditRow,
    build_duplicate_audit_report,
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


if __name__ == "__main__":
    unittest.main()
