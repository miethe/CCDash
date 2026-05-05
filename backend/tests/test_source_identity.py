from pathlib import PurePosixPath
import unittest

from backend.services.source_identity import (
    ProjectId,
    SourceIdentityInput,
    SourceRootId,
    resolve_source_identity,
    source_identity_policy_from_env,
)


class SourceIdentityPolicyTests(unittest.TestCase):
    def test_claude_host_and_container_paths_share_source_key(self) -> None:
        policy = source_identity_policy_from_env(
            {
                "CCDASH_CLAUDE_HOME": "/Users/miethe/.claude",
                "CCDASH_CLAUDE_CONTAINER_HOME": "/home/ccdash/.claude",
            }
        )

        host = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("skillmeat"),
                artifact_kind="session",
                observed_path=PurePosixPath(
                    "/Users/miethe/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat/session.jsonl"
                ),
            ),
            policy,
        )
        container = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("skillmeat"),
                artifact_kind="session",
                observed_path=PurePosixPath(
                    "/home/ccdash/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat/session.jsonl"
                ),
            ),
            policy,
        )

        self.assertEqual(host.source_key, container.source_key)
        self.assertEqual(host.root_id, SourceRootId("claude_home"))
        self.assertEqual(host.relative_path, container.relative_path)

    def test_codex_host_and_container_paths_share_source_key(self) -> None:
        policy = source_identity_policy_from_env(
            {
                "CCDASH_CODEX_HOME": "/Users/miethe/.codex",
                "CCDASH_CODEX_CONTAINER_HOME": "/home/ccdash/.codex",
            }
        )

        host = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("ccdash"),
                artifact_kind="session",
                observed_path=PurePosixPath("/Users/miethe/.codex/sessions/2026/05/session.jsonl"),
            ),
            policy,
        )
        container = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("ccdash"),
                artifact_kind="session",
                observed_path=PurePosixPath("/home/ccdash/.codex/sessions/2026/05/session.jsonl"),
            ),
            policy,
        )

        self.assertEqual(host.source_key, container.source_key)
        self.assertEqual(host.root_id, SourceRootId("codex_home"))

    def test_workspace_host_and_container_paths_share_source_key(self) -> None:
        policy = source_identity_policy_from_env(
            {
                "CCDASH_WORKSPACE_HOST_ROOT": "/Users/miethe/dev/homelab/development",
                "CCDASH_WORKSPACE_CONTAINER_ROOT": "/workspace",
            }
        )

        host = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("ccdash"),
                artifact_kind="document",
                observed_path=PurePosixPath(
                    "/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/plan.md"
                ),
            ),
            policy,
        )
        container = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("ccdash"),
                artifact_kind="document",
                observed_path=PurePosixPath("/workspace/CCDash/docs/project_plans/plan.md"),
            ),
            policy,
        )

        self.assertEqual(host.source_key, container.source_key)
        self.assertEqual(host.root_id, SourceRootId("workspace"))

    def test_unknown_paths_are_stable_but_project_scoped(self) -> None:
        policy = source_identity_policy_from_env({})
        observed_path = PurePosixPath("/var/tmp/session.jsonl")

        first = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("project-a"),
                artifact_kind="session",
                observed_path=observed_path,
            ),
            policy,
        )
        second = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("project-a"),
                artifact_kind="session",
                observed_path=observed_path,
            ),
            policy,
        )
        other_project = resolve_source_identity(
            SourceIdentityInput(
                project_id=ProjectId("project-b"),
                artifact_kind="session",
                observed_path=observed_path,
            ),
            policy,
        )

        self.assertEqual(first.source_key, second.source_key)
        self.assertNotEqual(first.source_key, other_project.source_key)
        self.assertEqual(first.root_id, SourceRootId("opaque"))


if __name__ == "__main__":
    unittest.main()
